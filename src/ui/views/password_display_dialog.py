"""Modal dialog for displaying and copying temporary passwords."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStyle,
    QToolButton,
    QToolTip,
    QVBoxLayout,
)


class PasswordDisplayDialog(QDialog):
    """Shows a generated password and provides one-click clipboard copy."""

    _ICONS_DIR = Path(__file__).resolve().parents[1] / "assets" / "icons"

    def __init__(self, title: str, message: str, password: str, parent=None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle(title)
        self.resize(480, 150)
        self._password = password
        self._default_copy_tooltip = "Copy password"

        root = QVBoxLayout(self)
        root.addWidget(QLabel(message))

        row = QHBoxLayout()
        self.edit_password = QLineEdit(password)
        self.edit_password.setReadOnly(True)

        # Monospace prevents ambiguous character rendering (e.g. O/0, l/1).
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setFixedPitch(True)
        self.edit_password.setFont(mono)
        row.addWidget(self.edit_password, stretch=1)

        self.btn_copy = QToolButton()
        self.btn_copy.setAutoRaise(True)
        self.btn_copy.setIcon(self._icon("copy", QStyle.StandardPixmap.SP_FileIcon))
        self.btn_copy.setToolTip(self._default_copy_tooltip)
        self.btn_copy.clicked.connect(self._copy_password)
        row.addWidget(self.btn_copy)

        root.addLayout(row)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        root.addWidget(btn_close)

    def _icon(self, name: str, fallback: QStyle.StandardPixmap) -> QIcon:
        for ext in (".svg", ".png"):
            candidate = self._ICONS_DIR / f"{name}{ext}"
            if candidate.is_file():
                return QIcon(str(candidate))
        return self.style().standardIcon(fallback)

    def _copy_password(self) -> None:
        QApplication.clipboard().setText(self._password)
        self.btn_copy.setToolTip("Copied!")
        tip_pos = self.btn_copy.mapToGlobal(self.btn_copy.rect().center())
        QToolTip.showText(tip_pos, "Copied!", self.btn_copy)
        QTimer.singleShot(1200, self._restore_tooltip)

    def _restore_tooltip(self) -> None:
        self.btn_copy.setToolTip(self._default_copy_tooltip)
