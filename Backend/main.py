from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
import re

app = FastAPI(title="SoilGPT API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# REGIONAL SOIL REFERENCE
# ============================================================

SOIL_REFERENCE = {
    "gujarat": {
        "soil_type": "Deep Black Cotton Soil (Vertisols)",
        "ph_range": "7.1–8.9",
        "organic_carbon": "Low to medium (0.08%–0.86%)",
        "nitrogen": "Low to medium (125–323 kg/ha)",
        "phosphorus": "Medium to high (irrigated), low (rainfed)",
        "potassium": "High to very high",
        "deficiencies": "Zinc (Zn), Sulphur (S)",
        "recommendation": "Add organic matter, compost and balanced NPK. Supplement zinc and sulphur when soil testing indicates a deficiency."
    },
    "maharashtra": {
        "soil_type": "Black cotton soil and laterite (Konkan)",
        "ph_range": "6.5–8.2",
        "organic_carbon": "Low to medium (0.2%–0.75%)",
        "nitrogen": "Low to medium",
        "phosphorus": "Low to medium",
        "potassium": "Medium to high",
        "deficiencies": "Zinc, Boron, Iron in lateritic soils",
        "recommendation": "Use organic compost, balanced fertilizer and micronutrients based on soil testing."
    },
    "punjab": {
        "soil_type": "Alluvial soil (Indo-Gangetic plain)",
        "ph_range": "7.5–8.5",
        "organic_carbon": "Low (0.15%–0.5%)",
        "nitrogen": "Medium",
        "phosphorus": "Medium to high",
        "potassium": "Medium",
        "deficiencies": "Zinc, Iron, Manganese",
        "recommendation": "Consider green manuring, zinc sulphate where indicated and appropriate irrigation management."
    },
    "haryana": {
        "soil_type": "Alluvial soil (semi-arid)",
        "ph_range": "7.5–8.5",
        "organic_carbon": "Low",
        "nitrogen": "Low to medium",
        "phosphorus": "Medium",
        "potassium": "Medium",
        "deficiencies": "Zinc, Iron",
        "recommendation": "Add organic matter and use balanced NPK. Apply micronutrients according to soil-test results."
    },
    "uttarakhand": {
        "soil_type": "Brown forest soil and podzolic soil in hill regions",
        "ph_range": "5.5–7.0",
        "organic_carbon": "Medium to high (0.5%–1.5%)",
        "nitrogen": "Medium to high",
        "phosphorus": "Low to medium",
        "potassium": "Medium",
        "deficiencies": "Phosphorus, Boron",
        "recommendation": "Use suitable organic matter and address acidity or nutrient deficiencies based on soil testing."
    },
    "uttar pradesh": {
        "soil_type": "Alluvial soil (Gangetic plain)",
        "ph_range": "7.0–8.5",
        "organic_carbon": "Low to medium",
        "nitrogen": "Low to medium",
        "phosphorus": "Low to medium",
        "potassium": "Medium",
        "deficiencies": "Zinc, Sulphur",
        "recommendation": "Consider green manuring, balanced NPK and regular soil testing."
    },
    "karnataka": {
        "soil_type": "Red soil and black soil (Deccan)",
        "ph_range": "6.0–8.0",
        "organic_carbon": "Low to medium",
        "nitrogen": "Low to medium",
        "phosphorus": "Low to medium",
        "potassium": "Medium to high",
        "deficiencies": "Zinc, Boron",
        "recommendation": "Use organic manure, crop rotation and micronutrients when indicated by soil testing."
    },
    "tamil nadu": {
        "soil_type": "Red loam and coastal alluvial soil",
        "ph_range": "6.5–8.5",
        "organic_carbon": "Low to medium",
        "nitrogen": "Low to medium",
        "phosphorus": "Low to medium",
        "potassium": "Medium to high",
        "deficiencies": "Zinc, Iron",
        "recommendation": "Use balanced fertilizer and organic matter, with micronutrients guided by soil testing."
    },
    "rajasthan": {
        "soil_type": "Sandy and arid soil",
        "ph_range": "7.5–9.0",
        "organic_carbon": "Very low",
        "nitrogen": "Low",
        "phosphorus": "Low",
        "potassium": "Medium to high",
        "deficiencies": "Organic matter, Zinc, Iron",
        "recommendation": "Improve organic matter and irrigation efficiency. Soil amendments should be based on testing."
    },
    "delhi": {
        "soil_type": "Alluvial soil (Yamuna plain)",
        "ph_range": "7.0–8.5",
        "organic_carbon": "Low",
        "nitrogen": "Low to medium",
        "phosphorus": "Low to medium",
        "potassium": "Medium",
        "deficiencies": "Organic matter, Zinc",
        "recommendation": "Add suitable compost and avoid excessive fertilizer. Conduct regular soil testing."
    },
    "west bengal": {
        "soil_type": "Alluvial and deltaic soil",
        "ph_range": "5.5–7.5",
        "organic_carbon": "Medium",
        "nitrogen": "Medium",
        "phosphorus": "Low to medium",
        "potassium": "Medium",
        "deficiencies": "Zinc, Boron",
        "recommendation": "Maintain organic matter and use balanced fertilizer according to soil-test results."
    },
    "kerala": {
        "soil_type": "Laterite and coastal alluvial soil",
        "ph_range": "5.0–6.5",
        "organic_carbon": "Medium to high",
        "nitrogen": "Medium",
        "phosphorus": "Low",
        "potassium": "Medium",
        "deficiencies": "Phosphorus, Calcium, Magnesium",
        "recommendation": "Check soil acidity and nutrient levels before applying lime or other amendments."
    },
    "default": {
        "soil_type": "Mixed soil types; varies by region",
        "ph_range": "6.0–8.0 (typical reference range)",
        "organic_carbon": "Low to medium",
        "nitrogen": "Low to medium",
        "phosphorus": "Low to medium",
        "potassium": "Medium",
        "deficiencies": "Micronutrients such as Zn, B and Fe may be deficient",
        "recommendation": "Conduct a laboratory soil test for location-specific nutrient and fertilizer recommendations."
    }
}


def get_soil_reference(state: str):
    if not state:
        return SOIL_REFERENCE["default"]

    state_lower = state.lower().strip()

    for key, value in SOIL_REFERENCE.items():
        if key != "default" and (
            key in state_lower or state_lower in key
        ):
            return value

    return SOIL_REFERENCE["default"]


# ============================================================
# GEOCODING: OPEN-METEO
# ============================================================

def geocode_openmeteo(place: str):
    try:
        url = "https://geocoding-api.open-meteo.com/v1/search"

        params = {
            "name": place,
            "count": 1,
            "language": "en",
            "format": "json",
            "countryCode": "IN",
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        results = response.json().get("results", [])

        if not results:
            return None

        result = results[0]
        name = result.get("name", "")
        state = result.get("admin1", "")

        location = ", ".join(
            part for part in [name, state] if part and part != name
        )

        if not location:
            location = name

        return {
            "lat": float(result["latitude"]),
            "lon": float(result["longitude"]),
            "location": location,
            "pincode": None,
        }

    except Exception as error:
        print(f"[Open-Meteo geocoding] {error}")
        return None


# ============================================================
# GEOCODING: INDIAN PIN CODES
# ============================================================

def geocode_pincode(pincode: str):
    post_office_name = ""
    district_name = ""
    state_name = ""

    # First: retrieve post office, district and state.
    try:
        response = requests.get(
            f"https://api.postalpincode.in/pincode/{pincode}",
            timeout=8,
        )
        response.raise_for_status()

        data = response.json()

        if data and data[0].get("Status") == "Success":
            offices = data[0].get("PostOffice") or []

            if offices:
                office = offices[0]
                post_office_name = (office.get("Name") or "").strip()
                district_name = (office.get("District") or "").strip()
                state_name = (office.get("State") or "").strip()

    except Exception as error:
        print(f"[Postal lookup] {error}")

    # Second: retrieve approximate coordinates.
    latitude = None
    longitude = None
    zippo_name = ""

    try:
        response = requests.get(
            f"https://api.zippopotam.us/in/{pincode}",
            timeout=8,
        )

        if response.status_code == 200:
            data = response.json()
            places = data.get("places", [])

            if places:
                place = places[0]
                latitude = float(place["latitude"])
                longitude = float(place["longitude"])
                zippo_name = place.get("place name", "")

                if not state_name:
                    state_name = place.get("state", "")

    except Exception as error:
        print(f"[Zippopotam lookup] {error}")

    # Third: use the district's coordinates if necessary.
    if latitude is None and district_name:
        geo = geocode_openmeteo(district_name)

        if geo:
            latitude = geo["lat"]
            longitude = geo["lon"]

    if latitude is None or longitude is None:
        geo = geocode_openmeteo(pincode)

        if geo:
            latitude = geo["lat"]
            longitude = geo["lon"]

    if latitude is None or longitude is None:
        return None

    # Prefer the post office name when available.
    if post_office_name and district_name and state_name:
        location_name = (
            f"{post_office_name}, {district_name}, {state_name}"
        )
    elif post_office_name and state_name:
        location_name = f"{post_office_name}, {state_name}"
    elif district_name and state_name:
        location_name = f"{district_name}, {state_name}"
    elif zippo_name and state_name:
        location_name = f"{zippo_name}, {state_name}"
    elif zippo_name:
        location_name = zippo_name
    else:
        location_name = f"PIN {pincode}"

    return {
        "lat": latitude,
        "lon": longitude,
        "location": location_name,
        "pincode": pincode,
    }


# ============================================================
# GEOCODING: NOMINATIM FALLBACK
# ============================================================

def geocode_nominatim(place: str):
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": place,
                "format": "json",
                "limit": 1,
                "countrycodes": "in",
            },
            headers={
                "User-Agent": "SoilGPT/1.0 (educational project)"
            },
            timeout=10,
        )

        response.raise_for_status()
        results = response.json()

        if not results:
            return None

        result = results[0]
        parts = [
            part.strip()
            for part in result["display_name"].split(",")
        ]

        location_name = ", ".join(parts[:2])

        return {
            "lat": float(result["lat"]),
            "lon": float(result["lon"]),
            "location": location_name,
            "pincode": None,
        }

    except Exception as error:
        print(f"[Nominatim geocoding] {error}")
        return None


