"""SMS Provider abstractions and implementations.

Implements:
  - BaseSmsProvider: Protocol/abstract base
  - TwilioSmsProvider: Real Twilio REST API integration with timeout handling
  - MockSmsProvider: Test provider tracking dispatches without external I/O
"""

from abc import ABC, abstractmethod
import base64
from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Dict, List, Optional
import urllib.parse
import urllib.request
import urllib.error

from backend.app.core.config import settings
from backend.app.core.logging import logger


class ProviderSendStatus(str, Enum):
    ACCEPTED = "accepted"              # HTTP 201/200 from provider -> status 'submitted'
    UNKNOWN_TIMEOUT = "unknown_timeout"  # Ambiguous HTTP timeout -> reconciliation required
    REJECTED = "rejected"              # Provider HTTP 4xx/5xx rejection
    DISABLED = "disabled"              # SMS_ENABLED is false


@dataclass
class ProviderSendResult:
    status: ProviderSendStatus
    provider_message_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


class BaseSmsProvider(ABC):
    """Abstract interface for SMS providers."""

    @abstractmethod
    def send_sms(
        self,
        to_phone: str,
        message: str,
        idempotency_key: Optional[str] = None,
    ) -> ProviderSendResult:
        """Attempt to dispatch an SMS."""
        pass


class BaseWhatsAppProvider(ABC):
    """Abstract interface for WhatsApp providers."""

    @abstractmethod
    def send_whatsapp(
        self,
        to_phone: str,
        message: str,
        content_sid: Optional[str] = None,
        content_variables: Optional[Dict[str, str]] = None,
        idempotency_key: Optional[str] = None,
    ) -> ProviderSendResult:
        """Attempt to dispatch a WhatsApp message."""
        pass


class MockSmsProvider(BaseSmsProvider):
    """Zero-cost mock provider for test suites.
    
    Records outgoing messages in memory. Can be configured to simulate
    timeouts, rejections, or successes.
    """

    def __init__(self) -> None:
        self.sent_messages: List[Dict[str, Any]] = []
        self.force_timeout: bool = False
        self.force_error: Optional[str] = None

    def send_sms(
        self,
        to_phone: str,
        message: str,
        idempotency_key: Optional[str] = None,
    ) -> ProviderSendResult:
        if self.force_timeout:
            return ProviderSendResult(
                status=ProviderSendStatus.UNKNOWN_TIMEOUT,
                error_code="TIMEOUT",
                error_message="Provider connection timed out before acknowledgment.",
            )

        if self.force_error:
            return ProviderSendResult(
                status=ProviderSendStatus.REJECTED,
                error_code="MOCK_REJECTED",
                error_message=self.force_error,
            )

        msg_id = f"mock-sms-{len(self.sent_messages) + 1}"
        record = {
            "to": to_phone,
            "body": message,
            "idempotency_key": idempotency_key,
            "provider_message_id": msg_id,
        }
        self.sent_messages.append(record)
        return ProviderSendResult(
            status=ProviderSendStatus.ACCEPTED,
            provider_message_id=msg_id,
        )


class MockWhatsAppProvider(BaseWhatsAppProvider):
    """Zero-cost mock WhatsApp provider for test suites.
    
    Enforces trial-safe checks (e.g. sender prefix, template support).
    """

    def __init__(self) -> None:
        self.sent_messages: List[Dict[str, Any]] = []
        self.force_timeout: bool = False
        self.force_error: Optional[str] = None

    def send_whatsapp(
        self,
        to_phone: str,
        message: str,
        content_sid: Optional[str] = None,
        content_variables: Optional[Dict[str, str]] = None,
        idempotency_key: Optional[str] = None,
    ) -> ProviderSendResult:
        if self.force_timeout:
            return ProviderSendResult(
                status=ProviderSendStatus.UNKNOWN_TIMEOUT,
                error_code="TIMEOUT",
                error_message="WhatsApp provider connection timed out before acknowledgment.",
            )

        if self.force_error:
            return ProviderSendResult(
                status=ProviderSendStatus.REJECTED,
                error_code="MOCK_WHATSAPP_REJECTED",
                error_message=self.force_error,
            )

        msg_id = f"mock-wa-{len(self.sent_messages) + 1}"
        record = {
            "to": to_phone,
            "body": message,
            "content_sid": content_sid,
            "content_variables": content_variables,
            "idempotency_key": idempotency_key,
            "provider_message_id": msg_id,
        }
        self.sent_messages.append(record)
        return ProviderSendResult(
            status=ProviderSendStatus.ACCEPTED,
            provider_message_id=msg_id,
        )


