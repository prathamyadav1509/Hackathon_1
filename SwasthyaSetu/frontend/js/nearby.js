const API_BASE =
    window.location.protocol === "file:" ||
    ["5500", "5501", "3000", "5173"].includes(window.location.port)
        ? "http://127.0.0.1:8001"
        : "";

async function fetchNearbyHealthcare(latitude, longitude, radius = 5000, category = "all") {
    const response = await fetch(
        `${API_BASE}/nearby-healthcare?latitude=${encodeURIComponent(latitude)}&longitude=${encodeURIComponent(longitude)}&radius=${encodeURIComponent(radius)}&category=${encodeURIComponent(category)}`
    );
    if (!response.ok) {
        throw new Error("Failed to fetch nearby healthcare");
    }
    return response.json();
}

function openHealthcareOnGoogleMaps(query, latitude, longitude) {
    const mapsUrl =
        "https://www.google.com/maps/search/" +
        encodeURIComponent(query || "hospitals doctors clinics labs") +
        "/@" +
        latitude +
        "," +
        longitude +
        ",14z";

    window.open(mapsUrl, "_blank", "noopener,noreferrer");
}
