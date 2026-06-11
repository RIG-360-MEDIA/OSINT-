"""
Generate a synthetic multi-column newspaper PDF for pipeline testing.

Uses reportlab (already in requirements.txt) to produce a proper
digital-born PDF with real Unicode text, varied font sizes, and a
7-column newspaper grid — so the pdfplumber path exercises every tier:
column detection, headline identification, article assembly.

Usage:
    python scripts/gen_test_newspaper_pdf.py
    # writes: /tmp/test_newspaper_synthetic.pdf
"""
from __future__ import annotations
from pathlib import Path

OUTPUT = Path("/tmp/test_newspaper_synthetic.pdf")

ARTICLES = [
    {
        "headline": "CM Naidu Launches District Development Plan",
        "body": (
            "Chief Minister N. Chandrababu Naidu on Friday launched the "
            "district development plan for all 26 districts of Andhra Pradesh. "
            "The plan focuses on infrastructure, education, and healthcare. "
            "Speaking at the launch event in Amaravati, the CM said the government "
            "aims to bring every district to a minimum development threshold by 2028. "
            "Ministers and district collectors attended the event."
        ),
        "section": "Politics",
    },
    {
        "headline": "Hyderabad Sees Record Rainfall This Season",
        "body": (
            "Hyderabad recorded its highest June rainfall in three decades this week, "
            "with 142 mm falling over 48 hours. Low-lying areas in the old city "
            "reported flooding. The Greater Hyderabad Municipal Corporation deployed "
            "emergency pumping units across 18 wards. The Meteorological Department "
            "warned of continued heavy rain through the weekend."
        ),
        "section": "City",
    },
    {
        "headline": "Opposition Demands Probe Into Tender Irregularities",
        "body": (
            "The opposition YSRCP on Friday demanded a Central Bureau of Investigation "
            "probe into alleged irregularities in infrastructure tenders awarded over "
            "the past six months. Party president Y.S. Jagan Mohan Reddy said documents "
            "obtained through RTI show inflated estimates in three major road projects. "
            "The ruling TDP denied the allegations and called them politically motivated."
        ),
        "section": "Politics",
    },
    {
        "headline": "Tech Hub Inaugurated at Vizag Port",
        "body": (
            "A technology and innovation hub was inaugurated at Visakhapatnam Port Trust "
            "on Thursday, aimed at attracting IT and logistics startups to the region. "
            "The 50,000 sq ft facility can host up to 200 companies. Officials expect "
            "the hub to generate 5,000 direct jobs within three years."
        ),
        "section": "Business",
    },
    {
        "headline": "State Announces Free Coaching for Competitive Exams",
        "body": (
            "The Andhra Pradesh government announced a free coaching programme for "
            "students from economically weaker sections preparing for UPSC, APPSC, "
            "and banking exams. The scheme covers 10,000 seats across 13 centres. "
            "Applications open next Monday via the official state portal."
        ),
        "section": "Education",
    },
    {
        "headline": "India-Pakistan Talks Resume in Geneva",
        "body": (
            "India and Pakistan resumed back-channel talks in Geneva on Friday after a "
            "three-month pause, diplomatic sources confirmed. The discussions focused on "
            "the Line of Control situation and trade normalisation. No official statement "
            "was issued by either side following the closed-door session."
        ),
        "section": "National",
    },
]

MASTHEAD = "THE MORNING CHRONICLE"
DATE_LINE = "Saturday, June 7, 2026   |   Hyderabad Edition   |   Price: Rs 5"


def build_pdf() -> None:
    from reportlab.lib.pagesizes import A3
    from reportlab.lib.units import mm
    from reportlab.lib.colors import black, HexColor
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY

    PAGE_W, PAGE_H = A3
    MARGIN = 12 * mm
    COL_GAP = 4 * mm
    N_COLS = 7
    col_w = (PAGE_W - 2 * MARGIN - (N_COLS - 1) * COL_GAP) / N_COLS

    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A3,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
    )

    styles = getSampleStyleSheet()
    masthead_style = ParagraphStyle(
        "Masthead", fontSize=36, leading=40, alignment=TA_CENTER,
        fontName="Helvetica-Bold", spaceAfter=2,
    )
    dateline_style = ParagraphStyle(
        "Dateline", fontSize=8, leading=10, alignment=TA_CENTER,
        fontName="Helvetica", spaceAfter=4,
    )
    hl_full_style = ParagraphStyle(
        "HeadlineFull", fontSize=22, leading=26, alignment=TA_LEFT,
        fontName="Helvetica-Bold", spaceAfter=3, spaceBefore=6,
    )
    hl_half_style = ParagraphStyle(
        "HeadlineHalf", fontSize=16, leading=20, alignment=TA_LEFT,
        fontName="Helvetica-Bold", spaceAfter=2, spaceBefore=4,
    )
    hl_col_style = ParagraphStyle(
        "HeadlineCol", fontSize=12, leading=15, alignment=TA_LEFT,
        fontName="Helvetica-Bold", spaceAfter=2, spaceBefore=4,
    )
    body_style = ParagraphStyle(
        "Body", fontSize=8, leading=11, alignment=TA_JUSTIFY,
        fontName="Times-Roman", spaceAfter=4,
    )
    section_style = ParagraphStyle(
        "Section", fontSize=7, leading=9, alignment=TA_LEFT,
        fontName="Helvetica-BoldOblique", textColor=HexColor("#555555"),
        spaceAfter=1,
    )

    story = []

    # Masthead
    story.append(Paragraph(MASTHEAD, masthead_style))
    story.append(HRFlowable(width="100%", thickness=2, color=black))
    story.append(Paragraph(DATE_LINE, dateline_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=black))
    story.append(Spacer(1, 4 * mm))

    # Lead story — spans all 7 columns
    a0 = ARTICLES[0]
    story.append(Paragraph(a0["section"].upper(), section_style))
    story.append(Paragraph(a0["headline"], hl_full_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=black))

    # 7-column table for remaining body + other articles
    # Col 0-2: lead story body | Col 3-4: art[1] | Col 5-6: art[2]
    def cell(art: dict, hl_style=hl_half_style) -> list:
        return [
            Paragraph(art["section"].upper(), section_style),
            Paragraph(art["headline"], hl_style),
            Paragraph(art["body"], body_style),
        ]

    def empty_cell() -> list:
        return [Spacer(1, 1)]

    col_3 = col_w * 3 + COL_GAP * 2
    col_2 = col_w * 2 + COL_GAP
    col_2b = col_w * 2 + COL_GAP

    # Row 1: lead(3col) | art1(2col) | art2(2col)
    row1 = Table(
        [[
            [Paragraph(a0["body"], body_style)],
            cell(ARTICLES[1]),
            cell(ARTICLES[2]),
        ]],
        colWidths=[col_3, col_2, col_2b],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), COL_GAP),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LINEAFTER", (0, 0), (1, -1), 0.3, HexColor("#cccccc")),
        ]),
    )
    story.append(row1)
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#cccccc")))
    story.append(Spacer(1, 3 * mm))

    # Row 2: art3(2col) | art4(3col) | art5(2col)
    row2 = Table(
        [[
            cell(ARTICLES[3], hl_col_style),
            cell(ARTICLES[4], hl_col_style),
            cell(ARTICLES[5], hl_col_style),
        ]],
        colWidths=[col_2, col_3, col_2b],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), COL_GAP),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LINEAFTER", (0, 0), (1, -1), 0.3, HexColor("#cccccc")),
        ]),
    )
    story.append(row2)

    doc.build(story)
    print(f"[OK] Synthetic PDF written -> {OUTPUT}  ({OUTPUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    build_pdf()
