"""Qt-free mock hardware driver for ATE simulation.

Exposes a generic `execute_command(name, args) -> float` interface used by
the script-driven runner. Returns a measurement value for commands listed in
`MEASUREMENT_COMMANDS`; for side-effect commands (`setvoltage`, `relay`,
`getid`) the return value is ignored by the runner.
"""

from __future__ import annotations

import random
import time
from typing import ClassVar


class MockHardware:
    """Simulates hardware instrument responses without any Qt dependencies."""

    MEASUREMENT_COMMANDS: ClassVar[frozenset[str]] = frozenset({"readchannel"})

    _CHANNEL_NOMINALS: ClassVar[dict[int, tuple[float, float, int]]] = {
        0: (5.0, 0.05, 3),    # 5 V rail, +/- ~50 mV jitter, 3 decimals
        1: (12.0, 0.10, 3),   # 12 V rail, +/- ~100 mV jitter
        2: (1.2, 0.30, 3),    # 1.2 A current, wider jitter
    }
    _OUT_OF_SPEC_PROB: ClassVar[float] = 0.25

    def __init__(self) -> None:
        self.connected = False
        self._rng = random.Random()

    def connect(self) -> bool:
        """Optional: simulate session open (not required for execute_command)."""
        time.sleep(0.5)
        self.connected = True
        return True

    def disconnect(self) -> None:
        """Optional: release simulated session."""
        self.connected = False

    def execute_command(self, command: str, args: list[str]) -> float:
        """Dispatch a single hardware command.

        Returns the measured value for measurement commands; returns `0.0`
        for side-effect commands. Raises `ValueError` for unknown commands.
        """
        cmd = command.lower()

        if cmd == "readchannel":
            channel = int(args[0]) if args else 0
            return self._read_channel(channel)

        if cmd == "setvoltage":
            time.sleep(0.05)
            return 0.0

        if cmd == "relay":
            time.sleep(0.05)
            return 0.0

        if cmd == "getid":
            time.sleep(0.05)
            return 0.0

        raise ValueError(f"Unknown hardware command: {command!r}")

    def _read_channel(self, channel: int) -> float:
        nominal, jitter, decimals = self._CHANNEL_NOMINALS.get(
            channel, (50.0, 35.0, 2)
        )
        time.sleep(self._rng.uniform(0.2, 0.6))
        outside = self._rng.random() < self._OUT_OF_SPEC_PROB
        spread = jitter * (3.0 if outside else 1.0)
        value = nominal + self._rng.uniform(-spread, spread)
        return round(value, decimals)
