#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brandista API - New Modular Main Application
This is the refactored entry point that gradually migrates from the legacy main.py
"""

import os
import sys
import logging
from contextlib import asynccontextmanager

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')

# Setup logging early
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('brandista_api.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import APP_NAME, APP_VERSION, SECRET_KEY

# Import legacy main for gradual migration
# This allows us to use existing functionality while refactoring
import main as legacy_main

# ============================================================================
# LIFESPAN CONTEXT MANAGER
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown"""
    logger.info(f"🚀 Starting {APP_NAME} v{APP_VERSION}")
    
    # Initialize services from legacy main
    if hasattr(legacy_main, 'init_users'):
        legacy_main.init_users()
    
    # Initialize database if available
    if hasattr(legacy_main, 'DATABASE_ENABLED') and legacy_main.DATABASE_ENABLED:
        try:
            if hasattr(legacy_main, 'init_database'):
                legacy_main.init_database()
            logger.info("✅ Database initialized")
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
    
    # Initialize history database if available
    if hasattr(legacy_main, 'HISTORY_DB_AVAILABLE') and legacy_main.HISTORY_DB_AVAILABLE:
        try:
            if legacy_main.AnalysisHistoryDB:
                # Get database URL from environment or legacy main
                # Use same database as main if HISTORY_DATABASE_URL not set
                db_url = (
                    os.getenv('HISTORY_DATABASE_URL') or 
                    os.getenv('DATABASE_URL') or 
                    getattr(legacy_main, 'HISTORY_DATABASE_URL', None)
                )
                if db_url:
                    legacy_main.history_db = legacy_main.AnalysisHistoryDB(db_url)
                    await legacy_main.history_db.connect()
                    logger.info("✅ Analysis history database connected")
                else:
                    logger.warning("⚠️ History database URL not configured")
        except Exception as e:
            logger.error(f"❌ History DB initialization failed: {e}")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down application")
    
    # Close history database
    if hasattr(legacy_main, 'history_db') and legacy_main.history_db:
        try:
            await legacy_main.history_db.disconnect()
            logger.info("🗄️ Analysis history database closed")
        except Exception as e:
            logger.error(f"❌ Error closing history DB: {e}")

# ============================================================================
# CREATE FASTAPI APP
# ============================================================================

app = FastAPI(
    title=APP_NAME,
    description="Brandista Competitive Intelligence API - Refactored Modular Version",
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# ============================================================================
# MIDDLEWARE
# ============================================================================

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://brandista.eu",
        "https://www.brandista.eu",
        "http://brandista.eu",
        "http://www.brandista.eu",
        "https://api.brandista.eu",
        "https://fastapi-production-51f9.up.railway.app",
        "https://3000-ip92lxeccquecaiidxzl0-6aa4782a.manusvm.computer"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Requested-With",
        "Accept",
        "Origin",
        "Access-Control-Request-Method",
        "Access-Control-Request-Headers"
    ],
    expose_headers=["*"],
    max_age=600
)

# Session middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="brandista_session",
    max_age=3600,
    same_site="lax",
    https_only=True
)

# UTF-8 middleware
class UTF8Middleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if "application/json" in response.headers.get("content-type", ""):
            response.headers["content-type"] = "application/json; charset=utf-8"
        return response

app.add_middleware(UTF8Middleware)

# ============================================================================
# REGISTER ROUTERS
# ============================================================================

# Import and register new modular routers
try:
    from app.routers import health
    app.include_router(health.router, tags=["Health"])
    logger.info("✅ Health router registered")
except Exception as e:
    logger.warning(f"⚠️ Health router not available: {e}")

# Chat router with GPT integration
try:
    from app.routers import chat
    app.include_router(chat.router, tags=["Chat"])
    logger.info("✅ GPT-powered chat router registered")
except Exception as e:
    logger.warning(f"⚠️ Chat router not available: {e}")

# Import legacy routers from main.py
# These will be gradually migrated to app/routers/

