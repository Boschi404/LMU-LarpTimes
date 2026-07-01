import sqlite3
import os
import uuid
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import paths

DEFAULT_DB_PATH = paths.data_path("lmu_pit_strategist.db")


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Get a database connection and enable WAL mode.
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """
    Initialize database tables.
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Create sessions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_uuid TEXT NOT NULL,
            track TEXT NOT NULL,
            layout TEXT NOT NULL,
            car TEXT NOT NULL,
            session_type TEXT NOT NULL,
            started_at TEXT NOT NULL
        )
    """)

    # Create stints table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            stint_number INTEGER NOT NULL,
            compound_front TEXT NOT NULL,
            compound_rear TEXT NOT NULL,
            start_lap INTEGER NOT NULL,
            end_lap INTEGER,
            start_fuel_l REAL NOT NULL,
            end_fuel_l REAL,
            FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
        )
    """)

    # Create laps table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS laps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            stint_id INTEGER,
            lap_number INTEGER NOT NULL,
            lap_time REAL NOT NULL,
            sector_1 REAL NOT NULL,
            sector_2 REAL NOT NULL,
            sector_3 REAL NOT NULL,
            is_valid_lap INTEGER NOT NULL,
            is_pit_in_lap INTEGER NOT NULL,
            is_pit_out_lap INTEGER NOT NULL,
            compound_front TEXT NOT NULL,
            compound_rear TEXT NOT NULL,
            tyre_age_laps INTEGER NOT NULL,
            wear_pct_start_FL REAL NOT NULL,
            wear_pct_start_FR REAL NOT NULL,
            wear_pct_start_RL REAL NOT NULL,
            wear_pct_start_RR REAL NOT NULL,
            wear_pct_end_FL REAL NOT NULL,
            wear_pct_end_FR REAL NOT NULL,
            wear_pct_end_RL REAL NOT NULL,
            wear_pct_end_RR REAL NOT NULL,
            fuel_start_l REAL NOT NULL,
            fuel_end_l REAL NOT NULL,
            fuel_used_l REAL NOT NULL,
            track_temp REAL NOT NULL,
            ambient_temp REAL NOT NULL,
            weather_state TEXT NOT NULL,
            rain_intensity REAL NOT NULL,
            completed_at TEXT NOT NULL,
            anomaly_flag INTEGER NOT NULL DEFAULT 0,
            anomaly_reason TEXT,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE,
            FOREIGN KEY (stint_id) REFERENCES stints (id)
        )
    """)

    # Create pit_stops table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pit_stops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            lap_number INTEGER NOT NULL,
            pit_loss REAL NOT NULL,
            in_lap_number INTEGER NOT NULL,
            out_lap_number INTEGER NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
        )
    """)

    # Create sync_queue table (tracks which sessions have been pushed
    # to the cloud backend, with last error / last attempt for retries)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_uuid TEXT NOT NULL UNIQUE,
            backend TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            last_error TEXT,
            last_attempt_at TEXT,
            pushed_at TEXT,
            payload_size INTEGER
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sync_queue_status
        ON sync_queue(status)
    """)

    # Create db_users table (the local identity for the community DB)
    # Only ONE row allowed (SINGLE USER per local install by design).
    # If user opts in, this row gets a user_id and display_name.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS db_users (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            user_id TEXT UNIQUE,
            display_name TEXT,
            opt_in_global INTEGER NOT NULL DEFAULT 0,
            created_at TEXT,
            opt_in_at TEXT,
            opt_out_at TEXT
        )
    """)
    # Ensure the singleton row exists
    cursor.execute("""
        INSERT OR IGNORE INTO db_users (id, opt_in_global) VALUES (1, 0)
    """)

    conn.commit()
    _migrate_db(conn, cursor)
    # Ensure telemetry samples table exists
    _init_telemetry_samples_table_inner(conn, cursor)
    conn.close()


def _migrate_db(conn, cursor) -> None:
    try:
        cursor.execute("PRAGMA table_info(sessions)")
        cols = [r[1] for r in cursor.fetchall()]
        if "session_uuid" not in cols:
            cursor.execute("ALTER TABLE sessions ADD COLUMN session_uuid TEXT NOT NULL DEFAULT ''")
        if "completed_at" not in cols:
            cursor.execute("ALTER TABLE sessions ADD COLUMN completed_at TEXT NOT NULL DEFAULT ''")
        if "owner_email" not in cols:
            cursor.execute("ALTER TABLE sessions ADD COLUMN owner_email TEXT")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_owner_email ON sessions(owner_email)")
    except Exception:
        pass
    try:
        cursor.execute("PRAGMA table_info(laps)")
        cols = [r[1] for r in cursor.fetchall()]
        if "stint_id" not in cols:
            cursor.execute("ALTER TABLE laps ADD COLUMN stint_id INTEGER")
        if "completed_at" not in cols:
            cursor.execute("ALTER TABLE laps ADD COLUMN completed_at TEXT NOT NULL DEFAULT ''")
        if "owner_email" not in cols:
            cursor.execute("ALTER TABLE laps ADD COLUMN owner_email TEXT")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_laps_owner_email ON laps(owner_email)")
    except Exception:
        pass
    # sync_queue (created in init_db, but we also ensure it exists for
    # pre-existing DBs that were initialised before this version)
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_uuid TEXT NOT NULL UNIQUE,
                backend TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                last_error TEXT,
                last_attempt_at TEXT,
                pushed_at TEXT,
                payload_size INTEGER
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sync_queue_status
            ON sync_queue(status)
        """)
    except Exception:
        pass
    # owner_email (S-1): nullable, NULL = anonymous
    try:
        cursor.execute("PRAGMA table_info(sessions)")
        cols = [r[1] for r in cursor.fetchall()]
        if "owner_email" not in cols:
            cursor.execute("ALTER TABLE sessions ADD COLUMN owner_email TEXT")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_owner_email ON sessions(owner_email)")
    except Exception:
        pass
    # db_users.email (S-2)
    try:
        cursor.execute("PRAGMA table_info(db_users)")
        cols = [r[1] for r in cursor.fetchall()]
        if "email" not in cols:
            cursor.execute("ALTER TABLE db_users ADD COLUMN email TEXT")
    except Exception:
        pass
    # Make stint_number nullable if it exists (legacy compatibility)
    try:
        cursor.execute("PRAGMA table_info(laps)")
        for r in cursor.fetchall():
            if r["name"] == "stint_number" and r["notnull"] == 1:
                cursor.execute("ALTER TABLE laps RENAME TO laps_old")
                cursor.execute("""
                    CREATE TABLE laps_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id INTEGER NOT NULL,
                        stint_id INTEGER,
                        lap_number INTEGER NOT NULL,
                        lap_time REAL NOT NULL,
                        sector_1 REAL NOT NULL,
                        sector_2 REAL NOT NULL,
                        sector_3 REAL NOT NULL,
                        is_valid_lap INTEGER NOT NULL,
                        is_pit_in_lap INTEGER NOT NULL,
                        is_pit_out_lap INTEGER NOT NULL,
                        compound_front TEXT NOT NULL,
                        compound_rear TEXT NOT NULL,
                        tyre_age_laps INTEGER NOT NULL,
                        wear_pct_start_FL REAL NOT NULL,
                        wear_pct_start_FR REAL NOT NULL,
                        wear_pct_start_RL REAL NOT NULL,
                        wear_pct_start_RR REAL NOT NULL,
                        wear_pct_end_FL REAL NOT NULL,
                        wear_pct_end_FR REAL NOT NULL,
                        wear_pct_end_RL REAL NOT NULL,
                        wear_pct_end_RR REAL NOT NULL,
                        fuel_start_l REAL NOT NULL,
                        fuel_end_l REAL NOT NULL,
                        fuel_used_l REAL NOT NULL,
                        track_temp REAL NOT NULL,
                        ambient_temp REAL NOT NULL,
                        weather_state TEXT NOT NULL,
                        rain_intensity REAL NOT NULL,
                        completed_at TEXT NOT NULL,
                        anomaly_flag INTEGER NOT NULL DEFAULT 0,
                        anomaly_reason TEXT,
                        is_deleted INTEGER NOT NULL DEFAULT 0,
                        owner_email TEXT,
                        stint_number INTEGER
                    )
                """)
                cursor.execute("INSERT INTO laps_new SELECT * FROM laps_old")
                cursor.execute("DROP TABLE laps_old")
                cursor.execute("ALTER TABLE laps_new RENAME TO laps")
                print("[Migration] stint_number made nullable")
    except Exception:
        pass
    conn.commit()


