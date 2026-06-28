"""
Tests for scripts/setup_turus.py

We mock the libsql_client module so the test never touches the network.
Covers:
  - .env loading and saving
  - .env permissions (POSIX only)
  - gitignore updates
  - URL validation
  - Connection test (mocked libsql)
  - Schema application (mocked libsql, multiple statements)
  - Schema verification
  - --verify mode
  - Non-interactive --url + --token mode
"""

import os
import sys
import stat
import json
import types
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
SETUP_SCRIPT = SCRIPTS / "setup_turso.py"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

class _FakeResult:
    """Mock of libsql_client Result. Iterable (yields rows as tuples)."""
    def __init__(self, rows):
        self.rows = rows

    def __iter__(self):
        return iter(self.rows)

    def __len__(self):
        return len(self.rows)


class _FakeLibsqlClient:
    """In-memory mock of libsql_client.Client. Accepts any args/kwargs."""
    def __init__(self, *args, **kwargs):
        if args:
            self.url = args[0]
            self.auth_token = args[1] if len(args) > 1 else ""
        else:
            self.url = kwargs.get("url", "")
            self.auth_token = kwargs.get("auth_token", "")
        self.executed = []
        self._tables = set()

    def execute(self, sql):
        self.executed.append(sql.strip())
        sql_l = sql.strip().lower()
        if sql_l.startswith("select 1"):
            return _FakeResult([(1,)])
        if sql_l.startswith("create table"):
            # Extract table name
            parts = sql_l.split()
            try:
                idx = parts.index("table")
                self._tables.add(parts[idx + 2])  # "if not exists <name>"
            except (ValueError, IndexError):
                pass
            return _FakeResult([])
        if sql_l.startswith("create index"):
            return _FakeResult([])
        if sql_l.startswith("insert or ignore"):
            return _FakeResult([])
        if "from sqlite_master" in sql_l:
            # Return all tables we have
            return _FakeResult([(t,) for t in sorted(self._tables)])
        return _FakeResult([])


def _install_fake_libsql(monkeypatch, pre_populate_tables=False):
    """Install a fake libsql_client module into sys.modules."""
    def factory(*args, **kwargs):
        c = _FakeLibsqlClient(args[0] if args else kwargs.get("url", ""),
                              args[1] if len(args) > 1 else kwargs.get("auth_token", ""))
        if pre_populate_tables:
            for t in ["users", "sessions", "stints", "laps", "pit_stops", "community_meta"]:
                c._tables.add(t)
        return c

    fake = types.ModuleType("libsql_client")
    fake.create_client = factory
    fake._factory = factory
    monkeypatch.setitem(sys.modules, "libsql_client", fake)
    return fake


def _run_setup(args: list, input_text: str = "") -> subprocess.CompletedProcess:
    """Run the setup script as a subprocess."""
    return subprocess.run(
        [sys.executable, str(SETUP_SCRIPT)] + args,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=30,
    )


# ──────────────────────────────────────────────────────────────────────────────
# .env loading / saving
# ──────────────────────────────────────────────────────────────────────────────

def test_load_env_reads_simple_values(tmp_path, monkeypatch):
    """_load_env reads KEY=VALUE pairs from .env."""
    monkeypatch.chdir(ROOT)
    # Create a temp .env
    env_file = ROOT / ".env"
    env_file.write_text("TURSO_URL=libsql://foo\nTURSO_TOKEN=bar\n", encoding="utf-8")
    try:
        # Reload run_app to pick up the file
        sys.path.insert(0, str(ROOT))
        if "run_app" in sys.modules:
            del sys.modules["run_app"]
        import run_app
        loaded = run_app._load_dotenv()
        assert loaded["TURSO_URL"] == "libsql://foo"
        assert loaded["TURSO_TOKEN"] == "bar"
    finally:
        if env_file.exists():
            env_file.unlink()


def test_load_env_skips_comments_and_blanks(tmp_path, monkeypatch):
    """Comments and blank lines are ignored."""
    monkeypatch.chdir(ROOT)
    env_file = ROOT / ".env"
    env_file.write_text(
        "# This is a comment\n"
        "\n"
        "TURSO_URL=libsql://x\n"
        "  # indented comment\n"
        "TURSO_TOKEN=secret\n",
        encoding="utf-8",
    )
    try:
        sys.path.insert(0, str(ROOT))
        if "run_app" in sys.modules:
            del sys.modules["run_app"]
        import run_app
        loaded = run_app._load_dotenv()
        assert loaded == {"TURSO_URL": "libsql://x", "TURSO_TOKEN": "secret"}
    finally:
        if env_file.exists():
            env_file.unlink()


