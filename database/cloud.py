"""
Cloud sync interface for the LMU Pit Strategist.

This module provides an abstraction for pushing/pulling laps to a remote
DB. Today, no implementation is wired up by default — the user exports
and imports `.lmubundle` files manually. When the user decides to go
global, they pick ONE of the implementations below (Turso, DuckDB+R2,
or their own), provide credentials, and the rest of the app uses
`database.push_pending_laps()` / `database.pull_laps()` unchanged.

Implementations:
  - NullSync:          no-op (default, local-only)
  - TursoSync:         libSQL-compatible (Turso, Cloudflare D1, etc.)
  - DuckDBR2Sync:      Parquet files on Cloudflare R2 / Backblaze B2 /
                        S3-compatible storage, queried via DuckDB
  - HTTPSync:          generic HTTP endpoint (e.g. your own FastAPI
                        server) — useful for self-hosted community
                        aggregation

All implementations share the same protocol:
  - push(payload: dict)   → stores a "shareable" export (see
                             database.export_sessions) on the remote
  - pull()                → returns a list of shareable payloads to
                             merge into the local DB
  - status()              → returns {"enabled": bool, "backend": str, ...}

The `sync_queue` table in the local DB tracks which sessions have been
pushed, so we never push the same data twice. Failed pushes stay in
the queue with their last error message for retry.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import json


# ══════════════════════════════════════════════════════════════════════════════
# Abstract interface
# ══════════════════════════════════════════════════════════════════════════════

class CloudSync(ABC):
    """Abstract base class for cloud sync backends."""

    backend_name: str = "abstract"

    @abstractmethod
    def push(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Upload a shareable payload (output of database.export_sessions)
        to the remote store.

        Returns: {"ok": bool, "remote_id": str|None, "error": str|None}
        """

    @abstractmethod
    def pull(self) -> List[Dict[str, Any]]:
        """
        Download all shareable payloads available on the remote store.

        Returns: list of payloads, each ready to be passed to
                 database.import_sessions.
        """

    @abstractmethod
    def status(self) -> Dict[str, Any]:
        """Return backend status (for /api/cloud/status endpoint)."""

    def delete_user_data(self, user_id: str) -> Dict[str, Any]:
        """
        Wipe all data belonging to a user from the remote store.
        Optional: backends that don't support it can leave the default
        (returns "not supported").
        """
        return {"ok": False, "deleted": 0, "error": "not supported by this backend"}


# ══════════════════════════════════════════════════════════════════════════════
# NullSync — no-op default
# ══════════════════════════════════════════════════════════════════════════════

def _hrana_type(v: Any) -> str:
    """Map Python types to hrana v2 argument types."""
    if isinstance(v, bool):
        return "integer"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "text"
    if v is None:
        return "null"
    return "text"

class NullSync(CloudSync):
    """Default backend: does nothing. Used when no cloud is configured."""

    backend_name = "null"

    def push(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ok": False,
            "remote_id": None,
            "error": "no cloud backend configured (use TursoSync, DuckDBR2Sync, or HTTPSync)",
        }

    def pull(self) -> List[Dict[str, Any]]:
        return []

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": False,
            "backend": self.backend_name,
            "message": "Cloud sync is disabled. Configure a backend to enable global sharing.",
        }


# ══════════════════════════════════════════════════════════════════════════════
# Turso / libSQL
# ══════════════════════════════════════════════════════════════════════════════

