"""
Govt-collector tunables.

Pulled out of inline magic constants (defect D-19) so operators can adjust
caps/timeouts via env vars without re-shipping code.

Defaults match what the family adapters and govt_collector previously
hard-coded — switching to this module is purely a refactor.
"""
from __future__ import annotations

import os


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Maximum docs harvested from one portal in one collection run. Higher
# values risk crawling the full archive on a redesigned page; lower
# values miss high-volume days. 15 has been the project default since
# Phase 3.
PER_PORTAL_CAP: int = _int("GOVT_PER_PORTAL_CAP", 15)

# Connect/read timeout for each httpx call inside an adapter, in seconds.
HTTP_TIMEOUT_SECONDS: int = _int("GOVT_HTTP_TIMEOUT_SECONDS", 30)

# Default `since_days` window for the periodic collection task.
DEFAULT_SINCE_DAYS: int = _int("GOVT_DEFAULT_SINCE_DAYS", 2)
