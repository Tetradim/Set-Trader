"""Environment and Vault Configuration.

Provides environment-aware configuration loading with vault integration for secrets management.
"""
import os
import json
import logging
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel


logger = logging.getLogger(__name__)


class Environment(str, Enum):
    """Deployment environments."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class VaultConfig(BaseModel):
    """Vault configuration."""
    enabled: bool = False
    url: str = "http://localhost:8200"
    role: str = "sentinel-reader"
    auth_method: str = "k8s"  # k8s, token, approle
    path_prefix: str = "secret/data/sentinel"


class EnvironmentConfig(BaseModel):
    """Environment configuration."""
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = True
    log_level: str = "INFO"
    
    # Database
    db_host: str = "localhost"
    db_port: int = 27017
    db_name: str = "sentinel"
    
    # Redis/Cache
    redis_host: str = "localhost"
    redis_port: int = 6379
    
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # Security
    cors_origins: list[str] = ["http://localhost:3000"]
    trusted_proxies: list[str] = ["127.0.0.1"]
    rate_limit_per_minute: int = 60
    
    # Features
    features: Dict[str, bool] = {
        "paper_trading": True,
        "live_trading": False,
        "telegram": False,
        "opentelemetry": True,
    }


# Global configuration
_config: Optional[EnvironmentConfig] = None
_vault_config: Optional[VaultConfig] = None


def get_environment() -> Environment:
    """Get current environment from ENV."""
    env = os.getenv("ENVIRONMENT", "development").lower()
    try:
        return Environment(env)
    except ValueError:
        logger.warning(f"Invalid ENVIRONMENT: {env}, defaulting to development")
        return Environment.DEVELOPMENT


def load_config() -> EnvironmentConfig:
    """Load configuration based on environment."""
    global _config
    
    env = get_environment()
    
    # Load base config
    _config = EnvironmentConfig(
        environment=env,
        debug=env == Environment.DEVELOPMENT,
        log_level="DEBUG" if env == Environment.DEVELOPMENT else "INFO",
    )
    
    # Environment-specific overrides
    if env == Environment.DEVELOPMENT:
        _config.db_host = "localhost"
        _config.redis_host = "localhost"
        _config.features["live_trading"] = False
        
    elif env == Environment.STAGING:
        _config.db_host = os.getenv("DB_HOST", "staging-mongo.internal")
        _config.redis_host = os.getenv("REDIS_HOST", "staging-redis.internal")
        _config.debug = False
        _config.features["live_trading"] = True
        
    elif env == Environment.PRODUCTION:
        _config.db_host = os.getenv("DB_HOST", "prod-mongo.internal")
        _config.redis_host = os.getenv("REDIS_HOST", "prod-redis.internal")
        _config.debug = False
        _config.log_level = "WARNING"
        _config.features["paper_trading"] = False
        _config.features["live_trading"] = True
    
    # Load from environment variables (highest priority)
    _config.db_host = os.getenv("DB_HOST", _config.db_host)
    _config.db_port = int(os.getenv("DB_PORT", str(_config.db_port)))
    _config.db_name = os.getenv("DB_NAME", _config.db_name)
    _config.redis_host = os.getenv("REDIS_HOST", _config.redis_host)
    _config.redis_port = int(os.getenv("REDIS_PORT", str(_config.redis_port)))
    
    logger.info(f"Loaded configuration for environment: {env}")
    
    return _config


def get_config() -> EnvironmentConfig:
    """Get current configuration."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def load_vault_config() -> VaultConfig:
    """Load vault configuration."""
    global _vault_config
    
    vault_url = os.getenv("VAULT_URL")
    if not vault_url:
        _vault_config = VaultConfig(enabled=False)
        return _vault_config
    
    _vault_config = VaultConfig(
        enabled=True,
        url=vault_url,
        role=os.getenv("VAULT_ROLE", "sentinel-reader"),
        auth_method=os.getenv("VAULT_AUTH_METHOD", "k8s"),
        path_prefix=os.getenv("VAULT_PATH_PREFIX", "secret/data/sentinel"),
    )
    
    return _vault_config


async def get_secret(key: str) -> Optional[str]:
    """Get a secret from vault."""
    global _vault_config
    
    if _vault_config is None:
        _vault_config = load_vault_config()
    
    if not _vault_config.enabled:
        # Fallback to environment variable
        return os.getenv(key.upper())
    
    # In production, this would make actual vault API calls
    logger.warning("Vault integration not fully implemented")
    return os.getenv(key.upper())


async def get_secrets(prefix: str = "") -> Dict[str, str]:
    """Get multiple secrets from vault."""
    global _vault_config
    
    if _vault_config is None:
        _vault_config = load_vault_config()
    
    if not _vault_config.enabled:
        # Fallback to environment variables with prefix
        secrets = {}
        for key, value in os.environ.items():
            if prefix and key.startswith(prefix):
                secrets[key] = value
            elif prefix == "":
                # Return all sensitive keys
                for sensitive_key in ["API_KEY", "SECRET", "PASSWORD", "TOKEN"]:
                    if sensitive_key in key:
                        secrets[key] = value
        return secrets
    
    logger.warning("Vault integration not fully implemented")
    return {}


def validate_config() -> list[str]:
    """Validate configuration and return issues."""
    config = get_config()
    issues = []
    
    # Check required fields for production
    if config.environment == Environment.PRODUCTION:
        if config.debug:
            issues.append("debug must be False in production")
        
        if config.features.get("paper_trading"):
            issues.append("paper_trading should be disabled in production")
        
        if not config.cors_origins:
            issues.append("cors_origins must be configured in production")
    
    return issues


def get_environment_tags() -> Dict[str, str]:
    """Get environment-specific tags for logging/metrics."""
    env = get_environment()
    return {
        "environment": env.value,
        "version": os.getenv("APP_VERSION", "unknown"),
        "debug": str(get_config().debug),
    }


# Initialize on import
load_config()
load_vault_config()


__all__ = [
    "Environment",
    "VaultConfig", 
    "EnvironmentConfig",
    "get_environment",
    "load_config",
    "get_config",
    "load_vault_config",
    "get_secret",
    "get_secrets",
    "validate_config",
    "get_environment_tags",
]