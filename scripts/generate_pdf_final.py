#!/usr/bin/env python3
"""
generate_pdf_final.py
Generates a clean, well-formatted academic PDF from the research paper markdown.
Handles: section headings, tables, code blocks, math (unicode), bullet lists, bold/italic.
"""

import os, re
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph,
    Spacer, Table, TableStyle, HRFlowable, KeepTogether,
    PageBreak, Preformatted
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus.flowables import HRFlowable

# ── paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD_PATH = os.path.join(
    os.path.expanduser("~"),
    ".gemini/antigravity/brain/0ff41455-d925-40ff-b33b-55704dc3e27c/lumina_smartswitch_research_paper.md"
)
OUT_PDF = os.path.join(PROJECT_ROOT, "lumina_smartswitch_FINAL.pdf")

# ── colour palette ────────────────────────────────────────────────────────────
C_TITLE   = colors.HexColor("#0A2540")
C_HEAD1   = colors.HexColor("#1A3A5C")
C_HEAD2   = colors.HexColor("#2C5F8A")
C_HEAD3   = colors.HexColor("#3A7BB5")
C_ACCENT  = colors.HexColor("#1565C0")
C_CODE_BG = colors.HexColor("#F4F6F8")
C_TABLE_H = colors.HexColor("#1A3A5C")
C_TABLE_R = colors.HexColor("#EBF0F7")
C_LINE    = colors.HexColor("#C0CDD8")
C_NOTE_BG = colors.HexColor("#FFF8E1")
C_WARN_BG = colors.HexColor("#FFF3E0")
C_TIP_BG  = colors.HexColor("#E8F5E9")
C_TEXT    = colors.HexColor("#1A1A2E")
C_MUTED   = colors.HexColor("#546E7A")

PAGE_W, PAGE_H = letter
MARGIN_INNER = 0.85 * inch
MARGIN_OUTER = 0.85 * inch
MARGIN_TOP   = 1.0  * inch
MARGIN_BOT   = 0.9  * inch
TEXT_W = PAGE_W - MARGIN_INNER - MARGIN_OUTER

