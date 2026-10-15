"""DOCX export with python-docx.

DOCX cannot embed fonts through python-docx, so every run explicitly sets the East Asian font
(w:eastAsia) to Microsoft JhengHei, which ships with Windows and Office; without it Word may show
Chinese as empty boxes. Latin text uses Calibri. The disclaimer is in the page footer and at the end.
"""

from __future__ import annotations

from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

EAST_ASIA_FONT = "Microsoft JhengHei"
LATIN_FONT = "Calibri"
STYLES_TO_FIX = ("Normal", "Title", "Heading 1", "Heading 2", "Heading 3", "List Bullet", "Table Grid", "Footer")


def _set_fonts(rpr_parent, lang: str) -> None:
    """Set ascii/hAnsi/eastAsia fonts (and East Asian language) on a run or style rPr."""
    rpr = rpr_parent.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    latin = EAST_ASIA_FONT if lang == "zh_hant" else LATIN_FONT
    fonts.set(qn("w:ascii"), latin)
    fonts.set(qn("w:hAnsi"), latin)
    fonts.set(qn("w:eastAsia"), EAST_ASIA_FONT)
    fonts.set(qn("w:cs"), latin)
    if lang == "zh_hant":
        fonts.set(qn("w:hint"), "eastAsia")
    lang_el = rpr.find(qn("w:lang"))
    if lang_el is None:
        lang_el = OxmlElement("w:lang")
        rpr.append(lang_el)
    lang_el.set(qn("w:val"), "en-GB")
    lang_el.set(qn("w:eastAsia"), "zh-HK")


def _run(paragraph, text: str, lang: str, *, bold: bool = False, size: float | None = None,
         color: str | None = None, italic: bool = False):
    run = paragraph.add_run(text)
    run.bold = bold
    run.italic = italic
    if size:
        run.font.size = Pt(size)
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    _set_fonts(run._r, lang)
    return run


def _para(doc_or_cell, text: str, lang: str, style: str | None = None, **run_kwargs):
    p = doc_or_cell.add_paragraph(style=style) if style else doc_or_cell.add_paragraph()
    _run(p, text, lang, **run_kwargs)
    return p


def _heading(doc, text: str, lang: str, level: int):
    h = doc.add_heading(level=level)
    _run(h, text, lang)
    return h


