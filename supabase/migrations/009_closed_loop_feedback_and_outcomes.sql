-- =============================================================================
-- Crop Risk Intelligence Platform - Closed-Loop Feedback & Outcome Tracking
-- Migration: 009_closed_loop_feedback_and_outcomes.sql
-- =============================================================================

-- 1. Extend farm_crops with ground-truth harvest/failure outcome tracking
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'farm_crops'
          AND column_name = 'actual_harvest_date'
    ) THEN
        ALTER TABLE public.farm_crops
            ADD COLUMN actual_harvest_date DATE,
            ADD COLUMN reported_yield_kg_per_ha NUMERIC(10, 2),
            ADD COLUMN outcome_notes TEXT;
    END IF;
END $$;

COMMENT ON COLUMN public.farm_crops.actual_harvest_date IS 'Actual harvest date recorded by farmer or expert';
COMMENT ON COLUMN public.farm_crops.reported_yield_kg_per_ha IS 'Actual harvested yield in kg per hectare';
COMMENT ON COLUMN public.farm_crops.outcome_notes IS 'Observed outcome notes (e.g. drought impact, pest incidence, normal harvest)';

-- 2. Create farm_feedback table for logging farmer actions & advisory acknowledgments
CREATE TABLE IF NOT EXISTS public.farm_feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    farm_id UUID NOT NULL REFERENCES public.farms(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    prediction_id UUID REFERENCES public.predictions(id) ON DELETE SET NULL,
    action_type TEXT NOT NULL, -- 'recommendation_viewed', 'recommendation_acknowledged', 'irrigation_applied', 'fertilizer_applied', 'pest_control_applied', 'farmer_note'
    notes TEXT,
    action_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_farm_feedback_farm_id ON public.farm_feedback(farm_id, action_date DESC);
CREATE INDEX IF NOT EXISTS idx_farm_feedback_user_id ON public.farm_feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_farm_feedback_prediction_id ON public.farm_feedback(prediction_id);

-- 3. Row Level Security for farm_feedback
ALTER TABLE public.farm_feedback ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own farm feedback" ON public.farm_feedback;
CREATE POLICY "Users can view own farm feedback"
    ON public.farm_feedback FOR SELECT
    USING (
        auth.uid() = user_id
        OR (auth.jwt() -> 'app_metadata' ->> 'role') IN ('expert', 'admin')
        OR (auth.jwt() -> 'user_metadata' ->> 'role') IN ('expert', 'admin')
        OR EXISTS (
            SELECT 1 FROM public.farms f
            WHERE f.id = farm_feedback.farm_id
            AND f.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "Users can insert own farm feedback" ON public.farm_feedback;
CREATE POLICY "Users can insert own farm feedback"
    ON public.farm_feedback FOR INSERT
    WITH CHECK (
        auth.uid() = user_id
        OR (auth.jwt() -> 'app_metadata' ->> 'role') IN ('expert', 'admin')
        OR (auth.jwt() -> 'user_metadata' ->> 'role') IN ('expert', 'admin')
        OR EXISTS (
            SELECT 1 FROM public.farms f
            WHERE f.id = farm_feedback.farm_id
            AND f.user_id = auth.uid()
        )
    );

-- 4. Grants
GRANT SELECT, INSERT ON public.farm_feedback TO authenticated;
GRANT ALL ON public.farm_feedback TO service_role;

-- Notify PostgREST to reload schema cache
NOTIFY pgrst, 'reload schema';

