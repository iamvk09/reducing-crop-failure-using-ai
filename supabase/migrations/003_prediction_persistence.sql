-- =============================================================================
-- Crop Risk Intelligence Platform - Prediction & Recommendation Persistence
-- Migration: 003_prediction_persistence.sql
-- =============================================================================

-- 1. Schema alignment for predictions table
ALTER TABLE public.predictions
    ADD COLUMN IF NOT EXISTS crop_id UUID REFERENCES public.farm_crops(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS state TEXT,
    ADD COLUMN IF NOT EXISTS district TEXT,
    ADD COLUMN IF NOT EXISTS prediction_class INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS consensus_risk NUMERIC(6, 4),
    ADD COLUMN IF NOT EXISTS best_model_name TEXT DEFAULT 'agri_ai_runtime_bundle',
    ADD COLUMN IF NOT EXISTS weather_data JSONB,
    ADD COLUMN IF NOT EXISTS weather_source TEXT DEFAULT 'Open-Meteo',
    ADD COLUMN IF NOT EXISTS is_fallback_weather BOOLEAN DEFAULT false;

-- 2. Enhanced composite indexes for query performance
CREATE INDEX IF NOT EXISTS idx_predictions_farm_created_at
    ON public.predictions(farm_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_predictions_user_created_at
    ON public.predictions(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendations_prediction_id
    ON public.recommendations(prediction_id);

-- -----------------------------------------------------------------------------
-- 3. Hardened RLS Policies for Predictions and Recommendations
-- -----------------------------------------------------------------------------

-- Drop previous prediction policies if any to recreate idempotent rules
DROP POLICY IF EXISTS "Users can view own predictions" ON public.predictions;
DROP POLICY IF EXISTS "Users can insert own predictions" ON public.predictions;

-- SELECT: Farmers see predictions for their own user_id or farms they own; Experts & Admins view all
CREATE POLICY "Users can view own predictions"
    ON public.predictions FOR SELECT
    USING (
        auth.uid() = user_id 
        OR public.current_user_role() IN ('expert', 'admin')
        OR EXISTS (
            SELECT 1 FROM public.farms f
            WHERE f.id = predictions.farm_id
            AND f.user_id = auth.uid()
        )
    );

-- INSERT: Authenticated users can insert predictions tagged with their own user_id
CREATE POLICY "Users can insert own predictions"
    ON public.predictions FOR INSERT
    WITH CHECK (
        auth.uid() = user_id
    );

-- RECOMMENDATIONS RLS Policies
DROP POLICY IF EXISTS "Users can view own recommendations" ON public.recommendations;
DROP POLICY IF EXISTS "Users can insert recommendations for own predictions" ON public.recommendations;

-- SELECT: Read recommendations linked to accessible predictions
CREATE POLICY "Users can view own recommendations"
    ON public.recommendations FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.predictions p
            WHERE p.id = recommendations.prediction_id
            AND (
                p.user_id = auth.uid() 
                OR public.current_user_role() IN ('expert', 'admin')
            )
        )
    );

-- INSERT: Insert recommendations linked to own predictions
CREATE POLICY "Users can insert recommendations for own predictions"
    ON public.recommendations FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.predictions p
            WHERE p.id = recommendations.prediction_id
            AND (
                p.user_id = auth.uid() 
                OR public.current_user_role() IN ('expert', 'admin')
            )
        )
    );
