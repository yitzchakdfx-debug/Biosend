# Architectural Execution Plan — Dashboard Refactor

## A. Up-front architectural calls (read first)

### A.1 Results colorization: delegate, not model migration
**Results widget is `QTableWidget`, not `QTableView` over a model.** A full migration to `QAbstractTableModel` is a multi-day refactor that touches `update_results_table`, `_on_loop_started`, `_filter_table_results`, and PDF/CSV cell readouts. To honor your architectural constraint without that blast radius, **use a `QStyledItemDelegate` on the existing `QTableWidget`**. The delegate reads the row's data via `index.data(Qt.DisplayRole)` on column 4 ("Result") and paints background per state. `update_results_table` stays purely a data-writer; no per-cell color setters in a loop. This satisfies the spirit of "model/delegate, not widget-painted" while keeping the change to a single new file plus one `setItemDelegate` call.

### A.2 "Save as log" semantics need confirmation
**Today**, `_finalize_run_reports` ([main_window.py:703-718](src/ui/views/main_window.py#L703-L718)) **always** archives a PDF at end-of-run. Two ways to wire the new checkbox:
- **(a) Gate the existing PDF archive** behind `control_panel.chk_save_log.isChecked()` — checkbox now controls whether each run is persisted.
- **(b) New independent flag** that controls only some new behavior (e.g., dumping the HW Trace alongside the PDF).

**Recommendation:** (a) — it matches the natural reading of the label and removes an always-on side effect for admins who don't want every run archived. Flag this in the PR description; if you prefer (b), the plan still applies, just point the gate at a different sink.

### A.3 No `sequence_finished(bool)` signal exists yet
**Solution:** Emit the new signal from `MainWindow` itself inside `on_tests_finished`, deriving the bool from `th.report_snapshot()[0]['overall_result']` (already used at [line 1153](src/ui/views/main_window.py#L1153)). Adding it to `TestRunnerThread` is also fine but expands the runner contract for one consumer; not worth it.

### A.4 Existing "Save log" button is different
**The current "Save log" *button* in the trace toolbar** ([main_window.py:540-544](src/ui/views/main_window.py#L540-L544)) is a different thing (saves trace .txt) — leave it alone. The new checkbox lives on the right rail.

---

## B. File-by-file change inventory

### B.1 `src/ui/widgets/control_panel.py`

**Remove:**
- The `user_box` block ([control_panel.py:48-59](src/ui/widgets/control_panel.py#L48-L59)) — its widgets (`edit_user_name`, `edit_user_level`) will be reconstructed inside the new left-sidebar User block.

**Important constraint:** They must remain attributes on `ControlPanelWidget` because callers reference `control_panel.edit_user_name` in multiple places ([main_window.py:699, 871, 925, 899, 1166](src/ui/views/main_window.py#L699)).

**Solution:** Keep construction in ControlPanelWidget, but move the QGroupBox from the panel's layout to the left sidebar layout from MainWindow. Use a `take_user_box()` accessor to transfer the groupbox, or expose the line-edits as forwarding attributes after MainWindow builds the left sidebar.

**Add:**
- `self.chk_save_log = QCheckBox("Save as log")`, `setChecked(True)`, inserted between `btn_stop` and `user_box` (or right after `btn_stop`).
- Default visible — `MainWindow._apply_role_permissions` will toggle visibility.

**Summary:**
- Start/Stop buttons stay.
- `chk_save_log` added (new).
- User box widgets transferred to left sidebar (moved, not deleted).
- Unit & Status boxes stay in place.

---

### B.2 `src/ui/views/main_window.py`

#### B.2.1 Restructure left sidebar layout ([main_window.py:479-488](src/ui/views/main_window.py#L479-L488))

Replace the current `sidebar_layout` content with, top to bottom:

1. **New `QGroupBox("User")`** holding the moved `edit_user_name` + `edit_user_level` (preserve `grp_user` object name so existing QSS rules still apply).
2. **Existing `lbl_test_cases` label.**
3. **Existing `test_list`** (stretch=1).
4. **New `QHBoxLayout`** with three `QPushButton`s:
   - `btn_select_all` — "Select All"
   - `btn_clear_all` — "Clear All"
   - `btn_default` — "Default"
   - Compact (`setMinimumHeight(26)`), small font; no icons.

#### B.2.2 Wire the three new left-sidebar buttons

Add three new slots to `MainWindow`:
- `_on_select_all_tests()` → loop `test_list` items, `setCheckState(Qt.CheckState.Checked)`.
- `_on_clear_all_tests()` → loop `test_list` items, `setCheckState(Qt.CheckState.Unchecked)`.
- `_on_restore_default_tests()` → call `_reload_script_into_list()` (rebuilds from active script with all checked, matching the parse-time default).

**Role restriction:** All three should respect operator role — disabled when `_is_operator()` (safer than hiding to keep layout stable). Add to `_apply_role_permissions`.

#### B.2.3 Update proportions ([main_window.py:480-481, 613-614](src/ui/views/main_window.py#L480))

- Raise `left_sidebar` `setMaximumWidth(280)` → **`setMaximumWidth(340)`**; bump `setMinimumWidth(200)` → **`220`**.
- Raise `right_scroll` `setMaximumWidth(360)` → **`setMaximumWidth(420)`**; bump `setMinimumWidth(300)` → **`340`**.
- `main_row` uses `addWidget(v_splitter, stretch=1)` — center already takes the leftover, so widening the rails automatically narrows it. No stretch-factor changes needed.

#### B.2.4 Extend `_apply_role_permissions` ([main_window.py:194-217](src/ui/views/main_window.py#L194-L217))

Append:
- `self.control_panel.chk_save_log.setVisible(self._is_admin())`
- Disable `btn_select_all`, `btn_clear_all`, `btn_default` when `self._is_operator()`

#### B.2.5 Gate PDF archive behind checkbox ([main_window.py:703-718](src/ui/views/main_window.py#L703-L718))

Wrap the `generate_pdf_auto_archive` call in `if self.control_panel.chk_save_log.isChecked():`. The audit-log entry stays unconditional — auditing must not be opt-out.

#### B.2.6 Emit `sequence_finished` signal in `on_tests_finished` ([main_window.py:1136-1167](src/ui/views/main_window.py#L1136-L1167))

- Add class-level `sequence_finished = Signal(bool)` (import from `PySide6.QtCore`).
- After the existing report/audit work and before `self.test_thread = None`, derive `overall_passed` from `meta.get('overall_result')` (string equality with `"PASS"`), emit the signal, and connect once in `_setup_ui` to a new `_show_result_dialog(passed)` slot.

#### B.2.7 Install delegate on results table

After `self.results_table` is built ([main_window.py:510-528](src/ui/views/main_window.py#L510-L528)), call:
```python
self.results_table.setItemDelegate(ResultRowDelegate(self.results_table))
```

Optionally restrict to column 4 via `setItemDelegateForColumn(4, ...)` if you only want the Result cell colored. The mockup colors the **whole row** — use the row-wide delegate variant.

#### B.2.8 Connect sequence_finished signal to dialog

In `_setup_ui`, after creating the main widgets:
```python
self.sequence_finished.connect(self._show_result_dialog)
```

Implement `_show_result_dialog(passed: bool)`:
```python
def _show_result_dialog(self, passed: bool) -> None:
    dialog = TestResultDialog(passed, parent=self)
    dialog.exec()
```

---

### B.3 `src/ui/widgets/result_row_delegate.py` (new file)

Create a new `QStyledItemDelegate` subclass: `ResultRowDelegate`.

**Key methods:**
- `initStyleOption(self, option, index)`:
  - Read `index.sibling(index.row(), 4).data(Qt.DisplayRole)`.
  - If `"PASS"`, set `option.backgroundBrush = QBrush(QColor("#22c55e"))` (or softer tint `#bbf7d0`).
  - If `"FAIL"`, set `option.backgroundBrush = QBrush(QColor("#ef4444"))` (or softer tint `#fecaca`).
  - Else leave default.
  - Set text color for contrast: `option.palette.setColor(QPalette.Text, ...)`.

**Important:** The delegate must call `super().initStyleOption(...)` first, then mutate, so default text/alignment still render.

**Handle loop separators:** `_on_loop_started` spans the row across columns and sets its own bold blue background ([main_window.py:1078-1093](src/ui/views/main_window.py#L1078-L1093)). The delegate must not override that. Detection: set a custom `Qt.UserRole + 1` flag on the separator item in `_on_loop_started` and check it in the delegate; if set, skip styling.

---

### B.4 `src/ui/views/test_result_dialog.py` (new file)

Create a new `QDialog` subclass: `TestResultDialog(passed: bool, parent=None)`.

**Layout:**
- Fixed size (~480x220).
- Single big `QLabel`: text `"PASS"` or `"FAIL"`, font size ~64pt, bold, centered.
- Color via inline stylesheet: `#16a34a` for PASS, `#dc2626` for FAIL.
- Single `QPushButton("Close")` wired to `self.accept()`.

**Behavior:**
- Center on parent in `showEvent`: `self.move(parent.geometry().center() - self.rect().center())`.
- `setModal(True)` so operator must acknowledge before next sequence.

---

### B.5 `src/ui/assets/light_theme.qss` and `dark_theme.qss`

#### B.5.1 Global font bump

In the base `QWidget { ... font-size: 9pt; }` rule, raise to **11pt**. Audit every `font-size:` line in both files (roughly 12 per file):
- `9pt` → `11pt`
- `10pt` → `12pt`
- `11pt` → `12pt`
- **Leave `7pt` ribbon button labels alone** — they're tight against 80px buttons; bumping risks ellipsis.

**Also bump min-heights:**
- QProgressBar `min-height: 14px` → `18px` (was tight at 9pt, even tighter at 11pt).
- Compact form rows `min-height: 20px` → `26px` (line 353 in light_theme.qss).

#### B.5.2 Light theme background

Change:
- `QMainWindow, QDialog { background-color: #f0f4f8; }` ([light_theme.qss:6-8](src/ui/assets/light_theme.qss#L6-L8)) to **`#dde3ea`** or **`#d4d4d4`** (per your preference).
- Update matching scrollbar track background `#f0f4f8` ([qss:374, 379](src/ui/assets/light_theme.qss#L374)) to the new background so scrollbar gutter doesn't look detached.

White panels (`QListWidget`, `QTableWidget`, `QLineEdit`, `QTextEdit` all `#ffffff`) will now pop. No changes needed.

#### B.5.3 Dark theme background

Unchanged.

---

## C. Risks & things worth confirming before coding

1. **"Save as log" semantics** — confirm (a) gate the PDF archive, or (b) new independent behavior.
2. **"Default" button** — confirm it means "all checked, as parsed from current script" vs. some per-script saved subset. Plan assumes the former.
3. **Row-wide vs Result-cell-only coloring** — third image is row-wide; first mockup is cell-only. Plan assumes row-wide.
4. **Loop-separator interaction** — delegate must not override the blue separator styling. Plan handles with `UserRole+1` sentinel.
5. **Operator role and left-sidebar buttons** — operator currently can't toggle items. Plan: disable buttons for operators, matching that intent. Confirm OK?
6. **Font bump on QSpinBox** — already roomy at `min-height: 28px`. But progress bars `min-height: 14px` need to rise to `18px`.
7. **User box transfer** — `take_user_box()` vs property shims. Pick one approach and apply uniformly.

---

## D. Suggested execution order (one PR, ~6 commits)

1. **New file:** `ResultRowDelegate` + install on `results_table`. Verify color on existing PASS/FAIL data without any other changes.
2. **New file:** `TestResultDialog` + `sequence_finished` signal + wiring in `on_tests_finished`. Verify pop-up fires.
3. **ControlPanelWidget:** remove `user_box`, add `chk_save_log`. Add property shims so MainWindow still resolves `edit_user_name` / `edit_user_level`.
4. **MainWindow._setup_ui:** rebuild `left_sidebar` (User box + label + list + 3 buttons). Wire the three button slots. Update `_apply_role_permissions`.
5. **Proportions:** widen left/right rails' min/max widths.
6. **QSS:** font bump + light background change (both themes touched).

Each commit is independently runnable and reviewable — if a commit breaks the UI, the previous step is still a working baseline.

---

## E. Open questions to confirm before implementation

1. **Save-as-log behavior:** gate PDF archive (a) or new independent flag (b)?
2. **Row coloring scope:** full row or Result cell only?
3. **User box transfer method:** `take_user_box()` accessor or property shims?
4. **Default button behavior:** reload all-checked (current plan) or custom per-script subset?
5. **Operator button behavior:** disable (current plan) or hide?

---

*Plan generated: 2026-05-26*
