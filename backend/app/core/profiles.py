"""
Deployment Profiles — P2-4 Configuration Management

Centralizes environment-specific configuration (dev/prod/staging) to avoid mixing
security defaults and local-mode assumptions in runtime code.

PROBLEM (Pre-P2-4):
- CORS origins hardcoded in main.py (localhost + dev server mixed)
- Log level hardcoded to INFO (no dev/prod distinction)
- Cookie secure flag with inline env check (scattered config)
- AUTH_ENABLED with pytest detection inline (anti-pattern)

SOLUTION (P2-4):
- Profile enum: DEV, PROD, STAGING
- Profile-specific config classes with sensible defaults
- Factory function get_config() provides current profile config
- All environment-specific settings centralized in one module

USAGE:
    from app.core.profiles import get_profile, get_config, Profile
    
    if get_profile() == Profile.PROD:
        # Production-only logic
        ...
    
    config = get_config()
    logger.setLevel(config.log_level)
"""
import logging
import os
import sys
from dataclasses import dataclass
from enum import Enum
from typing import List


class Profile(str, Enum):
    """Deployment profile enumeration."""
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


@dataclass(frozen=True)
class ProfileConfig:
    """Base configuration class. Subclassed for each profile."""
    
    # Identity
    profile: Profile
    profile_name: str
    
    # Logging
    log_level: str
    json_logs: bool
    
    # CORS (Cross-Origin Resource Sharing)
    cors_origins: List[str]
    cors_allow_credentials: bool
    cors_allow_methods: List[str]
    
    # Security
    cookie_secure: bool
    auth_enabled: bool
    csrf_protection: bool
    
    # Features
    swagger_ui_enabled: bool
    debug_endpoints: bool
    
    # Performance
    workers: int
    
    def __str__(self) -> str:
        return f"ProfileConfig({self.profile_name})"


# ═══════════════════════════════════════════════════════════════════════════════
# PROFILE CONFIGURATIONS
# ═══════════════════════════════════════════════════════════════════════════════

class DevConfig(ProfileConfig):
    """Development profile: permissive, verbose logging, debug tools enabled."""
    
    def __init__(self):
        # Auto-detect port from env or default 8000
        port = int(os.environ.get("PSEUDONYMIZER_PORT", "8000"))
        
        # In tests: disable auth by default (unless explicitly enabled)
        # This way tests don't need to provide auth tokens
        is_testing = os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules
        auth_enabled_for_dev = not is_testing  # Disable auth in tests
        
        super().__init__(
            profile=Profile.DEV,
            profile_name="Development",
            
            # Logging: verbose for debugging
            log_level=os.environ.get("LOG_LEVEL", "DEBUG"),
            json_logs=False,  # Human-readable logs
            
            # CORS: localhost + dev server (Vite default 5173)
            cors_origins=[
                f"http://127.0.0.1:{port}",
                f"http://localhost:{port}",
                "http://127.0.0.1:5173",  # Vite dev server
                "http://localhost:5173",
                "http://127.0.0.1:3000",  # Alternative frontend port
                "http://localhost:3000",
            ],
            cors_allow_credentials=True,
            cors_allow_methods=["GET", "POST", "DELETE", "PUT", "PATCH"],
            
            # Security: relaxed for local development
            cookie_secure=False,  # Allow HTTP cookies (dev on localhost)
            auth_enabled=auth_enabled_for_dev,  # Disable auth in tests
            csrf_protection=False,  # Disable CSRF for local testing
            
            # Features: all debug tools available
            swagger_ui_enabled=True,  # Swagger UI at /api/docs
            debug_endpoints=True,    # /api/debug/* endpoints
            
            # Performance: single worker for debugging
            workers=1,
        )


class StagingConfig(ProfileConfig):
    """Staging profile: production-like but with debug tools."""
    
    def __init__(self):
        port = int(os.environ.get("PSEUDONYMIZER_PORT", "8000"))
        
        super().__init__(
            profile=Profile.STAGING,
            profile_name="Staging",
            
            # Logging: INFO level, structured logs
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            json_logs=True,  # Structured JSON for log aggregation
            
            # CORS: only staging frontend URL (must be configured)
            cors_origins=[
                os.environ.get("STAGING_FRONTEND_URL", f"https://staging.example.com:{port}"),
            ],
            cors_allow_credentials=True,
            cors_allow_methods=["GET", "POST", "DELETE"],
            
            # Security: production-like
            cookie_secure=True,  # HTTPS required
            auth_enabled=True,
            csrf_protection=True,
            
            # Features: Swagger enabled for QA testing
            swagger_ui_enabled=True,
            debug_endpoints=True,  # Allow debug endpoints for QA
            
            # Performance: moderate workers
            workers=2,
        )


