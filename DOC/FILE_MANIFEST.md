# FILE_MANIFEST - The Project Map

Authoritative inventory of every source artifact in the DFX_ate project. Update
this table whenever a file is added, renamed, removed, or has its responsibility
materially changed.

| File Path                              | Module        | Short Description                                                                                       |
| -------------------------------------- | ------------- | ------------------------------------------------------------------------------------------------------- |
| `src/main.py`                          | entry         | Application entry point; constructs `QApplication`, runs `LoginDialog`, then opens `MainWindow`.        |
| `src/ui/__init__.py`                   | ui            | Marks the Qt UI layer package.                                                                          |
| `src/ui/views/__init__.py`             | ui.views      | Marks the views (top-level dialogs and the main window) package.                                        |
| `src/ui/views/main_window.py`          | ui.views      | `MainWindow` (`QMainWindow`); ribbon (Toggle Theme / Load Script / Edit Test File), role-aware gating (Operator/Engineer/Admin), metadata-driven part-number autofill from script header, export controls, prompt dialog handler that releases the runner via `resume()`, and wiring to `TestRunnerThread`. |
| `src/ui/views/login_dialog.py`         | ui.views      | `LoginDialog`; authenticates via `AuthManager`, blocks invalid login, and forces password change when required. |
| `src/ui/views/change_password_dialog.py` | ui.views    | `ChangePasswordDialog`; mandatory post-login password update flow when `must_change_pwd=1`.             |
| `src/ui/views/user_management_dialog.py` | ui.views    | `UserManagementDialog`; Admin-only CRUD/reset operations for local users and roles.                     |
| `src/ui/views/script_editor.py`        | ui.views      | `ScriptEditorDialog`; `QPlainTextEdit`-based editor for `.tst` files, delegates I/O to `ScriptManager`. |
| `src/ui/widgets/__init__.py`           | ui.widgets    | Marks the reusable widgets package.                                                                     |
| `src/ui/widgets/control_panel.py`      | ui.widgets    | `ControlPanelWidget`; right-hand control rail (start/stop, user, unit, status, progress, counters).     |
| `src/ui/assets/light_theme.qss`        | ui.assets     | Light QSS theme (palette + headers + scrollbars + plain-text editor).                                   |
| `src/ui/assets/dark_theme.qss`         | ui.assets     | Dark QSS theme (palette + headers + plain-text editor).                                                 |
| `src/ui/assets/style.qss`              | ui.assets     | Legacy stylesheet retained for reference; not loaded by the running app.                                |
| `src/logic/__init__.py`                | logic         | Marks the test sequencing and domain-model package.                                                     |
| `src/logic/models.py`                  | logic         | Domain types: `TestLimit` (legacy), `TestStep` (parsed script step, includes `retry_count`), `TestResultPayload` `TypedDict` (includes `is_measurement`), `TestRunRecord`. |
| `src/logic/test_engine.py`             | logic         | `TestRunnerThread(QThread)`; **script-driven**. Loads via `ScriptManager`, dispatches commands through `MockHardware.execute_command`, intercepts `Delay` via `msleep`, intercepts `Log` (-> `script_log` signal) and `Prompt` (parks on `threading.Event` until `resume()`), runs each step inside a `Retry` loop that reports only the final attempt, aborts on `Critical` failures. |
| `src/logic/limit_manager.py`           | logic         | `LimitManager`; **legacy**. Superseded by inline `Limits` keyword in `.tst` scripts; kept on disk for reference / external tooling but no longer wired into the runtime. |
| `src/logic/database_manager.py`        | logic         | `DatabaseManager`; SQLite schema bootstrap and parameterized inserts for `test_runs` / `test_results` plus RBAC user storage and password lifecycle operations. |
| `src/logic/script_manager.py`          | logic         | `ScriptManager`; discovery, raw read/write, and parsing of `.tst` files into `ScriptDocument` (`metadata` + `steps`). Recognizes `PartNum:` header metadata plus `Critical`, `Limits`, `Tolerance` (`Target ... Tol ...`), `Unit`, and `Retry`; defines `ScriptParseError` for line-precise diagnostics. |
| `src/logic/auth_manager.py`            | logic         | `AuthManager`; DB-backed authentication facade with password-strength validation and password-change support. |
| `src/logic/file_lock.py`               | logic         | `SingleInstanceLock`; PID-file guard preventing concurrent app instances from mutating local state.      |
| `src/drivers/__init__.py`              | drivers       | Marks the hardware-abstraction package.                                                                 |
| `src/drivers/base_driver.py`           | drivers       | `BaseDriver` abstract interface. **STALE** - imports `TestOutcome`/`TestConfig` from `logic.models`, which do not currently exist; not implemented by `MockHardware`. Slated for refactor. |
| `src/drivers/mock_hardware.py`         | drivers       | `MockHardware`; Qt-free simulator. Generic `execute_command(name, args) -> float` dispatch supporting `readchannel`, `setvoltage`, `relay`, `getid`. Exposes `MEASUREMENT_COMMANDS`. |
| `src/data/limits.json`                 | data (config) | **Legacy** - JSON spec limits superseded by inline `Limits` in `.tst` files. Retained on disk; no longer loaded at runtime. |
| `src/data/database.db`                 | data (state)  | SQLite database holding historical `test_runs` and `test_results`. Created on first run.                |
| `src/data/sequence.tst`                | data (config) | Default test-sequence script loaded on launch when no other script has been picked via "Load Script".   |
| `src/data/demo_system.tst`             | data (config) | Comprehensive demo script exercising every supported keyword (`Critical`, `Limits`, `Unit`) and command (`setvoltage`, `readchannel`, `relay`, `getid`, `Delay`). |
| `requirements.txt`                     | tooling       | Runtime dependency pin: `PySide6>=6.6.0`.                                                               |
| `.pylintrc`                            | tooling       | Pylint config; whitelists PySide6 C-extensions to silence `no-name-in-module`.                          |
| `DOC/FILE_MANIFEST.md`                 | docs          | This file.                                                                                              |
| `DOC/ARCHITECTURE_DEEP_DIVE.md`        | docs          | Threading model, hybrid data strategy, UI composition, signal map, ER diagram, maintenance protocol.    |
| `DOC/SPECIFICATIONS.md`                | docs          | Pinned environment: Python, GUI, storage, OS target, deployment tooling.                                |
| `DOC/TECH_STACK.md`                    | docs          | Required engineering competencies and paradigms.                                                        |
| `DOC/DEVELOPMENT_RULES.md`             | docs          | Non-negotiable architectural guardrails with verification hints.                                        |
| `DOC/KEYWORDS_DICTIONARY.md`           | docs          | Reference for every keyword (`:`, `Critical`, `Limits`, `Unit`) and command (`Delay`, `setvoltage`, `relay`, `getid`, `readchannel`) supported by the `.tst` script language. |
| `README.md`                            | docs          | Top-level project pointer; delegates to `DOC/` for everything authoritative.                            |

## Known stale artifacts

- `src/drivers/base_driver.py` references `TestOutcome` and `TestConfig` from
  `logic.models`, but neither symbol is defined there. The current runtime path
  uses `MockHardware` directly (no `BaseDriver` subclassing). This file should
  either be re-aligned with the real driver contract or removed; flagged here
  so future maintainers do not assume it is wired in.
