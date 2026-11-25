from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import sys
import requests

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from database.connection import ensure_tables, get_connection

WHO_FACTSHEETS_URL = "https://www.who.int/api/hubs/factsheets"
CONDITIONS_JSON_PATH = BASE_DIR / "data" / "medical" / "conditions.json"
USER_AGENT = "SwasthyaSetu/1.0 (healthcare referral project)"

# Common everyday WHO conditions we want to sync and keep user-friendly
_ALLOWED_COMMON_WHO_KEYWORDS = {
    "dengue": ("Dengue", "General Physician"),
    "malaria": ("Malaria", "General Physician"),
    "typhoid": ("Typhoid Fever", "General Physician"),
    "influenza (seasonal)": ("Seasonal Flu (Viral Fever)", "General Physician"),
    "asthma": ("Asthma / Breathing Allergy", "Pulmonologist"),
    "migraine": ("Migraine / Severe Headache", "General Physician"),
    "diarrhoeal": ("Stomach Infection / Diarrhoea", "Gastroenterologist"),
    "ringworm": ("Fungal Skin Infection (Ringworm)", "Dermatologist"),
    "anaemia": ("Anaemia (Low Haemoglobin)", "General Physician"),
    "hepatitis a": ("Jaundice / Hepatitis A", "Gastroenterologist"),
    "hepatitis b": ("Hepatitis B / Liver Infection", "Gastroenterologist"),
    "tuberculosis": ("Tuberculosis (TB) — Persistent Cough", "Pulmonologist"),
    "hypertension": ("High Blood Pressure (Hypertension)", "Cardiologist"),
    "coronavirus disease (covid-19)": ("COVID-19 / Viral Respiratory Illness", "General Physician"),
    "chikungunya": ("Chikungunya (Fever & Joint Pain)", "General Physician"),
    "rheumatoid arthritis": ("Joint Pain / Arthritis", "Orthopaedic Specialist"),
    "low back pain": ("Lower Back / Muscle Pain", "Orthopaedic Specialist"),
    "kidney disease": ("Kidney / Urinary Health Issue", "Nephrologist"),
}

