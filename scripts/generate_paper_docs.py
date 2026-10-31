#!/usr/bin/env python3
"""
generate_paper_docs.py
======================
Generates high-quality, publication-ready DOCX and PDF versions of the Lumina & SmartSwitch paper.
Uses ReportLab with custom styling:
- Proper XML escaping (&, <, >) to avoid broken formatting.
- Clean display of formulas, tables, callouts, and code blocks.
- Running headers and footers with dynamic page numbering.
"""

import os
import re
import sys
import html

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Preformatted,
    KeepTogether,
    HRFlowable,
)
from reportlab.pdfgen import canvas

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD_PATH = os.path.join(
    os.path.expanduser("~"),
    ".gemini/antigravity/brain/0ff41455-d925-40ff-b33b-55704dc3e27c/lumina_smartswitch_research_paper.md"
)
OUTPUT_DIR = PROJECT_ROOT
DOCX_PATH = os.path.join(OUTPUT_DIR, "lumina_smartswitch_research_paper.docx")
PDF_PATH = os.path.join(OUTPUT_DIR, "lumina_smartswitch_research_paper.pdf")


def clean_markdown_for_reportlab(text):
    """
    Safely converts markdown inline formatting into valid ReportLab XML.
    Escapes raw XML entities first so ReportLab parser never crashes.
    """
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    parts = re.split(r'(`[^`]+`)', text)
    safe_parts = []
    for part in parts:
        if part.startswith('`') and part.endswith('`') and len(part) > 1:
            code_content = html.escape(part[1:-1])
            safe_parts.append(f'<font face="Courier" color="#0F172A"><b>{code_content}</b></font>')
        else:
            p = html.escape(part)
            p = re.sub(r'\*\*\*([^*]+)\*\*\*', r'<b><i>\1</i></b>', p)
            p = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', p)
            p = re.sub(r'\*([^*]+)\*', r'<i>\1</i>', p)
            p = re.sub(r'\$([^\$]+)\$', r'<i>\1</i>', p)
            safe_parts.append(p)
    return ''.join(safe_parts)


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Times-Roman", 8.5)
        self.setFillColor(colors.HexColor("#475569"))
        if self._pageNumber > 1:
            self.drawString(54, 752, "Lumina & SmartSwitch: Resilient Edge LLM Serving via Analytical Memory Bounds")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(54, 746, 558, 746)

        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(54, 46, 558, 46)
        text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(558, 34, text)
        self.drawString(54, 34, "Confidential - Submitted for Peer Review")
        self.restoreState()


def build_docx(md_content, output_path):
    doc = Document()
    for s in doc.sections:
        s.top_margin = Inches(1.0)
        s.bottom_margin = Inches(1.0)
        s.left_margin = Inches(1.0)
        s.right_margin = Inches(1.0)

    normal_style = doc.styles['Normal']
    normal_style.font.name = 'Times New Roman'
    normal_style.font.size = Pt(11)
    normal_style.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)

    lines = md_content.split('\n')
    i = 0
    in_code = False
    code_lines = []

    while i < len(lines):
        line = lines[i]
        if line.strip().startswith('```'):
            if in_code:
                in_code = False
                code_text = '\n'.join(code_lines)
                tbl = doc.add_table(rows=1, cols=1)
                tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
                cell = tbl.cell(0, 0)
                shd = parse_xml(r'<w:shd {} w:fill="F8FAFC"/>'.format(nsdecls('w')))
                cell._tc.get_or_add_tcPr().append(shd)
                cp = cell.paragraphs[0]
                cp.paragraph_format.space_before = Pt(4)
                cp.paragraph_format.space_after = Pt(4)
                run = cp.add_run(code_text)
                run.font.name = 'Courier New'
                run.font.size = Pt(8.5)
                code_lines = []
            else:
                in_code = True
                code_lines = []
            i += 1
            continue

        if in_code:
            code_lines.append(line)
            i += 1
            continue

        if line.strip().startswith('|') and '|' in line[1:]:
            tbl_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                tbl_lines.append(lines[i].strip())
                i += 1
            if len(tbl_lines) >= 3:
                hdrs = [c.strip() for c in tbl_lines[0].split('|')[1:-1]]
                data_rows = []
                for r in tbl_lines[2:]:
                    cols = [c.strip() for c in r.split('|')[1:-1]]
                    if len(cols) == len(hdrs):
                        data_rows.append(cols)
                table = doc.add_table(rows=len(data_rows) + 1, cols=len(hdrs))
                table.alignment = WD_TABLE_ALIGNMENT.CENTER
                hdr_cells = table.rows[0].cells
                for idx, t in enumerate(hdrs):
                    hdr_cells[idx].text = re.sub(r'[*_$`]', '', t)
                    shd = parse_xml(r'<w:shd {} w:fill="1E3A8A"/>'.format(nsdecls('w')))
                    hdr_cells[idx]._tc.get_or_add_tcPr().append(shd)
                    p = hdr_cells[idx].paragraphs[0]
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    for r in p.runs:
                        r.font.bold = True
                        r.font.name = 'Times New Roman'
                        r.font.size = Pt(9.5)
                        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                for r_idx, rd in enumerate(data_rows):
                    row_cells = table.rows[r_idx + 1].cells
                    for c_idx, val in enumerate(rd):
                        row_cells[c_idx].text = re.sub(r'[*_$`]', '', val)
                        if r_idx % 2 == 1:
                            shd = parse_xml(r'<w:shd {} w:fill="F1F5F9"/>'.format(nsdecls('w')))
                            row_cells[c_idx]._tc.get_or_add_tcPr().append(shd)
                        for p in row_cells[c_idx].paragraphs:
                            for r in p.runs:
                                r.font.name = 'Times New Roman'
                                r.font.size = Pt(9)
                doc.add_paragraph().paragraph_format.space_after = Pt(4)
            continue

        if line.startswith('# '):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(line[2:].strip())
            run.font.bold = True
            run.font.size = Pt(17)
            run.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)
            p.paragraph_format.space_after = Pt(8)
        elif line.startswith('## '):
            p = doc.add_paragraph()
            run = p.add_run(line[3:].strip())
            run.font.bold = True
            run.font.size = Pt(13)
            run.font.color.rgb = RGBColor(0x1E, 0x3A, 0x8A)
            p.paragraph_format.space_before = Pt(12)
            p.paragraph_format.space_after = Pt(4)
        elif line.startswith('### '):
            p = doc.add_paragraph()
            run = p.add_run(line[4:].strip())
            run.font.bold = True
            run.font.size = Pt(11.5)
            run.font.color.rgb = RGBColor(0x33, 0x41, 0x55)
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after = Pt(3)
        elif line.strip() == '---':
            pass
        elif line.strip() != '':
            clean = re.sub(r'[*_$`]', '', line)
            doc.add_paragraph(clean)
        i += 1

    doc.save(output_path)
    print(f"[+] DOCX successfully created: {output_path}")


