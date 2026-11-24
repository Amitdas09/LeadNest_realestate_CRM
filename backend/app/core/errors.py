"""Consistent error body for every API failure:
{"code": ..., "message": ..., "field_errors": {...}, "correlation_id": ...}
"""

import uuid
from contextvars import ContextVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

CORRELATION_HEADER = "X-Correlation-ID"
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="-")


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        field_errors: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.field_errors = field_errors or {}


def _body(code: str, message: str, field_errors: dict[str, str] | None = None) -> dict:
    return {
        "code": code,
        "message": message,
        "field_errors": field_errors or {},
        "correlation_id": correlation_id_var.get(),
    }


def install_error_handling(app: FastAPI) -> None:
    @app.middleware("http")
    async def correlation_id_middleware(request: Request, call_next):
        incoming = request.headers.get(CORRELATION_HEADER, "")
        cid = incoming if 0 < len(incoming) <= 64 else uuid.uuid4().hex
        token = correlation_id_var.set(cid)
        try:
            response = await call_next(request)
        finally:
            correlation_id_var.reset(token)
        response.headers[CORRELATION_HEADER] = cid
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(exc.code, exc.message, exc.field_errors),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError):
        field_errors: dict[str, str] = {}
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", []) if p not in ("body", "query", "path")]
            field_errors[".".join(loc) or "request"] = err.get("msg", "Invalid value")
        return JSONResponse(
            status_code=422,
            content=_body("validation_error", "Some fields are invalid.", field_errors),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(f"http_{exc.status_code}", str(exc.detail)),
        )
