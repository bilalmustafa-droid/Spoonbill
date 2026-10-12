import json
import os
from pathlib import Path
import google.generativeai as genai
from rag.retriever import HybridRetriever

class BriefGenerator:
    def __init__(self, chroma_dir: str, chunks_path: str):
        self.retriever = HybridRetriever(chunks_path, chroma_dir)
        
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            env_path = Path("track2_rag/.env")
            if env_path.exists():
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("GEMINI_API_KEY="):
                            api_key = line.split("=", 1)[1].strip()
                            break
                            
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set in .env")
            
        genai.configure(api_key=api_key)
        # Using gemini-1.5-flash-latest for robust API alias matching
        self.model = genai.GenerativeModel("gemini-3-flash")

    def generate_brief(self, anomaly: dict) -> dict:
        props = anomaly["properties"]
        anomaly_id = props["anomaly_id"]
        zone_hint = props.get("zone_hint", "WBA")
        
        query = f"Development, wetland filling, fishpond conversion in {zone_hint} area assessment requirements"
        chunks = self.retriever.retrieve(query, k=3)
        
        if not chunks:
            return self._build_abstain_brief(anomaly_id, "No relevant statutory clauses retrieved above threshold.")
            
        context_text = "\n\n".join([f"Chunk ID: {c['chunk_id']}\nText: {c['text']}" for c in chunks])
        
        prompt = f"""
You are an expert environmental legal assistant for Project Spoonbill, monitoring Hong Kong's Deep Bay wetland conservation area.
Generate a preliminary enforcement brief JSON object adhering strictly to the schema (English only).

Anomaly Details:
- ID: {anomaly_id}
- Affected Area: {props['area_ha']} ha
- Radar Backscatter Delta: {props['delta_vv_db']} dB
- NDWI Delta: {props['delta_ndwi']}
- Zone Hint: {zone_hint}
- First Detection: {props['first_detection_date']}

Retrieved Statutory Context Chunks:
{context_text}

JSON Schema structure requirements:
- schema_version: "1.0"
- anomaly_id: "{anomaly_id}"
- status: "cited"
- model: "gemini-1.5-flash-latest"
- generated_at: "2026-10-11T00:00:00Z"
- en: object with keys title, summary, evidence (array of strings), statutory_basis (array of strings), recommended_action, limitations
- zh_hant: same keys as en (can contain English text)
- citations: array of objects with chunk_id, document_title, page_number, verbatim_quote
- human_review_required: true
- abstain_reason: null
- redaction_log: object with items_removed (0), types (empty array)

Instructions:
1. Return ONLY valid JSON matching the schema.
2. Use ONLY the provided statutory chunks for citations. Include verbatim quotes (maximum 40 words).
3. Maintain a neutral screening tone.
"""
        
        try:
            response = self.model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            raw_text = response.text.strip()
            brief_data = json.loads(raw_text)
            return brief_data
        except Exception as e:
            return self._build_abstain_brief(anomaly_id, f"Generation or parsing error: {str(e)}")

    def _build_abstain_brief(self, anomaly_id: str, reason: str) -> dict:
        return {
            "schema_version": "1.0",
            "anomaly_id": anomaly_id,
            "status": "abstained_human_review",
            "model": "gemini-1.5-flash-latest",
            "generated_at": "2026-10-11T00:00:00Z",
            "en": {
                "title": "Preliminary Observation: Requires Manual Review",
                "summary": "Automatic statutory matching inconclusive.",
                "evidence": [],
                "statutory_basis": [],
                "recommended_action": "Refer for manual officer inspection.",
                "limitations": "Satellite-derived indicator for screening purposes only."
            },
            "zh_hant": {
                "title": "Preliminary Observation: Requires Manual Review",
                "summary": "Automatic statutory matching inconclusive.",
                "evidence": [],
                "statutory_basis": [],
                "recommended_action": "Refer for manual officer inspection.",
                "limitations": "Satellite-derived indicator for screening purposes only."
            },
            "citations": [],
            "human_review_required": True,
            "abstain_reason": reason,
            "redaction_log": {"items_removed": 0, "types": []}
        }