"""
Reshapes track2_rag/rag/generator.py's real output into the exact shape
frontend/track3_app/core/models.py requires. The generator's citations use
chunk_id/document_title/page_number/verbatim_quote and statutory_basis as
plain strings; the frontend's Brief model requires
id/doc/doc_title_zh/page/section/quote/source_url citations and
statutory_basis as a list of {claim, citation_ids} objects. Without this,
every real generated brief shows as "invalid" in the UI.

Idempotent: if a citation already has an "id" key (already adapted), it is
left alone, so this is safe to call on cache hits every time without
double-transforming.

Document titles/URLs come from track2_rag/corpus/SOURCES.md -- never
invented. No official Chinese document titles exist in that source, so
doc_title_zh falls back to the same English title rather than a fabricated
translation; this is a documented limitation, not an oversight.
"""

# chunk "doc" field -> (official title, source URL), from
# track2_rag/corpus/SOURCES.md. Keep in sync if SOURCES.md changes.
DOC_INFO = {
    "pg12c_e": (
        "Town Planning Board Guidelines for Application for Developments within Deep Bay Area (TPB PG-No. 12C)",
        "https://www.tpb.gov.hk/en/forms/Guidelines/pg12c_e.pdf",
    ),
    "sstt2_sylmp8_sylntm14_20240920-e": (
        "LegCo Brief on S/STT/2, S/YL-MP/8, S/YL-NTM/14",
        "https://www.legco.gov.hk/yr2024/english/brief/sstt2_sylmp8_sylntm14_20240920-e.pdf",
    ),
    "GN7_2023": (
        "AFCD GN 7/2023 Ecological Baseline Survey",
        "https://www.afcd.gov.hk/english/conservation/con_tech/files/GN7_2023.pdf",
    ),
    "GN10_2023": (
        "AFCD GN 10/2023 Terrestrial Baseline Survey Methods",
        "https://www.afcd.gov.hk/english/conservation/con_tech/files/GN10_2023.pdf",
    ),
    "GN6": (
        "EPD GN 6/2023 Ecological Assessment Observations",
        "https://www.epd.gov.hk/eia/common/files/hb/materials/GN6.pdf",
    ),
}


def _doc_id_from_chunk_id(chunk_id: str) -> str:
    # chunk_ids look like "pg12c_e-p6" -- the doc id is everything before the
    # last "-pN" page suffix.
    return chunk_id.rsplit("-p", 1)[0] if "-p" in chunk_id else chunk_id


def _adapt_citation(cit: dict) -> dict:
    if "id" in cit:
        return cit  # already adapted
    chunk_id = cit.get("chunk_id", "")
    page = cit.get("page_number", 0)
    doc_id = _doc_id_from_chunk_id(chunk_id)
    title, url = DOC_INFO.get(doc_id, (cit.get("document_title", doc_id), None))
    return {
        "id": chunk_id,
        "doc": cit.get("document_title", title),
        "doc_title_zh": title,  # no official Chinese title in the corpus; English title reused, not translated
        "page": page,
        "section": f"p.{page}",  # chunks.json has no section metadata; page reference used instead of inventing one
        "quote": cit.get("verbatim_quote", ""),
        "source_url": url,
    }


def _claim_text(entry) -> str:
    """Handles three shapes seen for one statutory_basis entry: a plain
    string (the generator's raw output), an already-fully-adapted
    {claim, citation_ids} dict, or a transitionally-wrapped dict from an
    earlier buggy run whose citation_ids was still empty -- in every case
    the underlying claim text is recovered, never double-wrapped."""
    if isinstance(entry, str):
        return entry
    claim = entry.get("claim", "")
    return _claim_text(claim) if isinstance(claim, dict) else claim


def _adapt_language_block(block: dict, all_citation_ids: list[str]) -> dict:
    basis = block.get("statutory_basis", [])
    if basis and isinstance(basis[0], dict) and all(
        isinstance(c.get("claim"), str) and c.get("citation_ids") for c in basis
    ):
        return block  # already adapted: claim is a string and every claim has at least one citation id
    adapted = dict(block)
    # The schema requires each claim to cite at least one id, but the source
    # data has no per-claim attribution -- every claim references the full
    # set of citations actually used in this brief rather than being left
    # empty (which the schema rejects) or guessed at a finer grain than the
    # data supports.
    adapted["statutory_basis"] = [
        {"claim": _claim_text(entry), "citation_ids": list(all_citation_ids)}
        for entry in basis
    ]
    return adapted


def adapt_brief_for_frontend(brief: dict) -> dict:
    """Returns a new dict; never mutates the input. Safe to call on any
    brief, already-adapted or not."""
    adapted = dict(brief)
    adapted["citations"] = [_adapt_citation(c) for c in brief.get("citations", [])]
    all_citation_ids = [c["id"] for c in adapted["citations"]]
    for lang in ("en", "zh_hant"):
        if lang in brief:
            adapted[lang] = _adapt_language_block(brief[lang], all_citation_ids)
    return adapted
