-- Migration 008: Add farm boundary geometry (GeoJSON Polygon/MultiPolygon)
-- Adds optional boundary_geojson JSONB column to public.farms table

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'farms'
          AND column_name = 'boundary_geojson'
    ) THEN
        ALTER TABLE public.farms
            ADD COLUMN boundary_geojson JSONB;
    END IF;
END $$;

COMMENT ON COLUMN public.farms.boundary_geojson IS 'Optional GeoJSON Polygon or MultiPolygon defining the exact farm boundary';

-- Notify PostgREST to reload schema cache
NOTIFY pgrst, 'reload schema';
