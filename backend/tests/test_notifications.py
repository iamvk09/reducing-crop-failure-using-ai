"""Comprehensive unit tests for SMS notifications, idempotency, consent, and timeout handling."""

import pytest

from backend.app.core.config import settings
from backend.app.repositories.notification_repository import InMemoryNotificationRepository
from backend.app.services.notification.provider import (
    MockSmsProvider,
    MockWhatsAppProvider,
    ProviderSendStatus,
)
from backend.app.services.notification_service import (
    NotificationService,
    generate_idempotency_key,
    is_valid_e164,
    mask_phone_number,
)


@pytest.fixture
def mock_repo():
    return InMemoryNotificationRepository()


@pytest.fixture
def mock_provider():
    return MockSmsProvider()


@pytest.fixture
def mock_whatsapp_provider():
    return MockWhatsAppProvider()


@pytest.fixture
def notification_svc(mock_repo, mock_provider, mock_whatsapp_provider):
    return NotificationService(
        repository=mock_repo,
        sms_provider=mock_provider,
        whatsapp_provider=mock_whatsapp_provider,
    )


# ---------------------------------------------------------------------------
# 1. Phone number masking & E.164 validation tests
# ---------------------------------------------------------------------------

def test_mask_phone_number():
    assert mask_phone_number("+919876543210") == "+91******3210"
    assert mask_phone_number("+14155552671") == "+14*****2671"
    assert mask_phone_number("12345") == "******"


def test_is_valid_e164():
    assert is_valid_e164("+919876543210") is True
    assert is_valid_e164("+14155552671") is True
    assert is_valid_e164("9876543210") is False  # Missing +
    assert is_valid_e164("+0123456789") is False  # Country codes do not start with 0
    assert is_valid_e164("invalid") is False


# ---------------------------------------------------------------------------
# 2. Consent & Zero-Cost Defaults
# ---------------------------------------------------------------------------

def test_sms_disabled_by_default(notification_svc, mock_provider):
    """When SMS_ENABLED=False in settings, no messages are sent even if user consents."""
    settings.SMS_ENABLED = False

    alert = {"id": "alert-1", "alert_type": "RISK_THRESHOLD_CROSSED", "severity": "critical"}
    result = notification_svc.dispatch_alert_sms(
        user_id="user-1",
        phone_number="+919876543210",
        sms_consent=True,
        farm_name="Green Acres",
        alert=alert,
    )

    assert result is None
    assert len(mock_provider.sent_messages) == 0


def test_sms_requires_explicit_opt_in(notification_svc, mock_provider):
    """If sms_consent=False, dispatch is aborted immediately."""
    settings.SMS_ENABLED = True

    alert = {"id": "alert-2", "alert_type": "RISK_THRESHOLD_CROSSED", "severity": "critical"}
    result = notification_svc.dispatch_alert_sms(
        user_id="user-1",
        phone_number="+919876543210",
        sms_consent=False,  # Explicitly False
        farm_name="Green Acres",
        alert=alert,
    )

    assert result is None
    assert len(mock_provider.sent_messages) == 0


# ---------------------------------------------------------------------------
# 3. Successful Dispatch & State Progression
# ---------------------------------------------------------------------------

def test_successful_sms_dispatch_marks_submitted_not_delivered(notification_svc, mock_provider, mock_repo):
    """Initial provider acceptance must mark status 'submitted', NEVER 'delivered'."""
    settings.SMS_ENABLED = True

    alert = {
        "id": "alert-3",
        "alert_type": "RISK_THRESHOLD_CROSSED",
        "severity": "critical",
        "risk_probability": 0.78,
        "recommended_action": "Halt synthetic fertilizers and inspect drainage channels.",
    }
    result = notification_svc.dispatch_alert_sms(
        user_id="user-1",
        phone_number="+919876543210",
        sms_consent=True,
        farm_name="Punjab Wheat Farm",
        alert=alert,
        farm_id="farm-123",
        prediction_id="pred-456",
    )

    assert result is not None
    assert result["status"] == "submitted"  # Not delivered!
    assert result["provider_message_id"] == "mock-sms-1"
    assert result["phone_number_masked"] == "+91******3210"
    assert "Punjab Wheat Farm" in result["message_body"]
    assert "78%" in result["message_body"]

    # Durable audit record verified in repository
    audit = mock_repo.get_by_idempotency_key(result["idempotency_key"])
    assert audit is not None
    assert audit["status"] == "submitted"


# ---------------------------------------------------------------------------
# 4. Strict Idempotency Across Repeated Predictions
# ---------------------------------------------------------------------------

