from datetime import datetime
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import requests

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.main import app
from services import nearby_healthcare as nh
from services.nearby_healthcare import (
    _classify_facility,
    _is_hospital_facility,
    evaluate_opening_hours,
    find_nearby_healthcare,
)


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_frontend_pages_served():
    for page in ["/", "/symptoms.html", "/result.html", "/nearby.html", "/history.html"]:
        resp = client.get(page)
        assert resp.status_code == 200


def test_assess_and_history_workflow(tmp_path, monkeypatch):
    test_db = tmp_path / "test_swasthyasetu.db"
    monkeypatch.setenv("DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(test_db))

    payload = {
        "age": 28,
        "symptoms": "Loose Motion, Vomiting, Stomach Pain",
        "duration": "4_to_7_days",
    }
    resp = client.post("/assess", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_level"] == "Moderate"
    assert "Gastroenterologist" in data["recommended_specialists"]
    matched_names = [match["condition"] for match in data["condition_matches"]]
    assert "Food Poisoning / Stomach Infection" in matched_names
    assert data["condition_matches"][0]["who_url"].startswith("https://www.who.int/")

    urgent_resp = client.post(
        "/assess",
        json={"age": 45, "symptoms": "Chest Pain", "duration": "1_to_3_days"},
    )
    assert urgent_resp.status_code == 200
    assert urgent_resp.json()["risk_level"] == "Urgent"
    assert "Cardiologist" in urgent_resp.json()["recommended_specialists"]

    history_resp = client.get("/assessment-history")
    assert history_resp.status_code == 200
    history = history_resp.json()
    assert history["count"] >= 2
    assert history["assessments"][0]["symptoms"] == "Chest Pain"


def test_assess_validation():
    assert client.post("/assess", json={"age": 0, "symptoms": "Fever", "duration": "1_to_3_days"}).status_code == 422
    assert client.post("/assess", json={"age": 25, "symptoms": "   ", "duration": "1_to_3_days"}).status_code == 422
    assert client.post("/assess", json={"age": 25, "symptoms": "Fever", "duration": "invalid"}).status_code == 422


def test_other_symptoms_nlp_and_persistence(tmp_path, monkeypatch):
    test_db = tmp_path / "test_other.db"
    monkeypatch.setenv("DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(test_db))

    # Custom text with no predefined red flags
    resp = client.post(
        "/assess",
        json={
            "age": 26,
            "symptoms": "Other",
            "other_symptoms": "skin rash, ear pain",
            "duration": "1_to_3_days",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["symptoms"] == "Other (skin rash; ear pain)"
    assert body["other_symptoms"] == "skin rash, ear pain"
    assert body["risk_level"] == "Low"
    assert "Dermatologist" in body["recommended_specialists"]
    assert "ENT Specialist" in body["recommended_specialists"]
    assert len(body["condition_matches"]) > 0

    # Hinglish description in Other triggers NLP symptom + risk detection
    hinglish_resp = client.post(
        "/assess",
        json={
            "age": 40,
            "symptoms": "Other",
            "other_symptoms": "mujhe bukhar aur seene me dard ho raha hai",
            "duration": "1_to_3_days",
        },
    )
    assert hinglish_resp.status_code == 200
    h_body = hinglish_resp.json()
    assert "Fever" in h_body["detected_from_other"]
    assert "Chest Pain" in h_body["detected_from_other"]
    assert h_body["risk_level"] == "Urgent"


def test_facility_classification_rules():
    assert _is_hospital_facility({"name": "City Civil Hospital", "amenity": "hospital"}) is True
    assert _is_hospital_facility({"name": "Dr. Sharma Clinic", "amenity": "clinic"}) is False

    assert _classify_facility({"name": "Dr. Vidya Joshi", "amenity": "doctors"}) == "doctor"
    assert _classify_facility({"name": "Dr. Godbole Laboratory", "amenity": "doctors"}) == "lab"
    assert _classify_facility({"name": "Healing Hands Clinic", "amenity": "clinic"}) == "clinic"
    assert _classify_facility({"name": "PH Diagnostic Center", "healthcare": "laboratory"}) == "lab"

    # Non-medical facilities must be excluded
    assert _classify_facility({"name": "National Chemical Laboratory", "amenity": "research_institute"}) is None
    assert _classify_facility({"name": "Regional Forensic Science Laboratory", "office": "laboratory"}) is None
    assert _classify_facility({"name": "Apollo Pharmacy", "amenity": "pharmacy"}) is None
    assert _classify_facility({"name": "Pet Care Veterinary Hospital", "amenity": "hospital"}) is None


def test_opening_hours_evaluation():
    open_flag, label = evaluate_opening_hours("24/7")
    assert open_flag is True
    assert "24/7" in label

    # Wednesday 11:00 AM inside Mo-Sa 09:00-13:00
    wed_morning = datetime(2026, 11, 25, 11, 0)
    open_flag, _ = evaluate_opening_hours("Mo-Sa 09:00-13:00, 17:00-21:00", now=wed_morning)
    assert open_flag is True

    # Wednesday 15:00 PM between morning and evening shifts
    wed_afternoon = datetime(2026, 11, 25, 15, 0)
    open_flag, _ = evaluate_opening_hours("Mo-Sa 09:00-13:00, 17:00-21:00", now=wed_afternoon)
    assert open_flag is False

    open_flag, label = evaluate_opening_hours(None)
    assert open_flag is None
    assert "call to confirm" in label


def test_nearby_hospitals_and_all_healthcare_endpoints():
    nh._CACHE.clear()
    nh._OVERPASS_COOLDOWN_UNTIL = 0.0

    mock_overpass = MagicMock()
    mock_overpass.raise_for_status.return_value = None
    mock_overpass.json.return_value = {
        "elements": [
            {
                "type": "node",
                "lat": 18.5204,
                "lon": 73.8567,
                "tags": {"name": "Sassoon General Hospital", "amenity": "hospital", "opening_hours": "24/7"},
            },
            {
                "type": "node",
                "lat": 18.5210,
                "lon": 73.8570,
                "tags": {"name": "Dr. Kulkarni Clinic", "amenity": "clinic"},
            },
            {
                "type": "node",
                "lat": 18.5220,
                "lon": 73.8580,
                "tags": {"name": "Dr. Mehta", "amenity": "doctors", "healthcare:speciality": "general"},
            },
            {
                "type": "node",
                "lat": 18.5230,
                "lon": 73.8590,
                "tags": {"name": "Nadkarni Pathology Laboratory", "healthcare": "laboratory"},
            },
        ]
    }

    with patch("services.nearby_healthcare.requests.post", return_value=mock_overpass):
        hosp_resp = client.get("/nearby-hospitals?latitude=18.5204&longitude=73.8567")
        assert hosp_resp.status_code == 200
        hosp_body = hosp_resp.json()
        assert hosp_body["filter"] == "hospitals_only"
        assert hosp_body["count"] == 1
        assert hosp_body["hospitals"][0]["name"] == "Sassoon General Hospital"

        all_resp = client.get("/nearby-healthcare?latitude=18.5204&longitude=73.8567&category=all")
        assert all_resp.status_code == 200
        all_body = all_resp.json()
        assert all_body["count"] == 4
        assert all_body["counts"] == {"hospital": 1, "doctor": 1, "clinic": 1, "lab": 1}

    nh._CACHE.clear()
    nh._OVERPASS_COOLDOWN_UNTIL = 0.0

    def fake_nominatim_get(url, params=None, **kwargs):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        if params.get("amenity") == "hospital":
            resp.json.return_value = [
                {"name": "Jehangir Hospital", "category": "amenity", "type": "hospital", "lat": "18.5290", "lon": "73.8760", "address": {}, "extratags": {}}
            ]
        elif params.get("amenity") == "doctors":
            resp.json.return_value = [
                {"name": "Dr. Vidya Joshi", "category": "amenity", "type": "doctors", "lat": "18.5250", "lon": "73.8600", "address": {}, "extratags": {"phone": "123456"}}
            ]
        elif params.get("amenity") == "clinic":
            resp.json.return_value = [
                {"name": "Healing Hands Clinic", "category": "amenity", "type": "clinic", "lat": "18.5260", "lon": "73.8610", "address": {}, "extratags": {}}
            ]
        else:
            resp.json.return_value = [
                {"name": "PH Diagnostic Center", "category": "healthcare", "type": "laboratory", "lat": "18.5270", "lon": "73.8620", "address": {}, "extratags": {}}
            ]
        return resp

    with patch("services.nearby_healthcare.requests.post", side_effect=requests.RequestException("Overpass 502")), \
         patch("services.nearby_healthcare.requests.get", side_effect=fake_nominatim_get):
        results = find_nearby_healthcare(18.5204, 73.8567, radius=5000, category="all")
        types = {item["type"] for item in results}
        assert types == {"hospital", "doctor", "clinic", "lab"}

    assert client.get("/nearby-hospitals?latitude=999&longitude=73.85").status_code == 422
