"""
SoilGPT Backend
- GET /analyze?location=<pincode_or_place>
- Geocodes location → coordinates (works for all of India)
- Fetches live soil moisture + temperature from Open-Meteo
- Returns JSON
"""

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

# ------------------------------------------------------------
# GEOCODING (PIN code + place name, works anywhere in India)
# ------------------------------------------------------------

def geocode_pincode_india(pincode: str):
    """Use the free Zippopotam API to get coordinates from an Indian PIN code."""
    try:
        url = f"https://api.zippopotam.us/in/{pincode}"
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            data = r.json()
            place = data["places"][0]
            return {
                "lat": float(place["latitude"]),
                "lon": float(place["longitude"]),
                "location": f"{place['place name']}, {place['state']}",
                "pincode": pincode,
            }
    except Exception as e:
        print(f"Zippopotam error: {e}")
    return None


def geocode_place_nominatim(place: str):
    """Use Nominatim (OpenStreetMap) to geocode a place name anywhere in India."""
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": place,
            "format": "json",
            "limit": 1,
            "countrycodes": "in",
        }
        headers = {"User-Agent": "SoilGPT/1.0 (educational project)"}
        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data:
                result = data[0]
                display = result["display_name"]
                parts = [p.strip() for p in display.split(",")]
                location = parts[0] if parts else place
                if len(parts) >= 2:
                    location = f"{parts[0]}, {parts[-1]}"
                return {
                    "lat": float(result["lat"]),
                    "lon": float(result["lon"]),
                    "location": location,
                    "pincode": None,
                }
    except Exception as e:
        print(f"Nominatim error: {e}")
    return None


def geocode(location: str):
    """Try PIN code first, then place name."""
    location = location.strip()
    if re.fullmatch(r"\d{6}", location):
        result = geocode_pincode_india(location)
        if result:
            return result
    result = geocode_place_nominatim(location)
    if result:
        return result
    return None


# ------------------------------------------------------------
# LIVE SOIL DATA (Open-Meteo — free, no API key, works globally)
# ------------------------------------------------------------

