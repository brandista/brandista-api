#!/usr/bin/env python3
"""
Railway startup script - reads PORT from environment
"""
import os
import sys

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    
    # Import uvicorn and run
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
