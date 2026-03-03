"""
Generates DST-accurate city files for the current moment.

Reads cities.csv (downloaded if absent), computes each city's current UTC
offset via zoneinfo (respects DST), and writes:
  data/cities/utc+N.json
  data/cities/utc-N.json   (etc. for every offset that exists right now)

Output format per file:
  {
    "France": {"toast": "Santé", "cities": [{"name":..,"lat":..,"lon":..}, ...]},
    "United Kingdom": {
      "toast": "Cheers",
      "cities": [
        {"name": "London", ...},
        {"name": "Cardiff", ..., "toast": "Iechyd da", "pronunciation": "Yeh-hid dah"}
      ]
    }
  }

Country-level toast is stored once per country. Cities only carry a toast
override when they resolve at state or city level (e.g. Welsh/Scottish regions).
Files are capped at MAX_CITIES_PER_FILE entries, spread across countries.

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
TOASTS_FILE         = ROOT / "data" / "toasts.json"
NAME_OVERRIDES_FILE = ROOT / "data" / "name_overrides.json"

MAX_CITIES_PER_FILE = 1000  # Set to an int (e.g. 1000) to cap cities per file

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

# ── Load name overrides ───────────────────────────────────────────────────────
with open(NAME_OVERRIDES_FILE, encoding="utf-8") as _f:
    _name_overrides = json.load(_f)

# ── Load toasts lookup ────────────────────────────────────────────────────────
with open(TOASTS_FILE, encoding="utf-8") as _f:
    _toasts = json.load(_f)
_toast_countries = _toasts.get("countries", {})
_toast_states    = _toasts.get("states", {})
_toast_cities    = _toasts.get("cities", {})

def resolve_toast(name, state, country):
    val = (
        _toast_cities.get(f"{name}, {country}")
        or _toast_states.get(f"{state}, {country}")
        or _toast_countries.get(country)
        or ""
    )
    if isinstance(val, dict):
        return val.get("toast", ""), val.get("pronunciation", "")
    return val, ""

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
        name    = _name_overrides.get(name, name)
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

# buckets[utc_key][country] = {"t"?: str, "p"?: str, "c": [...]}
# Single-char keys: t=toast, p=pronunciation, c=cities, n=name, y=lat, x=lon, z=zoom
buckets: dict[str, dict] = {}

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
    country   = city["country"]

    if key not in buckets:
        buckets[key] = {}

    if country not in buckets[key]:
        # Store country-level toast once
        raw = _toast_countries.get(country, "")
        entry: dict = {"c": []}
        if isinstance(raw, dict):
            if raw.get("toast"):
                entry["t"] = raw["toast"]
            if raw.get("pronunciation"):
                entry["p"] = raw["pronunciation"]
        elif raw:
            entry["t"] = raw
        buckets[key][country] = entry

    # Build city entry — embed toast only for state/city-level overrides
    city_entry: dict = {"n": city["name"], "y": city["lat"], "x": city["lon"]}

    city_key  = f"{city['name']}, {country}"
    state_key = f"{city['state']}, {country}" if city["state"] else None
    if _toast_cities.get(city_key) or (state_key and _toast_states.get(state_key)):
        t, p = resolve_toast(city["name"], city["state"], country)
        city_entry["t"] = t
        if p:
            city_entry["p"] = p

    zoom = ISLAND_ZOOM.get(country)
    if zoom:
        city_entry["z"] = zoom

    buckets[key][country]["c"].append(city_entry)

# ── Cap cities per file, maximising country diversity ─────────────────────────
def cap_bucket(country_data: dict, max_cities) -> dict:
    if max_cities is None:
        return country_data
    total = sum(len(v["c"]) for v in country_data.values())
    if total <= max_cities:
        return country_data

    # Round-robin: take 1 city per country per round until cap is hit.
    # This maximises country diversity before any country gets a second city.
    result: dict = {
        name: {k: v for k, v in d.items() if k != "c"} | {"c": []}
        for name, d in country_data.items()
    }
    country_list = list(country_data.keys())
    indices      = {name: 0 for name in country_list}
    taken        = 0

    while taken < max_cities:
        added = False
        for name in country_list:
            if taken >= max_cities:
                break
            idx = indices[name]
            if idx < len(country_data[name]["c"]):
                result[name]["c"].append(country_data[name]["c"][idx])
                indices[name] += 1
                taken += 1
                added  = True
        if not added:
            break  # All countries exhausted

    return {name: d for name, d in result.items() if d["c"]}

# ── Write files ───────────────────────────────────────────────────────────────
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Remove stale files from a previous run
for fname in os.listdir(OUTPUT_DIR):
    if fname.startswith("utc") and fname.endswith(".json"):
        os.remove(OUTPUT_DIR / fname)

total_entries = 0
for key, country_data in sorted(buckets.items()):
    capped = cap_bucket(country_data, MAX_CITIES_PER_FILE)
    total_entries += sum(len(v["c"]) for v in capped.values())
    with open(OUTPUT_DIR / f"{key}.json", "w", encoding="utf-8") as f:
        json.dump(capped, f, ensure_ascii=False)

print(f"  {len(buckets)} offset files written to {OUTPUT_DIR}/")
cap_note = f"capped at {MAX_CITIES_PER_FILE} per file" if MAX_CITIES_PER_FILE else "unlimited"
print(f"  {total_entries} total entries ({cap_note})")
print("Done.")