def _shade(cell, hex_fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tc_pr.append(shd)


def _cell_text(cell, text: str, lang: str, **run_kwargs) -> None:
    cell.text = ""
    _run(cell.paragraphs[0], text, lang, **run_kwargs)


def _boxed(doc, lines: list[tuple[str, dict]], lang: str, fill: str) -> None:
    table = doc.add_table(rows=1, cols=1)
    table.style = "Table Grid"
    cell = table.cell(0, 0)
    _shade(cell, fill)
    cell.text = ""
    first = True
    for text, kwargs in lines:
        p = cell.paragraphs[0] if first else cell.add_paragraph()
        first = False
        _run(p, text, lang, **kwargs)
    doc.add_paragraph()


def _grid(doc, rows: list[list[str]], lang: str, header: bool, widths_cm: list[float]) -> None:
    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
    table.style = "Table Grid"
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            cell = table.cell(r, c)
            cell.width = Cm(widths_cm[c])
            _cell_text(cell, value, lang, bold=header and r == 0, size=9.5)
            if header and r == 0:
                _shade(cell, "E9ECEF")


def _images(doc, model: dict, lang: str) -> None:
    # Image and caption share one cell so they never split across pages.
    table = doc.add_table(rows=1, cols=2)
    for i, img in enumerate(model["images"]):
        cell = table.cell(0, i)
        cell.text = ""
        first = cell.paragraphs[0]
        first.paragraph_format.keep_with_next = True
        if img["path"] is not None:
            first.add_run().add_picture(str(img["path"]), width=Cm(7))
        else:
            _shade(cell, "F1F3F5")
            _run(first, model["image_missing_text"], lang, italic=True)
        _run(cell.add_paragraph(), img["caption"], lang, size=8.5, color="495057")


def _brief(doc, model: dict, lang: str) -> None:
    b, lab = model["brief"], model["labels"]
    _heading(doc, lab["brief_heading"], lang, 2)
    _para(doc, f'{lab["report_status"]}: {model["status_label"]}', lang, size=9, color="495057")
    if b["notice"]:
        _boxed(doc, [(b["notice"], {})], lang, "F1F3F5")
        return
    if b["review"]:
        r = b["review"]
        _boxed(doc, [(r["heading"], {"bold": True, "size": 12}), (r["body"], {}),
                     (f'{r["reason_label"]}: {r["reason"]}', {"bold": False})], lang, "FFF4D6")
    if b["title"]:
        _heading(doc, b["title"], lang, 3)
    if b["summary"]:
        _para(doc, lab["summary"], lang, bold=True)
        _para(doc, b["summary"], lang)
    if b["evidence"]:
        _para(doc, lab["evidence"], lang, bold=True)
        for e in b["evidence"]:
            _para(doc, e, lang, style="List Bullet")
    if b["claims"]:
        _para(doc, lab["statutory_basis"], lang, bold=True)
        for i, c in enumerate(b["claims"], start=1):
            _para(doc, f'{i}. {c["text"]} {" ".join(c["refs"])}'.rstrip(), lang)
            if c["missing"]:
                _para(doc, f'⚠ {c["missing"]}', lang, bold=True, color="7A1F1F", size=9.5)
    if b["recommended_action"]:
        _para(doc, lab["recommended_action"], lang, bold=True)
        _para(doc, b["recommended_action"], lang)
    if b["limitations"]:
        _para(doc, lab["limitations"], lang, bold=True)
        _para(doc, b["limitations"], lang)
    if b["meta"]:
        _para(doc, b["meta"], lang, size=8.5, color="495057")


def _citations(doc, model: dict, lang: str) -> None:
    if not model["citations"]:
        return
    lab = model["labels"]
    _heading(doc, lab["citations"], lang, 2)
    for c in model["citations"]:
        _para(doc, f'[{c["number"]}] {c["doc"]} · {lab["page"]} {c["page"]} · {lab["section"]}: {c["section"]}',
              lang, bold=True, size=10)
        _para(doc, f'“{c["quote"]}”', lang, italic=True, size=9.5)
        _para(doc, c["source_url"], lang, size=8.5, color="495057")


def render_docx(model: dict) -> bytes:
    lang = model["lang"]
    doc = Document()
    for name in STYLES_TO_FIX:
        try:
            _set_fonts(doc.styles[name].element, lang)
        except KeyError:
            continue
    section = doc.sections[0]
    section.left_margin = section.right_margin = Cm(2)
    footer_p = section.footer.paragraphs[0]
    _run(footer_p, model["disclaimer"], lang, size=7.5, color="495057")

    if model["fixture_label"]:
        _boxed(doc, [(f'⚠ {model["fixture_label"]}', {"bold": True, "color": "FFFFFF"})], lang, "7A1F1F")
    title = doc.add_heading(level=0)
    _run(title, f'{model["title"]}: {model["anomaly_id"]}', lang)
    _para(doc, f'{model["generated_label"]}: {model["generated_at"]}', lang, size=9, color="495057")

    lab = model["labels"]
    _heading(doc, lab["location_heading"], lang, 2)
    _grid(doc, [[k, v] for k, v in model["location"]], lang, header=False, widths_cm=[5, 12])
    _heading(doc, lab["metrics_heading"], lang, 2)
    _grid(doc, [model["metrics"]["header"]] + model["metrics"]["rows"], lang, header=True,
          widths_cm=[5.5, 3, 3, 5.5])
    _heading(doc, lab["images_heading"], lang, 2)
    _images(doc, model, lang)
    _brief(doc, model, lang)
    _citations(doc, model, lang)

    doc.add_paragraph()
    _boxed(doc, [(lab["disclaimer_label"], {"bold": True}), (model["disclaimer"], {})], lang, "F1F3F5")
    doc.core_properties.title = f'{model["title"]} {model["anomaly_id"]}'
    doc.core_properties.author = "Project Spoonbill"
    doc.core_properties.comments = model["disclaimer"]
    for p in doc.paragraphs:
        if p.style.name == "Title":
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
