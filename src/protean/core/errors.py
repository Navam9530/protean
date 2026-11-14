"""One error shape for the whole API: {"error": {"code": ..., "message": ...}}."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Every error code the API can return (the `code` field). The UI switches on these strings.
CORRUPT_FILE = "corrupt_file"
FORBIDDEN_ORIGIN = "forbidden_origin"
ALREADY_SIGNED_IN = "already_signed_in"
GITHUB_UNREACHABLE = "github_unreachable"
GITHUB_ERROR = "github_error"


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error": {"code": code, "message": message}}
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle(_: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message)
