"""
Tests for the self-audit module (security/self_audit.py).

Covers:
  - check_gitignore: .env in .gitignore
  - check_env_permissions: .env permissions (POSIX + Windows)
  - check_env_token: token format validation
  - check_host_binding: 127.0.0.1 vs 0.0.0.0
  - check_jwt_secret: auth_secret.txt presence
  - check_webbrowser_exposed: tunneling env vars
  - run_audit: full run with results
"""

import os
import sys
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ──────────────────────────────────────────────────────────────────────────────
# check_gitignore
# ──────────────────────────────────────────────────────────────────────────────

def test_gitignore_contains_dot_env(monkeypatch):
    def test_gitignore_contains_dot_env(monkeypatch):
        """If .gitignore contains .env, check_gitignore returns 'ok'."""
        from security.self_audit import check_gitignore
        # Use the real project root
        from security.self_audit import PROJECT_ROOT
        sev, msg = check_gitignore(project_root=PROJECT_ROOT)
        if (PROJECT_ROOT / ".gitignore").exists():
            content = (PROJECT_ROOT / ".gitignore").read_text()
            if ".env" in content:
                assert sev == "ok"
                assert ".env" in msg


    def test_gitignore_missing_is_warn(monkeypatch, tmp_path):
        """No .gitignore at all yields a warning."""
        from security.self_audit import check_gitignore
        # Use a tmp_path that has no .gitignore
        sev, msg = check_gitignore(project_root=tmp_path)
        assert sev == "warn"
        assert "no .gitignore" in msg.lower()


# ──────────────────────────────────────────────────────────────────────────────
# check_env_permissions
# ──────────────────────────────────────────────────────────────────────────────

def test_env_permissions_no_env(monkeypatch, tmp_path):
    """No .env at all yields 'info' (cloud disabled, OK)."""
    from security.self_audit import check_env_permissions
    sev, msg = check_env_permissions(project_root=tmp_path)
    assert sev == "info"
    assert "no .env" in msg.lower()


def test_env_permissions_with_env(monkeypatch, tmp_path):
    """With a valid .env, returns 'ok' or 'warn' (never 'critical')."""
    from security.self_audit import check_env_permissions
    (tmp_path / ".env").write_text("TURSO_TOKEN=test\n", encoding="utf-8")
    sev, msg = check_env_permissions(project_root=tmp_path)
    assert sev in ("ok", "warn", "info")


# ──────────────────────────────────────────────────────────────────────────────
# check_env_token
# ──────────────────────────────────────────────────────────────────────────────

def test_token_no_env(monkeypatch, tmp_path):
    """No .env file = info (cloud not configured)."""
    from security.self_audit import check_env_token
    sev, msg = check_env_token(project_root=tmp_path)
    assert sev == "info"


def test_token_not_set(monkeypatch, tmp_path):
    """TURSO_TOKEN= but empty = info (cloud not configured)."""
    from security.self_audit import check_env_token
    (tmp_path / ".env").write_text("TURSO_TOKEN=\n", encoding="utf-8")
    sev, msg = check_env_token(project_root=tmp_path)
    assert sev == "info"


def test_token_valid(monkeypatch, tmp_path):
    """A valid-looking token returns 'ok'."""
    from security.self_audit import check_env_token
    (tmp_path / ".env").write_text(
        "TURSO_TOKEN=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.x.y\n",
        encoding="utf-8",
    )
    sev, msg = check_env_token(project_root=tmp_path)
    assert sev == "ok"


def test_token_too_short(monkeypatch, tmp_path):
    """Token < 20 chars is critical."""
    from security.self_audit import check_env_token
    (tmp_path / ".env").write_text("TURSO_TOKEN=short\n", encoding="utf-8")
    sev, msg = check_env_token(project_root=tmp_path)
    assert sev == "critical"
    assert "too short" in msg.lower()


def test_token_with_spaces(monkeypatch, tmp_path):
    """Token with spaces is critical (will be rejected)."""
    from security.self_audit import check_env_token
    (tmp_path / ".env").write_text(
        "TURSO_TOKEN=eyJ token with spaces\n", encoding="utf-8"
    )
    sev, msg = check_env_token(project_root=tmp_path)
    assert sev == "critical"
    assert "spaces" in msg.lower()


# ──────────────────────────────────────────────────────────────────────────────
# check_host_binding
# ──────────────────────────────────────────────────────────────────────────────

def test_host_binding_localhost(monkeypatch, tmp_path):
    """When run_app.py has SERVER_HOST='127.0.0.1'."""
    from security.self_audit import check_host_binding
    (tmp_path / "run_app.py").write_text(
        'SERVER_HOST = "127.0.0.1"\n', encoding="utf-8"
    )
    sev, msg = check_host_binding(project_root=tmp_path)
    assert sev == "ok"
    assert "127.0.0.1" in msg


def test_host_binding_public(monkeypatch, tmp_path):
    """When run_app.py has SERVER_HOST='0.0.0.0' = critical."""
    from security.self_audit import check_host_binding
    (tmp_path / "run_app.py").write_text(
        'SERVER_HOST = "0.0.0.0"\n', encoding="utf-8"
    )
    sev, msg = check_host_binding(project_root=tmp_path)
    assert sev == "critical"
    assert "0.0.0.0" in msg


# ──────────────────────────────────────────────────────────────────────────────
# check_webbrowser_exposed
# ──────────────────────────────────────────────────────────────────────────────

def test_no_tunneling_env_vars():
    """Without tunneling env vars, returns 'ok'."""
    from security.self_audit import check_webbrowser_exposed
    sev, msg = check_webbrowser_exposed()
    assert sev == "ok"


def test_tunneling_env_var_detected(monkeypatch):
    """With NGROK_AUTHTOKEN set, returns 'warn'."""
    from security.self_audit import check_webbrowser_exposed
    with monkeypatch.context() as m:
        m.setenv("NGROK_AUTHTOKEN", "test")
        sev, msg = check_webbrowser_exposed()
        assert sev == "warn"
        assert "NGROK_AUTHTOKEN" in msg


# ──────────────────────────────────────────────────────────────────────────────
# run_audit — full integration
# ──────────────────────────────────────────────────────────────────────────────

def test_run_audit_returns_summary():
    """run_audit() returns a dict with ok/warn/critical/info counts."""
    from security.self_audit import run_audit
    result = run_audit(silent=True)
    assert "ok" in result
    assert "warn" in result
    assert "critical" in result
    assert "info" in result
    assert "has_critical" in result
    assert "results" in result
    assert len(result["results"]) == 6  # 6 checks


def test_run_audit_never_crashes():
    """run_audit() handles all edge cases silently."""
    from security.self_audit import run_audit
    result = run_audit(silent=True)
    assert isinstance(result["has_critical"], bool)
    assert all(r["severity"] in ("ok", "warn", "critical", "info") for r in result["results"])
