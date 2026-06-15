"""Hardware driver selection helpers."""

from __future__ import annotations

from config import HARDWARE_BACKEND

from drivers.base_driver import BaseDriver
from drivers.mock_hardware import MockHardware


def create_driver() -> BaseDriver:
    backend = HARDWARE_BACKEND.strip().lower()
    if backend in {"prodigit", "visa", "usb"}:
        from drivers.prodigit_visa import ProdigitVisaDriver

        return ProdigitVisaDriver()
    return MockHardware()
