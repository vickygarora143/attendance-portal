# -*- coding: utf-8 -*-
"""Backup the attendance portal database.

Supabase's free plan has NO automatic backups, so run this on a schedule.

Usage:
    python backup_db.py                 # uses DATABASE_URL env / backup_config.json
    python backup_db.py --local         # backup the local SQLite portal.db

Output: backups/portal_YYYYmmdd_HHMMSS.sql.gz  (+ a manifest line in backup.log)
Keeps the newest KEEP files (default 8).
"""
import gzip
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, "backups")
KEEP = int(os.environ.get("BACKUP_KEEP", "8"))


def _database_url():
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    cfg = os.path.join(HERE, "backup_config.json")
    if os.path.exists(cfg):
        with open(cfg, "r", encoding="utf-8") as f:
            return json.load(f)["database_url"]
    return None


def dump_postgres(url):
    import psycopg2
    conn = psycopg2.connect(url, connect_timeout=30)
    conn.set_session(readonly=True)
    cur = conn.cursor()
    cur.execute("""SELECT tablename FROM pg_tables
                   WHERE schemaname = 'public' ORDER BY tablename""")
    tables = [r[0] for r in cur.fetchall()]
    lines, counts = [], {}
    lines.append("-- Attendance Portal backup %s\n" % datetime.now().isoformat())
    lines.append("BEGIN;\n")
    for t in tables:
        cur.execute('SELECT * FROM "%s"' % t)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        counts[t] = len(rows)
        col_sql = ", ".join('"%s"' % c for c in cols)
        for row in rows:
            vals = cur.mogrify("(" + ", ".join(["%s"] * len(cols)) + ")", row).decode("utf-8")
            lines.append('INSERT INTO "%s" (%s) VALUES %s;\n' % (t, col_sql, vals))
        if "id" in cols:
            lines.append(
                "SELECT setval(pg_get_serial_sequence('\"%s\"', 'id'), "
                "COALESCE((SELECT max(id) FROM \"%s\"), 1));\n" % (t, t))
    lines.append("COMMIT;\n")
    conn.close()
    return "".join(lines), counts


def dump_sqlite(path):
    conn = sqlite3.connect(path)
    lines, counts = [], {}
    lines.append("-- Attendance Portal local backup %s\n" % datetime.utcnow().isoformat())
    for line in conn.iterdump():
        lines.append(line + "\n")
    for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        try:
            counts[t] = conn.execute('SELECT count(*) FROM "%s"' % t).fetchone()[0]
        except sqlite3.Error:
            pass
    conn.close()
    return "".join(lines), counts


def prune(keep):
    files = sorted(
        (os.path.join(OUTDIR, f) for f in os.listdir(OUTDIR) if f.endswith(".sql.gz")),
        key=os.path.getmtime, reverse=True)
    for old in files[keep:]:
        os.remove(old)
        print("pruned:", os.path.basename(old))


def main():
    local = "--local" in sys.argv
    os.makedirs(OUTDIR, exist_ok=True)

    if local:
        path = os.path.join(HERE, "portal.db")
        if not os.path.exists(path):
            print("ERROR: portal.db not found")
            return 1
        sql, counts = dump_sqlite(path)
        tag = "local"
    else:
        url = _database_url()
        if not url:
            print("ERROR: no DATABASE_URL and no backup_config.json")
            return 1
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        sql, counts = dump_postgres(url)
        tag = "cloud"

    raw = sql.encode("utf-8")
    name = "portal_%s_%s.sql.gz" % (tag, datetime.now().strftime("%Y%m%d_%H%M%S"))
    dest = os.path.join(OUTDIR, name)
    with gzip.open(dest, "wb", compresslevel=9) as f:
        f.write(raw)

    size = os.path.getsize(dest)
    print("backup:", dest)
    print("size: %.1f KB (raw %.1f KB)" % (size / 1024, len(raw) / 1024))
    print("sha256:", hashlib.sha256(raw).hexdigest()[:16])
    print("rows:", json.dumps(counts, sort_keys=True))
    prune(KEEP)
    return 0


if __name__ == "__main__":
    sys.exit(main())
