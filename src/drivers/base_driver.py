"""Abstract base class for hardware interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from logic.models import TestOutcome

if TYPE_CHECKING:
    from logic.models import TestConfig


class BaseDriver(ABC):
    """Hardware or simulation backend for tests."""

    @abstractmethod
    def connect(self) -> bool:
        """Open session to hardware (or simulator)."""

    @abstractmethod
    def disconnect(self) -> None:
        """Release resources."""

    @abstractmethod
    def execute_test(
        self, config: TestConfig
    ) -> tuple[TestOutcome, str, dict[str, float]]:
        """Run one test; returns (outcome, message, measured values)."""
