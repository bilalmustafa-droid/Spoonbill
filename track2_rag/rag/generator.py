import json
import os
from pathlib import Path
import google.generativeai as genai
from track2_rag.rag.retriever import HybridRetriever

class BriefGenerator:
    def __init__(self, chroma_dir: str, chunks_path: str):
        self.retriever = HybridRetriever(chunks_path, chroma_dir)
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set in .env")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-1.5-pro")

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
Generate a preliminary enforcement brief JSON object adhering strictly to the required schema (English only).

Anomaly Details:
- ID: {anomaly_id}
- Affected Area: {props['area_ha']} ha
- Radar Backscatter Delta: {props['delta_vv_db']} dB
- NDWI Delta: {props['delta_ndwi']}
- Zone Hint: {zone_hint}
- First Detection: {props['first_detection_date']}

Retrieved Statutory Context Chunks:
{context_text}

Instructions:
1. Provide output in English only (leave zh_hant fields with basic English fallback matching structure).
2. Use ONLY the provided statutory chunks for citations. 
3. Include verbatim quotes (maximum 40 words) from the chunks in the citations array.
4. Maintain a neutral tone: use terms like "possible", "preliminary observation", never state a definitive legal violation.
5. Return ONLY valid JSON matching the brief schema structure.
"""
        
        try:
            response = self.model.generate_content(prompt)
            raw_text = response.text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
                
            brief_data = json.loads(raw_text.strip())
            return brief_data
        except Exception as e:
            return self._build_abstain_brief(anomaly_id, f"Generation or parsing error: {str(e)}")

    def _build_abstain_brief(self, anomaly_id: str, reason: str) -> dict:
        return {
            "schema_version": "1.0",
            "anomaly_id": anomaly_id,
            "status": "abstained_human_review",
            "model": "gemini-1.5-pro",
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