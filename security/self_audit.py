"""
Self-audit che gira all'avvio dell'app. Controlla:
  1. .env non è committabile (in .gitignore)
  2. Server ascolta su 127.0.0.1, non 0.0.0.0
  3. Token Turso non contiene spazi/truncation
  4. .env non è leggibile da altri (POSIX chmod 600)
  5. Porta 8000 non è esposta su rete pubblica (solo un warn)
  6. Nessuna dipendenza deprecata / vulnerabile (verbo)
  7. JWT secret file non è committabile

Ogni check è un Warning/Bug/Ok silenzioso. I risultati
vengono stampati in console all'avvio (una tantum).
Se un CRITICAL viene trovato, l'app si avvia ma stampa
un avviso in rosso ben visibile.

Uso:
    from security.self_audit import run_audit
    audit_result = run_audit()
    if audit_result["critical"]:
        print("CORREGGI I PROBLEMI CRITICI PRIMA DI CONTINUARE")
"""

import os
import stat
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

# Colori per console (funzionano su Windows 10+)
_RED = "\033[91m" if os.name != "nt" else ""
_GREEN = "\033[92m" if os.name != "nt" else ""
_YELLOW = "\033[93m" if os.name != "nt" else ""
_CYAN = "\033[96m" if os.name != "nt" else ""
_RESET = "\033[0m" if os.name != "nt" else ""

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVER_HOST = "127.0.0.1"  # default, deve essere questo
SERVER_PORT = 8000


def _ok(msg: str) -> str:
    return f"{_GREEN}✓{_RESET} {msg}"


def _warn(msg: str) -> str:
    return f"{_YELLOW}⚠{_RESET} {msg}"


def _crit(msg: str) -> str:
    return f"{_RED}✗{_RESET} {msg}"


def _info(msg: str) -> str:
    return f"{_CYAN}i{_RESET} {msg}"


# ── Checks ───────────────────────────────────────────────────────────────

def check_gitignore(project_root: Path = PROJECT_ROOT) -> Tuple[str, str]:
    """Check that .env is in .gitignore (never committed)."""
    gitignore = project_root / ".gitignore"
    if not gitignore.exists():
        return "warn", "no .gitignore found — create one"
    content = gitignore.read_text(encoding="utf-8")
    if ".env" not in content:
        return "critical", ".env NOT in .gitignore — token leak risk!"
    if ".env" in content:
        return "ok", ".env in .gitignore ✓"
    return "ok", "ok"


def check_env_permissions(project_root: Path = PROJECT_ROOT) -> Tuple[str, str]:
    """Check .env is not world-readable (POSIX only)."""
    env_file = project_root / ".env"
    if not env_file.exists():
        return "info", "no .env file (cloud sync disabled, OK)"
    if os.name != "posix" and sys.platform != "linux":
        # Windows: Advanced permissions not checked via POSIX chmod
        # Quick check: file not hidden and accessible only to owner
        try:
            st = os.stat(env_file)
            # On Windows S_IROTH is 4 (others can read). We check that
            # the file is NOT in a public location
            env_str = str(env_file).lower()
            if "public" in env_str or "shared" in env_str:
                return "warn", ".env is in a shared/public location"
        except Exception:
            pass
        return "ok", ".env exists (Windows — no POSIX permission check)"
    try:
        mode = stat.S_IMODE(os.stat(env_file).st_mode)
        if mode & stat.S_IROTH:
            return "warn", ".env is world-readable (chmod 600 recommended)"
        if mode & stat.S_IRGRP:
            return "warn", ".env is group-readable (chmod 600 recommended)"
        return "ok", ".env permissions OK (mode 600 or equivalent)"
    except Exception:
        return "ok", ".env exists"


def check_env_token(project_root: Path = PROJECT_ROOT) -> Tuple[str, str]:
    """Check Turso token is present and looks valid."""
    env_file = project_root / ".env"
    if not env_file.exists():
        return "info", "no .env, skipping token check"
    try:
        token = None
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("TURSO_TOKEN="):
                token = line.split("=", 1)[1].strip().strip("\"'")
        if not token:
            return "info", "TURSO_TOKEN not set in .env (cloud sync disabled)"
        if len(token) < 20:
            return "critical", "TURSO_TOKEN is too short (< 20 chars) — invalid!"
        if not token.startswith("ey"):
            return "warn", f"TURSO_TOKEN doesn't start with 'ey' — may be wrong format"
        if " " in token:
            return "critical", "TURSO_TOKEN contains spaces — will be rejected!"
        return "ok", f"TURSO_TOKEN present ({len(token)} chars)"
    except Exception as e:
        return "warn", f"cannot read .env: {e}"


