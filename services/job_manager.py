"""
Job Management Service
Thread-safe job status tracking for long-running operations
"""
import threading
import uuid
import time
from datetime import datetime
from typing import Dict, Optional, Any, List


class JobManager:
    """Thread-safe job status manager"""
    
    def __init__(self):
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
    
    def create_job(self, job_type: str, metadata: Optional[Dict] = None) -> str:
        """
        Create a new job and return its job_id.
        
        Args:
            job_type: Type of job ('pdf_translation', 'solution_generation', 'mcq_generation')
            metadata: Optional metadata to store with the job
        
        Returns:
            job_id: Unique job identifier
        """
        job_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        job = {
            "job_id": job_id,
            "type": job_type,
            "status": "pending",
            "progress": 0,
            "message": "Job created, waiting to start...",
            "created_at": now,
            "updated_at": now,
            "result": None,
            "error": None,
            "metadata": metadata or {},
            "logs": [],  # List of log entries with timestamps
            "stage_start_time": None,  # Track stage timing
            "job_start_time": None,  # Track job start time (set when processing starts)
            "debug_data": {}  # Store debug information (extracted text, prompts, responses)
        }
        
        with self._lock:
            self._jobs[job_id] = job
        
        return job_id
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get job status by job_id.
        
        Args:
            job_id: Job identifier
        
        Returns:
            Job dictionary or None if not found
        """
        with self._lock:
            return self._jobs.get(job_id)
    
    def add_log(self, job_id: str, log_message: str, log_type: str = "info") -> bool:
        """
        Add a log entry to the job.
        
        Args:
            job_id: Job identifier
            log_message: Log message
            log_type: Log type ('info', 'success', 'warning', 'error')
        
        Returns:
            True if log added, False if job not found
        """
        with self._lock:
            if job_id not in self._jobs:
                return False
            
            job = self._jobs[job_id]
            current_time = time.time()
            
            # Calculate elapsed time if stage started
            elapsed = None
            if job.get("stage_start_time"):
                elapsed = current_time - job["stage_start_time"]
                elapsed_str = f" ({elapsed:.1f}s)"
            else:
                elapsed_str = ""
            
            # Calculate time since job start
            if job.get("job_start_time") is None:
                job["job_start_time"] = current_time
            
            job_start = job.get("job_start_time", current_time)
            total_elapsed = current_time - job_start
            time_str = f"[{total_elapsed:.1f}s{elapsed_str}]" if elapsed_str else f"[{total_elapsed:.1f}s]"
            
            log_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "time": time_str,
                "message": log_message,
                "type": log_type,
                "elapsed": elapsed,
                "total_elapsed": total_elapsed
            }
            
            job["logs"].append(log_entry)
            
            # Keep only last 100 logs to prevent memory issues
            if len(job["logs"]) > 100:
                job["logs"] = job["logs"][-100:]
            
            job["updated_at"] = datetime.utcnow()
            
            return True
    
    def start_stage(self, job_id: str, stage_name: str) -> bool:
        """Start tracking a new stage."""
        with self._lock:
            if job_id not in self._jobs:
                return False
            job = self._jobs[job_id]
            current_time = time.time()
            
            # Set job start time on first stage if not set
            if job.get("job_start_time") is None:
                job["job_start_time"] = current_time
            
            # End previous stage if it exists
            if job.get("stage_start_time"):
                prev_stage_time = job["stage_start_time"]
                elapsed = current_time - prev_stage_time
                if elapsed > 0.1:  # Only log if stage took significant time
                    prev_stage_name = job.get("current_stage", "previous stage")
                    self._add_log_internal(job, f"✓ {prev_stage_name} completed in {elapsed:.1f}s", "success")
            
            # Start new stage
            job["stage_start_time"] = current_time
            job["current_stage"] = stage_name
            
            return True
    
    def update_job(
        self,
        job_id: str,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        result: Optional[Any] = None,
        error: Optional[str] = None,
        add_log_entry: bool = True
    ) -> bool:
        """
        Update job status.
        
        Args:
            job_id: Job identifier
            status: New status ('pending', 'processing', 'completed', 'failed')
            progress: Progress percentage (0-100)
            message: Status message
            result: Final result data
            error: Error message if failed
            add_log_entry: Whether to add message to logs
        
        Returns:
            True if job updated, False if job not found
        """
        with self._lock:
            if job_id not in self._jobs:
                return False
            
            job = self._jobs[job_id]
            
            if status is not None:
                job["status"] = status
            if progress is not None:
                job["progress"] = max(0, min(100, progress))
            if message is not None:
                job["message"] = message
                # Add to logs if enabled
                if add_log_entry and message:
                    self._add_log_internal(job, message, "info" if status != "failed" else "error")
            if result is not None:
                job["result"] = result
            if error is not None:
                job["error"] = error
                if error:
                    self._add_log_internal(job, f"Error: {error}", "error")
            
            job["updated_at"] = datetime.utcnow()
            
            return True
    
    def _add_log_internal(self, job: Dict, log_message: str, log_type: str = "info"):
        """Internal method to add log (assumes lock is already held)."""
        current_time = time.time()
        
        # Calculate elapsed time if stage started
        elapsed = None
        if job.get("stage_start_time"):
            elapsed = current_time - job["stage_start_time"]
            elapsed_str = f" ({elapsed:.1f}s)"
        else:
            elapsed_str = ""
        
        # Calculate time since job start
        if job.get("job_start_time") is None:
            job["job_start_time"] = current_time
        
        job_start = job.get("job_start_time", current_time)
        total_elapsed = current_time - job_start
        time_str = f"[{total_elapsed:.1f}s{elapsed_str}]" if elapsed_str else f"[{total_elapsed:.1f}s]"
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "time": time_str,
            "message": log_message,
            "type": log_type,
            "elapsed": elapsed,
            "total_elapsed": total_elapsed
        }
        
        job["logs"].append(log_entry)
        
        # Keep only last 100 logs to prevent memory issues
        if len(job["logs"]) > 100:
            job["logs"] = job["logs"][-100:]
    
    def set_debug_data(self, job_id: str, key: str, value: Any) -> bool:
        """
        Store debug data for a job (extracted text, prompts, responses).
        
        Args:
            job_id: Job identifier
            key: Debug data key (e.g., 'extracted_text', 'prompt_to_gemini', 'gemini_response')
            value: Debug data value (text, dict, etc.)
        
        Returns:
            True if debug data stored, False if job not found
        """
        with self._lock:
            if job_id not in self._jobs:
                return False
            
            job = self._jobs[job_id]
            if "debug_data" not in job:
                job["debug_data"] = {}
            
            job["debug_data"][key] = value
            job["updated_at"] = datetime.utcnow()
            
            return True
    
    def list_jobs(self, job_type: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        List jobs, optionally filtered by type.
        
        Args:
            job_type: Filter by job type (optional)
            limit: Maximum number of jobs to return
        
        Returns:
            List of job dictionaries
        """
        with self._lock:
            jobs = list(self._jobs.values())
            
            if job_type:
                jobs = [j for j in jobs if j["type"] == job_type]
            
            # Sort by created_at descending
            jobs.sort(key=lambda x: x["created_at"], reverse=True)
            
            return jobs[:limit]
    
    def delete_job(self, job_id: str) -> bool:
        """
        Delete a job from the manager.
        
        Args:
            job_id: Job identifier
        
        Returns:
            True if job deleted, False if not found
        """
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                return True
            return False


# Global job manager instance
job_manager = JobManager()

