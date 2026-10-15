"""
SoilGPT Backend
- GET /analyze?location=<pincode_or_city>       → live soil data + ICAR reference
- POST /ask                                     → soil Q&A (RAG)
- POST /recommend/crop                          → crop recommendation (ML)
- POST /recommend/fertilizer                    → fertilizer recommendation (ML)
"""

import os
import re
import pickle
import numpy as np
import requests
import torch
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="SoilGPT API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# AI MODELS — load once at startup
# ============================================================

print("[AI] Loading models...")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---- RAG index ----
RAG_PATH = os.path.join(BASE_DIR, "rag_index.pt")
if os.path.exists(RAG_PATH):
    from sentence_transformers import SentenceTransformer
    from transformers import pipeline

    rag_data = torch.load(RAG_PATH, map_location="cpu")
    rag_documents = rag_data["documents"]
    rag_embeddings = rag_data["document_embeddings"]
    rag_soil_knowledge = rag_data["soil_knowledge"]

    embedding_model = SentenceTransformer(
        "sentence-transformers/all-MiniLM-L6-v2",
        device="cpu"
    )
    answer_generator = pipeline(
        "text2text-generation",
        model="google/flan-t5-base",
        device=-1,
        max_new_tokens=200,
    )
    RAG_READY = True
    print(f"[AI] RAG loaded — {len(rag_documents)} documents indexed")
else:
    RAG_READY = False
    print(f"[AI] WARNING: {RAG_PATH} not found — /ask will fail")

# ---- Crop model ----
CROP_PATH = os.path.join(BASE_DIR, "crop_model.pkl")
if os.path.exists(CROP_PATH):
    with open(CROP_PATH, "rb") as f:
        crop_data = pickle.load(f)
        crop_model = crop_data["model"]
        crop_label_encoder = crop_data["label_encoder"]
    CROP_READY = True
    print("[AI] Crop model loaded")
else:
    CROP_READY = False
    print(f"[AI] WARNING: {CROP_PATH} not found — /recommend/crop will fail")

# ---- Fertilizer model ----
FERT_PATH = os.path.join(BASE_DIR, "fert_model.pkl")
if os.path.exists(FERT_PATH):
    with open(FERT_PATH, "rb") as f:
        fert_data = pickle.load(f)
        fert_model = fert_data["model"]
        fert_label_encoder = fert_data["label_encoder"]
    FERT_READY = True
    print("[AI] Fertilizer model loaded")
else:
    FERT_READY = False
    print(f"[AI] WARNING: {FERT_PATH} not found — /recommend/fertilizer will fail")

print("[AI] Startup complete")


# ============================================================
# GEOCODING
# ============================================================

def geocode_openmeteo(place: str):
    """Use Open-Meteo geocoding (free, no key)."""
    try:
        url = "https://geocoding-api.open-meteo.com/v1/search"
        params = {
            "name": place,
            "count": 1,
            "language": "en",
            "format": "json",
            "countryCode": "IN",
        }
        r = requests.get(url, params=params, timeout=8)
        if r.status_code == 200:
            data = r.json()
            results = data.get("results", [])
            if results:
                res = results[0]
                name = res.get("name", "")
                admin1 = res.get("admin1", "")
                location = f"{name}, {admin1}" if admin1 else name
                return {
                    "lat": float(res["latitude"]),
                    "lon": float(res["longitude"]),
                    "location": location,
                    "pincode": None,
                }
    except Exception as e:
        print(f"[Open-Meteo geocode] {e}")
    return None


def geocode_pincode(pincode: str):
    """Multi-layer PIN code lookup."""
    district = None
    state = None

    try:
        r = requests.get(
            f"https://api.postalpincode.in/pincode/{pincode}", timeout=8
        )
        if r.status_code == 200:
            data = r.json()
            if data and data[0].get("Status") == "Success":
                po = data[0].get("PostOffice", [])
                if po:
                    district = (po[0].get("District") or "").strip()
                    state = (po[0].get("State") or "").strip()
    except Exception as e:
        print(f"[postalpincode] {e}")

    lat = lon = None
    try:
        r = requests.get(f"https://api.zippopotam.us/in/{pincode}", timeout=8)
        if r.status_code == 200:
            place = r.json()["places"][0]
            lat = float(place["latitude"])
            lon = float(place["longitude"])
    except Exception as e:
        print(f"[Zippopotam] {e}")

    if lat is None and district:
        geo = geocode_openmeteo(district)
        if geo:
            lat = geo["lat"]
            lon = geo["lon"]

    if lat is None or lon is None:
        return None

    if district and state:
        location = f"{district}, {state}"
    elif district:
        location = district
    else:
        location = f"PIN {pincode}"

    return {
        "lat": lat,
        "lon": lon,
        "location": location,
        "pincode": pincode,
    }


