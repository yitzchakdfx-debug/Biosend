"""Load and query test limits from JSON."""

from __future__ import annotations

import json
from pathlib import Path

from logic.models import TestLimit
from paths import user_data_path


class LimitManager:
    """Data-driven limits keyed by exact test name."""

    def __init__(self, limits_path: Path | None = None) -> None:
        path = limits_path or user_data_path("limits.json")
        self._limits: dict[str, TestLimit] = self._load(path)

    def _load(self, path: Path) -> dict[str, TestLimit]:
        raw_text = path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
        if not isinstance(data, dict):
            raise ValueError(f"limits.json root must be an object, got {type(data).__name__}")

        limits: dict[str, TestLimit] = {}
        for test_name, entry in data.items():
            if not isinstance(test_name, str):
                raise ValueError(f"limit key must be str, got {type(test_name).__name__}")
            if not isinstance(entry, dict):
                raise ValueError(
                    f'limit for "{test_name}" must be an object, got {type(entry).__name__}'
                )
            try:
                min_v = entry["min"]
                max_v = entry["max"]
                unit = entry["unit"]
            except KeyError as exc:
                raise ValueError(f'limit for "{test_name}" missing key: {exc.args[0]}') from exc
            if not isinstance(min_v, (int, float)) or isinstance(min_v, bool):
                raise ValueError(f'limit "{test_name}" min must be a number')
            if not isinstance(max_v, (int, float)) or isinstance(max_v, bool):
                raise ValueError(f'limit "{test_name}" max must be a number')
            if not isinstance(unit, str):
                raise ValueError(f'limit "{test_name}" unit must be a string')

            limits[test_name] = TestLimit(
                test_name=test_name,
                min_val=float(min_v),
                max_val=float(max_v),
                unit=unit,
            )
        return limits

    def get_limit(self, test_name: str) -> TestLimit | None:
        return self._limits.get(test_name)
