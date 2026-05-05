"""Right-hand ATE control rail (start/stop, user, unit, status)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class ControlPanelWidget(QWidget):
    def __init__(self, user_info: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)

        self.btn_start = QPushButton("Start")
        self.btn_start.setMinimumHeight(56)
        root.addWidget(self.btn_start)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setObjectName("btn_stop")
        root.addWidget(self.btn_stop)

        user_box = QGroupBox("User")
        user_form = QFormLayout(user_box)
        self.edit_user_name = QLineEdit()
        self.edit_user_name.setReadOnly(True)
        self.edit_user_name.setText(str(user_info.get("name", "")))
        user_form.addRow("Name", self.edit_user_name)
        self.edit_user_level = QLineEdit()
        self.edit_user_level.setReadOnly(True)
        self.edit_user_level.setText(str(user_info.get("role", "")))
        user_form.addRow("Level", self.edit_user_level)
        root.addWidget(user_box)

        unit_box = QGroupBox("Unit")
        unit_form = QFormLayout(unit_box)
        self.edit_part_number = QLineEdit()
        unit_form.addRow("Part number", self.edit_part_number)
        self.edit_serial_number = QLineEdit()
        unit_form.addRow("Serial number", self.edit_serial_number)
        root.addWidget(unit_box)

        status_box = QGroupBox("Status")
        status_layout = QVBoxLayout(status_box)
        self.edit_current_test = QLineEdit()
        self.edit_current_test.setReadOnly(True)
        self.edit_current_test.setPlaceholderText("—")
        status_layout.addWidget(QLabel("Current test"))
        status_layout.addWidget(self.edit_current_test)

        status_layout.addWidget(QLabel("Test progress"))
        self.progress_test = QProgressBar()
        status_layout.addWidget(self.progress_test)

        status_layout.addWidget(QLabel("Total progress"))
        self.progress_total = QProgressBar()
        status_layout.addWidget(self.progress_total)

        counters = QHBoxLayout()
        self.label_pass = QLabel("0")
        self.label_pass.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_pass.setStyleSheet(
            "background-color: #22c55e; color: white; font-weight: bold; "
            "padding: 8px; border-radius: 4px;"
        )
        self.label_fail = QLabel("0")
        self.label_fail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_fail.setStyleSheet(
            "background-color: #ef4444; color: white; font-weight: bold; "
            "padding: 8px; border-radius: 4px;"
        )
        counters.addWidget(self.label_pass)
        counters.addWidget(self.label_fail)
        status_layout.addLayout(counters)

        loops_row = QHBoxLayout()
        loops_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.chk_loops = QCheckBox("Loops")
        self.spin_loops = QSpinBox()
        self.spin_loops.setMinimum(1)
        self.spin_loops.setMaximum(999)
        self.spin_loops.setValue(1)
        self.spin_loops.setMinimumWidth(72)
        self.spin_loops.setMinimumHeight(28)
        self.spin_loops.setEnabled(False)
        self.chk_loops.toggled.connect(self.spin_loops.setEnabled)
        loops_row.addWidget(self.chk_loops, 0, Qt.AlignmentFlag.AlignVCenter)
        loops_row.addWidget(self.spin_loops, 0, Qt.AlignmentFlag.AlignVCenter)
        status_layout.addLayout(loops_row)

        self.chk_stop_on_fail = QCheckBox("Stop on fail")
        status_layout.addWidget(self.chk_stop_on_fail)

        root.addWidget(status_box)
        root.addStretch()
