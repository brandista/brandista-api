#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Database module for Brandista API - Handles PostgreSQL user management"""

import psycopg2
import os
from typing import Optional, Dict, List, Any
import logging

logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL")

# ✅ FIXED: Add DATABASE_ENABLED flag (main.py tries to import this!)
DATABASE_ENABLED = bool(DATABASE_URL)

def connect_db():
    if not DATABASE_URL:
        return None
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return None

def init_database():
    """Initialize database tables and auto-migrate schema if needed"""
    conn = connect_db()
    if not conn:
        logger.warning("No database connection - skipping init")
        return
    try:
        cursor = conn.cursor()
        
        # Fix old column name (backward compatibility)
        try:
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='password_hash'")
            if cursor.fetchone():
                cursor.execute("ALTER TABLE users RENAME COLUMN password_hash TO hashed_password")
                logger.info("🔧 Auto-fixed: Renamed password_hash to hashed_password")
        except Exception as e:
            logger.warning(f"Column rename check: {e}")
        
        # Create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username VARCHAR(100) PRIMARY KEY,
                hashed_password TEXT NOT NULL,
                role VARCHAR(50) NOT NULL DEFAULT 'user',
                search_limit INTEGER NOT NULL DEFAULT 3,
                searches_used INTEGER NOT NULL DEFAULT 0,
                email VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ✅ FIX: Add email column if it doesn't exist (auto-migration)
        try:
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='users' AND column_name='email'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE users ADD COLUMN email VARCHAR(255)")
                logger.info("🔧 Auto-fixed: Added email column to users table")
                conn.commit()
        except Exception as e:
            logger.warning(f"Email column migration check: {e}")
        
        conn.commit()
        logger.info("✅ Database tables initialized")
    except Exception as e:
        logger.error(f"Database init failed: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def is_database_available():
    conn = connect_db()
    if conn:
        conn.close()
        return True
    return False

def get_user_from_db(username: str):
    conn = connect_db()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT username, hashed_password, role, search_limit, searches_used FROM users WHERE username = %s", (username,))
        row = cursor.fetchone()
        if row:
            return {'username': row[0], 'hashed_password': row[1], 'role': row[2], 'search_limit': row[3], 'searches_used': row[4]}
        return None
    except Exception as e:
        logger.error(f"Failed to get user {username}: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def get_all_users_from_db():
    conn = connect_db()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT username, hashed_password, role, search_limit, searches_used FROM users")
        return [{'username': r[0], 'hashed_password': r[1], 'role': r[2], 'search_limit': r[3], 'searches_used': r[4]} for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Failed to get all users: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def create_user_in_db(username: str, hashed_password: str, role: str = 'user', search_limit: int = 3, email: str = None):
    """
    Create or update user in database (UPSERT)
    
    Args:
        username: Username
        hashed_password: Hashed password
        role: User role (user/admin/super_user)
        search_limit: Search quota limit
        email: User email (optional)
    
    Returns:
        bool: True if created or updated successfully
    """
    conn = connect_db()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        
        # ✅ FIX: Use UPSERT to update role/email if user exists
        # This ensures admin role persists across logins!
        cursor.execute("""
            INSERT INTO users (username, hashed_password, role, search_limit, searches_used, email) 
            VALUES (%s, %s, %s, %s, 0, %s) 
            ON CONFLICT (username) DO UPDATE SET
                role = EXCLUDED.role,
                email = EXCLUDED.email,
                hashed_password = EXCLUDED.hashed_password,
                search_limit = EXCLUDED.search_limit,
                updated_at = CURRENT_TIMESTAMP
        """, (username, hashed_password, role, search_limit, email))
        
        conn.commit()
        
        # Check if it was INSERT or UPDATE
        if cursor.rowcount > 0:
            logger.info(f"✅ User saved to DB: {username} (role: {role}, email: {email})")
            return True
        else:
            logger.warning(f"⚠️ No changes made for user: {username}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Failed to save user {username}: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

def update_user_in_db(username: str, **kwargs):
    conn = connect_db()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        fields, values = [], []
        for k in ['search_limit', 'searches_used', 'role', 'email']:
            if k in kwargs:
                fields.append(f"{k} = %s")
                values.append(kwargs[k])
        if not fields:
            return False
        fields.append("updated_at = CURRENT_TIMESTAMP")
        values.append(username)
        cursor.execute(f"UPDATE users SET {', '.join(fields)} WHERE username = %s", values)
        conn.commit()
        success = cursor.rowcount > 0
        if success:
            logger.info(f"✅ Updated user in DB: {username}")
        return success
    except Exception as e:
        logger.error(f"Failed to update user {username}: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

def delete_user_from_db(username: str):
    conn = connect_db()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE username = %s", (username,))
        conn.commit()
        success = cursor.rowcount > 0
        if success:
            logger.info(f"✅ Deleted user from DB: {username}")
        return success
    except Exception as e:
        logger.error(f"Failed to delete user {username}: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

def sync_hardcoded_users_to_db(users_dict):
    """Sync hardcoded users to database (called at startup)"""
    conn = connect_db()
    if not conn:
        logger.info("No database - skipping user sync")
        return
    synced = 0
    for username, user_data in users_dict.items():
        try:
            # Don't pass email for hardcoded users (they don't have it)
            if create_user_in_db(
                username, 
                user_data['hashed_password'], 
                user_data['role'], 
                user_data['search_limit']
            ):
                synced += 1
        except Exception as e:
            logger.error(f"Failed to sync user {username}: {e}")
    if synced > 0:
        logger.info(f"✅ Synced {synced} users to database")
