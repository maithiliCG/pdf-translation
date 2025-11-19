# MongoDB Integration Architecture

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PDF Translation Application                      │
│                              (Streamlit UI)                              │
└───────────────────────┬─────────────────────────────────────────────────┘
                        │
                        │ User Interactions
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ PDF Translator│ │   Solution   │ │     MCQ      │
│     Tab       │ │  Generator   │ │  Generator   │
│               │ │     Tab      │ │     Tab      │
└───────┬───────┘ └───────┬──────┘ └───────┬──────┘
        │                 │                 │
        │                 │                 │
        └─────────────────┼─────────────────┘
                          │
                          │ app.py
                          │
                          ▼
              ┌────────────────────────┐
              │  Database Service      │
              │  (database_service.py) │
              │                        │
              │  • store_translation() │
              │  • store_solution()    │
              │  • store_mcq()         │
              │  • get_*()             │
              │  • list_*()            │
              └───────────┬────────────┘
                          │
                          │ PyMongo
                          │
              ┌───────────▼────────────┐
              │      MongoDB           │
              │  (Local or Atlas)      │
              └────────────────────────┘
```

---

## Data Flow - PDF Translation

```
User Upload PDF
      │
      ▼
┌─────────────────────────────────────┐
│  1. Streamlit File Uploader         │
│     (translator_file)                │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  2. PDF Translation Engine          │
│     (translate_pdf_with_pdf2zh)     │
│     - Processes PDF                 │
│     - Generates translations        │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  3. Save to Local Files             │
│     - mono_pdf_path                 │
│     - dual_pdf_path                 │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  4. Store in MongoDB                │
│     db_service.store_translation()  │
│     ┌─────────────────────────────┐ │
│     │ Input PDF → GridFS          │ │
│     │ Mono PDF → GridFS           │ │
│     │ Dual PDF → GridFS           │ │
│     │ Metadata → Collection       │ │
│     └─────────────────────────────┘ │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  5. User Downloads                  │
│     - Monolingual PDF               │
│     - Bilingual PDF                 │
└─────────────────────────────────────┘
```

---

## MongoDB Collection Structure

```
pdf_translation_db (Database)
│
├── translations (Collection)
│   ├── Document 1
│   │   ├── _id: ObjectId
│   │   ├── input_file_id: ObjectId → GridFS
│   │   ├── input_filename: "document.pdf"
│   │   ├── language: "Hindi"
│   │   ├── mono_pdf_id: ObjectId → GridFS
│   │   ├── dual_pdf_id: ObjectId → GridFS
│   │   ├── created_at: ISODate
│   │   ├── status: "completed"
│   │   └── metadata: {...}
│   └── ...
│
├── solutions (Collection)
│   ├── Document 1
│   │   ├── _id: ObjectId
│   │   ├── input_file_id: ObjectId → GridFS
│   │   ├── input_filename: "questions.pdf"
│   │   ├── language: "Telugu"
│   │   ├── docx_file_id: ObjectId → GridFS
│   │   ├── json_data: {...}
│   │   ├── created_at: ISODate
│   │   ├── status: "completed"
│   │   └── metadata: {...}
│   └── ...
│
├── mcqs (Collection)
│   ├── Document 1
│   │   ├── _id: ObjectId
│   │   ├── topic: "Photosynthesis"
│   │   ├── language: "English"
│   │   ├── num_questions: 5
│   │   ├── mcq_data: [...]
│   │   ├── docx_file_id: ObjectId → GridFS
│   │   ├── created_at: ISODate
│   │   ├── status: "completed"
│   │   └── metadata: {...}
│   └── ...
│
└── GridFS (File Storage)
    ├── fs.files (Metadata)
    │   ├── _id: ObjectId
    │   ├── filename: "document.pdf"
    │   ├── length: 1024000
    │   ├── chunkSize: 261120
    │   └── uploadDate: ISODate
    │
    └── fs.chunks (File Data)
        ├── _id: ObjectId
        ├── files_id: ObjectId → fs.files
        ├── n: 0 (chunk number)
        └── data: BinData (actual file bytes)
