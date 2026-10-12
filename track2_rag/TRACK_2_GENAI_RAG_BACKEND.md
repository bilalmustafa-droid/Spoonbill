# TRACK 2: GenAI and RAG Backend (Project Spoonbill)

**Owner:** GenAI Backend Developer
**Mission:** Ground every detected anomaly in Hong Kong statutory text and produce a bilingual (English and Traditional Chinese) preliminary enforcement brief, with strict "cite-or-abstain" behaviour and personal-data redaction.

> Assumed calendar (adjust if your deadline differs): Day 1 = Mon 5 Oct 2026, Day 8 = Mon 12 Oct, Day 12 = Fri 16 Oct, Days 13-14 = Sat/Sun 17-18 Oct (freeze and submission buffer).

---

## 0. Dependency map

```
Track 1 (GeoJSON anomalies)  ->  Track 2 (retrieve + generate brief)  ->  Track 3 (render + export)
```

You consume Track 1's file and produce JSON briefs that Track 3 renders. You can work from Day 1 using the mock file; you do not need real satellite output until Day 4.

## 1. Shared data contracts (v1, frozen on Day 1)

**Input (from Track 1):** `data/anomalies_v1.geojson`. The fields you use are inside `features[].properties`:
`anomaly_id, site_id, centroid_lon, centroid_lat, area_ha, baseline_vv_db, current_vv_db, delta_vv_db, baseline_ndwi, current_ndwi, delta_ndwi, first_detection_date, persistence_count, persistence_total, confidence_tier, zone_hint (WCA | WBA | OTHER | UNKNOWN)`.

**Output (to Track 3):** `data/briefs/{anomaly_id}.json`

```json
{
  "schema_version": "1.0",
  "anomaly_id": "DB-0001",
  "status": "cited",
  "model": "qwen2.5-14b-instruct",
  "generated_at": "2026-10-10T09:00:00Z",
  "en": {
    "title": "Preliminary Observation: Possible Wetland Fill near Site A",
    "summary": "...",
    "evidence": ["Area 1.42 ha", "VV +5.9 dB vs. baseline", "NDWI -0.35 vs. baseline", "First detected April 2025, persistent 5 of 6 months"],
    "statutory_basis": [{"claim": "...", "citation_ids": ["TPB12C-p7-c3"]}],
    "recommended_action": "Refer for site inspection and zoning confirmation by the relevant authority.",
    "limitations": "Satellite-derived indicator, not proof of unauthorised development."
  },
  "zh_hant": { "title": "...", "summary": "...", "evidence": [], "statutory_basis": [], "recommended_action": "...", "limitations": "..." },
  "citations": [{"id": "TPB12C-p7-c3", "doc": "TPB PG-No. 12C", "page": 7, "section": "...", "quote": "exact snippet, max 40 words"}],
  "human_review_required": false,
  "abstain_reason": null,
  "redaction_log": {"items_removed": 0, "types": []}
}
```

`status` is one of `cited`, `abstained_human_review`, `error`. When `status` is `abstained_human_review`, `statutory_basis` is empty, `human_review_required` is `true`, and `abstain_reason` explains why in plain language.

## 2. Suggested open-source stack (swap freely)

| Layer | Primary | Notes |
|---|---|---|
| PDF parsing | `PyMuPDF` (`fitz`) | Keep page numbers. For scanned PDFs: `ocrmypdf` + Tesseract with `chi_tra` and `eng` |
| Embeddings | `BAAI/bge-m3` via `sentence-transformers` | Multilingual, handles English and Traditional Chinese queries on the same index |
| Vector store | `ChromaDB` (persisted to disk) | `FAISS` is an equivalent fallback |
| Keyword search | `rank_bm25` | Hybrid search helps with clause numbers and exact terms |
| LLM (open source) | `Qwen2.5-14B-Instruct` (or 7B on weak hardware) through `Ollama` or `llama.cpp` | Strong Traditional Chinese. Alternatives: Llama 3.1 8B, Mistral |
| LLM (optional, hosted) | Gemini via API | Not open source. Keep it behind the same interface as an optional switch; confirm which Gemini model is currently available since older versions get retired |
| Structured output | `pydantic` v2 | Validate every LLM output against the brief schema |
| Redaction | `presidio-analyzer` plus custom regex | Names, HKID, phone, email, addresses of individuals, company-owner fields |
| Serving | Plain Python module first, `FastAPI` only if Track 3 needs a separate service | Fewer moving parts is better |

