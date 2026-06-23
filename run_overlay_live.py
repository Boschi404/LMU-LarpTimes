"""Run the LMU Pit Strategist overlay with live shared memory data from LMU/rFactor 2."""
import sys
import time

print("[Overlay] Starting...")

from overlay.app import run_overlay
from telemetry.source import LiveSharedMemorySource

print("[Overlay] Initialising telemetry source...")
source = LiveSharedMemorySource()
source.start()
print("[Overlay] Source started.")

print("[Overlay] Launching overlay GUI...")
ret = run_overlay(source)
print(f"[Overlay] Overlay exited with code {ret}")
sys.exit(ret)