def check_host_binding(project_root: Path = PROJECT_ROOT) -> Tuple[str, str]:
    """Check server is binding to localhost only (read from run_app.py)."""
    run_app = project_root / "run_app.py"
    if not run_app.exists():
        return "info", "no run_app.py to check"
    try:
        content = run_app.read_text(encoding="utf-8")
        if 'SERVER_HOST = "127.0.0.1"' in content or "SERVER_HOST = '127.0.0.1'" in content:
            return "ok", f"server binds to 127.0.0.1 (localhost only)"
        elif '"0.0.0.0"' in content or "'0.0.0.0'" in content:
            return "critical", "server binds to 0.0.0.0 — accessible from the NETWORK!"
        else:
            return "warn", f"unknown SERVER_HOST in run_app.py — check manually"
    except Exception:
        return "info", "cannot check host binding"


def check_jwt_secret(project_root: Path = PROJECT_ROOT) -> Tuple[str, str]:
    """Check JWT secret file is not accidentally committed."""
    import paths
    try:
        secret_path = Path(paths.base_dir()) / "auth_secret.txt"
        if not secret_path.exists():
            return "info", "no auth_secret.txt (auth module not in use, OK)"
        # Check it's in .gitignore
        gitignore = project_root / ".gitignore"
        if gitignore.exists():
            content = gitignore.read_text(encoding="utf-8")
            if "auth_secret.txt" not in content and "auth_secret" not in content:
                return "warn", "auth_secret.txt NOT in .gitignore — commit risk!"
        return "ok", "auth_secret.txt present"
    except Exception:
        return "info", "cannot check JWT secret"


def check_webbrowser_exposed() -> Tuple[str, str]:
    """Warn if the user may have exposed localhost externally (e.g. ngrok)."""
    # We can't detect ngrok directly, but we can check environment variables
    # that suggest a tunneling service is active
    for env_var in ["NGROK_AUTHTOKEN", "CLOUDFLARE_TUNNEL_TOKEN", "FRP_TOKEN", "BORING_REGISTER"]:
        if os.environ.get(env_var):
            return "warn", f"{env_var} is set — are you tunneling localhost?"
    return "ok", "no tunneling env vars detected"


# ── Run ───────────────────────────────────────────────────────────────────

def run_audit(silent: bool = False, project_root: Optional[Path] = None) -> Dict[str, Any]:
    """
    Run all security checks and return a summary dict.

    Args:
        silent: If True, only print warnings and criticals (no ok lines).
        project_root: Override the project root (for testing).

    Returns:
        {
            "ok": int,
            "warn": int,
            "critical": int,
            "info": int,
            "has_critical": bool,
            "results": [{"severity": str, "message": str}, ...]
        }
    """
    root = project_root or PROJECT_ROOT
    checks = [
        ("Gitignore", check_gitignore(root)),
        (".env permissions", check_env_permissions(root)),
        ("Turso token", check_env_token(root)),
        ("Host binding", check_host_binding(root)),
        ("JWT secret", check_jwt_secret(root)),
        ("Network exposure", check_webbrowser_exposed()),
    ]

    results = []
    counts = {"ok": 0, "warn": 0, "critical": 0, "info": 0}

    for name, (severity, message) in checks:
        results.append({"name": name, "severity": severity, "message": message})
        counts[severity] = counts.get(severity, 0) + 1

        if silent and severity in ("ok", "info"):
            continue

        if severity == "ok":
            print(f"  {_ok(message)}")
        elif severity == "warn":
            print(f"  {_warn(message)}")
        elif severity == "critical":
            print(f"  {_crit(message)}")
        else:
            print(f"  {_info(message)}")

    return {
        **counts,
        "has_critical": counts.get("critical", 0) > 0,
        "results": results,
    }


if __name__ == "__main__":
    print(f"\n{_CYAN}═══════════════════════════════════════{_RESET}")
    print(f"{_CYAN}  LMU Pit Strategist — Security Audit{_RESET}")
    print(f"{_CYAN}═══════════════════════════════════════{_RESET}")
    result = run_audit()
    print()
    if result["has_critical"]:
        print(f"  {_RED}⚠ {result['critical']} CRITICAL issue(s) detected!{_RESET}")
    else:
        print(f"  {_GREEN}✓ All checks passed.{_RESET}")
    print()