class ProdConfig(ProfileConfig):
    """Production profile: strict security, minimal logging, no debug tools."""
    
    def __init__(self):
        port = int(os.environ.get("PSEUDONYMIZER_PORT", "8000"))
        
        # Require PROD_FRONTEND_URL in production
        frontend_url = os.environ.get("PROD_FRONTEND_URL")
        if not frontend_url:
            # Fallback to localhost (air-gapped deployment)
            frontend_url = f"https://127.0.0.1:{port}"
        
        super().__init__(
            profile=Profile.PROD,
            profile_name="Production",
            
            # Logging: WARNING level, structured JSON
            log_level=os.environ.get("LOG_LEVEL", "WARNING"),
            json_logs=True,  # Structured JSON for SIEM integration
            
            # CORS: only production frontend URL
            cors_origins=[frontend_url],
            cors_allow_credentials=True,
            cors_allow_methods=["GET", "POST", "DELETE"],
            
            # Security: maximum strictness
            cookie_secure=True,  # HTTPS required (enforce Secure flag)
            auth_enabled=True,   # Always require authentication
            csrf_protection=True,  # CSRF tokens mandatory
            
            # Features: no debug tools
            swagger_ui_enabled=False,  # No Swagger UI in production
            debug_endpoints=False,     # Disable /api/debug/*
            
            # Performance: multiple workers
            workers=int(os.environ.get("WORKERS", "4")),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PROFILE DETECTION & FACTORY
# ═══════════════════════════════════════════════════════════════════════════════

def get_profile() -> Profile:
    """
    Detect current deployment profile from environment.
    
    Detection order:
    1. DEPLOYMENT_PROFILE env var (explicit: "dev", "staging", "prod")
    2. Auto-detect from pytest context → DEV
    3. Default: DEV (fail-safe, permissive for local development)
    
    Returns:
        Profile enum (DEV, STAGING, or PROD)
    
    Example:
        >>> os.environ["DEPLOYMENT_PROFILE"] = "prod"
        >>> get_profile()
        <Profile.PROD: 'prod'>
    """
    # 1. Explicit profile from env var
    profile_str = os.environ.get("DEPLOYMENT_PROFILE", "").lower().strip()
    if profile_str:
        try:
            return Profile(profile_str)
        except ValueError:
            # Invalid profile string, log warning and fall back to DEV
            logging.warning(
                "Invalid DEPLOYMENT_PROFILE='%s'. Valid: dev, staging, prod. Falling back to DEV.",
                profile_str
            )
    
    # 2. Auto-detect pytest context → DEV
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        return Profile.DEV
    
    # 3. Default: DEV (permissive for local development)
    return Profile.DEV


def get_config() -> ProfileConfig:
    """
    Get configuration for current deployment profile.
    
    Returns:
        ProfileConfig instance (DevConfig, StagingConfig, or ProdConfig)
    
    Example:
        >>> config = get_config()
        >>> logger.setLevel(config.log_level)
        >>> app.add_middleware(CORSMiddleware, allow_origins=config.cors_origins)
    """
    profile = get_profile()
    
    if profile == Profile.PROD:
        return ProdConfig()
    elif profile == Profile.STAGING:
        return StagingConfig()
    else:  # Profile.DEV
        return DevConfig()


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def is_production() -> bool:
    """Convenience: check if running in production profile."""
    return get_profile() == Profile.PROD


def is_development() -> bool:
    """Convenience: check if running in development profile."""
    return get_profile() == Profile.DEV


def is_staging() -> bool:
    """Convenience: check if running in staging profile."""
    return get_profile() == Profile.STAGING


def print_profile_info() -> None:
    """Print current profile configuration (for startup logging)."""
    config = get_config()
    print("=" * 80)
    print(f"DEPLOYMENT PROFILE: {config.profile_name} ({config.profile.value})")
    print("=" * 80)
    print(f"  Log Level:         {config.log_level}")
    print(f"  JSON Logs:         {config.json_logs}")
    print(f"  CORS Origins:      {', '.join(config.cors_origins)}")
    print(f"  Cookie Secure:     {config.cookie_secure}")
    print(f"  Auth Enabled:      {config.auth_enabled}")
    print(f"  CSRF Protection:   {config.csrf_protection}")
    print(f"  Swagger UI:        {config.swagger_ui_enabled}")
    print(f"  Debug Endpoints:   {config.debug_endpoints}")
    print(f"  Workers:           {config.workers}")
    print("=" * 80)


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════════

# Cache config on module import (avoid repeated env var lookups)
_cached_profile = get_profile()
_cached_config = get_config()


def get_cached_config() -> ProfileConfig:
    """Get cached config (for performance, avoids repeated env lookups)."""
    return _cached_config
