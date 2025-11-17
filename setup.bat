@echo off
REM Setup script for AI Study Assistant (Windows)

echo 🚀 Setting up AI Study Assistant...

REM Check Python
python --version
if errorlevel 1 (
    echo ❌ Python not found! Please install Python 3.10 or higher.
    exit /b 1
)

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo 📦 Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo 🔌 Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo 📥 Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt

REM Install pdf2zh_next package
echo 📚 Installing pdf2zh_next package...
pip install -e .

REM Setup environment file
if not exist ".env" (
    echo ⚙️  Creating .env file from template...
    copy env.example .env
    echo ⚠️  Please edit .env and add your GENAI_API_KEY
) else (
    echo ✅ .env file already exists
)

REM Create runtime directories
echo 📁 Creating runtime directories...
if not exist "solution_jobs" mkdir solution_jobs
if not exist "pdf2zh_jobs" mkdir pdf2zh_jobs
if not exist "pdf2zh_files" mkdir pdf2zh_files

echo ✅ Setup complete!
echo.
echo To run the application:
echo   venv\Scripts\activate
echo   streamlit run app.py

pause

