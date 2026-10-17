"""Notification Service — durable dispatch and privacy orchestration for farmer SMS alerts."""

import hashlib
import re
from typing import Any, Dict, List, Optional

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.repositories.notification_repository import (
    NotificationRepository,
    notification_repository as default_notification_repo,
)
from backend.app.services.notification.provider import (
    BaseSmsProvider,
    BaseWhatsAppProvider,
    ProviderSendStatus,
    TwilioSmsProvider,
    TwilioWhatsAppProvider,
)


def mask_phone_number(phone: str) -> str:
    """Mask phone number preserving leading country code and trailing 4 digits.
    
    Example: '+919876543210' -> '+91******3210'
    """
    clean = re.sub(r"[^\d+]", "", phone.strip())
    if len(clean) <= 6:
        return "******"
    prefix = clean[:3]
    suffix = clean[-4:]
    masked_count = len(clean) - 7
    return f"{prefix}{'*' * max(3, masked_count)}{suffix}"


def is_valid_e164(phone: str) -> bool:
    """Validate standard E.164 phone number format (+[1-9][0-9]{6,14})."""
    pattern = r"^\+[1-9]\d{6,14}$"
    return bool(re.match(pattern, phone.strip()))


def generate_idempotency_key(alert_id: str, user_id: str, alert_type: str, channel: str = "sms") -> str:
    """Generate a deterministic idempotency key for an alert dispatch per channel.
    
    Ties the key strictly to the alert instance, recipient, and channel so repeated
    inferences cannot trigger multiple dispatches, while allowing independent SMS and WhatsApp sends.
    """
    raw = f"alert:{alert_id}:user:{user_id}:type:{alert_type}:channel:{channel}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class NotificationService:
    """Coordinates SMS and WhatsApp alert dispatches with privacy checks and idempotency."""

    def __init__(
        self,
        repository: Optional[NotificationRepository] = None,
        sms_provider: Optional[BaseSmsProvider] = None,
        whatsapp_provider: Optional[BaseWhatsAppProvider] = None,
    ) -> None:
        self.repository = repository or default_notification_repo
        self.sms_provider = sms_provider or TwilioSmsProvider()
        self.whatsapp_provider = whatsapp_provider or TwilioWhatsAppProvider()
        # Backward compatibility alias
        self.provider = self.sms_provider

    def format_alert_sms(
        self,
        farm_name: str,
        alert_type: str,
        severity: str,
        risk_probability: Optional[float],
        recommended_action: Optional[str] = None,
        language: str = "en",
    ) -> str:
        """Format a clear, concise SMS for farmers without exposing internal technical jargon."""
        risk_pct = f"{round(risk_probability * 100)}%" if risk_probability is not None else "High"
        sev_label = severity.upper()

        if alert_type == "RISK_THRESHOLD_CROSSED":
            headline = f"CropAI Alert [{sev_label}]: Crop failure risk on '{farm_name}' has reached {risk_pct}."
        elif alert_type == "RISK_TREND_INCREASING":
            headline = f"CropAI Alert [{sev_label}]: Rapidly escalating risk detected on '{farm_name}' ({risk_pct})."
        elif alert_type in ("SATELLITE_STALE", "WEATHER_STALE", "TELEMETRY_DEGRADATION"):
            headline = f"CropAI Warning: Telemetry gap on '{farm_name}'. Ground checks advised."
        else:
            headline = f"CropAI Advisory for '{farm_name}': Current risk is {risk_pct}."

        action_text = f" Action: {recommended_action[:100]}" if recommended_action else " View your CropAI dashboard for details."
        return f"{headline}{action_text}"

    def dispatch_alert_sms(
        self,
        user_id: str,
        phone_number: Optional[str],
        sms_consent: bool,
        farm_name: str,
        alert: Dict[str, Any],
        farm_id: Optional[str] = None,
        prediction_id: Optional[str] = None,
        user_token: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Safely attempt to dispatch an SMS alert.
        
        Guarantees:
          1. Does NOT dispatch if SMS_ENABLED is false.
          2. Does NOT dispatch if user has not explicitly opted in (sms_consent=False).
          3. Does NOT dispatch if phone number is invalid or missing.
          4. Idempotent: Skips dispatch if idempotency key already exists.
          5. If an ambiguous timeout occurs, tags status as 'reconciliation_required'
             and refuses to blindly resend.
          6. Returns dispatch record, never raises an uncaught exception to caller.
        """
        # Guard 1: SMS globally enabled
        if not settings.SMS_ENABLED:
            logger.info("SMS dispatch skipped: SMS_ENABLED is false.")
            return None

        # Guard 2: Explicit farmer opt-in consent
        if not sms_consent:
            logger.info("SMS dispatch skipped: User %s has not opted in to SMS.", user_id)
            return None

        # Guard 3: Phone number existence and E.164 validity
        if not phone_number or not is_valid_e164(phone_number):
            logger.warning(
                "SMS dispatch skipped: User %s has invalid or missing phone number.",
                user_id,
            )
            return None

        alert_id = str(alert.get("id"))
        alert_type = str(alert.get("alert_type", "GENERAL"))
        idempotency_key = generate_idempotency_key(alert_id, user_id, alert_type, channel="sms")

        # Guard 4: Idempotency check against existing records
        try:
            existing = self.repository.get_by_idempotency_key(idempotency_key, user_token=user_token)
            if existing:
                logger.info(
                    "SMS dispatch skipped: Alert %s already has dispatch record %s (status: %s).",
                    alert_id,
                    existing.get("id"),
                    existing.get("status"),
                )
                return existing
        except Exception as err:
            logger.error("Could not query existing dispatch record: %s", err)
            # Failure isolation: Do not block, but do not risk blind duplicate
            return None

        # Format message and mask phone number
        masked_phone = mask_phone_number(phone_number)
        message_body = self.format_alert_sms(
            farm_name=farm_name,
            alert_type=alert_type,
            severity=alert.get("severity", "warning"),
            risk_probability=alert.get("risk_probability"),
            recommended_action=alert.get("recommended_action"),
        )

        # Create durable queued record in repository
        try:
            dispatch_record = self.repository.create_dispatch(
                user_id=user_id,
                phone_number_masked=masked_phone,
                message_body=message_body,
                idempotency_key=idempotency_key,
                channel="sms",
                farm_id=farm_id,
                alert_id=alert_id,
                prediction_id=prediction_id,
                provider="twilio",
                user_token=user_token,
            )
        except Exception as err:
            logger.error("Failed to create durable dispatch record for alert %s: %s", alert_id, err)
            return None

        dispatch_id = dispatch_record["id"]

        # Attempt provider delivery
        try:
            result = self.sms_provider.send_sms(
                to_phone=phone_number,
                message=message_body,
                idempotency_key=idempotency_key,
            )

            if result.status == ProviderSendStatus.ACCEPTED:
                # Crucial: Provider accepted -> mark 'submitted', NOT 'delivered'
                return self.repository.update_status(
                    dispatch_id=dispatch_id,
                    status="submitted",
                    provider_message_id=result.provider_message_id,
                    user_token=user_token,
                )
            elif result.status == ProviderSendStatus.UNKNOWN_TIMEOUT:
                # Ambiguous timeout: Mark reconciliation required, DO NOT blindly resend
                return self.repository.update_status(
                    dispatch_id=dispatch_id,
                    status="reconciliation_required",
                    error_code=result.error_code,
                    error_message_sanitized="Provider request timed out; awaiting reconciliation.",
                    increment_retry=True,
                    user_token=user_token,
                )
            else:
                # Explicit provider rejection
                return self.repository.update_status(
                    dispatch_id=dispatch_id,
                    status="failed",
                    error_code=result.error_code,
                    error_message_sanitized=result.error_message,
                    increment_retry=True,
                    user_token=user_token,
                )
        except Exception as err:
            logger.error("Unexpected exception during SMS dispatch: %s", err)
            try:
                return self.repository.update_status(
                    dispatch_id=dispatch_id,
                    status="failed",
                    error_code="INTERNAL_EXCEPTION",
                    error_message_sanitized=str(err)[:200],
                    increment_retry=True,
                    user_token=user_token,
                )
            except Exception:
                return dispatch_record

    def dispatch_alert_whatsapp(
        self,
        user_id: str,
        phone_number: Optional[str],
        whatsapp_consent: bool,
        farm_name: str,
        alert: Dict[str, Any],
        farm_id: Optional[str] = None,
        prediction_id: Optional[str] = None,
        content_sid: Optional[str] = None,
        user_token: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Safely attempt to dispatch a WhatsApp alert.

        Guarantees:
          1. Does NOT dispatch if WHATSAPP_ENABLED is false.
          2. Does NOT dispatch if user has not explicitly opted in (whatsapp_consent=False).
          3. Does NOT dispatch if phone number is invalid or missing.
          4. Idempotent per channel: Skips dispatch if idempotency key already exists.
          5. Respects Twilio trial template parameters when ContentSid is configured.
          6. If an ambiguous timeout occurs, tags status as 'reconciliation_required'
             and refuses to blindly resend.
          7. Returns dispatch record, never raises an uncaught exception to caller.
        """
        # Guard 1: WhatsApp globally enabled
        if not settings.WHATSAPP_ENABLED:
            logger.info("WhatsApp dispatch skipped: WHATSAPP_ENABLED is false.")
            return None

        # Guard 2: Explicit farmer opt-in consent
        if not whatsapp_consent:
            logger.info("WhatsApp dispatch skipped: User %s has not opted in to WhatsApp.", user_id)
            return None

        # Guard 3: Phone number existence and E.164 validity
        if not phone_number or not is_valid_e164(phone_number):
            logger.warning(
                "WhatsApp dispatch skipped: User %s has invalid or missing phone number.",
                user_id,
            )
            return None

        alert_id = str(alert.get("id"))
        alert_type = str(alert.get("alert_type", "GENERAL"))
        idempotency_key = generate_idempotency_key(alert_id, user_id, alert_type, channel="whatsapp")

        # Guard 4: Idempotency check against existing records
        try:
            existing = self.repository.get_by_idempotency_key(idempotency_key, user_token=user_token)
            if existing:
                logger.info(
                    "WhatsApp dispatch skipped: Alert %s already has dispatch record %s (status: %s).",
                    alert_id,
                    existing.get("id"),
                    existing.get("status"),
                )
                return existing
        except Exception as err:
            logger.error("Could not query existing dispatch record: %s", err)
            return None

        # Format message and variables for WhatsApp template
        masked_phone = mask_phone_number(phone_number)
        message_body = self.format_alert_sms(
            farm_name=farm_name,
            alert_type=alert_type,
            severity=alert.get("severity", "warning"),
            risk_probability=alert.get("risk_probability"),
            recommended_action=alert.get("recommended_action"),
        )
        risk_pct = f"{round(alert.get('risk_probability', 0.0) * 100)}%" if alert.get("risk_probability") is not None else "High"
        content_variables = {
            "1": farm_name,
            "2": alert.get("severity", "warning").upper(),
            "3": risk_pct,
        }

        # Create durable queued record in repository
        try:
            dispatch_record = self.repository.create_dispatch(
                user_id=user_id,
                phone_number_masked=masked_phone,
                message_body=message_body,
                idempotency_key=idempotency_key,
                channel="whatsapp",
                farm_id=farm_id,
                alert_id=alert_id,
                prediction_id=prediction_id,
                provider="twilio",
                user_token=user_token,
            )
        except Exception as err:
            logger.error("Failed to create durable WhatsApp dispatch record for alert %s: %s", alert_id, err)
            return None

        dispatch_id = dispatch_record["id"]

        # Attempt provider delivery
        try:
            result = self.whatsapp_provider.send_whatsapp(
                to_phone=phone_number,
                message=message_body,
                content_sid=content_sid,
                content_variables=content_variables,
                idempotency_key=idempotency_key,
            )

            if result.status == ProviderSendStatus.ACCEPTED:
                return self.repository.update_status(
                    dispatch_id=dispatch_id,
                    status="submitted",
                    provider_message_id=result.provider_message_id,
                    user_token=user_token,
                )
            elif result.status == ProviderSendStatus.UNKNOWN_TIMEOUT:
                return self.repository.update_status(
                    dispatch_id=dispatch_id,
                    status="reconciliation_required",
                    error_code=result.error_code,
                    error_message_sanitized="WhatsApp provider request timed out; awaiting reconciliation.",
                    increment_retry=True,
                    user_token=user_token,
                )
            else:
                return self.repository.update_status(
                    dispatch_id=dispatch_id,
                    status="failed",
                    error_code=result.error_code,
                    error_message_sanitized=result.error_message,
                    increment_retry=True,
                    user_token=user_token,
                )
        except Exception as err:
            logger.error("Unexpected exception during WhatsApp dispatch: %s", err)
            try:
                return self.repository.update_status(
                    dispatch_id=dispatch_id,
                    status="failed",
                    error_code="INTERNAL_EXCEPTION",
                    error_message_sanitized=str(err)[:200],
                    increment_retry=True,
                    user_token=user_token,
                )
            except Exception:
                return dispatch_record


notification_service = NotificationService()
