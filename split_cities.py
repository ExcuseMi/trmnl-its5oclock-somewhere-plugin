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
import zoneinfo

CSV_URL = "https://raw.githubusercontent.com/dr5hn/countries-states-cities-database/master/csv/cities.csv"
CSV_FILE = "cities.csv"
OUTPUT_DIR = "data/cities"

# ── Download CSV if absent ────────────────────────────────────────────────────
if not os.path.exists(CSV_FILE):
    print(f"Downloading {CSV_FILE} ...")
    urllib.request.urlretrieve(CSV_URL, CSV_FILE)
    print("Done.")
else:
    print(f"Using existing {CSV_FILE}")

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
        if tz and name and lat and lon:
            cities.append({"name": name, "lat": float(lat),
                           "lon": float(lon), "country": country, "tz": tz})
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
    buckets.setdefault(key, []).append(
        {"name": city["name"], "lat": city["lat"],
         "lon": city["lon"], "country": city["country"]}
    )

# ── Write files ───────────────────────────────────────────────────────────────
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Remove stale files from a previous run
for fname in os.listdir(OUTPUT_DIR):
    if fname.startswith("utc") and fname.endswith(".json"):
        os.remove(os.path.join(OUTPUT_DIR, fname))

for key, city_list in sorted(buckets.items()):
    with open(os.path.join(OUTPUT_DIR, f"{key}.json"), "w", encoding="utf-8") as f:
        json.dump(city_list, f, ensure_ascii=False)

print(f"  {len(buckets)} offset files written to {OUTPUT_DIR}/")
print(f"  {sum(len(v) for v in buckets.values())} total entries")
print("Done.")