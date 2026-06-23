import sqlite3
import os
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lmu_pit_strategist.db")


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
            track TEXT NOT NULL,
            layout TEXT NOT NULL,
            car TEXT NOT NULL,
            session_type TEXT NOT NULL,
            started_at TEXT NOT NULL
        )
    """)

    # Create laps table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS laps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            lap_number INTEGER NOT NULL,
            stint_number INTEGER NOT NULL,
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
            anomaly_flag INTEGER NOT NULL DEFAULT 0,
            anomaly_reason TEXT,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
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

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO sessions (track, layout, car, session_type, started_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (track, layout, car, session_type, started_at)
    )
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id


def insert_lap(lap_data: Dict[str, Any], db_path: Optional[str] = None) -> int:
    """
    Insert a lap record into the database.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # Check fields
    fields = [
        "session_id", "lap_number", "stint_number", "lap_time",
        "sector_1", "sector_2", "sector_3", "is_valid_lap",
        "is_pit_in_lap", "is_pit_out_lap", "compound_front", "compound_rear",
        "tyre_age_laps", "wear_pct_start_FL", "wear_pct_start_FR",
        "wear_pct_start_RL", "wear_pct_start_RR", "wear_pct_end_FL",
        "wear_pct_end_FR", "wear_pct_end_RL", "wear_pct_end_RR",
        "fuel_start_l", "fuel_end_l", "fuel_used_l",
        "track_temp", "ambient_temp", "weather_state", "rain_intensity",
        "anomaly_flag", "anomaly_reason"
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