# ============================================================
# MASTER GEOCODING FUNCTION
# ============================================================

def geocode(location: str):
    location = location.strip()

    if re.fullmatch(r"\d{6}", location):
        result = geocode_pincode(location)

        if result:
            return result

    result = geocode_openmeteo(location)

    if result:
        return result

    return geocode_nominatim(location)


# ============================================================
# LIVE SOIL DATA: OPEN-METEO
# ============================================================

def fetch_openmeteo_soil(latitude: float, longitude: float):
    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "hourly": (
                    "soil_moisture_0_to_1cm,"
                    "soil_moisture_1_to_3cm,"
                    "soil_temperature_0cm,"
                    "soil_temperature_6cm"
                ),
                "forecast_days": 1,
                "timezone": "auto",
            },
            timeout=15,
        )

        response.raise_for_status()
        return response.json()

    except Exception as error:
        print(f"[Open-Meteo soil data] {error}")
        return None


def parse_openmeteo_soil(raw):
    output = {}

    if not raw or "hourly" not in raw:
        return output

    hourly = raw["hourly"]
    times = hourly.get("time", [])

    def last_valid(key):
        values = hourly.get(key, [])

        for value in reversed(values):
            if value is not None:
                return value

        return None

    output["soil_moisture_0_1cm"] = last_valid(
        "soil_moisture_0_to_1cm"
    )
    output["soil_moisture_1_3cm"] = last_valid(
        "soil_moisture_1_to_3cm"
    )
    output["soil_temperature_0cm"] = last_valid(
        "soil_temperature_0cm"
    )
    output["soil_temperature_6cm"] = last_valid(
        "soil_temperature_6cm"
    )

    if times:
        output["reading_time"] = times[-1]

    return output


