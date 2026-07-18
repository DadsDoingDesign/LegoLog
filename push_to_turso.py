"""Push the locally-built legolog.db catalog into a remote Turso database.

Only pushes what app.py actually queries — themes, colors, parts, sets,
set_parts, set_totals — and skips rows belonging to excluded-theme sets
(gear/books/packs; see EXCLUDED_THEME_NAMES in app.py) since those are never
shown as buildable candidates anyway. owned_sets is created if missing but
never touched here, so your collection survives a catalog refresh.

Requires TURSO_DATABASE_URL and TURSO_AUTH_TOKEN — put them in a local .env
(see .env.example) before running.

Run with:  py -3.10 push_to_turso.py
"""

import os
import sqlite3
import time
from pathlib import Path

import libsql

BASE_DIR = Path(__file__).parent
LOCAL_DB = BASE_DIR / "legolog.db"

EXCLUDED_THEME_NAMES = (
    "Service Packs",
    "Bulk Bricks",
    "Supplemental",
    "VIP Add-On Packs",
    "Gear",
    "Books",
)

SCHEMA = """
DROP TABLE IF EXISTS themes;
DROP TABLE IF EXISTS colors;
DROP TABLE IF EXISTS parts;
DROP TABLE IF EXISTS sets;
DROP TABLE IF EXISTS set_parts;
DROP TABLE IF EXISTS set_totals;

CREATE TABLE themes (id INTEGER PRIMARY KEY, name TEXT, parent_id INTEGER);
CREATE TABLE colors (id INTEGER PRIMARY KEY, name TEXT, rgb TEXT, is_trans TEXT);
CREATE TABLE parts (part_num TEXT PRIMARY KEY, name TEXT, part_cat_id INTEGER);
CREATE TABLE sets (
    set_num TEXT PRIMARY KEY, name TEXT, year INTEGER,
    theme_id INTEGER, num_parts INTEGER, img_url TEXT
);
CREATE TABLE set_parts (
    set_num TEXT, part_num TEXT, color_id INTEGER,
    quantity INTEGER, spare_quantity INTEGER
);
CREATE TABLE set_totals (set_num TEXT PRIMARY KEY, total_parts INTEGER, distinct_parts INTEGER);

CREATE TABLE IF NOT EXISTS owned_sets (
    set_num TEXT PRIMARY KEY,
    quantity INTEGER NOT NULL DEFAULT 1,
    added_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_set_parts_set ON set_parts(set_num);
CREATE INDEX idx_set_parts_part ON set_parts(part_num, color_id, set_num, quantity, spare_quantity);
"""


def load_dotenv():
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def excluded_set_nums(local: sqlite3.Connection) -> set:
    placeholders = ",".join("?" * len(EXCLUDED_THEME_NAMES))
    rows = local.execute(
        f"""WITH RECURSIVE bad(id) AS (
                SELECT id FROM themes WHERE name IN ({placeholders})
                UNION
                SELECT t.id FROM themes t JOIN bad b ON t.parent_id = b.id
            )
            SELECT set_num FROM sets WHERE theme_id IN (SELECT id FROM bad)""",
        EXCLUDED_THEME_NAMES,
    ).fetchall()
    return {r[0] for r in rows}


# Kept conservative re: bound-parameter limits on the remote side — batch
# size is chosen per table so batch_size * num_columns stays well under 900.
# Exclusion is filtered in Python (not a giant SQL NOT IN list) to sidestep
# any parameter-count limit on the local or remote connection.
def push_table(local, remote, table, columns, skip_set_nums=None, batch_rows=150):
    set_num_idx = columns.index("set_num") if skip_set_nums else None
    cur = local.execute(f"SELECT {','.join(columns)} FROM {table}")
    sql_prefix = f"INSERT INTO {table} ({','.join(columns)}) VALUES "
    row_ph = "(" + ",".join("?" * len(columns)) + ")"
    n = skipped = 0
    pending = []
    while True:
        fetched = cur.fetchmany(5000)
        if not fetched:
            break
        for row in fetched:
            if skip_set_nums and row[set_num_idx] in skip_set_nums:
                skipped += 1
                continue
            pending.append(row)
        while len(pending) >= batch_rows:
            batch, pending = pending[:batch_rows], pending[batch_rows:]
            sql = sql_prefix + ",".join([row_ph] * len(batch))
            remote.execute(sql, [v for row in batch for v in row])
            n += len(batch)
            print(f"\r  {table}: {n:,} rows ({skipped:,} skipped)", end="", flush=True)
    if pending:
        sql = sql_prefix + ",".join([row_ph] * len(pending))
        remote.execute(sql, [v for row in pending for v in row])
        n += len(pending)
    remote.commit()
    print(f"\r  {table}: {n:,} rows ({skipped:,} skipped)")
    return n


def main():
    load_dotenv()
    if not LOCAL_DB.exists():
        raise SystemExit(f"{LOCAL_DB} not found — run `py -3.10 import_data.py --download` first.")
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    if not url or not token:
        raise SystemExit(
            "Set TURSO_DATABASE_URL and TURSO_AUTH_TOKEN in a .env file (see .env.example)."
        )

    local = sqlite3.connect(LOCAL_DB)
    remote = libsql.connect(database=url, auth_token=token)

    excluded = excluded_set_nums(local)
    print(f"Excluding {len(excluded):,} sets from gear/books/packs themes.")

    print("Creating schema on Turso (owned_sets preserved if it already exists)...")
    for stmt in SCHEMA.split(";"):
        stmt = stmt.strip()
        if stmt:
            remote.execute(stmt)
    remote.commit()

    t0 = time.time()
    push_table(local, remote, "themes", ["id", "name", "parent_id"], batch_rows=250)
    push_table(local, remote, "colors", ["id", "name", "rgb", "is_trans"], batch_rows=200)
    push_table(local, remote, "parts", ["part_num", "name", "part_cat_id"], batch_rows=250)
    push_table(
        local, remote, "sets",
        ["set_num", "name", "year", "theme_id", "num_parts", "img_url"],
        skip_set_nums=excluded, batch_rows=140,
    )
    push_table(
        local, remote, "set_parts",
        ["set_num", "part_num", "color_id", "quantity", "spare_quantity"],
        skip_set_nums=excluded, batch_rows=150,
    )
    push_table(
        local, remote, "set_totals",
        ["set_num", "total_parts", "distinct_parts"],
        skip_set_nums=excluded, batch_rows=250,
    )

    print(f"Done in {time.time() - t0:.0f}s.")


if __name__ == "__main__":
    main()
