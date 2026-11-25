from datetime import datetime
import json
import math
from pathlib import Path
import re
import time
from urllib.parse import quote_plus
import requests


OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "SwasthyaSetu/1.0 (healthcare referral project)"
BASE_DIR = Path(__file__).resolve().parent.parent
LOCAL_DOCTORS_DIR = BASE_DIR / "data" / "doctors"

_CACHE = {}
_CACHE_TTL_SECONDS = 120
_OVERPASS_COOLDOWN_UNTIL = 0.0

_WEEKDAYS = {
    "mo": 0,
    "tu": 1,
    "we": 2,
    "th": 3,
    "fr": 4,
    "sa": 5,
    "su": 6,
}

_LAB_KEYWORDS = (
    "pathology",
    "pathlab",
    "path lab",
    "diagnostic",
    "diagnostica",
    "laboratory",
    "lab ",
    " labs",
    "blood test",
    "imaging",
    "radiology",
    "sonography",
    "ultrasound",
    "x-ray",
    "mri",
    "ct scan",
)

_NON_MEDICAL_KEYWORDS = (
    "veterinary",
    "vet ",
    "animal hospital",
    "pet hospital",
    "pet clinic",
    "forensic",
    "chemical laboratory",
    "research_institute",
    "pharmacy",
    "medical store",
    "chemist",
    "restaurant",
    "hotel",
    "shop",
    "store",
    "academy",
)


