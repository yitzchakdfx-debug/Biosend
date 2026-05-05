# KEYWORDS DICTIONARY - The `.tst` Script Vocabulary

The complete reference for the script language consumed by
[`ScriptManager.load_script`](../src/logic/script_manager.py) and executed by
[`TestRunnerThread`](../src/logic/test_engine.py).

## General syntax rules

- One statement per line. Trailing whitespace is ignored.
- Comments start with `#` and run to end of line. Inline comments are allowed.
- Blank lines and lines before the first `:` header are ignored (file preamble).
- **Keyword names are case-insensitive** (`Critical` == `CRITICAL` == `critical`).
- Test names (everything after the `:`), unit strings, and command arguments
  preserve their original case.
- `Limits` and `Tolerance` (`Target ... Tol ...`) are **mutually exclusive** within
  a single step.

## Header keywords (script preamble)

Header keywords are parsed before the first `:<Test Name>` block and are used as
metadata that can drive the UI.

| Keyword | Syntax | Description |
| --- | --- | --- |
| `PartNum` | `PartNum: <value>` (or `# PartNum: <value>`) | Sets the default part number for the loaded script. The UI auto-populates the part-number field if the operator has not manually edited it. |

## Core Structural Keywords

| Keyword     | Syntax                       | Description                                                                                                  |
| ----------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `:`         | `:<Name>`                    | **Test Header**: Starts a new test block.                                                                    |
| `Critical`  | `Critical`                   | **Abort on Fail**: Stops the entire sequence if this step fails.                                             |
| `Limits`    | `Limits <min> <max>`         | **Fixed Range**: Sets the PASS/FAIL boundaries.                                                              |
| `Tolerance` | `Target <val> Tol <%>`       | **Dynamic Range**: Calculates limits from a target and a percentage (e.g. `Target 5.0 Tol 10`).             |
| `Unit`      | `Unit <str>`                 | **Units**: Sets the unit string for reporting (`V`, `A`, etc.).                                              |
| `Delay`     | `Delay <ms>`                 | **Wait**: Pauses execution for X milliseconds.                                                               |
| `Retry`     | `Retry <num>`                | **Auto-Repeat**: Re-runs the step up to X times if it fails before declaring a final FAIL.                   |
| `Prompt`    | `Prompt <msg>`               | **User Action**: Pauses and shows a popup message. Waits for user "OK" to continue.                          |
| `Log`       | `Log <msg>`                  | **Trace Note**: Prints a custom message directly to the Hardware Trace log.                                  |

`Critical`, `Limits`, `Tolerance`, `Unit`, and `Retry` are step-level
configuration: they apply to the most recent `:` header. `Delay`, `Prompt`,
and `Log` are *per-line commands* and may appear anywhere inside a step, in
sequence with hardware commands.

## Hardware commands (mock backend)

The set of hardware commands recognized by `MockHardware.execute_command`:

| Command       | Kind          | Syntax                       | Notes                                                                                          |
| ------------- | ------------- | ---------------------------- | ---------------------------------------------------------------------------------------------- |
| `setvoltage`  | side-effect   | `setvoltage <volts>`         | Sets a rail to the requested voltage. Returns no measurement.                                  |
| `relay`       | side-effect   | `relay <id> <on\|off>`       | Switches a relay. Returns no measurement.                                                      |
| `getid`       | side-effect   | `getid`                      | Mock identification ping. Returns no measurement.                                              |
| `readchannel` | measurement   | `readchannel <channel>`      | Reads channel `<channel>`. The **last** measurement value executed in a step is what gets compared against `Limits` / `Tolerance`. |

The set of measurement commands is defined in
`MockHardware.MEASUREMENT_COMMANDS` and currently contains only
`readchannel`. Adding a new measurement command means appending it to that
frozenset, implementing it in `MockHardware.execute_command`, and adding a
row here.

Any unknown command name raises `ValueError("Unknown hardware command: ...")`
inside the runner; the step is marked FAIL and the trace shows the offending
command.

## Worked example

```text
# Power-up a UUT, prompt the operator, take a tolerance-checked measurement,
# and retry it once if the supply has not settled.

:Power Supply Init
Critical
setvoltage 5.0
Delay 200

:Operator Confirm
Prompt Insert UUT and click OK to continue
Log Operator confirmed UUT insertion

:5V Output Voltage
Target 5.0 Tol 5
Unit V
Retry 1
readchannel 0

:Cleanup
setvoltage 0.0
```

Behavior:

1. `Power Supply Init` is critical: any failure aborts the run.
2. `Operator Confirm` parks the runner on `Prompt`; the GUI shows a
   `QMessageBox` and the runner only continues after the operator clicks
   OK. The `Log` line then appears in the Hardware Trace in a distinct
   style.
3. `5V Output Voltage` derives its limits from `Target 5.0 Tol 5` (i.e.
   min 4.75, max 5.25). If `readchannel 0` returns out-of-range, the
   runner re-runs the step once before declaring a final FAIL.
4. `Cleanup` runs unconditionally as a non-measured pass row.

## Validation summary

The parser raises a `ScriptParseError(line_no, line, msg)` for any of:

- A `:` header with an empty name.
- A keyword (`Critical`, `Limits`, `Tolerance`, `Unit`, `Retry`) appearing
  before any `:` header.
- A command appearing before any `:` header.
- `Critical` with extra arguments.
- `Limits` without exactly two numeric arguments, or with `min > max`.
- `Target ... Tol ...` with the wrong shape, with non-numeric `<val>` /
  `<pct>`, with `<pct>` negative, or when the step already has `Limits`.
- `Limits` when the step already has `Target/Tol`.
- `Unit` without a unit string.
- `Retry` without exactly one non-negative integer argument.

`TestRunnerThread` catches `ScriptParseError` and emits the error to the
trace log; it does not throw out of the QThread.
