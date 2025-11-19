"""
MongoDB Database Service for PDF Translation Application
Stores metadata only (no binary files)
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from bson.objectid import ObjectId
from config.settings import get_mongodb_connection


class DatabaseService:
    """Service class for MongoDB operations - metadata only"""
    
    def __init__(self):
        """Initialize database connection"""
        self.client, self.db = get_mongodb_connection()
        
        # Initialize collections
        if self.db is not None:
            self.translations_collection = self.db['translations']
            self.solutions_collection = self.db['solutions']
            self.mcqs_collection = self.db['mcqs']
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
        except Exception as e:
            print(f"Warning: Could not create indexes: {e}")
    
    def is_connected(self) -> bool:
        """Check if MongoDB is connected"""
        return self.db is not None
    
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
        Store PDF translation metadata (no binary files)
        
        Args:
            input_file_data: Not stored (kept for compatibility)
            input_filename: Name of input file
            language: Target translation language
            mono_pdf_data: Not stored (kept for compatibility)
            dual_pdf_data: Not stored (kept for compatibility)
            metadata: Additional metadata
            
        Returns:
            Translation job ID if successful, None otherwise
        """
        if not self.is_connected():
            return None
        
        try:
            # Create translation document (metadata only)
            translation_doc = {
                "input_filename": input_filename,
                "language": language,
                "has_mono_pdf": mono_pdf_data is not None,
                "has_dual_pdf": dual_pdf_data is not None,
                "created_at": datetime.utcnow(),
                "status": "completed",
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
        Store solution generation metadata (no binary files)
        
        Args:
            input_file_data: Not stored (kept for compatibility)
            input_filename: Name of input file
            language: Target language
            docx_data: Not stored (kept for compatibility)
            json_data: Solution JSON data
            metadata: Additional metadata
            
        Returns:
            Solution job ID if successful, None otherwise
        """
        if not self.is_connected():
            return None
        
        try:
            # Create solution document (metadata only)
            solution_doc = {
                "input_filename": input_filename,
                "language": language,
                "has_docx": docx_data is not None,
                "json_data": json_data,
                "created_at": datetime.utcnow(),
                "status": "completed",
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
        Store MCQ generation metadata (no binary files)
        
        Args:
            topic: MCQ topic
            language: Target language
            num_questions: Number of questions
            mcq_data: MCQ data (list of questions)
            docx_data: Not stored (kept for compatibility)
            metadata: Additional metadata
            
        Returns:
            MCQ job ID if successful, None otherwise
        """
        if not self.is_connected():
            return None
        
        try:
            # Create MCQ document (metadata only)
            mcq_doc = {
                "topic": topic,
                "language": language,
                "num_questions": num_questions,
                "mcq_data": mcq_data,
                "has_docx": docx_data is not None,
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

