import json
from pathlib import Path
from database.connection import get_connection

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "data" / "medical" / "conditions.json"


def _load_conditions_from_db():
    try:
        connection = get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                SELECT name, source, who_url, specialist, overview, symptoms_json
                FROM who_conditions
                """
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()
            connection.close()

        conditions = []
        for row in rows:
            conditions.append({
                "name": row[0],
                "source": row[1],
                "who_url": row[2],
                "specialist": row[3],
                "overview": row[4],
                "symptoms": json.loads(row[5]),
            })
        return conditions
    except Exception:
        return []


def load_conditions():
    """
    Loads stored WHO conditions from the database first, falling back to
    data/medical/conditions.json if the database table is not yet populated.
    """
    db_conditions = _load_conditions_from_db()
    if db_conditions:
        return {"conditions": db_conditions}

    with open(DATA_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def match_conditions(user_symptoms, limit=4):
    """
    Matches user symptoms against the stored WHO condition knowledge base.
    Ranks conditions by matched symptom coverage and weighted score.
    """
    data = load_conditions()

    normalized_inputs = []
    seen_inputs = set()
    for s in user_symptoms:
        clean = s.strip()
        if clean and clean.lower() not in seen_inputs and clean.lower() != "other":
            normalized_inputs.append(clean)
            seen_inputs.add(clean.lower())

    if not normalized_inputs:
        return []

    results = []

    for condition in data.get("conditions", []):
        condition_symptoms = condition.get("symptoms", {})
        if not condition_symptoms:
            continue

        lower_map = {k.lower(): (k, v) for k, v in condition_symptoms.items()}

        matched_symptoms = []
        score = 0
        maximum_score = sum(condition_symptoms.values())
        if maximum_score <= 0:
            continue

        for symptom in normalized_inputs:
            key_lower = symptom.lower()
            if key_lower in lower_map:
                canonical_name, weight = lower_map[key_lower]
                matched_symptoms.append(canonical_name)
                score += weight

        if score > 0:
            # Blend condition coverage and user-symptom coverage for balanced ranking
            condition_coverage = score / maximum_score
            user_coverage = len(matched_symptoms) / len(normalized_inputs)
            blended_score = (0.65 * condition_coverage) + (0.35 * user_coverage)
            match_percentage = min(99, max(10, round(condition_coverage * 100)))

            if match_percentage >= 65:
                match_level = "Strong symptom match"
            elif match_percentage >= 35:
                match_level = "Moderate symptom match"
            else:
                match_level = "Possible symptom match"

            results.append({
                "condition": condition["name"],
                "source": condition.get("source", "WHO"),
                "who_url": condition.get("who_url", ""),
                "overview": condition.get("overview", ""),
                "specialist": condition.get("specialist", "General Physician"),
                "matched_symptoms": matched_symptoms,
                "match_percentage": match_percentage,
                "match_level": match_level,
                "_rank": (len(matched_symptoms), blended_score, score),
            })

    results.sort(key=lambda x: x["_rank"], reverse=True)
    for item in results:
        item.pop("_rank", None)

    return results[:limit]
