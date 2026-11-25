from contextlib import asynccontextmanager
from pathlib import Path
import sys
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from database.connection import ensure_tables, get_connection
from services.medical_matcher import match_conditions
from services.nearby_healthcare import find_nearby_healthcare
from services.specialist_matcher import recommend_specialist
from services.symptom_nlp import extract_symptoms


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_tables()
    yield


app = FastAPI(title="SwasthyaSetu", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class SymptomRequest(BaseModel):
    age: int = Field(..., ge=1, le=120)
    symptoms: str = Field(..., min_length=1, max_length=500)
    duration: Literal[
        "1_to_3_days",
        "4_to_7_days",
        "1_to_2_weeks",
        "more_than_2_weeks",
    ]
    other_symptoms: Optional[str] = Field(default=None, max_length=500)

    @field_validator("symptoms")
    @classmethod
    def validate_symptoms(cls, value: str) -> str:
        cleaned = ", ".join(
            part.strip()
            for part in value.split(",")
            if part.strip()
        )
        if not cleaned:
            raise ValueError("At least one symptom is required.")
        return cleaned

    @field_validator("other_symptoms")
    @classmethod
    def validate_other_symptoms(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = " ".join(value.split()).strip()
        return cleaned or None


def assess_risk(symptoms: str, duration: str, age: int):
    symptoms_lower = symptoms.lower()

    urgent_symptoms = [
        "chest pain",
        "breathing problem",
    ]

    for symptom in urgent_symptoms:
        if symptom in symptoms_lower:
            return {
                "level": "Urgent",
                "title": "Prompt Medical Care Recommended",
                "message": (
                    "The symptoms you selected may require prompt "
                    "professional medical attention. Please contact "
                    "a qualified healthcare professional or appropriate "
                    "medical facility."
                ),
                "next_step": (
                    "Seek professional medical care promptly. "
                    "If symptoms are severe or rapidly worsening, "
                    "seek emergency medical help."
                ),
            }

    moderate_symptoms = [
        "vomiting",
        "loose motion",
        "dizziness",
        "weakness",
        "stomach pain",
    ]

    moderate_found = any(
        symptom in symptoms_lower
        for symptom in moderate_symptoms
    )

    long_duration = duration in [
        "1_to_2_weeks",
        "more_than_2_weeks",
    ]

    age_caution = age < 5 or age >= 65

    if moderate_found or long_duration or age_caution:
        return {
            "level": "Moderate",
            "title": "Medical Consultation Recommended",
            "message": (
                "Your information suggests that speaking with a "
                "qualified healthcare professional may be appropriate, "
                "especially if the symptoms continue or become worse."
            ),
            "next_step": (
                "Consider consulting a healthcare professional "
                "and monitor whether your symptoms improve or worsen."
            ),
        }

    return {
        "level": "Low",
        "title": "Monitor Your Symptoms",
        "message": (
            "No urgent warning sign was identified from the information "
            "provided. Continue to monitor your symptoms."
        ),
        "next_step": (
            "Monitor your symptoms. If they continue, become worse, "
            "or cause concern, consult a qualified healthcare professional."
        ),
    }


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "message": "SwasthyaSetu API is running successfully!",
    }


@app.post("/assess")
def assess_symptoms(data: SymptomRequest):
    user_symptoms = [
        symptom.strip()
        for symptom in data.symptoms.split(",")
        if symptom.strip()
    ]

    extracted_from_other = []
    if data.other_symptoms:
        extracted_from_other = extract_symptoms(data.other_symptoms)
        for detected in extracted_from_other:
            if detected not in user_symptoms:
                user_symptoms.append(detected)

    # Format display string so custom problem details are preserved cleanly in DB and UI
    if data.other_symptoms:
        safe_other = data.other_symptoms.replace(",", ";")
        display_parts = [
            f"Other ({safe_other})" if item == "Other" else item
            for item in [s.strip() for s in data.symptoms.split(",") if s.strip()]
        ]
        if "Other" not in [s.strip() for s in data.symptoms.split(",")]:
            display_parts.append(f"Other ({safe_other})")
        formatted_symptoms = ", ".join(display_parts)
    else:
        formatted_symptoms = data.symptoms

    risk_eval_text = ", ".join(user_symptoms)
    if data.other_symptoms:
        risk_eval_text = f"{risk_eval_text}, {data.other_symptoms}"

    risk = assess_risk(
        risk_eval_text,
        data.duration,
        data.age,
    )

    condition_matches = match_conditions(user_symptoms)
    specialists = recommend_specialist(user_symptoms, condition_matches)

    connection = None
    cursor = None
    try:
        ensure_tables()
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO health_assessments
            (age, symptoms, duration, risk_level, recommended_specialist)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                data.age,
                formatted_symptoms,
                data.duration,
                risk["level"],
                ", ".join(specialists),
            ),
        )
        connection.commit()
    except Exception as exc:
        if connection is not None:
            connection.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Could not save assessment: {exc}",
        ) from exc
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()

    return {
        "message": "Your information has been received successfully.",
        "age": data.age,
        "symptoms": formatted_symptoms,
        "other_symptoms": data.other_symptoms,
        "detected_from_other": extracted_from_other,
        "duration": data.duration,
        "risk_level": risk["level"],
        "risk_title": risk["title"],
        "risk_message": risk["message"],
        "next_step": risk["next_step"],
        "condition_matches": condition_matches,
        "recommended_specialists": specialists,
    }


