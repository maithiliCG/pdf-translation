"""
Configuration settings and constants for PDFMathTranslate
"""
import os
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai
from typing import Optional, Tuple

# Load environment variables
load_dotenv()

# Gemini API Configuration
GEMINI_API_KEY = os.getenv("GENAI_API_KEY") or os.getenv("GEMINI_API_KEY")
GEMINI_MODEL_NAME = (
    os.getenv("GENAI_MODEL") or os.getenv("GEMINI_MODEL") or "models/gemini-2.0-flash"
)

# Initialize Gemini (will be configured in app.py)
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL_NAME)
else:
    model = None

# Language mappings
LANGUAGES = {
    "English": "en",
    "Hindi": "hi",
    "Bengali": "bn",
    "Telugu": "te",
    "Marathi": "mr",
    "Tamil": "ta",
    "Gujarati": "gu",
    "Kannada": "kn",
    "Odia": "or",
    "Malayalam": "ml",
    "Punjabi": "pa",
    "Assamese": "as",
    "Urdu": "ur",
}

# Job directories
SOLUTION_JOBS_ROOT = Path("solution_jobs")
SOLUTION_JOBS_ROOT.mkdir(parents=True, exist_ok=True)

PDF2ZH_JOBS_ROOT = Path("pdf2zh_jobs")
PDF2ZH_JOBS_ROOT.mkdir(parents=True, exist_ok=True)

# Language-specific labels for solutions
PIPELINE_LABELS = {
    "telugu": ("సమాధానం", "వివరణ", "తెలుగులో అనువదించిన ప్రశ్నపత్రం"),
    "hindi": ("उत्तर", "व्याख्या", "हिंदी में अनुवादित प्रश्नपत्र"),
    "odia": ("ଉତ୍ତର", "ବ୍ୟାଖ୍ୟା", "ଓଡ଼ିଆରେ ଅନୁବାଦିତ ପ୍ରଶ୍ନପତ୍ର"),
    "tamil": ("பதில்", "விரிவுரை", "தமிழில் மொழிபெயர்த்த கேள்வித்தாள்"),
    "kannada": ("ಉತ್ತರ", "ವಿವರಣೆ", "ಕನ್ನಡದಲ್ಲಿ ಅನುವಾದಿತ ಪ್ರಶ್ನೆ ಪತ್ರಿಕೆ"),
}

# MongoDB Configuration
MONGODB_URI = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "pdf_translation_db")


def get_mongodb_connection() -> Tuple[Optional[object], Optional[object]]:
    """
    Get MongoDB client and database connection.
    
    Returns:
        Tuple of (client, database). Returns (None, None) if MongoDB is not configured.
    """
    if not MONGODB_URI:
        return None, None
    
    try:
        from pymongo import MongoClient
        
        client = MongoClient(MONGODB_URI)
        db = client[MONGODB_DB_NAME]
        
        # Test connection
        client.admin.command('ping')
        
        return client, db
    except Exception as e:
        print(f"MongoDB connection error: {e}")
        return None, None

