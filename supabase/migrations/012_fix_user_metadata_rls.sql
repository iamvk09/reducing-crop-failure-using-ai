-- =============================================================================
-- Crop Risk Intelligence Platform - Security Hardening Migration
-- Migration: 012_fix_user_metadata_rls.sql
-- =============================================================================
-- Objective:
-- 1. Fix Supabase Advisor Security Warning: "RLS references user metadata" on public.users.
-- 2. Strictly eliminate all authorization checks relying on client-editable `user_metadata`.
-- 3. Rely exclusively on server-managed `app_metadata` (`auth.jwt() -> 'app_metadata' ->> 'role'`)
--    for non-recursive role evaluation in JWTs, alongside security definer helper `public.current_user_role()`.
-- 4. Eliminate infinite recursion in public.users UPDATE policy:
--    - Avoid subqueries against public.users within public.users RLS policies.
--    - Enforce role & id immutability via non-bypassable BEFORE UPDATE trigger.
-- 5. Revoke table-level UPDATE on public.users from authenticated and grant strictly column-level UPDATE.
-- 6. Harden public.farm_feedback policies to eliminate user_metadata role evaluations.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Helper function public.current_user_role() - Safe Security Definer Configuration
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.current_user_role()
RETURNS user_role
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    -- Explicitly reads role from public.users using elevated definer privileges
    SELECT role FROM public.users WHERE id = auth.uid();
$$ LANGUAGE sql;

-- Function permission lockdown
REVOKE ALL ON FUNCTION public.current_user_role() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.current_user_role() TO authenticated, service_role;

-- -----------------------------------------------------------------------------
-- 2. Database Trigger: Absolute Immunity Against Role & ID Tampering on public.users
-- -----------------------------------------------------------------------------
-- In addition to RLS, a trigger executes at the engine level for EVERY update row.
-- If an authenticated user attempts to alter their role, id, or email directly or indirectly,
-- the update is blocked or coerced back to the authoritative value.
CREATE OR REPLACE FUNCTION public.enforce_user_immutability()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    -- Only service_role or superuser can change roles directly on public.users
    IF (auth.jwt() ->> 'role') != 'service_role' AND current_user NOT IN ('postgres', 'service_role') THEN
        IF NEW.role IS DISTINCT FROM OLD.role THEN
            RAISE EXCEPTION 'Unauthorized: User role cannot be modified by user.';
        END IF;
        IF NEW.id IS DISTINCT FROM OLD.id THEN
            RAISE EXCEPTION 'Unauthorized: User ID is immutable.';
        END IF;
        IF NEW.email IS DISTINCT FROM OLD.email THEN
            RAISE EXCEPTION 'Unauthorized: User email is managed by auth service.';
        END IF;
        IF NEW.is_active IS DISTINCT FROM OLD.is_active THEN
            RAISE EXCEPTION 'Unauthorized: Account status cannot be modified by user.';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trigger_enforce_user_immutability ON public.users;
CREATE TRIGGER trigger_enforce_user_immutability
    BEFORE UPDATE ON public.users
    FOR EACH ROW
    EXECUTE FUNCTION public.enforce_user_immutability();

-- -----------------------------------------------------------------------------
-- 3. Non-Recursive RLS Policies on public.users
-- -----------------------------------------------------------------------------
-- Drop legacy or recursive policies
DROP POLICY IF EXISTS "Users can read own profile" ON public.users;
DROP POLICY IF EXISTS "Users can read own profile and staff can read all" ON public.users;
DROP POLICY IF EXISTS "Users can update own profile" ON public.users;

-- SELECT: Non-recursive. Evaluates auth.uid() = id, trusted app_metadata role claim,
-- or current_user_role() (which is SECURITY DEFINER and bypasses recursive RLS).
CREATE POLICY "Users can read own profile and staff can read all"
    ON public.users
    FOR SELECT
    TO authenticated
    USING (
        auth.uid() = id
        OR (auth.jwt() -> 'app_metadata' ->> 'role') IN ('expert', 'admin')
        OR public.current_user_role() IN ('expert', 'admin')
    );

-- UPDATE: Non-recursive. Strictly verifies auth.uid() = id without self-referential subqueries.
-- Role modification protection is guaranteed by trigger enforce_user_immutability AND column grants.
CREATE POLICY "Users can update own profile"
    ON public.users
    FOR UPDATE
    TO authenticated
    USING (auth.uid() = id)
    WITH CHECK (auth.uid() = id);

-- -----------------------------------------------------------------------------
-- 4. Defense-in-Depth Column-Level Permissions on public.users
-- -----------------------------------------------------------------------------
-- Revoke all table-level UPDATE privileges on public.users from authenticated
REVOKE UPDATE ON public.users FROM authenticated;

-- Grant column-level UPDATE ONLY on safe, user-editable profile columns
GRANT UPDATE (
    full_name,
    phone_number,
    preferred_language,
    sms_notifications_enabled,
    sms_consent_timestamp,
    whatsapp_notifications_enabled,
    whatsapp_consent_timestamp,
    updated_at
) ON public.users TO authenticated;

-- Ensure authenticated can still SELECT necessary profile columns
GRANT SELECT ON public.users TO authenticated;

-- -----------------------------------------------------------------------------
-- 5. Harden public.farm_feedback RLS Policies (Eliminate user_metadata checks)
-- -----------------------------------------------------------------------------
DROP POLICY IF EXISTS "Users can view own farm feedback" ON public.farm_feedback;
CREATE POLICY "Users can view own farm feedback"
    ON public.farm_feedback
    FOR SELECT
    TO authenticated
    USING (
        auth.uid() = user_id
        OR (auth.jwt() -> 'app_metadata' ->> 'role') IN ('expert', 'admin')
        OR public.current_user_role() IN ('expert', 'admin')
        OR EXISTS (
            SELECT 1 FROM public.farms f
            WHERE f.id = farm_feedback.farm_id
            AND f.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "Users can insert own farm feedback" ON public.farm_feedback;
CREATE POLICY "Users can insert own farm feedback"
    ON public.farm_feedback
    FOR INSERT
    TO authenticated
    WITH CHECK (
        auth.uid() = user_id
        OR (auth.jwt() -> 'app_metadata' ->> 'role') IN ('expert', 'admin')
        OR public.current_user_role() IN ('expert', 'admin')
        OR EXISTS (
            SELECT 1 FROM public.farms f
            WHERE f.id = farm_feedback.farm_id
            AND f.user_id = auth.uid()
        )
    );

-- -----------------------------------------------------------------------------
-- 6. Notify PostgREST to reload schema cache
-- -----------------------------------------------------------------------------
NOTIFY pgrst, 'reload schema';
