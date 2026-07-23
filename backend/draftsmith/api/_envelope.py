"""backend.draftsmith.api._envelope — the {ok, data, error} response shape.

Every draftsmith API response — success or failure — goes through ok()/err()
so the wire shape never drifts route to route (see rig-news's
.claude/rules/api-conventions.md for the CMS-side contract this mirrors).
Never return a bare dict/list/dataclass from a route handler directly.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def ok(data: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"ok": True, "data": jsonable_encoder(data), "error": None},
    )


def err(code: str, message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"ok": False, "data": None, "error": {"code": code, "message": message}},
    )


class ApiError(StarletteHTTPException):
    """Raise from a route to produce an enveloped error with a
    machine-readable `code`. app.py's StarletteHTTPException handler turns
    this (and any other HTTPException) into the {ok, data, error} shape."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(status_code=status_code, detail={"code": code, "message": message})
        self.code = code
        self.message = message


def detail_to_error(status_code: int, detail: Any) -> JSONResponse:
    """Shared conversion used by app.py's exception handler: an HTTPException
    (ours or Starlette's own, e.g. 404 on an unmatched route) into the
    envelope. `detail` is either our {"code","message"} dict or a bare
    string/other value from a plain HTTPException raised elsewhere."""
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        return err(detail["code"], str(detail["message"]), status_code=status_code)
    return err("http_error", str(detail), status_code=status_code)