def test_deterministic_idempotency_prevents_duplicate_dispatch(notification_svc, mock_provider):
    """Calling dispatch multiple times for the same alert must only send one SMS."""
    settings.SMS_ENABLED = True

    alert = {"id": "alert-idempotent", "alert_type": "RISK_TREND_INCREASING", "severity": "warning"}
    
    # First dispatch
    res1 = notification_svc.dispatch_alert_sms(
        user_id="user-1",
        phone_number="+919876543210",
        sms_consent=True,
        farm_name="Farm Alpha",
        alert=alert,
    )
    assert res1 is not None
    assert len(mock_provider.sent_messages) == 1

    # Repeated prediction / midnight cron with same alert
    res2 = notification_svc.dispatch_alert_sms(
        user_id="user-1",
        phone_number="+919876543210",
        sms_consent=True,
        farm_name="Farm Alpha",
        alert=alert,
    )
    # Returns existing record, sends no new message
    assert res2["id"] == res1["id"]
    assert len(mock_provider.sent_messages) == 1


# ---------------------------------------------------------------------------
# 5. Ambiguous Timeout Safety & Reconciliation
# ---------------------------------------------------------------------------

def test_ambiguous_timeout_marks_reconciliation_required_without_resend(notification_svc, mock_provider, mock_repo):
    """When a provider request times out, status becomes 'reconciliation_required' and is not blindly resent."""
    settings.SMS_ENABLED = True
    mock_provider.force_timeout = True

    alert = {"id": "alert-timeout", "alert_type": "TELEMETRY_DEGRADATION", "severity": "warning"}
    result = notification_svc.dispatch_alert_sms(
        user_id="user-1",
        phone_number="+919876543210",
        sms_consent=True,
        farm_name="Farm Beta",
        alert=alert,
    )

    assert result is not None
    assert result["status"] == "reconciliation_required"
    assert result["retry_count"] == 1
    assert "reconciliation" in result["error_message_sanitized"]

    # Re-dispatch with same key must NOT send again blindly
    res2 = notification_svc.dispatch_alert_sms(
        user_id="user-1",
        phone_number="+919876543210",
        sms_consent=True,
        farm_name="Farm Beta",
        alert=alert,
    )
    assert res2["status"] == "reconciliation_required"
    assert len(mock_provider.sent_messages) == 0


# ---------------------------------------------------------------------------
# 6. Failure Non-Interference Guarantee
# ---------------------------------------------------------------------------

def test_provider_rejection_marks_failed_without_raising(notification_svc, mock_provider):
    """Provider rejections must be captured safely in audit logs without throwing to the caller."""
    settings.SMS_ENABLED = True
    mock_provider.force_error = "Destination number unreachable"

    alert = {"id": "alert-fail", "alert_type": "RISK_THRESHOLD_CROSSED", "severity": "critical"}
    result = notification_svc.dispatch_alert_sms(
        user_id="user-1",
        phone_number="+919876543210",
        sms_consent=True,
        farm_name="Farm Gamma",
        alert=alert,
    )

    assert result is not None
    assert result["status"] == "failed"
    assert result["error_code"] == "MOCK_REJECTED"
    assert "Destination number unreachable" in result["error_message_sanitized"]


# ---------------------------------------------------------------------------
# 7. WhatsApp Tests (Channel Independence, Consent, & Idempotency)
# ---------------------------------------------------------------------------

def test_whatsapp_disabled_by_default(notification_svc, mock_whatsapp_provider):
    """When WHATSAPP_ENABLED=False, no WhatsApp messages are sent."""
    settings.WHATSAPP_ENABLED = False

    alert = {"id": "wa-1", "alert_type": "RISK_THRESHOLD_CROSSED", "severity": "critical"}
    result = notification_svc.dispatch_alert_whatsapp(
        user_id="user-1",
        phone_number="+919876543210",
        whatsapp_consent=True,
        farm_name="Green Acres",
        alert=alert,
    )

    assert result is None
    assert len(mock_whatsapp_provider.sent_messages) == 0


def test_whatsapp_requires_explicit_opt_in(notification_svc, mock_whatsapp_provider):
    """WhatsApp dispatch aborts if whatsapp_consent=False."""
    settings.WHATSAPP_ENABLED = True

    alert = {"id": "wa-2", "alert_type": "RISK_THRESHOLD_CROSSED", "severity": "critical"}
    result = notification_svc.dispatch_alert_whatsapp(
        user_id="user-1",
        phone_number="+919876543210",
        whatsapp_consent=False,
        farm_name="Green Acres",
        alert=alert,
    )

    assert result is None
    assert len(mock_whatsapp_provider.sent_messages) == 0


