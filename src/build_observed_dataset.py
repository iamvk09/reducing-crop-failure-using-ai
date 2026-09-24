"""Build a traceable observed DES + historical-weather dataset.

This intentionally does not fabricate missing measurements.  It produces a new
file instead of replacing the synthetic demonstration dataset.
"""

from pathlib import Path

import pandas as pd


RAW_DIR = Path("data/raw")
OUTPUT_PATH = Path("data/district_observed_dataset.csv")
COVERAGE_PATH = Path("data/district_observed_coverage.csv")
SELECTION_PATH = RAW_DIR / "selected_important_districts.csv"
REQUIRED_CROP_COLUMNS = {"District", "State", "Year", "Season", "Crop", "Area", "Production"}
REQUIRED_WEATHER_COLUMNS = {"District", "State", "Year", "Rainfall", "Temperature"}


def _read_and_validate(path, required_columns, source_name):
    if not path.exists():
        raise FileNotFoundError(f"Missing {source_name} input: {path}")
    frame = pd.read_csv(path)
    missing = required_columns - set(frame.columns)
    if missing:
        raise ValueError(f"{source_name} is missing required columns: {sorted(missing)}")
    return frame


def build_observed_dataset(
    crop_path=RAW_DIR / "des_crop_production.csv",
    weather_path=RAW_DIR / "open_meteo_district_annual_weather.csv",
    output_path=OUTPUT_PATH,
    coverage_path=COVERAGE_PATH,
    selection_path=SELECTION_PATH,
    failure_threshold=-0.20,
):
    """Join official crop outcomes to observed historical district weather.

    ``FailureLikeEvent`` is a transparent yield-anomaly flag, not an insurance
    claim or a confirmed individual-farm crop failure.
    """
    crop = _read_and_validate(crop_path, REQUIRED_CROP_COLUMNS, "DES crop production")
    weather = _read_and_validate(weather_path, REQUIRED_WEATHER_COLUMNS, "historical weather")
    selection = _read_and_validate(
        selection_path, {"District", "State", "SelectionRank", "SelectionMethod"}, "district selection"
    )
    selection = selection[["State", "District", "SelectionRank", "SelectionMethod"]].drop_duplicates(
        ["State", "District"]
    )

    crop = crop.copy()
    crop["Year"] = pd.to_numeric(crop["Year"], errors="coerce")
    crop["Area"] = pd.to_numeric(crop["Area"], errors="coerce")
    crop["Production"] = pd.to_numeric(crop["Production"], errors="coerce")
    crop = crop.dropna(subset=["Year", "Area", "Production"])
    crop["Year"] = crop["Year"].astype(int)
    crop = crop.merge(selection, on=["State", "District"], how="inner", validate="many_to_one")

    crop["YieldTonnesPerHectare"] = crop["Production"] / crop["Area"].replace(0, pd.NA)
    crop = crop.dropna(subset=["YieldTonnesPerHectare"])
    keys = ["District", "State", "Year", "Season", "Crop"]
    crop = crop.sort_values(keys)
    group_keys = ["District", "State", "Season", "Crop"]
    crop["HistoricalYieldBaseline"] = crop.groupby(group_keys)["YieldTonnesPerHectare"].transform(
        lambda values: values.shift(1).rolling(5, min_periods=3).mean()
    )
    crop["YieldAnomaly"] = (
        crop["YieldTonnesPerHectare"] / crop["HistoricalYieldBaseline"] - 1
    )
    crop["FailureLikeEvent"] = (crop["YieldAnomaly"] <= failure_threshold).where(
        crop["YieldAnomaly"].notna(), pd.NA
    ).astype("Int64")

    weather_keys = ["District", "State", "Year"]
    weather = weather.drop_duplicates(weather_keys)
    merged = crop.merge(weather, on=weather_keys, how="left", validate="many_to_one", indicator=True)
    missing_weather = merged.loc[merged["_merge"] != "both", weather_keys].drop_duplicates()
    # Keep only records backed by both authoritative DES values and real API
    # weather observations.  Coverage is exported separately; missing values
    # are never filled or represented as observed.
    observed = merged.loc[merged["_merge"] == "both"].drop(columns="_merge")
    observed["CropDataSource"] = "DES, Ministry of Agriculture & Farmers Welfare"
    observed["WeatherDataSource"] = "Open-Meteo Historical Weather API"
    observed["OutcomeDefinition"] = f"Yield anomaly <= {failure_threshold:.0%} vs preceding 5-year mean"
    observed["ObservationStatus"] = "Observed DES production + historical weather API"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    observed.to_csv(output_path, index=False)
    coverage_path = Path(coverage_path)
    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    missing_weather.assign(Status="No matched historical weather observation").to_csv(
        coverage_path, index=False
    )
    return observed


if __name__ == "__main__":
    result = build_observed_dataset()
    print(f"Wrote {len(result):,} observed records to {OUTPUT_PATH}")
