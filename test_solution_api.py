"""
Test Solution Generator via API endpoint
Tests the solution generator API with a PDF file.
"""
import requests
import json
import time
from pathlib import Path

# Configuration
BASE_URL = "http://localhost:5000"
PDF_PATH = r"C:\surya work\AI-Eshwar anna translater\SBI CLERK PRELIMS (1).pdf"
TARGET_LANGUAGE = "Telugu"

def test_solution_generator_api():
    """Test solution generator via API."""
    print("=" * 60)
    print("TESTING SOLUTION GENERATOR VIA API")
    print("=" * 60)
    print(f"\nPDF: {Path(PDF_PATH).name}")
    print(f"Target Language: {TARGET_LANGUAGE}")
    print(f"API URL: {BASE_URL}\n")
    
    # Check if PDF exists
    if not Path(PDF_PATH).exists():
        print(f"❌ ERROR: PDF not found: {PDF_PATH}")
        return
    
    print("📤 Step 1: Uploading PDF and starting job...")
    print("-" * 60)
    
    # Prepare file upload
    with open(PDF_PATH, 'rb') as f:
        files = {'file': (Path(PDF_PATH).name, f, 'application/pdf')}
        data = {'target_language': TARGET_LANGUAGE}
        
        try:
            response = requests.post(
                f"{BASE_URL}/api/solution/generate",
                files=files,
                data=data,
                timeout=30
            )
            
            if response.status_code != 202:
                print(f"❌ ERROR: API returned {response.status_code}")
                print(f"Response: {response.text}")
                return
            
            result = response.json()
            job_id = result.get('job_id')
            print(f"✅ Job created: {job_id}")
            print(f"   Status: {result.get('status')}")
            print(f"   Message: {result.get('message')}\n")
            
        except requests.exceptions.RequestException as e:
            print(f"❌ ERROR: Failed to connect to API")
            print(f"   Error: {e}")
            print(f"\n   Make sure Flask server is running on {BASE_URL}")
            return
    
    print("📊 Step 2: Monitoring job status...")
    print("-" * 60)
    
    # Poll for job status
    max_wait_time = 300  # 5 minutes max
    start_time = time.time()
    last_status = None
    
    while True:
        elapsed = time.time() - start_time
        if elapsed > max_wait_time:
            print(f"\n⚠️  Timeout: Job taking longer than {max_wait_time}s")
            break
        
        try:
            response = requests.get(f"{BASE_URL}/api/jobs/{job_id}/status", timeout=10)
            if response.status_code != 200:
                print(f"❌ ERROR: Failed to get job status: {response.status_code}")
                break
            
            job = response.json()
            status = job.get('status')
            progress = job.get('progress', 0)
            message = job.get('message', '')
            
            # Print status updates
            if status != last_status:
                print(f"\n[{elapsed:.0f}s] Status: {status.upper()}")
                last_status = status
            
            # Print progress updates (only when it changes significantly)
            if progress and progress != job.get('last_progress', 0):
                print(f"   Progress: {progress}% - {message}")
                job['last_progress'] = progress
            
            # Check logs for detailed info
            logs = job.get('logs', [])
            if logs:
                last_log = logs[-1]
                log_message = last_log.get('message', '')
                if 'translat' in log_message.lower() or 'generat' in log_message.lower():
                    print(f"   📝 {log_message}")
            
            # Check if completed or failed
            if status == 'completed':
                print(f"\n✅ Job completed successfully!")
                print(f"   Total time: {elapsed:.1f}s")
                
                # Analyze result
                result = job.get('result', {})
                print(f"\n📊 Results:")
                print(f"   Language: {result.get('language', 'N/A')}")
                print(f"   Final DOCX: {result.get('final_docx', 'N/A')}")
                
                # Check sample questions
                sample = result.get('sample', [])
                if sample:
                    print(f"\n📝 Sample Questions (First 2):")
                    for idx, item in enumerate(sample[:2], 1):
                        print(f"\n   Question {idx}:")
                        print(f"      Number: {item.get('question_number', 'N/A')}")
                        print(f"      Section: {item.get('section', 'None')}")
                        print(f"      Method: {item.get('method', 'N/A')}")
                        
                        # Check translation
                        lang_lower = TARGET_LANGUAGE.lower()
                        has_translation = (
                            item.get(f'question_text_{lang_lower}') or
                            item.get(f'answer_{lang_lower}') or
                            item.get(f'explanation_{lang_lower}')
                        )
                        
                        if has_translation:
                            q_telugu = item.get(f'question_text_{lang_lower}', '')[:80]
                            a_telugu = item.get(f'answer_{lang_lower}', '')[:80]
                            print(f"      ✅ Translated Question: {q_telugu}...")
                            print(f"      ✅ Translated Answer: {a_telugu}...")
                        else:
                            print(f"      ⚠️  No translation fields found")
                        
                        # Check structure consistency
                        has_section = 'section' in item
                        print(f"      Section field: {'✅ Present' if has_section else '❌ Missing'}")
                
                print(f"\n🔗 View full results at: {BASE_URL}/jobs/{job_id}/status")
                print(f"📥 Download DOCX at: {BASE_URL}/api/jobs/{job_id}/download")
                break
                
            elif status == 'failed':
                error = job.get('error', 'Unknown error')
                print(f"\n❌ Job failed: {error}")
                break
            
            # Wait before next poll
            time.sleep(2)
            
        except requests.exceptions.RequestException as e:
            print(f"❌ ERROR: Failed to poll job status: {e}")
            break
    
    print("\n" + "=" * 60)
    print("TEST COMPLETED")
    print("=" * 60)

if __name__ == "__main__":
    test_solution_generator_api()