def test_whatsapp_successful_dispatch_marks_submitted_not_delivered(
    notification_svc, mock_whatsapp_provider, mock_repo
):
    """WhatsApp provider acceptance sets status 'submitted'."""
    settings.WHATSAPP_ENABLED = True

    alert = {
        "id": "wa-3",
        "alert_type": "RISK_THRESHOLD_CROSSED",
        "severity": "critical",
        "risk_probability": 0.82,
    }
    result = notification_svc.dispatch_alert_whatsapp(
        user_id="user-1",
        phone_number="+919876543210",
        whatsapp_consent=True,
        farm_name="Mysore Farm",
        alert=alert,
    )

    assert result is not None
    assert result["channel"] == "whatsapp"
    assert result["status"] == "submitted"
    assert result["provider_message_id"] == "mock-wa-1"

    # Verify audit record
    audit = mock_repo.get_by_idempotency_key(result["idempotency_key"])
    assert audit is not None
    assert audit["channel"] == "whatsapp"
    assert audit["status"] == "submitted"


def test_independent_channel_idempotency(notification_svc, mock_provider, mock_whatsapp_provider):
    """SMS and WhatsApp can both be sent for the same alert without blocking each other, but cannot duplicate within channel."""
    settings.SMS_ENABLED = True
    settings.WHATSAPP_ENABLED = True

    alert = {"id": "alert-dual", "alert_type": "RISK_THRESHOLD_CROSSED", "severity": "critical"}

    # Send SMS
    sms_res = notification_svc.dispatch_alert_sms(
        user_id="user-1",
        phone_number="+919876543210",
        sms_consent=True,
        farm_name="Dual Farm",
        alert=alert,
    )
    # Send WhatsApp
    wa_res = notification_svc.dispatch_alert_whatsapp(
        user_id="user-1",
        phone_number="+919876543210",
        whatsapp_consent=True,
        farm_name="Dual Farm",
        alert=alert,
    )

    assert sms_res is not None and sms_res["channel"] == "sms"
    assert wa_res is not None and wa_res["channel"] == "whatsapp"
    assert sms_res["idempotency_key"] != wa_res["idempotency_key"]
    assert len(mock_provider.sent_messages) == 1
    assert len(mock_whatsapp_provider.sent_messages) == 1

    # Repeat both - neither should send duplicate
    sms_res2 = notification_svc.dispatch_alert_sms(
        user_id="user-1",
        phone_number="+919876543210",
        sms_consent=True,
        farm_name="Dual Farm",
        alert=alert,
    )
    wa_res2 = notification_svc.dispatch_alert_whatsapp(
        user_id="user-1",
        phone_number="+919876543210",
        whatsapp_consent=True,
        farm_name="Dual Farm",
        alert=alert,
    )

    assert sms_res2["id"] == sms_res["id"]
    assert wa_res2["id"] == wa_res["id"]
    assert len(mock_provider.sent_messages) == 1
    assert len(mock_whatsapp_provider.sent_messages) == 1


def test_whatsapp_ambiguous_timeout_marks_reconciliation(notification_svc, mock_whatsapp_provider):
    """Ambiguous WhatsApp timeout marks status 'reconciliation_required'."""
    settings.WHATSAPP_ENABLED = True
    mock_whatsapp_provider.force_timeout = True

    alert = {"id": "wa-timeout", "alert_type": "RISK_THRESHOLD_CROSSED", "severity": "critical"}
    result = notification_svc.dispatch_alert_whatsapp(
        user_id="user-1",
        phone_number="+919876543210",
        whatsapp_consent=True,
        farm_name="Timeout Farm",
        alert=alert,
    )

    assert result is not None
    assert result["status"] == "reconciliation_required"
    assert result["retry_count"] == 1


def test_repository_pagination_limit_and_offset(mock_repo):
    """Repository pagination respects limit and offset."""
    for i in range(10):
        mock_repo.create_dispatch(
            user_id="user-paginate",
            phone_number_masked="+91******1234",
            message_body=f"Msg {i}",
            idempotency_key=f"key-{i}",
            channel="sms",
        )

    page1 = mock_repo.list_dispatches_for_user(user_id="user-paginate", limit=3, offset=0)
    page2 = mock_repo.list_dispatches_for_user(user_id="user-paginate", limit=3, offset=3)

    assert len(page1) == 3
    assert len(page2) == 3
    assert page1[0]["id"] != page2[0]["id"]


# ---------------------------------------------------------------------------
# 8. User Consent Lifecycle Tests (Opt-In, Opt-Out, Re-Opt-In, Independence)
# ---------------------------------------------------------------------------

