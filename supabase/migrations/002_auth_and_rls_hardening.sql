-- =============================================================================
-- Crop Risk Intelligence Platform - Auth & RLS Hardening Migration
-- Migration: 002_auth_and_rls_hardening.sql
-- =============================================================================

-- 1. Helper function for fast, non-recursive role lookup
CREATE OR REPLACE FUNCTION public.current_user_role()
RETURNS user_role
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT role FROM public.users WHERE id = auth.uid();
$$ LANGUAGE sql;

-- 2. Schema schema alignment for farms and farm_crops
ALTER TABLE public.farms 
    ADD COLUMN IF NOT EXISTS village TEXT;

ALTER TABLE public.farm_crops 
    ADD COLUMN IF NOT EXISTS soil_type TEXT,
    ADD COLUMN IF NOT EXISTS irrigation_level TEXT,
    ADD COLUMN IF NOT EXISTS growth_stage TEXT;

-- -----------------------------------------------------------------------------
-- 3. Farm Crops RLS Policies (Enforces Farm Ownership Isolation)
-- -----------------------------------------------------------------------------

-- Drop existing generic or permissive policies if any
DROP POLICY IF EXISTS "Users can view farm crops" ON public.farm_crops;
DROP POLICY IF EXISTS "Users can insert farm crops" ON public.farm_crops;
DROP POLICY IF EXISTS "Users can update farm crops" ON public.farm_crops;
DROP POLICY IF EXISTS "Users can delete farm crops" ON public.farm_crops;

-- SELECT: Farmers read crops of their own farms; Experts/Admins read all
CREATE POLICY "Farmers can read crops on own farms"
    ON public.farm_crops FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.farms f
            WHERE f.id = farm_crops.farm_id
            AND (f.user_id = auth.uid() OR public.current_user_role() IN ('expert', 'admin'))
        )
    );

-- INSERT: Farmers insert crops only on farms they own
CREATE POLICY "Farmers can insert crops on own farms"
    ON public.farm_crops FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.farms f
            WHERE f.id = farm_crops.farm_id
            AND f.user_id = auth.uid()
        )
    );

-- UPDATE: Farmers update crops only on farms they own
CREATE POLICY "Farmers can update crops on own farms"
    ON public.farm_crops FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM public.farms f
            WHERE f.id = farm_crops.farm_id
            AND f.user_id = auth.uid()
        )
    );

-- DELETE: Farmers delete crops only on farms they own
CREATE POLICY "Farmers can delete crops on own farms"
    ON public.farm_crops FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM public.farms f
            WHERE f.id = farm_crops.farm_id
            AND f.user_id = auth.uid()
        )
    );

-- -----------------------------------------------------------------------------
-- 4. Weather and Satellite Observations RLS Policies
-- -----------------------------------------------------------------------------
DROP POLICY IF EXISTS "Users can view weather observations" ON public.weather_observations;
DROP POLICY IF EXISTS "Users can view satellite observations" ON public.satellite_observations;

CREATE POLICY "Users can view weather for accessible farms"
    ON public.weather_observations FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.farms f
            WHERE f.id = weather_observations.farm_id
            AND (f.user_id = auth.uid() OR public.current_user_role() IN ('expert', 'admin'))
        )
    );

CREATE POLICY "Users can view satellite data for accessible farms"
    ON public.satellite_observations FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.farms f
            WHERE f.id = satellite_observations.farm_id
            AND (f.user_id = auth.uid() OR public.current_user_role() IN ('expert', 'admin'))
        )
    );

-- -----------------------------------------------------------------------------
-- 5. Recommendations RLS Policies
-- -----------------------------------------------------------------------------
DROP POLICY IF EXISTS "Users can view recommendations" ON public.recommendations;

CREATE POLICY "Users can view own recommendations"
    ON public.recommendations FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.predictions p
            WHERE p.id = recommendations.prediction_id
            AND (p.user_id = auth.uid() OR public.current_user_role() IN ('expert', 'admin'))
        )
    );

-- -----------------------------------------------------------------------------
-- 6. Audit Logs RLS Policies
-- -----------------------------------------------------------------------------
DROP POLICY IF EXISTS "Users can view audit logs" ON public.audit_logs;
DROP POLICY IF EXISTS "Users can insert audit logs" ON public.audit_logs;

CREATE POLICY "Users can view own audit logs"
    ON public.audit_logs FOR SELECT
    USING (
        auth.uid() = user_id OR public.current_user_role() = 'admin'
    );

CREATE POLICY "Authenticated users can insert audit logs"
    ON public.audit_logs FOR INSERT
    TO authenticated
    WITH CHECK (
        auth.uid() = user_id OR user_id IS NULL
    );
