"""System feature flags and configuration, sourced from the environment (.env).

`.env` is the single source of truth (see DOC/.env.example). Every value falls
back to a safe default so the app launches even without a .env file.
"""
from __future__ import annotations

from env import get_bool, get_list, get_str

# --- Feature flags ---
SHOW_LIVE_MONITOR: bool = get_bool("SHOW_LIVE_MONITOR", True)
SHOW_SEARCH_BAR: bool = get_bool("SHOW_SEARCH_BAR", False)

# --- Pre-test dialog UUT options ---
UUT_TYPES: list[str] = get_list("UUT_TYPES", ["Power main", "Power Ctrl DSP", "Demo UUT"])
LOAD_SERIALS: list[str] = get_list(
    "LOAD_SERIALS",
    ["PRODIGIT-CH1", "PRODIGIT-CH2", "PRODIGIT-CH3", "PRODIGIT-CH4"],
)

# --- Secrets (override in .env) ---
LOG_ENCRYPTION_PASSWORD: str = get_str("LOG_ENCRYPTION_PASSWORD", "DFX")
ADMIN_REPORT_PASSWORD: str = get_str("ADMIN_REPORT_PASSWORD", "DFX")

# --- Default admin seed (used only on first DB init) ---
DEFAULT_ADMIN_USERNAME: str = get_str("DEFAULT_ADMIN_USERNAME", "lior")
DEFAULT_ADMIN_PASSWORD: str = get_str("DEFAULT_ADMIN_PASSWORD", "Aa123456")
DEFAULT_ADMIN_EMPLOYEE_ID: str = get_str("DEFAULT_ADMIN_EMPLOYEE_ID", "0000")

# --- Station / report identity ---
TESTER_SERIAL_NUMBER: str = get_str("TESTER_SERIAL_NUMBER", "ATE-DFX-001")
INPUT_CONNECTED_TARGET_V: str = get_str("INPUT_CONNECTED_TARGET_V", "24")
INPUT_CONNECTED_TOLERANCE_PCT: str = get_str("INPUT_CONNECTED_TOLERANCE_PCT", "5")
LOAD_RESISTANCE_50W_OHM: str = get_str("LOAD_RESISTANCE_50W_OHM", "12.5")
LOAD_RESISTANCE_300W_OHM: str = get_str("LOAD_RESISTANCE_300W_OHM", "2.2")