def geocode(location: str):
    """Master geocoder."""
    location = location.strip()
    if re.fullmatch(r"\d{6}", location):
        result = geocode_pincode(location)
        if result:
            return result
    return geocode_openmeteo(location)


# ============================================================
# LIVE SOIL DATA (Open-Meteo)
# ============================================================

def fetch_live_soil(lat: float, lon: float):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "soil_moisture_0_to_1cm,soil_temperature_0cm,soil_temperature_6cm",
        "forecast_days": 1,
        "timezone": "auto",
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            hourly = r.json().get("hourly", {})

            def last(key):
                vals = hourly.get(key, [])
                for v in reversed(vals):
                    if v is not None:
                        return v
                return None

            return {
                "soil_moisture": last("soil_moisture_0_to_1cm"),
                "soil_temp_0cm": last("soil_temperature_0cm"),
                "soil_temp_6cm": last("soil_temperature_6cm"),
            }
    except Exception as e:
        print(f"[Open-Meteo soil] {e}")
    return {}


# ============================================================
# REGIONAL SOIL REFERENCE (ICAR)
# ============================================================

REFERENCE = {
    "gujarat": {
        "soil_type": "Deep Black Cotton Soil (Vertisols)",
        "ph_range": "7.1 – 8.9",
        "nitrogen": "Low to medium",
        "phosphorus": "Medium (irrigated), Low (rainfed)",
        "potassium": "High to very high",
        "deficiencies": "Zinc, Sulphur",
        "recommendation": "Add organic matter. Supplement Zinc & Sulphur.",
    },
    "maharashtra": {
        "soil_type": "Black cotton + Laterite",
        "ph_range": "6.5 – 8.2",
        "nitrogen": "Low to medium",
        "phosphorus": "Low to medium",
        "potassium": "Medium to high",
        "deficiencies": "Zinc, Boron, Iron",
        "recommendation": "Use organic compost. Foliar micronutrient spray.",
    },
    "punjab": {
        "soil_type": "Alluvial soil",
        "ph_range": "7.5 – 8.5",
        "nitrogen": "Medium",
        "phosphorus": "Medium to high",
        "potassium": "Medium",
        "deficiencies": "Zinc, Iron, Manganese",
        "recommendation": "Green manuring. Add Zinc sulphate.",
    },
    "uttarakhand": {
        "soil_type": "Brown forest soil",
        "ph_range": "5.5 – 7.0",
        "nitrogen": "Medium to high",
        "phosphorus": "Low to medium",
        "potassium": "Medium",
        "deficiencies": "Phosphorus, Boron",
        "recommendation": "Add lime if acidic. Supplement phosphorus.",
    },
    "uttar pradesh": {
        "soil_type": "Alluvial soil",
        "ph_range": "7.0 – 8.5",
        "nitrogen": "Low to medium",
        "phosphorus": "Low to medium",
        "potassium": "Medium",
        "deficiencies": "Zinc, Sulphur",
        "recommendation": "Green manuring. Balanced NPK.",
    },
    "karnataka": {
        "soil_type": "Red + Black soil",
        "ph_range": "6.0 – 8.0",
        "nitrogen": "Low to medium",
        "phosphorus": "Low to medium",
        "potassium": "Medium to high",
        "deficiencies": "Zinc, Boron",
        "recommendation": "Add organic manure. Crop rotation.",
    },
    "tamil nadu": {
        "soil_type": "Red loam + Coastal alluvial",
        "ph_range": "6.5 – 8.5",
        "nitrogen": "Low to medium",
        "phosphorus": "Low to medium",
        "potassium": "Medium to high",
        "deficiencies": "Zinc, Iron",
        "recommendation": "Balanced fertilizer. Green manure.",
    },
    "delhi": {
        "soil_type": "Alluvial soil",
        "ph_range": "7.0 – 8.5",
        "nitrogen": "Low to medium",
        "phosphorus": "Low to medium",
        "potassium": "Medium",
        "deficiencies": "Organic matter, Zinc",
        "recommendation": "Compost heavily. Regular soil testing.",
    },
    "rajasthan": {
        "soil_type": "Sandy + Arid soil",
        "ph_range": "7.5 – 9.0",
        "nitrogen": "Low",
        "phosphorus": "Low",
        "potassium": "Medium to high",
        "deficiencies": "Organic matter, Zinc",
        "recommendation": "Heavy organic matter. Drip irrigation.",
    },
    "west bengal": {
        "soil_type": "Alluvial + Deltaic",
        "ph_range": "5.5 – 7.5",
        "nitrogen": "Medium",
        "phosphorus": "Low to medium",
        "potassium": "Medium",
        "deficiencies": "Zinc, Boron",
        "recommendation": "Balanced fertilizer. Organic matter.",
    },
    "kerala": {
        "soil_type": "Laterite + Coastal",
        "ph_range": "5.0 – 6.5",
        "nitrogen": "Medium",
        "phosphorus": "Low",
        "potassium": "Medium",
        "deficiencies": "Phosphorus, Calcium, Magnesium",
        "recommendation": "Apply lime. Rock phosphate for P.",
    },
    "default": {
        "soil_type": "Mixed — varies by region",
        "ph_range": "6.0 – 8.0",
        "nitrogen": "Low to medium",
        "phosphorus": "Low to medium",
        "potassium": "Medium",
        "deficiencies": "Micronutrients (Zn, B, Fe)",
        "recommendation": "Soil test for precise recommendations.",
    },
}