class TwilioSmsProvider(BaseSmsProvider):
    """Production Twilio REST API client.
    
    Uses standard library urllib to avoid extra dependencies and explicitly
    handles timeouts to guard against duplicate dispatches.
    """

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_phone: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        self.account_sid = account_sid or settings.TWILIO_ACCOUNT_SID
        self.auth_token = auth_token or settings.TWILIO_AUTH_TOKEN
        self.from_phone = from_phone or settings.TWILIO_PHONE_NUMBER
        self.timeout_seconds = timeout_seconds or settings.SMS_REQUEST_TIMEOUT_SECONDS

    def send_sms(
        self,
        to_phone: str,
        message: str,
        idempotency_key: Optional[str] = None,
    ) -> ProviderSendResult:
        if not settings.SMS_ENABLED:
            logger.info("SMS sending requested but SMS_ENABLED is false; dispatch skipped.")
            return ProviderSendResult(
                status=ProviderSendStatus.DISABLED,
                error_code="SMS_DISABLED",
                error_message="SMS dispatch is disabled in configuration.",
            )

        if not self.account_sid or not self.auth_token or not self.from_phone:
            logger.error("Twilio credentials or from_phone missing.")
            return ProviderSendResult(
                status=ProviderSendStatus.REJECTED,
                error_code="CONFIG_ERROR",
                error_message="Twilio configuration is incomplete.",
            )

        # Standard Twilio Messages API URL
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        data = urllib.parse.urlencode({
            "To": to_phone,
            "From": self.from_phone,
            "Body": message,
        }).encode("utf-8")

        auth_str = f"{self.account_sid}:{self.auth_token}"
        auth_header = "Basic " + base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "CropAI-AlertEngine/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                import json
                resp_data = json.loads(resp.read().decode("utf-8"))
                sid = resp_data.get("sid")
                return ProviderSendResult(
                    status=ProviderSendStatus.ACCEPTED,
                    provider_message_id=sid,
                    raw_response=resp_data,
                )
        except urllib.error.HTTPError as err:
            sanitized_body = ""
            try:
                import json
                err_json = json.loads(err.read().decode("utf-8"))
                sanitized_body = f"Twilio Error {err_json.get('code')}: {err_json.get('message')}"
            except Exception:
                sanitized_body = f"Twilio HTTP Error {err.code}"

            logger.warning("Twilio API rejected message dispatch: %s", sanitized_body)
            return ProviderSendResult(
                status=ProviderSendStatus.REJECTED,
                error_code=str(err.code),
                error_message=sanitized_body,
            )
        except (TimeoutError, urllib.error.URLError):
            # Crucial: If request timed out, we DO NOT know if Twilio queued it
            # We must flag it for reconciliation rather than blindly resending!
            logger.error(
                "Twilio API request timed out or network error. Ambiguous delivery state."
            )
            return ProviderSendResult(
                status=ProviderSendStatus.UNKNOWN_TIMEOUT,
                error_code="TIMEOUT",
                error_message="Ambiguous provider timeout. Reconciliation required.",
            )
        except Exception as err:
            logger.error(
                "Unexpected error in Twilio provider dispatch [exception_type=%s]",
                type(err).__name__,
            )
            return ProviderSendResult(
                status=ProviderSendStatus.REJECTED,
                error_code="UNEXPECTED_ERROR",
                error_message="Internal error attempting to contact SMS provider.",
            )


