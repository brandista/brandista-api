"""
Integration patch for main.py to add analysis history
Add these changes to your main_merged.py file
"""

# ============================================================================
# 1. ADD IMPORTS (add after existing imports)
# ============================================================================

from analysis_history_db import AnalysisHistoryDB, AnalysisRecord, UserUsage

# ============================================================================
# 2. INITIALIZE DATABASE (add to startup)
# ============================================================================

# Add this global variable near other globals (around line 700)
history_db: Optional[AnalysisHistoryDB] = None

# Add this to @app.on_event("startup") function:
@app.on_event("startup")
async def startup_event():
    # ... existing startup code ...
    
    # Initialize analysis history database
    global history_db
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        try:
            history_db = AnalysisHistoryDB(database_url)
            await history_db.connect()
            logger.info("✅ Analysis history database initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize history DB: {e}")
            history_db = None
    else:
        logger.warning("⚠️ DATABASE_URL not set, history disabled")

@app.on_event("shutdown")
async def shutdown_event():
    # ... existing shutdown code ...
    
    # Close history database
    if history_db:
        await history_db.disconnect()

# ============================================================================
# 3. MODIFY AI ANALYZE ENDPOINT (around line 8234)
# ============================================================================

@app.post("/api/v1/ai-analyze")
async def ai_analyze_comprehensive(
    request: CompetitorAnalysisRequest,
    background_tasks: BackgroundTasks,
    user: UserInfo = Depends(require_user)
):
    """Complete comprehensive website analysis with full SPA support."""
    try:
        # === QUOTA CHECK - NOW FROM DATABASE ===
        if user.role != "admin" and history_db:
            can_proceed, error_msg = await history_db.check_user_limit(
                user.username, 
                'single'
            )
            if not can_proceed:
                raise HTTPException(
                    status_code=403,
                    detail=error_msg or "Analysis limit reached"
                )
        
        # === URL VALIDATION ===
        url = clean_url(request.url)
        _reject_ssrf(url)
        
        # === PERFORM ANALYSIS ===
        result = await _perform_comprehensive_analysis_internal(
            url=url,
            company_name=request.company_name,
            language=request.language,
            force_playwright=getattr(request, 'force_playwright', False),
            user=user,
            revenue_input=None
        )
        
        # === SAVE TO DATABASE ===
        if history_db:
            try:
                analysis_id = await history_db.save_single_analysis(
                    user_id=user.username,
                    url=url,
                    company_name=request.company_name,
                    language=request.language,
                    analysis_result=result
                )
                logger.info(f"💾 Analysis saved: ID {analysis_id}")
            except Exception as e:
                logger.error(f"Failed to save analysis: {e}")
                # Continue even if save fails
        
        # === POST-PROCESSING ===
        # Remove old quota system if using database
        if not history_db and user.role != "admin":
            user_search_counts[user.username] = user_search_counts.get(user.username, 0) + 1
        
        background_tasks.add_task(cleanup_cache)
        
        logger.info(
            f"✅ Analysis complete for {user.username}: {url} | "
            f"Score: {result['basic_analysis']['digital_maturity_score']}"
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis error: {e}", exc_info=True)
        raise HTTPException(500, f"Analysis failed: {str(e)}")

# ============================================================================
# 4. MODIFY COMPETITOR DISCOVERY (in background task, around line 7900)
# ============================================================================

# In the background_discover_and_analyze function, add at the end:

async def background_discover_and_analyze(...):
    # ... existing discovery code ...
    
    # At the very end, after task is marked complete:
    if history_db and task_data.get("status") == "completed":
        try:
            await history_db.save_competitor_discovery(
                user_id=username,
                url=user_url,
                industry=industry,
                country_code=language,
                max_competitors=max_competitors,
                search_terms=search_terms_used,
                search_provider=search_provider_used,
                competitors=competitor_analyses,
                summary=task_data.get("summary")
            )
            logger.info(f"💾 Discovery saved to database")
        except Exception as e:
            logger.error(f"Failed to save discovery: {e}")

# ============================================================================
# 5. ADD NEW HISTORY ENDPOINTS
# ============================================================================

@app.get("/api/v1/analysis-history", tags=["History"])
async def get_analysis_history(
    limit: int = 20,
    analysis_type: Optional[str] = None,
    user: UserInfo = Depends(require_user)
):
    """
    Get user's analysis history.
    
    Parameters:
    - limit: Number of results (max 100)
    - analysis_type: Filter by 'single' or 'discovery'
    """
    if not history_db:
        raise HTTPException(503, "Analysis history not available")
    
    if limit > 100:
        limit = 100
    
    try:
        history = await history_db.get_user_history(
            user_id=user.username,
            limit=limit,
            analysis_type=analysis_type
        )
        
        return {
            "history": [
                {
                    "id": record.id,
                    "type": record.analysis_type,
                    "url": record.url,
                    "company_name": record.company_name,
                    "status": record.status,
                    "score": record.score,
                    "competitors_count": record.competitors_count,
                    "created_at": record.created_at.isoformat(),
                    "completed_at": record.completed_at.isoformat() if record.completed_at else None
                }
                for record in history
            ],
            "total": len(history)
        }
        
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        raise HTTPException(500, "Failed to fetch history")

@app.get("/api/v1/analysis-history/{analysis_id}", tags=["History"])
async def get_analysis_details(
    analysis_id: int,
    user: UserInfo = Depends(require_user)
):
    """Get full details of a specific analysis"""
    if not history_db:
        raise HTTPException(503, "Analysis history not available")
    
    try:
        details = await history_db.get_analysis_details(
            analysis_id=analysis_id,
            user_id=user.username
        )
        
        if not details:
            raise HTTPException(404, "Analysis not found")
        
        return details
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching analysis details: {e}")
        raise HTTPException(500, "Failed to fetch analysis details")

@app.get("/api/v1/user-usage", tags=["History"])
async def get_user_usage_stats(
    user: UserInfo = Depends(require_user)
):
    """Get user's usage statistics and limits"""
    if not history_db:
        raise HTTPException(503, "Usage stats not available")
    
    try:
        usage = await history_db.get_user_usage(user.username)
        
        if not usage:
            return {
                "single_analyses_this_month": 0,
                "discoveries_this_month": 0,
                "total_single_analyses": 0,
                "total_discoveries": 0,
                "single_analysis_limit": 100,
                "discovery_limit": 10
            }
        
        return {
            "single_analyses_this_month": usage.single_analyses_this_month,
            "discoveries_this_month": usage.discoveries_this_month,
            "total_single_analyses": usage.total_single_analyses,
            "total_discoveries": usage.total_discoveries,
            "total_competitors_analyzed": usage.total_competitors_analyzed,
            "single_analysis_limit": usage.single_analysis_limit,
            "discovery_limit": usage.discovery_limit,
            "single_analyses_remaining": (
                usage.single_analysis_limit - usage.single_analyses_this_month
                if usage.single_analysis_limit > 0
                else -1  # Unlimited
            ),
            "discoveries_remaining": (
                usage.discovery_limit - usage.discoveries_this_month
                if usage.discovery_limit > 0
                else -1  # Unlimited
            )
        }
        
    except Exception as e:
        logger.error(f"Error fetching usage stats: {e}")
        raise HTTPException(500, "Failed to fetch usage stats")

# ============================================================================
# 6. UPDATE /api/v1/info ENDPOINT TO INCLUDE HISTORY STATUS
# ============================================================================

# In the existing /api/v1/info endpoint, add:
@app.get("/api/v1/info")
async def info():
    return {
        # ... existing fields ...
        "features": {
            # ... existing features ...
            "analysis_history": history_db is not None,
            "history_endpoints": [
                "/api/v1/analysis-history",
                "/api/v1/analysis-history/{id}",
                "/api/v1/user-usage"
            ] if history_db else []
        }
    }
