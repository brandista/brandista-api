#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Health and Info Endpoints
Simple endpoints for health checks and API information
"""

from datetime import datetime
from fastapi import APIRouter, Depends

# We'll import from the old main.py for now to keep things working
# This will be refactored incrementally
import sys
sys.path.insert(0, '/Users/tuukka/Downloads/Projects/brandista-api-git')

from app.config import APP_NAME, APP_VERSION, SCORING_CONFIG

router = APIRouter(tags=["Health"])

@router.get("/")
async def root():
    """API root endpoint with basic information"""
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "status": "operational",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "redoc": "/redoc"
        }
    }

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": APP_VERSION,
        "timestamp": datetime.now().isoformat(),
        "scoring": {
            "weights": SCORING_CONFIG.weights,
            "configurable": True
        }
    }
