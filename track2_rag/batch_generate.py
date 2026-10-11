import json
import os
from pathlib import Path
from rag.generator import BriefGenerator
import jsonschema

def run_batch():
    geojson_path = "contract/mock_anomalies.geojson"
    if not Path(geojson_path).exists():
        geojson_path = "data/anomalies_v1.geojson"
        
    if not Path(geojson_path).exists():
        print(f"Error: Anomaly GeoJSON not found at {geojson_path}.")
        return

    with open(geojson_path, "r", encoding="utf-8") as f:
        geojson_data = json.load(f)

    generator = BriefGenerator("track2_rag/chroma_db", "track2_rag/corpus/chunks.json")
    schema_path = "contract/brief.schema.json"
    
    with open(schema_path, "r", encoding="utf-8") as f:
        brief_schema = json.load(f)

    out_dir = Path("data/briefs")
    out_dir.mkdir(parents=True, exist_ok=True)

    for feature in geojson_data.get("features", []):
        props = feature["properties"]
        anomaly_id = props["anomaly_id"]
        print(f"Generating brief for {anomaly_id}...")
        
        brief = generator.generate_brief(feature)
        
        out_path = out_dir / f"{anomaly_id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(brief, f, ensure_ascii=False, indent=2)
            
        try:
            jsonschema.validate(brief, brief_schema)
            print(f"SUCCESS: {anomaly_id}.json generated and validated!")
        except Exception as e:
            print(f"WARNING: {anomaly_id}.json failed schema validation: {e}")

if __name__ == "__main__":
    run_batch() 