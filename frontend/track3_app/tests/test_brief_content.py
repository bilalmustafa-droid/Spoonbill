from conftest import read_json, write_json
from core import config, loader
from core.brief_content import prepare_brief_content, resolve_claim_citations
from core.content_guard import has_legal_conclusion, has_personal_data, screen
from core.i18n import DISCLAIMER
from core.issues import log_issue


def test_all_citations_resolve_for_normal_brief(fixture_dir):
    brief = loader.load_brief(fixture_dir, "DB-0001")
    for lang in config.LANGS:
        content = prepare_brief_content(brief, lang)
        assert content.claims and all(c.citations and not c.missing_ids for c in content.claims)
        assert content.issues == []


def test_unresolvable_citation_is_kept_and_flagged(fixture_dir):
    brief = loader.load_brief(fixture_dir, "DB-0003")
    content = prepare_brief_content(brief, "en")
    assert len(content.claims) == 2                       # claim is not dropped
    broken = content.claims[1]
    assert broken.citations == [] and broken.missing_ids == ["FIXTURE-MISSING-p99-c9"]
    assert broken.claim.value                              # text still shown
    assert content.missing_citation_ids == ["FIXTURE-MISSING-p99-c9"]
    assert any("do not resolve" in i for i in content.issues)


def test_resolve_claim_citations_partial(fixture_dir):
    brief = loader.load_brief(fixture_dir, "DB-0001")
    found, missing = resolve_claim_citations(brief, ["FIXTURE-A-p3-c1", "NOPE"])
    assert [c.id for c in found] == ["FIXTURE-A-p3-c1"] and missing == ["NOPE"]


def test_abstained_has_reason_and_no_claims(fixture_dir):
    brief = loader.load_brief(fixture_dir, "DB-0005")
    content = prepare_brief_content(brief, "zh_hant")
    assert content.claims == []
    assert content.abstain_reason.value
    assert len(content.evidence) >= 3


def test_issue_log_writes_once_and_skips_fixtures(tmp_path):
    target = tmp_path / "ISSUES.md"
    assert log_issue("DB-0003: citation X missing", enabled=True, path=target)
    assert not log_issue("DB-0003: citation X missing", enabled=True, path=target)   # deduplicated
    assert target.read_text(encoding="utf-8").count("citation X missing") == 1
    other = tmp_path / "OTHER.md"
    assert not log_issue("anything", enabled=False, path=other)
    assert not other.exists()


def test_personal_data_patterns():
    for text in ["Owner HKID A123456(7)", "contact someone@example.com", "call 9123 4567",
                 "Tel +852 2123-4567", "Flat B, 12/F", "Mr. Chan owns the pond", "12樓A室"]:
        assert has_personal_data(text), text
    for text in ["Radar backscatter rose +5.9 dB above the 2023-2024 baseline",
                 "Affected area: 1.42 ha", "First detected 2025-04", "114.0521, 22.4974", "DB-0001",
                 "TPB12C-p7-c3"]:
        assert not has_personal_data(text), text


def test_legal_conclusion_patterns_but_disclaimer_passes():
    assert has_legal_conclusion("This is an illegal fill.")
    assert has_legal_conclusion("Clear violation of zoning.")
    assert has_legal_conclusion("此乃違法填塘")
    assert not has_legal_conclusion(DISCLAIMER["en"])
    assert not has_legal_conclusion(DISCLAIMER["zh_hant"])
    assert not has_legal_conclusion("Refer for site inspection and verification.")


def test_withheld_text_in_brief(data_copy):
    path = data_copy / config.BRIEFS_DIRNAME / "DB-0001.json"
    doc = read_json(path)
    doc["en"]["summary"] = "The site is an unauthorised fill by Mr. Wong."
    doc["en"]["evidence"][0] = "This is illegal."
    write_json(path, doc)
    content = prepare_brief_content(loader.load_brief(data_copy, "DB-0001"), "en")
    assert content.summary.withheld and content.summary.reason == "personal"
    assert content.evidence[0].withheld and content.evidence[0].reason == "legal"
    assert any("withheld" in i for i in content.issues)


def test_quotes_are_not_censored_for_statutory_wording():
    assert screen("enforcement against unauthorized development", check_legal=False).text
