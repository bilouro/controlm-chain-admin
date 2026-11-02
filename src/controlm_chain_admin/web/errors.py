"""One exception handler: typed core errors become HTTP statuses with a common body."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from controlm_chain_admin.core.errors import (
    ChainError,
    ChangeConflict,
    DuplicateName,
    EnvironmentRequired,
    GitError,
    InvalidChange,
    ModelError,
    NotAChainRepo,
    NothingToPackage,
    OrderConflict,
    SelectionConflict,
    UnknownEnvironment,
    UnresolvedConstant,
    UnsafeName,
    XmlFormatError,
)

log = logging.getLogger("ctmchain.web")

_STATUS: tuple[tuple[type[ChainError], int], ...] = (
    (InvalidChange, 422),  # before ModelError, its base class
    (ChangeConflict, 409),
    (SelectionConflict, 409),  # before GitError, its base class
    (GitError, 422),
    (ModelError, 404),
    (UnknownEnvironment, 404),
    (NotAChainRepo, 503),
    (DuplicateName, 409),
    (OrderConflict, 409),
    (UnsafeName, 422),
    (EnvironmentRequired, 422),
    (XmlFormatError, 422),
    (UnresolvedConstant, 422),
    (NothingToPackage, 422),
)


def status_for(error: ChainError) -> int:
    for kind, status in _STATUS:
        if isinstance(error, kind):
            return status
    return 400


def _body(error: str, message: str, detail: object = None) -> dict[str, object]:
    return {"error": error, "message": message, "detail": detail}


def register(app: FastAPI) -> None:
    @app.exception_handler(ChainError)
    async def chain_error(_: Request, exc: ChainError) -> JSONResponse:
        detail = getattr(exc, "detail", None)
        return JSONResponse(
            status_code=status_for(exc), content=_body(type(exc).__name__, str(exc), detail)
        )

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unexpected error", exc_info=exc)
        return JSONResponse(
            status_code=500, content=_body("InternalError", "unexpected error; see the server log")
        )
