"""backend.draftsmith.api — the Door B FastAPI surface.

Job lifecycle (routes_jobs), draft review + finalize (routes_draft), one-at-
a-time flag resolution (routes_flags), and hero-image selection
(routes_images) — all behind a shared Bearer token (auth.py) and wrapped in
the {ok, data, error} envelope (_envelope.py). See app.py for the assembled
FastAPI() instance.
"""
from __future__ import annotations

from backend.draftsmith.api.app import app

__all__ = ["app"]
