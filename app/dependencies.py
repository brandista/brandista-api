#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brandista API - FastAPI Dependencies
Shared dependencies for authentication, rate limiting, and database access
"""

import time
import logging
from typing import Optional, Dict
from collections import defaultdict
from fastapi import HTTPException, Header, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from app.config import SECRET_KEY, ALGORITHM, RATE_LIMIT_ENABLED, RATE_LIMIT_PER_MINUTE

logger = logging.getLogger(__name__)
security = HTTPBearer()

# Rate limiting storage
request_counts: Dict[str, list] = defaultdict(list)

# ============================================================================
# AUTHENTICATION DEPENDENCIES
# ============================================================================

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Validate JWT token and return current user
    
    Args:
        credentials: HTTP Bearer token from Authorization header
        
    Returns:
        User dict with username and other claims
        
    Raises:
        HTTPException: 401 if token is invalid or expired
    """
    token = credentials.credentials
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        
        if username is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication credentials"
            )
        
        return {"username": username, **payload}
        
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token has expired"
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )

async def get_optional_user(
    authorization: Optional[str] = Header(None)
) -> Optional[dict]:
    """
    Get current user if token is provided, otherwise return None
    Useful for endpoints that work both authenticated and unauthenticated
    
    Args:
        authorization: Optional Authorization header
        
    Returns:
        User dict if authenticated, None otherwise
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    token = authorization.replace("Bearer ", "")
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        
        if username:
            return {"username": username, **payload}
    except (ExpiredSignatureError, InvalidTokenError):
        pass
    
    return None

# ============================================================================
# RATE LIMITING
# ============================================================================

async def check_rate_limit(client_ip: str) -> None:
    """
    Check if client has exceeded rate limit
    
    Args:
        client_ip: Client IP address
        
    Raises:
        HTTPException: 429 if rate limit exceeded
    """
    if not RATE_LIMIT_ENABLED:
        return
    
    now = time.time()
    
    # Clean up old requests (older than 1 minute)
    request_counts[client_ip] = [
        t for t in request_counts[client_ip] 
        if now - t < 60
    ]
    
    # Check if limit exceeded
    if len(request_counts[client_ip]) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {RATE_LIMIT_PER_MINUTE} requests per minute"
        )
    
    # Add current request
    request_counts[client_ip].append(now)

# ============================================================================
# DATABASE DEPENDENCIES
# ============================================================================

# These will be implemented when we extract database logic
# For now, they're placeholders that can be imported

async def get_db_session():
    """
    Get database session (placeholder for future implementation)
    """
    # TODO: Implement proper database session management
    pass

async def get_redis_client():
    """
    Get Redis client (placeholder for future implementation)
    """
    # TODO: Implement Redis client access
    pass
