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
    Get MongoDB client and database connection with proper SSL/TLS configuration.
    
    Returns:
        Tuple of (client, database). Returns (None, None) if MongoDB is not configured.
    """
    if not MONGODB_URI:
        return None, None
    
    # Check if this is a MongoDB Atlas connection
    is_atlas = 'mongodb.net' in MONGODB_URI or 'mongodb+srv' in MONGODB_URI
    
    try:
        from pymongo import MongoClient
        
        if is_atlas:
            # MongoDB Atlas requires TLS/SSL
            # Use mongodb+srv:// format which automatically handles TLS
            if 'mongodb+srv://' in MONGODB_URI:
                # mongodb+srv automatically uses TLS - best option for Atlas
                client = MongoClient(
                    MONGODB_URI,
                    serverSelectionTimeoutMS=30000,
                    connectTimeoutMS=30000,
                    socketTimeoutMS=30000,
                    retryWrites=True
                )
            elif 'mongodb://' in MONGODB_URI:
                # Standard connection - ensure TLS is enabled
                # Add tls=true if not present
                if 'tls=true' not in MONGODB_URI and 'ssl=true' not in MONGODB_URI:
                    separator = '&' if '?' in MONGODB_URI else '?'
                    uri_with_tls = f"{MONGODB_URI}{separator}tls=true&retryWrites=true&w=majority"
                else:
                    uri_with_tls = MONGODB_URI
                
                client = MongoClient(
                    uri_with_tls,
                    serverSelectionTimeoutMS=30000,
                    connectTimeoutMS=30000,
                    socketTimeoutMS=30000,
                    tls=True,
                    tlsAllowInvalidCertificates=False
                )
            else:
                # Fallback
                client = MongoClient(
                    MONGODB_URI,
                    serverSelectionTimeoutMS=30000,
                    connectTimeoutMS=30000,
                    socketTimeoutMS=30000
                )
        else:
            # Local MongoDB connection (no SSL needed)
            client = MongoClient(
                MONGODB_URI,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000
            )
        
        db = client[MONGODB_DB_NAME]
        
        # Test connection with a simple ping
        client.admin.command('ping')
        
        return client, db
    except Exception as e:
        print(f"MongoDB connection error: {e}")
        # Try alternative connection method with relaxed SSL for troubleshooting
        if is_atlas:
            try:
                from pymongo import MongoClient
                print("Attempting MongoDB connection with alternative SSL settings...")
                # Try with tlsAllowInvalidCertificates=True for troubleshooting
                # (Note: This is less secure, but helps diagnose SSL issues)
                if 'mongodb+srv://' in MONGODB_URI:
                    client = MongoClient(
                        MONGODB_URI,
                        serverSelectionTimeoutMS=30000,
                        connectTimeoutMS=30000,
                        socketTimeoutMS=30000,
                        retryWrites=True
                    )
                else:
                    client = MongoClient(
                        MONGODB_URI,
                        tls=True,
                        tlsAllowInvalidCertificates=True,  # For troubleshooting only
                        serverSelectionTimeoutMS=30000,
                        connectTimeoutMS=30000,
                        socketTimeoutMS=30000
                    )
                db = client[MONGODB_DB_NAME]
                client.admin.command('ping')
                print("✓ MongoDB connection successful with alternative method")
                return client, db
            except Exception as e2:
                print(f"✗ MongoDB alternative connection also failed: {e2}")
                print("\nTroubleshooting tips:")
                print("1. Ensure your MongoDB Atlas connection string uses 'mongodb+srv://' format")
                print("2. Check that your IP address is whitelisted in MongoDB Atlas")
                print("3. Verify your username and password are correct")
                print("4. Check MongoDB Atlas cluster status")
        return None, None

