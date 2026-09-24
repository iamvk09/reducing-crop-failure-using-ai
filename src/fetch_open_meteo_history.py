"""Download historical weather for DES districts from Open-Meteo.

The DES report is an HTML table saved with an .xls extension.  This module reads
the districts from that report, geocodes their real locations, and downloads
daily precipitation and mean temperature. No weather values are generated or
filled. The final result is annual aggregation, matched to the start year of a
DES reporting-year label (for example, 2013 represents 2013–2014).
"""

import csv
import json
from html.parser import HTMLParser
from pathlib import Path
from time import sleep
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

DES_REPORT = Path("/Users/i_vinaysaini/Downloads/apy_query_report des main.xls")
OUTPUT_PATH = Path("data/raw/open_meteo_district_annual_weather.csv")
FAILED_GEOCODES_PATH = Path("data/raw/open_meteo_geocoding_failures.csv")
WEATHER_FAILURES_PATH = Path("data/raw/open_meteo_weather_failures.csv")
DISTRICT_SELECTION_PATH = Path("data/raw/selected_important_districts.csv")
START_DATE = "2013-01-01"
END_DATE = "2023-12-31"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
BOUNDARY_PATH = Path("data/raw/geoboundaries_ind_adm2.geojson")


class _DesTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell, self.in_table = [], None, None, False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.row = []
        elif self.in_table and tag in {"th", "td"} and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if self.in_table and tag in {"th", "td"} and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif self.in_table and tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        elif tag == "table":
            self.in_table = False


def _request_json(url, parameters, attempts=5):
    query = urlencode(parameters)
    request = Request(f"{url}?{query}", headers={"User-Agent": "AI-Crop-Failure-Project/1.0"})
    last_error = None
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=25) as response:
                return json.load(response)
        except Exception as error:
            last_error = error
            # The public archive endpoint can briefly throttle requests.  Back
            # off rather than immediately repeating the same rejected request.
            if attempt < attempts - 1:
                sleep(min(30, 2**attempt))
    raise last_error


def districts_from_des_report(report_path=DES_REPORT):
    parser = _DesTableParser()
    parser.feed(Path(report_path).read_text(encoding="utf-8", errors="replace"))
    if len(parser.rows) < 3:
        raise ValueError(f"No DES data rows found in {report_path}")
    return sorted({(row[1], row[2]) for row in parser.rows[2:] if len(row) >= 3})


def _geocode_district(state, district):
    result = _request_json(
        GEOCODING_URL,
        {"name": f"{district}, {state}, India", "count": 10, "language": "en", "format": "json"},
    )
    candidates = result.get("results", [])
    india_candidates = [
        item for item in candidates if item.get("country_code") == "IN"
    ]
    if not india_candidates:
        # District-specific queries are not always indexed; retry with its name.
        result = _request_json(
            GEOCODING_URL,
            {"name": district, "count": 10, "language": "en", "format": "json"},
        )
        india_candidates = [
            item for item in result.get("results", []) if item.get("country_code") == "IN"
        ]
    if not india_candidates:
        raise ValueError(f"Open-Meteo could not geocode {district}, {state}, India")
    selected = india_candidates[0]
    return selected["latitude"], selected["longitude"], selected.get("name", district)


def _fetch_daily_weather(latitude, longitude):
    result = _request_json(
        ARCHIVE_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": START_DATE,
            "end_date": END_DATE,
            "daily": "precipitation_sum,temperature_2m_mean",
            "timezone": "Asia/Kolkata",
        },
    )
    daily = result.get("daily", {})
    required = {"time", "precipitation_sum", "temperature_2m_mean"}
    if not required.issubset(daily):
        raise ValueError(f"Open-Meteo returned incomplete daily data: {result}")
    return daily


def _normalise_name(value):
    return "".join(character for character in value.lower() if character.isalnum())


def _ring_centroid(ring):
    """Return an area-weighted centroid for a longitude/latitude polygon ring."""
    twice_area = centroid_x = centroid_y = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        cross = x1 * y2 - x2 * y1
        twice_area += cross
        centroid_x += (x1 + x2) * cross
        centroid_y += (y1 + y2) * cross
    if twice_area == 0:
        return ring[0][1], ring[0][0], 0.0
    return centroid_y / (3 * twice_area), centroid_x / (3 * twice_area), abs(twice_area)


