"""
Configuration settings and constants for PDFMathTranslate
"""
import os
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

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
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "pdf_translation_db")

# MongoDB Client initialization
mongodb_client = None
mongodb_db = None

def get_mongodb_connection():
    """Get MongoDB connection and database instance"""
    global mongodb_client, mongodb_db
    
    if mongodb_client is None:
        try:
            mongodb_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
            # Test connection
            mongodb_client.admin.command('ping')
            mongodb_db = mongodb_client[MONGODB_DATABASE]
            print(f"[OK] MongoDB connected successfully to database: {MONGODB_DATABASE}")
        except ConnectionFailure as e:
            print(f"[WARNING] MongoDB connection failed: {e}")
            print("[INFO] Application will continue without MongoDB storage.")
            mongodb_client = None
            mongodb_db = None
        except Exception as e:
            print(f"[WARNING] MongoDB error: {e}")
            mongodb_client = None
            mongodb_db = None
    
    return mongodb_client, mongodb_db