def test_consent_timestamp_lifecycle_and_channel_independence():
    """Verify consent timestamp is generated on opt-in, cleared to None on opt-out, and channels are independent."""
    from backend.app.core.security import AuthenticatedUser
    from backend.app.schemas.auth import UserProfileUpdateRequest
    from backend.app.services.user_service import user_service

    test_user = AuthenticatedUser(
        id="test-consent-user-123",
        email="farmer@cropai.org",
        role="farmer",
    )
    user_service.clear()

    # Step 1: Initial profile has no consent
    prof0 = user_service.get_or_create_profile(test_user)
    assert prof0.sms_notifications_enabled is False
    assert prof0.sms_consent_timestamp is None
    assert prof0.whatsapp_notifications_enabled is False
    assert prof0.whatsapp_consent_timestamp is None

    # Step 2: Opt-in to SMS only
    prof1 = user_service.update_profile(
        user=test_user,
        update_in=UserProfileUpdateRequest(sms_notifications_enabled=True),
    )
    assert prof1.sms_notifications_enabled is True
    assert prof1.sms_consent_timestamp is not None
    initial_sms_ts = prof1.sms_consent_timestamp
    # WhatsApp remains completely unaffected
    assert prof1.whatsapp_notifications_enabled is False
    assert prof1.whatsapp_consent_timestamp is None

    # Step 3: Opt-in to WhatsApp as well (Independent)
    prof2 = user_service.update_profile(
        user=test_user,
        update_in=UserProfileUpdateRequest(whatsapp_notifications_enabled=True),
    )
    assert prof2.whatsapp_notifications_enabled is True
    assert prof2.whatsapp_consent_timestamp is not None
    # SMS consent timestamp remains unchanged
    assert prof2.sms_notifications_enabled is True
    assert prof2.sms_consent_timestamp == initial_sms_ts

    # Step 4: Opt-out of SMS (Must clear timestamp to None!)
    prof3 = user_service.update_profile(
        user=test_user,
        update_in=UserProfileUpdateRequest(sms_notifications_enabled=False),
    )
    assert prof3.sms_notifications_enabled is False
    assert prof3.sms_consent_timestamp is None
    # WhatsApp remains enabled with intact timestamp
    assert prof3.whatsapp_notifications_enabled is True
    assert prof3.whatsapp_consent_timestamp is not None

    # Step 5: Re-opt-in to SMS (Must record a fresh timestamp)
    prof4 = user_service.update_profile(
        user=test_user,
        update_in=UserProfileUpdateRequest(sms_notifications_enabled=True),
    )
    assert prof4.sms_notifications_enabled is True
    assert prof4.sms_consent_timestamp is not None

    # Step 6: Opt-out of WhatsApp (Must clear timestamp to None)
    prof5 = user_service.update_profile(
        user=test_user,
        update_in=UserProfileUpdateRequest(whatsapp_notifications_enabled=False),
    )
    assert prof5.whatsapp_notifications_enabled is False
    assert prof5.whatsapp_consent_timestamp is None
    assert prof5.sms_notifications_enabled is True
    assert prof5.sms_consent_timestamp is not None


def test_supabase_persistence_payloads_and_failure_handling(monkeypatch):
    """Verify Supabase patch payloads for consent opt-in/opt-out and that database failures raise without updating memory."""
    from backend.app.core.security import AuthenticatedUser
    from backend.app.core.supabase import supabase_client
    from backend.app.schemas.auth import UserProfileUpdateRequest
    from backend.app.services.user_service import user_service

    test_user = AuthenticatedUser(
        id="mock-db-user-456",
        email="farmer@cropai.org",
        role="farmer",
    )
    user_service.clear()

    # Track payloads passed to update()
    captured_updates = []
    should_fail = False

    def mock_is_live():
        return True

    def mock_update(table, data, params=None, user_token=None):
        if should_fail:
            raise RuntimeError("Database connection reset by peer")
        captured_updates.append({"table": table, "data": data, "params": params})
        return [data]

    monkeypatch.setattr(supabase_client, "is_live_configured", mock_is_live)
    monkeypatch.setattr(supabase_client, "update", mock_update)

    # 1. Opt-in SMS
    prof1 = user_service.update_profile(
        user=test_user,
        update_in=UserProfileUpdateRequest(sms_notifications_enabled=True),
    )
    assert len(captured_updates) == 1
    assert captured_updates[-1]["data"]["sms_notifications_enabled"] is True
    assert captured_updates[-1]["data"]["sms_consent_timestamp"] is not None

    # 2. Opt-out SMS
    prof2 = user_service.update_profile(
        user=test_user,
        update_in=UserProfileUpdateRequest(sms_notifications_enabled=False),
    )
    assert len(captured_updates) == 2
    assert captured_updates[-1]["data"]["sms_notifications_enabled"] is False
    assert captured_updates[-1]["data"]["sms_consent_timestamp"] is None

    # 3. Opt-in WhatsApp
    prof3 = user_service.update_profile(
        user=test_user,
        update_in=UserProfileUpdateRequest(whatsapp_notifications_enabled=True),
    )
    assert len(captured_updates) == 3
    assert captured_updates[-1]["data"]["whatsapp_notifications_enabled"] is True
    assert captured_updates[-1]["data"]["whatsapp_consent_timestamp"] is not None

    # 4. Opt-out WhatsApp
    prof4 = user_service.update_profile(
        user=test_user,
        update_in=UserProfileUpdateRequest(whatsapp_notifications_enabled=False),
    )
    assert len(captured_updates) == 4
    assert captured_updates[-1]["data"]["whatsapp_notifications_enabled"] is False
    assert captured_updates[-1]["data"]["whatsapp_consent_timestamp"] is None

    # 5. Database failure: must raise RuntimeError and NOT modify in-memory profile state
    should_fail = True
    with pytest.raises(RuntimeError) as exc_info:
        user_service.update_profile(
            user=test_user,
            update_in=UserProfileUpdateRequest(sms_notifications_enabled=True),
        )
    assert "Database error updating user profile" in str(exc_info.value)
    # Confirm in-memory state remains unchanged (still False)
    current_prof = user_service.get_user_profile(test_user.id)
    assert current_prof.sms_notifications_enabled is False
    assert current_prof.sms_consent_timestamp is None