def _geometry_centroid(geometry):
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    pieces = [_ring_centroid(polygon[0]) for polygon in polygons if polygon and polygon[0]]
    total_area = sum(piece[2] for piece in pieces)
    if not total_area:
        return pieces[0][0], pieces[0][1]
    return (
        sum(latitude * area for latitude, _, area in pieces) / total_area,
        sum(longitude * area for _, longitude, area in pieces) / total_area,
    )


def district_boundary_coordinates(report_path=DES_REPORT, boundary_path=BOUNDARY_PATH):
    """Match DES district names to unambiguous India ADM2 boundary centroids."""
    if not Path(boundary_path).exists():
        raise FileNotFoundError(f"Missing district boundary file: {boundary_path}")
    boundary_features = json.loads(Path(boundary_path).read_text())["features"]
    by_name = {}
    for feature in boundary_features:
        by_name.setdefault(_normalise_name(feature["properties"]["shapeName"]), []).append(feature)

    coordinates, failures = [], []
    for state, district in districts_from_des_report(report_path):
        matches = by_name.get(_normalise_name(district), [])
        if len(matches) != 1:
            reason = "No exact ADM2 boundary match" if not matches else "Ambiguous ADM2 boundary name"
            failures.append({"State": state, "District": district, "Error": reason})
            continue
        latitude, longitude = _geometry_centroid(matches[0]["geometry"])
        coordinates.append(
            {"State": state, "District": district, "Latitude": latitude, "Longitude": longitude,
             "ResolvedLocation": matches[0]["properties"]["shapeName"], "CoordinateSource": "geoBoundaries India ADM2 centroid"}
        )
    return coordinates, failures


def select_priority_districts(locations, crop_path=Path("data/raw/des_crop_production.csv"), limit=350):
    """Select a reproducible agricultural-priority subset of matched districts.

    Priority is total DES-reported production over the report period, with
    state and district used only as deterministic tie breakers.  This avoids a
    subjective definition of an "important" district.
    """
    crop = pd.read_csv(crop_path, usecols=["State", "District", "Production"])
    crop["Production"] = pd.to_numeric(crop["Production"], errors="coerce")
    totals = crop.groupby(["State", "District"], as_index=False)["Production"].sum()
    priority = pd.DataFrame(locations).merge(totals, on=["State", "District"], how="left")
    priority["Production"] = priority["Production"].fillna(0)
    priority = priority.sort_values(
        ["Production", "State", "District"], ascending=[False, True, True], kind="stable"
    ).head(limit).copy()
    priority["SelectionMethod"] = "Top total DES-reported production across available reporting years"
    priority["SelectionRank"] = range(1, len(priority) + 1)
    DISTRICT_SELECTION_PATH.parent.mkdir(parents=True, exist_ok=True)
    priority.to_csv(DISTRICT_SELECTION_PATH, index=False)
    return priority.drop(columns=["Production", "SelectionMethod", "SelectionRank"]).to_dict("records")


def _fetch_weather_batch(locations):
    result = _request_json(
        ARCHIVE_URL,
        {
            "latitude": ",".join(f"{location['Latitude']:.6f}" for location in locations),
            "longitude": ",".join(f"{location['Longitude']:.6f}" for location in locations),
            "start_date": START_DATE,
            "end_date": END_DATE,
            "daily": "precipitation_sum,temperature_2m_mean",
            "timezone": "Asia/Kolkata",
        },
    )
    return result if isinstance(result, list) else [result]


def _fetch_one_district(state, district):
    latitude, longitude, resolved_name = _geocode_district(state, district)
    daily = _fetch_daily_weather(latitude, longitude)
    daily_frame = pd.DataFrame(
        {
            "Date": pd.to_datetime(daily["time"]),
            "Rainfall": daily["precipitation_sum"],
            "Temperature": daily["temperature_2m_mean"],
        }
    )
    daily_frame["Year"] = daily_frame["Date"].dt.year
    annual = daily_frame.groupby("Year", as_index=False).agg(
        Rainfall=("Rainfall", "sum"), Temperature=("Temperature", "mean")
    )
    return [
        {
            "Year": row.Year,
            "State": state,
            "District": district,
            "Latitude": latitude,
            "Longitude": longitude,
            "ResolvedLocation": resolved_name,
            "Rainfall": round(row.Rainfall, 2),
            "Temperature": round(row.Temperature, 2),
            "WeatherAggregation": "Calendar year; proxy for DES reporting year starting this year",
            "WeatherDataSource": "Open-Meteo Historical Weather API",
        }
        for row in annual.itertuples(index=False)
    ]