# Everyday primary-care conditions aligned with WHO & standard general practice
# (covers common symptoms that lack standalone WHO fact sheets, e.g. Common Cold, Food Poisoning, Acidity, Skin Allergy)
COMMON_PRIMARY_CARE_CONDITIONS = [
    {
        "name": "Common Cold & Cough",
        "source": "WHO Primary Care",
        "who_url": "https://www.who.int/news-room/fact-sheets/detail/influenza-(seasonal)",
        "specialist": "General Physician",
        "overview": "Mild upper respiratory viral infection causing runny nose, sneezing, sore throat, and cough. Usually improves with rest and fluids.",
        "symptoms": {"Cold": 3, "Cough": 3, "Sore Throat": 2, "Fever": 1, "Headache": 1, "Weakness": 1},
    },
    {
        "name": "Viral Fever",
        "source": "WHO Primary Care",
        "who_url": "https://www.who.int/news-room/fact-sheets/detail/influenza-(seasonal)",
        "specialist": "General Physician",
        "overview": "Common short-term fever caused by viral infection, often accompanied by body ache, headache, and tiredness.",
        "symptoms": {"Fever": 3, "Body Pain": 2, "Headache": 2, "Weakness": 2, "Chills": 1, "Cold": 1},
    },
    {
        "name": "Food Poisoning / Stomach Infection",
        "source": "WHO",
        "who_url": "https://www.who.int/news-room/fact-sheets/detail/diarrhoeal-disease",
        "specialist": "Gastroenterologist",
        "overview": "Common digestive illness from contaminated food or water causing loose motion, vomiting, and stomach cramps. Hydration (ORS) is important.",
        "symptoms": {"Loose Motion": 3, "Vomiting": 3, "Stomach Pain": 3, "Weakness": 1, "Fever": 1},
    },
    {
        "name": "Acidity / Gastritis (Indigestion)",
        "source": "WHO Primary Care",
        "who_url": "",
        "specialist": "Gastroenterologist",
        "overview": "Stomach lining irritation or acid reflux causing upper stomach pain, nausea, or chest discomfort after meals.",
        "symptoms": {"Stomach Pain": 3, "Vomiting": 2, "Chest Pain": 1, "Loss of Appetite": 1},
    },
    {
        "name": "Throat Infection (Tonsillitis / Pharyngitis)",
        "source": "WHO Primary Care",
        "who_url": "",
        "specialist": "ENT Specialist",
        "overview": "Irritation or infection of the throat causing throat pain, difficulty swallowing, cough, or mild fever.",
        "symptoms": {"Sore Throat": 3, "Cough": 2, "Fever": 2, "Cold": 1, "Swelling": 1},
    },
    {
        "name": "Skin Allergy / Rash (Dermatitis)",
        "source": "WHO Primary Care",
        "who_url": "",
        "specialist": "Dermatologist",
        "overview": "Common skin reaction to allergens, heat, or irritation causing redness, itching, bumps, or rash.",
        "symptoms": {"Skin Rash": 3, "Swelling": 1},
    },
    {
        "name": "Dehydration / Heat Exhaustion",
        "source": "WHO Primary Care",
        "who_url": "https://www.who.int/news-room/fact-sheets/detail/diarrhoeal-disease",
        "specialist": "General Physician",
        "overview": "Loss of body fluids and salts causing dizziness, weakness, headache, and fatigue, especially after fever, vomiting, or loose motion.",
        "symptoms": {"Dizziness": 3, "Weakness": 3, "Headache": 2, "Loose Motion": 1, "Vomiting": 1},
    },
    {
        "name": "Urinary Tract Infection (UTI)",
        "source": "WHO Primary Care",
        "who_url": "",
        "specialist": "Urologist",
        "overview": "Common urinary infection causing burning or discomfort while urinating, lower stomach pain, or fever.",
        "symptoms": {"Urinary Burning": 3, "Stomach Pain": 2, "Fever": 1},
    },
    {
        "name": "Ear Infection",
        "source": "WHO Primary Care",
        "who_url": "https://www.who.int/news-room/fact-sheets/detail/deafness-and-hearing-loss",
        "specialist": "ENT Specialist",
        "overview": "Common middle or outer ear infection causing ear pain, mild fever, or dizziness, often following a cold.",
        "symptoms": {"Ear Pain": 3, "Fever": 1, "Cold": 1, "Dizziness": 1},
    },
    {
        "name": "Eye Infection / Allergy (Conjunctivitis)",
        "source": "WHO Primary Care",
        "who_url": "",
        "specialist": "Ophthalmologist",
        "overview": "Irritation or infection of the eye causing redness, itching, watering, or mild eye pain.",
        "symptoms": {"Eye Pain": 3, "Headache": 1},
    },
    {
        "name": "Chest / Heart Warning (Needs Urgent Check)",
        "source": "WHO",
        "who_url": "https://www.who.int/news-room/fact-sheets/detail/cardiovascular-diseases-(cvds)",
        "specialist": "Cardiologist",
        "overview": "Chest pain or breathing trouble can sometimes indicate a serious heart or lung issue and should be evaluated promptly by a doctor.",
        "symptoms": {"Chest Pain": 3, "Breathing Problem": 3, "Dizziness": 2, "Weakness": 1},
    },
]

