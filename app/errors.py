import logging

from fastapi import FastAPI, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.templating import templates

logger = logging.getLogger(__name__)


def _wants_html(request: Request) -> bool:
    return "text/html" in request.headers.get("accept", "")


def _error_page(request: Request, status_code: int, message: str):
    return templates.TemplateResponse(
        request,
        "error.html",
        {"status_code": status_code, "message": message},
        status_code=status_code,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Browsers get a friendly HTML page; API clients keep getting JSON."""

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException):
        if _wants_html(request):
            return _error_page(request, exc.status_code, str(exc.detail))
        return await http_exception_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        if _wants_html(request):
            # A bad path value such as /upload/abc is simply "not found".
            if any(err["loc"][0] == "path" for err in exc.errors()):
                return _error_page(request, 404, "Page not found.")
            return _error_page(request, 422, "The request was not valid.")
        return await request_validation_exception_handler(request, exc)

    @app.exception_handler(SQLAlchemyError)
    async def handle_database_error(request: Request, exc: SQLAlchemyError):
        # Full details go to the server log only, never to the user.
        logger.error("Database error", exc_info=exc)
        message = "Something went wrong while saving your data. Please try again."
        if _wants_html(request):
            return _error_page(request, 500, message)
        return JSONResponse(status_code=500, content={"detail": message})
