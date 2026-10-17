-- =============================================================================
-- Migration 011: SMS Notifications & Dispatch Audit Trail
-- =============================================================================

-- 1. Add opt-in consent columns to public.users
-- Default is strictly false (explicit opt-in required).
ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS sms_notifications_enabled BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS sms_consent_timestamp TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS whatsapp_notifications_enabled BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS whatsapp_consent_timestamp TIMESTAMPTZ;

-- 2. Dispatch Status Enum / Domain Check
DO $$ BEGIN
    CREATE TYPE dispatch_status_enum AS ENUM (
        'queued',
        'submitted',
        'sent',
        'delivered',
        'failed',
        'undelivered',
        'reconciliation_required'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 3. Create public.notification_dispatches table
CREATE TABLE IF NOT EXISTS public.notification_dispatches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES public.users(id) ON DELETE SET NULL,
    farm_id UUID REFERENCES public.farms(id) ON DELETE SET NULL,
    alert_id UUID REFERENCES public.farm_alerts(id) ON DELETE SET NULL,
    prediction_id UUID REFERENCES public.predictions(id) ON DELETE SET NULL,
    channel TEXT NOT NULL DEFAULT 'sms' CHECK (channel IN ('sms', 'whatsapp')),
    phone_number_masked VARCHAR(32) NOT NULL,
    message_body TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    status dispatch_status_enum NOT NULL DEFAULT 'queued',
    provider TEXT NOT NULL DEFAULT 'twilio',
    provider_message_id TEXT,
    error_code TEXT,
    error_message_sanitized TEXT,
    retry_count INT NOT NULL DEFAULT 0,
    max_retries INT NOT NULL DEFAULT 3,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    submitted_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ
);

-- 4. High-Performance Indexes
CREATE INDEX IF NOT EXISTS idx_notification_dispatches_user ON public.notification_dispatches(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notification_dispatches_farm ON public.notification_dispatches(farm_id);
CREATE INDEX IF NOT EXISTS idx_notification_dispatches_alert ON public.notification_dispatches(alert_id);
CREATE INDEX IF NOT EXISTS idx_notification_dispatches_channel ON public.notification_dispatches(channel);
CREATE INDEX IF NOT EXISTS idx_notification_dispatches_status ON public.notification_dispatches(status);
CREATE INDEX IF NOT EXISTS idx_notification_dispatches_provider_msg ON public.notification_dispatches(provider_message_id);

-- 5. Enable Row-Level Security (RLS)
ALTER TABLE public.notification_dispatches ENABLE ROW LEVEL SECURITY;

-- Policy 1: Users view their own notification dispatches; Experts/Admins view cross-farm records
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'notification_dispatches' AND policyname = 'Users can view own notification dispatches'
    ) THEN
        CREATE POLICY "Users can view own notification dispatches"
        ON public.notification_dispatches
        FOR SELECT
        TO authenticated
        USING (
            user_id = auth.uid()
            OR public.current_user_role() IN ('expert', 'admin')
        );
    END IF;
END $$;

-- Policy 2: Authenticated users can insert/update only via service operations
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'notification_dispatches' AND policyname = 'Users cannot directly manipulate dispatch records'
    ) THEN
        CREATE POLICY "Users cannot directly manipulate dispatch records"
        ON public.notification_dispatches
        FOR ALL
        TO authenticated
        USING (false)
        WITH CHECK (false);
    END IF;
END $$;

-- 6. Grants: Restricted to authenticated read, full access to service_role
GRANT SELECT ON public.notification_dispatches TO authenticated;
GRANT ALL ON public.notification_dispatches TO service_role;
