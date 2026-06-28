"""Run the LMU Pit Strategist overlay with live shared memory data from LMU/rFactor 2.

Usage:
    python run_overlay_live.py            # full overlay (1 finestra, griglia 3x3)
    python run_overlay_live.py --modular  # overlay modulare (4 finestrelle + menu)
"""
import sys
import argparse

print("[Overlay] Starting...")

from telemetry.source import LiveSharedMemorySource

print("[Overlay] Initialising telemetry source...")
source = LiveSharedMemorySource()
source.start()
print("[Overlay] Source started.")

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--modular", action="store_true",
                    help="Use the modular overlay (4 separate mini-windows + config menu)")
args, _unknown = parser.parse_known_args()

if args.modular:
    print("[Overlay] Launching MODULAR overlay (4 mini-windows + ⚙ menu)...")
    from overlay.app_new import run_overlay
else:
    print("[Overlay] Launching FULL overlay (1 window, 3x3 grid)...")
    from overlay.app import run_overlay

ret = run_overlay(source)
print(f"[Overlay] Overlay exited with code {ret}")
sys.exit(ret)
