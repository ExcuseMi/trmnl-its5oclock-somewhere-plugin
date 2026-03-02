import csv
import json
import os
import urllib.request
from datetime import datetime
import zoneinfo

URL = "https://raw.githubusercontent.com/dr5hn/countries-states-cities-database/master/csv/cities.csv"
OUTPUT_DIR = "../data/cities"

print("Downloading cities.csv...")
urllib.request.urlretrieve(URL, "cities.csv")
print("Done.")

os.makedirs(OUTPUT_DIR, exist_ok=True)

buckets = {}

with open("../cities.csv", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        tz = row.get("timezone", "").strip().strip('"')
        name = row.get("name", "").strip().strip('"')
        lat = row.get("latitude", "").strip().strip('"')
        lon = row.get("longitude", "").strip().strip('"')

        if not tz or not name or not lat or not lon:
            continue

        try:
            zone = zoneinfo.ZoneInfo(tz)
            now = datetime.now(zone)
            offset_seconds = now.utcoffset().total_seconds()
            offset_hours = round(offset_seconds / 1800) * 0.5
        except Exception:
            continue

        sign = "+" if offset_hours >= 0 else ""
        hours_str = f"{offset_hours:.1f}".rstrip("0").rstrip(".")
        key = f"utc{sign}{hours_str}"

        buckets.setdefault(key, []).append({
            "name": name,
            "lat": float(lat),
            "lon": float(lon)
        })

for key, cities in sorted(buckets.items()):
    path = os.path.join(OUTPUT_DIR, f"{key}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cities, f, ensure_ascii=False)
    print(f"  {path}: {len(cities)} cities")

print(f"\nDone! {len(buckets)} offset files written to ./{OUTPUT_DIR}/")