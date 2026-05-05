"""Admin-only user management dialog."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from logic.database_manager import DatabaseManager
from ui.views.password_display_dialog import PasswordDisplayDialog


class UserManagementDialog(QDialog):
    _ROLES = ("Operator", "Engineer", "Admin")

    def __init__(self, current_username: str, parent=None) -> None:
        super().__init__(parent)
        self._db = DatabaseManager()
        self._current_username = current_username
        self.setWindowTitle("User Management")
        self.resize(600, 380)

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Manage users and role permissions."))

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Username", "Role", "Must Change Password"])
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self._table)

        row = QHBoxLayout()
        self._btn_add = QPushButton("Add User")
        self._btn_add.clicked.connect(self._add_user)
        row.addWidget(self._btn_add)

        self._btn_delete = QPushButton("Delete User")
        self._btn_delete.clicked.connect(self._delete_user)
        row.addWidget(self._btn_delete)

        self._btn_role = QPushButton("Edit Role")
        self._btn_role.clicked.connect(self._edit_role)
        row.addWidget(self._btn_role)

        self._btn_reset = QPushButton("Reset Password")
        self._btn_reset.clicked.connect(self._reset_password)
        row.addWidget(self._btn_reset)
        row.addStretch()
        root.addLayout(row)

        self._refresh()

    def _selected_username(self) -> str | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return item.text() if item else None

    def _refresh(self) -> None:
        users = self._db.list_users()
        self._table.setRowCount(0)
        for user in users:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(str(user["username"])))
            self._table.setItem(row, 1, QTableWidgetItem(str(user["role"])))
            self._table.setItem(
                row,
                2,
                QTableWidgetItem("Yes" if bool(user["must_change_pwd"]) else "No"),
            )

    def _add_user(self) -> None:
        username, ok = QInputDialog.getText(self, "Add User", "Username")
        if not ok or not username.strip():
            return
        role, ok = QInputDialog.getItem(self, "Add User", "Role", list(self._ROLES), 0, False)
        if not ok:
            return
        try:
            temp_password = self._db.reset_password_for_new_user(username.strip(), role)
            dialog = PasswordDisplayDialog(
                title="User Created",
                message=f"User '{username.strip()}' created. Share this temporary password:",
                password=temp_password,
                parent=self,
            )
            dialog.exec()
            self._refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Add User Failed", str(exc))

    def _delete_user(self) -> None:
        username = self._selected_username()
        if not username:
            QMessageBox.information(self, "Delete User", "Select a user first.")
            return
        if username == self._current_username:
            QMessageBox.warning(self, "Delete User", "You cannot delete the current user.")
            return
        choice = QMessageBox.question(
            self,
            "Delete User",
            f"Delete '{username}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            self._db.delete_user(username)
            self._refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Delete User Failed", str(exc))

    def _edit_role(self) -> None:
        username = self._selected_username()
        if not username:
            QMessageBox.information(self, "Edit Role", "Select a user first.")
            return
        role, ok = QInputDialog.getItem(self, "Edit Role", "Role", list(self._ROLES), 0, False)
        if not ok:
            return
        try:
            self._db.update_role(username, role)
            self._refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Edit Role Failed", str(exc))

    def _reset_password(self) -> None:
        username = self._selected_username()
        if not username:
            QMessageBox.information(self, "Reset Password", "Select a user first.")
            return
        try:
            temp_password = self._db.reset_password(username)
            dialog = PasswordDisplayDialog(
                title="Password Reset",
                message=f"Temporary password for '{username}':",
                password=temp_password,
                parent=self,
            )
            dialog.exec()
            self._refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Reset Password Failed", str(exc))
