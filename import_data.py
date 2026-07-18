"""LegoLog importer — local build step.

Loads the Rebrickable CSV dumps from ./data into a local legolog.db (SQLite)
and precomputes the `set_parts` table used by the buildability engine. This
is a build artifact, not what the app reads at runtime — run push_to_turso.py
afterward to push the relevant tables to Turso.

Run with:  py -3.10 import_data.py [--download]

--download fetches fresh copies of the CSVs from cdn.rebrickable.com first.

The user's collection (`owned_sets`) is preserved across re-imports.
"""

import argparse
import csv
import gzip
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = BASE_DIR / "legolog.db"

DOWNLOAD_BASE = "https://cdn.rebrickable.com/media/downloads/"

# table -> (csv file, columns pulled from the CSV header)
TABLES = {
    "themes": ("themes.csv.gz", ["id", "name", "parent_id"]),
    "colors": ("colors.csv.gz", ["id", "name", "rgb", "is_trans"]),
    "parts": ("parts.csv.gz", ["part_num", "name", "part_cat_id"]),
    "sets": ("sets.csv.gz", ["set_num", "name", "year", "theme_id", "num_parts", "img_url"]),
    "minifigs": ("minifigs.csv.gz", ["fig_num", "name", "num_parts", "img_url"]),
    "inventories": ("inventories.csv.gz", ["id", "version", "set_num"]),
    "inventory_parts": (
        "inventory_parts.csv.gz",
        ["inventory_id", "part_num", "color_id", "quantity", "is_spare", "img_url"],
    ),
    "inventory_minifigs": ("inventory_minifigs.csv.gz", ["inventory_id", "fig_num", "quantity"]),
}

SCHEMA = """
DROP TABLE IF EXISTS themes;
DROP TABLE IF EXISTS colors;
DROP TABLE IF EXISTS parts;
DROP TABLE IF EXISTS sets;
DROP TABLE IF EXISTS minifigs;
DROP TABLE IF EXISTS inventories;
DROP TABLE IF EXISTS inventory_parts;
DROP TABLE IF EXISTS inventory_minifigs;
DROP TABLE IF EXISTS set_parts;

CREATE TABLE themes (id INTEGER PRIMARY KEY, name TEXT, parent_id INTEGER);
CREATE TABLE colors (id INTEGER PRIMARY KEY, name TEXT, rgb TEXT, is_trans TEXT);
CREATE TABLE parts (part_num TEXT PRIMARY KEY, name TEXT, part_cat_id INTEGER);
CREATE TABLE sets (
    set_num TEXT PRIMARY KEY, name TEXT, year INTEGER,
    theme_id INTEGER, num_parts INTEGER, img_url TEXT
);
CREATE TABLE minifigs (fig_num TEXT PRIMARY KEY, name TEXT, num_parts INTEGER, img_url TEXT);
CREATE TABLE inventories (id INTEGER PRIMARY KEY, version INTEGER, set_num TEXT);
CREATE TABLE inventory_parts (
    inventory_id INTEGER, part_num TEXT, color_id INTEGER,
    quantity INTEGER, is_spare TEXT, img_url TEXT
);
CREATE TABLE inventory_minifigs (inventory_id INTEGER, fig_num TEXT, quantity INTEGER);

CREATE TABLE IF NOT EXISTS owned_sets (
    set_num TEXT PRIMARY KEY,
    quantity INTEGER NOT NULL DEFAULT 1,
    added_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

# set_parts: one row per (set_num, part_num, color_id).
#   quantity       = parts required to build the set (non-spare, minifigs expanded)
#   spare_quantity = extra spare parts included in the box (owned but not required)
DERIVED = """
CREATE INDEX idx_inv_parts_inv ON inventory_parts(inventory_id);
CREATE INDEX idx_inv_minifigs_inv ON inventory_minifigs(inventory_id);
CREATE INDEX idx_inventories_set ON inventories(set_num);

-- Latest inventory version per set / minifig
CREATE TEMP TABLE latest_inv AS
SELECT set_num, id FROM (
    SELECT set_num, id,
           ROW_NUMBER() OVER (PARTITION BY set_num ORDER BY version DESC) AS rn
    FROM inventories
) WHERE rn = 1;
CREATE INDEX temp.idx_latest_inv ON latest_inv(set_num);