def create_session(
    track: str,
    layout: str,
    car: str,
    session_type: str,
    started_at: Optional[str] = None,
    db_path: Optional[str] = None
) -> int:
    """
    Create a new driving session and return its id.
    """
    if started_at is None:
        started_at = datetime.now().isoformat()

    session_uuid = str(uuid.uuid4())
    # Auto-tag with the current owner_email (S-2)
    owner_email = get_owner_email(db_path)

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO sessions (session_uuid, track, layout, car, session_type, started_at, owner_email)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (session_uuid, track, layout, car, session_type, started_at, owner_email)
    )
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id


def create_stint(
    session_id: int,
    stint_number: int,
    compound_front: str,
    compound_rear: str,
    start_lap: int,
    start_fuel_l: float,
    db_path: Optional[str] = None
) -> int:
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO stints (session_id, stint_number, compound_front, compound_rear, start_lap, start_fuel_l)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session_id, stint_number, compound_front, compound_rear, start_lap, start_fuel_l)
    )
    stint_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return stint_id


def update_stint_end(
    stint_id: int,
    end_lap: int,
    end_fuel_l: float,
    db_path: Optional[str] = None
) -> None:
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE stints SET end_lap = ?, end_fuel_l = ? WHERE id = ?
        """,
        (end_lap, end_fuel_l, stint_id)
    )
    conn.commit()
    conn.close()


def get_active_stint(
    session_id: int,
    db_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM stints WHERE session_id = ? AND end_lap IS NULL ORDER BY stint_number DESC LIMIT 1
        """,
        (session_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def insert_lap(lap_data: Dict[str, Any], db_path: Optional[str] = None) -> int:
    """
    Insert a lap record into the database. Adapts to existing schema.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(laps)")
    existing_cols = {r[1] for r in cursor.fetchall()}

    # Map new field names to old column names if needed
    has_stint_id = "stint_id" in existing_cols
    has_stint_number = "stint_number" in existing_cols
    field_map = {
        "session_id": "session_id",
        "stint_id": "stint_id" if has_stint_id else ("stint_number" if has_stint_number else None),
        "lap_number": "lap_number",
        "lap_time": "lap_time",
        "sector_1": "sector_1",
        "sector_2": "sector_2",
        "sector_3": "sector_3",
        "is_valid_lap": "is_valid_lap",
        "is_pit_in_lap": "is_pit_in_lap",
        "is_pit_out_lap": "is_pit_out_lap",
        "compound_front": "compound_front",
        "compound_rear": "compound_rear",
        "tyre_age_laps": "tyre_age_laps",
        "wear_pct_start_FL": "wear_pct_start_FL",
        "wear_pct_start_FR": "wear_pct_start_FR",
        "wear_pct_start_RL": "wear_pct_start_RL",
        "wear_pct_start_RR": "wear_pct_start_RR",
        "wear_pct_end_FL": "wear_pct_end_FL",
        "wear_pct_end_FR": "wear_pct_end_FR",
        "wear_pct_end_RL": "wear_pct_end_RL",
        "wear_pct_end_RR": "wear_pct_end_RR",
        "fuel_start_l": "fuel_start_l",
        "fuel_end_l": "fuel_end_l",
        "fuel_used_l": "fuel_used_l",
        "track_temp": "track_temp",
        "ambient_temp": "ambient_temp",
        "weather_state": "weather_state",
        "rain_intensity": "rain_intensity",
        "completed_at": "completed_at",
        "owner_email": "owner_email",  # S-2
        "anomaly_flag": "anomaly_flag",  # engine core
        "anomaly_reason": "anomaly_reason",
    }

    # Filter to only columns that exist in the table
    fields = []
    values = []
    for new_name, col_name in field_map.items():
        if col_name in existing_cols:
            fields.append(col_name)
            val = lap_data.get(new_name)
            if col_name == "stint_number" and val is None:
                val = lap_data.get("stint_id", 1) or 1
            if new_name == "completed_at" and val is None:
                val = ""
            if col_name == "owner_email" and val is None:
                # Auto-tag: inherit from current owner
                val = get_owner_email(db_path)
            if col_name == "anomaly_flag" and val is None:
                val = 0
            if col_name == "anomaly_reason" and val is None:
                val = None
            values.append(val)

    # If both stint_id and stint_number exist, provide stint_number value
    if has_stint_id and has_stint_number and "stint_number" not in fields:
        st_id_val = lap_data.get("stint_id")
        if st_id_val is not None:
            fields.append("stint_number")
            values.append(st_id_val)

    placeholders = ", ".join(["?"] * len(fields))
    columns = ", ".join(fields)
    cursor.execute(f"INSERT INTO laps ({columns}) VALUES ({placeholders})", values)
    lap_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return lap_id


def update_lap_anomaly(
    lap_id: int,
    anomaly_flag: bool,
    anomaly_reason: Optional[str],
    db_path: Optional[str] = None
) -> None:
    """
    Update the anomaly status of a lap.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE laps
        SET anomaly_flag = ?, anomaly_reason = ?
        WHERE id = ?
        """,
        (1 if anomaly_flag else 0, anomaly_reason, lap_id)
    )
    conn.commit()
    conn.close()


def soft_delete_lap(lap_id: int, is_deleted: bool = True, db_path: Optional[str] = None) -> None:
    """
    Toggle soft delete on a lap.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE laps
        SET is_deleted = ?
        WHERE id = ?
        """,
        (1 if is_deleted else 0, lap_id)
    )
    conn.commit()
    conn.close()


def insert_pit_stop(
    session_id: int,
    lap_number: int,
    pit_loss: float,
    in_lap_number: int,
    out_lap_number: int,
    db_path: Optional[str] = None
) -> int:
    """
    Insert a recorded pit stop.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO pit_stops (session_id, lap_number, pit_loss, in_lap_number, out_lap_number)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, lap_number, pit_loss, in_lap_number, out_lap_number)
    )
    pit_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return pit_id


