# AI Study Assistant

A Streamlit application for solving PDF question papers, generating MCQs, and translating PDFs using Google Gemini AI.

## Features

### 1. Solution Generator
- Upload a PDF question paper
- Automatically extracts and solves questions using:
  - Answer keys (if present)
  - SymPy for mathematical equations
  - Google Gemini AI for complex problems
- Translates solutions to multiple Indian languages
- Downloads: Extracted JSON, Solved JSON, Translated JSON, and DOCX

### 2. MCQ Generator
- Generate multiple-choice questions on any topic
- Translate MCQs to multiple languages
- Download as DOCX

### 3. PDF Translator
- Full PDF translation with layout preservation
- Advanced PDF processing with layout preservation
- Outputs monolingual and bilingual PDFs

### 4. MongoDB Integration (Optional)
- Store input files (uploaded PDFs)
- Store translation outputs (monolingual and bilingual PDFs)
- Store solution generation results (DOCX and JSON)
- Store generated MCQs with metadata
- Support for both local MongoDB and MongoDB Atlas (cloud)
- Automatic file storage using GridFS for large files

📖 **See [MONGODB_SETUP.md](MONGODB_SETUP.md) for detailed setup instructions**

## Quick Start

### Prerequisites
- Python 3.10-3.13
- Google Gemini API key ([Get one here](https://makersuite.google.com/app/apikey))

### Local Setup

```bash
# Windows
setup.bat

# Linux/Mac
chmod +x setup.sh && ./setup.sh

# Create .env file
cp env.example .env
# Edit .env and add: GENAI_API_KEY=your_api_key_here

# Run the app
streamlit run app.py
```

Visit: `http://localhost:8501`

## Deployment

**Recommended: Streamlit Cloud** (FREE & Easy)

1. Push code to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect repository
4. Add secret: `GENAI_API_KEY`
5. Deploy!

## Project Structure

```
PDFMathTranslate-next/
├── app.py                    # Main Streamlit application (UI)
├── config/                   # Configuration
│   ├── __init__.py
│   └── settings.py           # API keys, constants, MongoDB config
├── modules/                   # Business logic modules
│   ├── __init__.py
│   ├── common.py             # Shared utilities
│   ├── database_service.py   # MongoDB service layer
│   ├── solution_generator.py  # Solution Generator module
│   ├── mcq_generator.py       # MCQ Generator module
│   └── pdf_translator.py      # PDF Translator module
├── pdf2zh_next/              # PDF translation library
├── requirements.txt           # Python dependencies
├── pyproject.toml             # Package configuration
├── Procfile                  # Heroku configuration
├── env.example               # Environment variables template
├── MONGODB_SETUP.md          # MongoDB setup guide
└── setup.sh & setup.bat      # Setup scripts
```

## Environment Variables

Create a `.env` file:
```env
# Required: Google Gemini API
GENAI_API_KEY=your_gemini_api_key_here

# Optional: MongoDB Configuration (for data persistence)
MONGODB_URI=mongodb://localhost:27017/
MONGODB_DATABASE=pdf_translation_db
```

**Note**: MongoDB is optional. The application works without it, but you won't have data persistence.

## License

AGPL-3.0
