const API_BASE =
    window.location.protocol === "file:" ||
    ["5500", "5501", "3000", "5173"].includes(window.location.port)
        ? "http://127.0.0.1:8001"
        : "";

const symptomForm = document.getElementById("symptomForm");

symptomForm.addEventListener("submit", async function (event) {
    event.preventDefault();

    const lang = localStorage.getItem("selectedLanguage") || "en";
    const age = Number(document.getElementById("age").value);
    const duration = document.getElementById("duration").value;

    if (!Number.isInteger(age) || age < 1 || age > 120) {
        alert(
            lang === "hi"
                ? "कृपया 1 से 120 के बीच सही उम्र दर्ज करें।"
                : "Please enter a valid age between 1 and 120."
        );
        return;
    }

    if (!duration) {
        alert(
            lang === "hi"
                ? "कृपया लक्षणों की अवधि चुनें।"
                : "Please select how long you have had these symptoms."
        );
        return;
    }

    const selectedSymptoms = Array.from(
        document.querySelectorAll('input[name="symptom"]:checked')
    ).map(input => input.value);

    if (selectedSymptoms.length === 0) {
        alert(
            lang === "hi"
                ? "कृपया कम से कम एक लक्षण चुनें।"
                : "Please select at least one symptom."
        );
        return;
    }

    const otherCheckbox = document.getElementById("otherSymptomCheckbox");
    const otherInput = document.getElementById("otherSymptomsInput");
    let otherSymptomsText = null;

    if (otherCheckbox && otherCheckbox.checked && otherInput) {
        otherSymptomsText = otherInput.value.trim();
        if (!otherSymptomsText) {
            alert(
                lang === "hi"
                    ? "कृपया अपनी अन्य समस्या लिखें।"
                    : "Please describe your other problem or symptoms."
            );
            otherInput.focus();
            return;
        }
    }

    const submitBtn = symptomForm.querySelector('button[type="submit"]');
    if (submitBtn) {
        submitBtn.disabled = true;
    }

    const data = {
        age: age,
        symptoms: selectedSymptoms.join(", "),
        duration: duration,
        other_symptoms: otherSymptomsText
    };

    try {
        const response = await fetch(`${API_BASE}/assess`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.detail || "Server error");
        }

        const result = await response.json();

        sessionStorage.setItem(
            "healthResult",
            JSON.stringify(result)
        );

        window.location.href = "result.html";

    } catch (error) {
        console.error("Error:", error);
        alert(
            "SwasthyaSetu server se connection nahi ho pa raha. " +
            "Please make sure FastAPI server is running."
        );
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
        }
    }
});