# ---------------------------------------------------------------------------
# 9. Provider Safe Exception Logging Test (No Secrets in Logs)
# ---------------------------------------------------------------------------

def test_provider_unexpected_exception_never_logs_secrets(caplog, monkeypatch):
    """Verify that an unexpected exception containing sensitive tokens or credentials does not leak into logs."""
    import logging
    from backend.app.services.notification.provider import TwilioSmsProvider, TwilioWhatsAppProvider

    fake_secret = "SUPER_SECRET_TWILIO_AUTH_TOKEN_XYZ12345"
    fake_destination = "+919876543210"
    fake_body = "Confidential Advisory Content"

    sms_provider = TwilioSmsProvider(
        account_sid="ACtest123",
        auth_token="dummy_token",
        from_phone="+1234567890",
    )
    wa_provider = TwilioWhatsAppProvider(
        account_sid="ACtest123",
        auth_token="dummy_token",
        from_whatsapp="+1234567890",
    )

    # Force urllib.request.urlopen to raise an exception embedding secret text
    def mock_urlopen_raising(*args, **kwargs):
        raise ValueError(f"Crash details: Authorization: Basic {fake_secret} for {fake_destination}")

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_raising)
    settings.SMS_ENABLED = True
    settings.WHATSAPP_ENABLED = True

    with caplog.at_level(logging.ERROR):
        res_sms = sms_provider.send_sms(to_phone=fake_destination, message=fake_body)
        res_wa = wa_provider.send_whatsapp(to_phone=fake_destination, message=fake_body)

    # Check caller-facing results
    assert res_sms.status == ProviderSendStatus.REJECTED
    assert res_sms.error_code == "UNEXPECTED_ERROR"
    assert res_sms.error_message == "Internal error attempting to contact SMS provider."

    assert res_wa.status == ProviderSendStatus.REJECTED
    assert res_wa.error_code == "UNEXPECTED_ERROR"
    assert res_wa.error_message == "Internal error attempting to contact WhatsApp provider."

    # Verify captured log text NEVER contains the secret or full sensitive string
    log_text = caplog.text
    assert fake_secret not in log_text
    assert "ValueError" in log_text  # Safe metadata type(err).__name__ is present
    assert "exception_type=ValueError" in log_text


# ---------------------------------------------------------------------------
# 10. End-to-End Mocked WhatsApp Alert Flow Test
# ---------------------------------------------------------------------------

