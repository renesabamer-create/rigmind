"""Exportación del reporte a .docx y .xlsx (sin depender de Office instalado)."""

import io
from datetime import datetime
from typing import Any, Dict, List

SEVERITY_LABEL = {
    "critical": "CRÍTICO",
    "warning": "ADVERTENCIA",
    "info": "INFO",
    "success": "OK",
}


def _meta_rows(p: Dict[str, Any]) -> List[tuple]:
    return [
        ("Pozo / Well", p.get("well") or "—"),
        ("Fecha / Date", p.get("report_date") or datetime.now().strftime("%d-%b-%Y")),
        ("Lapso / Period", f"{p.get('period_start', '00:00')} – {p.get('period_end', '24:00')}"),
        ("Completitud", f"{p.get('completeness', 0)} %"),
        ("Generado", datetime.now().strftime("%d-%b-%Y %H:%M")),
    ]


def _clean_findings(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for f in findings or []:
        ev = f.get("evidence") or {}
        out.append({
            "severity": f.get("severity", "info"),
            "badge": f.get("badge", ""),
            "agent": f.get("agent", ""),
            "message": f.get("message", ""),
            "line": ev.get("line"),
            "quote": ev.get("quote"),
            "standard": f.get("standard") or "",
            "suggestion": f.get("suggestion") or "",
        })
    return out


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------
def build_docx(payload: Dict[str, Any]) -> bytes:
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt, RGBColor
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Falta python-docx. Instale: pip install python-docx") from e

    p = payload or {}
    doc = Document()

    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("DAILY OPERATIONS REPORT (DOR)")
    run.bold = True
    run.font.size = Pt(16)
    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.add_run("Reporte de operaciones de pozo — español revisado + inglés de operaciones").italic = True

    table = doc.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for k, v in _meta_rows(p):
        cells = table.add_row().cells
        cells[0].text = k
        cells[1].text = str(v)
        for paragraph in cells[0].paragraphs:
            for r in paragraph.runs:
                r.bold = True

    findings = _clean_findings(p.get("findings") or [])
    doc.add_paragraph()
    doc.add_heading("1. Hallazgos de la auditoría", level=1)
    if findings:
        ft = doc.add_table(rows=1, cols=4)
        ft.style = "Table Grid"
        for i, h in enumerate(["Gravedad", "Hallazgo", "Evidencia / norma", "Corrección"]):
            cell = ft.rows[0].cells[i]
            cell.text = h
            for paragraph in cell.paragraphs:
                for r in paragraph.runs:
                    r.bold = True
        for f in findings[:80]:
            cells = ft.add_row().cells
            cells[0].text = SEVERITY_LABEL.get(f["severity"], f["severity"])
            cells[1].text = f"{f['badge']}\n{f['message']}"
            ev = ""
            if f["line"]:
                ev += f"L{f['line']} · "
            if f["quote"]:
                ev += f"«{f['quote']}»\n"
            if f["standard"]:
                ev += f"Norma: {f['standard']}"
            cells[2].text = ev.strip()
            cells[3].text = f["suggestion"]
        for row in ft.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for r in paragraph.runs:
                        r.font.size = Pt(8)
    else:
        doc.add_paragraph("Sin hallazgos registrados.")

    doc.add_heading("2. Reporte en español (revisado)", level=1)
    for line in (p.get("spanish") or "").split("\n"):
        par = doc.add_paragraph(line)
        par.paragraph_format.space_after = Pt(1)
        par.paragraph_format.space_before = Pt(0)

    english = (p.get("english") or "").strip()
    doc.add_heading("3. English operations report", level=1)
    if english:
        for line in english.split("\n"):
            par = doc.add_paragraph(line)
            par.paragraph_format.space_after = Pt(1)
            par.paragraph_format.space_before = Pt(0)
    else:
        doc.add_paragraph("[Traducción pendiente]")

    doc.add_paragraph()
    note = doc.add_paragraph()
    r = note.add_run(
        "Generado con RigMind. Este documento es un borrador de auditoría: "
        "requiere revisión y firma del responsable de operaciones antes de su entrega."
    )
    r.italic = True
    r.font.size = Pt(8)
    r.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------
def build_xlsx(payload: Dict[str, Any]) -> bytes:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Falta openpyxl. Instale: pip install openpyxl") from e

    p = payload or {}
    wb = Workbook()

    header_fill = PatternFill("solid", fgColor="1A232E")
    header_font = Font(bold=True, color="FFFFFF")

    def style_header(ws, row=1):
        for cell in ws[row]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(vertical="center")

    ws = wb.active
    ws.title = "Resumen"
    ws.append(["Campo", "Valor"])
    for k, v in _meta_rows(p):
        ws.append([k, v])
    style_header(ws)
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 60

    ops = wb.create_sheet("Operaciones")
    ops.append(["Desde", "Hasta", "Operación", "Completitud %", "Campos faltantes"])
    for o in p.get("operations") or []:
        missing = ", ".join(m.get("label", "") for m in (o.get("missing") or []))
        ops.append([o.get("from", ""), o.get("to", ""), o.get("label", ""),
                    o.get("score", ""), missing])
    style_header(ops)
    for col, width in zip("ABCDE", (10, 10, 38, 14, 70)):
        ops.column_dimensions[col].width = width

    fws = wb.create_sheet("Hallazgos")
    fws.append(["Gravedad", "Hallazgo", "Agente", "Mensaje", "Línea", "Cita", "Norma", "Corrección"])
    for f in _clean_findings(p.get("findings") or []):
        fws.append([SEVERITY_LABEL.get(f["severity"], f["severity"]), f["badge"], f["agent"],
                    f["message"], f["line"], f["quote"], f["standard"], f["suggestion"]])
    style_header(fws)
    for col, width in zip("ABCDEFGH", (12, 38, 20, 70, 7, 45, 30, 50)):
        fws.column_dimensions[col].width = width
    for row in fws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    es = wb.create_sheet("Texto_ES")
    for i, line in enumerate((p.get("spanish") or "").split("\n"), start=1):
        es.cell(row=i, column=1, value=line)
    es.column_dimensions["A"].width = 140

    en = wb.create_sheet("Texto_EN")
    for i, line in enumerate((p.get("english") or "").split("\n"), start=1):
        en.cell(row=i, column=1, value=line)
    en.column_dimensions["A"].width = 140

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
