-- Migration 010: Early Warning & Alert Engine Schema
-- Table: public.farm_alerts

CREATE TABLE IF NOT EXISTS public.farm_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    farm_id UUID NOT NULL REFERENCES public.farms(id) ON DELETE CASCADE,
    crop_id UUID REFERENCES public.farm_crops(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    alert_type TEXT NOT NULL CHECK (
        alert_type IN (
            'RISK_THRESHOLD_CROSSED',
            'RISK_TREND_INCREASING',
            'TELEMETRY_DEGRADATION',
            'SATELLITE_STALE',
            'WEATHER_STALE',
            'DATA_QUALITY_DEGRADED'
        )
    ),
    severity TEXT NOT NULL CHECK (severity IN ('critical', 'warning', 'info', 'CRITICAL', 'WARNING', 'INFO')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'acknowledged', 'resolved', 'ACTIVE', 'ACKNOWLEDGED', 'RESOLVED')),
    trigger_reason TEXT NOT NULL,
    prediction_id UUID REFERENCES public.predictions(id) ON DELETE SET NULL,
    risk_probability NUMERIC(5, 4),
    previous_risk_probability NUMERIC(5, 4),
    risk_delta_pp NUMERIC(6, 2),
    recommended_action TEXT,
    shap_context JSONB DEFAULT '[]'::jsonb,
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by UUID REFERENCES auth.users(id),
    resolved_at TIMESTAMPTZ,
    resolved_by UUID REFERENCES auth.users(id),
    resolution_notes TEXT
);

-- Indexes for high-throughput operational queries
CREATE INDEX IF NOT EXISTS idx_farm_alerts_farm_status ON public.farm_alerts(farm_id, status);
CREATE INDEX IF NOT EXISTS idx_farm_alerts_farm_created ON public.farm_alerts(farm_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_farm_alerts_severity ON public.farm_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_farm_alerts_prediction ON public.farm_alerts(prediction_id);

-- Enable Row-Level Security
ALTER TABLE public.farm_alerts ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Farmers can select alerts for farms they own
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'farm_alerts' AND policyname = 'Farmers can view alerts for their farms'
    ) THEN
        CREATE POLICY "Farmers can view alerts for their farms"
        ON public.farm_alerts
        FOR SELECT
        TO authenticated
        USING (
            farm_id IN (SELECT id FROM public.farms WHERE user_id = auth.uid())
            OR EXISTS (SELECT 1 FROM public.users WHERE id = auth.uid() AND role IN ('expert', 'admin'))
        );
    END IF;
END $$;

-- RLS Policy: Farmers can update/acknowledge alerts for farms they own
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'farm_alerts' AND policyname = 'Farmers can acknowledge alerts for their farms'
    ) THEN
        CREATE POLICY "Farmers can acknowledge alerts for their farms"
        ON public.farm_alerts
        FOR UPDATE
        TO authenticated
        USING (
            farm_id IN (SELECT id FROM public.farms WHERE user_id = auth.uid())
            OR EXISTS (SELECT 1 FROM public.users WHERE id = auth.uid() AND role IN ('expert', 'admin'))
        )
        WITH CHECK (
            farm_id IN (SELECT id FROM public.farms WHERE user_id = auth.uid())
            OR EXISTS (SELECT 1 FROM public.users WHERE id = auth.uid() AND role IN ('expert', 'admin'))
        );
    END IF;
END $$;

-- Permissions Grants
GRANT SELECT, INSERT, UPDATE, DELETE ON public.farm_alerts TO authenticated;
GRANT ALL ON public.farm_alerts TO service_role;

