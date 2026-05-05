"""Background test sequencer (QThread).

Loads a `.tst` script via `ScriptManager`, walks each `TestStep`, dispatches
hardware commands through `MockHardware.execute_command`, applies inline
limits, retries failing steps as configured, and aborts the run when a
`Critical` step fails. `Prompt` parks the runner on a `threading.Event`
that the UI releases via `resume()`. UI-free except for Qt threading
primitives and the standard-library `Event`.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Event

from PySide6.QtCore import QThread, Signal

from drivers.mock_hardware import MockHardware
from logic.database_manager import DatabaseManager
from logic.models import TestResultPayload, TestRunRecord, TestStep
from logic.script_manager import ScriptManager, ScriptParseError


class TestRunnerThread(QThread):
    """Runs a parsed `.tst` script off the GUI thread; reports via signals."""

    log_msg = Signal(str)
    test_result = Signal(str, dict)
    progress_total = Signal(int)
    progress_test = Signal(int)
    current_test = Signal(str)
    prompt_request = Signal(str)
    script_log = Signal(str)

    def __init__(
        self,
        script_path: Path,
        selected_names: set[str],
        *,
        loop_count: int = 1,
        stop_on_fail: bool = False,
        operator: str = "",
        part_number: str = "",
        serial_number: str = "",
        script_manager: ScriptManager | None = None,
    ) -> None:
        super().__init__()
        self._script_path = Path(script_path)
        self._selected_names = set(selected_names)
        self._loop_count = max(1, loop_count)
        self._stop_on_fail = stop_on_fail
        self._script_manager = script_manager or ScriptManager()
        self._hw = MockHardware()
        self._stop_requested = False
        self._prompt_event: Event = Event()
        self._db = DatabaseManager()
        self._run_record = TestRunRecord(
            operator=operator,
            part_number=part_number,
            serial_number=serial_number,
            overall_passed=True,
        )

    def run(self) -> None:
        self.progress_total.emit(0)
        self.progress_test.emit(0)
        self.current_test.emit("")

        overall_passed = True

        try:
            try:
                all_steps = self._script_manager.load_script(self._script_path)
            except ScriptParseError as exc:
                self.log_msg.emit(
                    f"Script load failed at line {exc.line_no}: {exc.msg}"
                )
                overall_passed = False
                return
            except (OSError, ValueError) as exc:
                self.log_msg.emit(f"Script load failed: {exc}")
                overall_passed = False
                return

            steps = [s for s in all_steps if s.name in self._selected_names]
            if not steps:
                self.log_msg.emit("No steps selected to run.")
                return

            total_steps = len(steps) * self._loop_count
            completed = 0
            abort_all_loops = False

            for _loop in range(self._loop_count):
                if self._stop_requested:
                    self.log_msg.emit("Test execution aborted by user.")
                    break

                for step in steps:
                    if self._stop_requested:
                        self.log_msg.emit("Test execution aborted by user.")
                        abort_all_loops = True
                        break

                    self.current_test.emit(step.name)
                    self.progress_test.emit(0)
                    self.log_msg.emit(f"Executing: {step.name}...")

                    attempts_total = step.retry_count + 1
                    passed = False
                    value: float | None = None
                    for attempt in range(1, attempts_total + 1):
                        if self._stop_requested:
                            break
                        passed, value = self._run_step(step)
                        if passed or attempt == attempts_total:
                            break
                        self.log_msg.emit(
                            f"{step.name}: attempt {attempt}/{attempts_total} "
                            "failed, retrying..."
                        )

                    if not passed:
                        overall_passed = False

                    payload: TestResultPayload = {
                        "value": value if value is not None else 0.0,
                        "min": step.min_val if step.min_val is not None else 0.0,
                        "max": step.max_val if step.max_val is not None else 0.0,
                        "unit": step.unit,
                        "passed": passed,
                        "is_measurement": step.has_limits and value is not None,
                    }
                    self.test_result.emit(step.name, dict(payload))
                    self._run_record.results.append(
                        {"test_name": step.name, **dict(payload)}
                    )

                    self.progress_test.emit(100)
                    completed += 1
                    self.progress_total.emit(
                        min(100, int((completed / total_steps) * 100))
                    )

                    if step.is_critical and not passed:
                        self.log_msg.emit(
                            f"CRITICAL ABORT: {step.name} failed; halting sequence."
                        )
                        abort_all_loops = True
                        break

                    if self._stop_on_fail and not passed:
                        self.log_msg.emit(
                            f"Stop on fail: {step.name} failed; aborting remaining tests."
                        )
                        abort_all_loops = True
                        break

                if abort_all_loops:
                    break

        finally:
            self._run_record.end_time = datetime.now()
            self._run_record.overall_passed = overall_passed
            try:
                self._db.save_run(self._run_record)
            except Exception as exc:
                self.log_msg.emit(f"ERROR: failed to save run to database: {exc!s}")
            self.current_test.emit("")
            self.progress_test.emit(0)
            self.finished.emit()

    def _run_step(self, step: TestStep) -> tuple[bool, float | None]:
        """Execute every command in `step`; return (passed, last_measurement)."""
        last_measurement: float | None = None
        n = max(1, len(step.commands))

        for idx, cmd in enumerate(step.commands, start=1):
            if self._stop_requested:
                return False, last_measurement
            try:
                result = self._execute_command(cmd)
                if result is not None:
                    last_measurement = result
            except Exception as exc:
                self.log_msg.emit(
                    f"ERROR in {step.name}: command {cmd['cmd']!r} raised: {exc!s}"
                )
                return False, last_measurement

            self.progress_test.emit(min(99, int((idx / n) * 100)))

        if step.has_limits:
            if last_measurement is None:
                self.log_msg.emit(
                    f"{step.name}: validation error - Limits set but no "
                    "measurement command executed; marking FAIL."
                )
                return False, None
            assert step.min_val is not None and step.max_val is not None
            in_spec = step.min_val <= last_measurement <= step.max_val
            return in_spec, last_measurement

        return True, last_measurement

    def _execute_command(self, cmd: dict) -> float | None:
        """Dispatch one command.

        Intercepts the runner-side commands `Delay`, `Log`, and `Prompt`
        before falling through to the hardware driver.
        """
        name = str(cmd["cmd"]).lower()
        args = cmd["args"]

        if name == "delay":
            if not args:
                raise ValueError("'Delay' requires a millisecond argument")
            self.msleep(int(float(args[0])))
            return None

        if name == "log":
            self.script_log.emit(" ".join(args))
            return None

        if name == "prompt":
            self._prompt_event.clear()
            self.prompt_request.emit(" ".join(args))
            self._prompt_event.wait()
            return None

        value = self._hw.execute_command(name, args)
        return value if name in MockHardware.MEASUREMENT_COMMANDS else None

    def resume(self) -> None:
        """Unblock a thread parked on a `Prompt` (called by the UI thread)."""
        self._prompt_event.set()

    def stop(self) -> None:
        self._stop_requested = True
        self._prompt_event.set()
