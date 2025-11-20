# 🔌 API Documentation for React Team

## Overview
This document describes all main functions that can be exposed as REST API endpoints for React frontend integration.

---

## 📋 Table of Contents
1. [PDF Translator APIs](#1-pdf-translator-apis)
2. [Solution Generator APIs](#2-solution-generator-apis)
3. [MCQ Generator APIs](#3-mcq-generator-apis)
4. [Database APIs](#4-database-apis)
5. [Common Utilities](#5-common-utilities)

---

## 1. PDF Translator APIs

### 1.1 Translate PDF
**Function:** `translate_pdf_with_pdf2zh()`

**Location:** `modules/pdf_translator.py`

**Description:** Translates entire PDF document while preserving layout

**Parameters:**
```python
uploaded_file: File object or bytes
target_language: str  # e.g., "Hindi", "Telugu", "English"
progress_bar: Optional[ProgressBar]  # For UI updates (can be None)
status_placeholder: Optional[StatusPlaceholder]  # For UI updates (can be None)
```

**Returns:**
```python
{
    "job_dir": str,              # Job directory path
    "mono_pdf_path": str,        # Path to monolingual PDF
    "dual_pdf_path": str,        # Path to bilingual PDF
    "lang_code": str,            # Language code (e.g., "hi", "te")
    "lang_label": str            # Language label (e.g., "Hindi")
}
```

**Example REST API Endpoint:**
```python
POST /api/pdf/translate
Content-Type: multipart/form-data

Form Data:
- file: PDF file
- target_language: "Hindi"

Response:
{
    "success": true,
    "job_id": "uuid-string",
    "mono_pdf_url": "/download/mono_pdf.pdf",
    "dual_pdf_url": "/download/dual_pdf.pdf",
    "language": "Hindi"
}
```

**Error Handling:**
- Returns error if babeldoc not available
- Falls back to Gemini API if SiliconFlowFree fails
- Raises RuntimeError on failure

---

## 2. Solution Generator APIs

### 2.1 Run Solution Pipeline (MAIN FUNCTION)
**Function:** `run_solution_generation_pipeline()`

**Location:** `modules/solution_generator.py`

**Description:** Complete pipeline: Extract → Solve → Translate → Generate DOCX

**Parameters:**
```python
uploaded_file: File object or bytes
target_language: str  # e.g., "Telugu", "Hindi"
progress_bar: Optional[ProgressBar]
status_placeholder: Optional[StatusPlaceholder]
```

**Returns:**
```python
{
    "job_dir": str,
    "extracted_json": str,           # Path to extracted_data.json
    "solved_json": str,              # Path to solved_extracted_data.json
    "translated_json": str,          # Path to translated JSON
    "final_docx": str,               # Path to final DOCX file
    "language": str,                 # Target language
    "json_data": dict                # Full solution data
}
```

**Example REST API Endpoint:**
```python
POST /api/solution/generate
Content-Type: multipart/form-data

Form Data:
- file: PDF file
- target_language: "Telugu"

Response:
{
    "success": true,
    "job_id": "uuid-string",
    "docx_url": "/download/solutions_telugu.docx",
    "extracted_data": {...},  # JSON data
    "language": "Telugu"
}
```

### 2.2 Extract PDF (Sub-function)
**Function:** `_pipeline_extract_pdf()`

**Location:** `modules/solution_generator.py`

**Description:** Extracts text and images from PDF

**Parameters:**
```python
input_pdf_path: Path  # Path to PDF file
job_dir: Path         # Job directory
```

**Returns:**
```python
(
    pages_data: list,      # List of page data with text and images
    extracted_json: Path   # Path to JSON file
)
```

### 2.3 Solve Pages (Sub-function)
**Function:** `_pipeline_solve_pages()`

**Location:** `modules/solution_generator.py`

**Description:** Solves all questions from extracted pages

**Parameters:**
```python
pages: list              # Extracted page data
job_dir: Path           # Job directory
progress_callback: Optional[Callable]  # Progress callback
```

**Returns:**
```python
(
    results: list,        # List of solved questions
    solved_file: Path    # Path to solved JSON file
)
```

### 2.4 Translate Items (Sub-function)
**Function:** `_pipeline_translate_items()`

**Location:** `modules/solution_generator.py`

**Description:** Translates solved solutions to target language

**Parameters:**
```python
items: list             # Solved question items
target_language: str     # Target language
job_dir: Path          # Job directory
progress_callback: Optional[Callable]
```

**Returns:**
```python
list  # Translated items
```

---

## 3. MCQ Generator APIs

### 3.1 Generate MCQs (MAIN FUNCTION)
**Function:** `generate_mcqs()`

**Location:** `modules/mcq_generator.py`

**Description:** Generates multiple-choice questions on a topic

**Parameters:**
```python
topic: str              # Topic name (e.g., "Photosynthesis")
num_questions: int = 5  # Number of questions (1-10)
language: str = "English"  # Target language
```

**Returns:**
```python
str  # Raw JSON string response from AI
```

**Example REST API Endpoint:**
```python
POST /api/mcq/generate
Content-Type: application/json

Body:
{
    "topic": "Photosynthesis",
    "num_questions": 5,
    "language": "English"
}

Response:
{
    "success": true,
    "mcqs": [
        {
            "question": "What is the primary pigment in photosynthesis?",
            "options": ["Chlorophyll", "Hemoglobin", "Melanin", "Carotene"],
            "correct_answer": "Chlorophyll",
            "explanation": "Chlorophyll is the green pigment..."
        },
        ...
    ]
}
```

### 3.2 Parse MCQs
**Function:** `parse_mcqs()`

**Location:** `modules/mcq_generator.py`

**Description:** Parses raw AI response into JSON array

**Parameters:**
```python
raw_text: str  # Raw response from generate_mcqs()
```

**Returns:**
```python
list | None  # List of MCQ objects or None if parsing fails
```

**Example:**
```python
raw_response = generate_mcqs("Photosynthesis", 5, "English")
mcqs = parse_mcqs(raw_response)
# Returns: [{"question": "...", "options": [...], ...}, ...]
```

### 3.3 Translate MCQ Items
**Function:** `_translate_mcq_items()`

**Location:** `modules/mcq_generator.py`

**Description:** Translates MCQ questions, options, answers, and explanations

**Parameters:**
```python
mcqs: list           # List of MCQ objects
target_language: str  # Target language
```

**Returns:**
```python
list  # List of translated MCQ objects
```

**Example REST API Endpoint:**
```python
POST /api/mcq/translate
Content-Type: application/json

Body:
{
    "mcqs": [...],  # Original MCQs
    "target_language": "Hindi"
}

Response:
{
    "success": true,
    "translated_mcqs": [
        {
            "question": "प्रकाश संश्लेषण में प्राथमिक वर्णक क्या है?",
            "options": [...],
            "answer": "क्लोरोफिल",
            "explanation": "..."
        },
        ...
    ]
}
```

### 3.4 Translate Text (Utility)
**Function:** `translate_text()`

**Location:** `modules/mcq_generator.py`

**Description:** Translates any text to target language

**Parameters:**
```python
text: str
target_language: str = "English"
```

**Returns:**
```python
str  # Translated text
```

---

## 4. Database APIs

### 4.1 Store Translation
**Function:** `db_service.store_translation()`

**Location:** `modules/database_service.py`

**Description:** Stores PDF translation job metadata

**Parameters:**
```python
input_file_data: bytes
input_filename: str
language: str
mono_pdf_data: Optional[bytes] = None
dual_pdf_data: Optional[bytes] = None
metadata: Optional[Dict] = None
```

**Returns:**
```python
str | None  # Job ID if successful, None otherwise
```

**Example REST API Endpoint:**
```python
POST /api/database/translations
Content-Type: application/json

Body:
{
    "input_filename": "document.pdf",
    "language": "Hindi",
    "input_file_size": 1024000,
    "has_mono_pdf": true,
    "mono_pdf_size": 1050000,
    "has_dual_pdf": true,
    "dual_pdf_size": 2100000
}

Response:
{
    "success": true,
    "job_id": "507f1f77bcf86cd799439011"
}
```

### 4.2 Store Solution
**Function:** `db_service.store_solution()`

**Location:** `modules/database_service.py`

**Description:** Stores solution generation job metadata

**Parameters:**
```python
input_file_data: bytes
input_filename: str
language: str
docx_data: Optional[bytes] = None
json_data: Optional[Dict] = None
metadata: Optional[Dict] = None
```

**Returns:**
```python
str | None  # Job ID
```

### 4.3 Store MCQ
**Function:** `db_service.store_mcq()`

**Location:** `modules/database_service.py`

**Description:** Stores MCQ generation job metadata

**Parameters:**
```python
topic: str
language: str
num_questions: int
mcq_data: List[Dict]
docx_data: Optional[bytes] = None
metadata: Optional[Dict] = None
```

**Returns:**
```python
str | None  # Job ID
```

### 4.4 Get Translation
**Function:** `db_service.get_translation()`

**Location:** `modules/database_service.py`

**Description:** Retrieves translation job by ID

**Parameters:**
```python
translation_id: str
```

**Returns:**
```python
dict | None  # Translation document or None
```

### 4.5 List Translations
**Function:** `db_service.list_translations()`

**Location:** `modules/database_service.py`

**Description:** Lists recent translations

**Parameters:**
```python
limit: int = 50
language: Optional[str] = None
```

**Returns:**
```python
list  # List of translation documents
```

---

## 5. Common Utilities

### 5.1 Call Generative Model
**Function:** `_call_generative_model()`

**Location:** `modules/common.py`

**Description:** Wrapper for Gemini API calls with retry logic

**Parameters:**
```python
prompt: str
max_attempts: int = 3
cooldown_seconds: float = 45.0
```

**Returns:**
```python
Response object  # Gemini API response
```

**Features:**
- Automatic retry on quota errors
- Rate limiting (1 second delay)
- Suppresses quota warnings during retries

### 5.2 Create DOCX
**Function:** `create_docx()`

**Location:** `modules/common.py`

**Description:** Creates DOCX file from text content

**Parameters:**
```python
content: str      # Text content
title: str = "Document"  # Document title
```

**Returns:**
```python
bytes | None  # DOCX file bytes or None on error
```

---

## 🔄 Recommended REST API Structure

### Base URL
```
http://your-backend-url/api
```

### Endpoints

#### PDF Translation
```
POST   /api/pdf/translate
GET    /api/pdf/translate/{job_id}
GET    /api/pdf/download/{job_id}/mono
GET    /api/pdf/download/{job_id}/dual
```

#### Solution Generator
```
POST   /api/solution/generate
GET    /api/solution/{job_id}
GET    /api/solution/download/{job_id}/docx
```

#### MCQ Generator
```
POST   /api/mcq/generate
POST   /api/mcq/translate
GET    /api/mcq/{job_id}
GET    /api/mcq/download/{job_id}/docx
```

#### Database
```
GET    /api/database/translations
GET    /api/database/solutions
GET    /api/database/mcqs
GET    /api/database/statistics
```

---

## 📝 Example React Integration

### Example 1: Generate MCQs
```javascript
// React Component
const generateMCQs = async (topic, numQuestions, language) => {
  const response = await fetch('/api/mcq/generate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      topic: topic,
      num_questions: numQuestions,
      language: language
    })
  });
  
  const data = await response.json();
  return data.mcqs;
};
```

### Example 2: Translate PDF
```javascript
// React Component
const translatePDF = async (file, targetLanguage) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('target_language', targetLanguage);
  
  const response = await fetch('/api/pdf/translate', {
    method: 'POST',
    body: formData
  });
  
  const data = await response.json();
  return {
    jobId: data.job_id,
    monoPdfUrl: data.mono_pdf_url,
    dualPdfUrl: data.dual_pdf_url
  };
};
```

### Example 3: Generate Solutions
```javascript
// React Component
const generateSolutions = async (file, targetLanguage) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('target_language', targetLanguage);
  
  const response = await fetch('/api/solution/generate', {
    method: 'POST',
    body: formData
  });
  
  const data = await response.json();
  return {
    jobId: data.job_id,
    docxUrl: data.docx_url,
    solutionData: data.extracted_data
  };
};
```

---

## 🔧 Backend Implementation (FastAPI Example)

```python
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse
from modules.pdf_translator import translate_pdf_with_pdf2zh
from modules.solution_generator import run_solution_generation_pipeline
from modules.mcq_generator import generate_mcqs, parse_mcqs

app = FastAPI()

@app.post("/api/pdf/translate")
async def translate_pdf(
    file: UploadFile = File(...),
    target_language: str = Form(...)
):
    result = translate_pdf_with_pdf2zh(
        uploaded_file=file,
        target_language=target_language
    )
    return {
        "success": True,
        "job_id": result["job_dir"],
        "mono_pdf_url": f"/api/pdf/download/{result['job_dir']}/mono",
        "dual_pdf_url": f"/api/pdf/download/{result['job_dir']}/dual"
    }

@app.post("/api/mcq/generate")
async def generate_mcq(
    topic: str,
    num_questions: int = 5,
    language: str = "English"
):
    raw = generate_mcqs(topic, num_questions, language)
    mcqs = parse_mcqs(raw)
    return {
        "success": True,
        "mcqs": mcqs
    }

@app.post("/api/solution/generate")
async def generate_solution(
    file: UploadFile = File(...),
    target_language: str = Form(...)
):
    result = run_solution_generation_pipeline(
        uploaded_file=file,
        target_language=target_language
    )
    return {
        "success": True,
        "job_id": result["job_dir"],
        "docx_url": f"/api/solution/download/{result['job_dir']}/docx",
        "extracted_data": result.get("json_data")
    }
```

---

## ⚙️ Configuration Required

### Environment Variables
```bash
GENAI_API_KEY=your_gemini_api_key
MONGODB_URI=mongodb://localhost:27017/  # Optional
```

### Dependencies
- Python 3.12 or 3.13
- All packages from `requirements.txt`
- FastAPI/Flask for REST API (if creating endpoints)

---

## 📊 Response Formats

### Success Response
```json
{
    "success": true,
    "data": {...},
    "message": "Operation completed successfully"
}
```

### Error Response
```json
{
    "success": false,
    "error": "Error message",
    "error_code": "ERROR_CODE"
}
```

---

## 🔐 Authentication (Optional)

If you need authentication:
```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

@app.post("/api/pdf/translate")
async def translate_pdf(
    token: str = Depends(security),
    ...
):
    # Verify token
    if not verify_token(token):
        raise HTTPException(status_code=401, detail="Invalid token")
    # ... rest of function
```

---

## 📝 Notes for React Team

1. **File Uploads:** Use `multipart/form-data` for PDF uploads
2. **Progress Tracking:** Consider WebSocket or Server-Sent Events for real-time progress
3. **Error Handling:** All functions may raise exceptions - handle gracefully
4. **Async Operations:** PDF translation and solution generation are long-running - consider background jobs
5. **File Downloads:** Return file paths/URLs, not file data in JSON responses
6. **Database:** MongoDB is optional - app works without it

---

## 🚀 Quick Start for Backend Team

1. Install dependencies: `pip install -r requirements.txt`
2. Set environment variables in `.env`
3. Create FastAPI/Flask app
4. Import functions from modules
5. Create REST endpoints as shown above
6. Test with Postman/curl before React integration

---

## 📞 Support

For questions about:
- **Function parameters:** Check function docstrings in source code
- **Return values:** Check function return types
- **Error handling:** Check exception handling in source code
- **Configuration:** Check `config/settings.py`