def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate great-circle distance in kilometers using the Haversine formula."""
    earth_radius = 6371

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)

    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(delta_lon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a),
    )

    return earth_radius * c


def _expand_day_spec(day_spec):
    """Expand OSM weekday tokens like 'Mo-Sa' or 'Mo,We,Fr' into weekday indices (0-6)."""
    days = set()
    for part in day_spec.lower().split(","):
        part = part.strip()
        if "-" in part:
            bounds = [b.strip()[:2] for b in part.split("-", 1)]
            if bounds[0] in _WEEKDAYS and bounds[1] in _WEEKDAYS:
                start = _WEEKDAYS[bounds[0]]
                end = _WEEKDAYS[bounds[1]]
                if start <= end:
                    days.update(range(start, end + 1))
                else:
                    days.update(range(start, 7))
                    days.update(range(0, end + 1))
        else:
            key = part[:2]
            if key in _WEEKDAYS:
                days.add(_WEEKDAYS[key])
    return days


def evaluate_opening_hours(opening_hours, now=None):
    """
    Evaluate an OpenStreetMap opening_hours string against local time.
    Returns (is_open_now: bool | None, availability_label: str).
    """
    if not opening_hours or not str(opening_hours).strip():
        return None, "Hours not listed — call to confirm"

    raw = str(opening_hours).strip()
    if raw.lower() in {"24/7", "24x7", "00:00-24:00"}:
        return True, "Available 24/7"

    if now is None:
        now = datetime.now()

    current_day = now.weekday()
    current_minutes = now.hour * 60 + now.minute

    matched_any_rule = False
    is_open = False

    for rule in raw.split(";"):
        rule = rule.strip()
        if not rule:
            continue

        if "off" in rule.lower() and not re.search(r"\d{1,2}:\d{2}", rule):
            continue

        time_ranges = re.findall(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})", rule)
        if not time_ranges:
            continue

        day_prefix = re.split(r"\d{1,2}:\d{2}", rule, maxsplit=1)[0].strip()
        allowed_days = _expand_day_spec(day_prefix) if day_prefix else set(range(7))
        if not allowed_days:
            # Handle phrases like "PH" or unrecognized day prefixes safely
            if re.search(r"[a-zA-Z]{2}", day_prefix):
                continue
            allowed_days = set(range(7))

        matched_any_rule = True
        if current_day not in allowed_days:
            continue

        for sh, sm, eh, em in time_ranges:
            start_min = int(sh) * 60 + int(sm)
            end_min = int(eh) * 60 + int(em)
            if end_min == 0 and start_min > 0:
                end_min = 24 * 60
            if start_min <= end_min:
                if start_min <= current_minutes <= end_min:
                    is_open = True
                    break
            else:
                if current_minutes >= start_min or current_minutes <= end_min:
                    is_open = True
                    break

    if not matched_any_rule:
        return None, f"Hours: {raw}"

    if is_open:
        return True, f"Available now ({raw})"
    return False, f"Closed now ({raw})"


def _classify_facility(tags, category="", item_type=""):
    """
    Classify an OSM element into one of: 'hospital', 'doctor', 'clinic', 'lab', or None.
    Excludes non-medical labs (chemical/forensic), pharmacies, veterinary clinics, and schools.
    """
    name = (tags.get("name") or "").strip()
    if not name:
        return None

    name_lower = name.lower()
    amenity = (tags.get("amenity") or (item_type if category == "amenity" else "") or "").strip().lower()
    healthcare = (tags.get("healthcare") or (item_type if category == "healthcare" else "") or "").strip().lower()
    office = (tags.get("office") or (item_type if category == "office" else "") or "").strip().lower()

    if amenity in {"research_institute", "university", "college", "school", "pharmacy", "veterinary"}:
        return None
    if office == "laboratory" or "forensic" in name_lower or "chemical lab" in name_lower:
        return None
    if any(word in name_lower for word in _NON_MEDICAL_KEYWORDS):
        return None

    # Medical / diagnostic / pathology labs
    if healthcare == "laboratory" or (
        any(kw in name_lower for kw in _LAB_KEYWORDS)
        and (amenity in {"hospital", "clinic", "doctors", "laboratory", ""} or healthcare != "")
    ):
        # If it is explicitly a hospital that also has a diagnostic wing, keep as hospital when 'hospital' is primary
        if (amenity == "hospital" or healthcare == "hospital") and "hospital" in name_lower:
            return "hospital"
        return "lab"

    if amenity in {"doctors", "doctor"} or healthcare == "doctor":
        return "doctor"

    if amenity == "clinic" or healthcare in {"clinic", "centre"}:
        return "clinic"

    if amenity == "hospital" or healthcare == "hospital":
        if "hospital" not in name_lower and any(
            word in name_lower for word in ("college", "school", "university")
        ):
            return None
        return "hospital"

    return None


def _is_hospital_facility(tags):
    """Compatibility helper: returns True strictly for hospital facilities."""
    return _classify_facility(tags) == "hospital"


def _format_specialty(raw_specialty):
    if not raw_specialty:
        return None
    parts = [p.strip().replace("_", " ").title() for p in str(raw_specialty).split(";") if p.strip()]
    return ", ".join(parts) if parts else None


def _build_facility_record(
    name,
    facility_type,
    facility_lat,
    facility_lon,
    user_lat,
    user_lon,
    address="",
    phone=None,
    website=None,
    emergency=None,
    opening_hours=None,
    specialty=None,
    source="OpenStreetMap",
    explicit_available=None,
):
    distance = calculate_distance(user_lat, user_lon, facility_lat, facility_lon)
    maps_query = quote_plus(f"{name}, {facility_lat},{facility_lon}")
    maps_url = f"https://www.google.com/maps/search/?api=1&query={maps_query}"

    if explicit_available is not None:
        is_open_now = bool(explicit_available)
        availability_label = (
            f"Available ({opening_hours})" if is_open_now and opening_hours
            else ("Available" if is_open_now else "Unavailable")
        )
    else:
        is_open_now, availability_label = evaluate_opening_hours(opening_hours)

    return {
        "name": name,
        "type": facility_type,
        "address": address,
        "phone": phone,
        "website": website,
        "emergency": emergency,
        "specialty": _format_specialty(specialty),
        "opening_hours": opening_hours,
        "is_open_now": is_open_now,
        "availability": availability_label,
        "source": source,
        "latitude": facility_lat,
        "longitude": facility_lon,
        "distance_km": round(distance, 2),
        "maps_url": maps_url,
    }


def _load_local_doctors(latitude, longitude, radius_km):
    """Load optional manual doctor records from data/doctors/*.json if present."""
    if not LOCAL_DOCTORS_DIR.exists():
        return []

    records = []
    for json_file in LOCAL_DOCTORS_DIR.glob("*.json"):
        try:
            payload = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        items = payload.get("doctors", payload) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            continue

        for doc in items:
            if not isinstance(doc, dict) or not doc.get("name"):
                continue
            lat = doc.get("latitude")
            lon = doc.get("longitude")
            if lat is None or lon is None:
                continue
            try:
                lat_f = float(lat)
                lon_f = float(lon)
            except (TypeError, ValueError):
                continue

            if calculate_distance(latitude, longitude, lat_f, lon_f) > radius_km * 1.25:
                continue

            records.append(
                _build_facility_record(
                    name=str(doc["name"]).strip(),
                    facility_type="doctor",
                    facility_lat=lat_f,
                    facility_lon=lon_f,
                    user_lat=latitude,
                    user_lon=longitude,
                    address=doc.get("address", ""),
                    phone=doc.get("phone"),
                    website=doc.get("website"),
                    opening_hours=doc.get("opening_hours"),
                    specialty=doc.get("specialty"),
                    source="Local Registry",
                    explicit_available=doc.get("available"),
                )
            )
    return records


def _query_overpass_facilities(latitude, longitude, radius, target_categories):
    global _OVERPASS_COOLDOWN_UNTIL
    if time.time() < _OVERPASS_COOLDOWN_UNTIL:
        return []

    clauses = []
    if "hospital" in target_categories:
        clauses.extend([
            f'nwr["amenity"="hospital"](around:{radius},{latitude},{longitude});',
            f'nwr["healthcare"="hospital"](around:{radius},{latitude},{longitude});',
        ])
    if "doctor" in target_categories:
        clauses.extend([
            f'nwr["amenity"="doctors"](around:{radius},{latitude},{longitude});',
            f'nwr["healthcare"="doctor"](around:{radius},{latitude},{longitude});',
        ])
    if "clinic" in target_categories:
        clauses.extend([
            f'nwr["amenity"="clinic"](around:{radius},{latitude},{longitude});',
            f'nwr["healthcare"="clinic"](around:{radius},{latitude},{longitude});',
        ])
    if "lab" in target_categories:
        clauses.extend([
            f'nwr["healthcare"="laboratory"](around:{radius},{latitude},{longitude});',
            f'nwr["amenity"="laboratory"](around:{radius},{latitude},{longitude});',
        ])

    if not clauses:
        return []

    query = f"""
    [out:json][timeout:5];
    (
        {' '.join(clauses)}
    );
    out center tags;
    """

    try:
        response = requests.post(
            OVERPASS_URL,
            data=query,
            headers={"User-Agent": USER_AGENT},
            timeout=6,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as error:
        print("Overpass API unavailable, using Nominatim fallback:", error)
        _OVERPASS_COOLDOWN_UNTIL = time.time() + 60
        return []

    facilities = []
    seen = set()

    for element in data.get("elements", []):
        tags = element.get("tags", {})
        facility_type = _classify_facility(tags)
        if facility_type not in target_categories:
            continue

        name = tags.get("name", "").strip()

        if "lat" in element and "lon" in element:
            facility_lat = element["lat"]
            facility_lon = element["lon"]
        elif "center" in element:
            facility_lat = element["center"].get("lat")
            facility_lon = element["center"].get("lon")
        else:
            continue

        if facility_lat is None or facility_lon is None:
            continue

        unique_key = (facility_type, name.lower(), round(facility_lat, 4), round(facility_lon, 4))
        if unique_key in seen:
            continue
        seen.add(unique_key)

        address_parts = [
            tags.get("addr:housenumber"),
            tags.get("addr:street"),
            tags.get("addr:suburb"),
            tags.get("addr:district"),
            tags.get("addr:city"),
            tags.get("addr:state"),
            tags.get("addr:postcode"),
        ]
        address = ", ".join(part for part in address_parts if part)

        facilities.append(
            _build_facility_record(
                name=name,
                facility_type=facility_type,
                facility_lat=facility_lat,
                facility_lon=facility_lon,
                user_lat=latitude,
                user_lon=longitude,
                address=address,
                phone=tags.get("phone") or tags.get("contact:phone") or tags.get("mobile") or tags.get("contact:mobile"),
                website=tags.get("website") or tags.get("contact:website"),
                emergency=tags.get("emergency"),
                opening_hours=tags.get("opening_hours"),
                specialty=tags.get("healthcare:speciality"),
            )
        )

    return facilities


def _nominatim_fetch(params, viewbox):
    try:
        response = requests.get(
            NOMINATIM_SEARCH_URL,
            params={
                "format": "jsonv2",
                "bounded": 1,
                "viewbox": viewbox,
                "extratags": 1,
                "addressdetails": 1,
                "limit": 25,
                **params,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=8,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as error:
        print("Nominatim search unavailable:", error)
        return []


def _query_nominatim_facilities(latitude, longitude, radius, target_categories):
    dlat = radius / 111000.0
    dlon = radius / (111000.0 * max(0.2, math.cos(math.radians(latitude))))
    viewbox = f"{longitude - dlon},{latitude + dlat},{longitude + dlon},{latitude - dlat}"

    queries = []
    if "hospital" in target_categories:
        queries.append({"amenity": "hospital"})
    if "doctor" in target_categories:
        queries.append({"amenity": "doctors"})
    if "clinic" in target_categories:
        queries.append({"amenity": "clinic"})
    if "lab" in target_categories:
        queries.append({"q": "diagnostic"})
        queries.append({"q": "pathology"})

    raw_items = []
    for query_params in queries:
        raw_items.extend(_nominatim_fetch(query_params, viewbox))

    facilities = []
    seen = set()
    max_km = radius / 1000.0

    for item in raw_items:
        category = (item.get("category") or "").strip().lower()
        item_type = (item.get("type") or "").strip().lower()
        extratags = item.get("extratags") or {}
        name = (item.get("name") or "").strip()

        synthetic_tags = {
            "name": name,
            "amenity": item_type if category == "amenity" else (extratags.get("amenity") or ""),
            "healthcare": item_type if category == "healthcare" else (extratags.get("healthcare") or ""),
            "office": item_type if category == "office" else (extratags.get("office") or ""),
        }
        facility_type = _classify_facility(synthetic_tags, category=category, item_type=item_type)
        if facility_type not in target_categories:
            continue

        try:
            facility_lat = float(item["lat"])
            facility_lon = float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue

        distance = calculate_distance(latitude, longitude, facility_lat, facility_lon)
        if distance > max_km * 1.15:
            continue

        unique_key = (facility_type, name.lower(), round(facility_lat, 4), round(facility_lon, 4))
        if unique_key in seen:
            continue
        seen.add(unique_key)

        addr = item.get("address") or {}
        address_parts = [
            addr.get("road"),
            addr.get("suburb") or addr.get("neighbourhood"),
            addr.get("city") or addr.get("town") or addr.get("state_district"),
            addr.get("state"),
            addr.get("postcode"),
        ]
        address = ", ".join(part for part in address_parts if part)

        facilities.append(
            _build_facility_record(
                name=name,
                facility_type=facility_type,
                facility_lat=facility_lat,
                facility_lon=facility_lon,
                user_lat=latitude,
                user_lon=longitude,
                address=address,
                phone=(
                    extratags.get("phone")
                    or extratags.get("contact:phone")
                    or extratags.get("mobile")
                    or extratags.get("contact:mobile")
                ),
                website=extratags.get("website") or extratags.get("contact:website"),
                emergency=extratags.get("emergency"),
                opening_hours=extratags.get("opening_hours"),
                specialty=extratags.get("healthcare:speciality"),
            )
        )

    return facilities


def find_nearby_healthcare(latitude, longitude, radius=5000, category="hospital"):
    """
    Find nearby healthcare facilities via OpenStreetMap (Overpass + Nominatim fallback)
    and optional local doctor registry.

    category: 'all', 'hospital', 'doctor', 'clinic', or 'lab'
    """
    radius = max(500, min(int(radius), 25000))
    normalized = (category or "all").strip().lower()

    if normalized == "all":
        target_categories = {"hospital", "doctor", "clinic", "lab"}
    elif normalized in {"hospital", "hospitals"}:
        target_categories = {"hospital"}
    elif normalized in {"doctor", "doctors"}:
        target_categories = {"doctor"}
    elif normalized in {"clinic", "clinics"}:
        target_categories = {"clinic"}
    elif normalized in {"lab", "labs", "laboratory"}:
        target_categories = {"lab"}
    else:
        target_categories = {"hospital", "doctor", "clinic", "lab"}

    cache_key = (round(latitude, 3), round(longitude, 3), radius, tuple(sorted(target_categories)))
    cached = _CACHE.get(cache_key)
    if cached and (time.time() - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    facilities = _query_overpass_facilities(latitude, longitude, radius, target_categories)
    if not facilities:
        facilities = _query_nominatim_facilities(latitude, longitude, radius, target_categories)

    if "doctor" in target_categories:
        local_docs = _load_local_doctors(latitude, longitude, radius / 1000.0)
        existing_keys = {
            (f["type"], f["name"].lower(), round(f["latitude"], 4), round(f["longitude"], 4))
            for f in facilities
        }
        for doc in local_docs:
            key = (doc["type"], doc["name"].lower(), round(doc["latitude"], 4), round(doc["longitude"], 4))
            if key not in existing_keys:
                facilities.append(doc)
                existing_keys.add(key)

    facilities.sort(key=lambda facility: facility["distance_km"])

    if normalized == "all":
        # Balanced cap per category so hospitals don't crowd out doctors, clinics, and labs
        selected = []
        for cat in ("hospital", "doctor", "clinic", "lab"):
            cat_items = [item for item in facilities if item["type"] == cat]
            selected.extend(cat_items[:15])
        selected.sort(key=lambda item: item["distance_km"])
        result = selected
    else:
        result = facilities[:20]

    _CACHE[cache_key] = (time.time(), result)
    return result