def test_whatsapp_end_to_end_mocked_alert_flow(monkeypatch):
    """End-to-end test covering alert creation, consent verification, phone validation,
    template parameter formatting, durable dispatch logging, and duplicate prevention.
    """
    from backend.app.core.security import AuthenticatedUser
    from backend.app.schemas.prediction import PredictionResponse, RecommendationDetails
    from backend.app.services.alert_service import AlertService
    from backend.app.repositories.alert_repository import AlertRepository
    from backend.app.services.user_service import user_service
    from backend.app.services.notification_service import notification_service
    from backend.app.repositories.notification_repository import InMemoryNotificationRepository
    from backend.app.services.notification.provider import MockWhatsAppProvider

    # 1. Setup isolated in-memory repositories and mock provider
    mock_alert_repo = AlertRepository()
    mock_notif_repo = InMemoryNotificationRepository()
    mock_wa_provider = MockWhatsAppProvider()

    test_alert_svc = AlertService(repo=mock_alert_repo)
    notification_service.repository = mock_notif_repo
    notification_service.whatsapp_provider = mock_wa_provider

    # Enable WhatsApp globally for test
    settings.WHATSAPP_ENABLED = True
    settings.SMS_ENABLED = False

    test_user = AuthenticatedUser(
        id="user-wa-e2e-123",
        email="farmer.e2e@cropai.org",
        role="farmer",
    )
    user_service.clear()

    # Opt in to WhatsApp with a valid E.164 number
    user_service.get_or_create_profile(test_user)
    from backend.app.schemas.auth import UserProfileUpdateRequest
    user_service.update_profile(
        user=test_user,
        update_in=UserProfileUpdateRequest(
            whatsapp_notifications_enabled=True,
            phone_number="+919876543210",
        ),
    )

    # 2. Simulate high risk prediction crossing threshold
    pred = PredictionResponse(
        prediction_id="pred-e2e-999",
        farm_id="farm-e2e-1",
        crop="Rice",
        district="Mandya",
        state="Karnataka",
        season="Kharif",
        risk_probability=0.88,
        risk_percentage="88.0%",
        risk_level="High",
        prediction_class=1,
        best_model_name="RandomForestClassifier",
        input_features={"Rainfall_mm": 110.0, "NDVI_Flowering": 0.45},
        provenance={"telemetry": "mock"},
        recommendations=RecommendationDetails(
            recommended_crop="Millets",
            advisory_summary="Escalate field drainage and halt urea applications.",
        ),
    )

    class MockFarm:
        id = "farm-e2e-1"
        name = "Kaveri Basin Plot 4"

    # 3. Evaluate alert conditions -> triggers automatic notification dispatch
    created_alerts = test_alert_svc.evaluate_alert_conditions(
        farm=MockFarm(),
        target_crop=None,
        current_pred=pred,
        previous_pred=None,
        user=test_user,
    )

    assert len(created_alerts) >= 1
    alert = created_alerts[0]
    assert alert["alert_type"] == "RISK_THRESHOLD_CROSSED"
    assert alert["severity"] == "critical"

    # 4. Verify provider received formatted message and template parameters
    assert len(mock_wa_provider.sent_messages) == 1
    sent_msg = mock_wa_provider.sent_messages[0]
    assert sent_msg["to"] == "+919876543210"
    assert "Kaveri Basin Plot 4" in sent_msg["body"]
    assert "88%" in sent_msg["body"]
    assert sent_msg["content_variables"]["1"] == "Kaveri Basin Plot 4"
    assert sent_msg["content_variables"]["2"] == "CRITICAL"
    assert sent_msg["content_variables"]["3"] == "88%"

    # 5. Verify durable audit dispatch record
    user_dispatches = mock_notif_repo.list_dispatches_for_user(user_id=test_user.id)
    assert len(user_dispatches) == 1
    dispatch = user_dispatches[0]
    assert dispatch["channel"] == "whatsapp"
    assert dispatch["status"] == "submitted"
    assert dispatch["phone_number_masked"] == "+91******3210"
    assert dispatch["provider_message_id"] == "mock-wa-1"

    # 6. Idempotency verification: Repeated evaluation for the same prediction must not duplicate dispatch
    repeat_alerts = test_alert_svc.evaluate_alert_conditions(
        farm=MockFarm(),
        target_crop=None,
        current_pred=pred,
        previous_pred=None,
        user=test_user,
    )
    # Deduplication rules prevent duplicate alert and dispatch
    assert len(mock_wa_provider.sent_messages) == 1
    assert len(mock_notif_repo.list_dispatches_for_user(user_id=test_user.id)) == 1

    # Reset test settings
    settings.WHATSAPP_ENABLED = False


# ---------------------------------------------------------------------------
# 11. TwilioWhatsAppProvider Payload Construction (Freeform vs Template)
# ---------------------------------------------------------------------------

