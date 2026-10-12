import json
import os
import re
from pathlib import Path
import google.generativeai as genai
from .retriever import HybridRetriever

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
        self.model = genai.GenerativeModel("gemini-3.8-flash")

    def _apply_pdpo_redaction(self, text: str) -> tuple[str, int]:
        """
        Applies basic regex checks for HKIDs, phone numbers, and emails 
        to ensure compliance with personal data privacy regulations.
        """
        redaction_count = 0
        
        # HKID pattern (e.g., A123456(7) or similar variations)
        hkid_pattern = r'\b[A-Z]{1,2}[0-9]{6}\([0-9A-Z]\)\b'
        # Email pattern
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        # Phone pattern (Hong Kong 8-digit or international)
        phone_pattern = r'\b(?:\+852[-.\s]?)?[2356789]\d{3}[-.\s]?\d{4}\b'
        
        patterns = [hkid_pattern, email_pattern, phone_pattern]
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            if matches:
                redaction_count += len(matches)
                text = re.sub(pattern, "[REDACTED]", text)
                
        return text, redaction_count

    def generate_brief(self, anomaly: dict) -> dict:
        props = anomaly["properties"]
        anomaly_id = props["anomaly_id"]
        zone_hint = props.get("zone_hint", "WBA")
        
        query = f"Development, wetland filling, fishpond conversion in {zone_hint} area assessment requirements"
        chunks = self.retriever.retrieve(query, k=3)
        
        if not chunks:
            return self._build_abstain_brief(anomaly_id, "No relevant statutory clauses retrieved above threshold.")
            
        context_text = "\n\n".join([f"Chunk ID: {c['chunk_id']}\nText: {c['text']}" for c in chunks])
        retrieved_chunk_ids = {c["chunk_id"] for c in chunks}
        retrieved_chunk_texts = {c["chunk_id"]: c["text"] for c in chunks}
        
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
- model: "gemini-3.8-flash"
- generated_at: "2026-10-11T00:00:00Z"
- en: object with keys title, summary, evidence (array of strings), statutory_basis (array of strings), recommended_action, limitations
- zh_hant: same keys as en
- citations: array of objects with chunk_id, document_title, page_number, verbatim_quote
- human_review_required: true
- abstain_reason: null
- redaction_log: object with items_removed (integer), types (array of strings)

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
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
                
            brief_data = json.loads(raw_text.strip())
            
            # --- DAY 5 PROGRAMMATIC GUARDRAIL: CITE-OR-ABSTAIN CHECK ---
            citations = brief_data.get("citations", [])
            valid_citations = []
            
            for cit in citations:
                c_id = cit.get("chunk_id")
                quote = cit.get("verbatim_quote", "")
                
                # Check if cited chunk ID exists in retrieved set
                if c_id in retrieved_chunk_ids:
                    # Check if quote reasonably exists in the chunk text
                    parent_text = retrieved_chunk_texts[c_id]
                    # Normalize whitespace for matching check
                    if quote.strip()[:20] in parent_text: 
                        valid_citations.append(cit)
            
            if not valid_citations and citations:
                # If model hallucinated citations that failed verification, force abstain
                return self._build_abstain_brief(anomaly_id, "Programmatic guardrail failed: Citations could not be verified against retrieved chunks.")
                
            brief_data["citations"] = valid_citations
            if not valid_citations:
                brief_data["status"] = "abstained_human_review"
                brief_data["abstain_reason"] = "No verifiable statutory citations survived post-generation filtering."

            # --- DAY 6 PDPO REDACTION PASS ---
            total_redactions = 0
            # Scan summary and evidence strings for privacy compliance
            for lang_key in ["en", "zh_hant"]:
                if lang_key in brief_data:
                    section = brief_data[lang_key]
                    if "summary" in section:
                        cleaned, count = self._apply_pdpo_redaction(section["summary"])
                        section["summary"] = cleaned
                        total_redactions += count
                    if "evidence" in section and isinstance(section["evidence"], list):
                        new_ev = []
                        for ev in section["evidence"]:
                            cleaned, count = self._apply_pdpo_redaction(ev)
                            new_ev.append(cleaned)
                            total_redactions += count
                        section["evidence"] = new_ev

            brief_data["redaction_log"] = {
                "items_removed": total_redactions,
                "types": ["HKID", "Email", "Phone"] if total_redactions > 0 else []
            }

            return brief_data
            
        except Exception as e:
            return self._build_abstain_brief(anomaly_id, f"Generation or parsing error: {str(e)}")

    def _build_abstain_brief(self, anomaly_id: str, reason: str) -> dict:
        return {
            "schema_version": "1.0",
            "anomaly_id": anomaly_id,
            "status": "abstained_human_review",
            "model": "gemini-3.8-flash",
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