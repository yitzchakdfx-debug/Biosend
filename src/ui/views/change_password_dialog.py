"""Forced password-change dialog used immediately after login."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from logic.auth_manager import AuthManager


class ChangePasswordDialog(QDialog):
    def __init__(self, auth: AuthManager, username: str, parent=None) -> None:
        super().__init__(parent)
        self._auth = auth
        self._username = username
        self.setWindowTitle("Change Password")
        self.setModal(True)

        root = QVBoxLayout(self)
        root.addWidget(QLabel(f"User: {username}"))
        root.addWidget(QLabel("You must change your password before continuing."))

        form = QFormLayout()
        self._new_password = QLineEdit()
        self._new_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm_password = QLineEdit()
        self._confirm_password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("New password", self._new_password)
        form.addRow("Confirm password", self._confirm_password)
        root.addLayout(form)

        self._error = QLabel("")
        root.addWidget(self._error)

        buttons = QHBoxLayout()
        buttons.addStretch()
        ok_btn = QPushButton("Update")
        ok_btn.clicked.connect(self._submit)
        buttons.addWidget(ok_btn)
        root.addLayout(buttons)

    def _submit(self) -> None:
        password = self._new_password.text()
        confirm = self._confirm_password.text()
        if password != confirm:
            self._error.setText("Passwords do not match.")
            return
        reason = self._auth.validate_password_strength(password)
        if reason:
            self._error.setText(reason)
            return
        try:
            self._auth.change_password(self._username, password)
        except Exception as exc:
            QMessageBox.critical(self, "Password Update Failed", str(exc))
            return
        self.accept()
