
# -*- coding: utf-8 -*-
"""Database module for Brandista API - Handles PostgreSQL user management"""

import psycopg2
import os
from typing import Optional, Dict, List, Any
import logging

logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL")

def connect_db():
    if not DATABASE_URL:
        return None
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return None

def init_database():
    conn = connect_db()
    if not conn:
        logger.warning("No database connection - skipping init")
        return
    try:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='password_hash'")
            if cursor.fetchone():
                cursor.execute("ALTER TABLE users RENAME COLUMN password_hash TO hashed_password")
                logger.info("🔧 Auto-fixed: Renamed password_hash to hashed_password")
        except Exception as e:
            logger.warning(f"Column rename check: {e}")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username VARCHAR(100) PRIMARY KEY,
                hashed_password TEXT NOT NULL,
                role VARCHAR(50) NOT NULL DEFAULT 'user',
                search_limit INTEGER NOT NULL DEFAULT 3,
                searches_used INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
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

def create_user_in_db(username: str, hashed_password: str, role: str = 'user', search_limit: int = 3):
    conn = connect_db()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, hashed_password, role, search_limit, searches_used) VALUES (%s, %s, %s, %s, 0) ON CONFLICT (username) DO NOTHING", (username, hashed_password, role, search_limit))
        conn.commit()
        success = cursor.rowcount > 0
        if success:
            logger.info(f"✅ Created user in DB: {username}")
        return success
    except Exception as e:
        logger.error(f"Failed to create user {username}: {e}")
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
        for k in ['search_limit', 'searches_used', 'role']:
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
    conn = connect_db()
    if not conn:
        logger.info("No database - skipping user sync")
        return
    synced = 0
    for username, user_data in users_dict.items():
        try:
            if create_user_in_db(username, user_data['hashed_password'], user_data['role'], user_data['search_limit']):
                synced += 1
        except Exception as e:
            logger.error(f"Failed to sync user {username}: {e}")
    if synced > 0:
        logger.info(f"✅ Synced {synced} users to database")
PYTHON_CODE

echo "✅ OIKEA database.py luotu"
