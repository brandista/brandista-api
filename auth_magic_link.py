#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Magic Link Authentication Module for Brandista - FIXED
Includes MagicLinkUser class definition with role support
"""

import os
import secrets
import smtplib
import json
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import redis
from fastapi import HTTPException, BackgroundTasks, Request, Depends
from pydantic import BaseModel, Field
# SendGrid imports
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, To, Content
    SENDGRID_AVAILABLE = True
except ImportError:
    SENDGRID_AVAILABLE = False
    print("SendGrid not installed - emails will not be sent")
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

class MagicLinkConfig:
    """Magic Link configuration"""
    EXPIRY_MINUTES = int(os.getenv("MAGIC_LINK_EXPIRY_MINUTES", "15"))
    BASE_URL = os.getenv("MAGIC_LINK_BASE_URL", "http://localhost:8000")
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
    
    # Email settings
    EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "smtp")  # smtp, sendgrid, resend
    EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@brandista.eu")
    EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "Brandista")
    
    # SMTP settings
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASS = os.getenv("SMTP_PASS", "")
    
    # SendGrid settings
    SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
    
    # Subscription tiers
    SUBSCRIPTION_TIERS = {
        "free": {
            "name": "Free",
            "search_limit": 1,
            "features": ["1 analysis per month", "Basic features"],
            "price": 0
        },
        "starter": {
            "name": "Competitor Insight",
            "search_limit": 10,
            "features": ["10 analyses per month", "Email support", "Export results"],
            "price": 49
        },
        "pro": {
            "name": "Growth Radar",
            "search_limit": 50,
            "features": ["50 analyses per month", "Priority support", "Team collaboration"],
            "price": 99
        },
        "enterprise": {
            "name": "Enterprise",
            "search_limit": -1,  # Unlimited
            "features": ["Unlimited analyses", "Dedicated support", "Custom integrations", "SLA"],
            "price": 299
        }
    }

config = MagicLinkConfig()

# ============================================================================
# EMAIL SERVICE
# ============================================================================

class MagicLinkEmailService:
    """Email service for sending magic links"""
    
    @staticmethod
    def generate_email_html(email: str, magic_link: str, metadata: Dict[str, Any] = None) -> str:
        """Generate HTML email content"""
        company_name = metadata.get("company_name", "") if metadata else ""
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Sign in to Brandista</title>
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #f3f4f6;">
            <div style="max-width: 600px; margin: 40px auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <!-- Header -->
                <div style="padding: 32px; text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
                    <h1 style="margin: 0; font-size: 28px; color: white;">
                        🚀 Brandista
                    </h1>
                    <p style="margin: 8px 0 0; color: rgba(255,255,255,0.9); font-size: 14px;">
                        Competitive Intelligence Platform
                    </p>
                </div>
                
                <!-- Content -->
                <div style="padding: 40px;">
                    <h2 style="margin: 0 0 16px; font-size: 22px; color: #1f2937;">
                        Welcome back{', ' + company_name if company_name else ''}!
                    </h2>
                    
                    <p style="margin: 0 0 24px; color: #4b5563; font-size: 16px; line-height: 1.5;">
                        Click the button below to securely sign in to your account. No password needed!
                    </p>
                    
                    <!-- CTA Button -->
                    <div style="text-align: center; margin: 32px 0;">
                        <a href="{magic_link}" style="display: inline-block; padding: 14px 32px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px;">
                            Sign In to Brandista
                        </a>
                    </div>
                    
                    <!-- Alternative link -->
                    <div style="margin: 24px 0; padding: 16px; background: #f9fafb; border-radius: 8px; border: 1px solid #e5e7eb;">
                        <p style="margin: 0 0 8px; color: #6b7280; font-size: 13px;">
                            Or copy and paste this link:
                        </p>
                        <p style="margin: 0; word-break: break-all; color: #4f46e5; font-size: 13px;">
                            {magic_link}
                        </p>
                    </div>
                    
                    <!-- Security notice -->
                    <div style="margin: 24px 0 0; padding: 12px; background: #fef3c7; border-left: 3px solid #f59e0b; border-radius: 4px;">
                        <p style="margin: 0; color: #92400e; font-size: 13px;">
                            <strong>🔒 Security:</strong> This link expires in {config.EXPIRY_MINUTES} minutes and can only be used once.
                        </p>
                    </div>
                </div>
                
                <!-- Footer -->
                <div style="padding: 20px 40px; background: #f9fafb; border-top: 1px solid #e5e7eb;">
                    <p style="margin: 0; color: #9ca3af; font-size: 12px; text-align: center;">
                        If you didn't request this, please ignore this email.
                    </p>
                    <p style="margin: 8px 0 0; color: #9ca3af; font-size: 12px; text-align: center;">
                        © 2025 Brandista. All rights reserved.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
    
    @staticmethod
    async def send_magic_link(email: str, token: str, metadata: Dict[str, Any] = None) -> bool:
        """Send magic link email"""
        
        # Remove trailing slash to avoid double slashes
        frontend_url = config.FRONTEND_URL.rstrip('/')
        # ✅ FINAL FIX: No /growthengine prefix - Router handles all routing
        magic_link = f"{frontend_url}/auth/magic-link/verify?token={token}"  
        html = MagicLinkEmailService.generate_email_html(email, magic_link, metadata)
        subject = "🚀 Sign in to Brandista"
        
        try:
            # SendGrid sending
            if config.EMAIL_PROVIDER == "sendgrid" and config.SENDGRID_API_KEY:
            
                
                message = Mail(
                    from_email=Email(config.EMAIL_FROM, config.EMAIL_FROM_NAME),
                    to_emails=To(email),
                    subject=subject,
                    html_content=Content("text/html", html)
                )
                
                sg = SendGridAPIClient(config.SENDGRID_API_KEY)
                response = sg.send(message)
                
                logger.info(f"Magic link sent via SendGrid to {email}: {response.status_code}")
                return response.status_code in [200, 201, 202]
            
            # SMTP sending
            elif config.EMAIL_PROVIDER == "smtp" and config.SMTP_USER and config.SMTP_PASS:
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart
                
                msg = MIMEMultipart('alternative')
                msg['Subject'] = subject
                msg['From'] = f"{config.EMAIL_FROM_NAME} <{config.EMAIL_FROM}>"
                msg['To'] = email
                
                text_part = MIMEText(f"Sign in to Brandista: {magic_link}", 'plain')
                html_part = MIMEText(html, 'html')
                
                msg.attach(text_part)
                msg.attach(html_part)
                
                with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
                    server.starttls()
                    server.login(config.SMTP_USER, config.SMTP_PASS)
                    server.send_message(msg)
                
                logger.info(f"Magic link sent via SMTP to {email}")
                return True
            
            else:
                logger.warning(f"No email provider configured - magic link not sent to {email}")
                logger.info(f"Magic link URL: {magic_link}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send magic link to {email}: {e}")
            return False

# ============================================================================
# DATA MODELS
# ============================================================================

class MagicLinkRequest(BaseModel):
    email: str = Field(..., pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    redirect_url: Optional[str] = Field(None, description="URL to redirect after login")

class MagicLinkVerify(BaseModel):
    token: str = Field(..., min_length=32)

class UserProfile(BaseModel):
    user_id: str
    email: str
    full_name: Optional[str] = None
    company: Optional[str] = None
    subscription_tier: str = "free"
    search_limit: int = 1
    searches_used: int = 0
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    next_billing_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)
    last_login: Optional[datetime] = None
    email_verified: bool = False
    onboarding_completed: bool = False

# ✅ TÄRKEÄ: MagicLinkUser luokka määritelty ENNEN MagicLinkUserManager luokkaa!
class MagicLinkUser(BaseModel):
    """User model for magic link authentication with role support"""
    user_id: str
    email: str
    username: Optional[str] = None
    full_name: Optional[str] = None
    company: Optional[str] = None
    role: str = "user"  # user, admin, super_user
    subscription_tier: str = "free"
    search_limit: int = 1
    searches_used: int = 0
    last_login: Optional[datetime] = None
    email_verified: bool = False

# ============================================================================
# STORAGE BACKENDS
# ============================================================================

class MagicLinkStorage:
    """Abstract storage interface for magic links"""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None, postgres_conn: Optional[Any] = None):
        self.redis_client = redis_client
        self.postgres_conn = postgres_conn
        self._memory_store: Dict[str, Dict[str, Any]] = {}
    
    async def store_token(self, token: str, email: str, expires_at: datetime, metadata: Dict[str, Any] = None) -> bool:
        """Store magic link token"""
        
        # Try Redis first
        if self.redis_client:
            try:
                key = f"magic_link:{token}"
                data = {
                    "email": email,
                    "expires_at": expires_at.isoformat(),
                    "used": False,
                    "created_at": datetime.now().isoformat(),
                    "metadata": metadata or {}
                }
                
                ttl = int((expires_at - datetime.now()).total_seconds())
                self.redis_client.setex(key, ttl, json.dumps(data))
                
                # Track by email
                email_key = f"magic_links_by_email:{email}"
                self.redis_client.sadd(email_key, token)
                self.redis_client.expire(email_key, ttl)
                
                logger.info(f"Magic link stored in Redis for {email}")
                return True
            except Exception as e:
                logger.error(f"Redis storage failed: {e}")
        
        # Try PostgreSQL
        if self.postgres_conn:
            try:
                import psycopg2
                cursor = self.postgres_conn.cursor()
                cursor.execute("""
                    INSERT INTO magic_links (token, email, expires_at, ip_address, user_agent)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    token, email, expires_at,
                    metadata.get("ip_address") if metadata else None,
                    metadata.get("user_agent") if metadata else None
                ))
                self.postgres_conn.commit()
                cursor.close()
                logger.info(f"Magic link stored in PostgreSQL for {email}")
                return True
            except Exception as e:
                logger.error(f"PostgreSQL storage failed: {e}")
        
        # Fallback to memory
        self._memory_store[token] = {
            "email": email,
            "expires_at": expires_at,
            "used": False,
            "metadata": metadata or {}
        }
        logger.info(f"Magic link stored in memory for {email}")
        return True
    
    async def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and consume magic link token"""
        
        # Check Redis first
        if self.redis_client:
            try:
                key = f"magic_link:{token}"
                data = self.redis_client.get(key)
                
                if data:
                    link_data = json.loads(data)
                    expires_at = datetime.fromisoformat(link_data["expires_at"])
                    
                    if datetime.now() > expires_at:
                        self.redis_client.delete(key)
                        return None
                    
                    if link_data.get("used", False):
                        return None
                    
                    # Mark as used
                    link_data["used"] = True
                    link_data["used_at"] = datetime.now().isoformat()
                    
                    ttl = self.redis_client.ttl(key)
                    if ttl > 0:
                        self.redis_client.setex(key, ttl, json.dumps(link_data))
                    
                    return link_data
            except Exception as e:
                logger.error(f"Redis verification failed: {e}")
        
        # Check PostgreSQL
        if self.postgres_conn:
            try:
                import psycopg2.extras
                cursor = self.postgres_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute("""
                    SELECT * FROM magic_links 
                    WHERE token = %s AND expires_at > NOW() AND used = FALSE
                """, (token,))
                
                db_link = cursor.fetchone()
                
                if db_link:
                    cursor.execute("UPDATE magic_links SET used = TRUE WHERE token = %s", (token,))
                    self.postgres_conn.commit()
                    cursor.close()
                    
                    return {
                        "email": db_link["email"],
                        "metadata": {
                            "ip_address": db_link.get("ip_address"),
                            "user_agent": db_link.get("user_agent")
                        }
                    }
                
                cursor.close()
            except Exception as e:
                logger.error(f"PostgreSQL verification failed: {e}")
        
        # Check memory
        if token in self._memory_store:
            link_data = self._memory_store[token]
            
            if datetime.now() > link_data["expires_at"]:
                del self._memory_store[token]
                return None
            
            if link_data.get("used", False):
                return None
            
            link_data["used"] = True
            return link_data
        
        return None
    
    async def check_rate_limit(self, email: str, max_attempts: int = 5) -> bool:
        """Check if email has exceeded rate limit"""
        
        if self.redis_client:
            try:
                key = f"magic_link_rate:{email}"
                attempts = self.redis_client.incr(key)
                
                if attempts == 1:
                    self.redis_client.expire(key, 3600)  # 1 hour
                
                return attempts <= max_attempts
            except Exception as e:
                logger.error(f"Rate limit check failed: {e}")
        
        # No rate limiting without Redis
        return True



# ============================================================================
# USER MANAGEMENT - WITH ROLE SUPPORT
# ============================================================================

class MagicLinkUserManager:
    """User management for magic link authentication"""
    
    def __init__(self, storage):
        self.storage = storage
        self._memory_users: Dict[str, MagicLinkUser] = {}
    
    async def get_user_by_email(self, email: str) -> Optional[MagicLinkUser]:
        """Get user from PostgreSQL or memory - WITH ROLE"""
        
        # Try PostgreSQL first
        if self.storage.postgres_conn:
            try:
                cursor = self.storage.postgres_conn.cursor()
                cursor.execute("""
                    SELECT user_id, email, full_name, company, subscription_tier, 
                           search_limit, searches_used, last_login, email_verified,
                           role, username
                    FROM user_profiles 
                    WHERE email = %s
                """, (email,))
                
                row = cursor.fetchone()
                cursor.close()
                
                if row:
                    return MagicLinkUser(
                        user_id=row[0],
                        email=row[1],
                        full_name=row[2],
                        company=row[3],
                        subscription_tier=row[4],
                        search_limit=row[5],
                        searches_used=row[6],
                        last_login=row[7],
                        email_verified=row[8],
                        role=row[9] or "user",  # ✅ LUE ROOLI TIETOKANNASTA!
                        username=row[10]
                    )
            except Exception as e:
                logger.error(f"Failed to get user from PostgreSQL: {e}")
        
        # Fallback to memory
        return self._memory_users.get(email)
    
    async def get_or_create_user(self, email: str, metadata: Dict = None) -> MagicLinkUser:
        """Get existing user or create new one - RESPECTS ROLE FROM DB"""
        
        # ✅ TÄRKEÄ: Hae käyttäjä tietokannasta ENSIN
        user = await self.get_user_by_email(email)
        
        if user:
            # ✅ Löytyi - päivitä vain last_login
            if self.storage.postgres_conn:
                try:
                    cursor = self.storage.postgres_conn.cursor()
                    cursor.execute("""
                        UPDATE user_profiles 
                        SET last_login = %s 
                        WHERE email = %s
                    """, (datetime.now(), email))
                    self.storage.postgres_conn.commit()
                    cursor.close()
                    logger.info(f"Updated last_login for existing user {email} with role {user.role}")
                except Exception as e:
                    logger.error(f"Failed to update last_login: {e}")
            
            # Update memory cache
            self._memory_users[email] = user
            return user
        
        # ❌ EI löytynyt - luo uusi käyttäjä (oletus: user)
        logger.info(f"Creating NEW user for {email} (not found in database)")
        
        user = MagicLinkUser(
            user_id=hashlib.sha256(email.encode()).hexdigest()[:16],
            email=email,
            full_name=metadata.get("full_name") if metadata else None,
            company=metadata.get("company") if metadata else None,
            role="user",  # Uudet käyttäjät ovat "user" - admin täytyy asettaa manuaalisesti
            subscription_tier="free",
            search_limit=config.SUBSCRIPTION_TIERS["free"]["search_limit"],
            email_verified=True,
            last_login=datetime.now()
        )
        
        # ✅ Tallenna uusi käyttäjä PostgreSQL:ään
        if self.storage.postgres_conn:
            try:
                cursor = self.storage.postgres_conn.cursor()
                cursor.execute("""
                    INSERT INTO user_profiles 
                    (user_id, email, full_name, company, subscription_tier, search_limit, 
                     email_verified, last_login, role, username, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (email) DO UPDATE SET last_login = EXCLUDED.last_login
                """, (
                    user.user_id, user.email, user.full_name, user.company,
                    user.subscription_tier, user.search_limit, user.email_verified,
                    user.last_login, user.role, user.username
                ))
                self.storage.postgres_conn.commit()
                cursor.close()
                logger.info(f"Inserted new user {email} to PostgreSQL with role '{user.role}'")
            except Exception as e:
                logger.error(f"Failed to insert new user to PostgreSQL: {e}")
        
        self._memory_users[email] = user
        return user
    
    async def update_subscription(self, email: str, tier: str) -> bool:
        """Update user subscription tier"""
        
        if tier not in config.SUBSCRIPTION_TIERS:
            return False
        
        # Update in PostgreSQL
        if self.storage.postgres_conn:
            try:
                cursor = self.storage.postgres_conn.cursor()
                cursor.execute("""
                    UPDATE user_profiles 
                    SET subscription_tier = %s, search_limit = %s, updated_at = NOW()
                    WHERE email = %s
                """, (
                    tier,
                    config.SUBSCRIPTION_TIERS[tier]["search_limit"],
                    email
                ))
                self.storage.postgres_conn.commit()
                cursor.close()
                logger.info(f"Updated subscription for {email} to {tier}")
                return True
            except Exception as e:
                logger.error(f"Failed to update subscription: {e}")
        
        # Update in memory
        if email in self._memory_users:
            self._memory_users[email].subscription_tier = tier
            self._memory_users[email].search_limit = config.SUBSCRIPTION_TIERS[tier]["search_limit"]
            return True
        
        return False

# ============================================================================
# MAIN MAGIC LINK AUTHENTICATION CLASS
# ============================================================================

class MagicLinkAuth:
    """Main class for magic link authentication"""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None, postgres_conn: Optional[Any] = None):
        self.storage = MagicLinkStorage(redis_client, postgres_conn)
        self.email_service = MagicLinkEmailService()
        self.user_manager = MagicLinkUserManager(self.storage)
    
    async def send_magic_link(
        self,
        email: str,
        request: Request,
        background_tasks: BackgroundTasks,
        redirect_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send magic link to user"""
        
        email = email.lower().strip()
        
        # Rate limiting
        if not await self.storage.check_rate_limit(email):
            raise HTTPException(429, "Too many magic link requests. Please try again later.")
        
        # Generate token
        token = secrets.token_hex(32)
        expires_at = datetime.now() + timedelta(minutes=config.EXPIRY_MINUTES)
        
        # Store metadata
        metadata = {
            "ip_address": request.client.host,
            "user_agent": request.headers.get("user-agent", ""),
            "redirect_url": redirect_url
        }
        
        # Store token
        await self.storage.store_token(token, email, expires_at, metadata)
        
        # Send email in background
        background_tasks.add_task(
            self.email_service.send_magic_link,
            email, token, metadata
        )
        
        logger.info(f"Magic link requested for {email} from IP {metadata['ip_address']}")
        
        return {
            "success": True,
            "message": "Magic link sent! Check your email to sign in.",
            "expires_in_minutes": config.EXPIRY_MINUTES
        }
    
    async def verify_magic_link(self, token: str, request: Request) -> Dict[str, Any]:
        """Verify magic link and create session"""
        
        # Verify token
        link_data = await self.storage.verify_token(token)
        
        if not link_data:
            raise HTTPException(400, "Invalid or expired magic link")
        
        email = link_data["email"]
        
        # Get or create user
        user = await self.user_manager.get_or_create_user(email, link_data.get("metadata"))
        
        # Track login activity
        logger.info(f"User {email} logged in via magic link from IP {request.client.host}")
        
        return {
            "valid": True,      # Backend expects 'valid' field
            "success": True,    # Keep for compatibility
            "user": user.dict(),
            "redirect_url": link_data.get("metadata", {}).get("redirect_url")
        }
    
    async def get_subscription_tiers(self) -> Dict[str, Any]:
        """Get available subscription tiers"""
        return {
            "tiers": config.SUBSCRIPTION_TIERS,
            "currency": "EUR",
            "billing_cycles": ["monthly", "yearly"]
        }
    
    async def upgrade_subscription(self, email: str, tier: str) -> Dict[str, Any]:
        """Upgrade user subscription"""
        
        if tier not in config.SUBSCRIPTION_TIERS:
            raise HTTPException(400, "Invalid subscription tier")
        
        success = await self.user_manager.update_subscription(email, tier)
        
        if not success:
            raise HTTPException(500, "Failed to upgrade subscription")
        
        tier_info = config.SUBSCRIPTION_TIERS[tier]
        
        return {
            "success": True,
            "message": f"Upgraded to {tier_info['name']} plan",
            "new_tier": tier,
            "new_limit": tier_info["search_limit"],
            "features": tier_info["features"]
        }

# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_magic_link_auth(redis_client: Optional[redis.Redis] = None, postgres_conn: Optional[Any] = None) -> MagicLinkAuth:
    """Factory function to create MagicLinkAuth instance"""
    return MagicLinkAuth(redis_client, postgres_conn)

# ============================================================================
# DATABASE SCHEMA
# ============================================================================

MAGIC_LINK_SCHEMA = """
-- Magic links table
CREATE TABLE IF NOT EXISTS magic_links (
    token VARCHAR(255) PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(45),
    user_agent TEXT
);

CREATE INDEX IF NOT EXISTS idx_magic_links_email ON magic_links(email);
CREATE INDEX IF NOT EXISTS idx_magic_links_expires ON magic_links(expires_at);

-- User profiles table
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id VARCHAR(255) PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    company VARCHAR(255),
    subscription_tier VARCHAR(50) DEFAULT 'free',
    search_limit INTEGER DEFAULT 1,
    searches_used INTEGER DEFAULT 0,
    stripe_customer_id VARCHAR(255),
    stripe_subscription_id VARCHAR(255),
    next_billing_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    email_verified BOOLEAN DEFAULT FALSE,
    onboarding_completed BOOLEAN DEFAULT FALSE,
    role VARCHAR(50) DEFAULT 'user',
    username VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_user_profiles_email ON user_profiles(email);
CREATE INDEX IF NOT EXISTS idx_user_profiles_stripe ON user_profiles(stripe_customer_id);
"""