# ============================================================
# API ENDPOINTS
# ============================================================

@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "SoilGPT API",
    }


# Use this endpoint to get a location name without soil analysis.
@app.get("/geocode")
def geocode_endpoint(
    location: str = Query(..., min_length=2)
):
    geo = geocode(location)

    if not geo:
        raise HTTPException(
            status_code=404,
            detail=f"Could not find location: {location}",
        )

    return {
        "location": geo["location"],
        "pincode": geo["pincode"],
        "lat": geo["lat"],
        "lon": geo["lon"],
    }


# Main soil analysis endpoint.
@app.get("/analyze")
def analyze(location: str = Query(..., min_length=2)):
    geo = geocode(location)

    if not geo:
        raise HTTPException(
            status_code=404,
            detail=f"Could not find location: {location}",
        )

    raw = fetch_openmeteo_soil(geo["lat"], geo["lon"])
    live = parse_openmeteo_soil(raw) if raw else {}

    # Extract the state from the returned location.
    state = ""

    if geo["location"] and "," in geo["location"]:
        state = geo["location"].split(",")[-1].strip()

    reference = get_soil_reference(state)

    return {
        "location": geo["location"],
        "pincode": geo["pincode"],
        "lat": geo["lat"],
        "lon": geo["lon"],
        "live": live,
        "reference": reference,
    }


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
    )