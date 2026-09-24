"""Normalize the official DES wide-format export into reproducible row records."""

import re
from pathlib import Path

import pandas as pd

from src.fetch_open_meteo_history import DES_REPORT, _DesTableParser


OUTPUT_PATH = Path("data/raw/des_crop_production.csv")
YEAR_PATTERN = re.compile(r"(\d{4})\s*-\s*(\d{4})")


def prepare_des_data(report_path=DES_REPORT, output_path=OUTPUT_PATH):
    parser = _DesTableParser()
    parser.feed(Path(report_path).read_text(encoding="utf-8", errors="replace"))
    reporting_years = []
    for label in parser.rows[0][3:]:
        match = YEAR_PATTERN.fullmatch(label)
        if not match:
            raise ValueError(f"Unexpected DES reporting-year header: {label}")
        reporting_years.append((int(match.group(1)), label))

    records = []
    for row in parser.rows[2:]:
        if len(row) < 3:
            continue
        state, district = row[1], row[2]
        values = row[3:]
        for index, (year, reporting_year) in enumerate(reporting_years):
            area, production, yield_value = (values + ["", "", ""])[index * 3 : index * 3 + 3]
            if not any([area, production, yield_value]):
                continue
            if not all([area, production, yield_value]):
                # Official report rows can be partially blank; do not infer a value.
                continue
            try:
                area = float(area.replace(",", ""))
                production = float(production.replace(",", ""))
                yield_value = float(yield_value.replace(",", ""))
            except ValueError as error:
                raise ValueError(f"Invalid DES values for {state}, {district}, {reporting_year}") from error
            records.append(
                {
                    "State": state,
                    "District": district,
                    "Year": year,
                    "ReportingYear": reporting_year,
                    "Season": "Whole Year",
                    "Crop": "All Crops",
                    "Area": area,
                    "Production": production,
                    "ReportedYieldTonnesPerHectare": yield_value,
                    "CropDataSource": "DES Area, Production & Yield Query Report",
                }
            )
    frame = pd.DataFrame(records)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)
    return frame


if __name__ == "__main__":
    result = prepare_des_data()
    print(f"Wrote {len(result):,} observed DES records to {OUTPUT_PATH}")