# ── styles ────────────────────────────────────────────────────────────────────
def build_styles():
    s = {}
    base = dict(fontName="Times-Roman", fontSize=10, leading=14,
                textColor=C_TEXT, alignment=TA_JUSTIFY)

    s["Normal"]    = ParagraphStyle("Normal", spaceAfter=4, **base)
    s["Body"]      = ParagraphStyle("Body", firstLineIndent=0, spaceBefore=2, spaceAfter=6, **base)

    s["Title"]     = ParagraphStyle("Title",
        fontName="Times-Bold", fontSize=17, leading=22,
        textColor=C_TITLE, alignment=TA_CENTER, spaceAfter=6, spaceBefore=0)
    s["Subtitle"]  = ParagraphStyle("Subtitle",
        fontName="Times-Roman", fontSize=10, leading=14,
        textColor=C_MUTED, alignment=TA_CENTER, spaceAfter=16)
    s["Abstract"]  = ParagraphStyle("Abstract",
        fontName="Times-Roman", fontSize=9.5, leading=13.5,
        textColor=C_TEXT, alignment=TA_JUSTIFY,
        leftIndent=24, rightIndent=24, spaceBefore=4, spaceAfter=8)
    s["AbstractLabel"] = ParagraphStyle("AbstractLabel",
        fontName="Times-Bold", fontSize=9.5, leading=13.5,
        textColor=C_TITLE, alignment=TA_CENTER, spaceAfter=3)

    s["H1"] = ParagraphStyle("H1",
        fontName="Times-Bold", fontSize=13, leading=17,
        textColor=C_HEAD1, spaceBefore=14, spaceAfter=4, keepWithNext=1)
    s["H2"] = ParagraphStyle("H2",
        fontName="Times-Bold", fontSize=11.5, leading=15,
        textColor=C_HEAD2, spaceBefore=10, spaceAfter=3, keepWithNext=1)
    s["H3"] = ParagraphStyle("H3",
        fontName="Times-BoldItalic", fontSize=10.5, leading=14,
        textColor=C_HEAD3, spaceBefore=8, spaceAfter=2, keepWithNext=1)
    s["H4"] = ParagraphStyle("H4",
        fontName="Times-Bold", fontSize=10, leading=14,
        textColor=C_HEAD3, spaceBefore=6, spaceAfter=2, keepWithNext=1)

    s["Bullet"] = ParagraphStyle("Bullet",
        fontName="Times-Roman", fontSize=10, leading=14,
        textColor=C_TEXT, leftIndent=18, firstLineIndent=-10,
        spaceBefore=1, spaceAfter=2, alignment=TA_LEFT)
    s["Bullet2"] = ParagraphStyle("Bullet2",
        fontName="Times-Roman", fontSize=9.5, leading=13,
        textColor=C_TEXT, leftIndent=32, firstLineIndent=-10,
        spaceBefore=0, spaceAfter=1, alignment=TA_LEFT)
    s["NumItem"]  = ParagraphStyle("NumItem",
        fontName="Times-Roman", fontSize=10, leading=14,
        textColor=C_TEXT, leftIndent=22, firstLineIndent=-14,
        spaceBefore=1, spaceAfter=2, alignment=TA_JUSTIFY)

    s["Code"] = ParagraphStyle("Code",
        fontName="Courier", fontSize=8, leading=11,
        textColor=colors.HexColor("#1B3A4B"),
        backColor=C_CODE_BG,
        leftIndent=10, rightIndent=10,
        spaceBefore=4, spaceAfter=4, alignment=TA_LEFT)

    s["Caption"] = ParagraphStyle("Caption",
        fontName="Times-Italic", fontSize=9, leading=12,
        textColor=C_MUTED, alignment=TA_CENTER,
        spaceBefore=3, spaceAfter=8)
    s["TableH"] = ParagraphStyle("TableH",
        fontName="Times-Bold", fontSize=8.5, leading=11,
        textColor=colors.white, alignment=TA_CENTER)
    s["TableC"] = ParagraphStyle("TableC",
        fontName="Times-Roman", fontSize=8.5, leading=11,
        textColor=C_TEXT, alignment=TA_LEFT)
    s["TableCB"] = ParagraphStyle("TableCB",
        fontName="Times-Bold", fontSize=8.5, leading=11,
        textColor=C_TEXT, alignment=TA_LEFT)
    s["Note"] = ParagraphStyle("Note",
        fontName="Times-Italic", fontSize=9, leading=12.5,
        textColor=colors.HexColor("#37474F"),
        leftIndent=12, rightIndent=12, spaceBefore=4, spaceAfter=8)
    s["FooterStyle"] = ParagraphStyle("FooterStyle",
        fontName="Times-Roman", fontSize=8, textColor=C_MUTED, alignment=TA_CENTER)
    s["Eq"] = ParagraphStyle("Eq",
        fontName="Times-Italic", fontSize=10, leading=15,
        textColor=C_TEXT, alignment=TA_CENTER,
        leftIndent=20, rightIndent=20, spaceBefore=6, spaceAfter=6)
    return s

STYLES = build_styles()

