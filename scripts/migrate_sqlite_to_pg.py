#!/usr/bin/env python3
"""One-time idempotent migration: local sqlite -> central PG (harness
platform-integration task 1.2).

Backs up the sqlite file, copies rows for the four pipeline tables
(discoveries/candidates/analyses/manifests) preserving ids, skips ids
already present in PG, and resets each table's id sequence. Safe to
re-run. Requires HARNESS_DATABASE_URL to point at the central PG.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TABLES = {  # sqlite table -> model class name
    "discoveries": "Discovery",
    "candidates": "Candidate",
    "analyses": "Analysis",
    "manifests": "Manifest",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", default="data/harness.db")
    args = ap.parse_args()

    from fd_scraw_harness.db import get_session
    import fd_scraw_harness.models as M

    sqlite_path = Path(args.sqlite)
    if not sqlite_path.exists():
        print(f"migrate: {sqlite_path} not found; nothing to do")
        return 0

    backup = sqlite_path.with_suffix(f".db.bak-{int(time.time())}")
    shutil.copy2(sqlite_path, backup)
    print(f"migrate: backup written -> {backup}")

    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row
    sess = get_session()

    for table, cls_name in TABLES.items():
        model = getattr(M, cls_name)
        cols = [c.name for c in model.__table__.columns]
        try:
            rows = src.execute(f"SELECT * FROM {table}").fetchall()
        except sqlite3.OperationalError:
            print(f"migrate: {table}: missing in sqlite, skipped")
            continue
        existing = {r[0] for r in sess.execute(
            __import__("sqlalchemy").select(model.id)).fetchall()}
        migrated = skipped = 0
        for row in rows:
            data = {c: row[c] for c in cols if c in row.keys()}
            if data.get("id") in existing:
                skipped += 1
                continue
            sess.execute(model.__table__.insert().values(**data))
            migrated += 1
        sess.commit()
        # keep sequences ahead of explicitly-inserted ids
        sess.execute(
            __import__("sqlalchemy").text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"coalesce((SELECT max(id) FROM {table}), 1))"))
        sess.commit()
        print(f"migrate: {table}: {migrated} migrated, {skipped} already present")

    sess.close()
    src.close()
    print("migrate: done (sqlite untouched; re-running is a no-op)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
