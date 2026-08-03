"""Shared pytest fixtures for LMU Pit Strategist.

Isolates the auth users DB from the real project DB: every test gets a
fresh temp DB for users, so repeated runs never collide on UNIQUE email
constraints and session state never leaks between tests (previously test
users leaked into the real ``lmu_pit_strategist.db``).
"""
import pytest


@pytest.fixture(autouse=True)
def _isolated_auth_db(tmp_path, monkeypatch):
    """Point the auth users DB at a fresh temp file for each test."""
    monkeypatch.setenv("LMU_AUTH_DB_PATH", str(tmp_path / "test_auth.db"))
    yield
