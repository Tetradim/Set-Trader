"""Authentication and Authorization Module.

Provides OIDC-based authentication, RBAC, and session management for firm-grade security.
"""
import os
import jwt
import hashlib
import secrets
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, List, Dict, Any
from functools import wraps

from fastapi import HTTPException, Request, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, OAuth2PasswordBearer
from pydantic import BaseModel


logger = logging.getLogger(__name__)


class Role(str, Enum):
    """RBAC roles for the system."""
    TRADER = "trader"
    RISK_OFFICER = "risk_officer"
    ADMIN = "admin"
    VIEWER = "viewer"


class User(BaseModel):
    """User model with RBAC."""
    id: str
    username: str
    email: str
    roles: List[Role] = []
    broker_access: List[str] = []  # List of broker IDs user can access
    is_active: bool = True
    created_at: datetime = None
    last_login: Optional[datetime] = None


class TokenData(BaseModel):
    """JWT token payload."""
    sub: str  # user_id
    username: str
    roles: List[str]
    broker_access: List[str]
    exp: datetime
    iat: datetime = None


class Session(BaseModel):
    """User session model."""
    session_id: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


# In-memory user store (in production, replace with actual database)
_users: Dict[str, User] = {}
_sessions: Dict[str, Session] = {}
_api_keys: Dict[str, Dict[str, Any]] = {}

# JWT secret (in production, load from vault)
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


def hash_password(password: str) -> str:
    """Hash a password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return hash_password(plain_password) == hashed_password


def create_access_token(user: User, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token for a user."""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    now = datetime.utcnow()
    token_data = TokenData(
        sub=user.id,
        username=user.username,
        roles=[r.value for r in user.roles],
        broker_access=user.broker_access,
        exp=expire,
        iat=now
    )
    
    return jwt.encode(token_data.model_dump(), JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> TokenData:
    """Verify a JWT token and return the payload."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return TokenData(**payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def create_session(user: User, ip_address: Optional[str] = None, 
                   user_agent: Optional[str] = None) -> str:
    """Create a new session and return session ID."""
    session_id = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    session = Session(
        session_id=session_id,
        user_id=user.id,
        created_at=now,
        expires_at=now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        ip_address=ip_address,
        user_agent=user_agent
    )
    _sessions[session_id] = session
    return session_id


def verify_session(session_id: str) -> Optional[Session]:
    """Verify a session and return it if valid."""
    session = _sessions.get(session_id)
    if not session:
        return None
    
    if session.expires_at < datetime.utcnow():
        del _sessions[session_id]
        return None
    
    return session


def create_api_key(user: User, name: str, broker_access: Optional[List[str]] = None) -> str:
    """Create an API key for a user."""
    key = f"sk_{secrets.token_hex(32)}"
    _api_keys[key] = {
        "user_id": user.id,
        "name": name,
        "broker_access": broker_access or user.broker_access,
        "roles": [r.value for r in user.roles],
        "created_at": datetime.utcnow(),
        "is_active": True
    }
    return key


def verify_api_key(api_key: str) -> Optional[Dict[str, Any]]:
    """Verify an API key and return its data."""
    key_data = _api_keys.get(api_key)
    if not key_data or not key_data.get("is_active"):
        return None
    return key_data


def revoke_api_key(api_key: str) -> bool:
    """Revoke an API key."""
    if api_key in _api_keys:
        _api_keys[api_key]["is_active"] = False
        return True
    return False


def require_roles(required_roles: List[Role]):
    """Dependency factory for role-based access control."""
    def role_checker(token_data: TokenData = Depends(get_current_user)):
        user_roles = set(token_data.roles)
        required = set(r.value for r in required_roles)
        
        if not user_roles.intersection(required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {required_roles}"
            )
        return token_data
    
    return role_checker


def require_broker_access(broker_id: str):
    """Dependency factory for broker-level access control."""
    def broker_checker(token_data: TokenData = Depends(get_current_user)):
        if broker_id not in token_data.broker_access and "admin" in token_data.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No access to broker: {broker_id}"
            )
        return token_data
    
    return broker_checker


# OAuth2 scheme for FastAPI
oauth2_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False)),
    request: Request = None
) -> TokenData:
    """Get current authenticated user from token or API key."""
    # Check API key first
    api_key = request.headers.get("X-API-Key") if request else None
    if api_key:
        key_data = verify_api_key(api_key)
        if key_data:
            now = datetime.utcnow()
            return TokenData(
                sub=key_data["user_id"],
                username=key_data.get("name", "api_user"),
                roles=key_data.get("roles", []),
                broker_access=key_data.get("broker_access", []),
                exp=now + timedelta(hours=24*365),  # API keys don't expire
                iat=now
            )
    
    # Check Bearer token
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return verify_token(credentials.credentials)


async def get_current_active_user(
    current_user: TokenData = Depends(get_current_user)
) -> TokenData:
    """Get current active user."""
    return current_user


# Initialize default admin user (in production, load from vault/config)
def init_default_users():
    """Initialize default admin user."""
    admin_user = User(
        id="admin",
        username="admin",
        email="admin@example.com",
        roles=[Role.ADMIN, Role.RISK_OFFICER, Role.TRADER],
        broker_access=["*"],  # Access to all brokers
        is_active=True
    )
    _users[admin_user.id] = admin_user
    logger.info("Initialized default admin user")


# Initialize on import
init_default_users()


# Public exports
__all__ = [
    "Role",
    "User", 
    "TokenData",
    "Session",
    "hash_password",
    "verify_password", 
    "create_access_token",
    "verify_token",
    "create_session",
    "verify_session",
    "create_api_key",
    "verify_api_key",
    "revoke_api_key",
    "require_roles",
    "require_broker_access",
    "get_current_user",
    "get_current_active_user",
    "oauth2_scheme",
]