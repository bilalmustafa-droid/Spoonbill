"""PDF export with reportlab and the bundled Noto Sans TC font.

WeasyPrint (HTML template -> PDF) was tried first but needs GTK/Pango system libraries that are not
available on Windows (`OSError: cannot load library 'libgobject-2.0-0'`), so reportlab is used instead.
It is pure Python, works offline, and embeds the bundled TrueType font so Chinese renders everywhere.
"""

from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, ListFlowable, ListItem, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from core.config import CJK_FONT_PATH

FONT = "NotoSansTC"
PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN
AMBER_BG, AMBER_EDGE = colors.HexColor("#FFF4D6"), colors.HexColor("#E0A800")
GREY_BG, GREY_EDGE = colors.HexColor("#F1F3F5"), colors.HexColor("#868E96")
BANNER_BG = colors.HexColor("#7A1F1F")


class FontMissingError(RuntimeError):
    pass


def ensure_font() -> None:
    if FONT in pdfmetrics.getRegisteredFontNames():
        return
    if not CJK_FONT_PATH.is_file():
        raise FontMissingError(
            f"Bundled CJK font not found at {CJK_FONT_PATH}. Run: python track3_app/scripts/fetch_fonts.py")
    pdfmetrics.registerFont(TTFont(FONT, str(CJK_FONT_PATH)))


def _styles(lang: str) -> dict[str, ParagraphStyle]:
    wrap = "CJK" if lang == "zh_hant" else None
    base = dict(fontName=FONT, alignment=TA_LEFT, wordWrap=wrap)
    return {
        "title": ParagraphStyle("title", fontSize=18, leading=24, spaceAfter=4, **base),
        "h2": ParagraphStyle("h2", fontSize=13, leading=18, spaceBefore=10, spaceAfter=4,
                             textColor=colors.HexColor("#1F4E5F"), **base),
        "h3": ParagraphStyle("h3", fontSize=11, leading=15, spaceBefore=6, spaceAfter=2, **base),
        "body": ParagraphStyle("body", fontSize=9.5, leading=14, **base),
        "small": ParagraphStyle("small", fontSize=8, leading=11, textColor=colors.HexColor("#495057"), **base),
        "quote": ParagraphStyle("quote", fontSize=9, leading=13, leftIndent=8, textColor=colors.HexColor("#343A40"),
                                **base),
        "banner": ParagraphStyle("banner", fontSize=10.5, leading=14, textColor=colors.white, **base),
        "cell": ParagraphStyle("cell", fontSize=9, leading=12, **base),
        "center": ParagraphStyle("center", fontSize=10, leading=14, fontName=FONT, alignment=TA_CENTER,
                                 wordWrap=wrap),
        "missing": ParagraphStyle("missing", fontSize=9, leading=12, textColor=colors.HexColor("#7A1F1F"), **base),
    }


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(text or ""), style)


def _boxed(flowables: list, bg, edge) -> Table:
    table = Table([[flowables]], colWidths=[CONTENT_W])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LINEBEFORE", (0, 0), (0, -1), 4, edge),
        ("BOX", (0, 0), (-1, -1), 0.5, edge),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _grid(rows: list[list[str]], widths: list[float], st: dict, header: bool) -> Table:
    data = [[_p(c, st["cell"]) for c in row] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CED4DA")),
             ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E9ECEF")))
    table.setStyle(TableStyle(style))
    return table


def _images(model: dict, st: dict) -> Table:
    cell_w = CONTENT_W / 2 - 4 * mm
    cells = []
    for img in model["images"]:
        if img["path"] is not None:
            visual = Image(str(img["path"]), width=cell_w, height=cell_w, kind="proportional")
        else:
            visual = Table([[_p(model["image_missing_text"], st["center"])]], colWidths=[cell_w],
                           rowHeights=[cell_w * 0.6])
            visual.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), GREY_BG),
                                        ("BOX", (0, 0), (-1, -1), 0.5, GREY_EDGE),
                                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        cells.append([visual, _p(img["caption"], st["small"])])
    table = Table([cells], colWidths=[CONTENT_W / 2, CONTENT_W / 2])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return table