# ── page template with header/footer ─────────────────────────────────────────
class LuminaDocTemplate(BaseDocTemplate):
    def __init__(self, filename, **kw):
        super().__init__(filename, **kw)
        frame = Frame(MARGIN_INNER, MARGIN_BOT, TEXT_W,
                      PAGE_H - MARGIN_TOP - MARGIN_BOT, id="main")
        self.addPageTemplates([PageTemplate(id="main", frames=[frame],
                                            onPage=self._draw_chrome)])

    def _draw_chrome(self, canvas, doc):
        canvas.saveState()
        # Header line
        canvas.setStrokeColor(C_LINE)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN_INNER, PAGE_H - MARGIN_TOP + 8,
                    PAGE_W - MARGIN_OUTER, PAGE_H - MARGIN_TOP + 8)
        # Header text
        canvas.setFont("Times-Roman", 7.5)
        canvas.setFillColor(C_MUTED)
        canvas.drawString(MARGIN_INNER, PAGE_H - MARGIN_TOP + 13,
                          "Lumina & SmartSwitch — Resilient Edge LLM Serving")
        canvas.drawRightString(PAGE_W - MARGIN_OUTER, PAGE_H - MARGIN_TOP + 13,
                               "Lumina Systems Research Team")
        # Footer line
        canvas.line(MARGIN_INNER, MARGIN_BOT - 10,
                    PAGE_W - MARGIN_OUTER, MARGIN_BOT - 10)
        # Page number
        canvas.drawCentredString(PAGE_W / 2, MARGIN_BOT - 22,
                                 f"— {doc.page} —")
        canvas.restoreState()

# ── text helpers ──────────────────────────────────────────────────────────────
def esc(t):
    """Escape XML special chars for ReportLab Paragraph."""
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return t

def math_unicode(t):
    """Convert common LaTeX fragments to readable Unicode/text for PDF."""
    subs = [
        (r'\text{s}', 's'), (r'\text{T/s}', 'T/s'), (r'\text{GB/s}', 'GB/s'),
        (r'\text{GB}', 'GB'), (r'\text{ms}', 'ms'), (r'\times', '×'),
        (r'\ge', '≥'), (r'\le', '≤'), (r'\cdot', '·'), (r'\pm', '±'),
        (r'\approx', '≈'), (r'\ne', '≠'), (r'\infty', '∞'),
        (r'\alpha', 'α'), (r'\beta', 'β'), (r'\eta', 'η'), (r'\kappa', 'κ'),
        (r'\theta', 'θ'), (r'\delta', 'δ'), (r'\epsilon', 'ε'), (r'\sigma', 'σ'),
        (r'\mu', 'μ'), (r'\mathcal{C}', 'C'), (r'\mathcal{F}', 'F'),
        (r'\mathcal{S}', 'S'), (r'\arg\max', 'argmax'), (r'\arg\min', 'argmin'),
        (r'\left(', '('), (r'\right)', ')'), (r'\left\{', '{'), (r'\right\}', '}'),
        (r'\left[', '['), (r'\right]', ']'), (r'\middle|', '|'),
        (r'\lor', 'OR'), (r'\land', 'AND'), (r'\frac', ''), (r'\sqrt', '√'),
        (r'\text{inf}', 'inf'), (r'\text{raw}', 'raw'),
        (r'_{\\text{inf}}', '_inf'), (r'_{\\text{raw}}', '_raw'),
        (r'_{\text{mem}}', '_mem'), (r'_{\text{pred}}', '_pred'),
        (r'_{\text{first}}', '_first'), (r'_{\text{curr}}', '_curr'),
        (r'_{\text{tps}}', '_tps'), (r'_{\text{ram}}', '_ram'),
        (r'_{\text{kv}}', '_kv'), (r'_{\text{nv}}', '_nv'),
        (r'^{\text{inf}}', '^inf'), (r'^{\text{raw}}', '^raw'),
        (r'^{(i)}', '(i)'), (r'^{(-i)}', '(-i)'),
        (r'B_{\text{mem}}^{\text{inf}}', 'B_mem^inf'),
        (r'B_{\text{mem}}^{\text{raw}}', 'B_mem^raw'),
        (r'B_{\text{mem}}', 'B_mem'),
        (r'P_{\text{pred}}', 'P_pred'),
        (r'T_{\text{first}}', 'T_first'),
        (r'T_{\text{curr}}', 'T_curr'),
        (r'M_{\text{traffic}}', 'M_traffic'),
        (r'\mathbb{I}', '𝟙'),
        (r'n_{\text{kv}}', 'n_kv'),
        (r'd_h', 'd_h'), (r'b_{\text{kv}}', 'b_kv'),
        (r'\\', ' '), (r'\quad', '  '), (r'\;', ' '),
    ]
    for latex, uni in subs:
        t = t.replace(latex, uni)
    # Remove remaining braces and backslash commands
    t = re.sub(r'\\[a-zA-Z]+', '', t)
    t = re.sub(r'[{}]', '', t)
    return t

