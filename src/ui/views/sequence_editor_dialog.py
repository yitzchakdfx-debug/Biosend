"""Dialog for editing active test sequence order and inclusion."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from logic.database_manager import DatabaseManager
from logic.models import TestStep
from logic.script_manager import ScriptManager


class SequenceEditorDialog(QDialog):
    def __init__(
        self,
        active_names: list[str],
        available_steps: list[TestStep],
        *,
        persist_new_version: bool = False,
        catalog_test_name: str = "",
        catalog_uut_type: str = "",
        created_by: str = "",
        employee_id: str = "",
        db: DatabaseManager | None = None,
        script_manager: ScriptManager | None = None,
        document_metadata: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Sequence")
        self.resize(760, 460)

        self._available_order = [step.name for step in available_steps]
        self._step_by_name = {step.name: step for step in available_steps}
        self._persist_new_version = persist_new_version
        self._catalog_test_name = catalog_test_name.strip()
        self._catalog_uut_type = catalog_uut_type.strip()
        self._created_by = created_by.strip()
        self._employee_id = employee_id.strip()
        self._db = db
        self._script_manager = script_manager
        self._document_metadata = dict(document_metadata or {})

        root = QVBoxLayout(self)
        body = QHBoxLayout()
        body.setSpacing(12)

        left_col = QVBoxLayout()
        left_col.addWidget(QLabel("Active Sequence"))
        self.active_list = QListWidget()
        self.active_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.active_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.active_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        left_col.addWidget(self.active_list)
        body.addLayout(left_col, stretch=2)

        right_col = QVBoxLayout()
        right_col.addWidget(QLabel("Available Tests"))
        self.available_list = QListWidget()
        self.available_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        right_col.addWidget(self.available_list, stretch=1)
        self.btn_add = QPushButton("Add")
        self.btn_add.clicked.connect(self._add_selected_test)
        right_col.addWidget(self.btn_add)
        right_col.addStretch()
        body.addLayout(right_col, stretch=1)

        root.addLayout(body, stretch=1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._seed_lists(active_names)

    def _on_save(self) -> None:
        if self._db is None or self._script_manager is None:
            QMessageBox.warning(self, "Save", "Version save is not configured.")
            return
        tname = self._catalog_test_name
        uut = self._catalog_uut_type
        if not tname:
            QMessageBox.warning(self, "Save", "Test name missing for versioning.")
            return
        if not uut:
            QMessageBox.warning(
                self,
                "Save",
                "UUT type is required. Run pre-test setup or ensure it is filled in.",
            )
            return
        ver_name, ok = QInputDialog.getText(
            self,
            "Save New Version",
            "Enter a unique version name (e.g. V1.1_custom):",
            text="V1.1_custom",
        )
        if not ok:
            return
        ver_name = ver_name.strip()
        if not ver_name:
            QMessageBox.warning(self, "Save", "Version name cannot be empty.")
            return
        invalid_chars = r'\/:*?"<>|'
        if any(ch in ver_name for ch in invalid_chars):
            QMessageBox.warning(
                self,
                "Invalid Name",
                f"Version name cannot contain any of the following characters:\n{invalid_chars}",
            )
            return
        if self._db.version_exists(tname, ver_name):
            QMessageBox.warning(
                self,
                "Save",
                f"Version {ver_name!r} already exists for test {tname!r}.",
            )
            return

        ordered_steps: list[TestStep] = []
        for nm in self.result_names():
            st = self._step_by_name.get(nm)
            if st is None:
                QMessageBox.warning(self, "Save", f"Unknown step: {nm}")
                return
            ordered_steps.append(st)

        try:
            text = self._script_manager.serialize_ordered_steps(
                ordered_steps,
                metadata=self._document_metadata or None,
            )
            self._db.add_test_version(tname, uut, ver_name, text, self._created_by)
        except Exception as exc:
            QMessageBox.warning(self, "Save Failed", str(exc))
            return

        try:
            self._db.log_audit_action(
                "Created new test version",
                username=self._created_by,
                employee_id=self._employee_id,
                details=f"test={tname!r} version={ver_name!r} uut_type={uut!r}",
            )
        except Exception:
            pass

        QMessageBox.information(self, "Saved", f"Stored version {ver_name!r} in catalog.")
        self.accept()

    def _seed_lists(self, active_names: list[str]) -> None:
        active_set = set(active_names)
        for name in active_names:
            self._append_active_item(name)
        for name in self._available_order:
            if name in active_set:
                continue
            self.available_list.addItem(name)

    def _append_active_item(self, name: str) -> None:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, name)
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(6, 2, 6, 2)
        row_layout.setSpacing(6)

        label = QLabel(name)
        delete_btn = QToolButton()
        delete_btn.setText("X")
        delete_btn.setToolTip("Remove from active sequence")
        delete_btn.clicked.connect(lambda _checked=False, it=item: self._remove_item(it))

        row_layout.addWidget(label, stretch=1)
        row_layout.addWidget(delete_btn, stretch=0)
        item.setSizeHint(row_widget.sizeHint())
        self.active_list.addItem(item)
        self.active_list.setItemWidget(item, row_widget)

    def _remove_item(self, item: QListWidgetItem) -> None:
        name = str(item.data(Qt.ItemDataRole.UserRole))
        row = self.active_list.row(item)
        if row >= 0:
            removed = self.active_list.takeItem(row)
            del removed
        self._insert_available_name(name)

    def _insert_available_name(self, name: str) -> None:
        if name in self._available_items():
            return
        order_index = self._available_order.index(name) if name in self._available_order else 10**9
        insert_row = self.available_list.count()
        for i in range(self.available_list.count()):
            current_name = self.available_list.item(i).text()
            current_idx = (
                self._available_order.index(current_name)
                if current_name in self._available_order
                else 10**9
            )
            if order_index < current_idx:
                insert_row = i
                break
        self.available_list.insertItem(insert_row, name)

    def _available_items(self) -> list[str]:
        return [self.available_list.item(i).text() for i in range(self.available_list.count())]

    def _add_selected_test(self) -> None:
        item = self.available_list.currentItem()
        if item is None:
            return
        name = item.text()
        self._append_active_item(name)
        self.available_list.takeItem(self.available_list.row(item))

    def result_names(self) -> list[str]:
        names: list[str] = []
        for i in range(self.active_list.count()):
            item = self.active_list.item(i)
            if item is None:
                continue
            names.append(str(item.data(Qt.ItemDataRole.UserRole)))
        return names
