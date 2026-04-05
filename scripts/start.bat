@echo off
REM Windows start script for Udemy Course Enroller

echo ========================================
echo  Udemy Course Enroller - Starting...
echo ========================================

REM Change to project root (one level up from scripts/)
cd /d "%~dp0.."

REM Create directories if they don't exist
if not exist "logs" mkdir logs
if not exist "Courses" mkdir Courses

REM Check for Python
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python not found. Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

REM Check Python version
python -c "import sys; assert sys.version_info >= (3,10), 'Python 3.10+ required'" 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python 3.10 or newer is required.
    pause
    exit /b 1
)

REM Create virtual environment if it doesn't exist
if not exist "venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv venv
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Upgrade pip silently
python -m pip install --upgrade pip -q

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt -q
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

REM Copy .env.example to .env if .env doesn't exist
if not exist ".env" (
    echo Creating .env from .env.example...
    copy .env.example .env >nul
    echo [INFO] .env created. Edit it if needed.
)

REM Start the application
echo.
echo ========================================
echo  Server starting at http://localhost:8000
echo  Press Ctrl+C to stop
echo ========================================
echo.

python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