def test_load_env_quoted_values(tmp_path, monkeypatch):
    """Quoted values have quotes stripped."""
    monkeypatch.chdir(ROOT)
    env_file = ROOT / ".env"
    env_file.write_text(
        'TURSO_URL="libsql://my-db"\n'
        "TURSO_TOKEN='abc def'\n",
        encoding="utf-8",
    )
    try:
        sys.path.insert(0, str(ROOT))
        if "run_app" in sys.modules:
            del sys.modules["run_app"]
        import run_app
        loaded = run_app._load_dotenv()
        assert loaded["TURSO_URL"] == "libsql://my-db"
        assert loaded["TURSO_TOKEN"] == "abc def"
    finally:
        if env_file.exists():
            env_file.unlink()


# ──────────────────────────────────────────────────────────────────────────────
# Setup script subprocess tests
# ──────────────────────────────────────────────────────────────────────────────

def test_setup_url_validation_rejects_invalid():
    """URLs that don't start with libsql:// or https:// are rejected."""
    result = _run_setup(["--url", "ftp://bad", "--token", "x"])
    # In non-interactive mode with bad URL, the script should fail
    # (we feed in token non-interactively)
    assert result.returncode != 0
    assert "Invalid URL" in result.stdout


def test_setup_with_missing_token_fails():
    """If --token not provided and not interactive, fails."""
    result = _run_setup(["--url", "libsql://foo", "--token", ""])
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "Token is required" in output