WHO_SYMPTOM_PATTERNS = {
    "Fever": [r"\bfever\b", r"\bhigh temperature\b", r"\bfebrile\b"],
    "Cold": [r"\brunny nose\b", r"\bnasal congestion\b", r"\bstuffy nose\b", r"\bsneezing\b", r"\bcoryza\b"],
    "Cough": [r"\bcough\b", r"\bcoughing\b"],
    "Headache": [r"\bheadache\b", r"\bheadaches\b", r"\bmigraine\b"],
    "Vomiting": [r"\bvomiting\b", r"\bvomit\b", r"\bnausea\b"],
    "Loose Motion": [r"\bdiarrhoea\b", r"\bdiarrhea\b", r"\bloose stool", r"\bwatery stool"],
    "Stomach Pain": [r"\babdominal pain\b", r"\bstomach pain\b", r"\babdominal cramp", r"\bstomach ache\b"],
    "Breathing Problem": [r"\bshortness of breath\b", r"\bdifficulty breathing\b", r"\bbreathlessness\b", r"\bwheezing\b"],
    "Chest Pain": [r"\bchest pain\b", r"\bpain in the chest\b", r"\bchest tightness\b"],
    "Dizziness": [r"\bdizziness\b", r"\bdizzy\b", r"\bvertigo\b", r"\blightheaded"],
    "Weakness": [r"\bweakness\b", r"\bfatigue\b", r"\btiredness\b", r"\blethargy\b"],
    "Body Pain": [r"\bmuscle pain\b", r"\bmuscle aches?\b", r"\bbody ache\b", r"\bbody pain\b", r"\baches and pains\b", r"\bback pain\b"],
    "Skin Rash": [r"\brash\b", r"\brashes\b", r"\bitching\b", r"\bhives\b", r"\bskin lesions?\b"],
    "Sore Throat": [r"\bsore throat\b", r"\bthroat pain\b", r"\bdifficulty swallowing\b"],
    "Joint Pain": [r"\bjoint pain\b", r"\bjoint swelling\b", r"\bstiff joints\b"],
    "Chills": [r"\bchills\b", r"\bshivering\b"],
    "Jaundice": [r"\bjaundice\b", r"\byellowing of the skin\b", r"\byellow eyes\b", r"\bdark urine\b"],
    "Weight Loss": [r"\bweight loss\b"],
    "Night Sweats": [r"\bnight sweats\b"],
    "Loss of Appetite": [r"\bloss of appetite\b", r"\bpoor appetite\b"],
    "Constipation": [r"\bconstipation\b"],
    "Eye Pain": [r"\beye pain\b", r"\bpain behind the eyes\b", r"\bconjunctivitis\b"],
    "Urinary Burning": [r"\bpainful urination\b", r"\bfrequent urination\b"],
    "Swelling": [r"\bswelling\b"],
    "Ear Pain": [r"\bear pain\b", r"\bhearing loss\b"],
}