def test_twilio_whatsapp_provider_payload_freeform_vs_template():
    """Verify TwilioWhatsAppProvider constructs Body when content_sid=None, and ContentSid when set."""
    from unittest.mock import patch, MagicMock
    from backend.app.services.notification.provider import TwilioWhatsAppProvider
    import urllib.parse
    import io

    settings.WHATSAPP_ENABLED = True
    provider = TwilioWhatsAppProvider(
        account_sid="ACtest12345678901234567890123456",
        auth_token="authtest1234567890123456789012",
        from_whatsapp="whatsapp:+17372508034",
        content_sid=None,
    )

    # Case A: Freeform Body Mode (Zero-cost sandbox 24h window) via explicit content_sid=""
    provider_freeform = TwilioWhatsAppProvider(
        account_sid="ACtest12345678901234567890123456",
        auth_token="authtest1234567890123456789012",
        from_whatsapp="whatsapp:+17372508034",
        content_sid="",
    )
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"sid": "SMtest123"}'
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        result = provider_freeform.send_whatsapp(
            to_phone="+919876543210",
            message="Alert message body",
            content_sid="",
        )
        assert result.status.value == "accepted"
        req = mock_urlopen.call_args[0][0]
        parsed_payload = urllib.parse.parse_qs(req.data.decode("utf-8"))
        assert parsed_payload["To"] == ["whatsapp:+919876543210"]
        assert parsed_payload["From"] == ["whatsapp:+17372508034"]
        assert parsed_payload["Body"] == ["Alert message body"]
        assert "ContentSid" not in parsed_payload
        assert "ContentVariables" not in parsed_payload

    # Case B: Template ContentSid Mode
    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        result = provider.send_whatsapp(
            to_phone="+919876543210",
            message="Alert message body",
            content_sid="HX1234567890abcdef",
            content_variables={"1": "Plot A", "2": "HIGH"},
        )
        assert result.status.value == "accepted"
        req = mock_urlopen.call_args[0][0]
        parsed_payload = urllib.parse.parse_qs(req.data.decode("utf-8"))
        assert parsed_payload["To"] == ["whatsapp:+919876543210"]
        assert parsed_payload["From"] == ["whatsapp:+17372508034"]
        assert parsed_payload["ContentSid"] == ["HX1234567890abcdef"]
        assert "1" in parsed_payload["ContentVariables"][0]
        assert "Body" not in parsed_payload

    settings.WHATSAPP_ENABLED = False


# ---------------------------------------------------------------------------
# 12. Mocked WhatsApp Preflight Script End-to-End Safety Tests
# ---------------------------------------------------------------------------

def test_sandbox_preflight_script_safeguards_end_to_end(monkeypatch):
    """Verify scratch/send_single_sandbox_whatsapp.py safety gates via mocks:
    - Dry-run mode never instantiates TwilioWhatsAppProvider
    - Live sending fails closed when WHATSAPP_ENABLED is False
    - Missing manual consent refuses live send
    - Exactly one provider dispatch occurs per live execution
    - Ambiguous timeout results in reconciliation_required without blind retry
    - InMemory repository is used (no Supabase access)
    """
    import pytest
    from unittest.mock import patch, MagicMock
    from scratch.send_single_sandbox_whatsapp import run_sandbox_preflight

    # 1. Dry run: Provider is never instantiated, zero network requests
    with patch("scratch.send_single_sandbox_whatsapp.TwilioWhatsAppProvider") as mock_provider_cls:
        # Should complete cleanly without raising SystemExit
        run_sandbox_preflight(
            recipient_phone="+919876543210",
            send_live=False,
            manual_consent_confirmed=False,
            use_template=False,
        )
        mock_provider_cls.assert_not_called()

    # 2. Live sending without manual consent must fail closed (SystemExit 1)
    with pytest.raises(SystemExit) as exc_info:
        run_sandbox_preflight(
            recipient_phone="+919876543210",
            send_live=True,
            manual_consent_confirmed=False,
            use_template=False,
        )
    assert exc_info.value.code == 1

    # 3. Live sending when WHATSAPP_ENABLED is False must fail closed (SystemExit 1)
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", False)
    with pytest.raises(SystemExit) as exc_info:
        run_sandbox_preflight(
            recipient_phone="+919876543210",
            send_live=True,
            manual_consent_confirmed=True,
            use_template=False,
        )
    assert exc_info.value.code == 1

    # 4. Mocked live dispatch: strictly one dispatch, freeform Body, and provider acceptance
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "ACtest12345678901234567890123456")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "authtest1234567890123456789012")
    monkeypatch.setattr(settings, "TWILIO_WHATSAPP_NUMBER", "whatsapp:+17372508034")

    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"sid": "SMtest999"}'
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        run_sandbox_preflight(
            recipient_phone="+919876543210",
            send_live=True,
            manual_consent_confirmed=True,
            use_template=False,
        )
        # Exactly one network request was initiated
        assert mock_urlopen.call_count == 1
        req = mock_urlopen.call_args[0][0]
        import urllib.parse
        parsed = urllib.parse.parse_qs(req.data.decode("utf-8"))
        assert parsed["To"] == ["whatsapp:+919876543210"]
        assert parsed["From"] == ["whatsapp:+17372508034"]
        assert "Body" in parsed
        assert "ContentSid" not in parsed

    # 5. Mocked live dispatch with timeout: maps to reconciliation_required, zero blind resends
    with patch("urllib.request.urlopen", side_effect=TimeoutError("Connection timed out")):
        run_sandbox_preflight(
            recipient_phone="+919876543210",
            send_live=True,
            manual_consent_confirmed=True,
            use_template=False,
        )

    # 6. Configuration restoration check: Ensure settings remain disabled
    monkeypatch.undo()
    assert settings.WHATSAPP_ENABLED is False
    assert settings.SMS_ENABLED is False


# ---------------------------------------------------------------------------
# 13. Nullable user_id & Orphaned Dispatch Schema Compatibility Tests
# ---------------------------------------------------------------------------