def get_reference(state: str):
    if not state:
        return REFERENCE["default"]
    state_lower = state.lower().strip()
    for key in REFERENCE:
        if key in state_lower or state_lower in key:
            return REFERENCE[key]
    return REFERENCE["default"]


# ============================================================
# REQUEST MODELS
# ============================================================

class SoilQuestion(BaseModel):
    question: str


class CropRequest(BaseModel):
    n: float
    p: float
    k: float
    temperature: float
    humidity: float
    ph: float
    rainfall: float


class FertilizerRequest(BaseModel):
    n_level: int
    p_level: int
    k_level: int


# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "SoilGPT API",
        "rag_ready": RAG_READY,
        "crop_ready": CROP_READY,
        "fert_ready": FERT_READY,
    }


@app.get("/analyze")
def analyze(location: str = Query(..., min_length=2)):
    geo = geocode(location)
    if not geo:
        raise HTTPException(404, f"Could not find location: {location}")

    live = fetch_live_soil(geo["lat"], geo["lon"])

    state = ""
    if geo["location"] and "," in geo["location"]:
        state = geo["location"].split(",")[-1].strip()
    reference = get_reference(state)

    return {
        "location": geo["location"],
        "pincode": geo["pincode"],
        "lat": geo["lat"],
        "lon": geo["lon"],
        "live": live,
        "reference": reference,
    }


@app.post("/ask")
def ask_soil(q: SoilQuestion):
    if not RAG_READY:
        raise HTTPException(503, "RAG model not loaded on server")

    q_emb = embedding_model.encode(
        q.question, convert_to_tensor=True, normalize_embeddings=True
    )
    scores = rag_embeddings @ q_emb
    top_idx = torch.topk(scores, k=3).indices.tolist()

    context = "\n".join([rag_documents[i] for i in top_idx])
    sources = [rag_soil_knowledge[i]["topic"] for i in top_idx]

    prompt = (
        f"Answer the soil question using the context.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {q.question}\n"
        f"Answer:"
    )
    result = answer_generator(prompt)
    answer = result[0]["generated_text"].strip()

    return {"answer": answer, "sources": sources}


@app.post("/recommend/crop")
def recommend_crop_endpoint(req: CropRequest):
    if not CROP_READY:
        raise HTTPException(503, "Crop model not loaded on server")

    features = np.array(
        [[req.n, req.p, req.k, req.temperature, req.humidity, req.ph, req.rainfall]]
    )
    probs = crop_model.predict_proba(features)[0]
    top_idx = np.argsort(probs)[::-1][:3]

    crops = [
        {
            "crop": crop_label_encoder.inverse_transform([i])[0],
            "confidence": round(float(probs[i]), 4),
        }
        for i in top_idx
    ]
    return {"recommended_crops": crops}


@app.post("/recommend/fertilizer")
def recommend_fertilizer_endpoint(req: FertilizerRequest):
    if not FERT_READY:
        raise HTTPException(503, "Fertilizer model not loaded on server")

    features = np.array([[req.n_level, req.p_level, req.k_level]])
    prediction = fert_model.predict(features)[0]
    fertilizer = fert_label_encoder.inverse_transform([prediction])[0]
    return {"recommended_fertilizer": fertilizer}


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)