import os
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from track2_rag.api import anomalies_store

app = FastAPI(
    title="Project Spoonbill - Track 2 RAG & Enforcement Brief API",
    version="1.0.0"
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CHROMA_DIR = "track2_rag/chroma_db"
CHUNKS_PATH = "track2_rag/corpus/chunks.json"
BRIEFS_DIR = Path("data/briefs")
OFFLINE_MODE = os.getenv("SPOONBILL_OFFLINE") == "1"

# Initialize generator on startup. The import itself (not just construction)
# is wrapped here: a missing RAG dependency (e.g. google.generativeai not
# installed) must degrade the brief endpoints to a clear 503, not crash the
# whole process before any route registers.
generator = None
generator_init_error: str | None = None

if OFFLINE_MODE:
    generator_init_error = "SPOONBILL_OFFLINE=1: live generation disabled"
else:
    try:
        from track2_rag.rag.generator import BriefGenerator
        generator = BriefGenerator(CHROMA_DIR, CHUNKS_PATH)
    except Exception as e:
        print(f"Warning: Could not initialize BriefGenerator on startup: {e}")
        generator_init_error = str(e)

@app.get("/")
def read_root():
    return {"status": "online", "service": "Project Spoonbill RAG API"}


def fetch_or_generate_brief(anomaly_id: str) -> dict:
    """
    Fetch an existing generated brief for an anomaly ID, or dynamically
    generate it if not found on disk. Shared by the legacy GET route and the
    new POST /api/brief route so there is exactly one implementation.
    """
    brief_path = BRIEFS_DIR / f"{anomaly_id}.json"

    if brief_path.exists():
        with open(brief_path, "r", encoding="utf-8") as f:
            return json.load(f)

    try:
        feature_collection = anomalies_store.load_anomalies()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Anomaly data source not available.")
    target_feature = anomalies_store.get_feature_by_id(feature_collection, anomaly_id)

    if not target_feature:
        raise HTTPException(status_code=404, detail=f"Anomaly ID {anomaly_id} not found.")

    if OFFLINE_MODE:
        raise HTTPException(
            status_code=503,
            detail=f"Offline mode active (SPOONBILL_OFFLINE=1): no cached brief found for {anomaly_id}, live generation disabled.",
        )

    if not generator:
        raise HTTPException(status_code=503, detail=f"BriefGenerator unavailable: {generator_init_error}")

    brief = generator.generate_brief(target_feature)

    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    with open(brief_path, "w", encoding="utf-8") as f:
        json.dump(brief, f, ensure_ascii=False, indent=2)

    return brief


@app.get("/api/v1/briefs/{anomaly_id}")
def get_brief(anomaly_id: str):
    return fetch_or_generate_brief(anomaly_id)


from track2_rag.api.routes import router as api_router
app.include_router(api_router)