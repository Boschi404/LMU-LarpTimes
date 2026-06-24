import sqlite3
import os
import uuid
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

    conn.commit()
    conn.close()
    _migrate_db(db_path)


def _migrate_db(db_path: Optional[str] = None) -> None:
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Add session_uuid to sessions
    try:
        cursor.execute("PRAGMA table_info(sessions)")
        cols = [r[1] for r in cursor.fetchall()]
        if "session_uuid" not in cols:
            cursor.execute("ALTER TABLE sessions ADD COLUMN session_uuid TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass

    # Check laps schema: if old schema (has stint_number), recreate to remove NOT NULL constraint
    try:
        cursor.execute("PRAGMA table_info(laps)")
        cols = [r[1] for r in cursor.fetchall()]
        if "stint_number" in cols:
            print("[DB] Migrating laps schema: dropping old table with stint_number")
            cursor.execute("DROP TABLE IF EXISTS laps")
            cursor.execute("""
                CREATE TABLE stints (
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
            cursor.execute("""
                CREATE TABLE laps (
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
                    completed_at TEXT NOT NULL DEFAULT '',
                    anomaly_flag INTEGER NOT NULL DEFAULT 0,
                    anomaly_reason TEXT,
                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE,
                    FOREIGN KEY (stint_id) REFERENCES stints (id)
                )
            """)
            print("[DB] Laps table recreated with new schema")
    except Exception as e:
        print(f"[DB] Migration error (stint_number): {e}")

    # If laps table exists but has no stint_id column, add it
    try:
        cursor.execute("PRAGMA table_info(laps)")
        cols = [r[1] for r in cursor.fetchall()]
        if "stint_number" not in cols and "stint_id" not in cols:
            cursor.execute("ALTER TABLE laps ADD COLUMN stint_id INTEGER")
            print("[DB] Added stint_id column to laps")
    except Exception as e:
        print(f"[DB] Migration error (stint_id): {e}")

    conn.commit()
    conn.close()


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

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO sessions (session_uuid, track, layout, car, session_type, started_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session_uuid, track, layout, car, session_type, started_at)
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
    Insert a lap record into the database.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # Check fields
    fields = [
        "session_id", "stint_id", "lap_number", "lap_time",
        "sector_1", "sector_2", "sector_3", "is_valid_lap",
        "is_pit_in_lap", "is_pit_out_lap", "compound_front", "compound_rear",
        "tyre_age_laps", "wear_pct_start_FL", "wear_pct_start_FR",
        "wear_pct_start_RL", "wear_pct_start_RR", "wear_pct_end_FL",
        "wear_pct_end_FR", "wear_pct_end_RL", "wear_pct_end_RR",
        "fuel_start_l", "fuel_end_l", "fuel_used_l",
        "track_temp", "ambient_temp", "weather_state", "rain_intensity",
        "completed_at"
    ]
    
    # Prepare query
    placeholders = ", ".join(["?"] * len(fields))
    columns = ", ".join(fields)
    values = [lap_data.get(f) for f in fields]
    
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
