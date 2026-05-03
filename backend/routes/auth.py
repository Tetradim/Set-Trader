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
"""Authentication, authorization, and security features."""
import os
import hashlib
import secrets
import time
from typing import Optional, List
from dataclasses import dataclass
from enum import Enum
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import jwt

import deps

router = APIRouter(tags=["Security"])
security = HTTPBearer()


# ---------------------------------------------------------------------------
# Enums & Models
# ---------------------------------------------------------------------------

class Role(str, Enum):
    ADMIN = "admin"
    TRADER = "trader"
    VIEWER = "viewer"


class TwoFactorMethod(str, Enum):
    NONE = "none"
    TOTP = "totp"  # Time-based one-time password
    EMAIL = "email"


@dataclass
class User:
    id: str
    username: str
    email: str
    role: Role
    password_hash: str
    salt: str
    two_factor_method: TwoFactorMethod
    two_factor_secret: Optional[str]
    totp_verified: bool
    created_at: float
    last_login: float
    failed_attempts: int
    locked_until: float


class AuthConfig:
    """Authentication configuration."""
    secret_key: str = os.environ.get("AUTH_SECRET_KEY", secrets.token_hex(32))
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24
    max_failed_attempts: int = 5
    lockout_duration_minutes: int = 15
    require_2fa: bool = False


config = AuthConfig()


# ---------------------------------------------------------------------------
# Password Utilities
# ---------------------------------------------------------------------------

def hash_password(password: str, salt: str) -> str:
    """Hash password with salt using SHA-256."""
    return hashlib.sha256((password + salt).encode()).hexdigest()


def generate_salt() -> str:
    """Generate a random salt."""
    return secrets.token_hex(16)


def verify_password(password: str, salt: str, password_hash: str) -> bool:
    """Verify password against hash."""
    return hash_password(password, salt) == password_hash


# ---------------------------------------------------------------------------
# JWT Tokens
# ---------------------------------------------------------------------------

def create_token(user: User) -> str:
    """Create JWT token for user."""
    payload = {
        "sub": user.id,
        "username": user.email,
        "role": user.role.value,
        "exp": time.time() + (config.jwt_expiry_hours * 3600),
        "iat": time.time(),
    }
    return jwt.encode(payload, config.secret_key, algorithm=config.jwt_algorithm)


