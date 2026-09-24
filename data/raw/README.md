# Official observed-data inputs

Do not place synthetic data in this folder.

## 1. DES crop production

Save an official Directorate of Economics and Statistics export as
`des_crop_production.csv`. It must contain these normalized columns:

`District, State, Year, Season, Crop, Area, Production`

`Area` must be in hectares and `Production` in tonnes. Keep the original export
alongside it with a source date and download URL.

## 2. Historical weather

Save district-season aggregates generated from official IMD gridded observations
as `imd_district_season_weather.csv`. Required columns:

`District, State, Year, Season, Rainfall, Temperature`

Optional observed columns include `Humidity`, `SoilMoisture`, and source-grid
metadata. Rainfall and temperature must be aggregated using the same seasonal
definition as the DES crop record.

For the initial pilot, `python3 -m src.fetch_open_meteo_history` creates
`open_meteo_district_daily_weather.csv` from the DES report and Open-Meteo's
historical API. It is a daily source file; aggregate it to the standard
district-season schema above before calling the observed dataset builder.

## Build

```bash
python3 -m src.build_observed_dataset
```

This writes `data/district_observed_dataset.csv`. Review its coverage and
provenance before replacing any demonstration data or retraining a model.