@app.get("/nearby-hospitals")
def nearby_hospitals(
    latitude: float = Query(..., ge=-90.0, le=90.0),
    longitude: float = Query(..., ge=-180.0, le=180.0),
    radius: int = Query(5000, ge=500, le=25000),
):
    hospitals = find_nearby_healthcare(
        latitude,
        longitude,
        radius=radius,
        category="hospital",
    )

    return {
        "source": "OpenStreetMap",
        "filter": "hospitals_only",
        "count": len(hospitals),
        "facilities": hospitals,
        "hospitals": hospitals,
    }


@app.get("/nearby-healthcare")
def nearby_healthcare(
    latitude: float = Query(..., ge=-90.0, le=90.0),
    longitude: float = Query(..., ge=-180.0, le=180.0),
    radius: int = Query(5000, ge=500, le=25000),
    category: Literal["all", "hospital", "doctor", "clinic", "lab"] = Query("all"),
):
    facilities = find_nearby_healthcare(
        latitude,
        longitude,
        radius=radius,
        category=category,
    )

    counts = {
        "hospital": sum(1 for item in facilities if item["type"] == "hospital"),
        "doctor": sum(1 for item in facilities if item["type"] == "doctor"),
        "clinic": sum(1 for item in facilities if item["type"] == "clinic"),
        "lab": sum(1 for item in facilities if item["type"] == "lab"),
    }

    return {
        "source": "OpenStreetMap",
        "category": category,
        "count": len(facilities),
        "counts": counts,
        "facilities": facilities,
    }


@app.get("/assessment-history")
def assessment_history():
    connection = None
    cursor = None
    try:
        ensure_tables()
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT
                id,
                age,
                symptoms,
                duration,
                risk_level,
                recommended_specialist,
                created_at
            FROM health_assessments
            ORDER BY id DESC
            LIMIT 20
            """
        )
        rows = cursor.fetchall()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not load assessment history: {exc}",
        ) from exc
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()

    assessments = []
    for row in rows:
        created_at = row[6]
        if hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()
        assessments.append({
            "id": row[0],
            "age": row[1],
            "symptoms": row[2],
            "duration": row[3],
            "risk_level": row[4],
            "recommended_specialist": row[5],
            "created_at": created_at,
        })

    return {
        "count": len(assessments),
        "assessments": assessments,
    }


FRONTEND_DIR = BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