def test_verify_command_without_env_fails(tmp_path, monkeypatch):
    """--verify with no .env exits with error."""
    monkeypatch.chdir(tmp_path)
    env_file = ROOT / ".env"
    existed = env_file.exists()
    if existed:
        original = env_file.read_text()
        env_file.unlink()
    try:
        result = _run_setup(["--verify"])
        assert result.returncode != 0
        output = result.stdout + result.stderr
        assert "No Turso credentials" in output
    finally:
        if existed:
            env_file.write_text(original, encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
# Mocked full flow
# ──────────────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────────
# Unit tests of internal helpers (no subprocess)
# ──────────────────────────────────────────────────────────────────────────────

def test_save_env_writes_restrictive_permissions(tmp_path, monkeypatch):
    """On POSIX, .env should be chmod 600."""
    if sys.platform == "win32":
        pytest.skip("POSIX-only test")
    monkeypatch.chdir(tmp_path)
    sys.path.insert(0, str(SCRIPTS))
    if "setup_turso" in sys.modules:
        del sys.modules["setup_turso"]
    import setup_turso
    setup_turso._save_env({"TURSO_URL": "x", "TURSO_TOKEN": "y"})
    assert setup_turso.ENV_FILE.exists()
    mode = stat.S_IMODE(os.stat(setup_turso.ENV_FILE).st_mode)
    assert mode == 0o600
    setup_turso.ENV_FILE.unlink()


def test_write_env_example_creates_template(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sys.path.insert(0, str(SCRIPTS))
    if "setup_turso" in sys.modules:
        del sys.modules["setup_turso"]
    import setup_turso
    if setup_turso.ENV_EXAMPLE.exists():
        setup_turso.ENV_EXAMPLE.unlink()
    setup_turso._write_env_example()
    assert setup_turso.ENV_EXAMPLE.exists()
    content = setup_turso.ENV_EXAMPLE.read_text()
    assert "TURSO_URL" in content
    assert "TURSO_TOKEN" in content
    assert "turso.tech" in content
    setup_turso.ENV_EXAMPLE.unlink()


def test_ensure_gitignore_adds_env(tmp_path, monkeypatch):
    """If .env is not in .gitignore, _ensure_gitignore adds it."""
    monkeypatch.chdir(tmp_path)
    sys.path.insert(0, str(SCRIPTS))
    if "setup_turso" in sys.modules:
        del sys.modules["setup_turso"]
    import setup_turso
    # Force-replace .gitignore with a clean one
    original = setup_turso.GITIGNORE.read_text() if setup_turso.GITIGNORE.exists() else None
    setup_turso.GITIGNORE.write_text("# existing content\n", encoding="utf-8")
    try:
        setup_turso._ensure_gitignore()
        content = setup_turso.GITIGNORE.read_text()
        assert ".env" in content
    finally:
        # Restore
        if original is not None:
            setup_turso.GITIGNORE.write_text(original, encoding="utf-8")
        else:
            setup_turso.GITIGNORE.unlink(missing_ok=True)


def test_test_connection_with_mocked_libsql(monkeypatch):
    """_test_connection returns True when the fake client says OK."""
    sys.path.insert(0, str(SCRIPTS))
    if "setup_turso" in sys.modules:
        del sys.modules["setup_turso"]
    import setup_turso

    fake = types.ModuleType("libsql_client")
    fake.create_client = lambda *args, **kwargs: _FakeLibsqlClient(
        args[0] if args else kwargs.get("url", ""),
        args[1] if len(args) > 1 else kwargs.get("auth_token", ""),
    )
    monkeypatch.setitem(sys.modules, "libsql_client", fake)

    # Capture print output to avoid noise
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = setup_turso._test_connection("libsql://x", "t")
    assert result is True


def test_test_connection_returns_false_on_error(monkeypatch):
    """If the libsql client raises, _test_connection returns False."""
    sys.path.insert(0, str(SCRIPTS))
    if "setup_turso" in sys.modules:
        del sys.modules["setup_turso"]
    import setup_turso

    fake = types.ModuleType("libsql_client")
    def boom(*args, **kwargs):
        raise RuntimeError("connection refused")
    fake.create_client = boom
    monkeypatch.setitem(sys.modules, "libsql_client", fake)

    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = setup_turso._test_connection("libsql://x", "t")
    assert result is False


def test_apply_schema_calls_execute(monkeypatch):
    """_apply_schema runs each statement in cloud_schema.sql."""
    sys.path.insert(0, str(SCRIPTS))
    if "setup_turso" in sys.modules:
        del sys.modules["setup_turso"]
    import setup_turso

    captured = []

    class _CaptureClient:
        def __init__(self, *args, **kwargs):
            pass
        def execute(self, sql):
            captured.append(sql)
            return _FakeResult([])

    fake = types.ModuleType("libsql_client")
    fake.create_client = lambda *args, **kwargs: _CaptureClient()
    monkeypatch.setitem(sys.modules, "libsql_client", fake)

    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = setup_turso._apply_schema("libsql://x", "t")
    assert result is True
    # Each non-empty statement in cloud_schema.sql should have been executed
    assert len(captured) > 5
    assert any("CREATE TABLE" in sql for sql in captured)
    assert any("CREATE INDEX" in sql for sql in captured)


def test_verify_schema_reports_all_tables(monkeypatch):
    """_verify_schema returns True when all expected tables exist."""
    sys.path.insert(0, str(SCRIPTS))
    if "setup_turso" in sys.modules:
        del sys.modules["setup_turso"]
    import setup_turso

    fake_client = _FakeLibsqlClient("x", "t")
    for t in ["users", "sessions", "stints", "laps", "pit_stops", "community_meta"]:
        fake_client._tables.add(t)

    fake = types.ModuleType("libsql_client")
    fake.create_client = lambda *args, **kwargs: fake_client
    monkeypatch.setitem(sys.modules, "libsql_client", fake)

    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = setup_turso._verify_schema("x", "t")
    assert result is True
    assert "All expected tables present" in buf.getvalue()


def test_verify_schema_reports_missing(monkeypatch):
    """_verify_schema returns False when a table is missing."""
    sys.path.insert(0, str(SCRIPTS))
    if "setup_turso" in sys.modules:
        del sys.modules["setup_turso"]
    import setup_turso

    fake_client = _FakeLibsqlClient("x", "t")
    # Only 2 tables — missing most
    fake_client._tables.update({"users", "sessions"})

    fake = types.ModuleType("libsql_client")
    fake.create_client = lambda *args, **kwargs: fake_client
    monkeypatch.setitem(sys.modules, "libsql_client", fake)

    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = setup_turso._verify_schema("x", "t")
    assert result is False
    assert "Missing tables" in buf.getvalue()