def _write_progress(records, boundary_failures, weather_failures, output_path):
    """Persist successful batches so an interrupted download remains auditable."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).to_csv(output_path, index=False, quoting=csv.QUOTE_MINIMAL)
    pd.DataFrame(boundary_failures, columns=["State", "District", "Error"]).to_csv(
        FAILED_GEOCODES_PATH, index=False
    )
    pd.DataFrame(weather_failures, columns=["State", "District", "Error"]).to_csv(
        WEATHER_FAILURES_PATH, index=False
    )


def _completed_weather_records(output_path, locations):
    """Return already complete selected districts, for safe retry after throttling."""
    output_path = Path(output_path)
    if not output_path.exists():
        return [], locations
    existing = pd.read_csv(output_path)
    required = {"State", "District", "Year", "Rainfall", "Temperature"}
    if not required.issubset(existing.columns):
        return [], locations
    selected_keys = {(item["State"], item["District"]) for item in locations}
    existing = existing.loc[
        existing[["State", "District"]].apply(tuple, axis=1).isin(selected_keys)
    ].copy()
    expected_years = set(range(int(START_DATE[:4]), int(END_DATE[:4]) + 1))
    complete_keys = {
        key for key, group in existing.groupby(["State", "District"])
        if set(group["Year"].astype(int)) == expected_years and len(group) == len(expected_years)
    }
    records = existing.loc[
        existing[["State", "District"]].apply(tuple, axis=1).isin(complete_keys)
    ].to_dict("records")
    pending = [item for item in locations if (item["State"], item["District"]) not in complete_keys]
    return records, pending


def fetch_des_weather(report_path=DES_REPORT, output_path=OUTPUT_PATH, batch_size=10, district_limit=350):
    """Write weather for the highest-production DES districts with valid centroids."""
    locations, boundary_failures = district_boundary_coordinates(report_path)
    locations = select_priority_districts(locations, limit=district_limit)
    records, pending_locations = _completed_weather_records(output_path, locations)
    weather_failures = []
    for start in range(0, len(pending_locations), batch_size):
        batch = pending_locations[start : start + batch_size]
        try:
            responses = _fetch_weather_batch(batch)
            if len(responses) != len(batch):
                raise ValueError(f"Expected {len(batch)} locations, received {len(responses)}")
            for location, response in zip(batch, responses):
                daily = response.get("daily", {})
                if not {"time", "precipitation_sum", "temperature_2m_mean"}.issubset(daily):
                    raise ValueError("Open-Meteo returned incomplete daily data")
                daily_frame = pd.DataFrame({"Date": pd.to_datetime(daily["time"]), "Rainfall": daily["precipitation_sum"], "Temperature": daily["temperature_2m_mean"]})
                daily_frame["Year"] = daily_frame["Date"].dt.year
                for row in daily_frame.groupby("Year", as_index=False).agg(Rainfall=("Rainfall", "sum"), Temperature=("Temperature", "mean")).itertuples(index=False):
                    records.append({**location, "Year": row.Year, "Rainfall": round(row.Rainfall, 2), "Temperature": round(row.Temperature, 2), "WeatherAggregation": "Calendar year; proxy for DES reporting year starting this year", "WeatherDataSource": "Open-Meteo Historical Weather API"})
        except Exception as error:
            weather_failures.extend({"State": location["State"], "District": location["District"], "Error": str(error)} for location in batch)
        _write_progress(records, boundary_failures, weather_failures, output_path)
        print(
            f"Processed {min(start + len(batch), len(pending_locations))}/{len(pending_locations)} pending districts "
            f"({len(records) // 11}/{len(locations)} complete)",
            flush=True,
        )
        sleep(2)

    frame = pd.DataFrame(records)
    if frame.empty:
        raise RuntimeError("No weather data was downloaded")
    _write_progress(records, boundary_failures, weather_failures, output_path)
    return frame


if __name__ == "__main__":
    result = fetch_des_weather()
    print(f"Wrote {len(result):,} annual historical weather rows to {OUTPUT_PATH}")
