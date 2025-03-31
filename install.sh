#!/bin/bash
set -e

echo "Amazon Invoice Downloader - Installation Script"
echo "-----------------------------------------------"

# Check Python version
python_version=$(python3 --version 2>&1 | cut -d" " -f2)
required_version="3.7"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
  echo "ERROR: Python $required_version or higher is required. You have $python_version"
  exit 1
fi

echo "✅ Python version check passed: $python_version"

# Create virtual environment
if [ ! -d "venv" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv venv
  echo "✅ Virtual environment created"
else
  echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install required packages
echo "Installing required Python packages..."
pip install playwright python-dotenv
echo "✅ Python packages installed"

# Install Playwright browsers
echo "Installing Playwright browsers..."
playwright install
echo "✅ Playwright browsers installed"

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
  echo "Creating .env file from template..."
  cp env-sample .env
  echo "✅ .env file created. Please edit it to add your Amazon email."
else
  echo "✅ .env file already exists"
fi

echo ""
echo "Installation completed successfully!"
echo ""
echo "To use the Amazon Invoice Downloader:"
echo "1. Edit the .env file and set your AMAZON_EMAIL"
echo "2. Activate the virtual environment: source venv/bin/activate"
echo "3. Run the script: python amazon-invoices-downloader.py"
echo ""
echo "Note: The script requires manual password entry and will open a browser window."