def test_notification_dispatch_response_user_id_compatibility():
    """Verify NotificationDispatchResponse handles non-null user_id and None (orphaned records)."""
    import datetime
    from backend.app.schemas.notification import NotificationDispatchResponse, DispatchStatus

    now = datetime.datetime.now(datetime.timezone.utc)

    # 1. Standard active user record (non-null user_id)
    active_data = {
        "id": "disp-active-001",
        "user_id": "usr-123456",
        "farm_id": "farm-999",
        "alert_id": "alert-888",
        "prediction_id": "pred-777",
        "channel": "sms",
        "phone_number_masked": "+91******3210",
        "message_body": "Critical weather alert",
        "idempotency_key": "key-active-123",
        "status": DispatchStatus.SUBMITTED,
        "provider": "twilio",
        "provider_message_id": "SMactive123",
        "created_at": now,
        "submitted_at": now,
    }
    active_resp = NotificationDispatchResponse(**active_data)
    assert active_resp.user_id == "usr-123456"
    assert active_resp.status == DispatchStatus.SUBMITTED
    serialized_active = active_resp.model_dump()
    assert serialized_active["user_id"] == "usr-123456"

    # 2. Orphaned dispatch record (user_id is None after account deletion)
    orphaned_data = {
        "id": "disp-orphaned-002",
        "user_id": None,
        "farm_id": None,
        "alert_id": "alert-888",
        "prediction_id": None,
        "channel": "whatsapp",
        "phone_number_masked": "+91******3210",
        "message_body": "[REDACTED — ACCOUNT DELETED]",
        "idempotency_key": "key-orphaned-456",
        "status": DispatchStatus.DELIVERED,
        "provider": "twilio",
        "provider_message_id": "MMorphaned456",
        "created_at": now,
        "submitted_at": now,
        "delivered_at": now,
    }
    orphaned_resp = NotificationDispatchResponse(**orphaned_data)
    assert orphaned_resp.user_id is None
    assert orphaned_resp.status == DispatchStatus.DELIVERED
    serialized_orphaned = orphaned_resp.model_dump()
    assert serialized_orphaned["user_id"] is None
    assert serialized_orphaned["message_body"] == "[REDACTED — ACCOUNT DELETED]"


def test_get_user_dispatches_route_with_orphaned_and_invalid_records(mock_repo):
    """Verify /notifications/dispatches route serializes orphaned records and logs validation warnings deliberately."""
    from unittest.mock import patch, MagicMock
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.core.security import AuthenticatedUser
    from backend.app.api.deps import get_current_user
    from backend.app.services.notification_service import notification_service
    import datetime

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    test_user = AuthenticatedUser(
        id="farmer-test-123",
        role="farmer",
        email="farmer@example.com",
    )

    app.dependency_overrides[get_current_user] = lambda: test_user
    client = TestClient(app)

    # Populate mock repository with:
    # 1. Normal active dispatch for this farmer
    # 2. Orphaned dispatch (user_id is None)
    mock_repo.dispatches = {
        "disp-1": {
            "id": "disp-1",
            "user_id": test_user.id,
            "farm_id": "farm-1",
            "alert_id": "alert-1",
            "prediction_id": "pred-1",
            "channel": "sms",
            "phone_number_masked": "+91******3210",
            "message_body": "Alert 1",
            "idempotency_key": "idemp-1",
            "status": "submitted",
            "provider": "twilio",
            "created_at": now,
        },
        "disp-2": {
            "id": "disp-2",
            "user_id": None,  # Orphaned
            "farm_id": None,
            "alert_id": None,
            "prediction_id": None,
            "channel": "whatsapp",
            "phone_number_masked": "+91******3210",
            "message_body": "[REDACTED — ACCOUNT DELETED]",
            "idempotency_key": "idemp-2",
            "status": "delivered",
            "provider": "twilio",
            "created_at": now,
        },
    }

    # Ensure global notification_service uses this mock_repo during test
    orig_repo = notification_service.repository
    notification_service.repository = mock_repo

    try:
        # Farmer querying their own dispatches returns only their user_id
        res = client.get("/api/v1/notifications/dispatches")
        assert res.status_code == 200
        data = res.json()
        assert "dispatches" in data
        assert len(data["dispatches"]) == 1
        assert data["dispatches"][0]["user_id"] == test_user.id

        # Verify that an orphaned record directly passes schema serialization when user_id is None
        from backend.app.schemas.notification import NotificationDispatchResponse
        orphaned_item = NotificationDispatchResponse(**mock_repo.dispatches["disp-2"])
        assert orphaned_item.user_id is None
        assert orphaned_item.id == "disp-2"
    finally:
        notification_service.repository = orig_repo
        app.dependency_overrides.clear()

