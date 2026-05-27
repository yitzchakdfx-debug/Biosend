"""Admin: manage test versions in the database (import / view / delete / export)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from config import UUT_TYPES
from logic.database_manager import DatabaseManager
from logic.script_manager import ScriptManager
from ui.views.connection_settings_form import ConnectionSettingsForm
from ui.views.script_editor import ScriptEditorDialog


def _next_import_version_name(db: DatabaseManager, test_name: str) -> str:
    """First import uses V1.0; further imports bump V1.1, V1.2, ..."""
    if not db.version_exists(test_name.strip(), "V1.0"):
        return "V1.0"
    n = 1
    while db.version_exists(test_name.strip(), f"V1.{n}"):
        n += 1
    return f"V1.{n}"


class ImportTestMetaDialog(QDialog):
    """Collect logical test name and UUT type after picking a `.tst` file."""

    def __init__(self, suggested_test_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import Test Metadata")
        root = QVBoxLayout(self)
        form = QFormLayout()
        self._edit_name = QLineEdit(suggested_test_name)
        form.addRow("Test Name", self._edit_name)
        self._combo_uut = QComboBox()
        self._combo_uut.addItems(UUT_TYPES)
        form.addRow("UUT Type", self._combo_uut)
        root.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def test_name(self) -> str:
        return self._edit_name.text().strip()

    def uut_type(self) -> str:
        return self._combo_uut.currentText().strip()


class VersionManagerDialog(QDialog):
    def __init__(
        self,
        current_username: str,
        script_manager: ScriptManager,
        *,
        employee_id: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._db = DatabaseManager()
        self._script_manager = script_manager
        self._user = current_username.strip()
        self._employee_id = employee_id.strip()
        self.setWindowTitle("Test Version Manager")
        self.resize(920, 480)

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Imported and saved sequences (Admin only)."))

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            [
                "Test Name",
                "UUT Type",
                "Version",
                "Connection Params",
                "Creator",
                "Created",
            ]
        )
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self._table)

        row = QHBoxLayout()
        self._btn_import = QPushButton("Import .tst")
        self._btn_import.clicked.connect(self._import_tst)
        row.addWidget(self._btn_import)
        self.btn_update_from_tst = QPushButton("Update from .tst")
        self.btn_update_from_tst.clicked.connect(self._update_from_tst)
        row.addWidget(self.btn_update_from_tst)
        self._btn_view = QPushButton("View")
        self._btn_view.clicked.connect(self._view)
        row.addWidget(self._btn_view)
        self._btn_edit = QPushButton("Edit")
        self._btn_edit.clicked.connect(self._edit)
        row.addWidget(self._btn_edit)
        self._btn_edit_conn = QPushButton("Edit Connection")
        self._btn_edit_conn.clicked.connect(self._edit_connection_params)
        row.addWidget(self._btn_edit_conn)
        self._btn_delete = QPushButton("Delete")
        self._btn_delete.clicked.connect(self._delete)
        row.addWidget(self._btn_delete)
        self._btn_export = QPushButton("Export .tst")
        self._btn_export.clicked.connect(self._export)
        row.addWidget(self._btn_export)
        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.clicked.connect(self._populate)
        row.addWidget(self._btn_refresh)
        row.addStretch()
        root.addLayout(row)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        root.addWidget(close_btn)

        self._populate()

    def _selected_id(self) -> int | None:
        cr = self._table.currentRow()
        if cr < 0:
            return None
        it = self._table.item(cr, 0)
        if it is None:
            return None
        data = it.data(Qt.ItemDataRole.UserRole)
        return int(data) if data is not None else None

    def _populate(self) -> None:
        rows = self._db.list_test_versions()
        self._table.setRowCount(0)
        for r in rows:
            i = self._table.rowCount()
            self._table.insertRow(i)
            c0 = QTableWidgetItem(str(r["test_name"]))
            c0.setData(Qt.ItemDataRole.UserRole, int(r["id"]))
            self._table.setItem(i, 0, c0)
            self._table.setItem(i, 1, QTableWidgetItem(str(r["uut_type"])))
            self._table.setItem(i, 2, QTableWidgetItem(str(r["version_name"])))
            self._table.setItem(
                i, 3, QTableWidgetItem(str(r.get("connection_params", "") or ""))
            )
            self._table.setItem(i, 4, QTableWidgetItem(str(r["created_by"])))
            self._table.setItem(i, 5, QTableWidgetItem(str(r["created_at"])))

    def _import_tst(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Import test script",
            str(self._script_manager.scripts_dir),
            "Test Scripts (*.tst);;All Files (*)",
        )
        if not path_str:
            return
        src = Path(path_str)
        try:
            raw = src.read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Import", str(exc))
            return
        meta = ImportTestMetaDialog(src.stem, parent=self)
        if meta.exec() != QDialog.DialogCode.Accepted:
            return
        tname = meta.test_name()
        uut = meta.uut_type()
        if not tname or not uut:
            QMessageBox.warning(self, "Import", "Test name and UUT type are required.")
            return
        ver = _next_import_version_name(self._db, tname)
        try:
            self._db.add_test_version(tname, uut, ver, raw, self._user)
        except Exception as exc:
            QMessageBox.warning(self, "Import Failed", str(exc))
            return
        try:
            self._db.log_audit_action(
                "Imported test version",
                username=self._user,
                employee_id=self._employee_id,
                details=f"test={tname!r} version={ver!r} uut_type={uut!r}",
            )
        except Exception:
            pass
        self._populate()
        QMessageBox.information(self, "Import", f"Saved as version {ver!r}.")

    def _update_from_tst(self) -> None:
        cr = self._table.currentRow()
        if cr < 0:
            QMessageBox.information(
                self, "Update from .tst", "Select a test first."
            )
            return
        item0 = self._table.item(cr, 0)
        item1 = self._table.item(cr, 1)
        if item0 is None or item1 is None:
            QMessageBox.information(
                self, "Update from .tst", "Select a test first."
            )
            return
        test_name = item0.text().strip()
        uut_type = item1.text().strip()
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Select test script",
            str(self._script_manager.scripts_dir),
            "Test Scripts (*.tst);;All Files (*)",
        )
        if not path_str:
            return
        src = Path(path_str)
        try:
            raw = src.read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Update from .tst", str(exc))
            return
        new_ver, ok = QInputDialog.getText(
            self,
            "New Version",
            "Enter new version name:",
            text="V1.x",
        )
        if not ok:
            return
        new_ver = new_ver.strip()
        if not new_ver:
            QMessageBox.warning(
                self, "Update from .tst", "Version name cannot be empty."
            )
            return
        invalid_chars = r'\/:*?"<>|'
        if any(ch in new_ver for ch in invalid_chars):
            QMessageBox.warning(
                self,
                "Invalid Name",
                f"Version name cannot contain any of the following characters:\n{invalid_chars}",
            )
            return
        if self._db.version_exists(test_name, new_ver):
            QMessageBox.warning(
                self,
                "Update from .tst",
                f"Version {new_ver!r} already exists for test {test_name!r}.",
            )
            return
        prior_conn = ""
        prior_id = self._selected_id()
        if prior_id is not None:
            prior = self._db.get_test_version(prior_id)
            if prior is not None:
                prior_conn = str(prior.get("connection_params", "") or "")
        try:
            self._db.add_test_version(
                test_name,
                uut_type,
                new_ver,
                raw,
                self._user,
                connection_params=prior_conn,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Update Failed", str(exc))
            return
        try:
            self._db.log_audit_action(
                "Created new test version",
                username=self._user,
                employee_id=self._employee_id,
                details=f"Updated from external file: {new_ver}",
            )
        except Exception:
            pass
        self._populate()
        QMessageBox.information(
            self,
            "Update from .tst",
            f"Stored new version {new_ver!r} for {test_name!r}.",
        )

    def _view(self) -> None:
        vid = self._selected_id()
        if vid is None:
            QMessageBox.information(self, "View", "Select a version first.")
            return

        rec = self._db.get_test_version(vid)
        if rec is None:
            self._populate()
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"{rec['test_name']} — {rec['version_name']}")
        dlg.resize(720, 520)

        layout = QVBoxLayout(dlg)

        editor = QPlainTextEdit(str(rec["test_content"]))

        mono_font = QFont("Consolas")
        mono_font.setPointSize(10)
        mono_font.setStyleHint(QFont.StyleHint.Monospace)
        mono_font.setFixedPitch(True)

        editor.setFont(mono_font)
        editor.setReadOnly(True)

        layout.addWidget(editor)

        btn = QPushButton("Close")
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn)

        dlg.exec()

    def _edit(self) -> None:
        vid = self._selected_id()
        if vid is None:
            QMessageBox.information(self, "Edit", "Select a version first.")
            return
        rec = self._db.get_test_version(vid)
        if rec is None:
            self._populate()
            return
        tname = str(rec["test_name"]).strip()
        uut = str(rec["uut_type"]).strip()
        dlg = ScriptEditorDialog(self._script_manager, parent=self)
        dlg.load_catalog_version(
            tname,
            str(rec["version_name"]),
            str(rec["test_content"]),
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        body = dlg.result_text()
        new_ver, ok = QInputDialog.getText(
            self,
            "New Version Name",
            "Enter a new unique version name (the selected row will not be overwritten):",
            text="V1.1",
        )
        if not ok:
            return
        new_ver = new_ver.strip()
        if not new_ver:
            QMessageBox.warning(self, "Edit", "Version name cannot be empty.")
            return
        invalid_chars = r'\/:*?"<>|'
        if any(ch in new_ver for ch in invalid_chars):
            QMessageBox.warning(
                self,
                "Invalid Name",
                f"Version name cannot contain any of the following characters:\n{invalid_chars}",
            )
            return
        if self._db.version_exists(tname, new_ver):
            QMessageBox.warning(
                self,
                "Edit",
                f"Version {new_ver!r} already exists for test {tname!r}.",
            )
            return
        try:
            self._db.add_test_version(
                tname,
                uut,
                new_ver,
                body,
                self._user,
                connection_params=str(rec.get("connection_params", "") or ""),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Save Failed", str(exc))
            return
        try:
            self._db.log_audit_action(
                "Created new test version",
                username=self._user,
                employee_id=self._employee_id,
                details=f"Edited to {new_ver}",
            )
        except Exception:
            pass
        self._populate()
        QMessageBox.information(
            self, "Saved", f"Stored new version {new_ver!r} for {tname!r}."
        )

    def _edit_connection_params(self) -> None:
        """Create a new auto-versioned row that updates the connection params string."""
        vid = self._selected_id()
        if vid is None:
            QMessageBox.information(
                self, "Edit Connection", "Select a version first."
            )
            return
        rec = self._db.get_test_version(vid)
        if rec is None:
            self._populate()
            return
        tname = str(rec["test_name"]).strip()
        uut = str(rec["uut_type"]).strip()
        current = str(rec.get("connection_params", "") or "")

        form = ConnectionSettingsForm(
            parent=self,
            subtitle=(
                f"Connection parameters for {tname!r} "
                f"(from {rec['version_name']!r}). "
                "Saving creates a new auto-incremented version; the selected row is preserved."
            ),
        )
        form.populate_form_from_db(current)
        if form.exec() != QDialog.DialogCode.Accepted:
            return
        new_params = form.get_form_as_db_string()
        if new_params == current:
            QMessageBox.information(
                self,
                "Edit Connection",
                "Connection parameters unchanged — no new version created.",
            )
            return
        new_ver = _next_import_version_name(self._db, tname)
        try:
            self._db.add_test_version(
                tname,
                uut,
                new_ver,
                str(rec["test_content"]),
                self._user,
                connection_params=new_params,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Save Failed", str(exc))
            return
        try:
            self._db.log_audit_action(
                "Updated connection parameters",
                username=self._user,
                employee_id=self._employee_id,
                details=(
                    f"test={tname!r} new_version={new_ver!r} "
                    f"params={new_params!r} prior_version={rec['version_name']!r}"
                ),
            )
        except Exception:
            pass
        self._populate()
        QMessageBox.information(
            self,
            "Connection Updated",
            f"Created new version {new_ver!r} for {tname!r} with updated connection params.",
        )

    def _delete(self) -> None:
        vid = self._selected_id()
        if vid is None:
            QMessageBox.information(self, "Delete", "Select a version first.")
            return
        if (
            QMessageBox.question(
                self,
                "Delete",
                "Delete this version permanently?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self._db.delete_test_version(vid)
        self._populate()

    def _export(self) -> None:
        vid = self._selected_id()
        if vid is None:
            QMessageBox.information(self, "Export", "Select a version first.")
            return
        rec = self._db.get_test_version(vid)
        if rec is None:
            self._populate()
            return
        default = (
            f"{rec['test_name']}_{rec['version_name']}.tst"
            .replace(" ", "_")
        )
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Export test script",
            str(self._script_manager.scripts_dir / default),
            "Test Scripts (*.tst)",
        )
        if not path_str:
            return
        outp = Path(path_str)
        if outp.suffix.lower() != ".tst":
            outp = outp.with_suffix(".tst")
        try:
            outp.write_text(rec["test_content"], encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Export", str(exc))
            return
