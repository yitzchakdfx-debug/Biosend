"""Main ATE window: layout, styling, and wiring to the script-driven runner."""

from __future__ import annotations

import csv
import html
import json
import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import SHOW_LIVE_MONITOR
from logic.models import TestResultPayload
from logic.monitor_engine import MonitorThread
from logic.script_manager import ScriptManager, ScriptParseError
from logic.test_engine import TestRunnerThread
from ui.views.script_editor import ScriptEditorDialog
from ui.views.user_management_dialog import UserManagementDialog
from ui.widgets.control_panel import ControlPanelWidget
from ui.widgets.instrument_panel import InstrumentPanelWidget
from version import __version__


_DEFAULT_SCRIPT_NAME = "sequence.tst"
_NA = "-"


def _format_measurement(value: float) -> str:
    """Human-readable numeric string without excessive trailing zeros."""
    return f"{value:g}"


class MainWindow(QMainWindow):
    _ICONS_DIR = Path(__file__).resolve().parents[1] / "assets" / "icons"
    _RESULTS_DIR = Path(__file__).resolve().parents[2] / "data" / "results"

    def __init__(self, user_info: dict) -> None:
        super().__init__()
        self._user_info = user_info
        self.setWindowTitle("DFX Tester - Component ATE")
        icon_path = self._ICONS_DIR / "BirdAppIcon.png"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1200, 800)
        self._setup_menu_bar()
        self.test_thread: TestRunnerThread | None = None
        self.is_dark_mode: bool = True
        self._script_manager = ScriptManager()
        self._active_script_path: Path = (
            self._script_manager.scripts_dir / _DEFAULT_SCRIPT_NAME
        )
        self._trace_history: list[dict] = []
        self._part_number_user_edited = False
        self._setup_ui()
        if SHOW_LIVE_MONITOR:
            self.monitor_thread = MonitorThread(parent=self)
            self.monitor_thread.values_updated.connect(self.instrument_panel.update_values)
            self.monitor_thread.start()
        self._apply_theme_file()
        self._update_icons(self.is_dark_mode)
        self._apply_role_permissions()
        self._reload_script_into_list()

    def _make_ribbon_button(self, object_name: str, text: str) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName(object_name)
        btn.setText(text)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setFixedSize(80, 70)
        btn.setIconSize(QSize(28, 28))
        btn.setAutoRaise(True)
        return btn

    def _icon(self, name: str, fallback: QStyle.StandardPixmap) -> QIcon:
        for ext in (".svg", ".png"):
            candidate = self._ICONS_DIR / f"{name}{ext}"
            if candidate.is_file():
                return QIcon(str(candidate))
        return self.style().standardIcon(fallback)

    def _update_icons(self, is_dark: bool) -> None:
        """Load theme-aware and ribbon icons; falls back to standard icons if assets missing."""
        SP = QStyle.StandardPixmap
        theme_name = "sun" if is_dark else "moon"
        theme_fallback = SP.SP_DialogYesButton if is_dark else SP.SP_DialogNoButton
        self.btn_toggle_theme.setIcon(self._icon(theme_name, theme_fallback))
        self.btn_load_script.setIcon(self._icon("folder", SP.SP_DirOpenIcon))
        self.btn_edit_script.setIcon(self._icon("edit", SP.SP_FileDialogDetailedView))
        self.btn_logout.setIcon(self._icon("logout", SP.SP_ArrowBack))
        self.btn_exit.setIcon(self._icon("power", SP.SP_DialogCloseButton))

    def show_about_dialog(self) -> None:
        QMessageBox.about(
            self,
            "About DFX Tester",
            "<b>DFX Tester - Component ATE</b><br>"
            f"Version {__version__}<br><br>"
            "In development.",
        )

    def _setup_menu_bar(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("&File")
        file_menu.addAction("&New Script...", self.new_script)
        file_menu.addAction("&Open Script...", self.load_script)
        file_menu.addAction("&Save Results...", self.save_results_json)
        file_menu.addSeparator()
        file_menu.addAction("E&xit", self.close)

        test_menu = menu.addMenu("&Test")
        test_menu.addAction("&Run", self.start_tests)
        test_menu.addAction("&Stop", self.stop_tests)
        test_menu.addSeparator()
        test_menu.addAction("Re&set Counters", self.reset_counters)

        results_menu = menu.addMenu("&Results")
        results_menu.addAction("Export to &CSV...", self.export_results_csv)
        results_menu.addAction("Open Results &Folder", self.open_results_folder)

        help_menu = menu.addMenu("&Help")
        if self._is_admin():
            help_menu.addAction("&User Management...", self.open_user_management)
        help_menu.addAction("&About", self.show_about_dialog)

    def _current_role(self) -> str:
        return str(self._user_info.get("role", "")).strip().title()

    def _is_operator(self) -> bool:
        return self._current_role() == "Operator"

    def _is_admin(self) -> bool:
        return self._current_role() == "Admin"

    def _apply_role_permissions(self) -> None:
        if self._is_operator():
            self.btn_edit_script.hide()
            self.results_table.setColumnHidden(2, True)
            self.results_table.setColumnHidden(3, True)

    def open_user_management(self) -> None:
        if not self._is_admin():
            QMessageBox.warning(self, "Not allowed", "Only Admin users can manage users.")
            return
        dialog = UserManagementDialog(
            current_username=str(self._user_info.get("username", "")),
            parent=self,
        )
        dialog.exec()

    def new_script(self) -> None:
        scripts_dir = self._script_manager.scripts_dir
        scripts_dir.mkdir(parents=True, exist_ok=True)
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "New test script",
            str(scripts_dir / "untitled.tst"),
            "Test Script Files (*.tst)",
        )
        if not selected:
            return
        path = Path(selected)
        if path.suffix.lower() != ".tst":
            path = path.with_suffix(".tst")
        self._script_manager.write_script(path, "")
        self._active_script_path = path
        self._reload_script_into_list()

    def reset_counters(self) -> None:
        self.control_panel.label_pass.setText("0")
        self.control_panel.label_fail.setText("0")
        self.control_panel.progress_total.setValue(0)
        self.control_panel.progress_test.setValue(0)
        self.control_panel.edit_current_test.clear()

    def _ensure_results_dir(self) -> Path:
        self._RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        return self._RESULTS_DIR

    def _default_export_basename(self) -> str:
        def _sanitize(value: str) -> str:
            cleaned = re.sub(r"\s+", "_", value.strip())
            return re.sub(r'[\\/:*?"<>|]+', "", cleaned)

        part = _sanitize(self.control_panel.edit_part_number.text())
        serial = _sanitize(self.control_panel.edit_serial_number.text())
        if part and serial:
            return f"{part}_{serial}"
        return "report"

    def _export_metadata(self, title: str) -> dict[str, str]:
        return {
            "title": title,
            "part_number": self.control_panel.edit_part_number.text().strip(),
            "serial_number": self.control_panel.edit_serial_number.text().strip(),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user_name": str(self._user_info.get("name", "")),
            "user_role": str(self._user_info.get("role", "")),
        }

    def _format_text_header(self, meta: dict[str, str]) -> str:
        return (
            f"Title: {meta['title']}\n"
            f"Part Number: {meta['part_number']}\n"
            f"Serial Number: {meta['serial_number']}\n"
            f"Date: {meta['date']}\n"
            f"User: {meta['user_name']} ({meta['user_role']})\n"
            "-------------------\n"
        )

    def open_results_folder(self) -> None:
        folder = self._ensure_results_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder.resolve())))

    def export_results_csv(self) -> None:
        if self.results_table.rowCount() == 0:
            QMessageBox.information(self, "Export to CSV", "No results to export.")
            return
        default = self._ensure_results_dir() / f"{self._default_export_basename()}.csv"
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Export results to CSV",
            str(default),
            "CSV Files (*.csv)",
        )
        if not selected:
            return
        self._write_results_csv(Path(selected))

    def save_results_json(self) -> None:
        if self.results_table.rowCount() == 0:
            QMessageBox.information(self, "Save Results", "No results to save.")
            return
        default = self._ensure_results_dir() / f"{self._default_export_basename()}.json"
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Save Results",
            str(default),
            "JSON Files (*.json)",
        )
        if not selected:
            return
        self._write_results_json(Path(selected))

    def _write_results_csv(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        is_operator = self._is_operator()
        headers = (
            ["Test Name", "Value", "Result"]
            if is_operator
            else ["Test Name", "Value", "Min", "Max", "Result"]
        )
        columns = [0, 1, 4] if is_operator else [0, 1, 2, 3, 4]
        with path.open("w", newline="", encoding="utf-8") as f:
            meta = self._export_metadata("DFX Tester - Test Report")
            f.write(self._format_text_header(meta))
            writer = csv.writer(f)
            writer.writerow(headers)
            for row in range(self.results_table.rowCount()):
                writer.writerow(
                    [
                        self.results_table.item(row, c).text()
                        if self.results_table.item(row, c)
                        else ""
                        for c in columns
                    ]
                )

    def _write_results_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        is_operator = self._is_operator()
        keys = (
            ("test_name", "value", "result")
            if is_operator
            else ("test_name", "value", "min", "max", "result")
        )
        columns = [0, 1, 4] if is_operator else [0, 1, 2, 3, 4]
        rows: list[dict[str, str]] = []
        for row in range(self.results_table.rowCount()):
            rows.append(
                {
                    keys[idx]: (
                        self.results_table.item(row, col).text()
                        if self.results_table.item(row, col)
                        else ""
                    )
                    for idx, col in enumerate(columns)
                }
            )
        meta = self._export_metadata("DFX Tester - Test Report")
        payload = {
            "title": meta["title"],
            "part_number": meta["part_number"],
            "serial_number": meta["serial_number"],
            "date": meta["date"],
            "user_name": meta["user_name"],
            "user_role": meta["user_role"],
            "script": self._active_script_path.name,
            "rows": rows,
        }
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _make_log_button(
        self,
        name: str,
        tip: str,
        fallback: QStyle.StandardPixmap,
        icon_name: str,
    ) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName(name)
        btn.setToolTip(tip)
        btn.setAutoRaise(True)
        btn.setFixedSize(28, 28)
        btn.setIconSize(QSize(18, 18))
        btn.setIcon(self._icon(icon_name, fallback))
        return btn

    def save_log_to_file(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Save trace log",
            str(self._ensure_results_dir() / f"{self._default_export_basename()}.txt"),
            "Text Files (*.txt)",
        )
        if not selected:
            return
        meta = self._export_metadata("DFX Tester - Trace Log")
        payload = self._format_text_header(meta) + "\n" + self.trace_log.toPlainText()
        Path(selected).write_text(payload, encoding="utf-8")

    def copy_log_to_clipboard(self) -> None:
        self.trace_log.selectAll()
        self.trace_log.copy()
        cursor = self.trace_log.textCursor()
        cursor.clearSelection()
        self.trace_log.setTextCursor(cursor)

    def _setup_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        ribbon = QHBoxLayout()
        self.btn_toggle_theme = self._make_ribbon_button("btn_toggle_theme", "Theme")
        self.btn_toggle_theme.clicked.connect(self.toggle_theme)
        ribbon.addWidget(self.btn_toggle_theme)

        self.btn_load_script = self._make_ribbon_button(
            "btn_load_script", "Open Test File"
        )
        self.btn_load_script.clicked.connect(self.load_script)
        ribbon.addWidget(self.btn_load_script)

        self.btn_edit_script = self._make_ribbon_button(
            "btn_edit_script", "Edit Test File"
        )
        self.btn_edit_script.clicked.connect(self.open_script_editor)
        ribbon.addWidget(self.btn_edit_script)

        self.label_active_script = QLabel("")
        ribbon.addSpacing(12)
        ribbon.addWidget(self.label_active_script)

        ribbon.addStretch()

        self.btn_logout = self._make_ribbon_button("btn_logout", "Log Out")
        self.btn_logout.clicked.connect(self.logout)
        ribbon.addWidget(self.btn_logout)

        self.btn_exit = self._make_ribbon_button("btn_exit", "Exit")
        self.btn_exit.clicked.connect(self.close)
        ribbon.addWidget(self.btn_exit)

        main_layout.addLayout(ribbon)

        main_row = QHBoxLayout()
        main_row.setContentsMargins(0, 0, 0, 0)
        main_row.setSpacing(8)

        self.test_list = QListWidget()
        self.test_list.setObjectName("test_list")
        self.test_list.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self.test_list.setItemAlignment(Qt.AlignmentFlag.AlignTop)

        self.left_sidebar = QWidget()
        self.left_sidebar.setMinimumWidth(200)
        self.left_sidebar.setMaximumWidth(280)
        sidebar_layout = QVBoxLayout(self.left_sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(8)
        sidebar_layout.addWidget(self.test_list, stretch=1)
        if SHOW_LIVE_MONITOR:
            self.instrument_panel = InstrumentPanelWidget()
            sidebar_layout.addWidget(self.instrument_panel, stretch=0)

        results_table_container = QWidget()
        center_layout = QVBoxLayout(results_table_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(6)

        self.edit_filter_results = QLineEdit()
        self.edit_filter_results.setObjectName("edit_filter_results")
        self.edit_filter_results.setClearButtonEnabled(True)
        self.edit_filter_results.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.edit_filter_results.setPlaceholderText(
            "\U0001F50D Search results (Test Name, Status...)"
        )
        self.edit_filter_results.textChanged.connect(self._filter_table_results)
        center_layout.addWidget(self.edit_filter_results)

        self.results_table = QTableWidget(0, 5)
        self.results_table.setObjectName("results_table")
        self.results_table.setHorizontalHeaderLabels(
            ["Test Name", "Value", "Min", "Max", "Result"]
        )
        header = self.results_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionsMovable(True)
        for col in range(4):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.results_table.setColumnWidth(0, 250)
        self.results_table.setColumnWidth(1, 100)
        self.results_table.setColumnWidth(2, 100)
        self.results_table.setColumnWidth(3, 100)
        center_layout.addWidget(self.results_table)

        self.trace_log = QTextEdit()
        self.trace_log.setObjectName("trace_log")
        self.trace_log.setReadOnly(True)
        self.trace_log.setMinimumHeight(80)

        log_bar = QHBoxLayout()
        log_bar.addWidget(QLabel("HW Trace"))
        log_bar.addStretch()

        SP = QStyle.StandardPixmap
        self.btn_save_log = self._make_log_button(
            "btn_save_log", "Save log", SP.SP_DialogSaveButton, "save"
        )
        self.btn_save_log.clicked.connect(self.save_log_to_file)
        log_bar.addWidget(self.btn_save_log)

        self.btn_copy_log = self._make_log_button(
            "btn_copy_log", "Copy log", SP.SP_FileIcon, "copy"
        )
        self.btn_copy_log.clicked.connect(self.copy_log_to_clipboard)
        log_bar.addWidget(self.btn_copy_log)

        self.btn_clear_log = self._make_log_button(
            "btn_clear_log", "Clear log", SP.SP_TrashIcon, "clear"
        )
        self.btn_clear_log.clicked.connect(self._clear_trace)
        log_bar.addWidget(self.btn_clear_log)

        log_bar.addSpacing(16)
        self.chk_display_cmds = QCheckBox("Display tst file commands")
        self.chk_display_cmds.setChecked(True)
        self.chk_display_cmds.toggled.connect(self._refresh_trace_display)
        log_bar.addWidget(self.chk_display_cmds)

        trace_container = QWidget()
        trace_layout = QVBoxLayout(trace_container)
        trace_layout.setContentsMargins(0, 0, 0, 0)
        trace_layout.addLayout(log_bar)
        trace_layout.addWidget(self.trace_log)

        v_splitter = QSplitter(Qt.Vertical)
        v_splitter.setObjectName("center_splitter")
        v_splitter.addWidget(results_table_container)
        v_splitter.addWidget(trace_container)
        v_splitter.setStretchFactor(0, 7)
        v_splitter.setStretchFactor(1, 3)
        v_splitter.setSizes([700, 300])
        v_splitter.setCollapsible(0, False)
        v_splitter.setCollapsible(1, False)
        v_splitter.setHandleWidth(4)

        self.control_panel = ControlPanelWidget(self._user_info)
        self.control_panel.setObjectName("control_panel")
        self.control_panel.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self.control_panel.setMinimumWidth(280)
        self.control_panel.setMaximumWidth(340)
        self.control_panel.btn_start.clicked.connect(self.start_tests)
        self.control_panel.btn_stop.clicked.connect(self.stop_tests)
        self.control_panel.edit_part_number.textEdited.connect(
            self._mark_part_number_user_edited
        )

        main_row.addWidget(self.left_sidebar)
        main_row.addWidget(v_splitter, stretch=1)
        main_row.addWidget(self.control_panel)

        main_layout.addLayout(main_row, stretch=1)

    def _filter_table_results(self, text: str) -> None:
        needle = text.strip().lower()
        for row in range(self.results_table.rowCount()):
            if not needle:
                self.results_table.setRowHidden(row, False)
                continue
            name_item = self.results_table.item(row, 0)
            result_item = self.results_table.item(row, 4)
            haystack = " ".join(
                i.text().lower() for i in (name_item, result_item) if i is not None
            )
            self.results_table.setRowHidden(row, needle not in haystack)

    def _theme_path(self) -> Path:
        name = "dark_theme.qss" if self.is_dark_mode else "light_theme.qss"
        return Path(__file__).resolve().parents[1] / "assets" / name

    def _apply_theme_file(self) -> None:
        path = self._theme_path()
        qss = path.read_text(encoding="utf-8")
        self.setStyleSheet(qss)

    def toggle_theme(self) -> None:
        self.is_dark_mode = not self.is_dark_mode
        self._apply_theme_file()
        self._update_icons(self.is_dark_mode)

    def _user_can_edit_scripts(self) -> bool:
        """Only Engineers/Admins can open the script editor."""
        return self._current_role() in {"Engineer", "Admin"}

    def _mark_part_number_user_edited(self, _text: str) -> None:
        self._part_number_user_edited = True

    def load_script(self) -> None:
        """Pick a `.tst` file and make it the active sequence."""
        scripts_dir = self._script_manager.scripts_dir
        scripts_dir.mkdir(parents=True, exist_ok=True)

        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Load test script",
            str(scripts_dir),
            "Test Script Files (*.tst);;All Files (*)",
        )
        if not selected:
            return

        self._active_script_path = Path(selected)
        self._reload_script_into_list()

    def open_script_editor(self) -> None:
        """Pick a `.tst` file from the data folder and open it in the editor."""
        if not self._user_can_edit_scripts():
            QMessageBox.information(
                self,
                "Not allowed",
                "Your role does not have permission to edit test scripts.",
            )
            return

        scripts_dir = self._script_manager.scripts_dir
        scripts_dir.mkdir(parents=True, exist_ok=True)

        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select test script",
            str(scripts_dir),
            "Test Script Files (*.tst);;All Files (*)",
        )
        if not selected:
            return

        path = Path(selected)
        dialog = ScriptEditorDialog(self._script_manager, parent=self)
        dialog.load_file(path)
        dialog.exec()

        if path == self._active_script_path:
            self._reload_script_into_list()

    def _reload_script_into_list(self) -> None:
        """Parse the active script and repopulate the test list checkboxes."""
        self.test_list.clear()
        self.label_active_script.setText(
            f"Script: {self._active_script_path.name}"
        )

        if not self._active_script_path.is_file():
            self.append_trace(
                f"Active script not found: {self._active_script_path}"
            )
            return

        try:
            document = self._script_manager.load_document(self._active_script_path)
            steps = document.steps
        except ScriptParseError as exc:
            QMessageBox.warning(
                self,
                "Script parse error",
                f"Could not parse {self._active_script_path.name}:\n"
                f"line {exc.line_no}: {exc.msg}",
            )
            self.append_trace(
                f"Script parse error at line {exc.line_no}: {exc.msg}"
            )
            return
        except (OSError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Script load error",
                f"Could not load {self._active_script_path.name}:\n{exc}",
            )
            return

        for step in steps:
            item = QListWidgetItem(step.name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.test_list.addItem(item)

        script_part_number = document.metadata.get("part_number", "").strip()
        if script_part_number and not self._part_number_user_edited:
            self.control_panel.edit_part_number.setText(script_part_number)

        self.append_trace(
            f"Loaded {len(steps)} step(s) from {self._active_script_path.name}."
        )

    def _selected_test_names(self) -> list[str]:
        """Return only checked test names from the list widget."""
        names: list[str] = []
        for i in range(self.test_list.count()):
            item = self.test_list.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                names.append(item.text())
        return names

    def start_tests(self) -> None:
        tests_to_run = self._selected_test_names()
        if not tests_to_run:
            self.append_trace("No tests selected (check at least one item in the list).")
            return

        if not self._active_script_path.is_file():
            QMessageBox.warning(
                self,
                "No script",
                f"Active script does not exist: {self._active_script_path}",
            )
            return

        operator = self.control_panel.edit_user_name.text().strip()
        part_number = self.control_panel.edit_part_number.text().strip()
        serial_number = self.control_panel.edit_serial_number.text().strip()

        if not part_number or not serial_number:
            QMessageBox.warning(
                self,
                "Missing unit info",
                "Part Number and Serial Number are required before starting a test.",
            )
            return

        self.results_table.setRowCount(0)
        self.control_panel.progress_total.setValue(0)
        self.control_panel.progress_test.setValue(0)
        self.control_panel.edit_current_test.clear()
        self.control_panel.label_pass.setText("0")
        self.control_panel.label_fail.setText("0")
        self._clear_trace()

        self.control_panel.btn_start.setEnabled(False)
        self.control_panel.btn_stop.setEnabled(True)

        loop_count = (
            self.control_panel.spin_loops.value()
            if self.control_panel.chk_loops.isChecked()
            else 1
        )
        stop_on_fail = self.control_panel.chk_stop_on_fail.isChecked()

        self.test_thread = TestRunnerThread(
            self._active_script_path,
            set(tests_to_run),
            loop_count=loop_count,
            stop_on_fail=stop_on_fail,
            operator=operator,
            part_number=part_number,
            serial_number=serial_number,
            script_manager=self._script_manager,
        )
        self.test_thread.log_msg.connect(self.append_trace)
        self.test_thread.test_result.connect(self.update_results_table)
        self.test_thread.progress_total.connect(self.control_panel.progress_total.setValue)
        self.test_thread.progress_test.connect(self.control_panel.progress_test.setValue)
        self.test_thread.current_test.connect(self.control_panel.edit_current_test.setText)
        self.test_thread.prompt_request.connect(self._on_prompt_request)
        self.test_thread.script_log.connect(self._on_script_log)
        self.test_thread.finished.connect(self.on_tests_finished)
        self.test_thread.start()

    def _on_prompt_request(self, msg: str) -> None:
        """Show a modal prompt; resume the runner once the operator clicks OK."""
        QMessageBox.information(self, "Test Prompt", msg)
        if self.test_thread is not None:
            self.test_thread.resume()

    def _on_script_log(self, msg: str) -> None:
        """Append an operator-authored Log line to the trace, distinctly styled."""
        self._record_trace("log", msg)

    def _format_trace_html(self, entry_type: str, text: str) -> str:
        if entry_type == "log":
            return (
                '<span style="color:#22d3ee;"><i>[LOG]</i> '
                f"{html.escape(text)}</span>"
            )
        return html.escape(text)

    def _entry_passes_filter(self, entry: dict) -> bool:
        if self.chk_display_cmds.isChecked():
            return True
        return entry["type"] != "cmd"

    def _record_trace(self, entry_type: str, text: str) -> None:
        entry = {
            "type": entry_type,
            "text": text,
            "html": self._format_trace_html(entry_type, text),
        }
        self._trace_history.append(entry)
        if self._entry_passes_filter(entry):
            self.trace_log.append(entry["html"])

    def _refresh_trace_display(self) -> None:
        self.trace_log.clear()
        for entry in self._trace_history:
            if self._entry_passes_filter(entry):
                self.trace_log.append(entry["html"])

    def _clear_trace(self) -> None:
        self._trace_history.clear()
        self.trace_log.clear()

    def stop_tests(self) -> None:
        if self.test_thread and self.test_thread.isRunning():
            self.test_thread.stop()
            self.append_trace("Stopping sequence...")

    def logout(self) -> None:
        """Closes the main window and signals the application to restart the login flow."""
        confirm = QMessageBox.question(
            self,
            "Log Out",
            "Are you sure you want to log out and switch users?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            if hasattr(self, "monitor_thread") and self.monitor_thread.isRunning():
                self.monitor_thread.stop()
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            self.setProperty("logout_requested", True)
            app = QApplication.instance()
            if app is not None:
                app.setProperty("logout_requested", True)
            self.close()

    def closeEvent(self, event) -> None:
        if hasattr(self, "monitor_thread") and self.monitor_thread.isRunning():
            self.monitor_thread.stop()
        super().closeEvent(event)

    def update_results_table(self, test_name: str, result: TestResultPayload) -> None:
        row = self.results_table.rowCount()
        self.results_table.insertRow(row)

        passed = bool(result["passed"])
        status = "PASS" if passed else "FAIL"
        is_measurement = bool(result.get("is_measurement", True))

        if is_measurement:
            unit = result["unit"]
            val_str = (
                f"{_format_measurement(result['value'])} {unit}".rstrip()
            )
            min_str = _format_measurement(result["min"])
            max_str = _format_measurement(result["max"])
        else:
            val_str = _NA
            min_str = _NA
            max_str = _NA

        self.results_table.setItem(row, 0, QTableWidgetItem(test_name))
        self.results_table.setItem(row, 1, QTableWidgetItem(val_str))
        self.results_table.setItem(row, 2, QTableWidgetItem(min_str))
        self.results_table.setItem(row, 3, QTableWidgetItem(max_str))

        status_item = QTableWidgetItem(status)
        status_item.setForeground(Qt.GlobalColor.green if passed else Qt.GlobalColor.red)
        self.results_table.setItem(row, 4, status_item)

        if passed:
            n = int(self.control_panel.label_pass.text() or "0") + 1
            self.control_panel.label_pass.setText(str(n))
        else:
            n = int(self.control_panel.label_fail.text() or "0") + 1
            self.control_panel.label_fail.setText(str(n))

    def append_trace(self, msg: str) -> None:
        entry_type = "cmd" if msg.startswith("Executing:") else "info"
        self._record_trace(entry_type, msg)

    def on_tests_finished(self) -> None:
        if self.control_panel.btn_start.isEnabled():
            return
        self.control_panel.btn_start.setEnabled(True)
        self.control_panel.btn_stop.setEnabled(False)
        self.append_trace("Sequence Complete.")
