# Brandista API - Railway Deployment

## Current Configuration

Railway is configured to use the **new modular structure** (`app/main.py`).

### Entry Point
```
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### What This Means

1. **Uses `app/main.py`** - The new refactored modular structure
2. **Imports from legacy `main.py`** - Bridge pattern maintains compatibility
3. **WebSocket support** - `/ws/chat` endpoint available
4. **GPT integration** - Uses existing OpenAI client from main.py

### Files Used in Production

```
app/
├── main.py              ✅ Primary entry point (imports from legacy)
├── config.py            ✅ Configuration
├── dependencies.py      ✅ Auth & rate limiting
└── routers/
    ├── health.py        ✅ Health checks
    └── chat.py          ✅ GPT chat endpoint (HTTP)

main.py                  ✅ Legacy file (still used via imports)
                         ✅ Contains /ws/chat WebSocket endpoint
```

### Deployment Process

When you push to GitHub:
1. Railway detects changes
2. Builds with nixpacks
3. Installs dependencies
4. Starts with `uvicorn app.main:app`
5. All endpoints available (legacy + new)

### Endpoints Available

**New Modular:**
- `GET /health` - Health check
- `POST /api/v1/chat/` - GPT chat (HTTP)

**Legacy (via import):**
- `WS /ws/chat` - GPT chat (WebSocket)
- All existing analysis endpoints
- All agent endpoints
- All other features

### Migration Status

✅ **Phase 1:** Modular structure created  
✅ **Phase 2:** Bridge pattern implemented  
✅ **Phase 3:** WebSocket chat added  
🔄 **Phase 4:** Gradual endpoint migration (ongoing)

### Next Steps

Gradually migrate endpoints from `main.py` to `app/routers/`:
1. Auth endpoints → `app/routers/auth.py`
2. Analysis endpoints → `app/routers/analysis.py`
3. Agent endpoints → `app/routers/agents.py`
4. etc.

Once all endpoints migrated, `main.py` can be deprecated.
