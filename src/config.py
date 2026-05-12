"""System feature flags and Phase 13 configuration."""

from __future__ import annotations

# Set to True for machines with power supply monitoring.
# Set to False for basic ATE stations to keep the UI clean and save resources.
SHOW_LIVE_MONITOR: bool = True
SHOW_SEARCH_BAR: bool = False

# Pre-test dialog and test version tagging.
UUT_TYPES: list[str] = ["Power main", "Power Ctrl DSP", "Demo UUT"]

# Encrypted system log key material (derived with PBKDF2 in SecureLogger).
LOG_ENCRYPTION_PASSWORD: str = "DFX"

# PDF password applied to Admin reports only (via PyPDF2).
ADMIN_REPORT_PASSWORD: str = "DFX"

# Station / tester identification on reports (dummy string until hardware binding).
TESTER_SERIAL_NUMBER: str = "ATE-DFX-001"
