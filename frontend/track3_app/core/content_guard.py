"""Last-line safeguard on upstream free text before it is rendered or exported.

Track 2 is responsible for redaction and neutral wording; this module only makes sure that if
something slips through, Track 3 withholds it instead of displaying it.

* Personal data: HKID, email, Hong Kong phone numbers, flat/room style individual addresses.
* Legal-conclusion wording: "illegal", "unauthorised", "violation", "breach" and Chinese equivalents.
  The mandated disclaimer itself contains "unauthorised development" / "違例發展", so the disclaimer
  sentences are removed before checking.
Verbatim citation quotes are checked for personal data only (they are quotes of statutory text).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .i18n import DISCLAIMER

_PERSONAL_PATTERNS = [
    re.compile(r"\b[A-Z]{1,2}\d{6}\s?\(?[0-9A]\)?", re.IGNORECASE),            # HKID e.g. A123456(7)
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),                                       # email
    # HK phone, 8 digits; year ranges like "2023-2024" are excluded.
    re.compile(r"(?:\+?852[\s-]?)?(?<![\d.])(?!(?:19|20)\d{2}[\s-]?(?:19|20)\d{2}(?![\d.]))"
               r"[2-9]\d{3}[\s-]?\d{4}(?![\d.])"),
    re.compile(r"\b(?:flat|room|unit)\s+\w+\s*,?\s*\d+\s*/\s*F\b", re.IGNORECASE),  # Flat A, 12/F
    re.compile(r"\d+\s*樓\s*\w*\s*室"),                                            # 12樓A室
    re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Dr)\.?\s+[A-Z][a-z]+"),                       # honorific + name
    re.compile(r"(?:先生|女士|小姐)(?:的|之)?(?:土地|業權)"),                         # owner references
    re.compile(r"\b(?:land\s+)?owner(?:'s)?\s+name\b", re.IGNORECASE),
]

_LEGAL_PATTERNS = [
    re.compile(r"\billegal(?:ly)?\b", re.IGNORECASE),
    re.compile(r"\bunauthori[sz]ed\b", re.IGNORECASE),
    re.compile(r"\bviolat(?:e|es|ed|ing|ion|ions)\b", re.IGNORECASE),
    re.compile(r"\bbreach(?:es|ed|ing)?\b", re.IGNORECASE),
    re.compile(r"違法|非法|違例|違規|違反|未經授權|未經許可"),
]


@dataclass(frozen=True)
class Screened:
    text: str | None          # None when withheld
    reason: str | None        # "personal" | "legal" | None


def _strip_disclaimer(text: str) -> str:
    for d in DISCLAIMER.values():
        text = text.replace(d, " ")
    # Disclaimer sentences can also appear individually or reworded in limitations; remove the
    # standard negated phrase so "not a legal determination of unauthorised development" passes.
    text = re.sub(r"not\s+(?:a\s+)?(?:legal\s+determination|proof)\s+of\s+unauthori[sz]ed\s+development",
                  " ", text, flags=re.IGNORECASE)
    text = text.replace("並非對違例發展的法律認定", " ")
    return text


def has_personal_data(text: str) -> bool:
    return any(p.search(text) for p in _PERSONAL_PATTERNS)


def has_legal_conclusion(text: str) -> bool:
    return any(p.search(_strip_disclaimer(text)) for p in _LEGAL_PATTERNS)


def screen(text: str | None, check_legal: bool = True) -> Screened:
    if text is None:
        return Screened(None, None)
    if has_personal_data(text):
        return Screened(None, "personal")
    if check_legal and has_legal_conclusion(text):
        return Screened(None, "legal")
    return Screened(text, None)
