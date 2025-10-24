@echo off
echo ========================================
echo Ojin Agents Desktop - Setup Script
echo ========================================
echo.

echo [1/5] Creating Python virtual environment...
if exist venv (
    echo ✓ Virtual environment already exists
) else (
    python -m venv venv
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
    echo ✓ Virtual environment created
)
echo.

echo [2/5] Installing Node.js dependencies...
call npm install
if %errorlevel% neq 0 (
    echo ERROR: Failed to install Node.js dependencies
    pause
    exit /b 1
)
echo ✓ Node.js dependencies installed
echo.

echo [3/5] Installing Python dependencies...
call venv\Scripts\activate.bat
pip install -r dev-requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install Python dependencies
    echo.
    echo Troubleshooting:
    echo - Make sure Python is in your PATH
    echo - If PyAudio fails, try: pip install pipwin ^&^& pipwin install pyaudio
    pause
    exit /b 1
)
echo ✓ Python dependencies installed
echo.

echo [4/5] Setting up environment file...
if not exist .env (
    copy .env.example .env
    echo ✓ Created .env file from template
    echo ⚠ IMPORTANT: Edit .env and add your API keys:
    echo   - OJIN_API_KEY
    echo   - HUME_API_KEY
) else (
    echo ✓ .env file already exists
)
echo.

echo [5/5] Verifying configuration...
if not exist config.json (
    echo ⚠ WARNING: config.json not found
) else (
    echo ✓ config.json exists
)
echo.

echo ========================================
echo Setup complete! 
echo ========================================
echo.
echo Next steps:
echo 1. Activate virtual environment: venv\Scripts\activate
echo 2. Edit .env and add your API keys
echo 3. Edit config.json and set persona/hume IDs
echo 4. Run: npm run dev
echo.
echo NOTE: The virtual environment will be activated automatically when debugging.
echo.
pause
