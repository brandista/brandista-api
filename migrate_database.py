#!/usr/bin/env python3
"""
Database Migration Script for Analysis History
Run this once to set up the database schema
"""

import asyncio
import asyncpg
import os
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_migration():
    """Run database migration"""
    
    # Get database URL
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("❌ DATABASE_URL environment variable not set")
        sys.exit(1)
    
    logger.info(f"🔗 Connecting to database...")
    
    try:
        # Connect to database
        conn = await asyncpg.connect(database_url)
        
        logger.info("✅ Connected to database")
        
        # Read schema file
        schema_path = os.path.join(os.path.dirname(__file__), 'analysis_history_schema.sql')
        
        if not os.path.exists(schema_path):
            logger.error(f"❌ Schema file not found: {schema_path}")
            sys.exit(1)
        
        with open(schema_path, 'r') as f:
            schema_sql = f.read()
        
        logger.info("📄 Schema file loaded")
        
        # Run migration
        logger.info("🚀 Running migration...")
        
        await conn.execute(schema_sql)
        
        logger.info("✅ Migration completed successfully!")
        
        # Verify tables were created
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        
        logger.info("📊 Created tables:")
        for table in tables:
            logger.info(f"  - {table['table_name']}")
        
        # Close connection
        await conn.close()
        
        logger.info("✅ Migration complete! Analysis history is ready to use.")
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_migration())
