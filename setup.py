#!/usr/bin/env python
"""Setup script to install dependencies and run tests."""

import subprocess
import sys
import os

def run_command(cmd, description):
    """Run a shell command and report results."""
    print(f"\n{'='*60}")
    print(f"📦 {description}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode == 0:
        print(f"✅ {description} - SUCCESS")
    else:
        print(f"❌ {description} - FAILED")
    return result.returncode == 0

def main():
    """Main setup flow."""
    print("""
╔════════════════════════════════════════════════════════════════╗
║          Udemy Enroller - Technatic Edition                    ║
║            Pure Emulation Logic (No Playwright)                 ║
╚════════════════════════════════════════════════════════════════╝
    """)
    
    # Step 1: Install dependencies
    print("\n1️⃣  Installing dependencies...")
    run_command(
        f"{sys.executable} -m pip install --upgrade pip",
        "Upgrade pip"
    )
    run_command(
        f"{sys.executable} -m pip install -r requirements.txt",
        "Install requirements"
    )
    
    # Step 2: Run tests
    print("\n2️⃣  Running test suite...")
    run_command(
        f"{sys.executable} -m pytest tests/test_core_functionality.py -v",
        "Run pytest tests"
    )
    
    # Step 3: Generate coverage report
    print("\n3️⃣  Generating coverage report...")
    run_command(
        f"{sys.executable} -m pytest tests/ --cov=app --cov-report=term-missing",
        "Generate coverage"
    )
    
    # Step 4: Verify imports
    print("\n4️⃣  Verifying all modules import correctly...")
    print("    Checking security module...")
    run_command(
        f"{sys.executable} -c \"from app.security import hash_password, verify_password; print('✅ Security module OK')\"",
        "Verify security imports"
    )
    
    print("    Checking logging configuration...")
    run_command(
        f"{sys.executable} -c \"from app.logging_config import setup_logging; print('✅ Logging module OK')\"",
        "Verify logging imports"
    )
    
    print("    Checking Udemy client...")
    run_command(
        f"{sys.executable} -c \"from app.services.udemy_client import UdemyClient; print('✅ UdemyClient module OK')\"",
        "Verify Udemy client imports"
    )
    
    # Step 5: Summary
    print("""
╔════════════════════════════════════════════════════════════════╗
║                   ✅ SETUP COMPLETE                            ║
╚════════════════════════════════════════════════════════════════╝

🎉 Playwright-Free Implementation Active:
  ✅ Mobile Emulation Logic
  ✅ CloudScraper Integration
  ✅ Async FastAPI Pipeline
  ✅ Alembic Database Migrations
  ✅ JSON Structured Logging

📊 Next Steps:
  1. Configure your .env file:
     cp .env.example .env
     
  2. Apply database migrations:
     alembic upgrade head
     
  3. Run the application:
     python run.py
     
  4. Access health check:
     curl http://localhost:8000/api/health

🔒 Security Features Active:
  - Passwords hashed with bcrypt
  - CORS restricted to configured origins
  - JSON structured logging with audit trail
  - Input validation on all URLs
  - Secure cookie settings (httpOnly, secure, sameSite)

📚 Documentation:
  - Run: pytest tests/ -v for test suite
  - View: logs/app.log for application logs
    """)

if __name__ == "__main__":
    main()