Design the LLM call behind one interface (`LLMClient.generate(prompt, schema)`) so you can switch between Ollama and a hosted API in one config line.

## 3. Document set to index (target 8 to 12; verify titles, versions and licence before ingesting)

| Priority | Document | Why |
|---|---|---|
| Must | **TPB Guidelines No. 12C** (Application for Developments within Deep Bay Area under s.16 of the Town Planning Ordinance) | Core guidance for WCA and WBA |
| Must | Explanatory Statements and Notes of the **Deep Bay-area Outline Zoning Plans** relevant to your showcase sites (WCA, WBA, and related zoning notes) | Zone-specific permitted uses |
| Must | **EIA / Environmental Permit conditions** relevant to your sites (EIAO Cap. 499 materials, technical memorandum on ecological assessment) | Condition-level citations |
| Should | Town Planning Ordinance (Cap. 131), enforcement and unauthorised development provisions | What "enforcement" means legally |
| Should | Northern Metropolis Action Agenda and Development Strategy (no net loss wording) | The policy promise |
| Should | Hong Kong Biodiversity Strategy and Action Plan and AFCD Ramsar/Mai Po material | Ecological context |
| Could | Short method notes on NDWI and SAR change detection from open sources | Lets the agent explain its own limits |

Minimum viable set if time collapses: **TPB PG-No. 12C + one OZP Notes/Explanatory Statement + one EIA ecological guidance document.**

**Privacy rule:** do not ingest any land registry or ownership data at all. The index must contain only public policy and statutory text. Briefs identify locations by coordinates, site ID and area, never by owner.

---

## PHASE 1: MUST-HAVE CORE SOLUTION (Days 1-8, high priority)

### Day 1 (Mon 5 Oct): Contracts and corpus
- [ ] Freeze the data contracts above with Tracks 1 and 3 (15 minute call).
- [ ] Set up repo folder `track2_rag/`, environment, and run the LLM locally (`ollama pull qwen2.5:14b` or 7b) to confirm it responds in Traditional Chinese.
- [ ] Download the Must-priority documents into `corpus/raw/` and record source URL, date and version in `corpus/SOURCES.md`.
- **Validation:** the LLM answers a simple prompt in both languages; all Must documents are on disk.

### Day 2 (Tue 6 Oct): Parse, chunk, index
- [ ] Parse PDFs into page-aware text; chunk by section or clause (about 300 to 600 tokens, small overlap); give every chunk a stable ID like `TPB12C-p7-c3` and metadata (doc, page, section).
- [ ] Embed with bge-m3 and persist to Chroma; add a BM25 index for hybrid search.
- **Validation:** `python -m rag.stats` prints chunk counts per document, and no chunk is empty or garbled (spot check 10 chunks, especially Chinese text).

### Day 3 (Wed 7 Oct): Retrieval that works
- [ ] Implement `retrieve(query, k=5)` with hybrid ranking and a similarity threshold.
- [ ] Build the query from anomaly fields, for example: "development or filling of wetland in Wetland Buffer Area, fishpond conversion, Deep Bay" plus `zone_hint`.
- [ ] Create a **gold test set of 15 to 20 questions** with the expected source chunk (for example "What does PG-12C say about no-net-loss in wetland buffer?").
- **Checkpoint CP1 (Day 3):** end-to-end mock run: mock GeoJSON -> retrieve -> placeholder brief JSON -> Track 3 can render it.
- **Validation:** gold set top-5 hit rate at least 80%.

