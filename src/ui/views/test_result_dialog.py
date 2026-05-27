"""Modal end-of-sequence result dialog (big PASS / FAIL banner)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class TestResultDialog(QDialog):
    def __init__(self, passed: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sequence Result")
        self.setModal(True)
        self.setFixedSize(480, 260)

        status_text = "Test Pass" if passed else "Test Fail"
        banner_bg = "#22c55e" if passed else "#ef4444"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(16)

        self._banner = QLabel(status_text)
        self._banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._banner.setMinimumHeight(120)
        self._banner.setStyleSheet(
            f"background-color: {banner_bg};"
            "color: #000000;"
            "font-size: 44pt;"
            "font-weight: 900;"
            "letter-spacing: 2px;"
            "border-radius: 6px;"
            "padding: 24px;"
        )
        layout.addWidget(self._banner, stretch=1)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self._btn_close = QPushButton("Close")
        self._btn_close.setFixedWidth(140)
        self._btn_close.setMinimumHeight(32)
        self._btn_close.setDefault(True)
        self._btn_close.clicked.connect(self.accept)
        button_row.addWidget(self._btn_close)
        button_row.addStretch()
        layout.addLayout(button_row)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        parent = self.parentWidget()
        if parent is not None:
            center = parent.geometry().center()
            self.move(
                center.x() - self.width() // 2,
                center.y() - self.height() // 2,
            )
