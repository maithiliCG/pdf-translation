# ⚡ Quick API Reference - Main Functions

## 🎯 Three Main Functions for React Team

### 1. PDF Translation
```python
# Function
translate_pdf_with_pdf2zh(uploaded_file, target_language)

# Input
- uploaded_file: PDF file (bytes or file object)
- target_language: "Hindi" | "Telugu" | "English" | etc.

# Output
{
    "mono_pdf_path": "/path/to/mono.pdf",
    "dual_pdf_path": "/path/to/dual.pdf",
    "lang_code": "hi",
    "lang_label": "Hindi"
}

# REST Endpoint
POST /api/pdf/translate
```

---

### 2. Solution Generator
```python
# Function
run_solution_generation_pipeline(uploaded_file, target_language)

# Input
- uploaded_file: PDF file (bytes or file object)
- target_language: "Telugu" | "Hindi" | etc.

# Output
{
    "final_docx": "/path/to/solutions.docx",
    "json_data": {...},  # All solution data
    "language": "Telugu"
}

# REST Endpoint
POST /api/solution/generate
```

---

### 3. MCQ Generator
```python
# Function
generate_mcqs(topic, num_questions, language)

# Input
- topic: "Photosynthesis"
- num_questions: 5
- language: "English" | "Hindi" | etc.

# Output (raw string - needs parsing)
"[{\"question\": \"...\", \"options\": [...], ...}]"

# Parse with
parse_mcqs(raw_response)  # Returns list of MCQ objects

# REST Endpoint
POST /api/mcq/generate
```

---

## 📦 Function Locations

| Function | File | Line |
|----------|------|------|
| `translate_pdf_with_pdf2zh` | `modules/pdf_translator.py` | 154 |
| `run_solution_generation_pipeline` | `modules/solution_generator.py` | 982 |
| `generate_mcqs` | `modules/mcq_generator.py` | 11 |
| `parse_mcqs` | `modules/mcq_generator.py` | 29 |

---

## 🔄 Simple REST API Mapping

```
React Frontend Request
    ↓
FastAPI/Flask Backend
    ↓
Python Function Call
    ↓
Return JSON Response
```

---

## 📝 Example Backend Code

```python
from fastapi import FastAPI, UploadFile, File, Form
from modules.pdf_translator import translate_pdf_with_pdf2zh
from modules.solution_generator import run_solution_generation_pipeline
from modules.mcq_generator import generate_mcqs, parse_mcqs

app = FastAPI()

@app.post("/api/pdf/translate")
def translate_pdf(file: UploadFile, language: str = Form()):
    result = translate_pdf_with_pdf2zh(file, language)
    return {"success": True, "data": result}

@app.post("/api/solution/generate")
def generate_solution(file: UploadFile, language: str = Form()):
    result = run_solution_generation_pipeline(file, language)
    return {"success": True, "data": result}

@app.post("/api/mcq/generate")
def generate_mcq(topic: str, num_questions: int, language: str):
    raw = generate_mcqs(topic, num_questions, language)
    mcqs = parse_mcqs(raw)
    return {"success": True, "mcqs": mcqs}
```

---

## 🎨 React Example

```javascript
// PDF Translation
const translatePDF = async (file, language) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('language', language);
  
  const res = await fetch('/api/pdf/translate', {
    method: 'POST',
    body: formData
  });
  return await res.json();
};

// Generate MCQs
const generateMCQs = async (topic, count, language) => {
  const res = await fetch('/api/mcq/generate', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({topic, num_questions: count, language})
  });
  return await res.json();
};
```

---

## ⚙️ Required Setup

1. **Environment Variable:**
   ```bash
   GENAI_API_KEY=your_key_here
   ```

2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Create REST API:**
   - Use FastAPI or Flask
   - Import functions from modules
   - Create endpoints as shown above

---

## 📚 Full Documentation

See `API_DOCUMENTATION.md` for complete details.


