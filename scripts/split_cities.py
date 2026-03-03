"""
Generates DST-accurate city files for the current moment.

Reads cities15000.txt from GeoNames (downloaded + extracted if absent), computes
each city's current UTC offset via zoneinfo (respects DST), and writes:
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

import json
import os
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
import zoneinfo

# ── Paths (always relative to the project root, regardless of cwd) ────────────
ROOT       = Path(__file__).parent.parent
OUTPUT_DIR = ROOT / "data" / "cities"
TOASTS_FILE             = ROOT / "data" / "toasts.json"
NAME_OVERRIDES_FILE     = ROOT / "data" / "name_overrides.json"
TIMEZONE_OVERRIDES_FILE = ROOT / "data" / "timezone_overrides.json"

# GeoNames source files (downloaded if absent, not committed to repo)
GEONAMES_ZIP_URL     = "https://download.geonames.org/export/dump/cities15000.zip"
GEONAMES_ZIP_FILE    = ROOT / "cities15000.zip"
GEONAMES_TXT_FILE    = ROOT / "cities15000.txt"
COUNTRY_INFO_URL     = "https://download.geonames.org/export/dump/countryInfo.txt"
COUNTRY_INFO_FILE    = ROOT / "countryInfo.txt"
ADMIN1_URL           = "https://download.geonames.org/export/dump/admin1CodesASCII.txt"
ADMIN1_FILE          = ROOT / "admin1CodesASCII.txt"

MAX_CITIES_PER_FILE = 500  # Set to None to disable cap

# Countries where zoom 7 shows only ocean — keyed by country_name from GeoNames
ISLAND_ZOOM = {
    # Tiny atolls / < 5 km
    "Maldives": 11, "Tuvalu": 11, "Nauru": 11, "Tokelau": 11,
    "Saint Kitts and Nevis": 11, "Wallis and Futuna Islands": 11,
    # Very small islands / 5–30 km
    "Marshall Islands": 10, "Kiribati": 10, "Federated States of Micronesia": 10,
    "Palau": 10, "Niue": 10, "Cook Islands": 10, "Tonga": 10,
    "Barbados": 10, "Grenada": 10, "Saint Lucia": 10,
    "Saint Vincent and the Grenadines": 10, "Antigua and Barbuda": 10,
    "Dominica": 10, "Comoros": 10, "Seychelles": 10,
    "Sao Tome and Principe": 10, "Malta": 10, "Bahrain": 10,
    "Singapore": 10,
    # Small islands / 30–150 km
    "Samoa": 9, "Vanuatu": 9, "Solomon Islands": 9, "Fiji": 9,
    "Trinidad and Tobago": 9, "Mauritius": 9, "Cape Verde": 9,
    "East Timor": 9,
}

# ── Load name overrides ───────────────────────────────────────────────────────
with open(NAME_OVERRIDES_FILE, encoding="utf-8") as _f:
    _name_overrides = json.load(_f)

# ── Load timezone overrides ───────────────────────────────────────────────────
# Keyed by "City, Country" to fix cities with wrong timezone data in GeoNames.
with open(TIMEZONE_OVERRIDES_FILE, encoding="utf-8") as _f:
    _timezone_overrides = json.load(_f)

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

def normalise_toast_for_json(raw):
    """Convert a toasts.json value to (t_val, p_val) for JSON output.

    raw can be a str, dict {toast, pronunciation}, or list of those.
    t_val: str | list  — stored as "t" key
    p_val: str         — stored as "p" key (only for single-value toasts)
    Arrays of one item are collapsed to a single value.
    """
    if isinstance(raw, list):
        opts = []
        for item in raw:
            if isinstance(item, dict):
                t = item.get("toast", "")
                p = item.get("pronunciation", "")
                if t:
                    opts.append({"t": t, "p": p} if p else t)
            elif isinstance(item, str) and item:
                opts.append(item)
        if not opts:
            return "", ""
        if len(opts) == 1:
            s = opts[0]
            if isinstance(s, dict):
                return s.get("t", ""), s.get("p", "")
            return s, ""
        return opts, ""
    elif isinstance(raw, dict):
        return raw.get("toast", ""), raw.get("pronunciation", "")
    return raw or "", ""

# ── Download GeoNames files if absent ─────────────────────────────────────────
def _download(url: str, path: Path, label: str) -> None:
    if not path.exists():
        print(f"Downloading {label} ...")
        urllib.request.urlretrieve(url, path)
        print("Done.")
    else:
        print(f"Using existing {path.name}")

_download(COUNTRY_INFO_URL, COUNTRY_INFO_FILE, "countryInfo.txt")
_download(ADMIN1_URL,        ADMIN1_FILE,        "admin1CodesASCII.txt")

if not GEONAMES_TXT_FILE.exists():
    _download(GEONAMES_ZIP_URL, GEONAMES_ZIP_FILE, "cities15000.zip")
    print("Extracting cities15000.txt ...")
    with zipfile.ZipFile(GEONAMES_ZIP_FILE) as zf:
        zf.extract("cities15000.txt", ROOT)
    print("Done.")
else:
    print(f"Using existing {GEONAMES_TXT_FILE.name}")

# ── Build country code → country name lookup ──────────────────────────────────
# countryInfo.txt is tab-separated; lines starting with # are comments.
# Fields: ISO, ISO3, ISO-Numeric, FIPS, Country, Capital, ...
_country_names: dict[str, str] = {}
with open(COUNTRY_INFO_FILE, encoding="utf-8") as _f:
    for _line in _f:
        if _line.startswith("#"):
            continue
        _parts = _line.strip().split("\t")
        if len(_parts) > 4:
            _country_names[_parts[0]] = _parts[4].strip()  # ISO2 -> English name

# ── Build admin1 code → state name lookup ────────────────────────────────────
# admin1CodesASCII.txt fields: "{CC}.{admin1}\tname\tasciiname\tgeonameid"
_admin1_names: dict[str, str] = {}
with open(ADMIN1_FILE, encoding="utf-8") as _f:
    for _line in _f:
        _parts = _line.strip().split("\t")
        if len(_parts) >= 2:
            _admin1_names[_parts[0]] = _parts[1]  # "US.CA" -> "California"

# ── Parse cities15000.txt ─────────────────────────────────────────────────────
# Tab-separated fields (0-based):
#  0=geonameid  1=name  2=asciiname  3=alternatenames  4=lat  5=lon
#  6=feature_class  7=feature_code  8=country_code  9=cc2
#  10=admin1_code  11=admin2_code  12=admin3_code  13=admin4_code
#  14=population  15=elevation  16=dem  17=timezone  18=modification_date
#
# feature_code PPLX = section of populated place (neighbourhood/district).
# These are often unrecognisable to a global audience, so we exclude them.
EXCLUDE_FEATURE_CODES = {"PPLX"}

# Priority tier for feature codes — lower = shown first within a country.
# Capitals and admin seats are preferred over generic populated places.
FEATURE_PRIORITY = {
    "PPLC":  0,  # national capital
    "PPLA":  1,  # state / province capital
    "PPLA2": 2,  # county / district capital
    "PPLA3": 3,
    "PPLA4": 4,
}
# Anything not listed gets tier 5 (generic populated place)

print("Parsing cities...")
cities = []
with open(GEONAMES_TXT_FILE, encoding="utf-8") as f:
    for line in f:
        parts = line.strip().split("\t")
        if len(parts) < 18:
            continue
        feature_code = parts[7].strip()
        if feature_code in EXCLUDE_FEATURE_CODES:
            continue
        name    = parts[1].strip()
        name    = _name_overrides.get(name, name)
        lat     = parts[4].strip()
        lon     = parts[5].strip()
        cc      = parts[8].strip()
        admin1  = parts[10].strip()
        pop_str = parts[14].strip()
        tz      = parts[17].strip()
        country = _country_names.get(cc, cc)
        state   = _admin1_names.get(f"{cc}.{admin1}", "")
        tz      = _timezone_overrides.get(f"{name}, {country}", tz)
        if name and lat and lon and tz:
            cities.append({"name": name, "lat": float(lat), "lon": float(lon),
                           "country": country, "state": state, "tz": tz,
                           "pop": int(pop_str) if pop_str.isdigit() else 0,
                           "tier": FEATURE_PRIORITY.get(feature_code, 5)})
print(f"  {len(cities)} cities")

# Sort: capitals and admin seats first (tier), then by population descending.
# cap_bucket's round-robin will therefore always prefer well-known cities.
cities.sort(key=lambda c: (c["tier"], -c["pop"]))

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
        t_val, p_val = normalise_toast_for_json(raw)
        if isinstance(t_val, list):
            entry["t"] = t_val
        elif t_val:
            entry["t"] = t_val
            if p_val:
                entry["p"] = p_val
        buckets[key][country] = entry

    # Build city entry — embed toast only for state/city-level overrides
    city_entry: dict = {"n": city["name"], "y": city["lat"], "x": city["lon"]}

    city_key  = f"{city['name']}, {country}"
    state_key = f"{city['state']}, {country}" if city["state"] else None
    override  = _toast_cities.get(city_key) or (state_key and _toast_states.get(state_key))
    if override:
        t_val, p_val = normalise_toast_for_json(override)
        if isinstance(t_val, list):
            city_entry["t"] = t_val
        elif t_val:
            city_entry["t"] = t_val
            if p_val:
                city_entry["p"] = p_val

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
        json.dump({"countries": capped}, f, ensure_ascii=False)

print(f"  {len(buckets)} offset files written to {OUTPUT_DIR}/")
cap_note = f"capped at {MAX_CITIES_PER_FILE} per file" if MAX_CITIES_PER_FILE else "unlimited"
print(f"  {total_entries} total entries ({cap_note})")
print("Done.")
# ── Print countries without toasts ────────────────────────────────────────────
countries_with_toasts = set(_toast_countries.keys())
countries_in_cities = set()
for country_data in buckets.values():
    countries_in_cities.update(country_data.keys())

missing = countries_in_cities - countries_with_toasts
if missing:
    print("\nCountries without toasts:")
    for country in sorted(missing):
        print(f"  '{country}'")
else:
    print("\nAll countries have toasts.")