"""
API endpoints for MCQ generation
"""
import logging
import threading

from flask import Blueprint, request, jsonify

from modules.mcq_generator import generate_mcqs, parse_mcqs, _iter_options
from modules.common import create_docx
from services.job_manager import job_manager

logger = logging.getLogger(__name__)

bp = Blueprint('mcq_generator', __name__, url_prefix='/api/mcq')


def process_mcq_generation(job_id: str, topic: str, num_questions: int, language: str):
    """Background processor for MCQ generation jobs."""
    import time
    import tempfile
    import os
    
    try:
        # Initialize job start time
        job = job_manager.get_job(job_id)
        if job and job.get("job_start_time") is None:
            job_manager.update_job(job_id, status="processing", progress=0, message="Starting MCQ generation...", add_log_entry=False)
            with job_manager._lock:
                if job_id in job_manager._jobs:
                    job_manager._jobs[job_id]["job_start_time"] = time.time()
        
        job_manager.add_log(job_id, f"📚 Topic: {topic}", "info")
        job_manager.add_log(job_id, f"❓ Generating {num_questions} MCQs in {language}", "info")
        job_manager.start_stage(job_id, "mcq_generation")
        job_manager.add_log(job_id, f"🔄 Generating {num_questions} MCQs on '{topic}' in {language}...", "info")
        job_manager.update_job(job_id, status="processing", progress=10, message=f"Generating {num_questions} MCQs in {language}...", add_log_entry=False)
        
        # Generate MCQs directly in target language
        raw = generate_mcqs(topic, num_questions, language)
        mcqs = parse_mcqs(raw) if raw else None
        
        if not mcqs:
            raise RuntimeError("Failed to parse MCQ output")
        
        job_manager.add_log(job_id, f"✅ Generated {len(mcqs)} MCQs successfully", "success")
        job_manager.update_job(job_id, progress=60, message="MCQs generated, formatting...", add_log_entry=False)
        
        # Normalize options format (convert to {label, text} format for all languages)
        normalized_mcqs = []
        for mcq in mcqs:
            normalized_options = []
            options = mcq.get("options", [])
            # Convert options to standardized format
            for letter, text in _iter_options(options):
                normalized_options.append({"label": letter, "text": text})
            normalized_mcq = {
                "question": mcq.get("question", ""),
                "options": normalized_options,
                "answer": mcq.get("correct_answer", ""),
                "explanation": mcq.get("explanation", "")
            }
            normalized_mcqs.append(normalized_mcq)
        
        mcqs = normalized_mcqs
        job_manager.start_stage(job_id, "docx_creation")
        job_manager.add_log(job_id, "📝 Formatting MCQs for document...", "info")
        job_manager.update_job(job_id, progress=80, message="Creating DOCX document...", add_log_entry=False)
        
        # Create DOCX content (unified path for all languages)
        docx_content = [f"MCQs on: {topic} ({language})", ""]
        
        for idx, item in enumerate(mcqs, start=1):
            docx_content.extend([
                f"Question {idx}: {item.get('question', '')}",
            ])
            for opt in item.get("options", []):
                docx_content.append(f"{opt['label']}. {opt['text']}")
            docx_content.extend([
                f"Correct Answer: {item.get('answer', '')}",
                f"Explanation: {item.get('explanation', '')}",
                "═══",
            ])
        
        # Generate DOCX
        docx_bytes = create_docx("\n".join(docx_content), f"MCQs - {topic} ({language})")
        
        # Save DOCX to a temporary location for download
        temp_dir = tempfile.gettempdir()
        docx_path = os.path.join(temp_dir, f"mcq_{job_id}.docx")
        if docx_bytes:
            with open(docx_path, "wb") as f:
                f.write(docx_bytes)
        
        job_manager.add_log(job_id, f"✅ DOCX document created ({len(docx_bytes)} bytes)", "success")
        
        # Prepare result
        result = {
            "topic": topic,
            "language": language,
            "num_questions": len(mcqs),
            "mcqs": mcqs,
            "docx_path": docx_path if docx_bytes else None,
            "docx_size": len(docx_bytes) if docx_bytes else 0
        }
        
        job_manager.add_log(job_id, f"✅ MCQ generation completed successfully! Generated {len(mcqs)} MCQs", "success")
        job_manager.update_job(
            job_id,
            status="completed",
            progress=100,
            message="MCQ generation completed successfully!",
            result=result,
            add_log_entry=False
        )
    except Exception as e:
        logger.error(f"MCQ generation job {job_id} failed: {e}", exc_info=True)
        job_manager.add_log(job_id, f"❌ MCQ generation failed: {str(e)}", "error")
        job_manager.update_job(
            job_id,
            status="failed",
            message=f"MCQ generation failed: {str(e)}",
            error=str(e),
            add_log_entry=False
        )


@bp.route('/generate', methods=['POST'])
def generate_mcq():
    """Start an MCQ generation job."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        topic = data.get('topic', '').strip()
        num_questions = int(data.get('num_questions', 5))
        language = data.get('language', 'English')
        
        if not topic:
            return jsonify({"error": "Topic is required"}), 400
        
        if num_questions < 1 or num_questions > 25:
            return jsonify({"error": "num_questions must be between 1 and 25"}), 400
        
        # Create job
        job_id = job_manager.create_job(
            job_type="mcq_generation",
            metadata={
                "topic": topic,
                "num_questions": num_questions,
                "language": language
            }
        )
        
        # Start background processing
        thread = threading.Thread(
            target=process_mcq_generation,
            args=(job_id, topic, num_questions, language),
            daemon=True
        )
        thread.start()
        
        return jsonify({
            "job_id": job_id,
            "status": "pending",
            "message": "MCQ generation job created"
        }), 202
    
    except Exception as e:
        logger.error(f"Error creating MCQ generation job: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

