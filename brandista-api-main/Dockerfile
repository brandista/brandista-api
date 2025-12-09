# ============================================================================
# BRANDISTA COMPETITIVE INTELLIGENCE API - DOCKERFILE
# Production-ready with Python 3.11 + Playwright
# ============================================================================

FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Install Playwright browsers (if not already in base image)
RUN playwright install chromium --with-deps || echo "Chromium already installed"

# Use existing pwuser from Playwright image (UID 1000)
RUN chown -R 1000:1000 /app
USER 1000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=5)" || exit 1

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
