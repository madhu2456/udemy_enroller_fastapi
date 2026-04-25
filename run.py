"""Application runner - ensures correct event loop on Windows before starting Uvicorn."""

import os
import sys
import asyncio

def setup_event_loop():
    """Set the ProactorEventLoopPolicy on Windows for subprocess support."""
    if sys.platform == "win32":
        try:
            from asyncio import WindowsProactorEventLoopPolicy
            asyncio.set_event_loop_policy(WindowsProactorEventLoopPolicy())
            print("[INFO] Windows ProactorEventLoopPolicy set.")
        except ImportError:
            print("[WARN] Could not set WindowsProactorEventLoopPolicy.")

if __name__ == "__main__":
    # 1. Setup the loop policy BEFORE anything else
    setup_event_loop()
    
    # 2. Import uvicorn and run
    import uvicorn
    
    # Get port from env or default
    port = int(os.getenv("PORT", 8005))
    host = os.getenv("HOST", "0.0.0.0")
    
    # CRITICAL: On Windows with Python 3.8+, Uvicorn's reload mechanism often 
    # forces the SelectorEventLoop in child processes.
    # To fix this, we DISABLE reload by default on Windows.
    reload_env = os.getenv("DEBUG", "true").lower() == "true"
    reload = reload_env if sys.platform != "win32" else False
    
    if sys.platform == "win32" and reload_env:
        print("[INFO] Windows detected: Disabling auto-reload to ensure ProactorEventLoop is used.")
    
    print(f"[INFO] Starting server on {host}:{port} (reload={reload})")
    
    # Respect LOG_LEVEL from settings
    from config.settings import get_settings
    app_log_level = get_settings().LOG_LEVEL.lower()
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        loop="asyncio", # Use the policy we set
        ws="none",      # Optimization
        log_level=app_log_level
    )
