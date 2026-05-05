<<<<<<< HEAD
# DFX_ate

A Windows desktop ATE (Automated Test Equipment) controller built on PySide6.
It runs a configurable test sequence against (mock) hardware off the GUI
thread, validates each measurement against JSON-defined limits, and persists
every run to a SQLite history database.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python src/main.py
```

Default login: `admin` / `admin` (Engineer role). Any other credentials
log in as a guest Technician.

## Documentation - read before contributing

All architecture, specifications, and rules live in [`DOC/`](DOC/). It is
the single source of truth for this project and is **kept in sync with the
code on every commit**.

- [`DOC/FILE_MANIFEST.md`](DOC/FILE_MANIFEST.md) - the project map; every file and its responsibility.
- [`DOC/ARCHITECTURE_DEEP_DIVE.md`](DOC/ARCHITECTURE_DEEP_DIVE.md) - threading model, hybrid data strategy, UI composition, signal/slot map, ER diagram.
- [`DOC/SPECIFICATIONS.md`](DOC/SPECIFICATIONS.md) - pinned Python/Qt/OS/storage versions and deployment plan.
- [`DOC/TECH_STACK.md`](DOC/TECH_STACK.md) - the engineering competencies expected of contributors.
- [`DOC/DEVELOPMENT_RULES.md`](DOC/DEVELOPMENT_RULES.md) - the five non-negotiable architectural guardrails.
- [`DOC/KEYWORDS_DICTIONARY.md`](DOC/KEYWORDS_DICTIONARY.md) - the `.tst` script vocabulary (keywords and commands).

If a `src/` change is not accompanied by a `DOC/` update in the same
commit, it requires a written justification in the PR description.
=======
# DFX_ate
>>>>>>> b34894bd7bea641d29894338c10760684354d4e1
