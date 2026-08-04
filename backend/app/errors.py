from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from app.providers import ProviderResponseError, ProviderUnavailableError


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        self.headers = headers


class AuthenticationError(AppError):
    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(
            "AUTHENTICATION_FAILED",
            message,
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )


class PermissionDeniedError(AppError):
    def __init__(self, message: str = "Insufficient permissions") -> None:
        super().__init__("PERMISSION_DENIED", message, status_code=403)


class NotFoundError(AppError):
    def __init__(self, resource: str, identifier: object) -> None:
        super().__init__(
            "RESOURCE_NOT_FOUND",
            f"{resource} was not found",
            status_code=404,
            details={"identifier": str(identifier)},
        )


class ConflictError(AppError):
    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__("RESOURCE_CONFLICT", message, status_code=409, details=details)


def _request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return str(value) if value is not None else None


def _response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    payload = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            details=details,
            request_id=_request_id(request),
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(payload, exclude_none=True),
        headers=headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return _response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _response(
            request,
            status_code=422,
            code="VALIDATION_ERROR",
            message="Request validation failed",
            details=jsonable_encoder(
                exc.errors(),
                custom_encoder={Exception: str},
            ),
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, _exc: IntegrityError) -> JSONResponse:
        return _response(
            request,
            status_code=409,
            code="DATABASE_CONFLICT",
            message="The operation conflicts with existing data",
        )

    @app.exception_handler(ProviderUnavailableError)
    async def provider_unavailable_handler(
        request: Request, exc: ProviderUnavailableError
    ) -> JSONResponse:
        structlog.get_logger(__name__).warning(
            "provider_unavailable",
            provider=exc.provider,
            reason=exc.reason,
        )
        return _response(
            request,
            status_code=503,
            code="PROVIDER_UNAVAILABLE",
            message="A required provider is unavailable",
            details={"provider": exc.provider},
        )

    @app.exception_handler(ProviderResponseError)
    async def provider_response_handler(
        request: Request, exc: ProviderResponseError
    ) -> JSONResponse:
        structlog.get_logger(__name__).warning(
            "provider_invalid_response",
            provider=exc.provider,
            reason=exc.reason,
        )
        return _response(
            request,
            status_code=502,
            code="PROVIDER_INVALID_RESPONSE",
            message="A provider returned an invalid response",
            details={"provider": exc.provider},
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, _exc: Exception) -> JSONResponse:
        return _response(
            request,
            status_code=500,
            code="INTERNAL_ERROR",
            message="An unexpected internal error occurred",
        )


class MessageResponse(BaseModel):
    message: str = Field(min_length=1)
