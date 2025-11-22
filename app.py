"""
Flask Application - AI Study Assistant
PDF Translator, Solution Generator, and MCQ Generator
"""
import logging
from pathlib import Path
from flask import Flask, render_template, jsonify, send_file, request
from flask_cors import CORS

from config.settings import LANGUAGES, GEMINI_API_KEY
import os
from services.job_manager import job_manager
from api.pdf_translator import bp as pdf_translator_bp
from api.solution_generator import bp as solution_generator_bp
from api.mcq_generator import bp as mcq_generator_bp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

# Enable CORS for React frontend integration
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Register blueprints
app.register_blueprint(pdf_translator_bp)
app.register_blueprint(solution_generator_bp)
app.register_blueprint(mcq_generator_bp)


@app.route('/')
def index():
    """Main page with UI."""
    return render_template('index.html')


@app.route('/jobs/<job_id>/status')
def job_status_page(job_id):
    """Job status page."""
    return render_template('job_status.html', job_id=job_id)


# API Routes

def serialize_for_json(obj):
    """Convert non-serializable objects to JSON-serializable format."""
    from pathlib import Path
    if isinstance(obj, Path):
        return str(obj)
    elif isinstance(obj, dict):
        return {key: serialize_for_json(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [serialize_for_json(item) for item in obj]
    elif hasattr(obj, 'isoformat'):  # datetime objects
        return obj.isoformat()
    else:
        return obj


@app.route('/api/jobs/<job_id>/status', methods=['GET'])
def get_job_status(job_id):
    """Get job status."""
    job = job_manager.get_job(job_id)
    
    if not job:
        return jsonify({"error": "Job not found"}), 404
    
    # Serialize job data to handle Path objects and datetime
    serialized_job = serialize_for_json({
        "job_id": job["job_id"],
        "type": job["type"],
        "status": job["status"],
        "progress": job["progress"],
        "message": job["message"],
        "result": job["result"],
        "error": job["error"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "logs": job.get("logs", []),  # Include process logs
        "debug_data": job.get("debug_data", {})  # Include debug data (extracted text, prompts, responses)
    })
    
    return jsonify(serialized_job)


@app.route('/api/jobs/<job_id>/download', methods=['GET'])
def download_job_result(job_id):
    """Download job result files."""
    job = job_manager.get_job(job_id)
    
    if not job:
        return jsonify({"error": "Job not found"}), 404
    
    if job["status"] != "completed":
        return jsonify({"error": "Job not completed yet"}), 400
    
    result = job.get("result")
    if not result:
        return jsonify({"error": "No result available"}), 404
    
    job_type = job["type"]
    download_type = request.args.get('type', 'default')
    
    try:
        if job_type == "pdf_translation":
            # PDF translation results - only monolingual PDF
            # Default to monolingual PDF (ignore dual/bilingual)
            file_path = result.get("mono_pdf_path") or result.get("dual_pdf_path")
            filename = f"translated_{result.get('lang_code', 'lang')}_mono.pdf"
            
            if file_path and os.path.exists(file_path):
                return send_file(
                    file_path,
                    mimetype='application/pdf',
                    as_attachment=True,
                    download_name=filename
                )
            else:
                return jsonify({"error": "File not found"}), 404
        
        elif job_type == "solution_generation":
            # Solution generation result
            file_path = result.get("final_docx")
            language = result.get("language", "unknown")
            filename = f"solutions_{language}.docx"
            
            if file_path and os.path.exists(file_path):
                return send_file(
                    file_path,
                    mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    as_attachment=True,
                    download_name=filename
                )
            else:
                return jsonify({"error": "File not found"}), 404
        
        elif job_type == "mcq_generation":
            # MCQ generation result
            file_path = result.get("docx_path")
            topic = result.get("topic", "MCQs")
            language = result.get("language", "English")
            filename = f"mcqs_{topic.replace(' ', '_')}_{language}.docx"
            
            if file_path and os.path.exists(file_path):
                return send_file(
                    file_path,
                    mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    as_attachment=True,
                    download_name=filename
                )
        else:
                return jsonify({"error": "File not found"}), 404
        
        return jsonify({"error": "Unknown job type"}), 400
    
    except Exception as e:
        logger.error(f"Error downloading file for job {job_id}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    """List all jobs (for debugging)."""
    job_type = request.args.get('type')
    limit = int(request.args.get('limit', 50))
    
    jobs = job_manager.list_jobs(job_type=job_type, limit=limit)
    
    return jsonify({
        "jobs": [
            {
                "job_id": j["job_id"],
                "type": j["type"],
                "status": j["status"],
                "progress": j["progress"],
                "message": j["message"],
                "created_at": j["created_at"].isoformat() if j["created_at"] else None,
                "updated_at": j["updated_at"].isoformat() if j["updated_at"] else None
            }
            for j in jobs
        ]
    })


@app.route('/api/languages', methods=['GET'])
def get_languages():
    """Get available languages."""
    return jsonify({
        "languages": LANGUAGES,
        "language_list": list(LANGUAGES.keys())
    })


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {error}", exc_info=True)
    return jsonify({"error": "Internal server error"}), 500


@app.before_request
def check_api_key():
    """Check if API key is configured (only on first request)."""
    if not hasattr(app, '_api_key_checked'):
        app._api_key_checked = True
        if not GEMINI_API_KEY:
            logger.warning(
                "⚠️ API Key Missing!\n\n"
                "Please add `GENAI_API_KEY` (or `GEMINI_API_KEY`) to your environment.\n\n"
                "For local development:\n"
                "1. Create a `.env` file in the project root\n"
                "2. Add: `GENAI_API_KEY=your_api_key_here`\n\n"
                "Get your API key from: https://makersuite.google.com/app/apikey"
            )


if __name__ == '__main__':
    # Check API key before starting
    if not GEMINI_API_KEY:
        print("WARNING: GEMINI_API_KEY not configured!")
        print("Please set GENAI_API_KEY in your environment or .env file")
        print("App will start but features may not work.")
    
    # Run Flask app
    print("Starting Flask server on http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
