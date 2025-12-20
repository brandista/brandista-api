#!/bin/bash
# 🚀 Git Repository Initialization Script
# For Growth Engine 2.0 with Unified Memory System

set -e

echo "🧠 ====================================="
echo "   GROWTH ENGINE 2.0 - GIT INIT"
echo "   Unified Memory System"
echo "====================================="
echo ""

# Check if we're in the right directory
if [ ! -f "agent_api.py" ]; then
    echo "❌ Error: agent_api.py not found!"
    echo "Please run this script from brandista-api-main directory"
    exit 1
fi

echo "✅ Found agent_api.py - in correct directory"
echo ""

# Check if git is already initialized
if [ -d ".git" ]; then
    echo "⚠️  Git repository already exists!"
    read -p "Remove and reinitialize? (y/N): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf .git
        echo "✅ Removed old .git directory"
    else
        echo "Keeping existing .git directory"
        exit 0
    fi
fi

echo "🔧 Initializing Git repository..."
git init
echo "✅ Git initialized"
echo ""

echo "📝 Adding all files..."
git add .
echo "✅ Files staged"
echo ""

echo "💾 Creating initial commit..."
git commit -m "🧠 Growth Engine 2.0 - Unified Memory System

✅ All 6 agents enhanced with memory
✅ Scout: Tracks Radar competitors, industry history
✅ Analyst: Score trends, +/- comparisons
✅ Guardian: Recurring threat detection, RASM trends
✅ Prospector: Opportunity tracking, duplicate prevention
✅ Strategist: 3-5 analysis trends, pattern recognition
✅ Planner: Action deduplication, progress tracking
✅ BaseAgent: get_unified_context_data() helper method

FEATURES:
- Real-time WebSocket insights
- PostgreSQL unified context
- JWT authentication
- Multi-language support (FI/EN)
- Company intelligence integration
- Revenue impact modeling

STATUS: Production ready for €600K MRR
"

echo "✅ Initial commit created"
echo ""

echo "🎯 Next steps:"
echo ""
echo "1️⃣  Add your remote repository:"
echo "    git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPO.git"
echo ""
echo "2️⃣  Push to GitHub/Railway:"
echo "    git push origin main --force"
echo ""
echo "    OR for Railway:"
echo "    git push origin main"
echo ""
echo "3️⃣  Railway will auto-deploy! 🚀"
echo ""
echo "✅ Git repository ready!"
