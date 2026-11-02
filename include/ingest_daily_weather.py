"""Extract daily weather for each city and load one row per day."""

import argparse
import csv
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY_VARIABLES = "temperature_2m_max,temperature_2m_min,precipitation_sum"
LOCATION_COLUMNS = ("location_name", "region", "rain_limit_mm")
OUTPUT_COLUMNS = (
    "location_name",
    "region",
    "rain_limit_mm",
    "latitude",
    "longitude",
    "timezone",
    "date",
    "temperature_max_c",
    "temperature_min_c",
    "precipitation_mm",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract daily weather and load a CSV.")
    parser.add_argument("--locations", type=Path, default=Path("input/locations.csv"))
    parser.add_argument("--output", type=Path, default=Path("output/daily_weather.csv"))
    parser.add_argument("--start-date", help="Inclusive start, YYYY-MM-DD. Airflow data_interval_start.")
    parser.add_argument("--end-date", help="Exclusive end, YYYY-MM-DD. Airflow data_interval_end.")
    return parser.parse_args()


def parse_interval(start: str | None, end: str | None) -> tuple[str, str] | None:
    if start is None and end is None:
        return None
    if not start or not end:
        raise ValueError("Pass both --start-date and --end-date, or neither")
    try:
        start_day = date.fromisoformat(start)
        end_day = date.fromisoformat(end)
    except ValueError as error:
        raise ValueError("--start-date and --end-date must be YYYY-MM-DD") from error
    if end_day <= start_day:
        raise ValueError("--end-date must be after --start-date")
    return start_day.isoformat(), end_day.isoformat()


def request_json(url: str, label: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "compass-rose-ingest"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{label}: Open-Meteo returned HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"{label}: Open-Meteo request failed: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{label}: Open-Meteo returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label}: Open-Meteo returned an unexpected payload")
    return payload


def read_locations(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or any(name not in reader.fieldnames for name in LOCATION_COLUMNS):
            raise ValueError(f"{path} must have columns: {', '.join(LOCATION_COLUMNS)}")
        rows = []
        for line_number, row in enumerate(reader, start=2):
            values = {name: (row.get(name) or "").strip() for name in LOCATION_COLUMNS}
            if not any(values.values()):
                continue
            if not all(values.values()):
                raise ValueError(f"{path}:{line_number} has an empty required column")
            try:
                if float(values["rain_limit_mm"]) < 0:
                    raise ValueError
            except ValueError as error:
                raise ValueError(f"{path}:{line_number} has an invalid rain_limit_mm") from error
            rows.append(values)
    if not rows:
        raise ValueError(f"{path} has no locations")
    return rows


def fetch_weather(name: str, latitude: float, longitude: float, interval: tuple[str, str] | None) -> dict:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": "auto",
        "daily": DAILY_VARIABLES,
    }
    if interval is None:
        params["past_days"] = 30
        params["forecast_days"] = 7
    else:
        inclusive_end = date.fromisoformat(interval[1]) - timedelta(days=1)
        params["start_date"] = interval[0]
        params["end_date"] = inclusive_end.isoformat()
    query = urllib.parse.urlencode(params)
    try:
        return request_json(f"{FORECAST_URL}?{query}", name)
    except RuntimeError as error:
        if interval is None or "out of allowed range" not in str(error):
            raise
    try:
        return request_json(f"{ARCHIVE_URL}?{query}", name)
    except RuntimeError as error:
        raise RuntimeError(
            f"{name}: interval {interval[0]}/{interval[1]} is outside the forecast window and the archive"
        ) from error


def extract_daily(location: dict[str, str], interval: tuple[str, str] | None) -> list[dict]:
    name = location["location_name"]
    geocoding = request_json(
        f"{GEOCODING_URL}?{urllib.parse.urlencode({'name': name, 'count': 1, 'language': 'pt', 'format': 'json'})}",
        name,
    )
    place = (geocoding.get("results") or [None])[0]
    if not place or place.get("latitude") is None or place.get("longitude") is None:
        raise RuntimeError(f"{name}: Open-Meteo found no coordinates")

    forecast = fetch_weather(name, place["latitude"], place["longitude"], interval)
    daily = forecast.get("daily")
    if not isinstance(daily, dict):
        raise RuntimeError(f"{name}: forecast has no daily series")
    try:
        series = [daily[field] for field in ("time", *DAILY_VARIABLES.split(","))]
    except KeyError as error:
        raise RuntimeError(f"{name}: forecast is missing {error.args[0]}") from error
    if not series[0] or any(not isinstance(values, list) or len(values) != len(series[0]) for values in series):
        raise RuntimeError(f"{name}: daily series are empty or misaligned")
    if any(forecast.get(field) is None for field in ("latitude", "longitude", "timezone")):
        raise RuntimeError(f"{name}: forecast is missing coordinates or timezone")

    rows = []
    for day, maximum, minimum, precipitation in zip(*series):
        if interval is not None and not interval[0] <= day < interval[1]:
            continue
        if None in (maximum, minimum, precipitation):
            raise RuntimeError(f"{name}: null weather value on {day}")
        rows.append(
            {
                "location_name": name,
                "region": location["region"],
                "rain_limit_mm": location["rain_limit_mm"],
                "latitude": forecast["latitude"],
                "longitude": forecast["longitude"],
                "timezone": forecast["timezone"],
                "date": day,
                "temperature_max_c": maximum,
                "temperature_min_c": minimum,
                "precipitation_mm": precipitation,
            }
        )
    if not rows:
        raise RuntimeError(f"{name}: no daily rows in the requested interval")
    return rows


def rows_outside(path: Path, interval: tuple[str, str]) -> list[dict]:
    if not path.exists():
        return []
    start, end = interval
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if list(reader.fieldnames or []) != list(OUTPUT_COLUMNS):
            raise ValueError(f"{path} does not match the daily weather columns")
        return [row for row in reader if not start <= row["date"] < end]


def load_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    try:
        with temporary.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main() -> None:
    args = parse_args()
    interval = parse_interval(args.start_date, args.end_date)
    locations = read_locations(args.locations)
    rows = [row for location in locations for row in extract_daily(location, interval)]
    if interval is not None:
        rows = rows_outside(args.output, interval) + rows
        rows.sort(key=lambda row: (row["date"], row["location_name"]))
    load_csv(args.output, rows)


if __name__ == "__main__":
    main()
