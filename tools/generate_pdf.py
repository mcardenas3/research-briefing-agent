"""
generate_pdf.py
Generates a formatted research digest PDF from summarized papers.

Structure:
  1. Cover page (title, author, date, research question)
  2. Table of contents (subtopics + paper titles)
  3. One section per subtopic with paper entries:
     Title, Authors & Year, Link, Summary, Findings, Results, Conclusion

Output: .tmp/research_digest_YYYY-MM-DD.pdf
"""

import argparse
import json
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents


# ── Colour palette ──────────────────────────────────────────────────────────
DARK_BLUE = colors.HexColor("#1B3A5C")
MID_BLUE = colors.HexColor("#2E6DA4")
LIGHT_BLUE = colors.HexColor("#E8F0F8")
ACCENT = colors.HexColor("#4A90D9")
TEXT = colors.HexColor("#2C2C2C")
MUTED = colors.HexColor("#6B7280")


# ── Custom doc template with header/footer ──────────────────────────────────
class ResearchDigestDoc(BaseDocTemplate):
    def __init__(self, filename, title, **kwargs):
        super().__init__(filename, **kwargs)
        self.doc_title = title
        self.page_width, self.page_height = A4
        self._setup_templates()

    def _setup_templates(self):
        margin = 2.2 * cm
        body_frame = Frame(
            margin, margin,
            self.page_width - 2 * margin,
            self.page_height - 3 * margin,
            id="body",
        )
        self.addPageTemplates([
            PageTemplate(id="cover", frames=[body_frame]),
            PageTemplate(
                id="main",
                frames=[body_frame],
                onPage=self._draw_header_footer,
            ),
        ])

    def _draw_header_footer(self, canvas, doc):
        canvas.saveState()
        w, h = A4
        margin = 2.2 * cm

        # Header line
        canvas.setStrokeColor(ACCENT)
        canvas.setLineWidth(0.5)
        canvas.line(margin, h - 1.8 * cm, w - margin, h - 1.8 * cm)

        # Header text
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(margin, h - 1.5 * cm, self.doc_title[:80])
        canvas.drawRightString(w - margin, h - 1.5 * cm, "Research Digest")

        # Footer
        canvas.setFont("Helvetica", 7)
        canvas.drawCentredString(w / 2, 1.2 * cm, f"Page {doc.page}")
        canvas.line(margin, 1.6 * cm, w - margin, 1.6 * cm)
        canvas.restoreState()


def build_styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "cover_title",
            fontName="Helvetica-Bold",
            fontSize=22,
            textColor=DARK_BLUE,
            alignment=TA_CENTER,
            spaceAfter=16,
            leading=28,
        ),
        "cover_subtitle": ParagraphStyle(
            "cover_subtitle",
            fontName="Helvetica",
            fontSize=12,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
        "cover_rq": ParagraphStyle(
            "cover_rq",
            fontName="Helvetica-Oblique",
            fontSize=11,
            textColor=TEXT,
            alignment=TA_CENTER,
            spaceAfter=8,
            leading=16,
        ),
        "section_heading": ParagraphStyle(
            "section_heading",
            fontName="Helvetica-Bold",
            fontSize=15,
            textColor=DARK_BLUE,
            spaceBefore=18,
            spaceAfter=6,
        ),
        "paper_title": ParagraphStyle(
            "paper_title",
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=MID_BLUE,
            spaceBefore=14,
            spaceAfter=2,
        ),
        "paper_meta": ParagraphStyle(
            "paper_meta",
            fontName="Helvetica",
            fontSize=8,
            textColor=MUTED,
            spaceAfter=2,
        ),
        "paper_link": ParagraphStyle(
            "paper_link",
            fontName="Helvetica",
            fontSize=8,
            textColor=ACCENT,
            spaceAfter=6,
        ),
        "label": ParagraphStyle(
            "label",
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=DARK_BLUE,
            spaceBefore=4,
            spaceAfter=1,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Helvetica",
            fontSize=9,
            textColor=TEXT,
            leading=13,
            alignment=TA_JUSTIFY,
            spaceAfter=3,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            fontName="Helvetica",
            fontSize=9,
            textColor=TEXT,
            leading=13,
            leftIndent=12,
            bulletIndent=0,
            spaceAfter=1,
        ),
        "toc_section": ParagraphStyle(
            "toc_section",
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=DARK_BLUE,
            spaceBefore=6,
        ),
        "toc_paper": ParagraphStyle(
            "toc_paper",
            fontName="Helvetica",
            fontSize=9,
            textColor=TEXT,
            leftIndent=16,
        ),
        "abstract_label": ParagraphStyle(
            "abstract_label",
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=MUTED,
            spaceBefore=4,
            spaceAfter=1,
        ),
        "abstract_body": ParagraphStyle(
            "abstract_body",
            fontName="Helvetica-Oblique",
            fontSize=8,
            textColor=MUTED,
            leading=12,
            alignment=TA_JUSTIFY,
            spaceAfter=4,
        ),
    }


def safe_para(text: str, style) -> Paragraph:
    """Escape HTML special chars for ReportLab Paragraph."""
    if not text:
        text = "N/A"
    text = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(text, style)


