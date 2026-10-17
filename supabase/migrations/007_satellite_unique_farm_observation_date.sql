-- Migration 007: Satellite unique constraint on (farm_id, observation_date)
-- Prevents duplicate satellite observation records for the same farm and pass date

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_satellite_obs_farm_date'
    ) THEN
        ALTER TABLE public.satellite_observations
            ADD CONSTRAINT uq_satellite_obs_farm_date UNIQUE (farm_id, observation_date);
    END IF;
END $$;

