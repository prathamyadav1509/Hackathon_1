# ==========================================
# SwasthyaSetu - Specialist Matcher
# ==========================================

SPECIALIST_RULES = {
    "Fever": "General Physician",
    "Cold": "General Physician",
    "Cough": "General Physician",
    "Headache": "General Physician",
    "Vomiting": "Gastroenterologist",
    "Loose Motion": "Gastroenterologist",
    "Stomach Pain": "Gastroenterologist",
    "Breathing Problem": "Pulmonologist",
    "Chest Pain": "Cardiologist",
    "Dizziness": "Neurologist",
    "Weakness": "General Physician",
    "Body Pain": "General Physician",
    "Skin Rash": "Dermatologist",
    "Sore Throat": "ENT Specialist",
    "Ear Pain": "ENT Specialist",
    "Eye Pain": "Ophthalmologist",
    "Joint Pain": "Orthopaedic Specialist",
    "Jaundice": "Gastroenterologist",
    "Urinary Burning": "Urologist",
    "Other": "General Physician",
}


def recommend_specialist(user_symptoms, condition_matches=None):
    """
    Suggests appropriate healthcare specialties based on reported symptoms
    and matched WHO conditions. This is a referral suggestion, not a diagnosis.
    """
    recommendations = []

    for symptom in user_symptoms:
        clean = symptom.strip()
        if not clean or clean.lower() == "other":
            continue
        specialist = SPECIALIST_RULES.get(clean, "General Physician")
        if specialist not in recommendations:
            recommendations.append(specialist)

    if condition_matches:
        for match in condition_matches[:2]:
            spec = (match.get("specialist") or "").strip()
            if spec and spec not in recommendations:
                recommendations.append(spec)

    if not recommendations:
        recommendations.append("General Physician")

    return recommendations[:3]
