"""Batch pre-test setup dialog for scanning multiple UUT serials."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from config import LOAD_SERIALS, UUT_TYPES
from logic.models import BatchUnit


class BatchPreTestDialog(QDialog):
    """Collect batch size and serial numbers while keeping a fixed slot mapping."""

    def __init__(
        self,
        tester_name_default: str,
        default_uut_type: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Batch Pre-Test Setup")
        self.resize(620, 420)
        self._serial_edits: list[QLineEdit] = []

        root = QVBoxLayout(self)
        form = QFormLayout()

        from PySide6.QtWidgets import QComboBox  # local import keeps file compact

        self._combo_uut = QComboBox()
        self._combo_uut.addItems(UUT_TYPES)
        if default_uut_type:
            self._combo_uut.setCurrentText(default_uut_type.strip())
        form.addRow("UUT Type", self._combo_uut)

        self._edit_tester = QLineEdit()
        self._edit_tester.setText(tester_name_default.strip())
        form.addRow("Tester Name", self._edit_tester)

        self._spin_count = QSpinBox()
        self._spin_count.setMinimum(1)
        self._spin_count.setMaximum(max(1, len(LOAD_SERIALS)))
        self._spin_count.setValue(1)
        self._spin_count.valueChanged.connect(self._rebuild_rows)
        form.addRow("Units in batch", self._spin_count)
        root.addLayout(form)

        self._units_box = QGroupBox("Serial Scan")
        self._grid = QGridLayout(self._units_box)
        self._grid.setContentsMargins(10, 10, 10, 10)
        self._grid.setHorizontalSpacing(10)
        self._grid.setVerticalSpacing(6)
        root.addWidget(self._units_box)

        self._error = QLabel("")
        self._error.setObjectName("lbl_error")
        root.addWidget(self._error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._try_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._rebuild_rows(self._spin_count.value())

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._serial_edits:
            self._serial_edits[0].setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def _clear_layout(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _rebuild_rows(self, count: int) -> None:
        self._clear_layout()
        self._serial_edits.clear()
        headers = ["Position", "Load channel", "Load serial", "UUT serial"]
        for col, text in enumerate(headers):
            lbl = QLabel(text)
            lbl.setObjectName("lbl_batch_header")
            self._grid.addWidget(lbl, 0, col)

        for idx in range(count):
            slot = idx + 1
            pos_label = QLabel(f"Position {slot}")
            channel_label = QLabel(f"CH{slot}")
            load_serial = QLabel(LOAD_SERIALS[idx] if idx < len(LOAD_SERIALS) else f"LOAD-{slot}")
            edit = QLineEdit()
            edit.setPlaceholderText("Scan or type serial number")
            edit.returnPressed.connect(
                lambda idx=idx: self._focus_next_serial_field(idx)
            )

            self._grid.addWidget(pos_label, slot, 0)
            self._grid.addWidget(channel_label, slot, 1)
            self._grid.addWidget(load_serial, slot, 2)
            self._grid.addWidget(edit, slot, 3)
            self._serial_edits.append(edit)

    def _focus_next_serial_field(self, current_index: int) -> None:
        next_index = current_index + 1
        if next_index >= len(self._serial_edits):
            return
        next_edit = self._serial_edits[next_index]
        next_edit.setFocus(Qt.FocusReason.TabFocusReason)
        next_edit.selectAll()

    def _try_accept(self) -> None:
        tester = self._edit_tester.text().strip()
        uut = self._combo_uut.currentText().strip()
        serials = [edit.text().strip() for edit in self._serial_edits]
        if not tester or not uut:
            self._error.setText("Tester name and UUT type are required.")
            return
        if any(not item for item in serials):
            self._error.setText("Every position must have a serial number.")
            return
        normalized = [item.casefold() for item in serials]
        if len(set(normalized)) != len(normalized):
            self._error.setText("Duplicate serial numbers are not allowed.")
            return
        self._error.clear()
        self.accept()

    def result_dict(self) -> dict[str, object]:
        units: list[BatchUnit] = []
        for idx, edit in enumerate(self._serial_edits):
            slot = idx + 1
            load_serial = LOAD_SERIALS[idx] if idx < len(LOAD_SERIALS) else f"LOAD-{slot}"
            units.append(
                BatchUnit(
                    serial_number=edit.text().strip(),
                    slot_index=slot,
                    position_label=f"Position {slot}",
                    load_channel=f"CH{slot}",
                    load_serial_number=load_serial,
                )
            )
        return {
            "uut_type": self._combo_uut.currentText().strip(),
            "tester_name": self._edit_tester.text().strip(),
            "batch_units": units,
        }
