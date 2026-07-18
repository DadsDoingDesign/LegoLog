"""Vercel entrypoint. Vercel's Python runtime reliably forwards full sub-paths
(/api/*) only when the FastAPI app lives at api/index.py — a root-level app.py
alone only serves "/" correctly. Local dev still runs `uvicorn app:app`
directly against the root module; this just re-exports the same app object.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app  # noqa: E402,F401
