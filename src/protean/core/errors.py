"""One error shape for the whole API: {"error": {"code": ..., "message": ...}}."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# Every error code the API can return (the `code` field). The UI switches on these strings.
CORRUPT_FILE = "corrupt_file"
FORBIDDEN_ORIGIN = "forbidden_origin"
ALREADY_SIGNED_IN = "already_signed_in"
GITHUB_UNREACHABLE = "github_unreachable"
GITHUB_ERROR = "github_error"
RATE_LIMITED = "rate_limited"
REPO_NOT_FOUND = "repo_not_found"
INVALID_FAMILY = "invalid_family"
TOO_LARGE = "too_large"
NOT_FOUND = "not_found"
ALREADY_EXISTS = "already_exists"
CONFLICT = "conflict"
UNRESOLVED = "unresolved_conflicts"
NO_SPACE = "no_space"
INVALID_DRAFT = "invalid_draft"
INVALID_REQUEST = "invalid_request"
NOT_SIGNED_IN = "not_signed_in"
NOT_OWNER = "not_owner"
DRAFT_EXISTS = "draft_exists"
NOT_PROTEAN_REPO = "not_protean_repo"
INTERNAL = "internal_error"


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

    @app.exception_handler(RequestValidationError)
    async def _handle_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        """A request FastAPI could not parse (bad path, query or body) uses the same shape."""
        problems = [
            ".".join(str(p) for p in e["loc"] if p not in ("body", "query", "path"))
            + f": {e['msg']}"
            for e in exc.errors()[:3]
        ]
        return error_response(422, INVALID_REQUEST, "; ".join(problems))
