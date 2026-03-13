@echo off
echo Starting FreightScan AI...
echo.

cd /d "%~dp0"

if not exist ".env" (
    echo ERROR: .env file not found.
    echo Please copy .env.example to .env and add your ANTHROPIC_API_KEY.
    pause
    exit /b 1
)

cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
