"""LegoLog — which sets can I build from the parts I own?

FastAPI backend over a Turso (libSQL) database — catalog + set_parts pushed
by push_to_turso.py, owned_sets read/written live.

Run with:  py -3.10 -m uvicorn app:app --port 8100
"""

import itertools
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from db import get_conn as db

BASE_DIR = Path(__file__).parent

app = FastAPI(title="LegoLog")

# Theme branches whose "sets" aren't buildable models: parts packs, gear, books.
# A set is excluded if its theme or ANY ancestor theme is named one of these.
EXCLUDED_THEME_NAMES = (
    "Service Packs",
    "Bulk Bricks",
    "Supplemental",
    "VIP Add-On Packs",
    "Gear",
    "Books",
)

_excluded_lock = threading.Lock()
_excluded_cache: frozenset | None = None


def excluded_sets() -> frozenset:
    """Lazily memoized per warm instance — avoids relying on startup events
    firing reliably across serverless cold starts."""
    global _excluded_cache
    if _excluded_cache is None:
        with _excluded_lock:
            if _excluded_cache is None:
                placeholders = ",".join("?" * len(EXCLUDED_THEME_NAMES))
                rows = db().execute(
                    f"""WITH RECURSIVE bad(id) AS (
                            SELECT id FROM themes WHERE name IN ({placeholders})
                            UNION
                            SELECT t.id FROM themes t JOIN bad b ON t.parent_id = b.id
                        )
                        SELECT set_num FROM sets WHERE theme_id IN (SELECT id FROM bad)""",
                    EXCLUDED_THEME_NAMES,
                ).fetchall()
                _excluded_cache = frozenset(r["set_num"] for r in rows)
    return _excluded_cache


# ---------------------------------------------------------------- collection

class OwnedSet(BaseModel):
    set_num: str
    quantity: int = 1


# Buildability results are cached until the collection changes.
_cache_lock = threading.Lock()
_cache: dict = {}  # key -> list of rows
_collection_version = 0


def _bump_version():
    global _collection_version
    with _cache_lock:
        _collection_version += 1
        _cache.clear()


@app.get("/api/collection")
def get_collection():
    rows = db().execute(
        """SELECT os.set_num, os.quantity, s.name, s.year, s.num_parts, s.img_url,
                  t.name AS theme, st.total_parts
           FROM owned_sets os
           JOIN sets s ON s.set_num = os.set_num
           LEFT JOIN themes t ON t.id = s.theme_id
           LEFT JOIN set_totals st ON st.set_num = os.set_num
           ORDER BY os.added_at DESC"""
    ).fetchall()
    total_parts = db().execute(
        """SELECT COALESCE(SUM((sp.quantity + sp.spare_quantity) * os.quantity), 0)
           FROM owned_sets os JOIN set_parts sp ON sp.set_num = os.set_num"""
    ).fetchone()[0]
    distinct = db().execute(
        """SELECT COUNT(*) FROM (
             SELECT 1 FROM owned_sets os JOIN set_parts sp ON sp.set_num = os.set_num
             GROUP BY sp.part_num, sp.color_id)"""
    ).fetchone()[0]
    return {
        "sets": [dict(r) for r in rows],
        "stats": {
            "set_count": sum(r["quantity"] for r in rows),
            "distinct_sets": len(rows),
            "total_parts": total_parts,
            "distinct_parts": distinct,
        },
    }


@app.post("/api/collection")
def add_set(item: OwnedSet):
    if item.quantity < 1:
        raise HTTPException(400, "quantity must be >= 1")
    exists = db().execute("SELECT 1 FROM sets WHERE set_num = ?", (item.set_num,)).fetchone()
    if not exists:
        raise HTTPException(404, f"unknown set {item.set_num}")
    db().execute(
        """INSERT INTO owned_sets (set_num, quantity) VALUES (?, ?)
           ON CONFLICT(set_num) DO UPDATE SET quantity = quantity + excluded.quantity""",
        (item.set_num, item.quantity),
    )
    db().commit()
    _bump_version()
    return {"ok": True}


