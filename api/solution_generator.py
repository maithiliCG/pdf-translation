"""
API endpoints for solution generation
"""
import io
import logging
import threading

from flask import Blueprint, request, jsonify

from modules.solution_generator import run_solution_generation_pipeline
from services.job_manager import job_manager

logger = logging.getLogger(__name__)

bp = Blueprint('solution_generator', __name__, url_prefix='/api/solution')


def process_solution_generation(job_id: str, file_data: bytes, filename: str, target_language: str):
    """Background processor for solution generation jobs."""
    import time
    
    try:
        # Initialize job start time
        job = job_manager.get_job(job_id)
        if job and job.get("job_start_time") is None:
            job_manager.update_job(job_id, status="processing", progress=0, message="Starting solution generation...", add_log_entry=False)
            with job_manager._lock:
                if job_id in job_manager._jobs:
                    job_manager._jobs[job_id]["job_start_time"] = time.time()
        
        job_manager.add_log(job_id, f"📄 PDF file received: {filename}", "info")
        job_manager.add_log(job_id, f"🌍 Target language: {target_language}", "info")
        job_manager.start_stage(job_id, "file_upload")
        job_manager.add_log(job_id, "📤 Uploading PDF...", "info")
        
        def status_callback(progress: int, message: str, status: str = "processing"):
            # Extract stage info from message
            if "extract" in message.lower() or "parsing" in message.lower():
                job_manager.start_stage(job_id, "extraction")
                job_manager.add_log(job_id, f"📖 {message}", "info")
            elif "solv" in message.lower():
                job_manager.start_stage(job_id, "solving")
                job_manager.add_log(job_id, f"🧮 {message}", "info")
            elif "translat" in message.lower():
                job_manager.start_stage(job_id, "translation")
                job_manager.add_log(job_id, f"🔄 {message}", "info")
            elif "generat" in message.lower() or "docx" in message.lower() or "word" in message.lower():
                job_manager.start_stage(job_id, "document_generation")
                job_manager.add_log(job_id, f"📝 {message}", "info")
            elif "complete" in message.lower():
                job_manager.add_log(job_id, f"✅ {message}", "success")
            else:
                job_manager.add_log(job_id, f"⚙️ {message}", "info")
            
            job_manager.update_job(job_id, progress=progress, message=message, status=status, add_log_entry=False)
        
        # Create file-like object from bytes
        file_obj = io.BytesIO(file_data)
        file_obj.name = filename
        
        result = run_solution_generation_pipeline(file_obj, target_language, status_callback, job_id=job_id)
        
        job_manager.add_log(job_id, "✅ Solution generation completed successfully!", "success")
        job_manager.update_job(
            job_id,
            status="completed",
            progress=100,
            message="Solution generation completed successfully!",
            result=result,
            add_log_entry=False
        )
    except Exception as e:
        logger.error(f"Solution generation job {job_id} failed: {e}", exc_info=True)
        job_manager.add_log(job_id, f"❌ Solution generation failed: {str(e)}", "error")
        job_manager.update_job(
            job_id,
            status="failed",
            message=f"Solution generation failed: {str(e)}",
            error=str(e),
            add_log_entry=False
        )


@bp.route('/generate', methods=['POST'])
def generate_solution():
    """Start a solution generation job."""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        target_language = request.form.get('target_language', 'Telugu')
        
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "File must be a PDF"}), 400
        
        # Read file data
        file_data = file.read()
        
        # Create job
        job_id = job_manager.create_job(
            job_type="solution_generation",
            metadata={
                "filename": file.filename,
                "target_language": target_language
            }
        )
        
        # Start background processing
        thread = threading.Thread(
            target=process_solution_generation,
            args=(job_id, file_data, file.filename, target_language),
            daemon=True
        )
        thread.start()
        
        return jsonify({
            "job_id": job_id,
            "status": "pending",
            "message": "Solution generation job created"
        }), 202
    
    except Exception as e:
        logger.error(f"Error creating solution generation job: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

