"""Production-ready launcher for LMU Pit Strategist.

Single entry point: starts web UI, auto-launches overlay when LMU is detected.
On first run, auto-installs dependencies from requirements.txt if missing.
"""
import sys
import os
import time
import webbrowser
import signal
import threading
import subprocess
import importlib
from pathlib import Path

LMU_EXE_NAMES = ["LMU.exe", "Le Mans Ultimate.exe", "LMU_Racer.exe", "LMU"]
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8000
POLL_INTERVAL = 2.0

REQUIRED_MODULES = {
    "numpy": "numpy",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "jinja2": "jinja2",
    "psutil": "psutil",
    "PySide6": "PySide6",
    "scipy": "scipy",
}


def _load_dotenv() -> dict:
    """
    Load a simple KEY=VALUE .env file from the project root.
    Returns the parsed dict. Does NOT override os.environ entries
    that are already set (env vars take precedence).
    """
    env_path = Path(__file__).resolve().parent / ".env"
    parsed = {}
    if not env_path.exists():
        return parsed
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        parsed[k] = v
        if k not in os.environ:
            os.environ[k] = v
    return parsed


def _configure_cloud_backend() -> None:
    """
    If TURSO_URL and TURSO_TOKEN are set, configure the TursoSync backend.
    No-op otherwise. Errors are logged but not fatal — the app still runs
    fine without a cloud backend (just local-only mode).
    """
    if not os.environ.get("TURSO_URL") or not os.environ.get("TURSO_TOKEN"):
        return
    try:
        from database.cloud import backend_from_config, set_backend
        backend = backend_from_config({
            "backend": "turso",
            "turso": {
                "url": os.environ["TURSO_URL"],
                "auth_token": os.environ["TURSO_TOKEN"],
            },
        })
        set_backend(backend)
        # Print status on startup
        status = backend.status()
        if status.get("message"):
            print(f"[Cloud] {status['message']}")
    except Exception as e:
        print(f"[Cloud] WARNING: could not configure Turso backend: {e}")


def _check_dependencies() -> list:
    missing = []
    for mod_name, _pkg_name in REQUIRED_MODULES.items():
        try:
            importlib.import_module(mod_name)
        except ImportError:
            missing.append(mod_name)
    return missing


def _install_dependencies(missing: list) -> bool:
    req_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
    if not os.path.exists(req_file):
        print("[Launcher] requirements.txt not found. Cannot auto-install.")
        return False

    print(f"[Launcher] Missing dependencies: {', '.join(missing)}")
    print("[Launcher] Installing from requirements.txt...")
    python_exe = sys.executable
    try:
        proc = subprocess.run(
            [python_exe, "-m", "pip", "install", "-r", req_file],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            print("[Launcher] Dependencies installed successfully.")
            return True
        else:
            print(f"[Launcher] pip install failed:\n{proc.stderr}")
            return False
    except Exception as e:
        print(f"[Launcher] Failed to run pip: {e}")
        return False


def _ensure_dependencies() -> None:
    missing = _check_dependencies()
    if not missing:
        return

    print("[Launcher] First run detected — setting up environment...")
    success = _install_dependencies(missing)
    if not success:
        print("[Launcher] WARNING: Some dependencies could not be installed.")
        print("[Launcher] Please run: pip install -r requirements.txt")
        sys.exit(1)


def _is_lmu_running() -> bool:
    try:
        import psutil
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
    import uvicorn
    uvicorn.run(
        "web.server:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=False,
        log_level="warning",
    )


def _wait_for_server(timeout: float = 10.0) -> bool:
    import urllib.request
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
    """Launch overlay as a separate process, respecting the overlay_mode setting."""
    # Check the overlay config for the desired mode
    overlay_mode = "full"  # default
    try:
        import json as _json
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "overlay", "overlay_config.json")
        if os.path.exists(config_path):
            with open(config_path) as _f:
                _cfg = _json.load(_f)
                overlay_mode = _cfg.get("overlay_mode", "full")
    except Exception:
        pass

    if getattr(sys, 'frozen', False):
        overlay_path = os.path.join(os.path.dirname(sys.executable), "LMU Overlay.exe")
        cmd = [overlay_path]
        if overlay_mode == "modular":
            cmd.append("--modular")
    else:
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_overlay_live.py")
        python_exe = sys.executable
        cmd = [python_exe, script_path]
        if overlay_mode == "modular":
            cmd.append("--modular")

    print(f"[Launcher] Launching overlay ({overlay_mode} mode): {' '.join(cmd)}")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        print(f"[Launcher] Overlay PID: {proc.pid}")
    except Exception as e:
        print(f"[Launcher] FAILED to launch overlay: {e}")
        raise

    threading.Thread(
        target=_pump_stdout,
        args=(proc,),
        daemon=True,
    ).start()

    return proc


def _pump_stdout(proc):
    try:
        for line in proc.stdout:
            print(f"[Overlay] {line.rstrip()}")
    except Exception:
        pass


def main():
    _ensure_dependencies()

    # Load .env (TURSO_URL, TURSO_TOKEN, ...) BEFORE configuring backend
    _load_dotenv()
    _configure_cloud_backend()

    # Security self-audit on startup
    print()
    try:
        from security.self_audit import run_audit
        audit = run_audit(silent=True)
        if audit.get("has_critical"):
            print("  ⚠️   RUN_AUDIT FOUND CRITICAL ISSUES — fix them before going live")
            print(f"  ⚠️   See details above or run: python -m security.self_audit")
    except ImportError:
        pass  # security module may not exist on very old clones

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