def get_laps_for_analysis(
    car: str,
    track: str,
    compound_front: Optional[str] = None,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetch non-deleted, valid, non-anomalous laps for fitting models.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    query = """
        SELECT l.*, s.track, s.car
        FROM laps l
        JOIN sessions s ON l.session_id = s.id
        WHERE s.car = ? AND s.track = ?
          AND l.is_valid_lap = 1
          AND l.anomaly_flag = 0
          AND l.is_deleted = 0
          AND l.is_pit_in_lap = 0
          AND l.is_pit_out_lap = 0
    """
    params = [car, track]
    
    if compound_front:
        query += " AND l.compound_front = ?"
        params.append(compound_front)
        
    query += " ORDER BY l.id ASC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_all_laps_by_session(
    car: str,
    track: str,
    compound_front: Optional[str] = None,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetch all non-deleted, valid laps (including anomalous ones) to check anomaly status.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    query = """
        SELECT l.*, s.track, s.car
        FROM laps l
        JOIN sessions s ON l.session_id = s.id
        WHERE s.car = ? AND s.track = ?
          AND l.is_deleted = 0
    """
    params = [car, track]
    
    if compound_front:
        query += " AND l.compound_front = ?"
        params.append(compound_front)
        
    query += " ORDER BY l.id ASC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_all_sessions(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get all sessions from the database."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, session_uuid as session_id, track, layout, car, session_type, started_at, completed_at "
        "FROM sessions ORDER BY started_at DESC"
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_all_laps_for_archive(
    db_path: Optional[str] = None,
    include_deleted: bool = False
) -> List[Dict[str, Any]]:
    """
    Fetch all laps for the user interface archive table.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    query = """
        SELECT l.*, s.track, s.layout, s.car, s.session_type
        FROM laps l
        JOIN sessions s ON l.session_id = s.id
    """
    if not include_deleted:
        query += " WHERE l.is_deleted = 0"
        
    query += " ORDER BY l.id DESC"
    
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_pit_stops_loss_by_session(
    car: str,
    track: str,
    db_path: Optional[str] = None
) -> List[float]:
    """
    Fetch historical pit stop durations observed.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT p.pit_loss
        FROM pit_stops p
        JOIN sessions s ON p.session_id = s.id
        WHERE s.car = ? AND s.track = ?
        """,
        (car, track)
    )
    rows = cursor.fetchall()
    conn.close()
    return [row["pit_loss"] for row in rows]


def get_laps_chart_data(
    car: str,
    track: str,
    compound_front: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return structured data for the Chart.js lap-evolution chart.

    Returns:
    {
        "laps": [{lap_number, lap_time, stint_id, compound, is_pit_in/out,
                  fuel_start_l, tyre_age_laps, track_temp, weather_state}, ...],
        "pit_stops": [{lap_number, pit_loss}, ...],
        "stints": [{stint_number, compound_front, lap_start, lap_end}, ...],
        "sessions": [{session_uuid, session_type, car, track}, ...]
    }
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Laps (only active, valid, non-deleted)
    cursor.execute("""
        SELECT l.lap_number, l.lap_time, l.stint_id, l.compound_front,
               l.is_pit_in_lap, l.is_pit_out_lap, l.fuel_start_l,
               l.tyre_age_laps, l.track_temp, l.weather_state,
               l.session_id, l.anomaly_flag
        FROM laps l
        JOIN sessions s ON l.session_id = s.id
        WHERE s.car = ? AND s.track = ?
          AND (l.is_deleted = 0 OR l.is_deleted IS NULL)
        ORDER BY l.id
    """, (car, track))
    laps = [dict(r) for r in cursor.fetchall()]

    # Pit stops
    cursor.execute("""
        SELECT p.lap_number, p.pit_loss, p.in_lap_number, p.out_lap_number
        FROM pit_stops p
        JOIN sessions s ON p.session_id = s.id
        WHERE s.car = ? AND s.track = ?
        ORDER BY p.lap_number
    """, (car, track))
    pit_stops = [dict(r) for r in cursor.fetchall()]

    # Stints
    cursor.execute("""
        SELECT st.stint_number, st.compound_front, st.start_lap, st.end_lap
        FROM stints st
        JOIN sessions s ON st.session_id = s.id
        WHERE s.car = ? AND s.track = ?
        ORDER BY st.stint_number
    """, (car, track))
    stints = [dict(r) for r in cursor.fetchall()]

    # Active sessions
    cursor.execute("""
        SELECT s.session_uuid, s.session_type, s.car, s.track,
               s.started_at, s.owner_email
        FROM sessions s
        WHERE s.car = ? AND s.track = ?
        ORDER BY s.id DESC
    """, (car, track))
    sessions = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return {
        "laps": laps,
        "pit_stops": pit_stops,
        "stints": stints,
        "sessions": sessions,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Sharing — export/import of sessions + laps for the global DB pattern
#
# The user owns a local DB. To share their laps with the community (or to
# import laps from others), they call export_sessions() to dump a portable
# JSON-serialisable structure, and import_sessions() to load one back.
#
# Dedup is performed on (session_uuid, lap_number): the same lap imported
# twice will not be duplicated. Sessions and stints are matched by their
# unique UUIDs.
# ══════════════════════════════════════════════════════════════════════════════

SHAREABLE_LAP_COLUMNS = [
    "session_uuid", "stint_number",
    "lap_number", "lap_time", "sector_1", "sector_2", "sector_3",
    "is_valid_lap", "is_pit_in_lap", "is_pit_out_lap",
    "compound_front", "compound_rear", "tyre_age_laps",
    "wear_pct_start_FL", "wear_pct_start_FR", "wear_pct_start_RL", "wear_pct_start_RR",
    "wear_pct_end_FL", "wear_pct_end_FR", "wear_pct_end_RL", "wear_pct_end_RR",
    "fuel_start_l", "fuel_end_l", "fuel_used_l",
    "track_temp", "ambient_temp", "weather_state", "rain_intensity",
    "completed_at", "anomaly_flag", "anomaly_reason", "is_deleted",
]

SHAREABLE_SESSION_COLUMNS = [
    "session_uuid", "track", "layout", "car", "session_type",
    "started_at", "completed_at",
]

SHAREABLE_STINT_COLUMNS = [
    "stint_number", "compound_front", "compound_rear",
    "start_lap", "end_lap", "start_fuel_l", "end_fuel_l",
]

SHAREABLE_PIT_COLUMNS = [
    "pit_lap_number", "pit_loss", "in_lap_number", "out_lap_number",
]


def _row_to_dict(cursor, row, columns):
    """Convert a sqlite3.Row into a dict with only the requested columns."""
    return {col: row[col] for col in columns if col in row.keys()}


def export_sessions(
    db_path: Optional[str] = None,
    car: Optional[str] = None,
    track: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Export sessions (with their stints, laps, pit stops) to a portable
    JSON-serialisable dict.

    Filters:
      - car: only sessions for this car
      - track: only sessions for this track

    Returns:
        {
            "version": 1,
            "exported_at": "<iso8601>",
            "session_count": N,
            "lap_count": M,
            "sessions": [
                {
                    "session": {...},
                    "stints": [...],
                    "laps": [...],
                    "pit_stops": [...],
                },
                ...
            ]
        }
    """
    from datetime import datetime as _dt
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Build the WHERE clause for sessions
    where_clauses = []
    where_args: List[Any] = []
    if car:
        where_clauses.append("car = ?")
        where_args.append(car)
    if track:
        where_clauses.append("track = ?")
        where_args.append(track)
    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    cursor.execute(
        f"SELECT {', '.join(SHAREABLE_SESSION_COLUMNS)} FROM sessions{where_sql} "
        f"ORDER BY id",
        tuple(where_args),
    )
    session_rows = cursor.fetchall()

    exported_sessions = []
    total_laps = 0
    for s_row in session_rows:
        sess_dict = _row_to_dict(cursor, s_row, SHAREABLE_SESSION_COLUMNS)
        session_uuid = sess_dict["session_uuid"]

        # Stints
        cursor.execute(
            "SELECT id, " + ", ".join(SHAREABLE_STINT_COLUMNS) +
            " FROM stints WHERE session_id = (SELECT id FROM sessions WHERE session_uuid = ?)"
            " ORDER BY stint_number",
            (session_uuid,),
        )
        stints = []
        for st_row in cursor.fetchall():
            sd = {c: st_row[c] for c in SHAREABLE_STINT_COLUMNS}
            sd["stint_db_id"] = st_row["id"]
            stints.append(sd)

        # Laps
        cursor.execute(
            "SELECT s.session_uuid AS session_uuid, "
            "       COALESCE(st.stint_number, 1) AS stint_number, " +
            "       " + ", ".join(
                f"l.{c}" for c in SHAREABLE_LAP_COLUMNS
                if c not in ("session_uuid", "stint_number")
            ) + " "
            "FROM laps l "
            "JOIN sessions s ON l.session_id = s.id "
            "LEFT JOIN stints st ON l.stint_id = st.id "
            "WHERE s.session_uuid = ? "
            "ORDER BY l.lap_number",
            (session_uuid,),
        )
        laps = [_row_to_dict(cursor, r, SHAREABLE_LAP_COLUMNS) for r in cursor.fetchall()]
        total_laps += len(laps)

        # Pit stops
        cursor.execute(
            "SELECT p.lap_number AS pit_lap_number, p.pit_loss, "
            "       p.in_lap_number, p.out_lap_number "
            "FROM pit_stops p "
            "JOIN sessions s ON p.session_id = s.id "
            "WHERE s.session_uuid = ? "
            "ORDER BY p.lap_number",
            (session_uuid,),
        )
        pit_stops = [{c: r[c] for c in SHAREABLE_PIT_COLUMNS} for r in cursor.fetchall()]

        exported_sessions.append({
            "session": sess_dict,
            "stints": stints,
            "laps": laps,
            "pit_stops": pit_stops,
        })

    conn.close()

    return {
        "version": 1,
        "exported_at": _dt.now().isoformat(),
        "session_count": len(exported_sessions),
        "lap_count": total_laps,
        "sessions": exported_sessions,
    }


def _find_session_by_uuid(
    cursor, session_uuid: str
) -> Optional[int]:
    cursor.execute(
        "SELECT id FROM sessions WHERE session_uuid = ?",
        (session_uuid,),
    )
    row = cursor.fetchone()
    return row["id"] if row else None


def _find_stint_by_number(
    cursor, session_id: int, stint_number: int
) -> Optional[int]:
    cursor.execute(
        "SELECT id FROM stints WHERE session_id = ? AND stint_number = ?",
        (session_id, stint_number),
    )
    row = cursor.fetchone()
    return row["id"] if row else None


def _find_lap_by_session_and_number(
    cursor, session_id: int, lap_number: int
) -> Optional[int]:
    cursor.execute(
        "SELECT id FROM laps WHERE session_id = ? AND lap_number = ?",
        (session_id, lap_number),
    )
    row = cursor.fetchone()
    return row["id"] if row else None


def import_sessions(
    payload: Dict[str, Any],
    db_path: Optional[str] = None,
    overwrite_existing: bool = False,
) -> Dict[str, Any]:
    """
    Import a payload previously produced by export_sessions().

    Dedup is performed on (session_uuid, lap_number):
      - if a session with the same UUID exists, its laps are merged in
      - if a lap with the same (session, lap_number) exists, it is
        skipped unless overwrite_existing=True (in which case the lap
        row is replaced with the imported values)

    Returns a summary: {sessions_added, laps_added, laps_skipped,
                         laps_overwritten, pit_stops_added}
    """
    if not isinstance(payload, dict) or "sessions" not in payload:
        return {
            "sessions_added": 0,
            "laps_added": 0,
            "laps_skipped": 0,
            "laps_overwritten": 0,
            "pit_stops_added": 0,
            "error": "invalid payload (missing 'sessions')",
        }

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    sessions_added = 0
    laps_added = 0
    laps_skipped = 0
    laps_overwritten = 0
    pit_stops_added = 0

    for entry in payload.get("sessions", []):
        sess = entry.get("session", {})
        session_uuid = sess.get("session_uuid")
        if not session_uuid:
            continue

        existing_id = _find_session_by_uuid(cursor, session_uuid)
        if existing_id is None:
            cursor.execute(
                "INSERT INTO sessions (session_uuid, track, layout, car, "
                "session_type, started_at, completed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    session_uuid,
                    sess.get("track", ""),
                    sess.get("layout", ""),
                    sess.get("car", ""),
                    sess.get("session_type", ""),
                    sess.get("started_at", ""),
                    sess.get("completed_at", ""),
                ),
            )
            session_id = cursor.lastrowid
            sessions_added += 1
        else:
            session_id = existing_id

        # Stints: dedup by (session_id, stint_number)
        stint_id_by_number: Dict[int, int] = {}
        for stint in entry.get("stints", []):
            sn = int(stint.get("stint_number", 1) or 1)
            existing_stint = _find_stint_by_number(cursor, session_id, sn)
            if existing_stint is not None:
                stint_id_by_number[sn] = existing_stint
                continue
            cursor.execute(
                "INSERT INTO stints (session_id, stint_number, compound_front, "
                "compound_rear, start_lap, end_lap, start_fuel_l, end_fuel_l) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    sn,
                    stint.get("compound_front", "Medium"),
                    stint.get("compound_rear", "Medium"),
                    stint.get("start_lap", 1),
                    stint.get("end_lap"),
                    stint.get("start_fuel_l", 0.0),
                    stint.get("end_fuel_l"),
                ),
            )
            stint_id_by_number[sn] = cursor.lastrowid

        # Laps
        for lap in entry.get("laps", []):
            ln = int(lap.get("lap_number", 0) or 0)
            if ln <= 0:
                continue
            existing_lap = _find_lap_by_session_and_number(cursor, session_id, ln)
            if existing_lap is not None and not overwrite_existing:
                laps_skipped += 1
                continue

            stint_number = int(lap.get("stint_number", 1) or 1)
            stint_db_id = stint_id_by_number.get(stint_number)

            lap_values = (
                session_id,
                stint_db_id,
                ln,
                float(lap.get("lap_time", 0.0) or 0.0),
                float(lap.get("sector_1", 0.0) or 0.0),
                float(lap.get("sector_2", 0.0) or 0.0),
                float(lap.get("sector_3", 0.0) or 0.0),
                int(lap.get("is_valid_lap", 1) or 0),
                int(lap.get("is_pit_in_lap", 0) or 0),
                int(lap.get("is_pit_out_lap", 0) or 0),
                lap.get("compound_front", "Medium"),
                lap.get("compound_rear", "Medium"),
                int(lap.get("tyre_age_laps", 1) or 1),
                float(lap.get("wear_pct_start_FL", 0.0) or 0.0),
                float(lap.get("wear_pct_start_FR", 0.0) or 0.0),
                float(lap.get("wear_pct_start_RL", 0.0) or 0.0),
                float(lap.get("wear_pct_start_RR", 0.0) or 0.0),
                float(lap.get("wear_pct_end_FL", 0.0) or 0.0),
                float(lap.get("wear_pct_end_FR", 0.0) or 0.0),
                float(lap.get("wear_pct_end_RL", 0.0) or 0.0),
                float(lap.get("wear_pct_end_RR", 0.0) or 0.0),
                float(lap.get("fuel_start_l", 0.0) or 0.0),
                float(lap.get("fuel_end_l", 0.0) or 0.0),
                float(lap.get("fuel_used_l", 0.0) or 0.0),
                float(lap.get("track_temp", 25.0) or 25.0),
                float(lap.get("ambient_temp", 20.0) or 20.0),
                lap.get("weather_state", "DRY"),
                float(lap.get("rain_intensity", 0.0) or 0.0),
                lap.get("completed_at", ""),
                int(lap.get("anomaly_flag", 0) or 0),
                lap.get("anomaly_reason"),
                int(lap.get("is_deleted", 0) or 0),
            )

            if existing_lap is not None and overwrite_existing:
                cursor.execute(
                    "UPDATE laps SET session_id=?, stint_id=?, lap_number=?, "
                    "lap_time=?, sector_1=?, sector_2=?, sector_3=?, "
                    "is_valid_lap=?, is_pit_in_lap=?, is_pit_out_lap=?, "
                    "compound_front=?, compound_rear=?, tyre_age_laps=?, "
                    "wear_pct_start_FL=?, wear_pct_start_FR=?, "
                    "wear_pct_start_RL=?, wear_pct_start_RR=?, "
                    "wear_pct_end_FL=?, wear_pct_end_FR=?, "
                    "wear_pct_end_RL=?, wear_pct_end_RR=?, "
                    "fuel_start_l=?, fuel_end_l=?, fuel_used_l=?, "
                    "track_temp=?, ambient_temp=?, weather_state=?, "
                    "rain_intensity=?, completed_at=?, anomaly_flag=?, "
                    "anomaly_reason=?, is_deleted=? WHERE id=?",
                    lap_values + (existing_lap,),
                )
                laps_overwritten += 1
            else:
                cursor.execute(
                    "INSERT INTO laps (session_id, stint_id, lap_number, "
                    "lap_time, sector_1, sector_2, sector_3, "
                    "is_valid_lap, is_pit_in_lap, is_pit_out_lap, "
                    "compound_front, compound_rear, tyre_age_laps, "
                    "wear_pct_start_FL, wear_pct_start_FR, "
                    "wear_pct_start_RL, wear_pct_start_RR, "
                    "wear_pct_end_FL, wear_pct_end_FR, "
                    "wear_pct_end_RL, wear_pct_end_RR, "
                    "fuel_start_l, fuel_end_l, fuel_used_l, "
                    "track_temp, ambient_temp, weather_state, "
                    "rain_intensity, completed_at, anomaly_flag, "
                    "anomaly_reason, is_deleted) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                    "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                    "?, ?, ?, ?)",
                    lap_values,
                )
                laps_added += 1

        # Pit stops
        for ps in entry.get("pit_stops", []):
            cursor.execute(
                "INSERT INTO pit_stops (session_id, lap_number, pit_loss, "
                "in_lap_number, out_lap_number) VALUES (?, ?, ?, ?, ?)",
                (
                    session_id,
                    int(ps.get("pit_lap_number", 0) or 0),
                    float(ps.get("pit_loss", 0.0) or 0.0),
                    int(ps.get("in_lap_number", 0) or 0),
                    int(ps.get("out_lap_number", 0) or 0),
                ),
            )
            pit_stops_added += 1

    conn.commit()
    conn.close()

    return {
        "sessions_added": sessions_added,
        "laps_added": laps_added,
        "laps_skipped": laps_skipped,
        "laps_overwritten": laps_overwritten,
        "pit_stops_added": pit_stops_added,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Cloud sync — push/pull to the configured backend
#
# push_pending_sessions():
#   - Scans the local DB for sessions that have not yet been pushed
#     (sync_queue.status != 'pushed') to the current backend
#   - Calls backend.push() for each
#   - Updates sync_queue with the result
#
# pull_remote_sessions():
#   - Calls backend.pull() to fetch remote payloads
#   - Calls import_sessions() for each (with dedup, so safe to re-pull)
#   - Returns a summary
# ══════════════════════════════════════════════════════════════════════════════

def _enqueue_session_for_sync(
    session_uuid: str, backend_name: str, payload_size: int = 0,
    db_path: Optional[str] = None,
) -> None:
    """Add or update a session in the sync queue."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sync_queue (session_uuid, backend, status, payload_size)
        VALUES (?, ?, 'pending', ?)
        ON CONFLICT(session_uuid) DO UPDATE SET
            backend = excluded.backend,
            status = CASE
                WHEN sync_queue.status = 'pushed' THEN sync_queue.status
                ELSE 'pending'
            END
    """, (session_uuid, backend_name, payload_size))
    conn.commit()
    conn.close()


