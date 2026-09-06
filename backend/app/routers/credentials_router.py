"""
Credentials router — CRUD endpoints for user credential records.

Endpoints:
  GET    /api/credentials               → list/search (password: null)
  POST   /api/credentials               → save new credential
  PUT    /api/credentials/{id}          → update existing credential
  DELETE /api/credentials/{id}          → hard-delete a credential
  POST   /api/credentials/{id}/reveal   → decrypt and return plaintext password

All mutations require the user to supply their own account password
(Password_Confirmation_Prompt).  Decryption happens only on the backend;
plaintext passwords are never stored or returned in list responses.

Security notes:
  - Credential ownership is enforced via ``WHERE credential_id=? AND user_id=?``
    on every single-credential operation (Requirement 8.2, 5.3).
  - Encryption / decryption is delegated to EncryptorService (Requirement 8.1).
  - Every mutation and every reveal is logged to audit_log (Requirements 4.12,
    5.14, 6.9, 7.7).
  - Account password re-verification is required before every sensitive
    operation (Requirements 4.9, 6.6, 7.5).
  - The FERNET_KEY never appears in any response (Requirement 8.3).

Requirements: 4.1–4.12, 5.1–5.14, 6.1–6.9, 7.1–7.7, 8.1–8.7
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.permissions import require_permission
from app.models import Credential
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.encryptor_service import EncryptorService
from app.utils.audit_columns import set_creation_audit, set_modification_audit

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic request / response schemas
# ---------------------------------------------------------------------------


class CredentialListItem(BaseModel):
    """Single item returned by the list/search endpoint.

    The password is always null — plaintext passwords are never sent in list
    responses (Requirement 5.4).
    """

    credential_id: int
    website_name: str
    email_or_username: str
    is_username_login: bool
    password: None = None

    class Config:
        from_attributes = True


class CreateCredentialRequest(BaseModel):
    """Body for POST /api/credentials."""

    website_name: str
    email_or_username: str
    is_username_login: bool = False
    password: str
    account_password: str


class CreateCredentialResponse(BaseModel):
    """Response body for POST /api/credentials (201)."""

    credential_id: int
    website_name: str


class UpdateCredentialRequest(BaseModel):
    """Body for PUT /api/credentials/{id}."""

    website_name: str
    email_or_username: str
    is_username_login: bool = False
    password: str
    account_password: str


class UpdateCredentialResponse(BaseModel):
    """Response body for PUT /api/credentials/{id} (200)."""

    credential_id: int


class DeleteCredentialRequest(BaseModel):
    """Body for DELETE /api/credentials/{id}."""

    account_password: str


class RevealCredentialRequest(BaseModel):
    """Body for POST /api/credentials/{id}/reveal."""

    account_password: str


class RevealCredentialResponse(BaseModel):
    """Response body for POST /api/credentials/{id}/reveal (200)."""

    password: str


# ---------------------------------------------------------------------------
# Helper: verify account password and raise 401 on failure
# ---------------------------------------------------------------------------


def _verify_account_password(
    user_id: int, raw_password: str, db: Session
) -> None:
    """Check *raw_password* against the stored hash for *user_id*.

    :raises HTTPException 401: If the password does not match.
    """
    auth_svc = AuthService(db)
    if not auth_svc.check_account_password(user_id, raw_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account password verification failed.",
        )


# ---------------------------------------------------------------------------
# Helper: fetch a credential by id, enforcing ownership
# ---------------------------------------------------------------------------


def _get_owned_credential(
    credential_id: int, user_id: int, db: Session
) -> Credential:
    """Retrieve the credential row, verifying it belongs to *user_id*.

    Uses ``WHERE credential_id=? AND user_id=?`` so that one user can never
    touch another user's records (Requirements 5.3, 8.2).

    :raises HTTPException 404: If no matching row exists.
    :raises HTTPException 403: If the credential exists but belongs to a
        different user (caught implicitly by the combined filter).
    """
    credential: Credential | None = (
        db.query(Credential)
        .filter(
            Credential.credential_id == credential_id,
            Credential.user_id == user_id,
        )
        .first()
    )
    if credential is None:
        # Return 403 rather than 404 when the credential exists but belongs to
        # another user; the combined filter makes it impossible to distinguish
        # the two cases without a second query, so we check explicitly.
        exists = (
            db.query(Credential.credential_id)
            .filter(Credential.credential_id == credential_id)
            .first()
        )
        if exists:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden.",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found.",
        )
    return credential


# ---------------------------------------------------------------------------
# GET /api/credentials?q=
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[CredentialListItem],
    status_code=status.HTTP_200_OK,
    summary="List / search credentials",
)
def list_credentials(
    q: Optional[str] = None,
    claims: dict = Depends(require_permission("credentials")),
    db: Session = Depends(get_db),
) -> list[CredentialListItem]:
    """Return the authenticated user's credentials, optionally filtered by *q*.

    - Filters by ``website_name ILIKE %q%`` OR ``email_or_username ILIKE %q%``
      (case-insensitive partial match — Requirement 5.2).
    - Only credentials owned by the current user are returned (Requirement 5.3).
    - The ``password`` field is always ``null`` (Requirement 5.4).

    Uses SQLAlchemy ORM ``ilike`` which maps to PostgreSQL ``ILIKE`` with
    parameterized binding — no raw string interpolation (Requirement 8.6).
    """
    user_id: int = claims["user_id"]

    query = db.query(Credential).filter(Credential.user_id == user_id)

    if q:
        pattern = f"%{q}%"
        query = query.filter(
            (Credential.website_name.ilike(pattern))
            | (Credential.email_or_username.ilike(pattern))
        )

    rows = query.all()

    return [
        CredentialListItem(
            credential_id=row.credential_id,
            website_name=row.website_name,
            email_or_username=row.email_or_username,
            is_username_login=row.is_username_login,
            password=None,
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# POST /api/credentials
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=CreateCredentialResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save a new credential",
)
def create_credential(
    body: CreateCredentialRequest,
    claims: dict = Depends(require_permission("credentials.new")),
    db: Session = Depends(get_db),
) -> CreateCredentialResponse:
    """Encrypt and persist a new credential record.

    Steps:
      1. Verify the user's account password (Requirement 4.9).
      2. Encrypt the credential password with EncryptorService (Requirement 4.10 / 8.1).
      3. Persist the record with creation audit columns (Requirement 4.11).
      4. Log INSERT to audit_log (Requirement 4.12).
      5. Return 201 with ``{credential_id, website_name}``.
    """
    user_id: int = claims["user_id"]

    # 1. Verify account password before any sensitive operation
    _verify_account_password(user_id, body.account_password, db)

    # 2. Encrypt the credential password
    encryptor = EncryptorService()
    encrypted_password: bytes = encryptor.encrypt(body.password)

    # 3. Build and persist the credential record
    credential = Credential(
        user_id=user_id,
        website_name=body.website_name,
        email_or_username=body.email_or_username,
        is_username_login=body.is_username_login,
        encrypted_password=encrypted_password,
    )
    set_creation_audit(credential, user_id=user_id)

    db.add(credential)
    db.commit()
    db.refresh(credential)

    # 4. Log INSERT to audit_log
    audit_svc = AuditService(db)
    audit_svc.log(
        user_id=user_id,
        operation="INSERT",
        affected_record_id=credential.credential_id,
    )

    # 5. Return 201
    return CreateCredentialResponse(
        credential_id=credential.credential_id,
        website_name=credential.website_name,
    )


# ---------------------------------------------------------------------------
# PUT /api/credentials/{id}
# ---------------------------------------------------------------------------


@router.put(
    "/{credential_id}",
    response_model=UpdateCredentialResponse,
    status_code=status.HTTP_200_OK,
    summary="Update an existing credential",
)
def update_credential(
    credential_id: int,
    body: UpdateCredentialRequest,
    claims: dict = Depends(require_permission("credentials.edit")),
    db: Session = Depends(get_db),
) -> UpdateCredentialResponse:
    """Update a credential record owned by the authenticated user.

    Steps:
      1. Verify ownership — ``WHERE credential_id=? AND user_id=?`` (Requirement 5.3 / 8.2).
      2. Verify the user's account password (Requirement 6.6).
      3. Re-encrypt the (possibly changed) password (Requirement 6.7 / 8.1).
      4. Persist updated fields and set modification audit columns (Requirement 6.8).
      5. Log UPDATE to audit_log (Requirement 6.9).
      6. Return 200 with ``{credential_id}``.
    """
    user_id: int = claims["user_id"]

    # 1. Fetch and verify ownership
    credential = _get_owned_credential(credential_id, user_id, db)

    # 2. Verify account password
    _verify_account_password(user_id, body.account_password, db)

    # 3. Re-encrypt the credential password
    encryptor = EncryptorService()
    encrypted_password: bytes = encryptor.encrypt(body.password)

    # 4. Apply updates and set modification audit columns
    credential.website_name = body.website_name
    credential.email_or_username = body.email_or_username
    credential.is_username_login = body.is_username_login
    credential.encrypted_password = encrypted_password
    set_modification_audit(credential, user_id=user_id)

    db.commit()
    db.refresh(credential)

    # 5. Log UPDATE to audit_log
    audit_svc = AuditService(db)
    audit_svc.log(
        user_id=user_id,
        operation="UPDATE",
        affected_record_id=credential.credential_id,
    )

    # 6. Return 200
    return UpdateCredentialResponse(credential_id=credential.credential_id)


# ---------------------------------------------------------------------------
# DELETE /api/credentials/{id}
# ---------------------------------------------------------------------------


@router.delete(
    "/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a credential",
)
def delete_credential(
    credential_id: int,
    body: DeleteCredentialRequest,
    claims: dict = Depends(require_permission("credentials.delete")),
    db: Session = Depends(get_db),
) -> None:
    """Permanently delete a credential record owned by the authenticated user.

    Steps:
      1. Verify ownership (Requirement 5.3 / 8.2).
      2. Verify the user's account password (Requirement 7.5).
      3. Hard-delete the record (Requirement 7.6).
      4. Log DELETE to audit_log (Requirement 7.7).
      5. Return 204 (no body).
    """
    user_id: int = claims["user_id"]

    # 1. Fetch and verify ownership
    credential = _get_owned_credential(credential_id, user_id, db)

    # 2. Verify account password
    _verify_account_password(user_id, body.account_password, db)

    # Capture id before deletion for the audit log entry
    record_id = credential.credential_id

    # 3. Hard-delete
    db.delete(credential)
    db.commit()

    # 4. Log DELETE to audit_log
    audit_svc = AuditService(db)
    audit_svc.log(
        user_id=user_id,
        operation="DELETE",
        affected_record_id=record_id,
    )

    # 5. Return 204 — FastAPI handles the empty body automatically


# ---------------------------------------------------------------------------
# POST /api/credentials/{id}/reveal
# ---------------------------------------------------------------------------


@router.post(
    "/{credential_id}/reveal",
    response_model=RevealCredentialResponse,
    status_code=status.HTTP_200_OK,
    summary="Reveal the plaintext password for a credential",
)
def reveal_credential(
    credential_id: int,
    body: RevealCredentialRequest,
    claims: dict = Depends(require_permission("credentials")),
    db: Session = Depends(get_db),
) -> RevealCredentialResponse:
    """Decrypt and return the plaintext password for a single credential.

    The frontend prompts the user for their account password
    (Password_Confirmation_Prompt) before calling this endpoint.  No
    session-level bypass is permitted — the prompt is shown on every call
    (Requirement 5.13).

    Steps:
      1. Verify ownership (Requirement 5.3 / 8.2).
      2. Verify the user's account password (Requirement 5.5).
         → 401 on failure (Requirement 4.9).
      3. Decrypt the credential password via EncryptorService (Requirement 5.6 / 8.1).
      4. Log SELECT to audit_log (Requirement 5.14).
      5. Return ``{password: plaintext}`` over HTTPS (Requirement 8.3).
    """
    user_id: int = claims["user_id"]

    # 1. Fetch and verify ownership
    credential = _get_owned_credential(credential_id, user_id, db)

    # 2. Verify account password
    _verify_account_password(user_id, body.account_password, db)

    # 3. Decrypt the credential password (backend-only — key never leaves server)
    encryptor = EncryptorService()
    plaintext_password: str = encryptor.decrypt(credential.encrypted_password)

    # 4. Log SELECT to audit_log (Requirement 5.14)
    audit_svc = AuditService(db)
    audit_svc.log(
        user_id=user_id,
        operation="SELECT",
        affected_record_id=credential.credential_id,
    )

    # 5. Return plaintext password
    return RevealCredentialResponse(password=plaintext_password)
