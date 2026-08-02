"""Safe, structured PDF rendering for validated reports."""
from __future__ import annotations

import io
import re
from pathlib import Path

from html import escape
from typing import Iterable

from ..schemas import ResearchReport


def safe_filename(company_name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "-", company_name).strip("-").lower() or "company"
    return f"{value[:80]}-research-report.pdf"


def _text(value: object) -> str:
    return escape(str(value) if value not in (None, "") else "Not publicly found.")


def render_pdf(report: ResearchReport) -> bytes:
    """Build a PDF without accepting HTML or touching the filesystem."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    regular_font, bold_font = "Helvetica", "Helvetica-Bold"
    font_dir = Path("/usr/share/fonts/truetype/dejavu")
    regular_path = font_dir / "DejaVuSans.ttf"
    bold_path = font_dir / "DejaVuSans-Bold.ttf"
    if regular_path.is_file() and bold_path.is_file():
        pdfmetrics.registerFont(TTFont("CRA-DejaVu", str(regular_path)))
        pdfmetrics.registerFont(TTFont("CRA-DejaVu-Bold", str(bold_path)))
        regular_font, bold_font = "CRA-DejaVu", "CRA-DejaVu-Bold"

    output = io.BytesIO()
    doc = SimpleDocTemplate(
        output, pagesize=letter, rightMargin=0.65 * inch, leftMargin=0.65 * inch,
        topMargin=0.65 * inch, bottomMargin=0.6 * inch, title=f"{report.company.name} research report",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("ReportTitle", parent=styles["Title"], fontName=bold_font, alignment=TA_CENTER, fontSize=20, leading=25, spaceAfter=8)
    heading = ParagraphStyle("ReportHeading", parent=styles["Heading2"], fontName=bold_font, fontSize=13, leading=17, spaceBefore=10, spaceAfter=5, textColor=colors.HexColor("#17324d"))
    body = ParagraphStyle("ReportBody", parent=styles["BodyText"], fontName=regular_font, fontSize=9.5, leading=13, spaceAfter=5)
    small = ParagraphStyle("ReportSmall", parent=body, fontName=regular_font, fontSize=8, leading=10)
    bullet = ParagraphStyle("ReportBullet", parent=body, fontName=regular_font, leftIndent=12, firstLineIndent=-8)
    story = [Paragraph(_text(report.company.name), title), Paragraph("Company Research Report", body),
             Paragraph(f"Generated: {_text(report.generated_at.isoformat())} &nbsp;|&nbsp; Model: {_text(report.model_id)}", small), Spacer(1, 8), HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#9ab0c4"))]

    story.extend([Paragraph("Company", heading)])
    company_rows = [
        [Paragraph("Name", small), Paragraph(_text(report.company.name), body)],
        [Paragraph("Website", small), Paragraph(_text(report.company.website), body)],
        [Paragraph("Phone", small), Paragraph(_text(report.company.phone), body)],
        [Paragraph("Address", small), Paragraph(_text(report.company.address), body)],
        [Paragraph("Country", small), Paragraph(_text(report.company.country), body)],
        [Paragraph("Industry", small), Paragraph(_text(report.company.industry), body)],
    ]
    company_table = Table(company_rows, colWidths=[1.15 * inch, 5.8 * inch], repeatRows=0)
    company_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#edf3f7")), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c5d1db")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    story.append(company_table)
    story.extend([Paragraph("Summary", heading), Paragraph(_text(report.summary), body)])

    story.append(Paragraph("Products and Services", heading))
    if report.products_services:
        story.extend(Paragraph(f"• {_text(item)}", bullet) for item in report.products_services)
    else:
        story.append(Paragraph("Not publicly found.", body))

    story.append(Paragraph("AI-Inferred Pain Points", heading))
    story.append(Paragraph("These are AI-inferred hypotheses based on the available evidence, not verified company claims.", small))
    if report.pain_points:
        story.extend(Paragraph(f"• {_text(item)}", bullet) for item in report.pain_points)
    else:
        story.append(Paragraph("Not publicly found.", body))

    story.append(Paragraph("Competitors", heading))
    if report.competitors:
        competitor_rows = [[Paragraph("Name", small), Paragraph("Website", small), Paragraph("Relevance", small)]]
        competitor_rows.extend([[Paragraph(_text(c.name), body), Paragraph(_text(c.website), body), Paragraph(_text(c.fit), body)] for c in report.competitors])
        table = Table(competitor_rows, colWidths=[1.55 * inch, 2.45 * inch, 2.95 * inch], repeatRows=1)
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324d")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c5d1db")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]))
        story.append(table)
    else:
        story.append(Paragraph("Not publicly found.", body))

    story.append(Paragraph("Sources", heading))
    if report.sources:
        for source in report.sources:
            story.append(Paragraph(f"• <b>{_text(source.title)}</b> — {_text(source.url)} ({_text(source.source_type)})", small))
    else:
        story.append(Paragraph("Not publicly found.", body))
    story.append(Paragraph("Warnings", heading))
    if report.warnings:
        for warning in report.warnings:
            story.append(Paragraph(f"• {_text(warning)}", bullet))
    else:
        story.append(Paragraph("None.", body))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#657789"))
        canvas.drawString(0.65 * inch, 0.35 * inch, "Company Research Assistant")
        canvas.drawRightString(letter[0] - 0.65 * inch, 0.35 * inch, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


# Friendly aliases for callers and tests.
generate_pdf = render_pdf