def _mark_sync_result(
    session_uuid: str, ok: bool, error: Optional[str] = None,
    db_path: Optional[str] = None,
) -> None:
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    from datetime import datetime as _dt
    now = _dt.now().isoformat()
    if ok:
        cursor.execute("""
            UPDATE sync_queue SET status = 'pushed', last_error = NULL,
                pushed_at = ?, last_attempt_at = ?
            WHERE session_uuid = ?
        """, (now, now, session_uuid))
    else:
        cursor.execute("""
            UPDATE sync_queue SET status = 'failed', last_error = ?,
                last_attempt_at = ?
            WHERE session_uuid = ?
        """, (error, now, session_uuid))
    conn.commit()
    conn.close()


def _get_pending_session_uuids(
    backend_name: str, db_path: Optional[str] = None,
) -> List[str]:
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.session_uuid FROM sessions s
        LEFT JOIN sync_queue q ON s.session_uuid = q.session_uuid
                              AND q.backend = ?
        WHERE s.session_uuid != ''
          AND (q.session_uuid IS NULL OR q.status != 'pushed')
        ORDER BY s.id
    """, (backend_name,))
    uuids = [r["session_uuid"] for r in cursor.fetchall()]
    conn.close()
    return uuids


def _attach_user_to_payload(
    payload: Dict[str, Any], db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    If the local user is opt-in, attach their user_id to every session
    in the payload so the cloud can attribute the data to the right user.
    Also attach the user's display_name at the payload level for stats.
    """
    user = get_local_user(db_path)
    if not user["opt_in_global"] or not user["user_id"]:
        return payload
    annotated = dict(payload)
    annotated["user_id"] = user["user_id"]
    annotated["display_name"] = user["display_name"]
    annotated["exported_by"] = user["user_id"]
    for session_entry in annotated.get("sessions", []):
        sess = session_entry.get("session", {})
        sess["user_id"] = user["user_id"]
    return annotated


