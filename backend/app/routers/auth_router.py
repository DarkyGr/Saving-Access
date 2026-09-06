"""
Auth router — handles user registration and login.

Endpoints:
  POST /api/auth/register  → 201 {user_id, username, role}
  POST /api/auth/login     → 200 {access_token, token_type, expires_in}

Requirements: 1.1–1.8, 2.1–2.4
"""

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.auth_service import AuthService

router = APIRouter()


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    password_confirmation: str


class LoginRequest(BaseModel):
    username: str
    password: str


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class RegisterResponse(BaseModel):
    user_id: int
    username: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
def register(
    body: RegisterRequest,
    db: Session = Depends(get_db),
) -> RegisterResponse:
    """
    Create a new user account.

    Validates password strength and confirmation match, checks for duplicate
    username/email, hashes the password with bcrypt, and persists the record.

    Returns the new user's id, username, and role on success.
    Raises HTTP 400 on any validation or uniqueness failure.
    """
    service = AuthService(db)
    user = service.register(body.model_dump())
    return RegisterResponse(
        user_id=user.user_id,
        username=user.username,
        role=user.role,
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and receive a JWT access token",
)
def login(
    body: LoginRequest,
    db: Session = Depends(get_db),
) -> LoginResponse:
    """
    Authenticate with username and password.

    On success returns a short-lived JWT (15 min) with user_id and role claims.
    On any failure returns the same generic 401 to avoid leaking field-level info.
    """
    service = AuthService(db)
    token_data = service.login(body.model_dump())
    return LoginResponse(**token_data)