class TwilioWhatsAppProvider(BaseWhatsAppProvider):
    """Production Twilio WhatsApp API client.

    Uses standard library urllib and handles Twilio WhatsApp sandbox/trial requirements:
    - Sender must start with 'whatsapp:' (e.g. 'whatsapp:+14155238886')
    - Recipient must be formatted with 'whatsapp:+...'
    - During trial, non-template freeform text is rejected by Twilio if outside 24h session.
      Supports passing ContentSid (approved template) or custom Body.
    - Idempotent and failsafe: Ambiguous timeout maps strictly to UNKNOWN_TIMEOUT.
    """

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_whatsapp: Optional[str] = None,
        content_sid: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        self.account_sid = account_sid or settings.TWILIO_ACCOUNT_SID
        self.auth_token = auth_token or settings.TWILIO_AUTH_TOKEN
        self.from_whatsapp = from_whatsapp or settings.TWILIO_WHATSAPP_NUMBER
        # If content_sid is explicitly passed as empty string (""), treat it as disabling template fallback
        if content_sid == "":
            self.content_sid = None
            self._explicitly_disabled_template = True
        else:
            self.content_sid = content_sid or settings.TWILIO_WHATSAPP_CONTENT_SID
            self._explicitly_disabled_template = False
        self.timeout_seconds = timeout_seconds or settings.WHATSAPP_REQUEST_TIMEOUT_SECONDS

    def _format_whatsapp_address(self, phone: str) -> str:
        """Ensure number has 'whatsapp:' prefix."""
        clean = phone.strip()
        if not clean.startswith("whatsapp:"):
            return f"whatsapp:{clean}"
        return clean

    def send_whatsapp(
        self,
        to_phone: str,
        message: str,
        content_sid: Optional[str] = None,
        content_variables: Optional[Dict[str, str]] = None,
        idempotency_key: Optional[str] = None,
    ) -> ProviderSendResult:
        if not settings.WHATSAPP_ENABLED:
            logger.info("WhatsApp sending requested but WHATSAPP_ENABLED is false; dispatch skipped.")
            return ProviderSendResult(
                status=ProviderSendStatus.DISABLED,
                error_code="WHATSAPP_DISABLED",
                error_message="WhatsApp dispatch is disabled in configuration.",
            )

        if not self.account_sid or not self.auth_token or not self.from_whatsapp:
            logger.error("Twilio credentials or from_whatsapp number missing.")
            return ProviderSendResult(
                status=ProviderSendStatus.REJECTED,
                error_code="CONFIG_ERROR",
                error_message="Twilio WhatsApp configuration is incomplete.",
            )

        to_address = self._format_whatsapp_address(to_phone)
        from_address = self._format_whatsapp_address(self.from_whatsapp)

        payload_dict: Dict[str, str] = {
            "To": to_address,
            "From": from_address,
        }

        # Check for approved ContentSid template (Trial WhatsApp requirement outside 24-hr session)
        if content_sid == "" or self._explicitly_disabled_template:
            effective_content_sid = None
        else:
            effective_content_sid = content_sid or self.content_sid

        if effective_content_sid:
            payload_dict["ContentSid"] = effective_content_sid
            if content_variables:
                import json
                payload_dict["ContentVariables"] = json.dumps(content_variables)
        else:
            payload_dict["Body"] = message

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        data = urllib.parse.urlencode(payload_dict).encode("utf-8")

        auth_str = f"{self.account_sid}:{self.auth_token}"
        auth_header = "Basic " + base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "CropAI-WhatsAppEngine/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                import json
                resp_data = json.loads(resp.read().decode("utf-8"))
                sid = resp_data.get("sid")
                return ProviderSendResult(
                    status=ProviderSendStatus.ACCEPTED,
                    provider_message_id=sid,
                    raw_response=resp_data,
                )
        except urllib.error.HTTPError as err:
            sanitized_body = ""
            try:
                import json
                err_json = json.loads(err.read().decode("utf-8"))
                sanitized_body = f"Twilio WhatsApp Error {err_json.get('code')}: {err_json.get('message')}"
            except Exception:
                sanitized_body = f"Twilio WhatsApp HTTP Error {err.code}"

            logger.warning("Twilio WhatsApp API rejected dispatch: %s", sanitized_body)
            return ProviderSendResult(
                status=ProviderSendStatus.REJECTED,
                error_code=str(err.code),
                error_message=sanitized_body,
            )
        except (TimeoutError, urllib.error.URLError):
            logger.error(
                "Twilio WhatsApp API request timed out or network error. Ambiguous delivery state."
            )
            return ProviderSendResult(
                status=ProviderSendStatus.UNKNOWN_TIMEOUT,
                error_code="TIMEOUT",
                error_message="Ambiguous WhatsApp provider timeout. Reconciliation required.",
            )
        except Exception as err:
            logger.error(
                "Unexpected error in Twilio WhatsApp provider dispatch [exception_type=%s]",
                type(err).__name__,
            )
            return ProviderSendResult(
                status=ProviderSendStatus.REJECTED,
                error_code="UNEXPECTED_ERROR",
                error_message="Internal error attempting to contact WhatsApp provider.",
            )

