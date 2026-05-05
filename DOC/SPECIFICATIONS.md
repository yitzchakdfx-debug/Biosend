# SPECIFICATIONS - Environment & Versions

The pinned operating envelope for DFX_ate. Anything outside these bounds is
unsupported until this document is updated.

## Runtime

| Concern        | Specification                                              | Notes                                                              |
| -------------- | ---------------------------------------------------------- | ------------------------------------------------------------------ |
| Python         | **3.12 or newer**                                          | Uses PEP 604 union syntax (`X \| None`), `slots=True` dataclasses. |
| GUI framework  | **PySide6 >= 6.6.0**                                       | See `requirements.txt`. Qt6, LGPL.                                 |
| Database       | **SQLite 3** (Python stdlib `sqlite3`)                     | File: `src/data/database.db`. `PRAGMA foreign_keys = ON;`.         |
| Configuration  | **JSON** (Python stdlib `json`)                            | File: `src/data/limits.json`.                                      |
| Test scripts   | **Plain text** (`.tst` suffix)                             | UTF-8; raw text today, structured grammar planned.                 |
| Filesystem API | **`pathlib.Path`** for all I/O                             | No `os.path` joins, no string concatenation for paths.             |

## OS target

| Concern         | Specification                                            |
| --------------- | -------------------------------------------------------- |
| Primary OS      | **Windows 10** and **Windows 11**, desktop only.         |
| Display         | 1280 x 800 minimum; the main window opens at 1200 x 800. |
| Filesystem      | NTFS (path separators handled by `pathlib`).             |
| Other OSes      | Not supported. The code is largely portable but neither tested nor packaged for Linux or macOS. |

## Dependencies

The full runtime dependency surface lives in `requirements.txt`:

```text
PySide6>=6.6.0
```

Everything else (`sqlite3`, `json`, `pathlib`, `dataclasses`, `typing`,
`abc`, `random`, `time`, `datetime`) is Python standard library. There is
no third-party ORM, no test framework, and no build system - by design.
Adding any new runtime dependency requires:

1. an entry in `requirements.txt` with a `>=` lower bound,
2. a justification in the PR description,
3. an update to this document.

## Tooling (development time)

| Tool   | Purpose                                              | Config              |
| ------ | ---------------------------------------------------- | ------------------- |
| pylint | Static analysis                                      | `.pylintrc`         |
| venv   | Isolated interpreter (`.venv/` at the project root)  | not in version control |

## Deployment (planned)

DFX_ate is built so it can be shipped as a single Windows executable to
ATE stations that do not have a Python runtime. The intended toolchain:

- **PyInstaller** - one-file `.exe` build of `src/main.py`. The data folder
  (`src/data/`) and assets (`src/ui/assets/*.qss`) must be bundled with
  `--add-data`, and the runtime must resolve them via `Path(__file__)`-relative
  lookups (already the case in every manager).
- **PyArmor** - source-level obfuscation prior to PyInstaller, applied to
  `src/logic/` and `src/drivers/` at minimum. UI code may also be obfuscated
  but the QSS files remain plain text (they are read at runtime).

Neither tool is wired into the repo yet. When a build script is added, list
it in `FILE_MANIFEST.md` and document the invocation in this section.