-- Direct parts for every set AND minifig
CREATE TEMP TABLE direct_parts AS
SELECT li.set_num, ip.part_num, ip.color_id,
       SUM(CASE WHEN ip.is_spare IN ('f', 'False') THEN ip.quantity ELSE 0 END) AS quantity,
       SUM(CASE WHEN ip.is_spare IN ('t', 'True') THEN ip.quantity ELSE 0 END) AS spare_quantity
FROM latest_inv li
JOIN inventory_parts ip ON ip.inventory_id = li.id
GROUP BY li.set_num, ip.part_num, ip.color_id;
CREATE INDEX temp.idx_direct_parts ON direct_parts(set_num);

-- Sets' minifig parts, expanded one level (minifigs cannot contain minifigs)
CREATE TABLE set_parts AS
SELECT set_num, part_num, color_id,
       SUM(quantity) AS quantity,
       SUM(spare_quantity) AS spare_quantity
FROM (
    SELECT dp.set_num, dp.part_num, dp.color_id, dp.quantity, dp.spare_quantity
    FROM direct_parts dp
    WHERE dp.set_num IN (SELECT set_num FROM sets)
    UNION ALL
    SELECT li.set_num, fp.part_num, fp.color_id,
           im.quantity * fp.quantity, im.quantity * fp.spare_quantity
    FROM latest_inv li
    JOIN inventory_minifigs im ON im.inventory_id = li.id
    JOIN direct_parts fp ON fp.set_num = im.fig_num
    WHERE li.set_num IN (SELECT set_num FROM sets)
)
GROUP BY set_num, part_num, color_id;

CREATE INDEX idx_set_parts_set ON set_parts(set_num);
-- covering index: donor ranking scans read everything from the index alone
CREATE INDEX idx_set_parts_part ON set_parts(part_num, color_id, set_num, quantity, spare_quantity);

-- Buildable totals per set (what the engine compares against)
DROP TABLE IF EXISTS set_totals;
CREATE TABLE set_totals AS
SELECT set_num, SUM(quantity) AS total_parts, COUNT(*) AS distinct_parts
FROM set_parts GROUP BY set_num;
CREATE UNIQUE INDEX idx_set_totals ON set_totals(set_num);
"""


def download():
    DATA_DIR.mkdir(exist_ok=True)
    for _, (fname, _) in TABLES.items():
        url = DOWNLOAD_BASE + fname
        dest = DATA_DIR / fname
        print(f"  downloading {fname} ...")
        urllib.request.urlretrieve(url, dest)


def load_csv(con, table, fname, cols):
    path = DATA_DIR / fname
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        placeholders = ",".join("?" * len(cols))
        sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
        batch = []
        n = 0
        for row in reader:
            batch.append(tuple(row[c] if row[c] != "" else None for c in cols))
            if len(batch) >= 50000:
                con.executemany(sql, batch)
                n += len(batch)
                batch = []
        if batch:
            con.executemany(sql, batch)
            n += len(batch)
    print(f"  {table}: {n:,} rows")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true", help="fetch fresh CSVs first")
    args = ap.parse_args()

    if args.download:
        download()

    missing = [f for _, (f, _) in TABLES.items() if not (DATA_DIR / f).exists()]
    if missing:
        sys.exit(f"Missing files in {DATA_DIR}: {missing}. Run with --download.")

    t0 = time.time()
    con = sqlite3.connect(DB_PATH)
    con.executescript("PRAGMA journal_mode=WAL; PRAGMA synchronous=OFF;")
    print("Creating schema (owned_sets preserved) ...")
    con.executescript(SCHEMA)

    print("Loading CSVs ...")
    for table, (fname, cols) in TABLES.items():
        load_csv(con, table, fname, cols)
    con.commit()

    print("Building set_parts (minifigs expanded, spares tracked) ...")
    con.executescript(DERIVED)
    con.commit()

    # Drop owned sets that no longer exist in the catalog (shouldn't happen)
    con.execute("DELETE FROM owned_sets WHERE set_num NOT IN (SELECT set_num FROM sets)")
    con.commit()

    n_sets = con.execute("SELECT COUNT(*) FROM sets").fetchone()[0]
    n_sp = con.execute("SELECT COUNT(*) FROM set_parts").fetchone()[0]
    con.close()
    print(f"Done in {time.time() - t0:.1f}s — {n_sets:,} sets, {n_sp:,} set_part rows -> {DB_PATH}")


if __name__ == "__main__":
    main()
