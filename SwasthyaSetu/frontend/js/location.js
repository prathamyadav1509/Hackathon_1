// ==========================================
// SwasthyaSetu - Location Permission
// ==========================================

function requestUserLocation() {

    if (!navigator.geolocation) {

        alert(
            "Your browser does not support location services."
        );

        return;
    }

    navigator.geolocation.getCurrentPosition(

        function (position) {

            const latitude = position.coords.latitude;
            const longitude = position.coords.longitude;

            // Save location temporarily for nearby healthcare search
            sessionStorage.setItem(
                "userLocation",
                JSON.stringify({
                    latitude: latitude,
                    longitude: longitude
                })
            );

            console.log("Location permission granted.");
            console.log("Latitude:", latitude);
            console.log("Longitude:", longitude);

            alert(
                "Location permission granted successfully!"
            );
        },

        function (error) {

            console.log(
                "Location permission was not granted.",
                error.message
            );

            alert(
                "Location permission was not granted. " +
                "You can still use the health guidance features."
            );
        },

        {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 0
        }
    );
}