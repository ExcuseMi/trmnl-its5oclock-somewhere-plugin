"""
Generates DST-accurate city files for the current moment.

Reads cities.csv (downloaded if absent), computes each city's current UTC
offset via zoneinfo (respects DST), and writes:
  data/cities/utc+N.json
  data/cities/utc-N.json   (etc. for every offset that exists right now)

Run manually or via the GitHub Action (.github/workflows/update-cities.yml)
which fires every 6 hours so DST transitions are always reflected within 6h.
"""

import csv
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
import zoneinfo

# ── Paths (always relative to the project root, regardless of cwd) ────────────
ROOT       = Path(__file__).parent.parent
CSV_URL    = "https://raw.githubusercontent.com/dr5hn/countries-states-cities-database/master/csv/cities.csv"
CSV_FILE   = ROOT / "cities.csv"
OUTPUT_DIR = ROOT / "data" / "cities"
TOASTS_FILE = ROOT / "data" / "toasts.json"

# Countries where zoom 7 shows only ocean — keyed by country_name from CSV
ISLAND_ZOOM = {
    # Tiny atolls / < 5 km
    "Maldives": 11, "Tuvalu": 11, "Nauru": 11, "Tokelau": 11,
    "Saint Kitts and Nevis": 11, "Wallis and Futuna": 11,
    # Very small islands / 5–30 km
    "Marshall Islands": 10, "Kiribati": 10, "Micronesia": 10,
    "Palau": 10, "Niue": 10, "Cook Islands": 10, "Tonga": 10,
    "Barbados": 10, "Grenada": 10, "Saint Lucia": 10,
    "Saint Vincent and the Grenadines": 10, "Antigua and Barbuda": 10,
    "Dominica": 10, "Comoros": 10, "Seychelles": 10,
    "São Tomé and Príncipe": 10, "Malta": 10, "Bahrain": 10,
    "Singapore": 10,
    # Small islands / 30–150 km
    "Samoa": 9, "Vanuatu": 9, "Solomon Islands": 9, "Fiji": 9,
    "Trinidad and Tobago": 9, "Mauritius": 9, "Cabo Verde": 9,
    "Timor-Leste": 9,
}

# ── Load toasts lookup ────────────────────────────────────────────────────────
with open(TOASTS_FILE, encoding="utf-8") as _f:
    _toasts = json.load(_f)
_toast_countries = _toasts.get("countries", {})
_toast_states    = _toasts.get("states", {})
_toast_cities    = _toasts.get("cities", {})

def resolve_toast(name, state, country):
    return (
        _toast_cities.get(f"{name}, {country}")
        or _toast_states.get(f"{state}, {country}")
        or _toast_countries.get(country)
        or ""
    )

# ── Download CSV if absent ────────────────────────────────────────────────────
if not CSV_FILE.exists():
    print(f"Downloading {CSV_FILE.name} ...")
    urllib.request.urlretrieve(CSV_URL, CSV_FILE)
    print("Done.")
else:
    print(f"Using existing {CSV_FILE.name}")

# ── Parse ─────────────────────────────────────────────────────────────────────
print("Parsing cities...")
cities = []
with open(CSV_FILE, encoding="utf-8") as f:
    for row in csv.DictReader(f):
        tz      = row.get("timezone", "").strip().strip('"')
        name    = row.get("name", "").strip().strip('"')
        lat     = row.get("latitude", "").strip().strip('"')
        lon     = row.get("longitude", "").strip().strip('"')
        country = row.get("country_name", "").strip().strip('"')
        state   = row.get("state_name", "").strip().strip('"')
        if tz and name and lat and lon:
            cities.append({"name": name, "lat": float(lat),
                           "lon": float(lon), "country": country,
                           "state": state, "tz": tz})
print(f"  {len(cities)} cities")

# ── Bucket by current DST-accurate offset ────────────────────────────────────
now = datetime.now(tz=timezone.utc)
print(f"Computing offsets for {now.strftime('%Y-%m-%d %H:%M UTC')} ...")

buckets: dict[str, list] = {}
for city in cities:
    try:
        zone           = zoneinfo.ZoneInfo(city["tz"])
        offset_seconds = now.astimezone(zone).utcoffset().total_seconds()
        offset_hours   = round(offset_seconds / 1800) * 0.5
    except Exception:
        continue

    sign      = "+" if offset_hours >= 0 else ""
    hours_str = f"{offset_hours:.1f}".rstrip("0").rstrip(".")
    key       = f"utc{sign}{hours_str}"
    toast = resolve_toast(city["name"], city["state"], city["country"])
    entry = {"name": city["name"], "lat": city["lat"],
             "lon": city["lon"], "country": city["country"]}
    if toast:
        entry["toast"] = toast
    zoom = ISLAND_ZOOM.get(city["country"])
    if zoom:
        entry["zoom"] = zoom
    buckets.setdefault(key, []).append(entry)

# ── Write files ───────────────────────────────────────────────────────────────
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Remove stale files from a previous run
for fname in os.listdir(OUTPUT_DIR):
    if fname.startswith("utc") and fname.endswith(".json"):
        os.remove(OUTPUT_DIR / fname)

for key, city_list in sorted(buckets.items()):
    with open(OUTPUT_DIR / f"{key}.json", "w", encoding="utf-8") as f:
        json.dump(city_list, f, ensure_ascii=False)

print(f"  {len(buckets)} offset files written to {OUTPUT_DIR}/")
print(f"  {sum(len(v) for v in buckets.values())} total entries")
print("Done.")
