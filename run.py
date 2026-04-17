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
    reload = os.getenv("DEBUG", "true").lower() == "true"
    
    print(f"[INFO] Starting server on {host}:{port} (reload={reload})")
    
    # Note: loop="asyncio" is important to prevent uvicorn from overriding our policy
    uvicorn.run(
        "main:app", 
        host=host, 
        port=port, 
        reload=reload, 
        loop="asyncio"
    )
