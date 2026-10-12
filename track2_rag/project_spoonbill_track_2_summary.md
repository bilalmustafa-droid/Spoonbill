# Project Spoonbill - Track 2 (GenAI & RAG Backend) Comprehensive Summary

This document serves as the master technical record for Track 2 of **Project Spoonbill**, detailing the architectural decisions, pipeline implementation, troubleshooting milestones, current operational status, and roadmap items.

---

## 1. Executive Summary & Core Intent
Project Spoonbill is an automated wetland anomaly monitoring and statutory enforcement brief generation system tailored for Hong Kong's Deep Bay area (covering Wetland Conservation Areas [WCA] and Wetland Buffer Areas [WBA]). 

Track 2 focuses on building a robust, RAG-powered backend that retrieves relevant statutory clauses (e.g., TPB PG-No. 12C), queries the Gemini API under strict schema constraints, and delivers bilingual (English and Traditional Chinese) enforcement briefs via a FastAPI service for frontend integration.

---

## 2. Architectural Decisions & Tech Stack

* **Language & Runtime:** Python 3.14 environment.
* **Vector Database & Persistence:** ChromaDB (`track2_rag/chroma_db`) persisting 231 pre-chunked statutory text segments (`chunks.json`).
* **Hybrid Retrieval Pipeline:** 
  * Dense vector embeddings via `BAAI/bge-m3` for semantic query matching.
  * Sparse keyword indexing via `BM25` to capture exact statutory section numbers and technical terms.
* **Generation Engine:** Google Gemini API (`gemini-3.8-flash`) leveraging system prompts with strict JSON schema enforcement (`response_mime_type="application/json"`).
* **API Service:** FastAPI framework configured with CORS middleware and dynamic on-the-fly brief generation fallback.
* **Data Contracts:** Strict adherence to `contract/brief.schema.json` ensuring mandatory fields, citations, and dual-language output (`en` and `zh_hant`).

---

## 3. Key Work Done & Troubleshooting Milestones

### A. Ingestion & Retriever Setup
* Ingested statutory documents into 231 structured chunks.
* Configured `HybridRetriever` in `track2_rag/rag/retriever.py` to combine semantic vector search with keyword scoring.

### B. Brief Generator & Model Transitions
* Implemented `BriefGenerator` in `track2_rag/rag/generator.py` with programmatic abstain logic (`_build_abstain_brief`) to handle low-confidence retrievals or parsing faults gracefully.
* Handled legacy model deprecations (`google-generativeai` SDK migration steps from `gemini-1.5-pro` through `gemini-2.5-flash` to the current production-ready `gemini-3.8-flash`).
* Resolved local network routing and API geographic restriction issues (`400 User location is not supported`) by verifying direct network / mobile hotspot routing.

### C. Test Dataset & API Service
* Expanded mock anomaly test coverage in `contract/mock_anomalies.geojson` to support multiple concurrent site polygons (`DB-0001`, `DB-0002`, `DB-0003`).
* Built a FastAPI backend service (`track2_rag/main.py`) exposing `/api/v1/briefs/{anomaly_id}` which checks local disk cache (`data/briefs/`) and triggers dynamic RAG generation on-the-fly for new anomalies.

---

## 4. Current Status

* **Backend Pipeline:** Fully functional, tested, and producing valid schema-compliant cited briefs (`status: "cited"`).
* **API Service:** Operational locally via Uvicorn (`uvicorn track2_rag.main:app --reload --port 8000`).
* **Environment Configuration:** Secure credential management via `.env` storing `GEMINI_API_KEY`.

---

## 5. Future Action Items & Roadmap

* [ ] **Expanded Batch Validation:** Run batch generation across a larger set of synthesized multi-zone anomalies to stress-test retriever thresholds.
* [ ] **Frontend Integration:** Coordinate with the frontend team (Track 3) to verify live HTTP response handling from `/api/v1/briefs/{anomaly_id}` on the map dashboard.
* [ ] **Production Deployment:** Containerize the RAG backend using Docker and configure production environment variables for cloud deployment.