def md_inline(t):
    """Convert markdown inline formatting to ReportLab XML tags."""
    t = esc(t)
    # Bold+italic ***text***
    t = re.sub(r'\*\*\*(.+?)\*\*\*', r'<b><i>\1</i></b>', t)
    # Bold **text**
    t = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', t)
    # Italic *text*
    t = re.sub(r'\*([^*]+?)\*', r'<i>\1</i>', t)
    # Code `text`
    t = re.sub(r'`([^`]+?)`', r'<font name="Courier" size="8.5">\1</font>', t)
    # Inline math $...$  (strip and render as italic text)
    def replace_math(m):
        inner = math_unicode(m.group(1))
        return f'<i>{esc(inner)}</i>'
    t = re.sub(r'\$([^$]+?)\$', replace_math, t)
    # Strip markdown links — keep text
    t = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', t)
    return t

def block_math(line):
    """Render a display math line as centered italic equation."""
    t = line.strip().strip('$').strip()
    t = math_unicode(t)
    # Extract tag like (1), (2)…
    tag_m = re.search(r'\\tag\{(\d+)\}', line)
    tag = f"  ({tag_m.group(1)})" if tag_m else ""
    t = re.sub(r'\\tag\{[^}]+\}', '', t)
    t = math_unicode(t).strip()
    return Paragraph(f'<i>{esc(t)}</i>{esc(tag)}', STYLES["Eq"])

# ── table builder ─────────────────────────────────────────────────────────────
def build_table(raw_lines):
    rows = []
    for ln in raw_lines:
        if re.match(r'^\s*\|[-| :]+\|\s*$', ln):
            continue
        cells = [c.strip() for c in ln.strip().strip('|').split('|')]
        rows.append(cells)
    if not rows:
        return None

    # Detect header row (first row)
    n_cols = max(len(r) for r in rows)
    # Pad rows
    rows = [r + [''] * (n_cols - len(r)) for r in rows]

    table_data = []
    for ri, row in enumerate(rows):
        style = STYLES["TableH"] if ri == 0 else STYLES["TableC"]
        table_data.append([Paragraph(md_inline(c), style) for c in row])

    col_w = TEXT_W / n_cols
    col_widths = [col_w] * n_cols

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    ts = TableStyle([
        # Header
        ('BACKGROUND',  (0, 0), (-1, 0),  C_TABLE_H),
        ('TEXTCOLOR',   (0, 0), (-1, 0),  colors.white),
        ('FONTNAME',    (0, 0), (-1, 0),  'Times-Bold'),
        ('FONTSIZE',    (0, 0), (-1, 0),  8.5),
        ('ALIGN',       (0, 0), (-1, 0),  'CENTER'),
        # Body alternating
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, C_TABLE_R]),
        ('FONTNAME',    (0, 1), (-1, -1), 'Times-Roman'),
        ('FONTSIZE',    (0, 1), (-1, -1), 8.5),
        ('VALIGN',      (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',  (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('GRID',        (0, 0), (-1, -1), 0.4, C_LINE),
        ('BOX',         (0, 0), (-1, -1), 0.8, C_HEAD1),
    ])
    t.setStyle(ts)
    return t