### Day 4 (Thu 8 Oct): Brief generation v0.1 on real data
- [ ] Prompt template with three blocks: (1) anomaly metrics as JSON, (2) retrieved clauses with their IDs, (3) strict instructions and output schema.
- [ ] Generate English first, then the Traditional Chinese version in a second call from the same facts (translating from verified English content works better than generating both at once); keep a small glossary: wetland conservation area 濕地保育區, wetland buffer area 濕地緩衝區, Deep Bay 后海灣, no net loss 無淨損失 (confirm official Chinese terms against the source documents).
- [ ] Validate with `pydantic`; retry up to 2 times on schema failure.
- [ ] Run on Track 1's `anomalies_v0.1.geojson`.
- **Validation:** 100% of outputs parse against the schema.

### Day 5 (Fri 9 Oct): Cite-or-abstain enforcement (programmatic)
Implement this as **code, not just a prompt instruction**:
1. If retrieval returns nothing above the similarity threshold, return `abstained_human_review` without calling the LLM.
2. The LLM may only cite chunk IDs it was given. After generation, verify every `citation_id` exists in the retrieved set.
3. Verify every quote appears (normalised string match) inside the cited chunk. Drop any claim whose citation fails, and if no claims survive, abstain.
4. Never let the model state a legal conclusion ("this is illegal"). The template always frames output as "possible", "preliminary", "refer for inspection".
- [ ] Add unit tests: one case that should cite, one that should abstain (no relevant clause), one with a fabricated citation that must be rejected.
- **Validation:** all three tests pass; across the gold set, 0 briefs contain a citation that is not in the index.

### Day 6 (Sat 10 Oct): PDPO redaction and safety
- [ ] Redaction pass on **input** (anomaly fields, any free text) and **output** (final brief): names, HKID patterns, phone, email, individual addresses, lot-owner terms. Log counts in `redaction_log` (never log the redacted values themselves).
- [ ] Confirm the pipeline never reads ownership data; add a startup check that fails if an unexpected data file is present in `corpus/`.
- [ ] Add a visible disclaimer in every brief: satellite indicator only, no determination of unauthorised development.
- **Validation:** a red-team test file with 10 fake personal data strings produces zero leaks in the output.

### Day 7 (Sun 11 Oct): Quality and bilingual review
- [ ] Generate briefs for all high and medium anomalies; have one bilingual teammate review at least 5 Chinese briefs for terminology and tone.
- [ ] Tune prompt wording, retrieval k, and threshold using the gold set.
- [ ] Measure and note per-brief latency and tokens (needed for the cost-efficiency pitch).
- **Validation:** reviewer approves at least 4 of 5 Chinese briefs with only minor edits.

### Day 8 (Mon 12 Oct): Freeze v1 and hand over
- [ ] Batch-generate `data/briefs/*.json` for all anomalies in `anomalies_v1.geojson` and commit them (so the demo works offline).
- [ ] Expose one function for Track 3: `generate_brief(anomaly_id | feature) -> dict`, plus a cached-read path.
- [ ] Write `track2_rag/README.md` (how to rebuild the index, how to switch LLM backend).
- **Checkpoint CP3:** full pipeline demo on a teammate's machine.
- **Validation:** rebuild index plus regenerate 3 briefs from a fresh clone in under 30 minutes.

---

## PHASE 2: ADVANCED / OPTIONAL ENHANCEMENTS (Days 9-12, low priority, non-blocking)

| Day | Task | Output |
|---|---|---|
| 9 | **Reranker** (`bge-reranker-v2-m3`) after hybrid retrieval to improve citation precision | Higher gold-set hit rate |
| 10 | **Portfolio summary brief:** one executive overview across all anomalies by site (total area, top 3 priorities), still cite-or-abstain | `data/briefs/_overview.json` |
| 11 | **Hosted model comparison:** run a Gemini (or other hosted) backend on the same 10 anomalies and compare citation accuracy and cost against the local model | Short comparison table for the pitch |
| 12 | **Carbon and cost log:** record tokens, runtime, and hardware per brief to feed the sustainability estimate (use `codecarbon` for local runs) | `data/energy_log.json` |