def verify_token(token: str) -> Optional[dict]:
    """Verify and decode JWT token."""
    try:
        return jwt.decode(token, config.secret_key, algorithms=[config.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    """Get current authenticated user from token."""
    token = credentials.credentials
    payload = verify_token(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Get user from database
    user_id = payload.get("sub")
    user_doc = await deps.db.users.find_one({"id": user_id})
    
    if not user_doc:
        raise HTTPException(status_code=401, detail="User not found")
    
    return User(**user_doc)


def require_role(allowed_roles: List[Role]):
    """Dependency to require specific roles."""
    async def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return role_checker


# ---------------------------------------------------------------------------
# Routes: Authentication
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str
    password: str
    totp_code: Optional[str] = None


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
    token_type: str
    user: dict


@router.post("/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """Authenticate user and return JWT token."""
    # Find user by email
    user_doc = await deps.db.users.find_one({"email": req.email})
    
    if not user_doc:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    user = User(**user_doc)
    
    # Check if locked
    if user.locked_until > time.time():
        raise HTTPException(
            status_code=423,
            detail=f"Account locked until {time.strftime('%H:%M:%S', time.localtime(user.locked_until))}"
        )
    
    # Verify password
    if not verify_password(req.password, user.salt, user.password_hash):
        # Increment failed attempts
        failed_attempts = user.failed_attempts + 1
        locked_until = 0
        
        if failed_attempts >= config.max_failed_attempts:
            locked_until = time.time() + (config.lockout_duration_minutes * 60)
        
        await deps.db.users.update_one(
            {"id": user.id},
            {"$set": {"failed_attempts": failed_attempts, "locked_until": locked_until}}
        )
        
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Check 2FA if enabled
    if user.two_factor_method == TwoFactorMethod.TOTP and not user.totp_verified:
        if not req.totp_code:
            raise HTTPException(status_code=402, detail="2FA code required")
        
        # Verify TOTP code (simplified - use proper library in production)
        if not verify_totp(user.two_factor_secret or "", req.totp_code):
            raise HTTPException(status_code=401, detail="Invalid 2FA code")
    
    # Reset failed attempts and update last login
    await deps.db.users.update_one(
        {"id": user.id},
        {"$set": {"failed_attempts": 0, "locked_until": 0, "last_login": time.time()}}
    )
    
    # Create token
    token = create_token(user)
    
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user={
            "id": user.id,
            "email": user.email,
            "role": user.role.value,
        }
    )


@router.post("/auth/logout")
async def logout(user: User = Depends(get_current_user)):
    """Logout current user (invalidate token client-side)."""
    # In production, you'd add token to a blocklist
    return {"message": "Logged out successfully"}


@router.post("/auth/refresh")
async def refresh_token(user: User = Depends(get_current_user)):
    """Refresh JWT token."""
    token = create_token(user)
    return {"access_token": token, "token_type": "bearer"}


# ---------------------------------------------------------------------------
# Routes: User Management (Admin only)
# ---------------------------------------------------------------------------

class CreateUserRequest(BaseModel):
    email: str
    password: str
    role: Role = Role.VIEWER


@router.post("/auth/users")
async def create_user(
    req: CreateUserRequest,
    admin: User = Depends(require_role([Role.ADMIN]))
):
    """Create a new user (admin only)."""
    # Check if email exists
    existing = await deps.db.users.find_one({"email": req.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Generate user ID and salt
    user_id = secrets.token_hex(8)
    salt = generate_salt()
    password_hash = hash_password(req.password, salt)
    
    user = User(
        id=user_id,
        username=req.email.split("@")[0],
        email=req.email,
        role=req.role,
        password_hash=password_hash,
        salt=salt,
        two_factor_method=TwoFactorMethod.NONE,
        two_factor_secret=None,
        totp_verified=False,
        created_at=time.time(),
        last_login=0,
        failed_attempts=0,
        locked_until=0,
    )
    
    await deps.db.users.insert_one(user.__dict__)
    
    await deps.audit_service.log_event(
        "USER_CREATED",
        user_id=user_id,
        details={"email": req.email, "role": req.role.value},
    )
    
    return {"ok": True, "user_id": user_id}


@router.get("/auth/users")
async def list_users(admin: User = Depends(require_role([Role.ADMIN]))):
    """List all users (admin only)."""
    users = await deps.db.users.find({}, {"password_hash": 0, "salt": 0, "two_factor_secret": 0}).to_list(100)
    return {"users": users}


@router.delete("/auth/users/{user_id}")
async def delete_user(user_id: str, admin: User = Depends(require_role([Role.ADMIN]))):
    """Delete a user (admin only)."""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    result = await deps.db.users.delete_one({"id": user_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    await deps.audit_service.log_event("USER_DELETED", user_id=user_id)
    
    return {"ok": True}


# ---------------------------------------------------------------------------
# Routes: 2FA
# ---------------------------------------------------------------------------

@router.post("/auth/2fa/setup")
async def setup_2fa(user: User = Depends(get_current_user)):
    """Set up two-factor authentication."""
    import pyotp
    
    # Generate TOTP secret
    secret = pyotp.random_base32()
    
    # Store secret (not verified yet)
    await deps.db.users.update_one(
        {"id": user.id},
        {"$set": {"two_factor_method": TwoFactorMethod.TOTP, "two_factor_secret": secret, "totp_verified": False}}
    )
    
    # Generate QR code URL
    totp = pyotp.TOTP(secret)
    provisioning_url = totp.provisioning_uri(user.email, issuer_name="Sentinel Pulse")
    
    return {
        "secret": secret,
        "qr_url": provisioning_url,
        "message": "Scan QR code with authenticator app, then verify with code"
    }


@router.post("/auth/2fa/verify")
async def verify_2fa(code: str = Query(...), user: User = Depends(get_current_user)):
    """Verify and enable 2FA."""
    import pyotp
    
    if not user.two_factor_secret:
        raise HTTPException(status_code=400, detail="2FA not set up")
    
    totp = pyotp.TOTP(user.two_factor_secret)
    if not totp.verify(code):
        raise HTTPException(status_code=400, detail="Invalid verification code")
    
    await deps.db.users.update_one(
        {"id": user.id},
        {"$set": {"totp_verified": True}}
    )
    
    await deps.audit_service.log_event("2FA_ENABLED", user_id=user.id)
    
    return {"ok": True, "message": "2FA enabled successfully"}


@router.post("/auth/2fa/disable")
async def disable_2fa(user: User = Depends(get_current_user)):
    """Disable two-factor authentication."""
    await deps.db.users.update_one(
        {"id": user.id},
        {"$set": {"two_factor_method": TwoFactorMethod.NONE, "two_factor_secret": None, "totp_verified": False}}
    )
    
    await deps.audit_service.log_event("2FA_DISABLED", user_id=user.id)
    
    return {"ok": True, "message": "2FA disabled"}


def verify_totp(secret: str, code: str) -> bool:
    """Verify TOTP code."""
    import pyotp
    totp = pyotp.TOTP(secret)
    return totp.verify(code)


# ---------------------------------------------------------------------------
# Routes: Audit Dashboard
# ---------------------------------------------------------------------------

@router.get("/auth/audit")
async def get_auth_audit_logs(
    limit: int = Query(50, le=200),
    admin: User = Depends(require_role([Role.ADMIN]))
):
    """Get authentication audit logs (admin only)."""
    logs = await deps.db.audit_logs.find({
        "event_type": {"$in": ["USER_CREATED", "USER_DELETED", "2FA_ENABLED", "2FA_DISABLED", "LOGIN_SUCCESS", "LOGIN_FAILED"]}
    }).sort("timestamp", -1).limit(limit).to_list(limit)
    
    return {"logs": logs}


# ---------------------------------------------------------------------------
# Role Checker Helper
# ---------------------------------------------------------------------------

def check_permission(user: User, required_role: Role) -> bool:
    """Check if user has required role."""
    role_hierarchy = {Role.ADMIN: 3, Role.TRADER: 2, Role.VIEWER: 1}
    return role_hierarchy.get(user.role, 0) >= role_hierarchy.get(required_role, 0)
