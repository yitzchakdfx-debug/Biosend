"""Background batch-aware test sequencer (QThread)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Any

from PySide6.QtCore import QThread, Signal

from config import (
    INPUT_CONNECTED_TARGET_V,
    INPUT_CONNECTED_TOLERANCE_PCT,
    LOAD_RESISTANCE_50W_OHM,
    LOAD_RESISTANCE_300W_OHM,
    LOAD_SERIALS,
)
from drivers.base_driver import BaseDriver, HardwareError
from drivers.mock_hardware import MockHardware
from logic.database_manager import DatabaseManager
from logic.models import BatchUnit, BatchUnitReport, TestResultPayload, TestRunRecord, TestStep
from logic.script_manager import ScriptManager, ScriptParseError
from logic.secure_logger import get_secure_logger


def _as_float(raw: str, fallback: float) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return fallback


class TestRunnerThread(QThread):
    """Runs one script across one or more batch units, sequentially."""

    log_msg = Signal(str)
    test_result = Signal(str, dict)
    progress_total = Signal(int)
    progress_test = Signal(int)
    current_test = Signal(str)
    prompt_request = Signal(str)
    script_log = Signal(str)
    loop_started = Signal(int, int)
    current_unit_changed = Signal(str, int, int, str)
    unit_finished = Signal(dict)
    unit_alert = Signal(str)

    def __init__(
        self,
        script_path: Path,
        selected_names: set[str],
        *,
        loop_count: int = 1,
        stop_on_fail: bool = False,
        operator: str = "",
        tester_name: str = "",
        employee_id: str = "",
        uut_type: str = "",
        part_number: str = "",
        serial_number: str = "",
        batch_units: list[BatchUnit] | None = None,
        script_manager: ScriptManager | None = None,
        start_time: datetime | None = None,
        logical_script_name: str = "",
        driver: BaseDriver | None = None,
    ) -> None:
        super().__init__()
        self._script_path = Path(script_path)
        self._logical_script_name = logical_script_name.strip() or self._script_path.stem
        self._selected_names = set(selected_names)
        self._loop_count = max(1, loop_count)
        self._stop_on_fail = stop_on_fail
        self._script_manager = script_manager or ScriptManager()
        self._hw: BaseDriver = driver or MockHardware()
        self._stop_requested = False
        self._prompt_event: Event = Event()
        self._pause_event: Event = Event()
        self._pause_event.set()
        self._db = DatabaseManager()
        try:
            self._secure_log = get_secure_logger()
        except Exception:
            self._secure_log = None
        self.tester_name = tester_name.strip() or operator.strip()
        self.employee_id = employee_id.strip()
        self.uut_type = uut_type.strip()
        self._part_number = part_number.strip()
        self._operator = operator.strip() or self.tester_name
        self._start_dt = start_time or datetime.now()
        self._connected_target_v = _as_float(INPUT_CONNECTED_TARGET_V, 24.0)
        self._connected_tol_pct = _as_float(INPUT_CONNECTED_TOLERANCE_PCT, 5.0)
        self._load_res_50w = _as_float(LOAD_RESISTANCE_50W_OHM, 12.5)
        self._load_res_300w = _as_float(LOAD_RESISTANCE_300W_OHM, 2.2)
        self._reports: list[BatchUnitReport] = []
        self._current_unit: BatchUnit | None = None
        if batch_units:
            self._batch_units = list(batch_units)
        else:
            load_serial = LOAD_SERIALS[0] if LOAD_SERIALS else "PRODIGIT-CH1"
            self._batch_units = [
                BatchUnit(
                    serial_number=serial_number.strip(),
                    slot_index=1,
                    position_label="Position 1",
                    load_channel="CH1",
                    load_serial_number=load_serial,
                )
            ]

    def _emit_log(self, category: str, msg: str) -> None:
        self.log_msg.emit(msg)
        if self._secure_log is not None:
            try:
                self._secure_log.log(
                    "trace",
                    {
                        "category": category,
                        "message": msg,
                        "script": self._logical_script_name,
                        "serial_number": self._current_unit.serial_number if self._current_unit else "",
                    },
                )
            except Exception:
                pass

    def run(self) -> None:
        self.progress_total.emit(0)
        self.progress_test.emit(0)
        self.current_test.emit("")

        try:
            try:
                if not self._hw.connect():
                    self._emit_log("error", "Hardware connect() returned False; aborting.")
                    return
            except HardwareError as exc:
                self._emit_log("error", f"Hardware connection failed: {exc}")
                return

            try:
                all_steps = self._script_manager.load_script(self._script_path)
            except ScriptParseError as exc:
                self._emit_log("error", f"Script load failed at line {exc.line_no}: {exc.msg}")
                return
            except (OSError, ValueError) as exc:
                self._emit_log("error", f"Script load failed: {exc}")
                return

            steps = [s for s in all_steps if s.name in self._selected_names]
            if not steps:
                self._emit_log("info", "No steps selected to run.")
                return

            total_units = len(self._batch_units)
            per_unit_steps = max(1, len(steps) * self._loop_count + 2)
            completed_steps = 0

            for unit_index, unit in enumerate(self._batch_units, start=1):
                if self._stop_requested:
                    self._emit_log("info", "Test execution aborted by user.")
                    break
                self._current_unit = unit
                self.current_unit_changed.emit(
                    unit.serial_number,
                    unit_index,
                    total_units,
                    unit.position_label,
                )
                self._emit_log(
                    "info",
                    f"=== Unit {unit_index}/{total_units}: {unit.serial_number} @ {unit.position_label} ===",
                )
                report = self._run_single_unit(unit, unit_index, total_units, steps)
                self._reports.append(report)
                completed_steps += per_unit_steps
                self.progress_total.emit(min(100, int((completed_steps / (per_unit_steps * total_units)) * 100)))
                self.unit_finished.emit(
                    {
                        "serial_number": unit.serial_number,
                        "slot_index": unit.slot_index,
                        "position_label": unit.position_label,
                        "passed": report.overall_result == "PASS",
                        "report_generated": report.should_generate_report,
                    }
                )
        finally:
            try:
                self._hw.disconnect()
            except Exception:
                pass
            self.current_test.emit("")
            self.progress_test.emit(0)
            self._pause_event.set()
            self.finished.emit()

    def _new_record(self, unit: BatchUnit, batch_index: int) -> TestRunRecord:
        return TestRunRecord(
            operator=self._operator,
            part_number=self._part_number,
            serial_number=unit.serial_number,
            overall_passed=True,
            batch_label=self._logical_script_name,
            batch_index=batch_index,
            slot_index=unit.slot_index,
            position_label=unit.position_label,
            load_channel=unit.load_channel,
            load_serial_number=unit.load_serial_number,
            start_time=datetime.now(),
        )

    def _run_single_unit(
        self,
        unit: BatchUnit,
        unit_index: int,
        total_units: int,
        steps: list[TestStep],
    ) -> BatchUnitReport:
        record = self._new_record(unit, unit_index)
        try:
            self._hw.activate_slot(unit.slot_index, load_serial_number=unit.load_serial_number)
        except Exception as exc:
            self._emit_log("error", f"{unit.serial_number}: failed to activate {unit.position_label}: {exc}")
            record.overall_passed = False
            record.end_time = datetime.now()
            record.results.append(self._result_row("Slot Activation", False, 0.0, 0.0, 0.0, ""))
            self._save_record(record)
            return BatchUnitReport(
                unit=unit,
                record=record,
                tester_name=self.tester_name,
                employee_id=self.employee_id,
                uut_type=self.uut_type,
                test_program_name=self._logical_script_name,
                overall_result="FAIL",
            )

        if not self._check_input_connection(record, unit):
            record.end_time = datetime.now()
            self._save_record(record)
            return BatchUnitReport(
                unit=unit,
                record=record,
                tester_name=self.tester_name,
                employee_id=self.employee_id,
                uut_type=self.uut_type,
                test_program_name=self._logical_script_name,
                overall_result="FAIL",
            )

        polarity_ok = self._check_polarity(record, unit)
        if not polarity_ok:
            record.end_time = datetime.now()
            self._save_record(record)
            msg = (
                f"Polarity check failed for {unit.serial_number} at {unit.position_label}. "
                "Skipping report for this unit."
            )
            self.unit_alert.emit(msg)
            return BatchUnitReport(
                unit=unit,
                record=record,
                tester_name=self.tester_name,
                employee_id=self.employee_id,
                uut_type=self.uut_type,
                test_program_name=self._logical_script_name,
                overall_result="FAIL",
                alert_message=msg,
                should_generate_report=False,
            )

        total_steps = len(steps) * self._loop_count
        completed = 0
        abort_loops = False
        overall_passed = True

        for loop_idx in range(self._loop_count):
            if self._stop_requested:
                self._emit_log("info", "Test execution aborted by user.")
                break
            loop_number = loop_idx + 1
            if self._loop_count > 1:
                self.loop_started.emit(loop_number, self._loop_count)
                self._emit_log("info", f"--- Loop {loop_number}/{self._loop_count} ---")

            for step in steps:
                self._pause_event.wait()
                if self._stop_requested:
                    abort_loops = True
                    break

                self.current_test.emit(step.name)
                self.progress_test.emit(0)
                self._configure_load_for_step(step)
                self._emit_log("cmd", f"Executing: {step.name}... [Unit: {unit.serial_number}]")

                attempts_total = step.retry_count + 1
                passed = False
                value: float | None = None
                for attempt in range(1, attempts_total + 1):
                    if self._stop_requested:
                        break
                    passed, value = self._run_step(step)
                    if passed or attempt == attempts_total:
                        break
                    self._emit_log(
                        "info",
                        f"{step.name}: attempt {attempt}/{attempts_total} failed, retrying...",
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
                self._emit_result(unit, step.name, payload)
                record.results.append({"test_name": step.name, "loop": loop_number, **dict(payload)})

                self.progress_test.emit(100)
                completed += 1
                step_progress = int((completed / max(1, total_steps)) * 100)
                self.progress_total.emit(
                    int((((unit_index - 1) + (step_progress / 100.0)) / max(1, total_units)) * 100)
                )

                if step.is_critical and not passed:
                    self._emit_log("error", f"CRITICAL ABORT: {step.name} failed for {unit.serial_number}.")
                    abort_loops = True
                    break

                if self._stop_on_fail and not passed:
                    self._emit_log("info", f"Stop on fail: {step.name} failed for {unit.serial_number}.")
                    abort_loops = True
                    break

            if abort_loops:
                break

        record.overall_passed = overall_passed and not self._stop_requested
        record.end_time = datetime.now()
        self._save_record(record)
        return BatchUnitReport(
            unit=unit,
            record=record,
            tester_name=self.tester_name,
            employee_id=self.employee_id,
            uut_type=self.uut_type,
            test_program_name=self._logical_script_name,
            overall_result="PASS" if record.overall_passed else "FAIL",
        )

    def _check_input_connection(self, record: TestRunRecord, unit: BatchUnit) -> bool:
        target = self._connected_target_v
        tol = self._connected_tol_pct
        min_v = target * (1.0 - tol / 100.0)
        max_v = target * (1.0 + tol / 100.0)
        try:
            value = self._hw.execute_command("readinput", [str(unit.slot_index)])
        except Exception as exc:
            self._emit_log("error", f"{unit.serial_number}: input read failed: {exc}")
            value = 0.0
        passed = min_v <= value <= max_v
        payload: TestResultPayload = {
            "value": value,
            "min": min_v,
            "max": max_v,
            "unit": "V",
            "passed": passed,
            "is_measurement": True,
        }
        self._emit_result(unit, "Input Connection Check", payload)
        record.results.append({"test_name": "Input Connection Check", "loop": 1, **dict(payload)})
        if not passed:
            self._emit_log(
                "error",
                f"{unit.serial_number}: input voltage {value:g} V out of range at {unit.position_label}.",
            )
            record.overall_passed = False
        return passed

    def _check_polarity(self, record: TestRunRecord, unit: BatchUnit) -> bool:
        try:
            polarity = self._hw.execute_command("checkpolarity", [str(unit.slot_index)])
        except Exception as exc:
            self._emit_log("error", f"{unit.serial_number}: polarity check failed: {exc}")
            polarity = -1.0
        passed = polarity >= 0
        payload: TestResultPayload = {
            "value": polarity,
            "min": 0.0,
            "max": 1.0,
            "unit": "",
            "passed": passed,
            "is_measurement": False,
        }
        self._emit_result(unit, "Polarity Check", payload)
        record.results.append({"test_name": "Polarity Check", "loop": 1, **dict(payload)})
        if not passed:
            self._emit_log("error", f"{unit.serial_number}: polarity check failed at {unit.position_label}.")
            record.overall_passed = False
        return passed

    @staticmethod
    def _result_row(
        test_name: str,
        passed: bool,
        value: float,
        min_v: float,
        max_v: float,
        unit: str,
    ) -> dict[str, Any]:
        return {
            "test_name": test_name,
            "loop": 1,
            "value": value,
            "min": min_v,
            "max": max_v,
            "unit": unit,
            "passed": passed,
            "is_measurement": True,
        }

    def _emit_result(self, unit: BatchUnit, test_name: str, payload: TestResultPayload) -> None:
        row = dict(payload)
        row["serial_number"] = unit.serial_number
        row["position_label"] = unit.position_label
        row["slot_index"] = unit.slot_index
        row["load_channel"] = unit.load_channel
        self.test_result.emit(test_name, row)
        if self._secure_log is not None:
            try:
                self._secure_log.log(
                    "test_result",
                    {
                        "serial_number": unit.serial_number,
                        "position_label": unit.position_label,
                        "test_name": test_name,
                        "passed": bool(payload.get("passed")),
                        "value": payload.get("value"),
                        "min": payload.get("min"),
                        "max": payload.get("max"),
                        "unit": payload.get("unit"),
                    },
                )
            except Exception:
                pass

    def _configure_load_for_step(self, step: TestStep) -> None:
        name = step.name.lower()
        resistance: float | None = None
        if "50w" in name:
            resistance = self._load_res_50w
        elif "300w" in name:
            resistance = self._load_res_300w
        if resistance is None:
            return
        try:
            self._hw.execute_command("setresistance", [f"{resistance:g}"])
            self._emit_log("info", f"Set load to constant resistance {resistance:g} ohm.")
        except Exception as exc:
            self._emit_log("error", f"Failed to set resistance for {step.name}: {exc}")

    def _run_step(self, step: TestStep) -> tuple[bool, float | None]:
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
                self._emit_log("error", f"ERROR in {step.name}: command {cmd['cmd']!r} raised: {exc!s}")
                return False, last_measurement
            self.progress_test.emit(min(99, int((idx / n) * 100)))

        if step.has_limits:
            if last_measurement is None:
                self._emit_log("error", f"{step.name}: Limits set but no measurement command executed; marking FAIL.")
                return False, None
            assert step.min_val is not None and step.max_val is not None
            return step.min_val <= last_measurement <= step.max_val, last_measurement

        return True, last_measurement

    def _execute_command(self, cmd: dict) -> float | None:
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
        return value if name in self._hw.measurement_commands else None

    def _save_record(self, record: TestRunRecord) -> None:
        try:
            self._db.save_run(record)
        except Exception as exc:
            self._emit_log("error", f"ERROR: failed to save run to database: {exc!s}")

    def resume(self) -> None:
        self._prompt_event.set()

    def pause(self) -> None:
        self._pause_event.clear()

    def resume_pause(self) -> None:
        self._pause_event.set()

    def stop(self) -> None:
        self._stop_requested = True
        self._prompt_event.set()
        self._pause_event.set()

    def report_snapshot(self) -> tuple[dict, list[dict]]:
        if not self._reports:
            return {}, []
        last = self._reports[-1]
        return last.meta(), last.rows()

    def report_snapshots(self) -> list[BatchUnitReport]:
        return list(self._reports)
