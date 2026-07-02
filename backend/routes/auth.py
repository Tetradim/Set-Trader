"""Authentication API routes."""
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

import deps
from password_security import hash_password, needs_password_rehash, verify_password
from auth import (
    Role,
    TokenData,
    User,
    create_access_token,
    create_api_key,
    get_auth_disabled_user,
    get_current_user,
    is_auth_disabled,
    require_roles,
    revoke_api_key,
    _api_keys,
)


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str
    roles: list[str]


class APIKeyRequest(BaseModel):
    name: str
    broker_access: list[str] = Field(default_factory=list)


class APIKeyResponse(BaseModel):
    api_key: str
    name: str
    created_at: str


class UserCreateRequest(BaseModel):
    username: str
    email: str
    password: str = Field(min_length=12)
    roles: list[Role] = Field(default_factory=lambda: [Role.VIEWER])
    broker_access: list[str] = Field(default_factory=list)


class BootstrapRequest(BaseModel):
    username: str
    email: str = ""
    password: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    roles: list[str]
    broker_access: list[str]
    is_active: bool
    created_at: Optional[str] = None
    last_login: Optional[str] = None


def _verify_password(password: str, user_doc: dict) -> bool:
    return verify_password(password, user_doc.get("password_hash", ""), user_doc.get("salt", ""))


def _normalize_roles(user_doc: dict) -> list[Role]:
    raw_roles = user_doc.get("roles")
    if raw_roles is None and user_doc.get("role"):
        raw_roles = [user_doc["role"]]
    roles = []
    for role in raw_roles or [Role.VIEWER.value]:
        roles.append(Role(role.value if isinstance(role, Role) else role))
    return roles


def _to_auth_user(user_doc: dict) -> User:
    created_at = user_doc.get("created_at")
    last_login = user_doc.get("last_login")
    return User(
        id=user_doc["id"],
        username=user_doc["username"],
        email=user_doc["email"],
        roles=_normalize_roles(user_doc),
        broker_access=user_doc.get("broker_access", []),
        is_active=user_doc.get("is_active", True),
        created_at=created_at if isinstance(created_at, datetime) else None,
        last_login=last_login if isinstance(last_login, datetime) else None,
    )


def _to_response(user_doc: dict) -> UserResponse:
    user = _to_auth_user(user_doc)
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        roles=[role.value for role in user.roles],
        broker_access=user.broker_access,
        is_active=user.is_active,
        created_at=user.created_at.isoformat() if user.created_at else None,
        last_login=user.last_login.isoformat() if user.last_login else None,
    )


async def _find_user_by_login(username: str) -> Optional[dict]:
    return await deps.db.users.find_one({
        "$or": [
            {"username": username},
            {"email": username},
        ]
    })


async def _create_user_doc(
    username: str,
    email: str,
    password: str,
    roles: list[Role],
    broker_access: list[str],
) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "id": secrets.token_urlsafe(16),
        "username": username,
        "email": email,
        "roles": [role.value for role in roles],
        "broker_access": broker_access,
        "is_active": True,
        "created_at": now,
        "last_login": None,
        "password_hash": hash_password(password),
        "salt": "",
    }


@router.get("/bootstrap-status")
async def bootstrap_status():
    """Return whether the first admin account needs to be created."""
    if is_auth_disabled():
        return {"needs_bootstrap": False, "auth_disabled": True}

    user_count = await deps.db.users.count_documents({})
    return {"needs_bootstrap": user_count == 0, "auth_disabled": False}