# ── alert box builder ─────────────────────────────────────────────────────────
def build_alert(lines, kind):
    text = ' '.join(ln.lstrip('> ').lstrip('[!NOTEWARNIGCAUTION]').lstrip(' ').rstrip()
                    for ln in lines)
    bg = {'NOTE': C_CODE_BG, 'WARNING': C_WARN_BG, 'CAUTION': C_WARN_BG,
          'TIP': C_TIP_BG, 'IMPORTANT': C_NOTE_BG}.get(kind, C_CODE_BG)
    label = {'NOTE': '📝 Note', 'WARNING': '⚠️ Warning',
             'CAUTION': '⚠️ Caution', 'TIP': '💡 Tip',
             'IMPORTANT': '❗ Important'}.get(kind, kind.title())
    style = ParagraphStyle(f"Alert_{kind}",
        parent=STYLES["Body"], backColor=bg,
        leftIndent=14, rightIndent=14, spaceBefore=6, spaceAfter=8,
        borderPad=6, borderColor=C_LINE, borderWidth=0.5,
        borderRadius=4)
    return Paragraph(f'<b>{label}:</b> {md_inline(text)}', style)

# ── main parser ───────────────────────────────────────────────────────────────
def parse_md(md):
    story = []
    lines = md.split('\n')
    i = 0
    in_abstract = False
    abstract_buf = []

    def flush_abstract():
        nonlocal in_abstract, abstract_buf
        if abstract_buf:
            story.append(Paragraph("Abstract", STYLES["AbstractLabel"]))
            story.append(Paragraph(md_inline(' '.join(abstract_buf)), STYLES["Abstract"]))
            story.append(Spacer(1, 8))
            abstract_buf.clear()
        in_abstract = False

    while i < len(lines):
        ln = lines[i]

        # ── code block ────────────────────────────────────────────────────────
        if ln.strip().startswith('```'):
            i += 1
            code_lines = []
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            i += 1
            code_text = '\n'.join(code_lines)
            # Skip mermaid diagrams (can't render, just note)
            if code_lines and re.match(r'\s*(flowchart|sequenceDiagram|graph|classDiagram|stateDiagram)', code_lines[0]):
                story.append(Paragraph('<i>[System architecture diagram — see source for Mermaid flowchart]</i>',
                                       STYLES["Caption"]))
            else:
                safe_code = code_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                story.append(Preformatted(safe_code, STYLES["Code"]))
            continue

        # ── display math $$...$$ ──────────────────────────────────────────────
        if ln.strip().startswith('$$'):
            math_lines = []
            if ln.count('$$') >= 2 and len(ln.strip()) > 4:
                math_lines = [ln.strip().strip('$$')]
            else:
                i += 1
                while i < len(lines) and '$$' not in lines[i]:
                    math_lines.append(lines[i])
                    i += 1
            story.append(block_math(' '.join(math_lines)))
            i += 1
            continue

        # ── alert blocks "> [!TYPE]" ──────────────────────────────────────────
        if ln.strip().startswith('> [!'):
            m = re.match(r'>\s*\[!(NOTE|WARNING|CAUTION|TIP|IMPORTANT)\]', ln)
            kind = m.group(1) if m else 'NOTE'
            alert_lines = [ln]
            i += 1
            while i < len(lines) and lines[i].strip().startswith('>'):
                alert_lines.append(lines[i])
                i += 1
            story.append(build_alert(alert_lines, kind))
            continue

        # ── tables ────────────────────────────────────────────────────────────
        if ln.strip().startswith('|') and '|' in ln[1:]:
            tbl_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                tbl_lines.append(lines[i])
                i += 1
            t = build_table(tbl_lines)
            if t:
                story.append(Spacer(1, 4))
                story.append(t)
                story.append(Spacer(1, 6))
            continue

        # ── horizontal rule ---
        if re.match(r'^\s*---+\s*$', ln):
            if in_abstract:
                flush_abstract()
            story.append(Spacer(1, 4))
            story.append(HRFlowable(width="100%", thickness=0.5, color=C_LINE))
            story.append(Spacer(1, 4))
            i += 1
            continue

        # ── headings ──────────────────────────────────────────────────────────
        h_m = re.match(r'^(#{1,4})\s+(.+)', ln)
        if h_m:
            if in_abstract:
                flush_abstract()
            level = len(h_m.group(1))
            text  = md_inline(h_m.group(2))
            skey  = {1: 'H1', 2: 'H2', 3: 'H3', 4: 'H4'}.get(level, 'H2')
            # Title (first # at top of file)
            if level == 1 and not any(isinstance(f, Paragraph) and f.style.name == 'Title'
                                       for f in story):
                story.append(Spacer(1, 6))
                story.append(Paragraph(text, STYLES["Title"]))
                story.append(HRFlowable(width="60%", thickness=1.5, color=C_ACCENT,
                                        hAlign='CENTER'))
                story.append(Spacer(1, 4))
            else:
                if skey == 'H1':
                    story.append(Spacer(1, 8))
                    story.append(HRFlowable(width="100%", thickness=0.4, color=C_LINE))
                story.append(Paragraph(text, STYLES[skey]))
            # Detect abstract start
            if 'abstract' in ln.lower():
                in_abstract = True
            i += 1
            continue

        # ── keyword / bold-label line (Authors / Keywords) ────────────────────
        if re.match(r'^\*\*Authors?\*\*|^\*\*Keywords?\*\*', ln):
            story.append(Paragraph(md_inline(ln), STYLES["Subtitle"]))
            i += 1
            continue

        # ── bullet list ───────────────────────────────────────────────────────
        bul_m = re.match(r'^(\s*)([-*+])\s+(.+)', ln)
        if bul_m:
            if in_abstract:
                abstract_buf.append(ln.strip())
                i += 1
                continue
            indent = len(bul_m.group(1))
            text = md_inline(bul_m.group(3))
            style = STYLES["Bullet2"] if indent >= 4 else STYLES["Bullet"]
            story.append(Paragraph(f'• {text}', style))
            i += 1
            continue

        # ── numbered list ─────────────────────────────────────────────────────
        num_m = re.match(r'^(\s*)\d+\.\s+(.+)', ln)
        if num_m:
            if in_abstract:
                abstract_buf.append(ln.strip())
                i += 1
                continue
            m2 = re.match(r'^(\s*)(\d+)\.\s+(.+)', ln)
            num  = m2.group(2)
            text = md_inline(m2.group(3))
            story.append(Paragraph(f'{num}.  {text}', STYLES["NumItem"]))
            i += 1
            continue

        # ── empty line ────────────────────────────────────────────────────────
        if not ln.strip():
            if in_abstract and abstract_buf:
                pass  # keep accumulating
            else:
                story.append(Spacer(1, 4))
            i += 1
            continue

        # ── regular paragraph ─────────────────────────────────────────────────
        if in_abstract:
            abstract_buf.append(ln.strip())
        else:
            story.append(Paragraph(md_inline(ln), STYLES["Body"]))
        i += 1

    if in_abstract:
        flush_abstract()

    return story

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[*] Reading {MD_PATH}")
    with open(MD_PATH, encoding="utf-8") as f:
        md = f.read()

    print("[*] Parsing markdown…")
    story = parse_md(md)

    print(f"[*] Building PDF → {OUT_PDF}")
    doc = LuminaDocTemplate(
        OUT_PDF,
        pagesize=letter,
        leftMargin=MARGIN_INNER,
        rightMargin=MARGIN_OUTER,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOT,
        title="Lumina & SmartSwitch: Resilient Edge LLM Serving",
        author="Lumina Systems Research Team",
        subject="Edge LLM Orchestration Research Paper",
    )
    doc.build(story)
    size_kb = os.path.getsize(OUT_PDF) // 1024
    print(f"[✔] Done! PDF: {OUT_PDF}  ({size_kb} KB)")

if __name__ == "__main__":
    main()
