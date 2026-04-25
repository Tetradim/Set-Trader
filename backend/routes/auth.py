"""Authentication API routes.

Provides endpoints for login, token refresh, session management, and API keys.
"""
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel


from auth import (
    get_current_user, TokenData, Role, User,
    create_access_token, create_session, create_api_key, verify_api_key, revoke_api_key,
    _users, _sessions, _api_keys
)


router = APIRouter(prefix="/api/auth", tags=["auth"])


# Request/Response models
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
    broker_access: list[str] = []


class APIKeyResponse(BaseModel):
    api_key: str
    name: str
    created_at: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    roles: list[str]
    broker_access: list[str]
    is_active: bool


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Login with username and password."""
    # For demo purposes, check against in-memory users
    # In production, this would validate against a database
    user = _users.get(request.username)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled"
        )
    
    # Create access token
    access_token = create_access_token(user)
    
    return LoginResponse(
        access_token=access_token,
        user_id=user.id,
        username=user.username,
        roles=[r.value for r in user.roles]
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: TokenData = Depends(get_current_user)
):
    """Get current user information."""
    user = _users.get(current_user.sub)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        roles=[r.value for r in user.roles],
        broker_access=user.broker_access,
        is_active=user.is_active
    )


@router.post("/api-keys", response_model=APIKeyResponse)
async def create_key(
    request: APIKeyRequest,
    current_user: TokenData = Depends(get_current_user)
):
    """Create an API key."""
    user = _users.get(current_user.sub)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    api_key = create_api_key(user, request.name, request.broker_access)
    
    key_data = _api_keys[api_key]
    
    return APIKeyResponse(
        api_key=api_key,
        name=request.name,
        created_at=key_data["created_at"].isoformat()
    )


@router.get("/api-keys")
async def list_api_keys(
    current_user: TokenData = Depends(get_current_user)
):
    """List all API keys for current user."""
    user_keys = []
    for key, data in _api_keys.items():
        if data["user_id"] == current_user.sub:
            user_keys.append({
                "key": key[:10] + "..." + key[-5:],  # partial key for display
                "name": data["name"],
                "broker_access": data["broker_access"],
                "roles": data["roles"],
                "created_at": data["created_at"].isoformat(),
                "is_active": data["is_active"]
            })
    
    return {"api_keys": user_keys}


@router.delete("/api-keys/{key_prefix}")
async def delete_api_key(
    key_prefix: str,
    current_user: TokenData = Depends(get_current_user)
):
    """Delete an API key."""
    # Find the key that matches the prefix
    key_to_delete = None
    for key in _api_keys:
        if key.startswith(key_prefix) or key.startswith("sk_") and key[3:].startswith(key_prefix):
            key_to_delete = key
            break
    
    if not key_to_delete:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    # Verify ownership
    if _api_keys[key_to_delete]["user_id"] != current_user.sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this key"
        )
    
    revoke_api_key(key_to_delete)
    
    return {"status": "ok", "message": "API key revoked"}


@router.get("/roles")
async def get_roles():
    """Get available roles."""
    return {"roles": [role.value for role in Role]}


__all__ = ["router"]