def build_pdf(papers: list[dict], context: dict, output_path: str):
    title = context.get("title", "Research Digest")
    author = context.get("author", "")
    research_question = context.get("research_question", "")
    today = date.today().strftime("%B %d, %Y")

    doc = ResearchDigestDoc(
        output_path,
        title=title,
        pagesize=A4,
        leftMargin=2.2 * cm,
        rightMargin=2.2 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.2 * cm,
    )

    S = build_styles()
    story = []

    # ── Cover page ────────────────────────────────────────────────────────
    story.append(Spacer(1, 3 * cm))
    story.append(safe_para("Research Paper Digest", S["cover_subtitle"]))
    story.append(Spacer(1, 0.5 * cm))
    story.append(safe_para(title, S["cover_title"]))
    story.append(Spacer(1, 0.8 * cm))

    if author:
        story.append(safe_para(author, S["cover_subtitle"]))
    story.append(safe_para(today, S["cover_subtitle"]))
    story.append(Spacer(1, 1.2 * cm))

    if research_question:
        story.append(HRFlowable(width="60%", color=ACCENT, hAlign="CENTER"))
        story.append(Spacer(1, 0.4 * cm))
        story.append(safe_para(f"Research Question: {research_question}", S["cover_rq"]))
        story.append(Spacer(1, 0.4 * cm))
        story.append(HRFlowable(width="60%", color=ACCENT, hAlign="CENTER"))

    story.append(Spacer(1, 1 * cm))
    story.append(safe_para(f"This digest covers {len(papers)} papers organized across {len(set(p.get('subtopic','') for p in papers))} subtopics.", S["cover_subtitle"]))

    story.append(PageBreak())

    # ── Table of Contents ─────────────────────────────────────────────────
    story.append(safe_para("Table of Contents", S["section_heading"]))
    story.append(HRFlowable(width="100%", color=LIGHT_BLUE, thickness=2))
    story.append(Spacer(1, 0.3 * cm))

    # Group by subtopic for TOC
    subtopic_order = []
    subtopic_papers: dict[str, list] = {}
    for paper in papers:
        st = paper.get("subtopic") or "Uncategorized"
        if st not in subtopic_papers:
            subtopic_papers[st] = []
            subtopic_order.append(st)
        subtopic_papers[st].append(paper)

    for st in subtopic_order:
        story.append(safe_para(st, S["toc_section"]))
        for p in subtopic_papers[st]:
            year = f" ({p.get('year', '')})" if p.get("year") else ""
            story.append(safe_para(f"• {p.get('title', 'Untitled')}{year}", S["toc_paper"]))
        story.append(Spacer(1, 0.2 * cm))

    story.append(PageBreak())

    # ── Sections per subtopic ─────────────────────────────────────────────
    doc.handle_nextPageTemplate("main")

    for st in subtopic_order:
        # Section header
        story.append(safe_para(st, S["section_heading"]))
        story.append(HRFlowable(width="100%", color=ACCENT, thickness=1.5))
        story.append(Spacer(1, 0.2 * cm))

        for paper in subtopic_papers[st]:
            title_text = paper.get("title") or "Untitled"
            authors = paper.get("authors") or ""
            year = paper.get("year") or ""
            url = paper.get("url") or ""
            doi = paper.get("doi") or ""

            abstract = paper.get("abstract") or ""
            summary = paper.get("summary") or ""
            findings = paper.get("findings") or []
            results = paper.get("results") or ""
            conclusion = paper.get("conclusion") or ""

            # Paper title
            story.append(safe_para(title_text, S["paper_title"]))

            # Authors & year
            meta = f"{authors}  |  {year}" if year else authors
            story.append(safe_para(meta, S["paper_meta"]))

            # Clickable link
            if url:
                display = url[:80] + ("..." if len(url) > 80 else "")
                link_para = Paragraph(
                    f'<link href="{url}" color="#4A90D9">{display}</link>',
                    S["paper_link"],
                )
                story.append(link_para)
            elif doi:
                story.append(safe_para(f"DOI: {doi}", S["paper_link"]))

            # Author abstract (italicised, muted — original author text)
            if abstract:
                story.append(safe_para("Author Abstract", S["abstract_label"]))
                story.append(safe_para(abstract, S["abstract_body"]))

            content_rows = []

            if summary:
                content_rows.append(("Summary", summary))
            if findings:
                bullets = "\n".join(f"• {f}" for f in findings if f)
                content_rows.append(("Key Findings", bullets))
            if results:
                content_rows.append(("Results", results))
            if conclusion:
                content_rows.append(("Conclusion", conclusion))

            for label, text in content_rows:
                story.append(safe_para(label, S["label"]))
                # Multi-line text for findings
                if "\n" in text:
                    for line in text.split("\n"):
                        if line.strip():
                            story.append(safe_para(line, S["bullet"]))
                else:
                    story.append(safe_para(text, S["body"]))

            story.append(HRFlowable(width="100%", color=LIGHT_BLUE, thickness=0.5))

        story.append(PageBreak())

    doc.build(story)
    print(f"PDF saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=".tmp/papers_summarized.json")
    parser.add_argument("--context", default=".tmp/proposal_context.json")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    papers = json.loads(Path(args.input).read_text(encoding="utf-8"))
    context = json.loads(Path(args.context).read_text(encoding="utf-8"))

    if not args.output:
        today = date.today().strftime("%Y-%m-%d")
        args.output = f".tmp/research_digest_{today}.pdf"

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    print(f"Generating PDF with {len(papers)} papers...")
    build_pdf(papers, context, args.output)


if __name__ == "__main__":
    main()