# Agent System
if hasattr(legacy_main, 'AGENT_SYSTEM_AVAILABLE') and legacy_main.AGENT_SYSTEM_AVAILABLE:
    if hasattr(legacy_main, 'agent_router') and legacy_main.agent_router:
        app.include_router(legacy_main.agent_router)
        logger.info("✅ Agent System routes registered")

# Notification WebSocket
if hasattr(legacy_main, 'NOTIFICATION_WS_AVAILABLE') and legacy_main.NOTIFICATION_WS_AVAILABLE:
    if hasattr(legacy_main, 'notification_router') and legacy_main.notification_router:
        app.include_router(legacy_main.notification_router)
        logger.info("✅ Notification WebSocket routes registered")

# Agent Chat V2
if hasattr(legacy_main, 'AGENT_CHAT_V2_AVAILABLE') and legacy_main.AGENT_CHAT_V2_AVAILABLE:
    if hasattr(legacy_main, 'agent_chat_router') and legacy_main.agent_chat_router:
        app.include_router(legacy_main.agent_chat_router, prefix="/api/v1/agents", tags=["Agent Chat V2"])
        logger.info("✅ Agent Chat V2 routes registered")

# AI Reports
if hasattr(legacy_main, 'AI_REPORTS_AVAILABLE') and legacy_main.AI_REPORTS_AVAILABLE:
    if hasattr(legacy_main, 'reports_router') and legacy_main.reports_router:
        app.include_router(legacy_main.reports_router, tags=["AI Reports"])
        logger.info("✅ AI Reports routes registered")

# Company Intelligence
if hasattr(legacy_main, 'COMPANY_INTEL_AVAILABLE') and legacy_main.COMPANY_INTEL_AVAILABLE:
    if hasattr(legacy_main, 'company_router') and legacy_main.company_router:
        app.include_router(legacy_main.company_router, prefix="/api/v1/company", tags=["Company Intelligence"])
        logger.info("✅ Company Intelligence routes registered")

# Unified Context
if hasattr(legacy_main, 'UNIFIED_CONTEXT_AVAILABLE') and legacy_main.UNIFIED_CONTEXT_AVAILABLE:
    if hasattr(legacy_main, 'context_router') and legacy_main.context_router:
        app.include_router(legacy_main.context_router)
        logger.info("✅ Unified Context routes registered")

# Scheduled Analysis
try:
    from scheduled_analysis import scheduled_router
    app.include_router(scheduled_router)
    logger.info("✅ Scheduled Analysis routes registered")
except ImportError:
    logger.warning("⚠️ Scheduled Analysis routes not available")

# History API
try:
    from history_api import history_router
    app.include_router(history_router)
    logger.info("✅ History API routes registered")
except ImportError:
    logger.warning("⚠️ History API routes not available")

# Chat WebSocket
try:
    from chat_ws import chat_ws_router
    app.include_router(chat_ws_router)
    logger.info("✅ Chat WebSocket registered: /ws/chat")
except ImportError as e:
    logger.warning(f"⚠️ Chat WebSocket not available: {e}")

# ============================================================================
# LEGACY ENDPOINTS (TO BE MIGRATED)
# ============================================================================

# For now, we'll import all endpoints from legacy main.py
# These will be gradually migrated to app/routers/

# Import all the endpoint functions and re-register them
# This is a temporary bridge during migration

# Auth endpoints
if hasattr(legacy_main, 'login'):
    app.post("/auth/login", response_model=legacy_main.TokenResponse)(legacy_main.login)
if hasattr(legacy_main, 'get_current_user_info'):
    app.get("/auth/me")(legacy_main.get_current_user_info)

# Magic link endpoints
if hasattr(legacy_main, 'request_magic_link'):
    app.post("/auth/magic-link/request")(legacy_main.request_magic_link)
if hasattr(legacy_main, 'verify_magic_link_get'):
    app.get("/auth/magic-link/verify")(legacy_main.verify_magic_link_get)

# Google OAuth endpoints
if hasattr(legacy_main, 'oauth_status'):
    app.get("/auth/oauth-status")(legacy_main.oauth_status)
if hasattr(legacy_main, 'google_login'):
    app.get("/auth/google/login")(legacy_main.google_login)
