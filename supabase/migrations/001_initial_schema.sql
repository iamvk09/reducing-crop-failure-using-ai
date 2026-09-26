-- =============================================================================
-- Crop Risk Intelligence Platform - Initial Supabase Database Schema
-- Migration: 001_initial_schema.sql
-- =============================================================================

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- -----------------------------------------------------------------------------
-- Enums
-- -----------------------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE user_role AS ENUM ('farmer', 'expert', 'admin');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE risk_level_enum AS ENUM ('Low', 'Medium', 'High');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE alert_severity_enum AS ENUM ('low', 'medium', 'high', 'critical');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- -----------------------------------------------------------------------------
-- Helper Trigger for updated_at
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- -----------------------------------------------------------------------------
-- 1. Users Profile (Extends Supabase auth.users)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT UNIQUE,
    full_name TEXT,
    phone_number VARCHAR(20),
    role user_role NOT NULL DEFAULT 'farmer',
    preferred_language VARCHAR(10) NOT NULL DEFAULT 'en',
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_role ON public.users(role);
CREATE INDEX IF NOT EXISTS idx_users_phone ON public.users(phone_number);

CREATE OR REPLACE TRIGGER trigger_users_updated_at
    BEFORE UPDATE ON public.users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- -----------------------------------------------------------------------------
-- 2. Farms
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.farms (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    state TEXT NOT NULL,
    district TEXT NOT NULL,
    region TEXT NOT NULL,
    latitude NUMERIC(8, 5) NOT NULL,
    longitude NUMERIC(8, 5) NOT NULL,
    area_hectares NUMERIC(10, 2),
    soil_type TEXT,
    irrigation_level TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_latitude CHECK (latitude >= -90.0 AND latitude <= 90.0),
    CONSTRAINT chk_longitude CHECK (longitude >= -180.0 AND longitude <= 180.0)
);

CREATE INDEX IF NOT EXISTS idx_farms_user_id ON public.farms(user_id);
CREATE INDEX IF NOT EXISTS idx_farms_location ON public.farms(state, district);

