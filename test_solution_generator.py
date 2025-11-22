"""
Test script for Solution Generator
Tests the solution generator with a specific PDF file and verifies output format and translation.
"""
import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from modules.solution_generator import run_solution_generation_pipeline


def test_status_callback(progress: int, message: str, status: str = "processing"):
    """Status callback for testing."""
    print(f"[{progress}%] {status.upper()}: {message}")


def test_solution_generator(pdf_path: str, target_language: str = "Telugu"):
    """Test the solution generator with a PDF file."""
    print("=" * 60)
    print(f"TESTING SOLUTION GENERATOR")
    print("=" * 60)
    print(f"\nPDF File: {pdf_path}")
    print(f"Target Language: {target_language}\n")
    
    # Check if file exists
    pdf_file_path = Path(pdf_path)
    if not pdf_file_path.exists():
        print(f"❌ ERROR: PDF file not found: {pdf_path}")
        return None
    
    print(f"✅ PDF file found: {pdf_file_path.name} ({pdf_file_path.stat().st_size / 1024:.1f} KB)\n")
    
    # Read PDF file
    with open(pdf_file_path, 'rb') as f:
        file_data = f.read()
    
    # Create file-like object
    import io
    file_obj = io.BytesIO(file_data)
    file_obj.name = pdf_file_path.name
    
    print("-" * 60)
    print("STARTING SOLUTION GENERATION PIPELINE")
    print("-" * 60)
    print()
    
    try:
        # Run pipeline
        result = run_solution_generation_pipeline(
            file_obj, 
            target_language, 
            test_status_callback
        )
        
        print("\n" + "=" * 60)
        print("PIPELINE COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print()
        
        # Analyze results
        print("📊 RESULTS ANALYSIS:")
        print("-" * 60)
        print(f"✅ Job Directory: {result.get('job_dir', 'N/A')}")
        print(f"✅ Language: {result.get('language', 'N/A')}")
        print(f"✅ Final DOCX: {result.get('final_docx', 'N/A')}")
        print(f"✅ Sample Items: {len(result.get('sample', []))} questions")
        print()
        
        # Check sample questions
        sample = result.get('sample', [])
        if sample:
            print("📝 SAMPLE QUESTIONS (First 3):")
            print("-" * 60)
            for idx, item in enumerate(sample[:3], 1):
                print(f"\nQuestion {idx}:")
                print(f"  Number: {item.get('question_number', 'N/A')}")
                print(f"  Section: {item.get('section', 'None')}")
                print(f"  Method: {item.get('method', 'N/A')}")
                
                # Check original fields
                q_text = item.get('question_text', '')[:100] if item.get('question_text') else 'N/A'
                print(f"  Original Question: {q_text}...")
                print(f"  Original Answer: {item.get('answer', 'N/A')[:100] if item.get('answer') else 'N/A'}...")
                
                # Check translated fields
                lang_lower = target_language.lower()
                q_text_translated = item.get(f'question_text_{lang_lower}', '')
                answer_translated = item.get(f'answer_{lang_lower}', '')
                explanation_translated = item.get(f'explanation_{lang_lower}', '')
                
                if q_text_translated:
                    print(f"  ✅ Translated Question ({target_language}): {q_text_translated[:100]}...")
                else:
                    print(f"  ⚠️  No translation found for question_text_{lang_lower}")
                
                if answer_translated:
                    print(f"  ✅ Translated Answer ({target_language}): {answer_translated[:100]}...")
                else:
                    print(f"  ⚠️  No translation found for answer_{lang_lower}")
                
                if explanation_translated:
                    print(f"  ✅ Translated Explanation ({target_language}): {explanation_translated[:100]}...")
                else:
                    print(f"  ⚠️  No translation found for explanation_{lang_lower}")
                
                # Check structure consistency
                required_fields = ['question_number', 'question_text', 'options', 'answer', 'explanation', 'method', 'section']
                missing_fields = [field for field in required_fields if field not in item]
                if missing_fields:
                    print(f"  ⚠️  Missing fields: {', '.join(missing_fields)}")
                else:
                    print(f"  ✅ All required fields present")
        
        # Check DOCX file
        docx_path = result.get('final_docx')
        if docx_path and Path(docx_path).exists():
            docx_size = Path(docx_path).stat().st_size
            print(f"\n✅ DOCX file generated: {Path(docx_path).name} ({docx_size / 1024:.1f} KB)")
        else:
            print(f"\n⚠️  DOCX file not found or not generated")
        
        # Check translation JSON
        translated_json_path = result.get('translated_json')
        if translated_json_path and Path(translated_json_path).exists():
            print(f"✅ Translation JSON: {Path(translated_json_path).name}")
            # Read and check translation JSON
            try:
                with open(translated_json_path, 'r', encoding='utf-8') as f:
                    translated_data = json.load(f)
                    total_items = len(translated_data) if isinstance(translated_data, list) else 0
                    print(f"   Total translated items: {total_items}")
                    
                    # Check if translations are present
                    lang_lower = target_language.lower()
                    translated_count = 0
                    for item in translated_data[:5]:  # Check first 5
                        if item.get(f'question_text_{lang_lower}') or item.get(f'answer_{lang_lower}'):
                            translated_count += 1
                    
                    if translated_count > 0:
                        print(f"   ✅ Translation fields present in sample: {translated_count}/5")
                    else:
                        print(f"   ⚠️  No translation fields found in sample")
            except Exception as e:
                print(f"   ⚠️  Error reading translation JSON: {e}")
        
        print("\n" + "=" * 60)
        print("✅ TEST COMPLETED!")
        print("=" * 60)
        
        return result
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    # Test with the specified PDF
    pdf_path = r"C:\surya work\AI-Eshwar anna translater\SBI CLERK PRELIMS (1).pdf"
    target_language = "Telugu"  # Change this to test different languages
    
    print("Testing with:")
    print(f"  PDF: {pdf_path}")
    print(f"  Language: {target_language}\n")
    
    result = test_solution_generator(pdf_path, target_language)
    
    if result:
        print("\n✅ Test passed! Check the output above for details.")
    else:
        print("\n❌ Test failed! Check the errors above.")

