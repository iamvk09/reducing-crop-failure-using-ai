-- =============================================================================
-- Crop Risk Intelligence Platform - Least Privilege Role Grants & RLS Hardening
-- Migration: 006_grant_permissions_and_fix_rls.sql
-- =============================================================================
-- Principles:
-- 1. anon: Zero access to agricultural & user data; read-only for public model versions registry.
-- 2. authenticated: Granular, table-specific permissions strictly matching active RLS policies.
-- 3. service_role: Full operational privileges for backend services enforcing server-side RBAC.
-- 4. RLS non-recursion: Fast, safe profile access for farmers and staff without self-referencing loops.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Schema Usage Grants
-- -----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;

-- -----------------------------------------------------------------------------
-- 2. Anonymous Role (anon) - Least Privilege (Public metadata only)
-- -----------------------------------------------------------------------------
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon;
REVOKE ALL ON ALL ROUTINES IN SCHEMA public FROM anon;

-- Public read-only model registry lookup
GRANT SELECT ON public.model_versions TO anon;

-- -----------------------------------------------------------------------------
-- 3. Authenticated Role (authenticated) - Scoped to User & Farm Operations
-- -----------------------------------------------------------------------------
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM authenticated;

-- User Profile Management (read own/staff, update own)
GRANT SELECT, UPDATE ON public.users TO authenticated;

-- Farm and Crop Management (CRUD scoped by farm ownership RLS)
GRANT SELECT, INSERT, UPDATE, DELETE ON public.farms TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.farm_crops TO authenticated;

-- ML Predictions & Recommendations (Generate & view predictions)
GRANT SELECT, INSERT ON public.predictions TO authenticated;
GRANT SELECT ON public.recommendations TO authenticated;

-- Telemetry & Environmental Observations (Read-only historical views)
GRANT SELECT ON public.weather_observations TO authenticated;
GRANT SELECT ON public.satellite_observations TO authenticated;

-- Model Registry & Alerts
GRANT SELECT ON public.model_versions TO authenticated;
GRANT SELECT, UPDATE ON public.alerts TO authenticated;

-- Audit Logs (Record user events and read own activity trail)
GRANT SELECT, INSERT ON public.audit_logs TO authenticated;

-- -----------------------------------------------------------------------------
-- 4. Backend Service Role (service_role) - Elevated Server-Side Client
-- -----------------------------------------------------------------------------
-- FastAPI backend services enforce authentication, tenant isolation, and RBAC
-- server-side. The service_role is used exclusively by backend processes with
-- SUPABASE_SECRET_KEY and is never exposed to browser or client applications.
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;
GRANT ALL ON ALL ROUTINES IN SCHEMA public TO service_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON ROUTINES TO service_role;

-- -----------------------------------------------------------------------------
-- 5. RLS Policy Hardening - Fix Recursion on public.users
-- -----------------------------------------------------------------------------
-- Replace the recursive subquery policy with a non-recursive policy that inspects
-- validated JWT claims directly, preserving farmer isolation and expert/admin access.
DROP POLICY IF EXISTS "Users can read own profile" ON public.users;
DROP POLICY IF EXISTS "Users can read own profile and staff can read all" ON public.users;

CREATE POLICY "Users can read own profile and staff can read all"
    ON public.users FOR SELECT
    USING (
        auth.uid() = id
        OR (auth.jwt() -> 'app_metadata' ->> 'role') IN ('expert', 'admin')
        OR (auth.jwt() -> 'user_metadata' ->> 'role') IN ('expert', 'admin')
    );