def _brief(model: dict, st: dict) -> list:
    b, lab = model["brief"], model["labels"]
    out = [_p(lab["brief_heading"], st["h2"]),
           _p(f'{lab["report_status"]}: {model["status_label"]}', st["small"])]
    if b["notice"]:
        out.append(_boxed([_p(b["notice"], st["body"])], GREY_BG, GREY_EDGE))
        return out
    if b["review"]:
        r = b["review"]
        out.append(_boxed([_p(r["heading"], st["h3"]), _p(r["body"], st["body"]),
                           _p(f'{r["reason_label"]}: {r["reason"]}', st["body"])], AMBER_BG, AMBER_EDGE))
    if b["title"]:
        out.append(_p(b["title"], st["h3"]))
    if b["summary"]:
        out += [_p(lab["summary"], st["h3"]), _p(b["summary"], st["body"])]
    if b["evidence"]:
        out.append(_p(lab["evidence"], st["h3"]))
        out.append(ListFlowable([ListItem(_p(e, st["body"]), leftIndent=10) for e in b["evidence"]],
                                bulletType="bullet", start="•", leftIndent=10, bulletFontName=FONT))
    if b["claims"]:
        out.append(_p(lab["statutory_basis"], st["h3"]))
        for i, c in enumerate(b["claims"], start=1):
            out.append(_p(f'{i}. {c["text"]} {" ".join(c["refs"])}', st["body"]))
            if c["missing"]:
                out.append(_p(f'⚠ {c["missing"]}', st["missing"]))
    if b["recommended_action"]:
        out += [_p(lab["recommended_action"], st["h3"]), _p(b["recommended_action"], st["body"])]
    if b["limitations"]:
        out += [_p(lab["limitations"], st["h3"]), _p(b["limitations"], st["body"])]
    if b["meta"]:
        out.append(_p(b["meta"], st["small"]))
    return out


def _citations(model: dict, st: dict) -> list:
    if not model["citations"]:
        return []
    lab = model["labels"]
    out = [_p(lab["citations"], st["h2"])]
    for c in model["citations"]:
        out.append(KeepTogether([
            _p(f'[{c["number"]}] {c["doc"]} · {lab["page"]} {c["page"]} · {lab["section"]}: {c["section"]}',
               st["body"]),
            _p(f'“{c["quote"]}”', st["quote"]),
            _p(c["source_url"], st["small"]),
            Spacer(1, 4),
        ]))
    return out


def _footer(model: dict):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont(FONT, 7)
        canvas.setFillColor(colors.HexColor("#495057"))
        lines = simpleSplit(model["disclaimer"], FONT, 7, CONTENT_W)
        y = 10 * mm + 8 * (len(lines) - 1)
        for line in lines:
            canvas.drawString(MARGIN, y, line)
            y -= 8
        canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 10 * mm, f'{model["anomaly_id"]} · {doc.page}')
        canvas.restoreState()
    return draw


def render_pdf(model: dict) -> bytes:
    ensure_font()
    st = _styles(model["lang"])
    lab = model["labels"]
    story = []
    if model["fixture_label"]:
        story.append(_boxed([_p(f'⚠ {model["fixture_label"]}', st["banner"])], BANNER_BG, colors.HexColor("#FFB000")))
        story.append(Spacer(1, 6))
    story += [
        _p(f'{model["title"]}: {model["anomaly_id"]}', st["title"]),
        _p(f'{model["generated_label"]}: {model["generated_at"]}', st["small"]),
        _p(lab["location_heading"], st["h2"]),
        _grid([[k, v] for k, v in model["location"]], [CONTENT_W * 0.3, CONTENT_W * 0.7], st, header=False),
        _p(lab["metrics_heading"], st["h2"]),
        _grid([model["metrics"]["header"]] + model["metrics"]["rows"],
              [CONTENT_W * 0.34, CONTENT_W * 0.18, CONTENT_W * 0.18, CONTENT_W * 0.30], st, header=True),
        _p(lab["images_heading"], st["h2"]),
        _images(model, st),
    ]
    story += _brief(model, st)
    story += _citations(model, st)
    story += [Spacer(1, 10), _boxed([_p(lab["disclaimer_label"], st["h3"]), _p(model["disclaimer"], st["body"])],
                                    GREY_BG, GREY_EDGE)]

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=16 * mm,
                            bottomMargin=24 * mm, title=f'{model["title"]} {model["anomaly_id"]}',
                            author="Project Spoonbill", subject=model["disclaimer"])
    footer = _footer(model)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