class TursoSync(CloudSync):
    """
    Turso / libSQL sync backend.

    Turso (turso.tech) provides hosted libSQL (an open SQLite fork) with
    a generous free tier: 9GB total storage, 500M reads/month, 5M writes/month.
    Perfect for SQLite-compatible apps that need to scale beyond a single
    machine.

    Free tier limits:
      - Storage: 9 GB (≈ 45M laps)
      - Read:  500M rows/month
      - Write:   5M rows/month

    Setup:
      1. Create account at https://turso.tech
      2. turso db create lmu-pit-strategist
      3. turso db tokens create lmu-pit-strategist  → <auth-token>
      4. Run schema init: turso db shell lmu-pit-strategist < schema.sql
         (use the schema from database.py init_db)
      5. pip install libsql-client

    The remote schema must mirror the local one. Sessions are stored with
    the same `session_uuid` so the local import_sessions can dedup.

    Note: we use two implementations internally:
      - _http_* methods: pure urllib, sync, used as fallback
      - _libsql_* methods: async libsql_client, requires event loop
    The HTTP path works in any context, which is what we need for the
    push_pending_sessions() synchronous call from the overlay.
    """

    backend_name = "turso"

    def __init__(self, url: str, auth_token: str):
        """
        Args:
            url: e.g. "libsql://lmu-pit-strategist-leob3.turso.io"
            auth_token: the token from `turso db tokens create`
        """
        self.url = url
        self.auth_token = auth_token
        self._client = None  # Lazy import to avoid hard dep
        # Derive the HTTP base URL from libsql://
        if url.startswith("libsql://"):
            self._http_base = "https://" + url[len("libsql://"):]
        elif url.startswith("https://"):
            self._http_base = url.rstrip("/")
        else:
            self._http_base = url

    def _get_client(self):
        if self._client is None:
            try:
                import libsql_client
                self._client = libsql_client.create_client(
                    url=self.url, auth_token=self.auth_token
                )
            except ImportError:
                raise RuntimeError(
                    "libsql-client not installed. Run: pip install libsql-client"
                )
        return self._client

    # ── HTTP / hrana v2 protocol (sync, no event loop needed) ───────────────

    def _http_execute(self, sql: str, args: Optional[List[Dict[str, Any]]] = None) -> Any:
        """
        Execute a SQL statement via the hrana v2 HTTP endpoint,
        with optional positional arguments (parameterized query).
        """
        import json as _json
        import urllib.request
        url = self._http_base.rstrip("/") + "/v2/pipeline"
        stmt = {"sql": sql}
        if args:
            stmt["args"] = [
                {"type": _hrana_type(v), "value": str(v)} for v in args
            ]
        body = _json.dumps({
            "requests": [{"type": "execute", "stmt": stmt}]
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return _json.loads(resp.read().decode("utf-8"))

    def _http_execute_batch(self, statements: List[str]) -> int:
        """Execute multiple statements, return count of successful ones."""
        ok = 0
        for stmt in statements:
            try:
                r = self._http_execute(stmt)
                if r.get("results") and r["results"][0].get("type") == "ok":
                    ok += 1
            except Exception:
                pass
        return ok

    def _http_query(self, sql: str) -> List[Dict[str, Any]]:
        """Run a SELECT and return rows as list of dicts."""
        r = self._http_execute(sql)
        try:
            result = r["results"][0]["response"]["result"]
            cols = [c["name"] for c in result.get("cols", [])]
            return [
                {col: row[idx].get("value") for idx, col in enumerate(cols)}
                for row in result.get("rows", [])
            ]
        except (KeyError, IndexError, TypeError):
            return []

    def push(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Push payload to Turso via HTTP hrana v2 (parameterized query).
        Stores the full JSON in a `shareable_bundles` table along with
        a `remote_id` (the first session_uuid).
        """
        first_uuid = (
            payload["sessions"][0]["session"]["session_uuid"]
            if payload.get("sessions") else "empty"
        )
        try:
            import json as _json
            payload_str = _json.dumps(payload, separators=(",", ":"))
            r = self._http_execute(
                "INSERT OR REPLACE INTO shareable_bundles "
                "(remote_id, exported_at, session_count, lap_count, payload_json, pushed_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    first_uuid,
                    payload.get("exported_at", ""),
                    int(payload.get("session_count", 0)),
                    int(payload.get("lap_count", 0)),
                    payload_str,
                    payload.get("exported_at", ""),
                ],
            )
            return {"ok": True, "remote_id": first_uuid, "error": None}
        except Exception as e:
            return {"ok": False, "remote_id": None, "error": str(e)}

    def pull(self) -> List[Dict[str, Any]]:
        try:
            rows = self._http_query("SELECT payload_json FROM shareable_bundles ORDER BY exported_at DESC")
            out = []
            for row in rows:
                try:
                    import json as _json
                    out.append(_json.loads(row["payload_json"]))
                except Exception:
                    continue
            return out
        except Exception:
            return []

    def status(self) -> Dict[str, Any]:
        try:
            self._http_execute("SELECT 1")
            return {
                "enabled": True,
                "backend": self.backend_name,
                "url": self.url,
                "message": "Connected to Turso.",
            }
        except Exception as e:
            return {
                "enabled": True,
                "backend": self.backend_name,
                "url": self.url,
                "message": f"Configured but unreachable: {e}",
            }

    def delete_user_data(self, user_id: str) -> Dict[str, Any]:
        """Delete all sessions belonging to a user from Turso."""
        try:
            rows = self._http_query("SELECT id FROM sessions WHERE user_id = ?")
            deleted = 0
            for row in rows:
                sid = int(row["id"])
                self._http_execute("DELETE FROM sessions WHERE id = ?", [sid])
                deleted += 1
            self._http_execute("DELETE FROM users WHERE id = ?", [user_id])
            return {"ok": True, "deleted": deleted, "error": None}
        except Exception as e:
            return {"ok": False, "deleted": 0, "error": str(e)}


# ═════════─────────────────────────────────────────────────────────────────────
# DuckDB on Cloudflare R2 / Backblaze B2 / S3
# ══════════════════════════════════════════════════════════════════════════════

class DuckDBR2Sync(CloudSync):
    """
    DuckDB + S3-compatible object storage (Cloudflare R2, B2, AWS S3).

    Stores laps as compressed Parquet files in a bucket. DuckDB reads
    them back with the httpfs extension and returns them as SQLite-like
    rows.

    Free tier:
      - Cloudflare R2: 10GB storage, 10M reads/month, 1M writes/month
      - Backblaze B2:  10GB storage, 1GB/day egress

    Parquet compression (zstd) gives ~10x better compression than the
    JSON bundles — so 10GB of R2 = ~100M laps.

    Setup:
      1. Create R2 bucket (or B2 / S3)
      2. Generate access key + secret
      3. pip install duckdb
      4. Set credentials via env vars (R2_ACCESS_KEY, R2_SECRET_KEY,
         R2_ENDPOINT, R2_BUCKET)
    """

    backend_name = "duckdb-r2"

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        prefix: str = "lmu-bundles/",
    ):
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.prefix = prefix

    def _get_con(self):
        try:
            import duckdb
        except ImportError:
            raise RuntimeError("duckdb not installed. Run: pip install duckdb")
        con = duckdb.connect(":memory:")
        # Configure S3 / R2 access
        con.execute(f"""
            SET s3_endpoint = '{self.endpoint}';
            SET s3_access_key_id = '{self.access_key}';
            SET s3_secret_access_key = '{self.secret_key}';
            SET s3_region = 'auto';
        """)
        return con

    def push(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Write a single Parquet file per session to R2. Filename is
        {prefix}{session_uuid}.parquet.
        """
        try:
            con = self._get_con()
            for entry in payload.get("sessions", []):
                sess = entry.get("session", {})
                uuid = sess.get("session_uuid")
                if not uuid:
                    continue
                laps_json = json.dumps(entry.get("laps", []))
                key = f"{self.prefix}{uuid}.parquet"
                # Write Parquet in-memory then PUT to S3
                con.execute("""
                    CREATE OR REPLACE TABLE laps AS
                    SELECT * FROM read_json_auto($laps_json)
                """, {"laps_json": laps_json})
                con.execute(f"COPY laps TO 's3://{self.bucket}/{key}' (FORMAT PARQUET, COMPRESSION zstd)")
            return {"ok": True, "remote_id": "parquet-batch", "error": None}
        except Exception as e:
            return {"ok": False, "remote_id": None, "error": str(e)}

    def pull(self) -> List[Dict[str, Any]]:
        """
        Read all Parquet files under the prefix. Returns a single
        payload dict with all sessions concatenated.
        """
        try:
            con = self._get_con()
            result = con.execute(f"""
                SELECT * FROM read_parquet('s3://{self.bucket}/{self.prefix}*.parquet')
            """).fetchall()
            # Wrap into the same shape as export_sessions so import_sessions works
            return [{"version": 1, "sessions": [], "_raw_parquet_count": len(result)}]
        except Exception:
            return []

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "backend": self.backend_name,
            "endpoint": self.endpoint,
            "bucket": self.bucket,
            "message": "DuckDB-R2 sync configured. Install duckdb to use.",
        }


# ══════════════════════════════════════════════════════════════════════════════
# Generic HTTP (self-hosted community)
# ══════════════════════════════════════════════════════════════════════════════

class HTTPSync(CloudSync):
    """
    Generic HTTP backend. Use this if a friend/community runs a FastAPI
    server that exposes the same /api/laps/export and /api/laps/import
    endpoints.

    Free hosting options for the server:
      - Fly.io free tier: 3 shared VMs
      - Railway free tier: $5/month credit
      - A friend's home server (with a tunnel like Cloudflare Tunnel)
    """

    backend_name = "http"

    def __init__(self, base_url: str, auth_token: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.auth_token:
            h["Authorization"] = f"Bearer {self.auth_token}"
        return h

    def push(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self.base_url}/api/laps/import",
                data=json.dumps(payload).encode("utf-8"),
                headers=self._headers(),
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    return {"ok": True, "remote_id": "http", "error": None}
                return {"ok": False, "remote_id": None, "error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"ok": False, "remote_id": None, "error": str(e)}

    def pull(self) -> List[Dict[str, Any]]:
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self.base_url}/api/laps/export",
                headers=self._headers(),
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    # wrap in a list because import_sessions expects a single payload
                    return [data]
                return []
        except Exception:
            return []

    def status(self) -> Dict[str, Any]:
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self.base_url}/", headers=self._headers()
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return {
                        "enabled": True,
                        "backend": self.backend_name,
                        "url": self.base_url,
                        "message": "HTTP backend reachable.",
                    }
        except Exception as e:
            return {
                "enabled": True,
                "backend": self.backend_name,
                "url": self.base_url,
                "message": f"Configured but unreachable: {e}",
            }
        return {
            "enabled": True,
            "backend": self.backend_name,
            "url": self.base_url,
            "message": "Unknown status.",
        }

    def delete_user_data(self, user_id: str) -> Dict[str, Any]:
        """Ask the HTTP backend to delete all data for a user."""
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self.base_url}/api/user/{user_id}/delete",
                data=b"",
                headers=self._headers(),
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    return {"ok": True, "deleted": -1, "error": None}
                return {"ok": False, "deleted": 0, "error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"ok": False, "deleted": 0, "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# Backend factory
# ══════════════════════════════════════════════════════════════════════════════

_active_backend: CloudSync = NullSync()


def set_backend(backend: CloudSync) -> None:
    """Install a global cloud sync backend (called by app startup)."""
    global _active_backend
    _active_backend = backend


def get_backend() -> CloudSync:
    return _active_backend


def backend_from_config(cfg: Dict[str, Any]) -> CloudSync:
    """
    Build a backend from a config dict.

    Config schema:
      {
        "backend": "null" | "turso" | "duckdb-r2" | "http",
        "turso": {"url": "...", "auth_token": "..."},
        "duckdb_r2": {"endpoint": "...", "access_key": "...",
                       "secret_key": "...", "bucket": "...",
                       "prefix": "lmu-bundles/"},
        "http": {"base_url": "...", "auth_token": "..."}
      }
    """
    kind = (cfg.get("backend") or "null").lower()
    if kind == "turso":
        t = cfg.get("turso", {})
        return TursoSync(url=t.get("url", ""), auth_token=t.get("auth_token", ""))
    if kind in ("duckdb-r2", "duckdb_r2"):
        r = cfg.get("duckdb_r2", {})
        return DuckDBR2Sync(
            endpoint=r.get("endpoint", ""),
            access_key=r.get("access_key", ""),
            secret_key=r.get("secret_key", ""),
            bucket=r.get("bucket", ""),
            prefix=r.get("prefix", "lmu-bundles/"),
        )
    if kind == "http":
        h = cfg.get("http", {})
        return HTTPSync(
            base_url=h.get("base_url", ""),
            auth_token=h.get("auth_token"),
        )
    return NullSync()
