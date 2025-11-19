"""
MongoDB Database Service for PDF Translation Application
Handles storing and retrieving metadata (no binary file storage)
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from bson.objectid import ObjectId
from config.settings import get_mongodb_connection


class DatabaseService:
    """Service class for MongoDB operations"""
    
    def __init__(self):
        """Initialize database connection (fs.files metadata, no fs.chunks)"""
        self.client, self.db = get_mongodb_connection()
        
        # Initialize collections
        if self.db is not None:
            self.translations_collection = self.db['translations']
            self.solutions_collection = self.db['solutions']
            self.mcqs_collection = self.db['mcqs']
            # fs.files collection for file metadata (no fs.chunks)
            self.fs_files_collection = self.db['fs.files']
            self._create_indexes()
    
    def _create_indexes(self):
        """Create database indexes for better performance"""
        try:
            # Create indexes for faster queries
            self.translations_collection.create_index([("created_at", -1)])
            self.translations_collection.create_index([("language", 1)])
            self.solutions_collection.create_index([("created_at", -1)])
            self.mcqs_collection.create_index([("topic", 1)])
            self.mcqs_collection.create_index([("created_at", -1)])
            # Indexes for fs.files (GridFS-like metadata)
            self.fs_files_collection.create_index([("filename", 1)])
            self.fs_files_collection.create_index([("uploadDate", -1)])
        except Exception as e:
            print(f"Warning: Could not create indexes: {e}")
    
    def is_connected(self) -> bool:
        """Check if MongoDB is connected"""
        return self.db is not None
    
    # ==== FILE METADATA OPERATIONS (fs.files format, no chunks) ====
    
    def store_file_metadata(
        self,
        file_data: bytes,
        filename: str,
        content_type: str = "application/octet-stream",
        metadata: Optional[Dict] = None
    ) -> Optional[ObjectId]:
        """
        Store file metadata in fs.files format (NO binary chunks stored)
        
        Args:
            file_data: File binary data (used only for size/md5 calculation, NOT stored)
            filename: File name
            content_type: MIME type
            metadata: Additional metadata
            
        Returns:
            File ID (ObjectId) if successful, None otherwise
        """
        if not self.is_connected():
            return None
        
        try:
            import hashlib
            
            # Calculate file properties (but don't store the data)
            file_length = len(file_data)
            md5_hash = hashlib.md5(file_data).hexdigest() if file_data else ""
            upload_date = datetime.utcnow()
            
            # Create fs.files document (GridFS metadata format)
            file_doc = {
                "_id": ObjectId(),
                "filename": filename,
                "length": file_length,
                "chunkSize": 255 * 1024,  # Standard GridFS chunk size
                "uploadDate": upload_date,
                "md5": md5_hash,
                "contentType": content_type,
                "metadata": metadata or {},
                # Custom flag to indicate no chunks stored
                "_no_chunks": True
            }
            
            result = self.fs_files_collection.insert_one(file_doc)
            return result.inserted_id
        
        except Exception as e:
            print(f"Error storing file metadata: {e}")
            return None
    
    def get_file_metadata(self, file_id: ObjectId) -> Optional[Dict]:
        """Get file metadata from fs.files collection"""
        if not self.is_connected():
            return None
        
        try:
            doc = self.fs_files_collection.find_one({"_id": file_id})
            if doc:
                doc['_id'] = str(doc['_id'])
            return doc
        except Exception as e:
            print(f"Error retrieving file metadata: {e}")
            return None
    
    def find_files_by_filename(self, filename: str) -> List[Dict]:
        """Find files by filename in fs.files collection"""
        if not self.is_connected():
            return []
        
        try:
            cursor = self.fs_files_collection.find({"filename": filename}).sort("uploadDate", -1)
            results = []
            for doc in cursor:
                doc['_id'] = str(doc['_id'])
                results.append(doc)
            return results
        except Exception as e:
            print(f"Error finding files: {e}")
            return []
    
    # ==== PDF TRANSLATION OPERATIONS ====
    
    def store_translation(
        self,
        input_file_data: bytes,
        input_filename: str,
        language: str,
        mono_pdf_data: Optional[bytes] = None,
        dual_pdf_data: Optional[bytes] = None,
        metadata: Optional[Dict] = None
    ) -> Optional[str]:
        """
        Store a PDF translation job metadata (no binary storage)
        
        Args:
            input_file_data: Original PDF file data (not stored, only for size calculation)
            input_filename: Name of input file
            language: Target translation language
            mono_pdf_data: Monolingual translated PDF (not stored, only for size calculation)
            dual_pdf_data: Bilingual translated PDF (not stored, only for size calculation)
            metadata: Additional metadata
            
        Returns:
            Translation job ID if successful, None otherwise
        """
        if not self.is_connected():
            return None
        
        try:
            # Store file metadata in fs.files (no chunks)
            input_file_id = None
            mono_file_id = None
            dual_file_id = None
            
            if input_file_data:
                input_file_id = self.store_file_metadata(
                    file_data=input_file_data,
                    filename=input_filename,
                    content_type="application/pdf",
                    metadata={"type": "input", "language": language}
                )
            
            if mono_pdf_data:
                mono_file_id = self.store_file_metadata(
                    file_data=mono_pdf_data,
                    filename=f"mono_{input_filename}",
                    content_type="application/pdf",
                    metadata={"type": "mono_pdf", "language": language}
                )
            
            if dual_pdf_data:
                dual_file_id = self.store_file_metadata(
                    file_data=dual_pdf_data,
                    filename=f"dual_{input_filename}",
                    content_type="application/pdf",
                    metadata={"type": "dual_pdf", "language": language}
                )
            
            # Create translation document with file IDs
            translation_doc = {
                "input_file_id": str(input_file_id) if input_file_id else None,
                "input_filename": input_filename,
                "input_file_size": len(input_file_data) if input_file_data else 0,
                "language": language,
                "mono_pdf_id": str(mono_file_id) if mono_file_id else None,
                "mono_pdf_size": len(mono_pdf_data) if mono_pdf_data else 0,
                "dual_pdf_id": str(dual_file_id) if dual_file_id else None,
                "dual_pdf_size": len(dual_pdf_data) if dual_pdf_data else 0,
                "created_at": datetime.utcnow(),
                "status": "completed" if mono_pdf_data or dual_pdf_data else "pending",
                "metadata": metadata or {}
            }
            
            result = self.translations_collection.insert_one(translation_doc)
            return str(result.inserted_id)
        
        except Exception as e:
            print(f"Error storing translation: {e}")
            return None
    
    def get_translation(self, translation_id: str) -> Optional[Dict]:
        """Get translation details by ID"""
        if not self.is_connected():
            return None
        
        try:
            doc = self.translations_collection.find_one({"_id": ObjectId(translation_id)})
            if doc:
                doc['_id'] = str(doc['_id'])
            return doc
        except Exception as e:
            print(f"Error retrieving translation: {e}")
            return None
    
    
    def list_translations(self, limit: int = 50, language: Optional[str] = None) -> List[Dict]:
        """List recent translations"""
        if not self.is_connected():
            return []
        
        try:
            query = {}
            if language:
                query['language'] = language
            
            cursor = self.translations_collection.find(query).sort("created_at", -1).limit(limit)
            results = []
            for doc in cursor:
                doc['_id'] = str(doc['_id'])
                results.append(doc)
            return results
        except Exception as e:
            print(f"Error listing translations: {e}")
            return []
    
    # ==== SOLUTION GENERATION OPERATIONS ====
    
    def store_solution(
        self,
        input_file_data: bytes,
        input_filename: str,
        language: str,
        docx_data: Optional[bytes] = None,
        json_data: Optional[Dict] = None,
        metadata: Optional[Dict] = None
    ) -> Optional[str]:
        """
        Store a solution generation job metadata (no binary storage)
        
        Args:
            input_file_data: Original PDF file data (not stored, only for size calculation)
            input_filename: Name of input file
            language: Target language
            docx_data: Generated DOCX file (not stored, only for size calculation)
            json_data: Solution JSON data (stored as metadata)
            metadata: Additional metadata
            
        Returns:
            Solution job ID if successful, None otherwise
        """
        if not self.is_connected():
            return None
        
        try:
            # Store file metadata in fs.files (no chunks)
            input_file_id = None
            docx_file_id = None
            
            if input_file_data:
                input_file_id = self.store_file_metadata(
                    file_data=input_file_data,
                    filename=input_filename,
                    content_type="application/pdf",
                    metadata={"type": "input", "language": language}
                )
            
            if docx_data:
                docx_file_id = self.store_file_metadata(
                    file_data=docx_data,
                    filename=f"solution_{input_filename.replace('.pdf', '.docx')}",
                    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    metadata={"type": "solution_docx", "language": language}
                )
            
            # Create solution document with file IDs
            solution_doc = {
                "input_file_id": str(input_file_id) if input_file_id else None,
                "input_filename": input_filename,
                "input_file_size": len(input_file_data) if input_file_data else 0,
                "language": language,
                "docx_file_id": str(docx_file_id) if docx_file_id else None,
                "has_docx": docx_data is not None,
                "docx_size": len(docx_data) if docx_data else 0,
                "json_data": json_data,
                "created_at": datetime.utcnow(),
                "status": "completed" if docx_data else "pending",
                "metadata": metadata or {}
            }
            
            result = self.solutions_collection.insert_one(solution_doc)
            return str(result.inserted_id)
        
        except Exception as e:
            print(f"Error storing solution: {e}")
            return None
    
    def get_solution(self, solution_id: str) -> Optional[Dict]:
        """Get solution details by ID"""
        if not self.is_connected():
            return None
        
        try:
            doc = self.solutions_collection.find_one({"_id": ObjectId(solution_id)})
            if doc:
                doc['_id'] = str(doc['_id'])
            return doc
        except Exception as e:
            print(f"Error retrieving solution: {e}")
            return None
    
    def list_solutions(self, limit: int = 50, language: Optional[str] = None) -> List[Dict]:
        """List recent solutions"""
        if not self.is_connected():
            return []
        
        try:
            query = {}
            if language:
                query['language'] = language
            
            cursor = self.solutions_collection.find(query).sort("created_at", -1).limit(limit)
            results = []
            for doc in cursor:
                doc['_id'] = str(doc['_id'])
                results.append(doc)
            return results
        except Exception as e:
            print(f"Error listing solutions: {e}")
            return []
    
    # ==== MCQ GENERATION OPERATIONS ====
    
    def store_mcq(
        self,
        topic: str,
        language: str,
        num_questions: int,
        mcq_data: List[Dict],
        docx_data: Optional[bytes] = None,
        metadata: Optional[Dict] = None
    ) -> Optional[str]:
        """
        Store an MCQ generation job metadata (no binary storage)
        
        Args:
            topic: MCQ topic
            language: Target language
            num_questions: Number of questions
            mcq_data: MCQ data (list of questions) - stored as metadata
            docx_data: Generated DOCX file (not stored, only for size calculation)
            metadata: Additional metadata
            
        Returns:
            MCQ job ID if successful, None otherwise
        """
        if not self.is_connected():
            return None
        
        try:
            # Store file metadata in fs.files (no chunks)
            docx_file_id = None
            
            if docx_data:
                docx_file_id = self.store_file_metadata(
                    file_data=docx_data,
                    filename=f"mcq_{topic.replace(' ', '_')}_{language}.docx",
                    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    metadata={"type": "mcq_docx", "topic": topic, "language": language}
                )
            
            # Create MCQ document with file ID
            mcq_doc = {
                "topic": topic,
                "language": language,
                "num_questions": num_questions,
                "mcq_data": mcq_data,
                "docx_file_id": str(docx_file_id) if docx_file_id else None,
                "has_docx": docx_data is not None,
                "docx_size": len(docx_data) if docx_data else 0,
                "created_at": datetime.utcnow(),
                "status": "completed",
                "metadata": metadata or {}
            }
            
            result = self.mcqs_collection.insert_one(mcq_doc)
            return str(result.inserted_id)
        
        except Exception as e:
            print(f"Error storing MCQ: {e}")
            return None
    
    def get_mcq(self, mcq_id: str) -> Optional[Dict]:
        """Get MCQ details by ID"""
        if not self.is_connected():
            return None
        
        try:
            doc = self.mcqs_collection.find_one({"_id": ObjectId(mcq_id)})
            if doc:
                doc['_id'] = str(doc['_id'])
            return doc
        except Exception as e:
            print(f"Error retrieving MCQ: {e}")
            return None
    
    def list_mcqs(self, limit: int = 50, topic: Optional[str] = None) -> List[Dict]:
        """List recent MCQs"""
        if not self.is_connected():
            return []
        
        try:
            query = {}
            if topic:
                query['topic'] = {"$regex": topic, "$options": "i"}
            
            cursor = self.mcqs_collection.find(query).sort("created_at", -1).limit(limit)
            results = []
            for doc in cursor:
                doc['_id'] = str(doc['_id'])
                results.append(doc)
            return results
        except Exception as e:
            print(f"Error listing MCQs: {e}")
            return []
    
    # ==== STATISTICS ====
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics"""
        if not self.is_connected():
            return {"error": "Database not connected"}
        
        try:
            stats = {
                "total_translations": self.translations_collection.count_documents({}),
                "total_solutions": self.solutions_collection.count_documents({}),
                "total_mcqs": self.mcqs_collection.count_documents({}),
                "database_connected": True
            }
            return stats
        except Exception as e:
            print(f"Error getting statistics: {e}")
            return {"error": str(e)}


# Create a singleton instance
db_service = DatabaseService()
