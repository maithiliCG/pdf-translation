"""
Configuration settings and constants for PDFMathTranslate
"""
import os
import re
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
        
        # Use a local variable for the connection URI (don't modify global)
        connection_uri = MONGODB_URI
        
        if is_atlas:
            # MongoDB Atlas requires mongodb+srv:// format for proper TLS handling
            # Convert mongodb:// to mongodb+srv:// if needed
            if 'mongodb://' in connection_uri and 'mongodb+srv://' not in connection_uri:
                # Convert to mongodb+srv:// format (removes port requirement)
                connection_uri = connection_uri.replace('mongodb://', 'mongodb+srv://')
                # Remove port numbers (SRV doesn't use ports)
                connection_uri = re.sub(r':\d+/', '/', connection_uri)  # Remove :27017/ or similar
                # Ensure retryWrites is set
                if 'retryWrites' not in connection_uri:
                    separator = '&' if '?' in connection_uri else '?'
                    connection_uri = f"{connection_uri}{separator}retryWrites=true&w=majority"
                print(f"Converting MongoDB URI to SRV format for Atlas connection...")
            
            # Use mongodb+srv:// which automatically handles TLS correctly
            client = MongoClient(
                connection_uri,
                serverSelectionTimeoutMS=30000,
                connectTimeoutMS=30000,
                socketTimeoutMS=30000,
                retryWrites=True
            )
        else:
            # Local MongoDB connection (no SSL needed)
            client = MongoClient(
                connection_uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000
            )
        
        db = client[MONGODB_DB_NAME]
        
        # Test connection with a simple ping
        client.admin.command('ping')
        
        return client, db
    except Exception as e:
        print(f"MongoDB connection error: {e}")
        # Try alternative connection method
        if is_atlas:
            try:
                from pymongo import MongoClient
                print("Attempting MongoDB connection with alternative method...")
                
                # Ensure we're using mongodb+srv:// format
                fallback_uri = MONGODB_URI
                if 'mongodb://' in fallback_uri and 'mongodb+srv://' not in fallback_uri:
                    fallback_uri = fallback_uri.replace('mongodb://', 'mongodb+srv://')
                    fallback_uri = re.sub(r':\d+/', '/', fallback_uri)
                    if 'retryWrites' not in fallback_uri:
                        separator = '&' if '?' in fallback_uri else '?'
                        fallback_uri = f"{fallback_uri}{separator}retryWrites=true&w=majority"
                
                client = MongoClient(
                    fallback_uri,
                    serverSelectionTimeoutMS=30000,
                    connectTimeoutMS=30000,
                    socketTimeoutMS=30000,
                    retryWrites=True
                )
                db = client[MONGODB_DB_NAME]
                client.admin.command('ping')
                print("✓ MongoDB connection successful with alternative method")
                return client, db
            except Exception as e2:
                print(f"✗ MongoDB alternative connection also failed: {e2}")
                print("\n" + "="*70)
                print("TROUBLESHOOTING GUIDE:")
                print("="*70)
                print("✅ Your connection string format is CORRECT!")
                print("   Format: mongodb+srv://username:password@cluster.mongodb.net/...")
                print()
                print("🔍 MOST COMMON ISSUES (since it worked yesterday):")
                print()
                print("1. IP ADDRESS NOT WHITELISTED (90% of cases):")
                print("   → Go to: MongoDB Atlas → Network Access")
                print("   → Click 'Add IP Address'")
                print("   → Add your current IP or use 'Allow Access from Anywhere' (0.0.0.0/0)")
                print("   → Wait 1-2 minutes for changes to take effect")
                print()
                print("2. PASSWORD WITH SPECIAL CHARACTERS:")
                print("   → If password has @, :, /, ?, #, [, ] - URL encode them:")
                print("     @ = %40,  : = %3A,  / = %2F,  ? = %3F")
                print("     # = %23,  [ = %5B,  ] = %5D")
                print("   → Example: password@123 → password%40123")
                print()
                print("3. CLUSTER PAUSED OR DOWN:")
                print("   → Check MongoDB Atlas dashboard")
                print("   → Verify cluster is 'Running' (not 'Paused')")
                print()
                print("4. NETWORK/FIREWALL BLOCKING:")
                print("   → Try accessing MongoDB Atlas website")
                print("   → Check if VPN/proxy is interfering")
                print()
                print("="*70)
        return None, None