CREATE OR REPLACE TRIGGER trigger_farms_updated_at
    BEFORE UPDATE ON public.farms
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- -----------------------------------------------------------------------------
-- 3. Farm Crops (Active and Historical Crop Cycles)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.farm_crops (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    farm_id UUID NOT NULL REFERENCES public.farms(id) ON DELETE CASCADE,
    crop TEXT NOT NULL,
    season TEXT NOT NULL,
    sowing_date DATE,
    expected_harvest_date DATE,
    status TEXT NOT NULL DEFAULT 'active', -- 'active', 'harvested', 'failed'
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_farm_crops_farm_id ON public.farm_crops(farm_id);
CREATE INDEX IF NOT EXISTS idx_farm_crops_active ON public.farm_crops(farm_id, is_active);

CREATE OR REPLACE TRIGGER trigger_farm_crops_updated_at
    BEFORE UPDATE ON public.farm_crops
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- -----------------------------------------------------------------------------
-- 4. Weather Observations
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.weather_observations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    farm_id UUID NOT NULL REFERENCES public.farms(id) ON DELETE CASCADE,
    observation_time TIMESTAMPTZ NOT NULL,
    temperature_c NUMERIC(5, 2),
    humidity_pct NUMERIC(5, 2),
    precipitation_mm NUMERIC(6, 2),
    soil_moisture_pct NUMERIC(5, 2),
    weather_code INT,
    source TEXT NOT NULL DEFAULT 'Open-Meteo',
    raw_data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_weather_farm_time ON public.weather_observations(farm_id, observation_time DESC);

-- -----------------------------------------------------------------------------
-- 5. Satellite Observations
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.satellite_observations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    farm_id UUID NOT NULL REFERENCES public.farms(id) ON DELETE CASCADE,
    observation_date DATE NOT NULL,
    ndvi_mean NUMERIC(5, 4),
    ndvi_min NUMERIC(5, 4),
    ndvi_max NUMERIC(5, 4),
    water_stress_index NUMERIC(5, 4),
    source TEXT NOT NULL DEFAULT 'Sentinel-2 / Derived',
    raw_metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_satellite_farm_date ON public.satellite_observations(farm_id, observation_date DESC);

-- -----------------------------------------------------------------------------
-- 6. Model Versions
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.model_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    model_name TEXT NOT NULL,
    version TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    metrics JSONB,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_model_versions_active ON public.model_versions(model_name, is_active);

-- -----------------------------------------------------------------------------
-- 7. Predictions
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.predictions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    farm_id UUID REFERENCES public.farms(id) ON DELETE SET NULL,
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    model_version_id UUID REFERENCES public.model_versions(id) ON DELETE SET NULL,
    crop TEXT NOT NULL,
    season TEXT NOT NULL,
    risk_probability NUMERIC(6, 4) NOT NULL,
    risk_level risk_level_enum NOT NULL,
    global_risk NUMERIC(6, 4),
    region_risk NUMERIC(6, 4),
    crop_risk NUMERIC(6, 4),
    input_features JSONB NOT NULL,
    provenance_metadata JSONB,
    is_farmer_case BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_predictions_farm_id ON public.predictions(farm_id);
CREATE INDEX IF NOT EXISTS idx_predictions_user_id ON public.predictions(user_id);
CREATE INDEX IF NOT EXISTS idx_predictions_created_at ON public.predictions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_predictions_risk_level ON public.predictions(risk_level);

-- -----------------------------------------------------------------------------
-- 8. Recommendations
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.recommendations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prediction_id UUID NOT NULL REFERENCES public.predictions(id) ON DELETE CASCADE,
    farm_id UUID REFERENCES public.farms(id) ON DELETE SET NULL,
    recommended_crop TEXT NOT NULL,
    top_options JSONB NOT NULL,
    advisory_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recommendations_prediction_id ON public.recommendations(prediction_id);
CREATE INDEX IF NOT EXISTS idx_recommendations_farm_id ON public.recommendations(farm_id);

-- -----------------------------------------------------------------------------
-- 9. Alerts
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prediction_id UUID REFERENCES public.predictions(id) ON DELETE SET NULL,
    farm_id UUID REFERENCES public.farms(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    alert_type TEXT NOT NULL, -- 'weather_stress', 'high_failure_risk', 'pest_warning'
    severity alert_severity_enum NOT NULL DEFAULT 'medium',
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unread', -- 'unread', 'read', 'dismissed'
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_user_status ON public.alerts(user_id, status);
CREATE INDEX IF NOT EXISTS idx_alerts_farm_id ON public.alerts(farm_id);

-- -----------------------------------------------------------------------------
-- 10. Audit Logs
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES public.users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    metadata JSONB,
    ip_address TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_user_time ON public.audit_logs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_resource ON public.audit_logs(resource_type, resource_id);

-- -----------------------------------------------------------------------------
-- Row Level Security (RLS) Configuration
-- -----------------------------------------------------------------------------

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.farms ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.farm_crops ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.weather_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.satellite_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.model_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;

-- Base RLS Policies

-- Users: Users can read and update their own profile; Experts & Admins can read all
CREATE POLICY "Users can read own profile"
    ON public.users FOR SELECT
    USING (auth.uid() = id OR (SELECT role FROM public.users WHERE id = auth.uid()) IN ('expert', 'admin'));

CREATE POLICY "Users can update own profile"
    ON public.users FOR UPDATE
    USING (auth.uid() = id);

-- Farms: Farmers own their farms; Experts/Admins can view all farms
CREATE POLICY "Farmers can read own farms"
    ON public.farms FOR SELECT
    USING (auth.uid() = user_id OR (SELECT role FROM public.users WHERE id = auth.uid()) IN ('expert', 'admin'));

CREATE POLICY "Farmers can insert own farms"
    ON public.farms FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Farmers can update own farms"
    ON public.farms FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Farmers can delete own farms"
    ON public.farms FOR DELETE
    USING (auth.uid() = user_id);

-- Predictions: Farmers view own predictions; Experts/Admins view all
CREATE POLICY "Users can view own predictions"
    ON public.predictions FOR SELECT
    USING (auth.uid() = user_id OR (SELECT role FROM public.users WHERE id = auth.uid()) IN ('expert', 'admin'));

CREATE POLICY "Users can insert own predictions"
    ON public.predictions FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Model Versions: Read-only for all authenticated users; Managed by Admins
CREATE POLICY "Authenticated users can read model versions"
    ON public.model_versions FOR SELECT
    TO authenticated
    USING (true);

-- Alerts: Users can view and manage their own alerts
CREATE POLICY "Users can view own alerts"
    ON public.alerts FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can update own alerts"
    ON public.alerts FOR UPDATE
    USING (auth.uid() = user_id);
