"""System feature flags. Edit per-station to enable optional modules."""

# Set to True for machines with power supply monitoring.
# Set to False for basic ATE stations to keep the UI clean and save resources.
SHOW_LIVE_MONITOR: bool = True
