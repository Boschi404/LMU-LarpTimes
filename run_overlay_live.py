"""Run the LMU Pit Strategist overlay with live shared memory data from LMU/rFactor 2."""
from overlay.app import run_overlay
from telemetry.source import LiveSharedMemorySource

if __name__ == "__main__":
    # Use the live shared memory source (LMU or rFactor 2 fallback)
    # Make sure:
    #  1. LMU is running on this machine
    #  2. "Enable Plugins" is enabled in LMU Settings → Gameplay
    #  3. LMU is in Windowed or Borderless mode (not exclusive fullscreen)
    source = LiveSharedMemorySource()
    run_overlay(source)