def push_pending_sessions(
    db_path: Optional[str] = None,
    backend: Optional[Any] = None,
    min_laps_per_session: int = 5,
) -> Dict[str, Any]:
    """
    Push all sessions that have not yet been pushed to the cloud backend.

    Args:
        db_path: local DB path (default: DEFAULT_DB_PATH)
        backend: a CloudSync instance; defaults to the active backend
                 from database.cloud.set_backend() / NullSync

    Returns:
        {
            "pushed": int,
            "failed": int,
            "skipped": int,
            "errors": [{"session_uuid": str, "error": str}, ...]
        }
    """
    if backend is None:
        from database.cloud import get_backend
        backend = get_backend()

    backend_name = getattr(backend, "backend_name", "custom")
    pending = _get_pending_session_uuids(backend_name, db_path=db_path)
    if not pending:
        return {"pushed": 0, "failed": 0, "skipped": 0, "errors": []}

    pushed = 0
    failed = 0
    errors = []

    # Export all sessions ONCE, then filter by UUID in the loop (avoids N²)
    all_payload = export_sessions(db_path=db_path)

    for uuid in pending:
        # Get only this session's export
        single_session = {
            **all_payload,
            "sessions": [
                s for s in all_payload.get("sessions", [])
                if s.get("session", {}).get("session_uuid") == uuid
            ],
        }
        if not single_session["sessions"]:
            continue
        # Skip sessions that are too short (test data noise)
        total_laps_in_session = sum(
            len(s.get("laps", [])) for s in single_session["sessions"]
        )
        if total_laps_in_session < min_laps_per_session:
            _mark_sync_result(
                uuid, ok=False,
                error=f"skipped: only {total_laps_in_session} laps (< {min_laps_per_session})",
                db_path=db_path,
            )
            failed += 1
            errors.append({
                "session_uuid": uuid,
                "error": f"too few laps ({total_laps_in_session})",
            })
            continue

        # Attach user_id if opt-in
        single_session = _attach_user_to_payload(single_session, db_path=db_path)
        size = len(json.dumps(single_session, separators=(",", ":")))
        _enqueue_session_for_sync(uuid, backend_name, payload_size=size, db_path=db_path)

        result = backend.push(single_session)
        if result.get("ok"):
            _mark_sync_result(uuid, ok=True, db_path=db_path)
            pushed += 1
        else:
            _mark_sync_result(uuid, ok=False, error=result.get("error"), db_path=db_path)
            failed += 1
            errors.append({"session_uuid": uuid, "error": result.get("error")})

    return {
        "pushed": pushed,
        "failed": failed,
        "skipped": len(pending) - pushed - failed,
        "errors": errors,
    }


