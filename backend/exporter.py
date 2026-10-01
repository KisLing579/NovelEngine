"""Render the approved story chapters as a downloadable PDF.

reportlab's built-in STSong-Light CID font is used so simplified Chinese
renders without bundling a font file. Only committed (approved) chapters are
included, matching what the engine has written to `world.chapter_number`.
"""
import html
import io

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate

FONT = "STSong-Light"
pdfmetrics.registerFont(UnicodeCIDFont(FONT))


def _esc(value):
    return html.escape(value or "")


def _style(name, **overrides):
    params = {
        "fontName": FONT,
        "wordWrap": "CJK",
        "fontSize": 11,
        "leading": 18,
        "spaceBefore": 0,
        "spaceAfter": 6,
    }
    params.update(overrides)
    return ParagraphStyle(name, **params)


def render_story_pdf(bundle):
    """Return the PDF bytes for a committed story bundle."""
    world = bundle["world"]
    number = world["chapter_number"]
    chapters = bundle.get("chapters", {})

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
        title=_esc(world["outline"]["premise"]),
    )

    title_style = _style("Title", fontSize=20, leading=28, alignment=TA_CENTER, spaceAfter=6)
    meta_style = _style("Meta", fontSize=10, leading=14, alignment=TA_CENTER, textColor="#666666", spaceAfter=20)
    chapter_style = _style("Chapter", fontSize=15, leading=22, spaceBefore=16, spaceAfter=4)
    body_style = _style("Body", fontSize=12, leading=20, alignment=TA_JUSTIFY, spaceAfter=8)

    story = [
        Paragraph(_esc(world["outline"]["premise"]), title_style),
        Paragraph(f"已生成 {number} 章", meta_style),
    ]

    for n in range(1, number + 1):
        record = chapters.get(str(n))
        if not record:
            continue
        story.append(Paragraph(f"第 {n} 章", chapter_style))
        for para in _esc(record.get("text")).splitlines():
            para = para.strip()
            if para:
                story.append(Paragraph(para, body_style))

    doc.build(story)
    return buffer.getvalue()
