from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.dependencies import CurrentUser, get_auth_service
from app.schemas.auth import LoginRequest, RefreshRequest, TokenPair, UserResponse
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post(
    "/login",
    response_model=TokenPair,
    status_code=status.HTTP_200_OK,
    summary="Authenticate an administrator",
)
async def login(
    request: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenPair:
    return await service.authenticate(request.username, request.password)


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Rotate an access and refresh token pair",
)
async def refresh(
    request: RefreshRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenPair:
    return await service.refresh(request.refresh_token)


@router.get("/me", response_model=UserResponse, summary="Return the authenticated user")
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    user: CurrentUser,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> Response:
    await service.revoke_tokens(user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