def fetch_openmeteo(lat: float, lon: float):
    """
    Fetch live soil moisture + soil temperature from Open-Meteo.
    Docs: https://open-meteo.com/en/docs
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "soil_moisture_0_to_1cm,soil_moisture_1_to_3cm,soil_temperature_0cm,soil_temperature_6cm",
        "forecast_days": 1,
        "timezone": "auto",
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        print(f"[Open-Meteo] status={r.status_code}")
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[Open-Meteo] error: {e}")
        return None


def parse_openmeteo(raw):
    """Extract the most recent soil moisture + temperature readings."""
    out = {}

    if not raw or "hourly" not in raw:
        return out

    hourly = raw["hourly"]
    times = hourly.get("time", [])

    def last_valid(key):
        vals = hourly.get(key, [])
        # Return most recent non-null value
        for v in reversed(vals):
            if v is not None:
                return v
        return None

    out["soil_moisture_0_1cm"] = last_valid("soil_moisture_0_to_1cm")
    out["soil_moisture_1_3cm"] = last_valid("soil_moisture_1_to_3cm")
    out["soil_temperature_0cm"] = last_valid("soil_temperature_0cm")
    out["soil_temperature_6cm"] = last_valid("soil_temperature_6cm")

    if times:
        out["reading_time"] = times[-1]

    return out


# ------------------------------------------------------------
# LOCAL SOIL REFERENCE DATA (region-based, from ICAR / Soil Health Card)
# Used to supplement live data with chemical properties.
# ------------------------------------------------------------

# Reference: ICAR-NBSS&LUP soil surveys + Government of India Soil Health Card
# Keyed by Indian state. Falls back to "default" if state not found.
SOIL_REFERENCE = {
    "gujarat": {
        "soil_type": "Deep Black Cotton Soil (Vertisols)",
        "ph_range": "7.1 – 8.9 (neutral to slightly alkaline)",
        "organic_carbon": "Low to medium (0.08% – 0.86%)",
        "nitrogen": "Low to medium (125 – 323 kg/ha)",
        "phosphorus": "Medium to high (irrigated), Low (rainfed)",
        "potassium": "High to very high",
        "deficiencies": "Zinc (Zn), Sulphur (S)",
        "recommendation": "Add organic matter (FYM, compost). Supplement with Zinc and Sulphur. Maintain balanced NPK."
    },
    "maharashtra": {
        "soil_type": "Black cotton soil + Laterite (Konkan)",
        "ph_range": "6.5 – 8.2 (neutral to slightly alkaline)",
        "organic_carbon": "Low to medium (0.2% – 0.75%)",
        "nitrogen": "Low to medium",
        "phosphorus": "Low to medium",
        "potassium": "Medium to high",
        "deficiencies": "Zinc, Boron, Iron (in laterite)",
        "recommendation": "Use organic compost. Foliar spray of micronutrients. Balanced fertilizer."
    },
    "punjab": {
        "soil_type": "Alluvial soil (Indo-Gangetic plain)",
        "ph_range": "7.5 – 8.5 (slightly alkaline)",
        "organic_carbon": "Low (0.15% – 0.5%)",
        "nitrogen": "Medium",
        "phosphorus": "Medium to high",
        "potassium": "Medium",
        "deficiencies": "Zinc, Iron, Manganese",
        "recommendation": "Green manuring recommended. Add Zinc sulphate. Avoid over-irrigation."
    },
    "uttarakhand": {
        "soil_type": "Brown forest soil + Podzolic (hills)",
        "ph_range": "5.5 – 7.0 (slightly acidic to neutral)",
        "organic_carbon": "Medium to high (0.5% – 1.5%)",
        "nitrogen": "Medium to high",
        "phosphorus": "Low to medium",
        "potassium": "Medium",
        "deficiencies": "Phosphorus, Boron",
        "recommendation": "Add lime if acidic. Supplement phosphorus. Terrace farming friendly."
    },
    "default": {
        "soil_type": "Mixed — varies by region",
        "ph_range": "6.0 – 8.0 (typical Indian range)",
        "organic_carbon": "Low to medium",
        "nitrogen": "Low to medium",
        "phosphorus": "Low to medium",
        "potassium": "Medium",
        "deficiencies": "Micronutrients (Zn, B, Fe) commonly deficient",
        "recommendation": "Conduct a soil test for precise recommendations. Add organic matter regularly."
    }
}


def get_soil_reference(state: str):
    """Return reference soil data for the given state."""
    if not state:
        return SOIL_REFERENCE["default"]
    state_lower = state.lower()
    for key in SOIL_REFERENCE:
        if key in state_lower or state_lower in key:
            return SOIL_REFERENCE[key]
    return SOIL_REFERENCE["default"]


# ------------------------------------------------------------
# ENDPOINTS
# ------------------------------------------------------------

@app.get("/")
def root():
    return {"status": "ok", "service": "SoilGPT API"}


@app.get("/debug/soilgrids")
def debug_soilgrids(lat: float = 20.0, lon: float = 73.78):
    """Debug: raw Open-Meteo response (name kept for compatibility)."""
    return fetch_openmeteo(lat, lon)


@app.get("/analyze")
def analyze(location: str = Query(..., min_length=2)):
    # 1. Geocode the input
    geo = geocode(location)
    if not geo:
        raise HTTPException(
            status_code=404,
            detail=f"Could not find location: {location}",
        )

    # 2. Fetch live soil data from Open-Meteo
    raw = fetch_openmeteo(geo["lat"], geo["lon"])
    if not raw:
        raise HTTPException(
            status_code=502,
            detail="Could not fetch live soil data",
        )

    live = parse_openmeteo(raw)

    # 3. Get reference chemical data based on state
    state = geo["location"].split(",")[-1].strip() if "," in geo["location"] else ""
    reference = get_soil_reference(state)

    return {
        "location": geo["location"],
        "pincode": geo["pincode"],
        "lat": geo["lat"],
        "lon": geo["lon"],
        "live": live,
        "reference": reference,
    }


# ------------------------------------------------------------
# RUN
# ------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)