#!/bin/bash
# Setup script for AI Study Assistant

echo "🚀 Setting up AI Study Assistant..."

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $python_version"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Install pdf2zh_next package
echo "📚 Installing pdf2zh_next package..."
pip install -e .

# Setup environment file
if [ ! -f ".env" ]; then
    echo "⚙️  Creating .env file from template..."
    cp env.example .env
    echo "⚠️  Please edit .env and add your GENAI_API_KEY"
else
    echo "✅ .env file already exists"
fi

# Create runtime directories
echo "📁 Creating runtime directories..."
mkdir -p solution_jobs pdf2zh_jobs pdf2zh_files

echo "✅ Setup complete!"
echo ""
echo "To run the application:"
echo "  source venv/bin/activate"
echo "  streamlit run app.py"

