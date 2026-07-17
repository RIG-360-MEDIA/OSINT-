"""Make the tests directory importable (so ``import _fakes`` works) and set the
test environment before any v1 module is imported."""
from __future__ import annotations

import os
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))                 # for `import _fakes`
sys.path.insert(0, str(_HERE.parents[1]))      # backend/ (for `import db`, `v1`, ...)

os.environ.setdefault("OSINT_DB_URL", "postgresql+asyncpg://u:p@localhost/db")
os.environ.setdefault("OSINT_APIKEY_HASH_SECRET", "unit-test-secret")
os.environ.setdefault("OSINT_ENVIRONMENT", "development")