@router.post("/bootstrap", response_model=LoginResponse)
async def bootstrap_admin(request: BootstrapRequest):
    """Create the first local admin account. Disabled after any user exists."""
    user_count = await deps.db.users.count_documents({})
    if user_count:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bootstrap already completed")

    user_doc = await _create_user_doc(
        username=request.username,
        email=request.email.strip() or f"{request.username}@sentinel.local",
        password=request.password,
        roles=[Role.ADMIN, Role.RISK_OFFICER, Role.TRADER],
        broker_access=["*"],
    )
    await deps.db.users.insert_one(user_doc)
    user = _to_auth_user(user_doc)
    access_token = create_access_token(user)
    return LoginResponse(
        access_token=access_token,
        user_id=user.id,
        username=user.username,
        roles=[role.value for role in user.roles],
    )


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Authenticate a database user and return a bearer token."""
    user_doc = await _find_user_by_login(request.username)
    if not user_doc or not _verify_password(request.password, user_doc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user = _to_auth_user(user_doc)
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    now = datetime.now(timezone.utc)
    updates = {"last_login": now}
    if needs_password_rehash(user_doc.get("password_hash", "")):
        updates["password_hash"] = hash_password(request.password)
        updates["salt"] = ""
    await deps.db.users.update_one({"id": user.id}, {"$set": updates})
    access_token = create_access_token(user)

    return LoginResponse(
        access_token=access_token,
        user_id=user.id,
        username=user.username,
        roles=[role.value for role in user.roles],
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: TokenData = Depends(get_current_user)):
    """Get the current authenticated user's database record."""
    if is_auth_disabled():
        local_user = get_auth_disabled_user()
        return UserResponse(
            id=local_user.sub,
            username=local_user.username,
            email="local@sentinel.local",
            roles=local_user.roles,
            broker_access=local_user.broker_access,
            is_active=True,
        )

    user_doc = await deps.db.users.find_one({"id": current_user.sub}, {"_id": 0, "password_hash": 0, "salt": 0})
    if not user_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _to_response(user_doc)


@router.get("/users")
async def list_users(current_user: TokenData = Depends(require_roles([Role.ADMIN]))):
    """List users. Admin role required."""
    docs = await deps.db.users.find({}, {"_id": 0, "password_hash": 0, "salt": 0}).to_list(500)
    return {"users": [_to_response(doc).model_dump() for doc in docs]}


@router.post("/users", response_model=UserResponse)
async def create_user(
    request: UserCreateRequest,
    current_user: TokenData = Depends(require_roles([Role.ADMIN])),
):
    """Create a user. Admin role required."""
    existing = await deps.db.users.find_one({
        "$or": [
            {"username": request.username},
            {"email": request.email},
        ]
    })
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

    user_doc = await _create_user_doc(
        username=request.username,
        email=request.email,
        password=request.password,
        roles=request.roles,
        broker_access=request.broker_access,
    )
    await deps.db.users.insert_one(user_doc)
    return _to_response(user_doc)


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: TokenData = Depends(require_roles([Role.ADMIN])),
):
    """Delete a user. Admin role required."""
    if user_id == current_user.sub:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account")

    result = await deps.db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {"ok": True}


@router.post("/api-keys", response_model=APIKeyResponse)
async def create_key(
    request: APIKeyRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Create an API key for the current user."""
    user_doc = await deps.db.users.find_one({"id": current_user.sub})
    if not user_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    api_key = create_api_key(_to_auth_user(user_doc), request.name, request.broker_access)
    key_data = _api_keys[api_key]
    return APIKeyResponse(
        api_key=api_key,
        name=request.name,
        created_at=key_data["created_at"].isoformat(),
    )


@router.get("/api-keys")
async def list_api_keys(current_user: TokenData = Depends(get_current_user)):
    """List API keys owned by the current user."""
    user_keys = []
    for key, data in _api_keys.items():
        if data["user_id"] == current_user.sub:
            user_keys.append({
                "key": f"{key[:10]}...{key[-5:]}",
                "name": data["name"],
                "broker_access": data["broker_access"],
                "roles": data["roles"],
                "created_at": data["created_at"].isoformat(),
                "is_active": data["is_active"],
            })
    return {"api_keys": user_keys}


@router.delete("/api-keys/{key_prefix}")
async def delete_api_key(
    key_prefix: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Revoke an API key owned by the current user."""
    key_to_delete = None
    for key, data in _api_keys.items():
        matches_prefix = key.startswith(key_prefix) or key.removeprefix("sk_").startswith(key_prefix)
        if matches_prefix and data["user_id"] == current_user.sub:
            key_to_delete = key
            break

    if not key_to_delete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    revoke_api_key(key_to_delete)
    return {"ok": True}


@router.get("/roles")
async def get_roles():
    """Get available roles."""
    return {"roles": [role.value for role in Role]}


__all__ = ["router"]