def build_pdf(md_content, output_path):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54,
    )

    styles = getSampleStyleSheet()

    body_style = ParagraphStyle(
        'AcadBody',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor("#1E293B"),
        spaceAfter=5,
        alignment=4,  # Justified
    )

    title_style = ParagraphStyle(
        'AcadTitle',
        parent=styles['Normal'],
        fontName='Times-Bold',
        fontSize=15.5,
        leading=19,
        alignment=1,  # Center
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=8,
    )

    author_style = ParagraphStyle(
        'AcadAuthor',
        parent=styles['Normal'],
        fontName='Times-Italic',
        fontSize=9,
        leading=13,
        alignment=1,
        textColor=colors.HexColor("#475569"),
        spaceAfter=12,
    )

    h1_style = ParagraphStyle(
        'AcadH1',
        parent=styles['Normal'],
        fontName='Times-Bold',
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#1E3A8A"),
        spaceBefore=11,
        spaceAfter=4,
        keepWithNext=True,
    )

    h2_style = ParagraphStyle(
        'AcadH2',
        parent=styles['Normal'],
        fontName='Times-Bold',
        fontSize=10.5,
        leading=13.5,
        textColor=colors.HexColor("#1E293B"),
        spaceBefore=8,
        spaceAfter=3,
        keepWithNext=True,
    )

    code_block_style = ParagraphStyle(
        'AcadCode',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#0F172A"),
    )

    callout_style = ParagraphStyle(
        'AcadCallout',
        parent=styles['Normal'],
        fontName='Times-Italic',
        fontSize=9,
        leading=12.5,
        textColor=colors.HexColor("#991B1B"),
        spaceBefore=4,
        spaceAfter=4,
    )

    math_block_style = ParagraphStyle(
        'AcadMath',
        parent=styles['Normal'],
        fontName='Times-Italic',
        fontSize=9.5,
        leading=13.5,
        alignment=1,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=4,
        spaceAfter=6,
    )

    story = []
    lines = md_content.split('\n')
    i = 0
    in_code_block = False
    code_lines = []

    while i < len(lines):
        line = lines[i]

        if line.strip().startswith('```'):
            if in_code_block:
                in_code_block = False
                code_text = html.escape('\n'.join(code_lines))
                p = Preformatted(code_text, code_block_style)
                tbl = Table([[p]], colWidths=[504])
                tbl.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                    ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('LEFTPADDING', (0, 0), (-1, -1), 8),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ]))
                story.append(tbl)
                story.append(Spacer(1, 6))
                code_lines = []
            else:
                in_code_block = True
                code_lines = []
            i += 1
            continue

        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        # Display math $$ ... $$
        if line.strip().startswith('$$') and line.strip().endswith('$$') and len(line.strip()) > 4:
            math_text = html.escape(line.strip()[2:-2].strip())
            story.append(Paragraph(f"<b>[Equation]</b> {math_text}", math_block_style))
            i += 1
            continue

        # Callout alerts (> [!WARNING], etc.)
        if line.strip().startswith('>'):
            clean_callout = clean_markdown_for_reportlab(line.strip().lstrip('> ').strip())
            p = Paragraph(clean_callout, callout_style)
            tbl = Table([[p]], colWidths=[504])
            tbl.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#FEF2F2")),
                ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor("#EF4444")),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 5))
            i += 1
            continue

        # Markdown Table Detection
        if line.strip().startswith('|') and '|' in line[1:]:
            tbl_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                tbl_lines.append(lines[i].strip())
                i += 1

            if len(tbl_lines) >= 3:
                raw_headers = [c.strip() for c in tbl_lines[0].split('|')[1:-1]]
                data_rows = []
                for r in tbl_lines[2:]:
                    cols = [c.strip() for c in r.split('|')[1:-1]]
                    if len(cols) == len(raw_headers):
                        data_rows.append(cols)

                col_w = 504.0 / len(raw_headers)
                t_data = []

                hdr_cells = [
                    Paragraph(f"<b>{clean_markdown_for_reportlab(h)}</b>", ParagraphStyle(
                        'HStyle', parent=body_style, fontSize=8, leading=10.5, textColor=colors.white, alignment=1
                    )) for h in raw_headers
                ]
                t_data.append(hdr_cells)

                for r in data_rows:
                    row_cells = [
                        Paragraph(clean_markdown_for_reportlab(c), ParagraphStyle(
                            'RStyle', parent=body_style, fontSize=7.5, leading=9.5, textColor=colors.HexColor("#1E293B")
                        )) for c in r
                    ]
                    t_data.append(row_cells)

                t = Table(t_data, colWidths=[col_w] * len(raw_headers), repeatRows=1)
                t_style = [
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                    ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
                    ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                    ('TOPPADDING', (0, 0), (-1, -1), 3),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                    ('LEFTPADDING', (0, 0), (-1, -1), 4),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]
                for r_idx in range(1, len(t_data)):
                    if r_idx % 2 == 0:
                        t_style.append(('BACKGROUND', (0, r_idx), (-1, r_idx), colors.HexColor("#F8FAFC")))
                t.setStyle(TableStyle(t_style))
                story.append(t)
                story.append(Spacer(1, 5))
            continue

        if line.startswith('# '):
            story.append(Paragraph(clean_markdown_for_reportlab(line[2:].strip()), title_style))
        elif line.startswith('## '):
            story.append(Paragraph(clean_markdown_for_reportlab(line[3:].strip()), h1_style))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CBD5E1"), spaceAfter=4, spaceBefore=1))
        elif line.startswith('### '):
            story.append(Paragraph(clean_markdown_for_reportlab(line[4:].strip()), h2_style))
        elif line.startswith('#### '):
            story.append(Paragraph(f"<b><i>{clean_markdown_for_reportlab(line[5:].strip())}</i></b>", h2_style))
        elif line.strip() == '---':
            story.append(Spacer(1, 4))
        elif line.strip() == '':
            pass
        else:
            text = clean_markdown_for_reportlab(line)
            if 'Authors:' in line or 'Keywords:' in line:
                story.append(Paragraph(text, author_style))
            elif line.strip().startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.', '- ', '* ')):
                list_style = ParagraphStyle('AcadList', parent=body_style, leftIndent=12, spaceAfter=3)
                story.append(Paragraph(text, list_style))
            else:
                story.append(Paragraph(text, body_style))

        i += 1

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[+] PDF successfully created: {output_path}")


def main():
    if not os.path.exists(MD_PATH):
        print(f"[!] Markdown source not found: {MD_PATH}")
        sys.exit(1)

    with open(MD_PATH, 'r', encoding='utf-8') as f:
        md_content = f.read()

    print("[*] Generating DOCX...")
    build_docx(md_content, DOCX_PATH)

    print("[*] Generating publication-grade PDF...")
    build_pdf(md_content, PDF_PATH)

    # Also copy PDF into conversation artifacts directory for easy download
    artifact_dir = os.path.dirname(MD_PATH)
    artifact_pdf = os.path.join(artifact_dir, "lumina_smartswitch_research_paper.pdf")
    import shutil
    shutil.copyfile(PDF_PATH, artifact_pdf)
    print(f"[+] Copied PDF to artifact directory: {artifact_pdf}")


if __name__ == '__main__':
    main()
