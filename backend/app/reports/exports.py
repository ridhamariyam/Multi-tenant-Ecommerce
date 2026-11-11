"""Report downloads: the rows a report already computed, written as CSV, XLSX or PDF.

No figures are worked out here -- every format renders the same list of dicts the
JSON report returns, so the downloads always match what the admin sees.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import Response
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

EXPORT_FORMATS = ("csv", "xlsx", "pdf")
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_MEDIA_TYPE = "application/pdf"

# A PDF is for reading and printing; past this many rows the CSV/XLSX is the right tool.
PDF_MAX_ROWS = 5000


def heading(key: str) -> str:
    """'units_sold' -> 'Units sold'."""
    return key.replace("_", " ").capitalize()


def _download(content: bytes | str, media_type: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )


def csv_response(name: str, rows: Iterable[dict]) -> Response:
    """Rows as a CSV download (opens in Excel)."""
    rows = list(rows)
    buffer = io.StringIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: "" if v is None else v for k, v in row.items()})
    # BOM so Excel reads UTF-8 names
    return _download("﻿" + buffer.getvalue(), "text/csv; charset=utf-8", f"{name}.csv")


def _cell(value):
    """A value Excel stores natively: numbers stay numbers, times lose their zone (UTC)."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def xlsx_bytes(title: str, rows: list[dict]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title[:31] or "Report"
    if rows:
        keys = list(rows[0].keys())
        sheet.append([heading(k) for k in keys])
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        sheet.freeze_panes = "A2"
        for row in rows:
            sheet.append([_cell(row.get(k)) for k in keys])
        for index, key in enumerate(keys, start=1):
            longest = max([len(heading(key))] + [len(str(r.get(key) or "")) for r in rows[:500]])
            sheet.column_dimensions[get_column_letter(index)].width = min(max(longest + 2, 8), 50)
            for (cell,) in sheet.iter_rows(
                min_row=2, min_col=index, max_col=index, max_row=len(rows) + 1
            ):
                if isinstance(cell.value, Decimal):
                    cell.number_format = "#,##0.00"
                elif isinstance(cell.value, datetime):
                    cell.number_format = "yyyy-mm-dd hh:mm"
                elif isinstance(cell.value, date):
                    cell.number_format = "yyyy-mm-dd"
    else:
        sheet.append(["No data for this report"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _pdf_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:,.2f}"
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value)


def pdf_bytes(title: str, subtitle: str | None, rows: list[dict]) -> bytes:
    styles = getSampleStyleSheet()
    cell = styles["BodyText"].clone("cell", fontSize=7, leading=8.5)
    head = cell.clone("head", fontName="Helvetica-Bold")
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title=title,
    )
    story = [Paragraph(title, styles["Title"])]
    if subtitle:
        story.append(Paragraph(subtitle, styles["Normal"]))
    story.append(Spacer(1, 4 * mm))
    if not rows:
        story.append(Paragraph("No data for this report.", styles["Normal"]))
    else:
        shown = rows[:PDF_MAX_ROWS]
        keys = [k for k in rows[0] if not k.endswith("_id")] or list(rows[0])
        numeric = {
            k for k in keys if any(isinstance(r.get(k), (int, float, Decimal)) for r in shown)
        }
        data = [[Paragraph(heading(k), head) for k in keys]]
        data += [[Paragraph(_pdf_text(r.get(k)), cell) for k in keys] for r in shown]
        table = LongTable(data, repeatRows=1, colWidths=[doc.width / len(keys)] * len(keys))
        style = [
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B8BCC4")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF0F4")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]
        for index, key in enumerate(keys):
            if key in numeric:
                style.append(("ALIGN", (index, 1), (index, -1), "RIGHT"))
        table.setStyle(TableStyle(style))
        story.append(table)
        if len(rows) > PDF_MAX_ROWS:
            story.append(Spacer(1, 3 * mm))
            story.append(
                Paragraph(
                    f"Showing the first {PDF_MAX_ROWS:,} of {len(rows):,} rows. "
                    "Download the Excel file for everything.",
                    styles["Italic"],
                )
            )
    doc.build(story)
    return buffer.getvalue()


def export_response(
    fmt: str, name: str, rows: Iterable[dict], *, title: str, subtitle: str | None = None
) -> Response:
    """The report as a download in `fmt` (csv, xlsx or pdf)."""
    rows = list(rows)
    if fmt == "csv":
        return csv_response(name, rows)
    if fmt == "xlsx":
        return _download(xlsx_bytes(title, rows), XLSX_MEDIA_TYPE, f"{name}.xlsx")
    if fmt == "pdf":
        return _download(pdf_bytes(title, subtitle, rows), PDF_MEDIA_TYPE, f"{name}.pdf")
    raise ValueError(f"Unknown export format {fmt}")
