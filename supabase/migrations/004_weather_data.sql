-- =============================================================================
-- Crop Risk Intelligence Platform - Weather Observations Schema Alignment
-- Migration: 004_weather_data.sql
-- =============================================================================

-- 1. Schema alignment for weather_observations table
ALTER TABLE public.weather_observations
    ADD COLUMN IF NOT EXISTS latitude NUMERIC(8, 5),
    ADD COLUMN IF NOT EXISTS longitude NUMERIC(8, 5),
    ADD COLUMN IF NOT EXISTS is_forecast BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS soil_moisture_m3m3 NUMERIC(5, 4);

-- 2. Index for fast farm-specific time-series queries
CREATE INDEX IF NOT EXISTS idx_weather_observations_farm_time
    ON public.weather_observations(farm_id, observation_time DESC);

-- 3. Hardened RLS Policies for Weather Observations
DROP POLICY IF EXISTS "Users can insert weather observations" ON public.weather_observations;

CREATE POLICY "Users can insert weather observations"
    ON public.weather_observations FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.farms f
            WHERE f.id = weather_observations.farm_id
            AND (f.user_id = auth.uid() OR public.current_user_role() IN ('expert', 'admin'))
        )
    );
