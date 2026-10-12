import os
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from rag.generator import BriefGenerator

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

# Initialize generator on startup
CHROMA_DIR = "track2_rag/chroma_db"
CHUNKS_PATH = "track2_rag/corpus/chunks.json"
BRIEFS_DIR = Path("data/briefs")

try:
    generator = BriefGenerator(CHROMA_DIR, CHUNKS_PATH)
except Exception as e:
    print(f"Warning: Could not initialize BriefGenerator on startup: {e}")
    generator = None

@app.get("/")
def read_root():
    return {"status": "online", "service": "Project Spoonbill RAG API"}

@app.get("/api/v1/briefs/{anomaly_id}")
def get_brief(anomaly_id: str):
    """
    Fetch an existing generated brief for an anomaly ID, 
    or dynamically generate it if not found on disk.
    """
    brief_path = BRIEFS_DIR / f"{anomaly_id}.json"
    
    if brief_path.exists():
        with open(brief_path, "r", encoding="utf-8") as f:
            return json.load(f)
            
    # If not pre-generated, check if it exists in mock/live anomalies to generate on-the-fly
    geojson_paths = ["contract/mock_anomalies.geojson", "data/anomalies_v1.geojson"]
    target_feature = None
    
    for path in geojson_paths:
        if Path(path).exists():
            with open(path, "r", encoding="utf-8") as f:
                geo_data = json.load(f)
                for feature in geo_data.get("features", []):
                    if feature["properties"].get("anomaly_id") == anomaly_id:
                        target_feature = feature
                        break
        if target_feature:
            break
            
    if not target_feature:
        raise HTTPException(status_code=404, detail=f"Anomaly ID {anomaly_id} not found.")
        
    if not generator:
        raise HTTPException(status_code=500, detail="BriefGenerator failed to initialize.")
        
    # Generate on the fly
    brief = generator.generate_brief(target_feature)
    
    # Save to disk cache
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    with open(brief_path, "w", encoding="utf-8") as f:
        json.dump(brief, f, ensure_ascii=False, indent=2)
        
    return brief