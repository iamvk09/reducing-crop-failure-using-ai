# Real observed-data pilot

This project retains `data/district_dataset.csv` as a synthetic demonstration
dataset. It must not be overwritten.

The first observed-data pilot is intentionally limited to Kharif rice in eight
districts from 2013 through 2023: Lucknow, Varanasi, Gorakhpur, Patna,
Muzaffarpur, Cuttack, Bhubaneswar, and Guwahati.

## Required official inputs

1. Export the DES Area, Production & Yield data for the configured districts,
   crop, season, and years. Normalize the column names to the crop schema in
   `data/raw/README.md` and save it as `data/raw/des_crop_production.csv`.
2. Download official IMD gridded rainfall and temperature observations, then
   aggregate them to each district and Kharif season. Save the result as
   `data/raw/imd_district_season_weather.csv`.

No field is simulated. The builder stops if a crop observation has no matching
weather observation.

## Output definition

The output contains observed area, production, yield, rainfall, and temperature.
`FailureLikeEvent` is a reproducible yield-anomaly flag: actual yield at least
20% below the preceding five-year mean for the same district, crop, and season.
It is not an insurance claim and must not be described as a confirmed farm-level
crop failure.

## Build

```bash
python3 -m src.build_observed_dataset
```

The output is `data/district_observed_dataset.csv`. Do not train the existing
synthetic failure model on it: its current features include synthetic NDVI,
soil moisture, water stress, and pest risk. A separate observed-data model and
dashboard adapter will be added only after input coverage is audited.