def _clean_html(raw_html):
    if not raw_html:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(raw_html))
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_symptom_texts(item):
    brief = _clean_html(item.get("SymptomsBriefSummary"))
    longer = _clean_html(item.get("SymptomsLongerSummary"))
    content = item.get("Content") or ""

    section_matches = re.findall(
        r"<h[23][^>]*>[^<]*(?:symptom|sign|clinical)[^<]*</h[23]>(.*?)(?=<h[23][^>]*>|$)",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    section_text = _clean_html(" ".join(section_matches))

    primary_text = " ".join(part for part in (brief, section_text) if part).strip()
    secondary_text = longer

    if not primary_text and not secondary_text:
        all_clean = _clean_html(item.get("ConditionBriefOverview") or "") + " " + _clean_html(content)
        sentences = re.split(r"(?<=[.!?])\s+", all_clean)
        symptom_sentences = [
            s for s in sentences
            if re.search(r"\b(symptom|symptoms|signs include|characterized by|presents with)\b", s, re.I)
        ]
        secondary_text = " ".join(symptom_sentences[:5])

    return primary_text, secondary_text


def _score_symptoms(primary_text, secondary_text):
    scores = {}
    p_lower = primary_text.lower()
    s_lower = secondary_text.lower()

    for symptom, patterns in WHO_SYMPTOM_PATTERNS.items():
        primary_hits = sum(len(re.findall(pat, p_lower)) for pat in patterns)
        secondary_hits = sum(len(re.findall(pat, s_lower)) for pat in patterns)
        if primary_hits > 0:
            scores[symptom] = 3 if primary_hits >= 2 else 2
        elif secondary_hits > 0:
            scores[symptom] = 2 if secondary_hits >= 2 else 1

    return scores


def _match_allowed_who_title(title):
    t = title.lower().strip()
    for key, (friendly_name, specialist) in _ALLOWED_COMMON_WHO_KEYWORDS.items():
        if key in t:
            return friendly_name, specialist
    return None, None


def fetch_who_conditions():
    """
    Fetch official WHO Fact Sheets via the public WHO OData API, keep common,
    patient-understandable conditions (excluding rare/alarming outbreak diseases),
    and combine with everyday primary-care conditions.
    """
    all_items = []
    for skip in range(0, 300, 50):
        response = requests.get(
            WHO_FACTSHEETS_URL,
            params={
                "$select": (
                    "Title,ConditionName,ItemDefaultUrl,ConditionBriefOverview,"
                    "SymptomsBriefSummary,SymptomsLongerSummary,Content"
                ),
                "$top": 50,
                "$skip": skip,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=25,
        )
        response.raise_for_status()
        batch = response.json().get("value", [])
        if not batch:
            break
        all_items.extend(batch)
        if len(batch) < 50:
            break

    conditions_by_name = {}

    for item in all_items:
        raw_name = (item.get("ConditionName") or item.get("Title") or "").strip()
        if not raw_name:
            continue

        friendly_name, specialist = _match_allowed_who_title(raw_name)
        if not friendly_name:
            continue

        primary_text, secondary_text = _extract_symptom_texts(item)
        symptom_scores = _score_symptoms(primary_text, secondary_text)
        if len(symptom_scores) < 2:
            continue

        overview_raw = _clean_html(item.get("ConditionBriefOverview") or primary_text or secondary_text)
        overview = overview_raw[:220].rsplit(" ", 1)[0] + "..." if len(overview_raw) > 220 else overview_raw

        url_path = (item.get("ItemDefaultUrl") or "").strip()
        who_url = (
            f"https://www.who.int/news-room/fact-sheets/detail{url_path}"
            if url_path.startswith("/")
            else "https://www.who.int/news-room/fact-sheets"
        )

        # Ensure key real-world symptoms for well-known Indian conditions aren't missed if brief omitted them
        if friendly_name == "Dengue":
            symptom_scores.setdefault("Fever", 3)
            symptom_scores.setdefault("Headache", 2)
            symptom_scores.setdefault("Body Pain", 2)
            symptom_scores.setdefault("Weakness", 1)
        elif friendly_name == "Malaria":
            symptom_scores.setdefault("Fever", 3)
            symptom_scores.setdefault("Headache", 2)
            symptom_scores.setdefault("Chills", 2)
            symptom_scores.setdefault("Weakness", 1)
        elif friendly_name == "Typhoid Fever":
            symptom_scores.setdefault("Fever", 3)
            symptom_scores.setdefault("Stomach Pain", 2)
            symptom_scores.setdefault("Headache", 2)
            symptom_scores.setdefault("Weakness", 2)

        conditions_by_name[friendly_name] = {
            "name": friendly_name,
            "source": "WHO",
            "who_url": who_url,
            "specialist": specialist,
            "overview": overview,
            "symptoms": symptom_scores,
        }

    # Add everyday primary-care conditions so mild/normal symptoms always return understandable matches
    for common in COMMON_PRIMARY_CARE_CONDITIONS:
        conditions_by_name.setdefault(common["name"], common)

    conditions = sorted(conditions_by_name.values(), key=lambda c: c["name"])
    return conditions


def store_conditions_to_json(conditions, path=CONDITIONS_JSON_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": "World Health Organization (WHO) Fact Sheets + Primary Care",
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "count": len(conditions),
        "conditions": conditions,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def store_conditions_to_db(conditions):
    """Persist curated WHO & common conditions into the who_conditions database table."""
    ensure_tables()
    connection = get_connection()
    cursor = connection.cursor()
    is_sqlite = getattr(connection, "backend", "postgres") == "sqlite"

    try:
        if is_sqlite:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS who_conditions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    source VARCHAR(50) NOT NULL,
                    who_url TEXT,
                    specialist TEXT,
                    overview TEXT,
                    symptoms_json TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS who_conditions (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    source VARCHAR(50) NOT NULL,
                    who_url TEXT,
                    specialist TEXT,
                    overview TEXT,
                    symptoms_json TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

        cursor.execute("DELETE FROM who_conditions")

        for cond in conditions:
            cursor.execute(
                """
                INSERT INTO who_conditions (name, source, who_url, specialist, overview, symptoms_json)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    cond["name"],
                    cond.get("source", "WHO"),
                    cond.get("who_url", ""),
                    cond.get("specialist", "General Physician"),
                    cond.get("overview", ""),
                    json.dumps(cond["symptoms"], ensure_ascii=False),
                ),
            )

        connection.commit()
    finally:
        cursor.close()
        connection.close()


def sync_who_knowledge_base():
    conditions = fetch_who_conditions()
    store_conditions_to_json(conditions)
    store_conditions_to_db(conditions)
    return conditions


if __name__ == "__main__":
    synced = sync_who_knowledge_base()
    print(f"Synced {len(synced)} common WHO & primary-care conditions into JSON and database.")
    for c in synced:
        print(" -", c["name"], "|", c["specialist"], "|", list(c["symptoms"].keys()))
