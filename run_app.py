"""Production-ready launcher for LMU Pit Strategist.

Single entry point: starts web UI, auto-launches overlay when LMU is detected.
"""
import sys
import os
import time
import webbrowser
import signal
import threading
import urllib.request
import urllib.error
import subprocess

import psutil
import uvicorn


LMU_EXE_NAMES = ["LMU.exe", "Le Mans Ultimate.exe", "LMU_Racer.exe", "LMU"]
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8000
POLL_INTERVAL = 2.0


def _is_lmu_running() -> bool:
    try:
        for proc in psutil.process_iter(['name']):
            try:
                name = (proc.info.get('name') or '').lower()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            if any(n.lower() in name for n in LMU_EXE_NAMES):
                return True
    except Exception:
        pass
    return False


def _run_server():
    uvicorn.run(
        "web.server:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=False,
        log_level="warning",
    )


def _wait_for_server(timeout: float = 10.0) -> bool:
    url = f"http://{SERVER_HOST}:{SERVER_PORT}/"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


def _launch_overlay_subprocess():
    """Launch overlay as a separate process so PySide6 errors don't kill the launcher."""
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_overlay_live.py")
    python_exe = sys.executable
    proc = subprocess.Popen([python_exe, script_path])
    return proc


def main():
    print("=" * 60)
    print("  LMU Pit Strategist — Launcher")
    print("=" * 60)

    print(f"[Launcher] Starting web server on http://{SERVER_HOST}:{SERVER_PORT} ...")
    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()

    print("[Launcher] Waiting for web server...")
    if _wait_for_server():
        print("[Launcher] Web server ready.")
    else:
        print("[Launcher] WARNING: web server not responding, opening browser anyway.")

    webbrowser.open(f"http://{SERVER_HOST}:{SERVER_PORT}/")
    print("[Launcher] Browser opened.")

    print("[Launcher] Monitoring for LMU process... (Ctrl+C to exit)")

    def _handle_sigint(signum, frame):
        print("\n[Launcher] Shutting down.")
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_sigint)

    overlay_active = False
    overlay_proc = None

    while True:
        if not overlay_active and _is_lmu_running():
            print("[Launcher] LMU detected — launching overlay.")
            try:
                overlay_proc = _launch_overlay_subprocess()
                overlay_proc.wait()
            except Exception as e:
                print(f"[Launcher] Overlay error: {e}")
            overlay_active = False
            overlay_proc = None
            print("[Launcher] Overlay closed. Monitoring for LMU...")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
