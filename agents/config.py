# agents/config.py
"""
Shared configuration for the Growth Engine.
All modules must import SECRET_KEY from here, never re-define it.
"""
import os
import logging

logger = logging.getLogger(__name__)


def _get_secret_key() -> str:
    key = os.getenv("SECRET_KEY")
    if key:
        return key
    env = os.getenv("ENVIRONMENT", "").lower()
    railway = os.getenv("RAILWAY_ENVIRONMENT", "")
    if env == "production" or railway:
        raise RuntimeError(
            "SECRET_KEY environment variable is required in production. "
            "Set it in Railway variables."
        )
    # Development fallback — stable across restarts, clearly insecure
    dev_key = "DEV-ONLY-INSECURE-KEY-SET-SECRET_KEY-IN-PRODUCTION"
    logger.warning(
        "⚠️  Using insecure dev SECRET_KEY. "
        "Set SECRET_KEY environment variable before deploying to production."
    )
    return dev_key


SECRET_KEY = _get_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