@app.put("/api/collection/{set_num}")
def set_quantity(set_num: str, item: OwnedSet):
    if item.quantity < 1:
        return remove_set(set_num)
    # Checked via a preliminary SELECT rather than UPDATE rowcount — a remote
    # libSQL connection isn't guaranteed to report affected-row counts.
    exists = db().execute("SELECT 1 FROM owned_sets WHERE set_num = ?", (set_num,)).fetchone()
    if not exists:
        raise HTTPException(404, "not in collection")
    db().execute(
        "UPDATE owned_sets SET quantity = ? WHERE set_num = ?", (item.quantity, set_num)
    )
    db().commit()
    _bump_version()
    return {"ok": True}


@app.delete("/api/collection/{set_num}")
def remove_set(set_num: str):
    db().execute("DELETE FROM owned_sets WHERE set_num = ?", (set_num,))
    db().commit()
    _bump_version()
    return {"ok": True}


# ---------------------------------------------------------------- search

@app.get("/api/search")
def search_sets(q: str = Query(min_length=1), limit: int = 25):
    like = f"%{q}%"
    # set-number prefix matches first, then name matches, biggest sets first
    rows = db().execute(
        """SELECT s.set_num, s.name, s.year, s.num_parts, s.img_url, t.name AS theme,
                  os.quantity AS owned
           FROM sets s
           LEFT JOIN themes t ON t.id = s.theme_id
           LEFT JOIN owned_sets os ON os.set_num = s.set_num
           WHERE s.set_num LIKE ? OR s.name LIKE ?
           ORDER BY (s.set_num LIKE ?) DESC, s.num_parts DESC
           LIMIT ?""",
        (like, like, q + "%", limit),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- buildable

def _compute_buildable(ignore_color: bool) -> list:
    """Coverage for every candidate set vs the pooled owned parts."""
    if ignore_color:
        owned_cte = """
            owned AS (
                SELECT sp.part_num, SUM((sp.quantity + sp.spare_quantity) * os.quantity) AS qty
                FROM owned_sets os JOIN set_parts sp ON sp.set_num = os.set_num
                GROUP BY sp.part_num
            ),
            req AS (
                SELECT set_num, part_num, SUM(quantity) AS quantity
                FROM set_parts GROUP BY set_num, part_num
            )"""
        join = "LEFT JOIN owned o ON o.part_num = req.part_num"
    else:
        owned_cte = """
            owned AS (
                SELECT sp.part_num, sp.color_id,
                       SUM((sp.quantity + sp.spare_quantity) * os.quantity) AS qty
                FROM owned_sets os JOIN set_parts sp ON sp.set_num = os.set_num
                GROUP BY sp.part_num, sp.color_id
            ),
            req AS (SELECT set_num, part_num, color_id, quantity FROM set_parts)"""
        join = "LEFT JOIN owned o ON o.part_num = req.part_num AND o.color_id = req.color_id"

    sql = f"""
        WITH {owned_cte}
        SELECT req.set_num,
               SUM(MIN(req.quantity, COALESCE(o.qty, 0))) AS have_parts,
               SUM(req.quantity) AS total_parts,
               SUM(req.quantity > COALESCE(o.qty, 0)) AS missing_lots
        FROM req {join}
        GROUP BY req.set_num
        HAVING have_parts > 0
    """
    return [dict(r) for r in db().execute(sql).fetchall()]


@app.get("/api/buildable")
def buildable(
    min_coverage: float = 1.0,
    min_parts: int = 20,
    theme_id: int | None = None,
    include_owned: bool = False,
    ignore_color: bool = False,
    sort: str = "coverage",
    limit: int = 200,
    offset: int = 0,
):
    key = ("buildable", _collection_version, ignore_color)
    with _cache_lock:
        rows = _cache.get(key)
    if rows is None:
        rows = _compute_buildable(ignore_color)
        with _cache_lock:
            _cache[key] = rows

    sets_meta = {
        r["set_num"]: dict(r)
        for r in db().execute(
            """SELECT s.set_num, s.name, s.year, s.theme_id, s.img_url, t.name AS theme,
                      os.quantity AS owned
               FROM sets s LEFT JOIN themes t ON t.id = s.theme_id
               LEFT JOIN owned_sets os ON os.set_num = s.set_num"""
        ).fetchall()
    }

    out = []
    for r in rows:
        meta = sets_meta.get(r["set_num"])
        if meta is None or r["total_parts"] < min_parts:
            continue
        if r["set_num"] in excluded_sets():
            continue
        if not include_owned and meta["owned"]:
            continue
        if theme_id is not None and meta["theme_id"] != theme_id:
            continue
        coverage = r["have_parts"] / r["total_parts"]
        if coverage < min_coverage:
            continue
        out.append({**meta, **r, "coverage": round(coverage, 4)})

    if sort == "parts":
        out.sort(key=lambda x: -x["total_parts"])
    elif sort == "year":
        out.sort(key=lambda x: -(x["year"] or 0))
    else:
        out.sort(key=lambda x: (-x["coverage"], -x["total_parts"]))

    return {"total": len(out), "results": out[offset : offset + limit]}


@app.get("/api/sets/{set_num}/missing")
def missing_parts(set_num: str, ignore_color: bool = False):
    """What's missing (and what's covered) to build set_num from the pool."""
    if ignore_color:
        sql = """
            WITH owned AS (
                SELECT sp.part_num, SUM((sp.quantity + sp.spare_quantity) * os.quantity) AS qty
                FROM owned_sets os JOIN set_parts sp ON sp.set_num = os.set_num
                GROUP BY sp.part_num
            ),
            req AS (
                SELECT part_num, SUM(quantity) AS quantity FROM set_parts
                WHERE set_num = ? GROUP BY part_num
            )
            SELECT req.part_num, NULL AS color_id, NULL AS color, NULL AS rgb,
                   p.name AS part_name, req.quantity AS need,
                   MIN(req.quantity, COALESCE(o.qty, 0)) AS have
            FROM req
            LEFT JOIN owned o ON o.part_num = req.part_num
            LEFT JOIN parts p ON p.part_num = req.part_num
            ORDER BY (need - have) DESC, need DESC"""
        rows = db().execute(sql, (set_num,)).fetchall()
    else:
        sql = """
            WITH owned AS (
                SELECT sp.part_num, sp.color_id,
                       SUM((sp.quantity + sp.spare_quantity) * os.quantity) AS qty
                FROM owned_sets os JOIN set_parts sp ON sp.set_num = os.set_num
                GROUP BY sp.part_num, sp.color_id
            )
            SELECT sp.part_num, sp.color_id, c.name AS color, c.rgb,
                   p.name AS part_name, sp.quantity AS need,
                   MIN(sp.quantity, COALESCE(o.qty, 0)) AS have
            FROM set_parts sp
            LEFT JOIN owned o ON o.part_num = sp.part_num AND o.color_id = sp.color_id
            LEFT JOIN parts p ON p.part_num = sp.part_num
            LEFT JOIN colors c ON c.id = sp.color_id
            WHERE sp.set_num = ?
            ORDER BY (need - have) DESC, need DESC"""
        rows = db().execute(sql, (set_num,)).fetchall()

    parts = [dict(r) for r in rows]
    return {
        "set_num": set_num,
        "missing": [p for p in parts if p["have"] < p["need"]],
        "covered_lots": sum(1 for p in parts if p["have"] >= p["need"]),
        "total_lots": len(parts),
    }


def _gap_lots(set_num: str, ignore_color: bool) -> list[tuple]:
    """Missing lots for set_num vs the owned pool: [(part_num, color_id, short)]."""
    if ignore_color:
        sql = """
            WITH owned AS (
                SELECT sp.part_num, SUM((sp.quantity + sp.spare_quantity) * os.quantity) AS qty
                FROM owned_sets os JOIN set_parts sp ON sp.set_num = os.set_num
                GROUP BY sp.part_num
            ),
            req AS (
                SELECT part_num, SUM(quantity) AS quantity FROM set_parts
                WHERE set_num = ? GROUP BY part_num
            )
            SELECT req.part_num, -1, req.quantity - COALESCE(o.qty, 0) AS short
            FROM req LEFT JOIN owned o ON o.part_num = req.part_num
            WHERE short > 0"""
    else:
        sql = """
            WITH owned AS (
                SELECT sp.part_num, sp.color_id,
                       SUM((sp.quantity + sp.spare_quantity) * os.quantity) AS qty
                FROM owned_sets os JOIN set_parts sp ON sp.set_num = os.set_num
                GROUP BY sp.part_num, sp.color_id
            )
            SELECT sp.part_num, sp.color_id, sp.quantity - COALESCE(o.qty, 0) AS short
            FROM set_parts sp
            LEFT JOIN owned o ON o.part_num = sp.part_num AND o.color_id = sp.color_id
            WHERE sp.set_num = ? AND short > 0"""
    return [tuple(r) for r in db().execute(sql, (set_num,)).fetchall()]


# Remote round trips are the bottleneck here (each one costs real network
# latency, unlike a local sqlite file), so every helper below fetches its
# data in exactly one query — a VALUES CTE standing in for what would be a
# WHERE IN (...) or a temp-table join against a small, per-call set of lots.


def _values_cte(name: str, cols: str, rows: list[tuple]) -> tuple[str, list]:
    placeholders = ",".join("(" + ",".join("?" * len(rows[0])) + ")" for _ in rows)
    params = [v for row in rows for v in row]
    return f"{name}({cols}) AS (VALUES {placeholders})", params


def _rarity_counts(con, lots: dict, ignore_color: bool) -> dict:
    """One round trip: how many sets hold each lot at all (any quantity)."""
    items = list(lots.items())
    if ignore_color:
        cte, params = _values_cte("g", "part_num", [(p,) for (p, _c), _s in items])
        rows = con.execute(
            f"""WITH {cte}
                SELECT g.part_num, COUNT(sp.set_num) AS n
                FROM g LEFT JOIN set_parts sp ON sp.part_num = g.part_num
                GROUP BY g.part_num""",
            params,
        ).fetchall()
        return {(r["part_num"], -1): r["n"] for r in rows}
    cte, params = _values_cte("g", "part_num, color_id", [(p, c) for (p, c), _s in items])
    rows = con.execute(
        f"""WITH {cte}
            SELECT g.part_num, g.color_id, COUNT(sp.set_num) AS n
            FROM g LEFT JOIN set_parts sp
                ON sp.part_num = g.part_num AND sp.color_id = g.color_id
            GROUP BY g.part_num, g.color_id""",
        params,
    ).fetchall()
    return {(r["part_num"], r["color_id"]): r["n"] for r in rows}


def _rank_donors_for_lots(con, lots: dict, rarity: dict, target: str, ignore_color: bool, limit: int) -> list[str]:
    """Rank donor sets by how much of `lots` they cover, joining only the rarest
    lots so common parts (held by thousands of sets) can't blow up the query."""
    counted = sorted((rarity.get((p, c), 0), p, c, short) for (p, c), short in lots.items())
    selected, budget = [], 150_000
    for n, p, c, short in counted:
        if selected and (len(selected) >= 30 or n > budget):
            break
        selected.append((p, c, short))
        budget -= n

    cte, values_params = _values_cte("g", "part_num, color_id, short", selected)
    color_join = "" if ignore_color else "AND sp.color_id = g.color_id"
    # set_parts is unique per (set, part, color), so COUNT(*) = distinct lots hit
    rows = con.execute(
        f"""WITH {cte}
            SELECT sp.set_num, SUM(MIN(sp.quantity + sp.spare_quantity, g.short)) AS cover,
                   COUNT(*) AS lots_hit
            FROM g
            JOIN set_parts sp ON sp.part_num = g.part_num {color_join}
            WHERE sp.set_num != ?
            GROUP BY sp.set_num
            ORDER BY lots_hit DESC, cover DESC
            LIMIT ?""",
        (*values_params, target, limit),
    ).fetchall()
    return [r["set_num"] for r in rows if r["set_num"] not in excluded_sets()]


def _bottleneck_suppliers(con, gap_map: dict, rarity: dict, target: str, ignore_color: bool) -> set:
    """One round trip: lots only a handful of sets can supply in full are
    mandatory candidates — generic ranking can miss them. Pre-filtered to
    lots with <=300 holders so a common part can't blow up the result size."""
    scarce = {lot: short for lot, short in gap_map.items() if rarity.get(lot, 0) <= 300}
    if not scarce:
        return set()
    cte, params = _values_cte(
        "g", "part_num, color_id, short", [(p, c, s) for (p, c), s in scarce.items()]
    )
    color_join = "" if ignore_color else "AND sp.color_id = g.color_id"
    rows = con.execute(
        f"""WITH {cte}
            SELECT g.part_num, g.color_id, sp.set_num
            FROM g JOIN set_parts sp ON sp.part_num = g.part_num {color_join}
            WHERE sp.set_num != ?
            GROUP BY g.part_num, g.color_id, sp.set_num
            HAVING SUM(sp.quantity + sp.spare_quantity) >= g.short""",
        (*params, target),
    ).fetchall()
    by_lot = {}
    for r in rows:
        by_lot.setdefault((r["part_num"], r["color_id"]), []).append(r["set_num"])
    must_have = set()
    for suppliers in by_lot.values():
        if 0 < len(suppliers) <= 20:
            must_have.update(s for s in suppliers[:5] if s not in excluded_sets())
    return must_have


def _donor_gap_lots(con, set_nums, gap_map, ignore_color: bool) -> dict:
    """For each donor set: {gap lot -> quantity it holds}. One batched query."""
    out = {sn: {} for sn in set_nums}
    if not set_nums:
        return out
    ph = ",".join("?" * len(set_nums))
    rows = con.execute(
        f"""SELECT set_num, part_num, color_id, quantity + spare_quantity AS q
            FROM set_parts WHERE set_num IN ({ph})""",
        set_nums,
    ).fetchall()
    for r in rows:
        key = (r["part_num"], -1 if ignore_color else r["color_id"])
        if key in gap_map:
            d = out[r["set_num"]]
            d[key] = d.get(key, 0) + r["q"]
    return out


@app.get("/api/sets/{set_num}/fill")
def fill_options(set_num: str, ignore_color: bool = False):
    """Suggest sets (singles and pairs) to buy that would cover this set's gap."""
    key = ("fill", _collection_version, set_num, ignore_color)
    with _cache_lock:
        cached = _cache.get(key)
    if cached is not None:
        return cached

    gap = _gap_lots(set_num, ignore_color)
    if not gap:
        return {"gap_parts": 0, "singles": [], "pairs": [], "near_pairs": [], "partial": []}
    gap_map = {(p, c): s for p, c, s in gap}
    gap_parts = sum(gap_map.values())
    con = db()

    rarity = _rarity_counts(con, gap_map, ignore_color)
    pool = _rank_donors_for_lots(con, gap_map, rarity, set_num, ignore_color, 60)[:40]
    if not pool:
        return {"gap_parts": gap_parts, "singles": [], "pairs": [], "near_pairs": [], "partial": []}

    # Bottleneck lots: if only a handful of sets can supply a lot in full,
    # those sets are mandatory candidates — generic ranking can miss them.
    must_have = _bottleneck_suppliers(con, gap_map, rarity, set_num, ignore_color)
    pool.extend(s for s in must_have if s not in pool)

    donor_lots = _donor_gap_lots(con, pool, gap_map, ignore_color)

    def coverage(*lots_dicts) -> int:
        return sum(
            min(short, sum(d.get(lot, 0) for d in lots_dicts))
            for lot, short in gap_map.items()
        )

    cover = {sn: coverage(donor_lots[sn]) for sn in pool}

    # Expand the pool with complements: for the best partial donors, find sets
    # that specifically cover what THEY still leave missing. Only needed when
    # no single set already covers everything. Complement lookups (rank calls)
    # still cost one round trip each, but their donor-lot fetches are batched
    # into a single call after the loop instead of one per complement.
    new_comps = []
    if not any(c >= gap_parts for c in cover.values()):
        expand = sorted((s for s in pool if cover[s] < gap_parts), key=lambda s: -cover[s])[:4]
        for first in expand:
            residual = {
                lot: short - donor_lots[first].get(lot, 0)
                for lot, short in gap_map.items()
                if short > donor_lots[first].get(lot, 0)
            }
            residual_rarity = _rarity_counts(con, residual, ignore_color)
            for comp in _rank_donors_for_lots(con, residual, residual_rarity, set_num, ignore_color, 10):
                if comp not in cover and comp not in new_comps:
                    new_comps.append(comp)
    if new_comps:
        donor_lots.update(_donor_gap_lots(con, new_comps, gap_map, ignore_color))
        pool.extend(new_comps)
        cover.update({comp: coverage(donor_lots[comp]) for comp in new_comps})

    ph = ",".join("?" * len(pool))
    meta = {
        r["set_num"]: dict(r)
        for r in con.execute(
            f"""SELECT s.set_num, s.name, s.year, s.num_parts, s.img_url, t.name AS theme
                FROM sets s LEFT JOIN themes t ON t.id = s.theme_id
                WHERE s.set_num IN ({ph})""",
            pool,
        ).fetchall()
    }

    def donor(sn: str) -> dict:
        return {**meta[sn], "covers": cover[sn], "covers_pct": round(cover[sn] / gap_parts, 4)}

    full_singles = sorted(
        (s for s in pool if cover[s] >= gap_parts), key=lambda s: meta[s]["num_parts"]
    )
    singles = [donor(s) for s in full_singles[:5]]

    partials = sorted((s for s in pool if cover[s] < gap_parts), key=lambda s: -cover[s])
    # keep bottleneck suppliers in the pair search even if their total cover is low
    pair_pool = partials[:50] + [s for s in partials[50:] if s in must_have]
    scored_pairs = []
    for a, b in itertools.combinations(pair_pool, 2):
        if cover[a] + cover[b] < gap_parts:
            continue  # cheap upper bound before the exact lot check
        if coverage(donor_lots[a], donor_lots[b]) >= gap_parts:
            scored_pairs.append((meta[a]["num_parts"] + meta[b]["num_parts"], a, b))
    scored_pairs.sort()
    pairs = [[donor(a), donor(b)] for _, a, b in scored_pairs[:5]]

    # Full coverage impossible (e.g. a part exclusive to this set)? Show the
    # closest pairings by combined coverage instead.
    near_pairs, partial = [], []
    if not singles and not pairs:
        best = sorted(pool, key=lambda s: -cover[s])[:12]
        combos = sorted(
            (
                (-coverage(donor_lots[a], donor_lots[b]), meta[a]["num_parts"] + meta[b]["num_parts"], a, b)
                for a, b in itertools.combinations(best, 2)
            ),
        )[:5]
        near_pairs = [
            [donor(a), donor(b), {"combined": -neg, "combined_pct": round(-neg / gap_parts, 4)}]
            for neg, _, a, b in combos
        ]
        partial = [donor(s) for s in best[:5]]

    result = {
        "gap_parts": gap_parts,
        "singles": singles,
        "pairs": pairs,
        "near_pairs": near_pairs,
        "partial": partial,
    }
    with _cache_lock:
        _cache[key] = result
    return result


@app.get("/api/themes")
def themes():
    rows = db().execute(
        """SELECT t.id, t.name, COUNT(s.set_num) AS n
           FROM themes t JOIN sets s ON s.theme_id = t.id
           GROUP BY t.id ORDER BY t.name"""
    ).fetchall()
    # hide theme branches whose sets are excluded from buildable results anyway
    bad_ids = {
        r[0]
        for r in db().execute(
            f"""WITH RECURSIVE bad(id) AS (
                    SELECT id FROM themes WHERE name IN ({','.join('?' * len(EXCLUDED_THEME_NAMES))})
                    UNION
                    SELECT t.id FROM themes t JOIN bad b ON t.parent_id = b.id
                )
                SELECT id FROM bad""",
            EXCLUDED_THEME_NAMES,
        ).fetchall()
    }
    return [dict(r) for r in rows if r["id"] not in bad_ids]


# ---------------------------------------------------------------- static
#
# On Vercel, public/** is served straight from the CDN and never reaches this
# function. This route only matters for local dev (uvicorn doesn't know about
# that convention).


@app.get("/")
def index():
    # public/index.html isn't bundled into the Vercel function (Vercel serves
    # public/** straight from its CDN and normally never reaches this route
    # for "/" at all) — but it does exist on disk for local uvicorn dev.
    local_path = BASE_DIR / "public" / "index.html"
    if local_path.exists():
        return FileResponse(local_path)
    return RedirectResponse("/index.html")
