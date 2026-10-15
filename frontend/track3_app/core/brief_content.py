"""Turn a Brief into display-ready content for one language. Shared by the UI and both exporters so
the screen, the PDF and the DOCX always show identical text.

* Every citation_id in statutory_basis is resolved against brief.citations. Unresolvable IDs are kept
  on the claim as `missing_ids` so the UI can show a visible "citation unavailable" marker.
* Free text passes through content_guard; withheld items keep their slot with a reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .content_guard import screen
from .models import Brief, Citation


@dataclass(frozen=True)
class Text:
    """A free-text value after screening. value is None when withheld (then reason is set)."""
    value: str | None
    reason: str | None = None

    @property
    def withheld(self) -> bool:
        return self.value is None and self.reason is not None


@dataclass(frozen=True)
class ResolvedClaim:
    claim: Text
    citations: list[Citation]
    missing_ids: list[str]


@dataclass(frozen=True)
class BriefContent:
    status: str
    lang: str
    title: Text
    summary: Text
    evidence: list[Text]
    claims: list[ResolvedClaim]
    recommended_action: Text
    limitations: Text
    abstain_reason: Text | None
    citations: list[Citation]          # full list, in brief order (quotes screened for personal data)
    human_review_required: bool
    model: str
    generated_at: str
    issues: list[str] = field(default_factory=list)   # integration issues found while preparing

    @property
    def missing_citation_ids(self) -> list[str]:
        return sorted({mid for c in self.claims for mid in c.missing_ids})


def _text(value: str | None, check_legal: bool = True) -> Text:
    screened = screen(value, check_legal=check_legal)
    return Text(screened.text, screened.reason)


def _safe_citation(c: Citation) -> Citation | None:
    """Quotes are verbatim statutory text: screened for personal data only."""
    fields = [c.doc, c.doc_title_zh, c.section, c.quote]
    if any(screen(f, check_legal=False).reason for f in fields):
        return None
    return c


def resolve_claim_citations(brief: Brief, citation_ids: list[str]) -> tuple[list[Citation], list[str]]:
    by_id = {c.id: c for c in brief.citations}
    found = [by_id[cid] for cid in citation_ids if cid in by_id]
    missing = [cid for cid in citation_ids if cid not in by_id]
    return found, missing


def prepare_brief_content(brief: Brief, lang: str) -> BriefContent:
    block = brief.block(lang)
    issues: list[str] = []

    safe_citations = []
    for c in brief.citations:
        safe = _safe_citation(c)
        if safe is None:
            issues.append(f"{brief.anomaly_id}: citation {c.id} withheld (possible personal data in citation text)")
        else:
            safe_citations.append(safe)
    safe_by_id = {c.id for c in safe_citations}

    claims = []
    # Contract: statutory_basis is empty whenever status is not "cited" (also enforced by the schema).
    if brief.status == "cited":
        for item in block.statutory_basis:
            found, missing = resolve_claim_citations(brief, item.citation_ids)
            found = [c for c in found if c.id in safe_by_id]
            if missing:
                issues.append(f"{brief.anomaly_id} [{lang}]: citation_ids {missing} in statutory_basis "
                              f"do not resolve against the citations array")
            claims.append(ResolvedClaim(claim=_text(item.claim), citations=found, missing_ids=missing))

    content = BriefContent(
        status=brief.status,
        lang=lang,
        title=_text(block.title),
        summary=_text(block.summary),
        evidence=[_text(e) for e in block.evidence],
        claims=claims,
        recommended_action=_text(block.recommended_action),
        limitations=_text(block.limitations),
        abstain_reason=_text(brief.abstain_reason) if brief.status == "abstained_human_review" else None,
        citations=safe_citations,
        human_review_required=brief.human_review_required,
        model=brief.model,
        generated_at=brief.generated_at,
        issues=issues,
    )
    withheld = [name for name, t in _named_texts(content) if t.withheld]
    for name in withheld:
        issues.append(f"{brief.anomaly_id} [{lang}]: field '{name}' withheld by content safeguard")
    return content


def _named_texts(content: BriefContent):
    yield "title", content.title
    yield "summary", content.summary
    for i, e in enumerate(content.evidence):
        yield f"evidence[{i}]", e
    for i, c in enumerate(content.claims):
        yield f"statutory_basis[{i}].claim", c.claim
    yield "recommended_action", content.recommended_action
    yield "limitations", content.limitations
    if content.abstain_reason is not None:
        yield "abstain_reason", content.abstain_reason
