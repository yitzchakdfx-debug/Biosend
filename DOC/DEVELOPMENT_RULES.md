# DEVELOPMENT RULES - The Guardrails

These are non-negotiable architectural rules. They exist to prevent the
specific failure modes that have historically eroded ATE codebases. A PR
that violates any of these is rejected on sight; if a rule needs to bend,
the rule must be amended in this document **first**, in a separate PR.

---

## Rule 1: No UI in logic

**`logic/` and `drivers/` modules must NEVER import `PySide6.QtWidgets`,
`PySide6.QtGui`, or any other UI module.**

The single sanctioned exception is `PySide6.QtCore` in `logic/test_engine.py`,
which needs `QThread` and `Signal` to participate in the Qt event system.
That exception is the *only* one. New thread primitives or queues should
prefer stdlib (`threading`, `queue`) unless they need to cross into Qt's
signal system.

**Why**: keeps business logic and hardware drivers headlessly testable,
scriptable, and reusable. If `LimitManager` ever needed a `QMessageBox`,
unit tests would require a `QApplication`.

**How to verify**:

```bash
rg "from PySide6\.(QtWidgets|QtGui)" src/logic src/drivers
rg "import PySide6\.(QtWidgets|QtGui)" src/logic src/drivers
```

Both must return zero matches.

---

## Rule 2: Thread safety - no blocking on the GUI thread

**No hardware calls and no `time.sleep` may run on the main UI thread.**
All blocking work goes inside a `QThread` (today: `TestRunnerThread`).

The narrow exception is `QApplication.processEvents()` used to keep the
event loop alive during sub-second synchronous file I/O - see
`ScriptEditorDialog._set_busy`. Even that is borderline; new code should
prefer a worker thread.

**Why**: blocking the GUI thread freezes the entire application - no
repaints, no input, no Stop button. Operators experience this as a crash.

**How to verify**:

```bash
rg "time\.sleep" src/ui
rg "MockHardware|run_test\(" src/ui
```

The first must return zero. The second is allowed only as type imports or
constructor wiring; never a direct call from a slot.

---

## Rule 3: All SQL lives in `DatabaseManager`

**Every SQL statement - DDL, DML, PRAGMA - must be issued from
`src/logic/database_manager.py`.** UI and logic call `DatabaseManager` methods
only.

If you find yourself writing `import sqlite3` outside `database_manager.py`,
stop. Add a method to `DatabaseManager` instead.

**Why**: gives us one place to enforce parameterization, one place to
manage connections and transactions, and one place to migrate when the
schema changes.

**How to verify**:

```bash
rg "import sqlite3" src/
rg "execute\(|executemany\(" src/
```

The only file matching either pattern must be
`src/logic/database_manager.py`.

---

## Rule 4: No inline styling - everything goes in `.qss`

**Python code must not call `widget.setStyleSheet("...string literal...")`.**
All visual styling lives in `src/ui/assets/light_theme.qss` and
`src/ui/assets/dark_theme.qss` and is applied once at the application root.

**Documented exception**: `ControlPanelWidget` currently styles its
pass/fail counter labels inline. This is grandfathered in and **must be
migrated** into the QSS files when the next styling change touches that
widget. Do not add new inline-style sites under this exception.

**Why**: theme switching is a one-line operation today (replace the
stylesheet). Inline styles silently override the active theme and produce
the exact "dark vertical header in light mode" class of bug we have already
fixed once.

**How to verify**:

```bash
rg "setStyleSheet\(" src/
```

All matches must either (a) load a `.qss` file via `read_text`, or
(b) be the documented `ControlPanelWidget` exception.

---

## Rule 5: Relational integrity - new tests are rows, not columns

**A new test name is a new row in `test_runs`/`test_results`. It must never
require a new column.**

The schema is intentionally tall and narrow: each measurement is one row in
`test_results` keyed to its parent run. This means adding a test is a JSON
edit (`limits.json`) plus, eventually, a `.tst` script row - **zero schema
changes**, zero migrations, no deployment risk.

If a feature seems to require per-test columns (for example, "store the
oscilloscope screenshot path for the RIPPLE test"), generalize it: add a
nullable column once that applies to all rows, or add a child table. Do not
add `value_voltage`, `value_ripple`, etc.

**Why**: hardcoding test names into columns is the single worst long-term
mistake an ATE database can make. It couples the schema to the product line
and turns every new test into a migration.

**How to verify**:

The schema in `database_manager.py` must continue to contain only the
columns documented in `ARCHITECTURE_DEEP_DIVE.md` Section 2.3. Any
`ALTER TABLE` or new `CREATE TABLE` requires both a documented migration
strategy and an update to that section.

---

## Maintenance rule

**Every code change must update the relevant `DOC/` files in the same
commit.** Touching `src/` without touching `DOC/` requires a written
justification in the PR description (typo fixes, one-line bug fixes that
do not change behavior, formatting changes). Anything else is drift, and
drift is the failure mode this document exists to prevent.

When adding or changing a script keyword or hardware command, also update
[KEYWORDS_DICTIONARY.md](KEYWORDS_DICTIONARY.md) - it is the user-facing
reference for the `.tst` language and a contract with whoever writes test
scripts.
