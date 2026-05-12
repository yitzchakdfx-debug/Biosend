"""PDF and CSV test reports with role-based detail and archiving."""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from PyPDF2 import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.platypus.tables import LongTable

from config import ADMIN_REPORT_PASSWORD, TESTER_SERIAL_NUMBER
from version import __version__

def sanitize_path_segment(value: str) -> str:
    """Flatten whitespace and strip characters that break filesystem paths."""
    cleaned = re.sub(r"\s+", "_", value.strip())
    return re.sub(r'[\\/:*?"<>|]+', "", cleaned) or "unknown"


class ReportGenerator:
    """Writes PDF archives under src/data/results/<UUT>/<Serial>/ and optional manual exports."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base = (
            base_dir
            if base_dir is not None
            else Path(__file__).resolve().parent.parent / "data" / "results"
        )

    def _resolved_archive_paths(self, run_meta: dict[str, Any]) -> tuple[Path, str]:
        """Sanitized subdirectory (uut/serial), timestamp stem for filenames."""
        uut_seg = sanitize_path_segment(str(run_meta.get("uut_type", "")).strip())
        sn_seg = sanitize_path_segment(str(run_meta.get("serial_number", "")).strip())
        test_name_meta = str(run_meta.get("test_program_name", "report")).strip()
        stem_test = sanitize_path_segment(test_name_meta)

        archive_dir = self._base / uut_seg / sn_seg
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        stem = "_".join(
            [
                stem_test,
                ts,
                sn_seg,
            ]
        )
        return archive_dir, stem

    def generate_pdf_auto_archive(
        self,
        run_meta: dict[str, Any],
        results: list[dict[str, Any]],
        role: str,
    ) -> Path:
        """Persist only PDF under the structured archive folder (CSV is manual-export only)."""
        role_key = role.strip().title()
        archive_dir, stem = self._resolved_archive_paths(run_meta)
        archive_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = archive_dir / f"{stem}_{role_key.replace(' ', '_')}.pdf"
        write_pdf_report(pdf_path, run_meta, results, role_key)
        return pdf_path

    def generate_csv_file(
        self,
        dest: Path | str,
        run_meta: dict[str, Any],
        results: list[dict[str, Any]],
        role: str,
    ) -> Path:
        path = Path(dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_csv(path, run_meta, results, role.strip().title())
        return path

    def generate_pdf_file(
        self,
        dest: Path | str,
        run_meta: dict[str, Any],
        results: list[dict[str, Any]],
        role: str,
    ) -> Path:
        path = Path(dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_pdf_report(path, run_meta, results, role.strip().title())
        return path

    # Backward-compat name used elsewhere
    def generate(
        self,
        run_meta: dict[str, Any],
        results: list[dict[str, Any]],
        role: str,
    ) -> Path:
        """Auto-archive PDF only."""
        return self.generate_pdf_auto_archive(run_meta, results, role)


def _fmt_num(v: Any) -> str:
    if v is None:
        return ""
    try:
        return f"{float(v):g}"
    except (TypeError, ValueError):
        return str(v)


def _header_rows(run_meta: dict[str, Any], role: str) -> list[tuple[str, str]]:
    overall = str(run_meta.get("overall_result", "—"))
    return [
        ("Result (Overall)", overall),
        ("Tester Name", str(run_meta.get("tester_name", ""))),
        ("Tester Employee ID", str(run_meta.get("employee_id", ""))),
        ("Test Program", str(run_meta.get("test_program_name", ""))),
        ("UUT Type", str(run_meta.get("uut_type", ""))),
        ("UUT Name (Part)", str(run_meta.get("part_number", ""))),
        ("UUT SN", str(run_meta.get("serial_number", ""))),
        ("Start Time", str(run_meta.get("start_time", ""))),
        ("End Time", str(run_meta.get("end_time", ""))),
        ("Tester SN", TESTER_SERIAL_NUMBER),
        ("SW Version", __version__),
        ("Role / Report Detail", role),
    ]


def _write_csv(
    path: Path,
    run_meta: dict[str, Any],
    results: list[dict[str, Any]],
    role: str,
) -> None:
    is_admin = role == "Admin"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Field", "Value"])
        for k, v in _header_rows(run_meta, role):
            writer.writerow([k, v])
        writer.writerow([])
        if is_admin:
            writer.writerow(["Test Name", "Min", "Max", "Value", "Unit", "Result"])
            for row in results:
                writer.writerow(
                    [
                        row.get("test_name", ""),
                        _fmt_num(row.get("min")),
                        _fmt_num(row.get("max")),
                        _fmt_num(row.get("value")),
                        row.get("unit", ""),
                        "PASS" if row.get("passed") else "FAIL",
                    ]
                )
        else:
            writer.writerow(["Test Name", "Result"])
            for row in results:
                writer.writerow(
                    [
                        row.get("test_name", ""),
                        "PASS" if row.get("passed") else "FAIL",
                    ]
                )


def write_pdf_report(
    path: Path,
    run_meta: dict[str, Any],
    results: list[dict[str, Any]],
    role: str,
) -> None:
    """Build paginated PDF (SimpleDocTemplate + LongTable for results splits across pages)."""
    is_admin = role == "Admin"
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    flow: list[Any] = []

    flow.append(
        Paragraph(
            "<b>DFX Tester — Test Report</b>",
            styles["Heading1"],
        )
    )
    flow.append(Spacer(1, 0.15 * inch))

    header_data = [["Field", "Value"]]
    for h, v in _header_rows(run_meta, role):
        header_data.append([h, v])
    ht = Table(header_data, colWidths=[2.4 * inch, 4 * inch])
    ht.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f65ca")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    flow.append(ht)
    flow.append(Spacer(1, 0.25 * inch))

    if is_admin:
        data = [["Test Name", "Min", "Max", "Value", "Unit", "Status"]]
        for row in results:
            ok = bool(row.get("passed"))
            data.append(
                [
                    Paragraph(row.get("test_name", ""), styles["Normal"]),
                    _fmt_num(row.get("min")),
                    _fmt_num(row.get("max")),
                    _fmt_num(row.get("value")),
                    row.get("unit", ""),
                    "PASS" if ok else "FAIL",
                ]
            )
        col_w = [
            1.35 * inch,
            0.75 * inch,
            0.75 * inch,
            0.85 * inch,
            0.65 * inch,
            0.65 * inch,
        ]
        rt = LongTable(data, colWidths=col_w, repeatRows=1)
    else:
        data = [["Test Name", "Result"]]
        for row in results:
            data.append(
                [
                    Paragraph(row.get("test_name", ""), styles["Normal"]),
                    "PASS" if row.get("passed") else "FAIL",
                ]
            )
        rt = LongTable(data, colWidths=[5.35 * inch, 1 * inch], repeatRows=1)

    rt.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#444444")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    flow.append(rt)

    doc.build(flow)
    raw_pdf = buffer.getvalue()
    buffer.close()

    if is_admin:
        reader = PdfReader(io.BytesIO(raw_pdf))
        writer = PdfWriter()
        for pg in reader.pages:
            writer.add_page(pg)
        writer.encrypt(
            user_password=ADMIN_REPORT_PASSWORD,
            owner_password=ADMIN_REPORT_PASSWORD,
        )
        out_buf = io.BytesIO()
        writer.write(out_buf)
        path.write_bytes(out_buf.getvalue())
    else:
        path.write_bytes(raw_pdf)
