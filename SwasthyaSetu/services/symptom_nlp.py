import re


SYMPTOM_KEYWORDS = {
    "Fever": [
        "fever",
        "bukhar",
        "high temperature",
        "बुखार",
    ],
    "Cold": [
        "cold",
        "sardi",
        "jukam",
        "runny nose",
        "blocked nose",
        "जुकाम",
        "सर्दी",
    ],
    "Cough": [
        "cough",
        "khansi",
        "खांसी",
    ],
    "Headache": [
        "headache",
        "migraine",
        "sar dard",
        "sir dard",
        "सिर दर्द",
        "सर दर्द",
    ],
    "Vomiting": [
        "vomiting",
        "vomit",
        "nausea",
        "ulti",
        "उल्टी",
        "जी मिचलाना",
    ],
    "Loose Motion": [
        "loose motion",
        "diarrhea",
        "diarrhoea",
        "dast",
        "watery stool",
        "दस्त",
    ],
    "Stomach Pain": [
        "stomach pain",
        "stomach ache",
        "abdominal pain",
        "pet pain",
        "pet dard",
        "पेट दर्द",
    ],
    "Breathing Problem": [
        "breathing problem",
        "difficulty breathing",
        "shortness of breath",
        "breathlessness",
        "wheezing",
        "saans ki problem",
        "saans lene me dikkat",
        "सांस लेने में परेशानी",
    ],
    "Chest Pain": [
        "chest pain",
        "pain in chest",
        "chest tightness",
        "seene me dard",
        "सीने में दर्द",
    ],
    "Dizziness": [
        "dizziness",
        "dizzy",
        "vertigo",
        "chakkar",
        "चक्कर",
    ],
    "Weakness": [
        "weakness",
        "weak",
        "fatigue",
        "tiredness",
        "kamzori",
        "थकान",
        "कमजोरी",
    ],
    "Body Pain": [
        "body pain",
        "body ache",
        "muscle pain",
        "badan dard",
        "शरीर में दर्द",
    ],
    "Skin Rash": [
        "skin rash",
        "rash",
        "rashes",
        "itching",
        "blister",
        "daane",
        "khujli",
        "दाने",
        "खुजली",
    ],
    "Sore Throat": [
        "sore throat",
        "throat pain",
        "gale me dard",
        "gale me kharash",
        "गले में दर्द",
        "गले में खराश",
    ],
    "Joint Pain": [
        "joint pain",
        "jodo me dard",
        "जोड़ों में दर्द",
    ],
    "Chills": [
        "chills",
        "shivering",
        "thand lagna",
        "कंपकंपी",
    ],
    "Jaundice": [
        "jaundice",
        "yellow eyes",
        "yellow skin",
        "piliya",
        "पीलिया",
    ],
    "Ear Pain": [
        "ear pain",
        "earache",
        "kaan dard",
        "kaan me dard",
        "कान में दर्द",
    ],
    "Eye Pain": [
        "eye pain",
        "red eyes",
        "blurred vision",
        "aankh dard",
        "aankh me dard",
    ],
    "Urinary Burning": [
        "burning urination",
        "painful urination",
        "peshab me jalan",
        "पेशाब में जलन",
    ],
    "Swelling": [
        "swelling",
        "swollen",
        "sujan",
        "सूजन",
    ],
    "Constipation": [
        "constipation",
        "kabz",
        "कब्ज",
    ],
}


def normalize_text(text):
    """Converts user text into a simple searchable format."""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def extract_symptoms(text):
    """
    Extracts known symptoms from natural-language user input.
    This function does NOT diagnose diseases; it only identifies symptom words/phrases.
    """
    text = normalize_text(text)
    detected_symptoms = []

    for symptom, keywords in SYMPTOM_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in text:
                if symptom not in detected_symptoms:
                    detected_symptoms.append(symptom)
                break

    return detected_symptoms
