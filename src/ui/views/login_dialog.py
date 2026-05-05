"""Pre-launch login dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from logic.auth_manager import AuthManager
from ui.views.change_password_dialog import ChangePasswordDialog


class LoginDialog(QDialog):
    """Collect credentials and resolve role via AuthManager."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("DFX ATE Login")
        self._user_info: dict = {}
        self._auth = AuthManager()

        layout = QVBoxLayout(self)
        title = QLabel("DFX ATE Login")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        layout.addWidget(QLabel("Username:"))
        self._username = QLineEdit()
        layout.addWidget(self._username)

        layout.addWidget(QLabel("Password:"))
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self._password)

        btn = QPushButton("Login")
        btn.clicked.connect(self._on_login)
        layout.addWidget(btn)
        self._error_label = QLabel("")
        layout.addWidget(self._error_label)

    def _on_login(self) -> None:
        user_info = self._auth.login(
            self._username.text().strip(),
            self._password.text(),
        )
        if user_info is None:
            self._error_label.setText("Invalid username or password.")
            return
        self._error_label.clear()
        if bool(user_info.get("must_change_pwd")):
            dialog = ChangePasswordDialog(
                auth=self._auth,
                username=str(user_info.get("username", "")),
                parent=self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self._error_label.setText("Password change is required before login.")
                return
            user_info["must_change_pwd"] = False
        self._user_info = user_info
        self.accept()

    def get_user_info(self) -> dict:
        """Return the dict from the last successful login(); call after exec() returns Accepted."""
        return dict(self._user_info)
