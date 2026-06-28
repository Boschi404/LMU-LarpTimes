"""
bundle_laps.py — CLI per esportare/importare giri in un file .lmubundle.

Uso:
    # Esporta tutto il DB in un file
    python scripts/bundle_laps.py export --out my_laps.lmubundle
    python scripts/bundle_laps.py export --out le_mans.lmubundle --car "Ferrari 499P" --track "Le Mans"

    # Importa in un altro DB
    python scripts/bundle_laps.py import --in my_laps.lmubundle --db target.db
    python scripts/bundle_laps.py import --in bundle.lmubundle --overwrite

    # Info sul bundle (numero sessioni, giri, ecc.)
    python scripts/bundle_laps.py info --in my_laps.lmubundle
"""
import argparse
import gzip
import json
import os
import sys
import tempfile

# Allow running this script from the project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import database


def cmd_export(args):
    payload = database.export_sessions(
        db_path=args.db,
        car=args.car,
        track=args.track,
    )
    # Compress with gzip
    data = json.dumps(payload, indent=None, separators=(",", ":")).encode("utf-8")
    with open(args.out, "wb") as f:
        f.write(gzip.compress(data))
    print(
        f"Exported {payload['session_count']} sessions, "
        f"{payload['lap_count']} laps → {args.out} "
        f"({os.path.getsize(args.out) / 1024:.1f} KB)"
    )


def cmd_import(args):
    with open(args.in_path, "rb") as f:
        raw = f.read()
    # Auto-detect: gzip starts with \x1f\x8b
    if raw[:2] == b"\x1f\x8b":
        data = gzip.decompress(raw)
    else:
        data = raw
    payload = json.loads(data.decode("utf-8"))
    summary = database.import_sessions(
        payload=payload,
        db_path=args.db,
        overwrite_existing=args.overwrite,
    )
    print(f"Import summary: {summary}")


def cmd_info(args):
    with open(args.in_path, "rb") as f:
        raw = f.read()
    if raw[:2] == b"\x1f\x8b":
        data = gzip.decompress(raw)
    else:
        data = raw
    payload = json.loads(data.decode("utf-8"))
    print(f"Bundle version: {payload.get('version')}")
    print(f"Exported at:    {payload.get('exported_at')}")
    print(f"Sessions:       {payload.get('session_count')}")
    print(f"Laps:           {payload.get('lap_count')}")
    for s in payload.get("sessions", []):
        sess = s.get("session", {})
        laps = s.get("laps", [])
        stints = s.get("stints", [])
        pits = s.get("pit_stops", [])
        print(
            f"  - {sess.get('car','?')} @ {sess.get('track','?')} "
            f"({sess.get('session_type','?')}): "
            f"{len(laps)} laps, {len(stints)} stints, {len(pits)} pit stops"
        )


def main():
    parser = argparse.ArgumentParser(
        description="LMU Pit Strategist — share laps via .lmubundle files"
    )
    parser.add_argument(
        "--db", default=database.DEFAULT_DB_PATH,
        help="Path to the SQLite database (default: %(default)s)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_exp = sub.add_parser("export", help="Export DB → bundle file")
    p_exp.add_argument("--out", required=True, help="Output .lmubundle path")
    p_exp.add_argument("--car", help="Filter by car name")
    p_exp.add_argument("--track", help="Filter by track name")
    p_exp.set_defaults(func=cmd_export)

    p_imp = sub.add_parser("import", help="Import bundle file → DB")
    p_imp.add_argument("--in", dest="in_path", required=True, help="Input .lmubundle path")
    p_imp.add_argument("--overwrite", action="store_true",
                       help="Overwrite existing laps (default: skip duplicates)")
    p_imp.set_defaults(func=cmd_import)

    p_info = sub.add_parser("info", help="Show bundle contents")
    p_info.add_argument("--in", dest="in_path", required=True, help="Input .lmubundle path")
    p_info.set_defaults(func=cmd_info)

    args = parser.parse_args()
    # Ensure DB exists
    if not os.path.exists(args.db) and args.cmd != "info":
        print(f"Database not found at {args.db}. Initialising...")
        database.init_db(db_path=args.db)
    args.func(args)


if __name__ == "__main__":
    main()
