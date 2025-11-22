"""
API endpoints for PDF translation
"""
import io
import logging
import threading
from pathlib import Path

from flask import Blueprint, request, jsonify, send_file

from modules.pdf_translator import translate_pdf_with_pdf2zh
from services.job_manager import job_manager

logger = logging.getLogger(__name__)

bp = Blueprint('pdf_translator', __name__, url_prefix='/api/pdf')


def process_pdf_translation(job_id: str, file_data: bytes, filename: str, target_language: str):
    """Background processor for PDF translation jobs."""
    import time
    stage_start_time = time.time()
    
    try:
        # Initialize job start time
        job = job_manager.get_job(job_id)
        if job and job.get("job_start_time") is None:
            import time
            job_manager.update_job(job_id, status="processing", progress=0, message="Starting translation...", add_log_entry=False)
            # Set job start time manually since we're in processing
            with job_manager._lock:
                if job_id in job_manager._jobs:
                    job_manager._jobs[job_id]["job_start_time"] = time.time()
        
        job_manager.add_log(job_id, f"📄 PDF file received: {filename}", "info")
        job_manager.add_log(job_id, f"🌍 Target language: {target_language}", "info")
        job_manager.start_stage(job_id, "file_upload")
        job_manager.add_log(job_id, "📤 Uploading and preparing PDF...", "info")
        
        def status_callback(progress: int, message: str, status: str = "processing"):
            # Extract stage name from message for better logging
            stage_name = message
            if "extract" in message.lower() or "parsing" in message.lower():
                job_manager.start_stage(job_id, "extraction")
                job_manager.add_log(job_id, f"📖 {message}", "info")
            elif "translat" in message.lower():
                job_manager.start_stage(job_id, "translation")
                job_manager.add_log(job_id, f"🔄 {message}", "info")
            elif "render" in message.lower() or "pdf" in message.lower() or "save" in message.lower():
                job_manager.start_stage(job_id, "rendering")
                job_manager.add_log(job_id, f"🎨 {message}", "info")
            elif "complete" in message.lower() or "finish" in message.lower():
                job_manager.add_log(job_id, f"✅ {message}", "success")
            else:
                job_manager.add_log(job_id, f"⚙️ {message}", "info")
            
            job_manager.update_job(job_id, progress=progress, message=message, status=status, add_log_entry=False)
        
        # Create file-like object from bytes
        file_obj = io.BytesIO(file_data)
        file_obj.name = filename
        
        result = translate_pdf_with_pdf2zh(file_obj, target_language, status_callback)
        
        job_manager.add_log(job_id, "✅ PDF translation completed successfully!", "success")
        job_manager.update_job(
            job_id,
            status="completed",
            progress=100,
            message="Translation completed successfully!",
            result=result,
            add_log_entry=False
        )
    except Exception as e:
        logger.error(f"PDF translation job {job_id} failed: {e}", exc_info=True)
        job_manager.add_log(job_id, f"❌ Translation failed: {str(e)}", "error")
        job_manager.update_job(
            job_id,
            status="failed",
            message=f"Translation failed: {str(e)}",
            error=str(e),
            add_log_entry=False
        )


@bp.route('/translate', methods=['POST'])
def translate_pdf():
    """Start a PDF translation job."""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        target_language = request.form.get('target_language', 'Hindi')
        
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "File must be a PDF"}), 400
        
        # Read file data
        file_data = file.read()
        
        # Create job
        job_id = job_manager.create_job(
            job_type="pdf_translation",
            metadata={
                "filename": file.filename,
                "target_language": target_language
            }
        )
        
        # Start background processing
        thread = threading.Thread(
            target=process_pdf_translation,
            args=(job_id, file_data, file.filename, target_language),
            daemon=True
        )
        thread.start()
        
        return jsonify({
            "job_id": job_id,
            "status": "pending",
            "message": "PDF translation job created"
        }), 202
    
    except Exception as e:
        logger.error(f"Error creating PDF translation job: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

