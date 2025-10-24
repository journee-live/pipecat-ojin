#!/bin/bash

echo "========================================"
echo "Ojin Agents Desktop - Setup Script"
echo "========================================"
echo

echo "[1/5] Creating Python virtual environment..."
if [ -d "venv" ]; then
    echo "✓ Virtual environment already exists"
else
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create virtual environment"
        exit 1
    fi
    echo "✓ Virtual environment created"
fi
echo

echo "[2/5] Installing Node.js dependencies..."
npm install
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install Node.js dependencies"
    exit 1
fi
echo "✓ Node.js dependencies installed"
echo

echo "[3/5] Installing Python dependencies..."
source venv/bin/activate
pip install -r dev-requirements.txt
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install Python dependencies"
    echo
    echo "Troubleshooting:"
    echo "- Make sure Python 3.8+ is installed"
    echo "- Try: pip3 instead of pip"
    exit 1
fi
echo "✓ Python dependencies installed"
echo

echo "[4/5] Setting up environment file..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✓ Created .env file from template"
    echo "⚠ IMPORTANT: Edit .env and add your API keys:"
    echo "  - OJIN_API_KEY"
    echo "  - HUME_API_KEY"
else
    echo "✓ .env file already exists"
fi
echo

echo "[5/5] Verifying configuration..."
if [ ! -f config.json ]; then
    echo "⚠ WARNING: config.json not found"
else
    echo "✓ config.json exists"
fi
echo

echo "========================================"
echo "Setup complete!"
echo "========================================"
echo
echo "Next steps:"
echo "1. Activate virtual environment: source venv/bin/activate"
echo "2. Edit .env and add your API keys"
echo "3. Edit config.json and set persona/hume IDs"
echo "4. Run: npm run dev"
echo
echo "NOTE: The virtual environment will be activated automatically when debugging."
echo
