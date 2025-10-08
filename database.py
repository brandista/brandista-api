#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database configuration and models for Brandista API
"""

import os
import logging
from typing import Optional
from sqlalchemy import create_engine, Column, String, Integer, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime

logger = logging.getLogger(__name__)

# Get DATABASE_URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

# Railway gives postgres:// but SQLAlchemy needs postgresql://
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Create engine only if DATABASE_URL exists
engine = None
SessionLocal = None
Base = declarative_base()

if DATABASE_URL:
    try:
        engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,  # Verify connections before using
            pool_size=5,
            max_overflow=10
        )
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        logger.info("✅ Database connection configured successfully")
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        engine = None
        SessionLocal = None
else:
    logger.warning("⚠️ DATABASE_URL not found - using in-memory storage")


# ============================================================================
# DATABASE MODELS
# ============================================================================

class UserDB(Base):
    """User table for persistent storage"""
    __tablename__ = "users"
    
    username = Column(String, primary_key=True, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")
    search_limit = Column(Integer, default=3)
    searches_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ============================================================================
# DATABASE HELPER FUNCTIONS
# ============================================================================

def init_database():
    """Initialize database tables"""
    if engine:
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("✅ Database tables created/verified")
            return True
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            return False
    return False


def get_db() -> Optional[Session]:
    """Get database session"""
    if SessionLocal:
        db = SessionLocal()
        try:
            return db
        except Exception as e:
            logger.error(f"Database session error: {e}")
            db.close()
            return None
    return None


def is_database_available() -> bool:
    """Check if database is available"""
    return engine is not None and SessionLocal is not None


# ============================================================================
# USER CRUD OPERATIONS
# ============================================================================

def create_user_in_db(username: str, hashed_password: str, role: str = "user", search_limit: int = 3) -> bool:
    """Create user in database"""
    db = get_db()
    if not db:
        return False
    
    try:
        user = UserDB(
            username=username,
            hashed_password=hashed_password,
            role=role,
            search_limit=search_limit,
            searches_used=0
        )
        db.add(user)
        db.commit()
        logger.info(f"✅ User created in DB: {username}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to create user {username}: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def get_user_from_db(username: str) -> Optional[dict]:
    """Get user from database"""
    db = get_db()
    if not db:
        return None
    
    try:
        user = db.query(UserDB).filter(UserDB.username == username).first()
        if user:
            return {
                "username": user.username,
                "hashed_password": user.hashed_password,
                "role": user.role,
                "search_limit": user.search_limit,
                "searches_used": user.searches_used
            }
        return None
    except Exception as e:
        logger.error(f"❌ Failed to get user {username}: {e}")
        return None
    finally:
        db.close()


def get_all_users_from_db() -> list:
    """Get all users from database"""
    db = get_db()
    if not db:
        return []
    
    try:
        users = db.query(UserDB).all()
        return [
            {
                "username": u.username,
                "role": u.role,
                "search_limit": u.search_limit,
                "searches_used": u.searches_used
            }
            for u in users
        ]
    except Exception as e:
        logger.error(f"❌ Failed to get users: {e}")
        return []
    finally:
        db.close()


def update_user_in_db(username: str, **kwargs) -> bool:
    """Update user in database"""
    db = get_db()
    if not db:
        return False
    
    try:
        user = db.query(UserDB).filter(UserDB.username == username).first()
        if not user:
            return False
        
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        
        db.commit()
        logger.info(f"✅ User updated in DB: {username}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to update user {username}: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def delete_user_from_db(username: str) -> bool:
    """Delete user from database"""
    db = get_db()
    if not db:
        return False
    
    try:
        user = db.query(UserDB).filter(UserDB.username == username).first()
        if not user:
            return False
        
        db.delete(user)
        db.commit()
        logger.info(f"✅ User deleted from DB: {username}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to delete user {username}: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def sync_hardcoded_users_to_db(users_dict: dict):
    """Sync hardcoded users from USERS_DB to database"""
    if not is_database_available():
        logger.warning("⚠️ Database not available - skipping sync")
        return
    
    for username, user_data in users_dict.items():
        existing = get_user_from_db(username)
        if not existing:
            create_user_in_db(
                username=username,
                hashed_password=user_data["hashed_password"],
                role=user_data["role"],
                search_limit=user_data["search_limit"]
            )
            logger.info(f"📦 Synced hardcoded user to DB: {username}")
