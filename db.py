"""Turso/libSQL connection layer.

Swaps in for the old direct sqlite3 usage with matching call shapes
(.execute/.fetchall/.fetchone/.commit, rows addressable by both name and
index) so app.py's SQL and row-handling didn't need to change.

Credentials come from TURSO_DATABASE_URL / TURSO_AUTH_TOKEN — set them in
the environment (Vercel project settings) or in a local .env file for dev.
"""

import os
import threading
from pathlib import Path

import libsql

BASE_DIR = Path(__file__).parent
_local = threading.local()


def _load_dotenv():
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


class Row:
    """dict- and tuple-like row, mirroring sqlite3.Row so app.py can use
    either row["col"] or row[0], and dict(row) for a plain dict copy."""

    __slots__ = ("_cols", "_vals")

    def __init__(self, cols, vals):
        self._cols = cols
        self._vals = vals

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._vals[key]
        return self._vals[self._cols.index(key)]

    def keys(self):
        return self._cols

    def __iter__(self):
        return iter(self._vals)

    def __len__(self):
        return len(self._vals)

    def __repr__(self):
        return repr(dict(self))


class Cursor:
    def __init__(self, raw):
        self._raw = raw
        self._cols = [c[0] for c in raw.description] if raw.description else []

    def fetchall(self):
        return [Row(self._cols, tuple(r)) for r in self._raw.fetchall()]

    def fetchone(self):
        r = self._raw.fetchone()
        return None if r is None else Row(self._cols, tuple(r))

    @property
    def rowcount(self):
        return getattr(self._raw, "rowcount", -1)


class Conn:
    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=()):
        return Cursor(self._raw.execute(sql, params))

    def commit(self):
        commit = getattr(self._raw, "commit", None)
        if commit:
            commit()


def _connect() -> Conn:
    url = os.environ["TURSO_DATABASE_URL"]
    token = os.environ["TURSO_AUTH_TOKEN"]
    return Conn(libsql.connect(database=url, auth_token=token))


def get_conn() -> Conn:
    if not hasattr(_local, "conn"):
        _local.conn = _connect()
    return _local.conn
