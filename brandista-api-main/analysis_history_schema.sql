-- ============================================================================
-- BRANDISTA ANALYSIS HISTORY DATABASE SCHEMA
-- Production-ready schema for storing both single analyses and discoveries
-- ============================================================================

-- Main analyses table - stores metadata for all analysis requests
CREATE TABLE IF NOT EXISTS analyses (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    analysis_type VARCHAR(50) NOT NULL, -- 'single' or 'discovery'
    url VARCHAR(500) NOT NULL,
    company_name VARCHAR(255),
    industry VARCHAR(255),
    country_code VARCHAR(10),
    language VARCHAR(10) DEFAULT 'en',
    
    -- Status tracking
    status VARCHAR(50) NOT NULL DEFAULT 'completed', -- 'pending', 'processing', 'completed', 'failed'
    progress INTEGER DEFAULT 100,
    error_message TEXT,
    
    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    duration_seconds INTEGER,
    
    -- Indexing for fast queries
    CONSTRAINT analyses_user_id_idx_check CHECK (user_id IS NOT NULL)
);

-- Single analysis results - stores detailed results for individual website analyses
CREATE TABLE IF NOT EXISTS analysis_results (
    id SERIAL PRIMARY KEY,
    analysis_id INTEGER NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    url VARCHAR(500) NOT NULL,
    
    -- Scores
    digital_maturity_score INTEGER,
    
    -- Score breakdown
    security_score INTEGER,
    seo_score INTEGER,
    content_score INTEGER,
    technical_score INTEGER,
    mobile_score INTEGER,
    social_score INTEGER,
    performance_score INTEGER,
    
    -- Full analysis data (JSONB for flexible querying)
    basic_analysis JSONB,
    technical_audit JSONB,
    content_analysis JSONB,
    seo_analysis JSONB,
    social_analysis JSONB,
    ux_analysis JSONB,
    competitive_analysis JSONB,
    
    -- AI Analysis (if available)
    ai_analysis JSONB,
    smart_actions JSONB,
    
    -- Metadata
    framework_detected VARCHAR(100),
    has_spa BOOLEAN DEFAULT FALSE,
    used_playwright BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Competitor discoveries - stores metadata for discovery tasks
CREATE TABLE IF NOT EXISTS competitor_discoveries (
    id SERIAL PRIMARY KEY,
    analysis_id INTEGER NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    
    -- Discovery parameters
    max_competitors INTEGER,
    competitors_found INTEGER DEFAULT 0,
    competitors_analyzed INTEGER DEFAULT 0,
    
    -- Search metadata
    search_terms JSONB, -- Array of search terms used
    search_provider VARCHAR(50), -- 'google', 'brave', etc.
    
    -- Summary data
    summary JSONB, -- Overview of all competitors
    
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Individual competitor results from discovery
CREATE TABLE IF NOT EXISTS competitor_results (
    id SERIAL PRIMARY KEY,
    discovery_id INTEGER NOT NULL REFERENCES competitor_discoveries(id) ON DELETE CASCADE,
    
    domain VARCHAR(255) NOT NULL,
    url VARCHAR(500) NOT NULL,
    company_name VARCHAR(255),
    
    -- Scores
    digital_maturity_score INTEGER,
    
    -- Score breakdown
    security_score INTEGER,
    seo_score INTEGER,
    content_score INTEGER,
    technical_score INTEGER,
    mobile_score INTEGER,
    social_score INTEGER,
    performance_score INTEGER,
    
    -- Full analysis data
    basic_analysis JSONB,
    technical_audit JSONB,
    content_analysis JSONB,
    detailed_analysis JSONB,
    
    -- Comparison flags
    is_user_stronger BOOLEAN,
    score_difference INTEGER, -- compared to user's site
    
    -- Metadata
    rank_in_results INTEGER, -- Position in discovery results
    analyzed_at TIMESTAMP,
    
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- User analysis quotas and usage tracking
CREATE TABLE IF NOT EXISTS user_analysis_usage (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL UNIQUE,
    
    -- Current month usage
    single_analyses_this_month INTEGER DEFAULT 0,
    discoveries_this_month INTEGER DEFAULT 0,
    
    -- Total lifetime usage
    total_single_analyses INTEGER DEFAULT 0,
    total_discoveries INTEGER DEFAULT 0,
    total_competitors_analyzed INTEGER DEFAULT 0,
    
    -- Limits
    single_analysis_limit INTEGER DEFAULT 100, -- -1 for unlimited
    discovery_limit INTEGER DEFAULT 10, -- -1 for unlimited
    
    -- Reset tracking
    last_reset_date DATE DEFAULT CURRENT_DATE,
    
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- Fast user lookups
CREATE INDEX IF NOT EXISTS idx_analyses_user_id ON analyses(user_id);
CREATE INDEX IF NOT EXISTS idx_analyses_user_created ON analyses(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_usage_user_id ON user_analysis_usage(user_id);

-- Fast URL lookups (for checking duplicates)
CREATE INDEX IF NOT EXISTS idx_analyses_url ON analyses(url);
CREATE INDEX IF NOT EXISTS idx_analysis_results_url ON analysis_results(url);

-- Fast status queries
CREATE INDEX IF NOT EXISTS idx_analyses_status ON analyses(status);
CREATE INDEX IF NOT EXISTS idx_analyses_type ON analyses(analysis_type);

-- Fast discovery lookups
CREATE INDEX IF NOT EXISTS idx_discoveries_analysis ON competitor_discoveries(analysis_id);
CREATE INDEX IF NOT EXISTS idx_competitor_results_discovery ON competitor_results(discovery_id);

-- JSONB indexes for common queries
CREATE INDEX IF NOT EXISTS idx_analysis_results_score ON analysis_results((basic_analysis->>'digital_maturity_score'));
CREATE INDEX IF NOT EXISTS idx_competitor_results_score ON competitor_results((basic_analysis->>'digital_maturity_score'));

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Function to check if user is within limits
CREATE OR REPLACE FUNCTION check_user_analysis_limit(
    p_user_id VARCHAR(255),
    p_analysis_type VARCHAR(50)
) RETURNS BOOLEAN AS $$
DECLARE
    v_usage RECORD;
    v_limit INTEGER;
    v_current INTEGER;
BEGIN
    -- Get user usage
    SELECT * INTO v_usage FROM user_analysis_usage WHERE user_id = p_user_id;
    
    -- If no usage record, create one
    IF NOT FOUND THEN
        INSERT INTO user_analysis_usage (user_id) VALUES (p_user_id);
        RETURN TRUE;
    END IF;
    
    -- Check if reset needed (new month)
    IF v_usage.last_reset_date < DATE_TRUNC('month', CURRENT_DATE) THEN
        UPDATE user_analysis_usage
        SET single_analyses_this_month = 0,
            discoveries_this_month = 0,
            last_reset_date = CURRENT_DATE
        WHERE user_id = p_user_id;
        RETURN TRUE;
    END IF;
    
    -- Check limits based on analysis type
    IF p_analysis_type = 'single' THEN
        v_limit := v_usage.single_analysis_limit;
        v_current := v_usage.single_analyses_this_month;
    ELSIF p_analysis_type = 'discovery' THEN
        v_limit := v_usage.discovery_limit;
        v_current := v_usage.discoveries_this_month;
    ELSE
        RETURN FALSE;
    END IF;
    
    -- -1 means unlimited
    IF v_limit = -1 THEN
        RETURN TRUE;
    END IF;
    
    -- Check if within limit
    RETURN v_current < v_limit;
END;
$$ LANGUAGE plpgsql;

-- Function to increment usage counter
CREATE OR REPLACE FUNCTION increment_user_usage(
    p_user_id VARCHAR(255),
    p_analysis_type VARCHAR(50),
    p_competitors_count INTEGER DEFAULT 0
) RETURNS VOID AS $$
BEGIN
    -- Insert or update usage
    INSERT INTO user_analysis_usage (
        user_id,
        single_analyses_this_month,
        discoveries_this_month,
        total_single_analyses,
        total_discoveries,
        total_competitors_analyzed
    ) VALUES (
        p_user_id,
        CASE WHEN p_analysis_type = 'single' THEN 1 ELSE 0 END,
        CASE WHEN p_analysis_type = 'discovery' THEN 1 ELSE 0 END,
        CASE WHEN p_analysis_type = 'single' THEN 1 ELSE 0 END,
        CASE WHEN p_analysis_type = 'discovery' THEN 1 ELSE 0 END,
        p_competitors_count
    )
    ON CONFLICT (user_id) DO UPDATE SET
        single_analyses_this_month = user_analysis_usage.single_analyses_this_month + 
            CASE WHEN p_analysis_type = 'single' THEN 1 ELSE 0 END,
        discoveries_this_month = user_analysis_usage.discoveries_this_month + 
            CASE WHEN p_analysis_type = 'discovery' THEN 1 ELSE 0 END,
        total_single_analyses = user_analysis_usage.total_single_analyses + 
            CASE WHEN p_analysis_type = 'single' THEN 1 ELSE 0 END,
        total_discoveries = user_analysis_usage.total_discoveries + 
            CASE WHEN p_analysis_type = 'discovery' THEN 1 ELSE 0 END,
        total_competitors_analyzed = user_analysis_usage.total_competitors_analyzed + p_competitors_count,
        updated_at = NOW();
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- VIEWS FOR COMMON QUERIES
-- ============================================================================

-- Recent analyses view
CREATE OR REPLACE VIEW recent_analyses AS
SELECT 
    a.id,
    a.user_id,
    a.analysis_type,
    a.url,
    a.company_name,
    a.status,
    a.created_at,
    a.completed_at,
    CASE 
        WHEN a.analysis_type = 'single' THEN ar.digital_maturity_score
        WHEN a.analysis_type = 'discovery' THEN (
            SELECT AVG(digital_maturity_score)::INTEGER 
            FROM competitor_results cr
            JOIN competitor_discoveries cd ON cd.id = cr.discovery_id
            WHERE cd.analysis_id = a.id
        )
    END as score,
    CASE
        WHEN a.analysis_type = 'discovery' THEN cd.competitors_found
        ELSE NULL
    END as competitors_count
FROM analyses a
LEFT JOIN analysis_results ar ON ar.analysis_id = a.id
LEFT JOIN competitor_discoveries cd ON cd.analysis_id = a.id
ORDER BY a.created_at DESC;

-- User statistics view
CREATE OR REPLACE VIEW user_analysis_stats AS
SELECT 
    u.user_id,
    u.single_analyses_this_month,
    u.discoveries_this_month,
    u.total_single_analyses,
    u.total_discoveries,
    u.total_competitors_analyzed,
    COUNT(DISTINCT a.id) as total_analyses,
    AVG(ar.digital_maturity_score)::INTEGER as avg_score,
    MAX(a.created_at) as last_analysis_date
FROM user_analysis_usage u
LEFT JOIN analyses a ON a.user_id = u.user_id AND a.status = 'completed'
LEFT JOIN analysis_results ar ON ar.analysis_id = a.id
GROUP BY u.user_id, u.single_analyses_this_month, u.discoveries_this_month,
         u.total_single_analyses, u.total_discoveries, u.total_competitors_analyzed;

-- ============================================================================
-- SAMPLE QUERIES
-- ============================================================================

-- Get user's analysis history with scores
-- SELECT * FROM recent_analyses WHERE user_id = 'user@example.com' LIMIT 20;

-- Get specific analysis with all details
-- SELECT a.*, ar.*, cd.* 
-- FROM analyses a
-- LEFT JOIN analysis_results ar ON ar.analysis_id = a.id
-- LEFT JOIN competitor_discoveries cd ON cd.analysis_id = a.id
-- WHERE a.id = 123;

-- Get all competitors from a discovery
-- SELECT cr.* 
-- FROM competitor_results cr
-- JOIN competitor_discoveries cd ON cd.id = cr.discovery_id
-- JOIN analyses a ON a.id = cd.analysis_id
-- WHERE a.id = 123
-- ORDER BY cr.digital_maturity_score DESC;

-- Check if user can perform analysis
-- SELECT check_user_analysis_limit('user@example.com', 'single');

-- Get user statistics
-- SELECT * FROM user_analysis_stats WHERE user_id = 'user@example.com';
