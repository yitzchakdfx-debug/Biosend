"""Background monitor loop for live voltage/current readout."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from config import HARDWARE_BACKEND
from drivers.base_driver import HardwareError
from drivers.factory import create_driver


class MonitorThread(QThread):
    """Emits live readings on an interval.

    When the active backend is ``mock`` this falls back to a synthetic demo
    stream; when the backend is ``prodigit`` it polls the hardware driver.
    """

    values_updated = Signal(dict)

    def __init__(
        self,
        parent: object | None = None,
        *,
        interval_ms: int = 500,
        simulate: bool | None = None,
    ) -> None:
        super().__init__(parent)
        self._interval_ms = max(1, interval_ms)
        self._simulate = simulate
        self._stop_requested = False
        self._driver = None

    def run(self) -> None:
        self._driver = create_driver()
        use_simulation = self._simulate
        if use_simulation is None:
            use_simulation = HARDWARE_BACKEND.strip().lower() != "prodigit"

        if not use_simulation:
            try:
                self._driver.connect()
            except Exception:
                return

        try:
            while not self._stop_requested:
                if use_simulation:
                    self.values_updated.emit(self._synthetic_values())
                else:
                    try:
                        voltage = self._driver.execute_command("readinput", [])
                        current = self._driver.execute_command("readchannel", ["3"])
                        self.values_updated.emit({"V": voltage, "A": current})
                    except HardwareError:
                        break
                    except Exception:
                        break
                self.msleep(self._interval_ms)
        finally:
            if self._driver is not None:
                try:
                    self._driver.disconnect()
                except Exception:
                    pass

    def stop(self) -> None:
        self._stop_requested = True
        self.wait()

    def _synthetic_values(self) -> dict[str, float]:
        from random import uniform

        voltage = 12.0 + uniform(-0.15, 0.15)
        current = 0.5 + uniform(-0.05, 0.05)
        return {"V": voltage, "A": current}
