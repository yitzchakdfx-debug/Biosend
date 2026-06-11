"""Background worker that archives PDF/XML reports off the GUI thread."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from logic.report_generator import ReportGenerator


class ReportWorker(QThread):
    archived = Signal(str)
    failed = Signal(str)

    def __init__(self, jobs: list[tuple[dict, list[dict]]], role: str, parent=None) -> None:
        super().__init__(parent)
        self._jobs = [(dict(meta), list(rows)) for meta, rows in jobs]
        self._role = role

    def run(self) -> None:
        try:
            rg = ReportGenerator()
            for meta, rows in self._jobs:
                pdf_path = rg.generate_pdf_auto_archive(meta, rows, self._role)
                xml_path = rg.generate_xml_auto_archive(meta, rows, self._role)
                self.archived.emit(str(pdf_path))
                self.archived.emit(str(xml_path))
        except Exception as exc:
            self.failed.emit(str(exc))
