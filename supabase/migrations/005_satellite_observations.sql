-- =============================================================================
-- Crop Risk Intelligence Platform - Satellite & Vegetation Observations Schema
-- Migration: 005_satellite_observations.sql
-- =============================================================================

-- 1. Schema alignment for satellite_observations table
ALTER TABLE public.satellite_observations
    ADD COLUMN IF NOT EXISTS ndvi_median NUMERIC(5, 4),
    ADD COLUMN IF NOT EXISTS ndvi_std NUMERIC(5, 4),
    ADD COLUMN IF NOT EXISTS valid_pixel_percent NUMERIC(5, 2),
    ADD COLUMN IF NOT EXISTS cloud_percent NUMERIC(5, 2),
    ADD COLUMN IF NOT EXISTS provider TEXT DEFAULT 'GoogleEarthEngine',
    ADD COLUMN IF NOT EXISTS satellite TEXT DEFAULT 'Sentinel-2',
    ADD COLUMN IF NOT EXISTS product TEXT DEFAULT 'COPERNICUS/S2_SR_HARMONIZED',
    ADD COLUMN IF NOT EXISTS geometry_type TEXT DEFAULT 'buffered_point',
    ADD COLUMN IF NOT EXISTS processing_status TEXT DEFAULT 'COMPLETED',
    ADD COLUMN IF NOT EXISTS quality_status TEXT DEFAULT 'GOOD',
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- 2. Fast query indexes for time-series retrieval
CREATE INDEX IF NOT EXISTS idx_satellite_obs_farm_date
    ON public.satellite_observations(farm_id, observation_date DESC);

CREATE INDEX IF NOT EXISTS idx_satellite_obs_quality
    ON public.satellite_observations(farm_id, quality_status);

-- 3. Row-Level Security Policies for Satellite Observations
ALTER TABLE public.satellite_observations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own farm satellite observations" ON public.satellite_observations;
DROP POLICY IF EXISTS "Users can insert satellite observations for own farm" ON public.satellite_observations;

CREATE POLICY "Users can view own farm satellite observations"
    ON public.satellite_observations FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.farms f
            WHERE f.id = satellite_observations.farm_id
            AND (f.user_id = auth.uid() OR public.current_user_role() IN ('expert', 'admin'))
        )
    );

CREATE POLICY "Users can insert satellite observations for own farm"
    ON public.satellite_observations FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.farms f
            WHERE f.id = satellite_observations.farm_id
            AND (f.user_id = auth.uid() OR public.current_user_role() IN ('expert', 'admin'))
        )
    );