if hasattr(legacy_main, 'google_callback'):
    app.get("/auth/google/callback")(legacy_main.google_callback)

# Analysis endpoints
if hasattr(legacy_main, 'calculate_revenue_impact'):
    app.post("/api/v1/calculate-impact")(legacy_main.calculate_revenue_impact)
if hasattr(legacy_main, 'discover_competitors'):
    app.post("/api/v1/discover-competitors", tags=["Competitor Discovery"])(legacy_main.discover_competitors)
if hasattr(legacy_main, 'get_discovery_status'):
    app.get("/api/v1/discovery-status/{task_id}", tags=["Competitor Discovery"])(legacy_main.get_discovery_status)
if hasattr(legacy_main, 'get_discovery_results'):
    app.get("/api/v1/discovery-results/{task_id}", tags=["Competitor Discovery"])(legacy_main.get_discovery_results)
if hasattr(legacy_main, 'ai_analyze'):
    app.post("/api/v1/ai-analyze")(legacy_main.ai_analyze)
if hasattr(legacy_main, 'get_my_discoveries'):
    app.get("/api/v1/my-discoveries")(legacy_main.get_my_discoveries)

# History endpoints
if hasattr(legacy_main, 'get_analysis_history'):
    app.get("/api/v1/analysis-history", tags=["History"])(legacy_main.get_analysis_history)
if hasattr(legacy_main, 'get_analysis_by_id'):
    app.get("/api/v1/analysis-history/{analysis_id}", tags=["History"])(legacy_main.get_analysis_by_id)
if hasattr(legacy_main, 'get_user_usage'):
    app.get("/api/v1/user-usage", tags=["History"])(legacy_main.get_user_usage)

# Subscription endpoints
if hasattr(legacy_main, 'create_checkout'):
    app.post("/api/subscription/checkout")(legacy_main.create_checkout)
if hasattr(legacy_main, 'get_current_subscription'):
    app.get("/api/subscription/current")(legacy_main.get_current_subscription)
if hasattr(legacy_main, 'manage_subscription'):
    app.get("/api/subscription/manage")(legacy_main.manage_subscription)
if hasattr(legacy_main, 'stripe_webhook'):
    app.post("/api/webhooks/stripe")(legacy_main.stripe_webhook)

# Admin endpoints
if hasattr(legacy_main, 'reset_all_users'):
    app.post("/admin/reset-all")(legacy_main.reset_all_users)
if hasattr(legacy_main, 'reset_user'):
    app.post("/admin/reset/{username}")(legacy_main.reset_user)
if hasattr(legacy_main, 'list_users'):
    app.get("/admin/users", response_model=legacy_main.List[legacy_main.UserQuotaView])(legacy_main.list_users)
if hasattr(legacy_main, 'update_user_quota'):
    app.post("/admin/users/{username}/quota", response_model=legacy_main.UserQuotaView)(legacy_main.update_user_quota)
if hasattr(legacy_main, 'create_user'):
    app.post("/admin/users", response_model=legacy_main.UserQuotaView)(legacy_main.create_user)
if hasattr(legacy_main, 'update_user_role'):
    app.put("/admin/users/{username}/role")(legacy_main.update_user_role)
if hasattr(legacy_main, 'delete_user'):
    app.delete("/admin/users/{username}")(legacy_main.delete_user)

# Competitive radar
if hasattr(legacy_main, 'competitive_radar'):
    app.post("/api/v1/competitive-radar", response_model=legacy_main.CompetitiveRadarResponse)(legacy_main.competitive_radar)

# Delete discovery
if hasattr(legacy_main, 'delete_discovery'):
    app.delete("/api/v1/discoveries/{task_id}")(legacy_main.delete_discovery)

# Config endpoint
if hasattr(legacy_main, 'get_config'):
    app.get("/api/v1/config")(legacy_main.get_config)

# OPTIONS handler
@app.options("/{full_path:path}")
async def options_handler():
    return {}

logger.info(f"✅ {APP_NAME} v{APP_VERSION} initialized successfully")
logger.info("📝 Note: This is a transitional version during refactoring")
logger.info("🔄 Endpoints are being gradually migrated to app/routers/")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
