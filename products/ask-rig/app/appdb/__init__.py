"""Writable per-user app DB (SEPARATE from the read-only corpus).

Default backend is SQLite (async via aiosqlite) — zero-infra and fully testable.
Swap to Postgres in production by setting ASKRIG_APP_DB_URL; the ORM is portable.
"""