```

---

## File Organization

```
pdf-translation/
│
├── app.py                              ← Main application (MODIFIED)
│   ├── Import db_service
│   ├── Tab 1: PDF Translator (+ MongoDB)
│   ├── Tab 2: Solution Generator (+ MongoDB)
│   └── Tab 3: MCQ Generator (+ MongoDB)
│
├── config/
│   ├── __init__.py
│   └── settings.py                     ← Configuration (MODIFIED)
│       ├── MONGODB_URI
│       ├── MONGODB_DATABASE
│       └── get_mongodb_connection()
│
├── modules/
│   ├── __init__.py
│   ├── common.py
│   ├── solution_generator.py
│   ├── mcq_generator.py
│   ├── pdf_translator.py
│   └── database_service.py             ← NEW - Database operations
│       ├── DatabaseService class
│       ├── store_translation()
│       ├── store_solution()
│       ├── store_mcq()
│       ├── get_*() methods
│       └── list_*() methods
│
├── requirements.txt                    ← Updated with MongoDB deps
│   ├── pymongo>=4.6.0
│   └── dnspython>=2.4.0
│
├── .env                                ← Your configuration (CREATE)
│   ├── GENAI_API_KEY=...
│   ├── MONGODB_URI=...
│   └── MONGODB_DATABASE=...
│
├── env.example                         ← Template (UPDATED)
│
├── README.md                           ← Updated with MongoDB info
│
└── Documentation (NEW)
    ├── MONGODB_SETUP.md                ← Complete setup guide
    ├── MONGODB_QUICK_REFERENCE.md      ← Quick reference
    ├── IMPLEMENTATION_SUMMARY.md       ← Technical details
    ├── SETUP_INSTRUCTIONS.txt          ← Step-by-step setup
    └── ARCHITECTURE_DIAGRAM.md         ← This file
```

---

## Component Interaction Flow

```
┌─────────────┐
│   User      │
└──────┬──────┘
       │ 1. Upload File
       ▼
┌──────────────────────┐
│  Streamlit UI        │
│  (app.py)            │
└──────┬───────────────┘
       │ 2. Process Request
       ▼
┌──────────────────────┐
│  Processing Modules  │
│  • pdf_translator    │
│  • solution_gen      │
│  • mcq_generator     │
└──────┬───────────────┘
       │ 3. Get Results
       │
       ├─────────────────┐
       │                 │
       ▼                 ▼
┌──────────────┐  ┌─────────────────────┐
│  Local Files │  │  Database Service   │
│  (temp)      │  │  (database_service) │
└──────────────┘  └─────────┬───────────┘
                            │ 4. Store Data
                            ▼
                  ┌──────────────────────┐
                  │  MongoDB             │
                  │  ┌────────────────┐  │
                  │  │  Collections   │  │
                  │  │  • translations│  │
                  │  │  • solutions   │  │
                  │  │  • mcqs        │  │
                  │  └────────────────┘  │
                  │  ┌────────────────┐  │
                  │  │  GridFS        │  │
                  │  │  • fs.files    │  │
                  │  │  • fs.chunks   │  │
                  │  └────────────────┘  │
                  └──────────────────────┘
```

---

## Error Handling Flow

```
Application Start
      │
      ▼
┌─────────────────────────────┐
│ Try: Connect to MongoDB     │
│ (get_mongodb_connection)    │
└──────────┬──────────────────┘
           │
           ├─────── Success? ──────┐
           │                       │
          YES                     NO
           │                       │
           ▼                       ▼
┌──────────────────┐   ┌─────────────────────┐
│ ✅ Connected     │   │ ⚠️ Warning Message  │
│ MongoDB Active   │   │ Continue without DB │
│ Data saved       │   │ No data persistence │
└──────────────────┘   └─────────────────────┘
           │                       │
           └───────────┬───────────┘
                       │
                       ▼
              ┌────────────────┐
              │ Application    │
              │ Runs Normally  │
              └────────────────┘