Days 13-14: code freeze, no schema changes, support demo rehearsals, keep cached briefs as the demo's safety net.

---

## RISK MANAGEMENT AND FALLBACKS

| # | Risk | Likelihood | Impact | Mitigation | Fallback |
|---|---|---|---|---|---|
| 1 | Statutory PDFs are scanned or badly parsed (especially Chinese) | Medium | High | Check parsing on Day 2, OCR with Tesseract `chi_tra` | Hand-transcribe the 10 to 20 key clauses into `corpus/manual/*.md` with page references; index those instead |
| 2 | LLM hallucinated clauses or invented legal conclusions | Medium | Very high | Programmatic citation and quote verification, abstain by default | Switch output to a **template-based brief**: facts filled from JSON, clause quotes inserted verbatim from retrieval, LLM only writes a short neutral summary (or none) |
| 3 | Local LLM too slow or too weak on available hardware | Medium | High | Test on Day 1, use 7B quantised if needed | Hosted API behind the same interface; pre-generate and cache all briefs on Day 8 so the demo does not depend on live inference |
| 4 | Traditional Chinese quality is poor or uses mainland terms | Medium | Medium | Glossary, generate Chinese from verified English, bilingual review on Day 7 | Offer Chinese title, evidence and recommended action from a fixed template, with only the summary generated |
| 5 | Retrieval returns irrelevant clauses | Medium | High | Hybrid search, gold set, threshold | Rule-based mapping from `zone_hint` to a fixed list of pre-selected clauses; retrieval only adds extras |
| 6 | PDPO or privacy breach | Low | Very high | No ownership data in the corpus, redaction on input and output, tests | Disable free-text fields entirely; briefs use only numeric and coordinate fields |
| 7 | Track 1 data arrives late or changes schema | Medium | Medium | Work from mock from Day 1, validate input against JSON schema | Keep a frozen copy of v0.1 as the dev dataset; add adapters rather than rewriting prompts |
| 8 | Model or API deprecated or rate-limited mid-project | Low | Medium | Single `LLMClient` interface, local model as default | Config switch to another model; cached briefs |
| 9 | Documents have licence or reuse restrictions | Low | Medium | Record source and terms in `SOURCES.md`; use government publications for analysis, quote short snippets only | Remove the document from the repo and index it locally only; the demo shows citations without redistributing the full text |

**Definition of done for this track:** every anomaly in `anomalies_v1.geojson` has a validated brief JSON (cited or abstained), all citation and redaction tests pass, Chinese briefs have been human-reviewed, and Track 3 renders the briefs without edits.




# Track 2: GenAI & RAG Backend Progress Log

## Architecture Overview
* **Corpus & Indexing:** ChromaDB vector database persisting 231 statutory chunks (`track2_rag/chroma_db`).
* **Retrieval Engine:** Hybrid search using `BAAI/bge-m3` dense embeddings and `BM25` sparse indexing (`track2_rag/rag/retriever.py`).
* **Generation Engine:** Gemini API integration (`gemini-1.5-flash-latest`) handling prompt construction, statutory citation mapping, and structured JSON output (`track2_rag/rag/generator.py`).
* **Validation & Schema:** Strict adherence to `contract/brief.schema.json` enforced via Python's `jsonschema` library.

## Completed Milestones
* [x] Ingested core statutory guidelines (TPB PG-No. 12C, etc.) into chunked JSON corpus.
* [x] Validated hybrid retriever performance on Deep Bay wetland queries.
* [x] Implemented programmatic abstain rules for incomplete statutory matches.
* [x] Established batch generation script (`batch_generate.py`) for processing anomaly GeoJSON files.
* [x] Successfully generated and schema-validated first end-to-end enforcement brief (`data/briefs/DB-0001.json`).

## Next Steps
* Expand mock anomaly test cases in `contract/mock_anomalies.geojson` to test multiple simultaneous site polygons.
* Integrate Track 2 brief outputs into the frontend dashboard review interface.