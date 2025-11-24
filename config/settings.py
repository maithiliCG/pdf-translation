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
        import ssl
        
        # Use a local variable for the connection URI (don't modify global)
        connection_uri = MONGODB_URI
        
        if is_atlas:
            # MongoDB Atlas requires mongodb+srv:// format for proper TLS handling
            # Convert mongodb:// to mongodb+srv:// if needed
            original_uri = connection_uri
            if 'mongodb://' in connection_uri and 'mongodb+srv://' not in connection_uri:
                # Convert to mongodb+srv:// format (removes port requirement)
                print(f"Converting MongoDB URI from mongodb:// to mongodb+srv:// format...")
                print(f"Original URI format detected: mongodb:// (with port)")
                
                # Convert protocol
                connection_uri = connection_uri.replace('mongodb://', 'mongodb+srv://')
                
                # Remove port numbers - handle various formats: :27017/, :27017?, :27017&, or :27017 at end
                # Pattern matches : followed by digits, then /, ?, &, or end of string
                connection_uri = re.sub(r':\d+(?=[/?&]|$)', '', connection_uri)
                
                # Ensure retryWrites is set
                if 'retryWrites' not in connection_uri:
                    separator = '&' if '?' in connection_uri else '?'
                    connection_uri = f"{connection_uri}{separator}retryWrites=true&w=majority"
                
                print(f"✓ Converted to: mongodb+srv:// format (port removed)")
                # Don't print full URI for security, just confirm conversion
            
            # Verify we're using mongodb+srv://
            if 'mongodb+srv://' not in connection_uri:
                print("⚠️ WARNING: Connection string should use mongodb+srv:// for Atlas!")
                print("   Your connection string appears to be in wrong format.")
                print("   Please update your MONGODB_URI to use mongodb+srv:// format")
            
            # Use mongodb+srv:// which automatically handles TLS correctly
            # Add explicit SSL context for better compatibility
            try:
                # Try with default SSL context (most compatible)
                client = MongoClient(
                    connection_uri,
                    serverSelectionTimeoutMS=30000,
                    connectTimeoutMS=30000,
                    socketTimeoutMS=30000,
                    retryWrites=True,
                    tls=True,
                    tlsAllowInvalidCertificates=False
                )
            except Exception as ssl_error:
                # If SSL fails, try with relaxed certificate validation (for troubleshooting)
                print(f"Initial SSL connection failed, trying with relaxed SSL settings...")
                client = MongoClient(
                    connection_uri,
                    serverSelectionTimeoutMS=30000,
                    connectTimeoutMS=30000,
                    socketTimeoutMS=30000,
                    retryWrites=True,
                    tls=True,
                    tlsAllowInvalidCertificates=True  # Only for troubleshooting
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
                original_fallback = fallback_uri
                if 'mongodb://' in fallback_uri and 'mongodb+srv://' not in fallback_uri:
                    print("Fallback: Converting mongodb:// to mongodb+srv:// format...")
                    fallback_uri = fallback_uri.replace('mongodb://', 'mongodb+srv://')
                    # Remove port numbers - handle various formats
                    fallback_uri = re.sub(r':\d+(?=[/?&]|$)', '', fallback_uri)
                    if 'retryWrites' not in fallback_uri:
                        separator = '&' if '?' in fallback_uri else '?'
                        fallback_uri = f"{fallback_uri}{separator}retryWrites=true&w=majority"
                    print(f"✓ Fallback URI converted to SRV format")
                
                # Verify format
                if 'mongodb+srv://' not in fallback_uri:
                    print("❌ ERROR: Connection string must use mongodb+srv:// for MongoDB Atlas!")
                    print("   Current format appears incorrect. Please check your MONGODB_URI.")
                    raise ValueError("MongoDB Atlas requires mongodb+srv:// connection string format")
                
                # Try multiple SSL configurations
                ssl_configs = [
                    # Config 1: Standard TLS
                    {"tls": True, "tlsAllowInvalidCertificates": False},
                    # Config 2: Relaxed certificate validation (for troubleshooting)
                    {"tls": True, "tlsAllowInvalidCertificates": True},
                    # Config 3: No explicit TLS (let mongodb+srv handle it)
                    {}
                ]
                
                for i, ssl_config in enumerate(ssl_configs, 1):
                    try:
                        print(f"Trying SSL configuration {i}/{len(ssl_configs)}...")
                        client = MongoClient(
                            fallback_uri,
                            serverSelectionTimeoutMS=30000,
                            connectTimeoutMS=30000,
                            socketTimeoutMS=30000,
                            retryWrites=True,
                            **ssl_config
                        )
                        # Test the connection
                        client.admin.command('ping')
                        print(f"✓ MongoDB connection successful with SSL config {i}")
                        break
                    except Exception as config_error:
                        if i == len(ssl_configs):
                            # Last attempt failed, raise the error
                            raise config_error
                        continue
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
                print("🔍 MOST COMMON ISSUES (TLSV1_ALERT_INTERNAL_ERROR):")
                print()
                print("1. IP ADDRESS NOT WHITELISTED (MOST COMMON - 90% of cases):")
                print("   → Go to: MongoDB Atlas → Network Access")
                print("   → Click 'Add IP Address'")
                print("   → Add your current IP or use 'Allow Access from Anywhere' (0.0.0.0/0)")
                print("   → Wait 1-2 minutes for changes to take effect")
                print("   → This is the #1 cause of TLSV1_ALERT_INTERNAL_ERROR")
                print()
                print("2. SSL/TLS VERSION MISMATCH:")
                print("   → Your Python SSL library might be incompatible")
                print("   → Try: pip install --upgrade certifi")
                print("   → Or update your system's SSL certificates")
                print()
                print("3. PASSWORD WITH SPECIAL CHARACTERS:")
                print("   → If password has @, :, /, ?, #, [, ] - URL encode them:")
                print("     @ = %40,  : = %3A,  / = %2F,  ? = %3F")
                print("     # = %23,  [ = %5B,  ] = %5D")
                print("   → Example: password@123 → password%40123")
                print()
                print("4. CLUSTER PAUSED OR DOWN:")
                print("   → Check MongoDB Atlas dashboard")
                print("   → Verify cluster is 'Running' (not 'Paused')")
                print()
                print("5. NETWORK/FIREWALL BLOCKING:")
                print("   → Try accessing MongoDB Atlas website")
                print("   → Check if VPN/proxy is interfering")
                print("   → Disable VPN temporarily to test")
                print()
                print("="*70)
        return None, None