```

---

## Database Service API

### Class: DatabaseService

```python
class DatabaseService:
    
    # Connection
    __init__()                              # Initialize connection
    is_connected() -> bool                  # Check connection status
    
    # PDF Translation
    store_translation(                      # Store translation job
        input_file_data,
        input_filename,
        language,
        mono_pdf_data=None,
        dual_pdf_data=None,
        metadata=None
    ) -> Optional[str]                      # Returns job_id
    
    get_translation(translation_id)         # Get by ID
    list_translations(limit, language)      # List with filters
    
    # Solution Generation
    store_solution(                         # Store solution job
        input_file_data,
        input_filename,
        language,
        docx_data=None,
        json_data=None,
        metadata=None
    ) -> Optional[str]                      # Returns job_id
    
    get_solution(solution_id)               # Get by ID
    list_solutions(limit, language)         # List with filters
    
    # MCQ Generation
    store_mcq(                              # Store MCQ job
        topic,
        language,
        num_questions,
        mcq_data,
        docx_data=None,
        metadata=None
    ) -> Optional[str]                      # Returns job_id
    
    get_mcq(mcq_id)                         # Get by ID
    list_mcqs(limit, topic)                 # List with filters
    
    # Utilities
    get_file_from_gridfs(file_id)           # Download file
    get_statistics()                        # Database stats
```

---

## GridFS Storage Pattern

```
Large File (e.g., 5MB PDF)
        │
        ▼
┌───────────────────────┐
│  GridFS.put()         │
│  - Chunks file        │
│  - Stores metadata    │
└───────┬───────────────┘
        │
        ├─────────────────────┐
        │                     │
        ▼                     ▼
┌──────────────┐    ┌────────────────┐
│  fs.files    │    │   fs.chunks    │
│              │    │                │
│ _id: xxx     │    │ files_id: xxx  │
│ filename     │    │ n: 0           │
│ length: 5MB  │    │ data: chunk0   │
│ chunkSize    │    │                │
│ uploadDate   │    │ files_id: xxx  │
│              │    │ n: 1           │
│              │    │ data: chunk1   │
│              │    │                │
│              │    │ ... (n chunks) │
└──────────────┘    └────────────────┘
```

**Retrieval:**
```
GridFS.get(file_id)
    ↓
Reassemble chunks
    ↓
Return complete file
```

---

## Performance Optimizations

### 1. Indexes Created Automatically
```javascript
// Translations
db.translations.createIndex({created_at: -1})
db.translations.createIndex({language: 1})

// Solutions
db.solutions.createIndex({created_at: -1})

// MCQs
db.mcqs.createIndex({topic: 1})
db.mcqs.createIndex({created_at: -1})
```

### 2. Connection Pooling
```
PyMongo automatically manages connection pool
- Default: 100 connections
- Reuses connections
- Thread-safe
```

### 3. GridFS Chunking
```
Files > 16MB automatically chunked
- Chunk size: 255KB (default)
- Parallel chunk retrieval
- Efficient for large files
```

---

## Security Architecture

```
┌─────────────────────────────────────┐
│  Application Layer                  │
│  - Environment variables (.env)     │
│  - No hardcoded credentials         │
└──────────────┬──────────────────────┘
               │ Secure connection
               │ (SSL/TLS)
               ▼
┌─────────────────────────────────────┐
│  MongoDB Atlas (Cloud)              │
│  ┌───────────────────────────────┐  │
│  │ Network Access                │  │
│  │ - IP Whitelist                │  │
│  │ - VPC Peering                 │  │
│  └───────────────────────────────┘  │
│  ┌───────────────────────────────┐  │
│  │ Database Access               │  │
│  │ - User authentication         │  │
│  │ - Role-based permissions      │  │
│  └───────────────────────────────┘  │
│  ┌───────────────────────────────┐  │
│  │ Data Encryption               │  │
│  │ - At rest                     │  │
│  │ - In transit                  │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

---

## Deployment Options

### Option 1: Local Development
```
Local MongoDB Server
        ↓
Development Machine
        ↓
Streamlit (localhost:8501)
```

### Option 2: Cloud Deployment
```
MongoDB Atlas (Cloud)
        ↓
        ↓ (Internet)
        ↓
Streamlit Cloud / Heroku / AWS
        ↓
Users (Web Browser)
```

---

## Summary

This architecture provides:

✅ **Scalable** - GridFS handles files of any size
✅ **Reliable** - Automatic failover with replica sets
✅ **Fast** - Indexed queries, connection pooling
✅ **Secure** - Encrypted connections, access control
✅ **Flexible** - Works with or without MongoDB
✅ **Production-Ready** - Error handling, logging

---

**Next Steps:** See SETUP_INSTRUCTIONS.txt to complete setup!