def pull_remote_sessions(
    db_path: Optional[str] = None,
    backend: Optional[Any] = None,
    overwrite_existing: bool = False,
) -> Dict[str, Any]:
    """
    Fetch payloads from the cloud backend and import them locally.

    Dedup is automatic via import_sessions. Pass overwrite_existing=True
    to force replacement of existing laps.

    Returns: aggregate summary across all pulled payloads.
    """
    if backend is None:
        from database.cloud import get_backend
        backend = get_backend()

    payloads = backend.pull() or []
    agg = {
        "sessions_added": 0,
        "laps_added": 0,
        "laps_skipped": 0,
        "laps_overwritten": 0,
        "pit_stops_added": 0,
        "payloads_processed": 0,
    }
    for payload in payloads:
        # Skip Parquet-only stubs that don't have 'sessions' key
        if not isinstance(payload, dict) or "sessions" not in payload:
            continue
        summary = import_sessions(
            payload=payload, db_path=db_path, overwrite_existing=overwrite_existing,
        )
        agg["sessions_added"] += summary.get("sessions_added", 0)
        agg["laps_added"] += summary.get("laps_added", 0)
        agg["laps_skipped"] += summary.get("laps_skipped", 0)
        agg["laps_overwritten"] += summary.get("laps_overwritten", 0)
        agg["pit_stops_added"] += summary.get("pit_stops_added", 0)
        agg["payloads_processed"] += 1
    return agg


