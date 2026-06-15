"""Prodigit electronic-load driver over VISA/USB.

This driver is intentionally configurable because Prodigit installations can
vary by option card, firmware, and site wiring. The default command templates
come from ``config.py`` and can be overridden in ``.env`` without code changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import (
    PRODIGIT_QUERY_CURRENT,
    PRODIGIT_QUERY_ID,
    PRODIGIT_QUERY_INPUT_VOLT,
    PRODIGIT_QUERY_POLARITY,
    PRODIGIT_QUERY_POWER,
    PRODIGIT_QUERY_VOLTAGE,
    PRODIGIT_SELECT_SLOT,
    PRODIGIT_SET_RELAY,
    PRODIGIT_SET_RESISTANCE,
    PRODIGIT_SET_VOLTAGE,
    PRODIGIT_VISA_BACKEND,
    PRODIGIT_VISA_RESOURCE,
    PRODIGIT_VISA_TIMEOUT_MS,
)
from drivers.base_driver import BaseDriver, UnknownCommandError


def _format_template(template: str, **values: Any) -> str:
    if not template.strip():
        return ""
    return template.format(**values).strip()


def _parse_float(value: str, fallback: float | None = None) -> float:
    try:
        return float(value.strip())
    except (TypeError, ValueError):
        if fallback is not None:
            return fallback
        raise


@dataclass(slots=True)
class _VISAContext:
    resource: Any
    resource_name: str


class ProdigitVisaDriver(BaseDriver):
    """VISA-backed driver for a Prodigit load system."""

    MEASUREMENT_COMMANDS = frozenset({"readchannel", "readinput", "checkpolarity"})

    def __init__(self) -> None:
        self._ctx: _VISAContext | None = None
        self._active_slot = 1
        self._load_serial = ""
        self._timeout_ms = int(_parse_float(PRODIGIT_VISA_TIMEOUT_MS, 5000))
        self._resource_name = PRODIGIT_VISA_RESOURCE.strip()
        self._backend = PRODIGIT_VISA_BACKEND.strip() or None

    @property
    def measurement_commands(self) -> frozenset[str]:
        return self.MEASUREMENT_COMMANDS

    def connect(self) -> bool:
        try:
            import pyvisa
        except ImportError as exc:
            raise RuntimeError(
                "pyvisa is required for the Prodigit USB/VISA driver. "
                "Install it and make sure the VISA runtime is available."
            ) from exc

        rm = pyvisa.ResourceManager(self._backend) if self._backend else pyvisa.ResourceManager()
        resource_name = self._resource_name or self._auto_discover(rm)
        if not resource_name:
            raise RuntimeError(
                "No VISA resource found for Prodigit. Set PRODIGIT_VISA_RESOURCE in .env."
            )

        resource = rm.open_resource(resource_name)
        resource.timeout = self._timeout_ms
        resource.read_termination = "\n"
        resource.write_termination = "\n"
        self._ctx = _VISAContext(resource=resource, resource_name=resource_name)
        try:
            _ = self.execute_command("getid", [])
        except Exception:
            # A real unit should still be usable even if *IDN? is not supported.
            pass
        return True

    def disconnect(self) -> None:
        if self._ctx is None:
            return
        try:
            self._ctx.resource.close()
        finally:
            self._ctx = None

    def activate_slot(self, slot_index: int, *, load_serial_number: str = "") -> None:
        self._active_slot = max(1, int(slot_index))
        self._load_serial = load_serial_number.strip()
        template = PRODIGIT_SELECT_SLOT
        if template.strip():
            self._write(template, slot=self._active_slot, load_serial=self._load_serial)

    def execute_command(self, command: str, args: list[str]) -> float:
        cmd = command.lower().strip()
        if cmd == "getid":
            return 0.0 if not self._query_text(PRODIGIT_QUERY_ID) else 0.0

        if cmd == "readinput":
            return self._read_measurement(PRODIGIT_QUERY_INPUT_VOLT, args)

        if cmd == "checkpolarity":
            return self._read_polarity()

        if cmd == "readchannel":
            channel = int(args[0]) if args else 0
            return self._read_channel(channel)

        if cmd == "setresistance":
            resistance = args[0] if args else "0"
            self._write(PRODIGIT_SET_RESISTANCE, value=resistance)
            return _parse_float(resistance, 0.0)

        if cmd == "setvoltage":
            voltage = args[0] if args else "0"
            if PRODIGIT_SET_VOLTAGE.strip():
                self._write(PRODIGIT_SET_VOLTAGE, value=voltage)
            return _parse_float(voltage, 0.0)

        if cmd == "relay":
            relay_id = args[0] if args else "1"
            state = args[1] if len(args) > 1 else "off"
            if PRODIGIT_SET_RELAY.strip():
                self._write(PRODIGIT_SET_RELAY, relay=relay_id, state=state)
            return 0.0

        raise UnknownCommandError(f"Unknown hardware command: {command!r}")

    def _require_resource(self) -> Any:
        if self._ctx is None:
            raise RuntimeError("Prodigit VISA driver is not connected.")
        return self._ctx.resource

    def _auto_discover(self, rm: Any) -> str:
        try:
            resources = rm.list_resources()
        except Exception:
            resources = ()
        for resource_name in resources:
            if "USB" not in str(resource_name).upper():
                continue
            try:
                resource = rm.open_resource(resource_name)
                resource.timeout = self._timeout_ms
                resource.read_termination = "\n"
                resource.write_termination = "\n"
                identity = resource.query(PRODIGIT_QUERY_ID).strip()
                resource.close()
                if identity:
                    return str(resource_name)
            except Exception:
                continue
        return next((str(item) for item in resources if "USB" in str(item).upper()), "")

    def _query_text(self, template: str, **values: Any) -> str:
        command = _format_template(template, slot=self._active_slot, load_serial=self._load_serial, **values)
        if not command:
            return ""
        return self._require_resource().query(command).strip()

    def _write(self, template: str, **values: Any) -> None:
        command = _format_template(template, slot=self._active_slot, load_serial=self._load_serial, **values)
        if not command:
            return
        resource = self._require_resource()
        for part in command.split(";"):
            part = part.strip()
            if part:
                resource.write(part)

    def _read_measurement(self, template: str, args: list[str]) -> float:
        query = _format_template(
            template,
            slot=self._active_slot,
            load_serial=self._load_serial,
            channel=args[0] if args else "",
        )
        if not query:
            raise RuntimeError("No VISA query template configured for this measurement.")
        value = self._require_resource().query(query).strip()
        return _parse_float(value)

    def _read_polarity(self) -> float:
        response = self._query_text(PRODIGIT_QUERY_POLARITY)
        if not response:
            return 1.0
        lowered = response.strip().lower()
        if lowered in {"1", "ok", "pass", "pos", "positive", "normal"}:
            return 1.0
        if lowered in {"0", "-1", "fail", "neg", "negative", "reverse"}:
            return -1.0
        try:
            return 1.0 if float(lowered) >= 0 else -1.0
        except ValueError:
            return 1.0 if "pos" in lowered else -1.0

    def _read_channel(self, channel: int) -> float:
        if channel in {0, 2, 10}:
            return self._read_measurement(PRODIGIT_QUERY_VOLTAGE, [str(channel)])
        if channel in {1, 3}:
            return self._read_measurement(PRODIGIT_QUERY_CURRENT, [str(channel)])
        if channel == 4:
            return self._read_measurement(PRODIGIT_QUERY_POWER, [str(channel)])
        return self._read_measurement(PRODIGIT_QUERY_VOLTAGE, [str(channel)])