def get_sync_status(db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Return the current sync state: counts of pushed/pending/failed,
    plus the active backend status.
    """
    from database.cloud import get_backend
    backend = get_backend()
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT status, COUNT(*) AS n FROM sync_queue GROUP BY status
    """)
    counts = {r["status"]: r["n"] for r in cursor.fetchall()}
    cursor.execute("""
        SELECT s.session_uuid, q.status, q.last_error, q.pushed_at
        FROM sync_queue q JOIN sessions s ON s.session_uuid = q.session_uuid
        ORDER BY q.id DESC LIMIT 20
    """)
    recent = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {
        "backend": backend.status(),
        "counts": {
            "pushed": counts.get("pushed", 0),
            "pending": counts.get("pending", 0),
            "failed": counts.get("failed", 0),
        },
        "recent": recent,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Community DB — opt-in / opt-out / user identity
#
# The user can opt in to share their laps with the global community
# database. On opt-in:
#   - A random user_id (UUID) is generated
#   - A random display_name is suggested (animal + number)
#   - user_id is attached to every session pushed to the cloud
#
# On opt-out:
#   - Local opt-in flag is cleared
#   - Cloud data is NOT automatically deleted (user must click
#     "Delete my data" to wipe from cloud)
# ══════════════════════════════════════════════════════════════════════════════

# Cute animal-themed display name pool (no offense, no politics)
_DISPLAY_NAME_ADJECTIVES = [
    "Furious", "Swift", "Silent", "Brave", "Clever", "Bold",
    "Lucky", "Mighty", "Stealthy", "Wild", "Calm", "Sharp",
    "Quick", "Bright", "Eager", "Calm", "Wise", "Daring",
]
_DISPLAY_NAME_ANIMALS = [
    "Falcon", "Panda", "Wolf", "Tiger", "Eagle", "Hawk",
    "Otter", "Fox", "Lynx", "Bear", "Owl", "Raven",
    "Cobra", "Shark", "Lion", "Panther", "Bison", "Heron",
]


def _generate_display_name() -> str:
    """Generate a random, friendly display name like 'SwiftFalcon42'."""
    import random
    adj = random.choice(_DISPLAY_NAME_ADJECTIVES)
    ani = random.choice(_DISPLAY_NAME_ANIMALS)
    num = random.randint(10, 99)
    return f"{adj}{ani}{num}"


def get_local_user(db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Return the local user's opt-in state and identity.

    Returns:
        {
            "user_id": str | None,
            "display_name": str | None,
            "opt_in_global": bool,
            "created_at": str | None,
            "opt_in_at": str | None,
            "opt_out_at": str | None,
        }
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM db_users WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return {
            "user_id": None, "display_name": None,
            "opt_in_global": False,
            "created_at": None, "opt_in_at": None, "opt_out_at": None,
        }
    return {
        "user_id": row["user_id"],
        "display_name": row["display_name"],
        "opt_in_global": bool(row["opt_in_global"]),
        "created_at": row["created_at"],
        "opt_in_at": row["opt_in_at"],
        "opt_out_at": row["opt_out_at"],
    }


def opt_in_to_community(
    display_name: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Opt the local user in to the community DB.

    If `display_name` is None, a random one is generated.
    A random user_id (UUID) is generated only on FIRST opt-in (re-opt-ins
    keep the existing user_id to avoid orphaning cloud data).

    Returns the updated user state.
    """
    from datetime import datetime as _dt
    now = _dt.now().isoformat()

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, display_name, opt_in_at FROM db_users WHERE id = 1")
    existing = cursor.fetchone()
    existing_user_id = existing["user_id"] if existing else None
    existing_opt_in_at = existing["opt_in_at"] if existing else None
    existing_display = existing["display_name"] if existing else None

    if existing_user_id:
        # Re-opt-in: keep identity, only refresh opt_in_at if was None
        user_id = existing_user_id
        created_at = None
        # Find created_at from the user_id we don't have directly;
        # fall back to the original opt_in_at as a stable timestamp
        created_at = existing_opt_in_at or now
        opt_in_at = existing_opt_in_at or now
    else:
        # First time: generate fresh identity
        user_id = str(uuid.uuid4())
        created_at = now
        opt_in_at = now

    # Use existing display_name if user didn't pass a new one
    if not display_name:
        display_name = existing_display or _generate_display_name()

    cursor.execute("""
        UPDATE db_users SET
            user_id = ?, display_name = ?, opt_in_global = 1,
            created_at = ?, opt_in_at = ?, opt_out_at = NULL
        WHERE id = 1
    """, (user_id, display_name, created_at, opt_in_at))
    conn.commit()
    conn.close()
    return get_local_user(db_path)


def opt_out_of_community(
    delete_cloud_data: bool = False,
    db_path: Optional[str] = None,
    backend: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Opt the local user out. If `delete_cloud_data=True`, also wipes all
    the user's data from the cloud backend.
    """
    from datetime import datetime as _dt
    now = _dt.now().isoformat()
    user = get_local_user(db_path)

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE db_users SET opt_in_global = 0, opt_out_at = ? WHERE id = 1
    """, (now,))
    conn.commit()
    conn.close()

    deleted_remote = 0
    if delete_cloud_data and user["user_id"]:
        if backend is None:
            from database.cloud import get_backend
            backend = get_backend()
        if hasattr(backend, "delete_user_data"):
            try:
                result = backend.delete_user_data(user["user_id"])
                deleted_remote = result.get("deleted", 0) if isinstance(result, dict) else 0
            except Exception:
                pass

    out = get_local_user(db_path)
    out["deleted_remote_records"] = deleted_remote
    return out


def set_display_name(
    new_name: str,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Update the user's display name (must be opt-in)."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE db_users SET display_name = ? WHERE id = 1 AND opt_in_global = 1
    """, (new_name,))
    conn.commit()
    conn.close()
    return get_local_user(db_path)


# ══════════════════════════════════════════════════════════════════════════════
# Owner email — S-2
#
# Lightweight identity: just an email saved locally. No password, no
# Google, no JWT. Used to filter the dashboard ("only my laps") and to
# tag new sessions so each user sees their own data.
# ══════════════════════════════════════════════════════════════════════════════

def get_owner_email(db_path: Optional[str] = None) -> Optional[str]:
    """Return the local owner's email (or None if not set)."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM db_users WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    email = row["email"]
    return email if email else None


def set_owner_email(
    email: Optional[str],
    db_path: Optional[str] = None,
) -> Optional[str]:
    """
    Set the local owner's email. Pass None to clear it.
    Returns the new value (validated / normalised).
    """
    if email:
        email = email.strip().lower()
        # Basic validation: must be in form user@domain.tld
        parts = email.split("@")
        if len(parts) != 2 or not parts[0] or not parts[1] or "." not in parts[1] or parts[1].endswith(".") or parts[1].startswith("."):
            raise ValueError(f"invalid email: {email!r}")
    else:
        email = None
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE db_users SET email = ? WHERE id = 1", (email,))
    conn.commit()
    conn.close()
    # Backfill any sessions that were created before we knew the email
    if email:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE sessions SET owner_email = ? WHERE owner_email IS NULL OR owner_email = ''",
            (email,),
        )
        cursor.execute(
            "UPDATE laps SET owner_email = ? WHERE owner_email IS NULL OR owner_email = ''",
            (email,),
        )
        conn.commit()
        conn.close()
    return email


# ══════════════════════════════════════════════════════════════════════════════
# Telemetry Samples — per-frame speed/RPM/gear/throttle traces
# ══════════════════════════════════════════════════════════════════════════════

TELEMETRY_SAMPLES_SCHEMA = """
CREATE TABLE IF NOT EXISTS lap_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lap_id INTEGER NOT NULL,
    elapsed_seconds REAL NOT NULL,
    speed REAL,
    rpm REAL,
    gear INTEGER,
    throttle REAL,
    brake REAL,
    brake_temp_fl REAL,
    brake_temp_fr REAL,
    brake_temp_rl REAL,
    brake_temp_rr REAL,
    tyre_temp_fl REAL,
    tyre_temp_fr REAL,
    tyre_temp_rl REAL,
    tyre_temp_rr REAL,
    FOREIGN KEY (lap_id) REFERENCES laps(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_lap_samples_lap ON lap_samples(lap_id);
"""


def _init_telemetry_samples_table_inner(conn, cursor):
    """Create the lap_samples table if it doesn't exist (uses existing cursor)."""
    cursor.executescript(TELEMETRY_SAMPLES_SCHEMA)
    conn.commit()


def init_telemetry_samples_table(db_path=None):
    """Create the lap_samples table if it doesn't exist (standalone call)."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.executescript(TELEMETRY_SAMPLES_SCHEMA)
    conn.commit()
    conn.close()


def save_lap_samples(lap_id: int, samples: list, db_path=None):
    """Save telemetry samples for a lap.

    samples: list of dicts with keys: elapsed_seconds, speed, rpm, gear, throttle, brake,
             brake_temp_fl, brake_temp_fr, brake_temp_rl, brake_temp_rr,
             tyre_temp_fl, tyre_temp_fr, tyre_temp_rl, tyre_temp_rr
    """
    if not samples:
        return
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.executemany(
        """INSERT INTO lap_samples
           (lap_id, elapsed_seconds, speed, rpm, gear, throttle, brake,
            brake_temp_fl, brake_temp_fr, brake_temp_rl, brake_temp_rr,
            tyre_temp_fl, tyre_temp_fr, tyre_temp_rl, tyre_temp_rr)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(lap_id,
          s.get('elapsed_seconds'), s.get('speed'), s.get('rpm'), s.get('gear'),
          s.get('throttle'), s.get('brake'),
          s.get('brake_temp_fl'), s.get('brake_temp_fr'),
          s.get('brake_temp_rl'), s.get('brake_temp_rr'),
          s.get('tyre_temp_fl'), s.get('tyre_temp_fr'),
          s.get('tyre_temp_rl'), s.get('tyre_temp_rr'))
         for s in samples]
    )
    conn.commit()
    conn.close()


def get_lap_samples(lap_id: int, db_path=None) -> list:
    """Get all telemetry samples for a lap, ordered by elapsed_seconds."""
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM lap_samples WHERE lap_id = ? ORDER BY elapsed_seconds ASC",
        (lap_id,)
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_track_distance(track_name: str) -> float:
    """Return approximate track length in km for a known track.
    Falls back to 5.0 km if unknown."""
    TRACK_DISTANCES = {
        "Le Mans": 13.626,
        "Monza": 5.793,
        "Spa": 7.004,
        "Silverstone": 5.891,
        "Nürburgring": 5.148,
        "Imola": 4.909,
        "Sebring": 6.020,
        "Daytona": 5.729,
        "Fuji": 4.563,
        "Interlagos": 4.309,
        "Bahrain": 5.412,
        "Yas Marina": 5.554,
        "Bathurst": 6.213,
        "Road Atlanta": 4.088,
        "Laguna Seca": 3.602,
        "Watkins Glen": 5.472,
        "Circuit of the Americas": 5.513,
        "Red Bull Ring": 4.318,
        "Zandvoort": 4.259,
        "Hungaroring": 4.381,
        "Barcelona": 4.675,
        "Monaco": 3.337,
        "Suzuka": 5.807,
        "Melbourne": 5.303,
        "Baku": 6.003,
        "Jeddah": 6.175,
        "Miami": 5.410,
        "Las Vegas": 6.201,
        "Losail": 5.380,
        "Shanghai": 5.451,
        "Portimão": 4.653,
        "Misano": 4.226,
        "Paul Ricard": 5.842,
        "Hockenheim": 4.574,
        "Sepang": 5.543,
        "Korea": 5.621,
    }
    if not track_name:
        return 5.0
    # Normalize for fuzzy matching: lowercase and remove diacritics
    import unicodedata
    def _normalize(s):
        nfkd = unicodedata.normalize('NFKD', s)
        return nfkd.encode('ascii', 'ignore').decode('ascii').lower()
    track_norm = _normalize(track_name)
    for name, dist in TRACK_DISTANCES.items():
        name_norm = _normalize(name)
        if name_norm in track_norm or track_norm in name_norm:
            return dist
    return 5.0  # default fallback
