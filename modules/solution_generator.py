"""
Solution Generator Module - PDF question solving and translation
"""
import json
import logging
import re
import uuid
from pathlib import Path

import fitz  # PyMuPDF
from sympy import Eq, solve, symbols

from config.settings import SOLUTION_JOBS_ROOT, PIPELINE_LABELS
from modules.common import (
    _call_generative_model,
    extract_json_block,
    extract_inner_json,
    _clean_text,
    _write_uploaded_file,
    create_docx,
)

logger = logging.getLogger(__name__)

JSON_SOLVER_CHAR_LIMIT = 50000
JSON_SOLVER_PROMPT_TEMPLATE = """
You are an expert MCQ solver.

Extract EVERY MCQ question from the document text EXACTLY as it appears (question number, wording, options).

{expected_clause}

STRICT RULES:
1. Return ONLY a valid JSON array. No headings, markdown, narration, or explanations outside JSON.
2. Include EVERY question. If the document has 35 MCQs, the array must contain 35 objects.
3. Each object must include question number, section (if available), question text, options array, the correct option label, the correct option text, and a short 2-3 sentence explanation.
4. The options array must contain objects with "label" and "text".
5. For the answer, provide both "correct_option" (label such as 1/2/3/4/5 or A/B/C/D) AND "answer_text" (the exact option text).
6. If sections/headings exist (e.g., "Numerical Ability"), include a "section" field; otherwise set it to null.
7. If a question number is missing in the PDF, assign a sequential string number yourself (\"31\", \"32\", ...).

OUTPUT FORMAT (MANDATORY):
[
  {{
    "question_number": "31",
    "section": "NUMERICAL ABILITY",
    "question_text": "...",
    "options": [
      {{"label": "1", "text": "..."}},
      {{"label": "2", "text": "..."}},
      {{"label": "3", "text": "..."}},
      {{"label": "4", "text": "..."}},
      {{"label": "5", "text": "..."}}
    ],
    "correct_option": "3",
    "answer_text": "13:14",
    "explanation": "2 concise sentences explaining the reasoning."
  }}
]

Document Text:
{document_text}

Return ONLY raw JSON. Do not add markdown fences.
"""


def _build_json_solver_prompt(document_text: str, expected_count: int | None) -> str:
    """Build the strict JSON solver prompt."""
    document_text = document_text.strip()
    expected_clause = (
        f"There are exactly {expected_count} MCQ questions in this document. The JSON array MUST contain {expected_count} objects."
        if expected_count
        else "Cover EVERY MCQ question that appears in the document. Do not skip any."
    )
    return JSON_SOLVER_PROMPT_TEMPLATE.format(
        expected_clause=expected_clause,
        document_text=document_text,
    )


def _parse_json_solver_output(raw_text: str) -> list:
    """Parse JSON array from model response with robust error handling."""
    if not raw_text:
        raise ValueError("Empty response from solver")
    
    # Try to extract and clean JSON
    # First, try extract_inner_json (looks for ```json blocks)
    parsed = extract_inner_json(raw_text)
    if parsed and isinstance(parsed, list):
        return parsed
    
    # Second, try extract_json_block (more flexible extraction)
    try:
        json_block = extract_json_block(raw_text)
        if json_block:
            # Clean common LLM JSON issues before parsing
            json_block = _sanitize_json_string(json_block)
            parsed = json.loads(json_block)
            if isinstance(parsed, list):
                return parsed
    except json.JSONDecodeError as e:
        logger.warning(f"JSON decode failed after sanitization: {e}")
    
    # Third, try to find JSON array directly in text
    try:
        # Look for [ ... ] pattern
        start_idx = raw_text.find('[')
        end_idx = raw_text.rfind(']')
        if start_idx >= 0 and end_idx > start_idx:
            json_str = raw_text[start_idx:end_idx+1]
            json_str = _sanitize_json_string(json_str)
            parsed = json.loads(json_str)
            if isinstance(parsed, list):
                return parsed
    except (json.JSONDecodeError, ValueError) as e:
        # Show detailed error for diagnosis
        preview = raw_text[:1000] if len(raw_text) > 1000 else raw_text
        error_msg = (
            f"JSON parsing failed: {e}\n\n"
            f"Response length: {len(raw_text)} characters\n"
            f"Response preview (first 1000 chars):\n{preview}\n\n"
            f"This is likely a Gemini formatting issue - check debug_data.gemini_response for full response"
        )
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    # If we got here, none of the methods worked
    preview = raw_text[:1000] if len(raw_text) > 1000 else raw_text
    error_msg = (
        f"Could not parse valid JSON array from solver output\n\n"
        f"Response length: {len(raw_text)} characters\n"
        f"Response preview (first 1000 chars):\n{preview}\n\n"
        f"Check debug_data.gemini_response for full Gemini output"
    )
    raise ValueError(error_msg)


def _sanitize_json_string(json_str: str) -> str:
    """Clean common JSON issues from LLM output."""
    if not json_str:
        return json_str
    
    # Remove markdown code fences if present
    json_str = re.sub(r'```json\s*', '', json_str, flags=re.IGNORECASE)
    json_str = re.sub(r'```\s*$', '', json_str)
    
    # Replace control characters in strings (but not structural newlines)
    # This is tricky - we want to keep JSON structure but clean string values
    # Simple approach: replace problematic control chars with spaces
    json_str = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]', ' ', json_str)
    
    # Fix common trailing comma issues (before ] or })
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
    
    return json_str.strip()


def _normalize_options(options):
    """Normalize options from solver output into [{'label','text'}]."""
    normalized = []
    if not isinstance(options, list):
        return normalized
    for opt in options:
        label = ""
        text = ""
        if isinstance(opt, dict):
            label = opt.get("label") or opt.get("option") or opt.get("id") or opt.get("value_label")
            text = opt.get("text") or opt.get("value") or opt.get("option_text")
        elif isinstance(opt, str):
            match = re.match(r"(\d+|[A-Ea-e])\)?\s*[:.)-]?\s*(.+)", opt.strip())
            if match:
                label = match.group(1)
                text = match.group(2)
        if label:
            normalized.append(
                {
                    "label": str(label).strip(),
                    "text": _clean_text(text),
                }
            )
    return normalized


def _normalize_json_solver_items(raw_items: list, answer_key: dict | None) -> list:
    """Convert solver JSON array into internal question objects."""
    normalized_results = []
    for idx, item in enumerate(raw_items, start=1):
        item = item or {}
        qnum = item.get("question_number") or idx
        qnum_str = str(qnum).strip()
        question_text = _clean_text(item.get("question_text") or item.get("question") or "")
        options = _normalize_options(item.get("options") or [])
        answer_option = str(item.get("answer_option") or item.get("correct_option") or "").strip()
        answer_text = _clean_text(item.get("answer_text") or item.get("answer") or "")
        explanation = _clean_text(item.get("explanation") or item.get("solution") or "")
        section = item.get("section")
        if isinstance(section, str):
            section = section.strip() or None
        else:
            section = None

        if not answer_option and options and answer_text:
            # Try to map answer text to option label
            for opt in options:
                if answer_text.lower().strip() == opt["text"].lower().strip():
                    answer_option = opt["label"]
                    break

        if not answer_text and answer_option and options:
            match_opt = next((opt for opt in options if str(opt["label"]) == str(answer_option)), None)
            if match_opt:
                answer_text = match_opt["text"]

        # Override with answer key if available
        try:
            qnum_int = int(qnum_str)
        except (TypeError, ValueError):
            qnum_int = None
        used_answer_key = False
        if qnum_int is not None and answer_key:
            key_opt = answer_key.get(qnum_int)
            if key_opt:
                used_answer_key = True
                answer_option = str(key_opt)
                match_opt = next((opt for opt in options if str(opt["label"]) == str(answer_option)), None)
                if match_opt:
                    answer_text = match_opt["text"]
                else:
                    answer_text = f"Option {answer_option}"

        if used_answer_key and answer_text and not explanation:
            explanation = _generate_llm_explanation(question_text, answer_text)

        answer_value = answer_text or ""
        if answer_option and answer_text:
            answer_value = f"{answer_option}) {answer_text}" if ")" not in answer_text else answer_text

        normalized_results.append(
            {
                "question_number": qnum_str,
                "question_text": question_text,
                "question_body": question_text,
                "options": options,
                "answer": answer_value,
                "answer_option": answer_option or None,
                "explanation": explanation,
                "method": "llm_json",
                "section": section,
            }
        )
    return normalized_results


def _format_questions_for_solver(question_blocks: list) -> str:
    """Build clean question text (Qx / options) for the solver prompt."""
    lines: list[str] = []
    for idx, block in enumerate(question_blocks, start=1):
        qnum = block.get("question_number") or idx
        
        # Use raw_block if question_text seems incomplete (too short)
        qtext = block.get("question_text", "").strip()
        raw_block = block.get("raw_block", "").strip()
        
        # If question_text is missing or seems truncated, use raw_block
        # Check if raw_block contains more complete text
        if not qtext or (raw_block and len(raw_block) > len(qtext) + 50):
            # Extract question text from raw_block (everything before first option)
            option_pattern = re.compile(r'(?m)^\s*([1-5])[\)\.]\s*', re.MULTILINE)
            first_option_match = option_pattern.search(raw_block)
            if first_option_match:
                qtext = raw_block[:first_option_match.start()].strip()
            else:
                # No options found, use raw_block but stop at next question or KEY
                next_q_match = re.search(r'^\s*\d{2,3}[\.)]|KEY', raw_block, re.MULTILINE)
                if next_q_match:
                    qtext = raw_block[:next_q_match.start()].strip()
                else:
                    qtext = raw_block
        
        qtext = _clean_text(qtext)
        if not qtext:
            continue
        
        lines.append(f"Question {qnum}: {qtext}")
        
        options = block.get("options") or []
        if options:
            lines.append("Options:")
            for opt in options:
                label = opt.get("label", "").strip()
                text = _clean_text(opt.get("text", "")).strip()
                if label and text:
                    lines.append(f"  {label}) {text}")
        else:
            # Try to extract options from raw_block if not found in block
            if raw_block:
                option_pattern = re.compile(r'(?m)^\s*([1-5])[\)\.]\s*(.+?)(?=\n\s*[1-5][\)\.]\s*|$|\n\s*\d{2,3}[\.)]|KEY)', re.MULTILINE)
                opt_matches = list(option_pattern.finditer(raw_block))
                if opt_matches:
                    lines.append("Options:")
                    for opt_match in opt_matches:
                        label = opt_match.group(1).strip()
                        text = _clean_text(opt_match.group(2).strip())
                        if label and text:
                            lines.append(f"  {label}) {text}")
        
        lines.append("")  # Empty line between questions
    return "\n".join(lines).strip()


def _solve_questions_with_json_prompt(
    solver_input_text: str,
    expected_count: int | None,
    expected_numbers: list[str] | None,
    answer_key: dict,
    progress_callback=None,
    job_id: str = None,
) -> list:
    """Call Gemini with strict JSON prompt and normalize the result. Single attempt only."""
    from services.job_manager import job_manager
    
    if not solver_input_text.strip():
        return []

    truncated_text = solver_input_text[:JSON_SOLVER_CHAR_LIMIT]

    prompt = _build_json_solver_prompt(truncated_text, expected_count)
    
    # Store prompt sent to Gemini
    if job_id:
        job_manager.set_debug_data(job_id, "gemini_prompt", prompt)
        job_manager.add_log(job_id, "🤖 Sending prompt to Gemini", "info")
    
    try:
        response = _call_generative_model(prompt)
        raw_text = (response.text or "").strip()
        
        # Store raw response from Gemini
        if job_id:
            job_manager.set_debug_data(job_id, "gemini_response", raw_text)
            job_manager.add_log(job_id, f"✅ Received response from Gemini ({len(raw_text)} characters)", "info")
        
        parsed_items = _parse_json_solver_output(raw_text)
        
        # Store parsed response
        if job_id:
            job_manager.set_debug_data(job_id, "gemini_parsed_response", parsed_items)
            job_manager.add_log(job_id, f"📊 Parsed {len(parsed_items)} questions from response", "info")

        normalized = _normalize_json_solver_items(parsed_items, answer_key)

        # Log coverage information (no validation, just info)
        if expected_count and job_id:
            coverage_percent = (len(normalized) / expected_count) * 100
            job_manager.add_log(job_id, f"📊 Coverage: {len(normalized)}/{expected_count} questions ({coverage_percent:.1f}%)", "info")

        # Log missing question numbers if any (no validation, just info)
        if expected_numbers and job_id:
            normalized_numbers = {
                str(item.get("question_number", "")).strip()
                for item in normalized
                if item.get("question_number")
            }
            missing_numbers = [
                num for num in expected_numbers if str(num).strip() not in normalized_numbers
            ]
            if missing_numbers:
                job_manager.add_log(job_id, f"ℹ️ Missing question numbers: {', '.join(map(str, missing_numbers))}", "info")

        if progress_callback:
            progress_callback(100, 100)

        return normalized

    except Exception as exc:
        error_message = f"JSON solver failed: {str(exc)}"
        logger.error(error_message)
        if job_id:
            job_manager.add_log(job_id, f"❌ {error_message}", "error")
        raise RuntimeError(error_message)

def _pipeline_extract_pdf(input_pdf_path: Path, job_dir: Path):
    """Extract text and images from PDF."""
    images_dir = job_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    extracted_json = job_dir / "extracted_data.json"

    doc = fitz.open(str(input_pdf_path))
    pages_data = []

    for page_number, page in enumerate(doc, start=1):
        text = page.get_text() or ""
        images = []
        for img_index, img in enumerate(page.get_images(full=True), start=1):
            xref = img[0]
            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.n > 4:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                image_path = images_dir / f"page{page_number}_img{img_index}.png"
                pix.save(image_path)
                images.append(str(image_path))
            except Exception:
                continue
        pages_data.append({"page": page_number, "text": text.strip(), "images": images})

    with extracted_json.open("w", encoding="utf-8") as f:
        json.dump(pages_data, f, ensure_ascii=False, indent=2)

    return pages_data, extracted_json


def _extract_answer_key_from_text(full_text: str) -> tuple[dict[int, str], int | None]:
    """Extract answer key from text."""
    if not full_text:
        return {}, None
    match = re.search(r"\bKEY\b", full_text, flags=re.IGNORECASE)
    if not match:
        return {}, None
    key_section = full_text[match.end() :]
    pairs = re.findall(r"(\d{1,3})\s*[.\-]\s*(\d)", key_section)
    key_map = {}
    for question, option_digit in pairs:
        try:
            key_map[int(question)] = option_digit
        except ValueError:
            continue
    return key_map, match.start()


def _extract_batch_text_from_raw(full_text: str, batch_blocks: list, first_qnum: str, last_qnum: str) -> str:
    """Extract the raw text portion corresponding to a batch of questions."""
    if not batch_blocks:
        return ""
    
    # Find the start position of the first question in the batch
    first_block = batch_blocks[0]
    first_raw = first_block.get("raw_block", "")
    
    # Try to find the first question number in the full text
    start_pos = 0
    if first_qnum:
        # Look for question number pattern (e.g., "31.", "31)", "31 ")
        patterns = [
            rf"\b{re.escape(first_qnum)}\.",
            rf"\b{re.escape(first_qnum)}\)",
            rf"\b{re.escape(first_qnum)}\s",
        ]
        for pattern in patterns:
            match = re.search(pattern, full_text)
            if match:
                start_pos = match.start()
                break
    
    # Find the end position - look for the next question after the last one
    end_pos = len(full_text)
    if len(batch_blocks) > 0 and last_qnum:
        # Try to find the question after the last one in the batch
        next_qnum = None
        try:
            last_qnum_int = int(last_qnum)
            next_qnum = str(last_qnum_int + 1)
        except (ValueError, TypeError):
            pass
        
        if next_qnum:
            patterns = [
                rf"\b{re.escape(next_qnum)}\.",
                rf"\b{re.escape(next_qnum)}\)",
                rf"\b{re.escape(next_qnum)}\s",
            ]
            # Search in the remaining text after start_pos
            remaining_text = full_text[start_pos + 1:]
            for pattern in patterns:
                match = re.search(pattern, remaining_text)
                if match:
                    # Adjust position back to original text coordinates
                    end_pos = start_pos + 1 + match.start()
                    break
    
    # Extract the batch text
    batch_text = full_text[start_pos:end_pos].strip()
    
    # If extraction is too short, use the raw blocks combined
    if len(batch_text) < 100:
        # Fallback: combine raw blocks
        batch_text = "\n\n".join(block.get("raw_block", "") for block in batch_blocks if block.get("raw_block"))
    
    return batch_text


def _segment_questions_from_text(full_text: str):
    """Segment questions from text."""
    if not full_text:
        return []

    # Question pattern: Questions are numbered 31-99+ (2+ digits) at start of line
    # Options are numbered 1-5 (single digit) at start of line
    # Look for question numbers that are >= 10 to avoid matching option numbers
    question_pattern = re.compile(
        r"(?sm)^\s*(\d{2,3})[\.)]\s*(.*?)(?=^\s*\d{2,3}[\.)]\s*|$)"
    )
    
    # Option pattern: Single digit (1-5) at start of line, followed by ) or .
    # This should NOT match at start of line when followed by more digits
    option_pattern = re.compile(r"(?m)^\s*([1-5])[\)\.]\s*(.+?)(?=\n\s*[1-5][\)\.]\s*|$|\n\s*\d{2,3}[\.)]|KEY)", re.MULTILINE)

    blocks = []
    for match in question_pattern.finditer(full_text):
        number = match.group(1).strip()
        raw_block = match.group(2).strip()
        if not raw_block:
            continue

        # Try to find options - look for single digit options (1-5) that are NOT question numbers
        option_matches = list(option_pattern.finditer(raw_block))
        
        # Filter out any matches that are actually question numbers (>= 10)
        filtered_option_matches = []
        for opt_match in option_matches:
            opt_num = opt_match.group(1).strip()
            # Only accept options that are single digit (1-5)
            if opt_num.isdigit() and 1 <= int(opt_num) <= 5:
                # Make sure this isn't part of a larger number
                start_pos = opt_match.start()
                if start_pos == 0 or not raw_block[start_pos - 1].isdigit():
                    filtered_option_matches.append(opt_match)
        
        option_matches = filtered_option_matches
        
        # If still no options, try alternative pattern: "(1) text (2) text"
        if not option_matches:
            option_pattern2 = re.compile(r'\(([1-5])\)\s*(.+?)(?=\([1-5]\)|$|\n\s*\d{2,3}[\.)]|KEY)', re.MULTILINE)
            option_matches = list(option_pattern2.finditer(raw_block))
        
        if option_matches:
            first_option_start = option_matches[0].start()
            question_prompt = raw_block[:first_option_start].strip()
        else:
            # No options found - use entire block as question text (up to next question or KEY)
            # Stop at next question number or KEY
            next_question_match = re.search(r'^\s*\d{2,3}[\.)]|KEY', raw_block, re.MULTILINE)
            if next_question_match:
                question_prompt = raw_block[:next_question_match.start()].strip()
            else:
                question_prompt = raw_block.strip()

        options = [
            {"label": opt.group(1).strip(), "text": opt.group(2).strip()}
            for opt in option_matches
        ]

        blocks.append(
            {
                "question_number": number,
                "question_text": question_prompt,
                "options": options,
                "raw_block": raw_block,  # Always preserve full raw block
            }
        )

    return blocks


def _solve_simple_equation(text: str):
    """Solve simple equations using SymPy."""
    if not text:
        return None
    x = symbols("x")
    try:
        cleaned = re.sub(r"[^\dxX\+\-\*/=\.\(\)\s]", "", text).replace("X", "x")
        if "=" not in cleaned:
            return None
        lhs, rhs = cleaned.split("=", 1)
        lhs = re.sub(r"(?<=\d)x", "*x", lhs)
        rhs = re.sub(r"(?<=\d)x", "*x", rhs)
        equation = Eq(eval(lhs), eval(rhs))
        solution = solve(equation, x)
        return solution
    except Exception:
        return None


def _generate_llm_explanation(question_text: str, answer_text: str) -> str:
    """Generate explanation using LLM."""
    if not question_text or not answer_text:
        return "Explanation unavailable."
    prompt = f"""
You are a helpful math tutor. Assume the provided answer is correct and describe,
in 2-3 sentences, the logical steps a student would take to reach it. Focus on the
method (e.g., compare totals, apply ratios, plug values into the formula).
Do NOT mention missing information, inconsistencies, or answer keys. Keep the tone confident.

QUESTION:
{question_text}

CORRECT ANSWER:
{answer_text}
"""
    try:
        response = _call_generative_model(prompt)
        return (response.text or "").strip()
    except Exception as exc:
        return f"Explanation unavailable ({exc})."


def _pipeline_solve_pages(pages, job_dir: Path, progress_callback=None, job_id: str = None):
    """Solve questions from PDF pages."""
    from services.job_manager import job_manager
    
    combined_text = "\n".join(page.get("text", "") for page in pages if page.get("text"))
    
    # Store extracted PDF text
    if job_id:
        job_manager.set_debug_data(job_id, "extracted_pdf_text", combined_text)
        job_manager.add_log(job_id, f"📝 Extracted {len(combined_text)} characters from PDF", "info")
    
    answer_key, key_start = _extract_answer_key_from_text(combined_text)
    questions_text = combined_text if key_start is None else combined_text[:key_start]
    
    # Store questions text (after removing answer key)
    if job_id:
        job_manager.set_debug_data(job_id, "questions_text_after_key_removal", questions_text)
        job_manager.set_debug_data(job_id, "answer_key", answer_key)
        job_manager.add_log(job_id, f"🔑 Answer key found: {len(answer_key)} questions", "info")
        job_manager.add_log(job_id, f"📋 Questions text length: {len(questions_text)} characters", "info")
    
    question_blocks = _segment_questions_from_text(questions_text)
    expected_count = len(question_blocks) or None
    expected_numbers = (
        [block.get("question_number") or str(idx) for idx, block in enumerate(question_blocks, start=1)]
        if question_blocks
        else None
    )
    
    # Store segmented question blocks metadata (for reference only)
    if job_id:
        job_manager.set_debug_data(job_id, "segmented_question_blocks_count", len(question_blocks))
        job_manager.add_log(job_id, f"📊 Found {len(question_blocks)} questions in text", "info")
    
    # BATCH PROCESSING: Split into batches of 10 questions to avoid incomplete JSON from Gemini
    # Gemini sometimes produces incomplete JSON when response is too long (18K+ chars)
    BATCH_SIZE = 10
    all_results = []
    
    if question_blocks and len(question_blocks) > 0:
        total_questions = len(question_blocks)
        num_batches = (total_questions + BATCH_SIZE - 1) // BATCH_SIZE
        
        if job_id:
            job_manager.add_log(job_id, f"🔄 Processing {total_questions} questions in {num_batches} batches (batch size: {BATCH_SIZE})", "info")
        
        for batch_idx in range(num_batches):
            start_idx = batch_idx * BATCH_SIZE
            end_idx = min(start_idx + BATCH_SIZE, total_questions)
            batch_blocks = question_blocks[start_idx:end_idx]
            
            if job_id:
                batch_numbers = [block.get("question_number", str(start_idx + i + 1)) for i, block in enumerate(batch_blocks)]
                job_manager.add_log(job_id, f"📦 Processing batch {batch_idx + 1}/{num_batches}: Questions {batch_numbers[0]}-{batch_numbers[-1]}", "info")
            
            # Extract RAW text for this batch from questions_text
            # Find the position of first question in this batch
            first_qnum = batch_blocks[0].get("question_number", "")
            first_qnum_str = str(first_qnum) if first_qnum else ""
            
            # Find the position of last question in this batch
            last_qnum = batch_blocks[-1].get("question_number", "")
            last_qnum_str = str(last_qnum) if last_qnum else ""
            
            # Extract batch text by finding question boundaries in raw text
            batch_text = _extract_batch_text_from_raw(questions_text, batch_blocks, first_qnum_str, last_qnum_str)
            
            if job_id:
                job_manager.add_log(job_id, f"📤 Sending batch {batch_idx + 1} to Gemini: {len(batch_text)} characters (RAW, NO MODIFICATIONS)", "info")
            
            # Solve this batch
            batch_expected_count = len(batch_blocks)
            batch_expected_numbers = [block.get("question_number") or str(start_idx + i + 1) for i, block in enumerate(batch_blocks)]
            
            try:
                batch_results = _solve_questions_with_json_prompt(
                    batch_text,
                    batch_expected_count,
                    batch_expected_numbers,
                    answer_key or {},
                    progress_callback=None,  # Don't pass main callback for batches
                    job_id=job_id,
                )
                
                if batch_results:
                    all_results.extend(batch_results)
                    if job_id:
                        job_manager.add_log(job_id, f"✅ Batch {batch_idx + 1} completed: {len(batch_results)} questions solved", "success")
                else:
                    if job_id:
                        job_manager.add_log(job_id, f"⚠️ Batch {batch_idx + 1} returned no results", "warning")
            
            except Exception as exc:
                logger.error(f"Batch {batch_idx + 1} failed: {exc}")
                if job_id:
                    job_manager.add_log(job_id, f"❌ Batch {batch_idx + 1} failed: {str(exc)}", "error")
                # Continue with other batches even if one fails
    
    else:
        # Fallback: if no question blocks found, send entire text as one batch
        if job_id:
            job_manager.add_log(job_id, f"⚠️ No question blocks found, sending entire text as single batch", "warning")
        
        try:
            all_results = _solve_questions_with_json_prompt(
                questions_text,
                expected_count,
                expected_numbers,
                answer_key or {},
                progress_callback=progress_callback,
                job_id=job_id,
            ) or []
        except Exception as exc:
            logger.error(f"Single batch processing failed: {exc}")
            if job_id:
                job_manager.add_log(job_id, f"❌ Single batch failed: {str(exc)}", "error")
            all_results = []
    
    if all_results:
        if job_id:
            job_manager.add_log(job_id, f"✅ All batches completed: {len(all_results)} total questions solved", "success")
        solved_file = job_dir / "solved_extracted_data.json"
        with solved_file.open("w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        return all_results, solved_file
    else:
        raise RuntimeError("JSON solver returned no results from any batch")


def _pipeline_translate_items(items, target_language: str, job_dir: Path, progress_callback=None):
    """Translate solved items to target language."""
    lang_lower = target_language.lower()
    translated_path = job_dir / f"translated_{lang_lower}_auto.json"
    translated = []
    total = len(items) or 1
    processed = 0
    batch_size = 5

    # Build formatted content for translation
    formatted_content_parts = []
    for item in items:
        qnum = item.get("question_number", "")
        q = item.get("question_body", item.get("question_text", ""))
        options = item.get("options", [])
        a = item.get("answer", "")
        e = item.get("explanation", "")
        
        # Build formatted content
        content_lines = []
        if qnum:
            content_lines.append(f"Q{qnum}: {q}")
        else:
            content_lines.append(f"Q: {q}")
        
        if options:
            opt_text = " | ".join([f"{opt.get('label', '')}) {opt.get('text', '')}" for opt in options])
            content_lines.append(f"Options: {opt_text}")
        
        if a:
            content_lines.append(f"✅ Answer: {a}")
        
        if e:
            content_lines.append(f"📝 Solution: {e}")
        
        content_lines.append("═══")
        formatted_content_parts.append("\n".join(content_lines))
    
    # Combine all content
    full_content = "\n\n".join(formatted_content_parts)
    
    # Translate in chunks if content is too long
    char_limit = 40000
    if len(full_content) <= char_limit:
        # Translate all at once
        prompt = f"""
Translate the following MCQ solutions to {target_language}.

**CRITICAL INSTRUCTIONS:**

1. Maintain ALL formatting: separators (═══), question numbers, structure

2. Translate question text, options, and explanations

3. Keep mathematical symbols, numbers, and formulas as-is

4. Keep "Q[Number]:", "Options:", "✅ Answer:", "📝 Solution:" labels

5. Ensure natural, fluent translation in {target_language}

6. Preserve line breaks and spacing

**Content to translate:**

{full_content}

**Provide ONLY the translated content, maintaining exact structure.**
"""
        try:
            if progress_callback:
                progress_callback(0, total)
            response = _call_generative_model(prompt)
            translated_text = response.text.strip()
            
            # Parse translated text back into items
            translated = _parse_translated_content(translated_text, items, lang_lower)
            if progress_callback:
                progress_callback(len(items), total)
        except Exception as exc:
            # Fallback to individual item translation
            translated = _translate_items_individually(items, target_language, lang_lower)
            if progress_callback:
                progress_callback(len(items), total)
    else:
        # Translate in batches
        translated = []
        for batch_start in range(0, len(items), batch_size):
            batch = items[batch_start : batch_start + batch_size]
            batch_content_parts = []
            for item in batch:
                qnum = item.get('question_number', '')
                qbody = item.get('question_body', item.get('question_text', ''))
                options = item.get('options', [])
                answer = item.get('answer', '')
                explanation = item.get('explanation', '')
                
                # Build options string
                if options:
                    opt_parts = []
                    for opt in options:
                        opt_label = opt.get('label', '')
                        opt_text = opt.get('text', '')
                        opt_parts.append(f"{opt_label}) {opt_text}")
                    options_str = " | ".join(opt_parts)
                else:
                    options_str = ""
                
                # Build formatted content for this item
                item_content = f"Q{qnum}: {qbody}\n"
                if options_str:
                    item_content += f"Options: {options_str}\n"
                if answer:
                    item_content += f"✅ Answer: {answer}\n"
                if explanation:
                    item_content += f"📝 Solution: {explanation}\n"
                item_content += "═══"
                batch_content_parts.append(item_content)
            
            batch_content = "\n\n".join(batch_content_parts)
            
            # Check if batch content exceeds limit - if so, split into smaller chunks
            if len(batch_content) > char_limit:
                # Batch too large - translate items individually to avoid truncation
                logger.warning(f"Batch size ({len(batch_content)} chars) exceeds limit ({char_limit}). Translating items individually.")
                batch_translated = _translate_items_individually(batch, target_language, lang_lower)
                translated.extend(batch_translated)
            else:
                # Batch fits within limit - translate together
                prompt = f"""
Translate the following MCQ solutions to {target_language}.

**CRITICAL INSTRUCTIONS:**

1. Maintain ALL formatting: separators (═══), question numbers, structure

2. Translate question text, options, and explanations

3. Keep mathematical symbols, numbers, and formulas as-is

4. Keep "Q[Number]:", "Options:", "✅ Answer:", "📝 Solution:" labels

5. Ensure natural, fluent translation in {target_language}

6. Preserve line breaks and spacing

7. Translate ALL questions in the batch - do not skip any

**Content to translate:**

{batch_content}

**Provide ONLY the translated content, maintaining exact structure.**
"""
                try:
                    response = _call_generative_model(prompt)
                    translated_text = response.text.strip()
                    batch_translated = _parse_translated_content(translated_text, batch, lang_lower)
                    
                    # Safety check: Ensure all items from batch are included
                    if len(batch_translated) < len(batch):
                        logger.warning(f"Translation returned {len(batch_translated)} items but batch had {len(batch)} items. Filling missing items.")
                        # Add missing items using individual translation
                        missing_indices = [i for i in range(len(batch)) if i >= len(batch_translated)]
                        for idx in missing_indices:
                            individual_translated = _translate_items_individually([batch[idx]], target_language, lang_lower)
                            if individual_translated:
                                batch_translated.extend(individual_translated)
                    
                    translated.extend(batch_translated)
                except Exception as exc:
                    logger.error(f"Batch translation failed: {exc}. Falling back to individual translation.")
                    # Fallback to individual item translation for this batch
                    batch_translated = _translate_items_individually(batch, target_language, lang_lower)
                    translated.extend(batch_translated)
            
            processed += len(batch)
            if progress_callback:
                progress_callback(processed, total)

    with translated_path.open("w", encoding="utf-8") as f:
        json.dump(translated, f, ensure_ascii=False, indent=2)

    return translated, translated_path


def _parse_translated_content(translated_text: str, original_items: list, lang_lower: str) -> list:
    """Parse translated formatted content back into item structure."""
    translated_items = []
    
    # Split by separator - but be more flexible with separators
    question_blocks = re.split(r'═{3,}', translated_text)
    # Remove empty blocks
    question_blocks = [b.strip() for b in question_blocks if b.strip()]
    
    # If no blocks found, try splitting by double newlines or section markers
    if not question_blocks or len(question_blocks) == 1:
        # Try alternative splitting
        question_blocks = re.split(r'\n\s*-{3,}\s*\n', translated_text)
        question_blocks = [b.strip() for b in question_blocks if b.strip()]
    
    logger.debug(f"Parsing translation: {len(question_blocks)} blocks found, {len(original_items)} original items")
    
    # Process matched blocks
    for idx, (block, original_item) in enumerate(zip(question_blocks, original_items)):
        if not block.strip():
            # Empty block - keep original item
            translated_items.append(original_item)
            continue
        
        block = block.strip()
        
        # Extract question number and text - try multiple patterns
        # The question text should be everything before "Options:" label
        qnum_match = re.search(r'Q\s*(\d+):\s*(.+?)(?=Options:)', block, re.DOTALL | re.IGNORECASE)
        if qnum_match:
            question_text = qnum_match.group(2).strip()
        else:
            q_match = re.search(r'Q:\s*(.+?)(?=Options:)', block, re.DOTALL | re.IGNORECASE)
            if q_match:
                question_text = q_match.group(1).strip()
            else:
                # Try Question X: pattern
                q_match2 = re.search(r'Question\s*\d+:\s*(.+?)(?=Options:)', block, re.DOTALL | re.IGNORECASE)
                if q_match2:
                    question_text = q_match2.group(1).strip()
                else:
                    # If no Options: label found, take everything up to answer/solution
                    q_match3 = re.search(r'Q\s*\d+:\s*(.+?)(?=✅|📝|$)', block, re.DOTALL | re.IGNORECASE)
                    question_text = q_match3.group(1).strip() if q_match3 else ""
        
        # Extract options - find all option lines between "Options:" and answer/solution
        options_match = re.search(r'Options:\s*(.+?)(?=✅|📝|સમાધાનం:|வரణ:|Answer:|ANSWER:|$)', block, re.DOTALL | re.IGNORECASE)
        options = []
        if options_match:
            options_text = options_match.group(1).strip()
            # Parse options like "1) text | 2) text" or "1) text\n2) text"
            opt_parts = re.split(r'\s*\|\s*|\n+\s*(?=\d+\))', options_text)
            for opt_part in opt_parts:
                opt_match = re.match(r'(\d+)\)\s*(.+)', opt_part.strip(), re.DOTALL)
                if opt_match:
                    options.append({"label": opt_match.group(1), "text": opt_match.group(2).strip()})
        
        # Extract answer - try multiple patterns
        answer_match = re.search(r'✅\s*Answer:\s*(.+?)(?:\n|📝|$)', block, re.DOTALL | re.IGNORECASE)
        if not answer_match:
            answer_match = re.search(r'(?:CORRECT\s+)?ANSWER:\s*(.+?)(?:\n|📝|$)', block, re.DOTALL | re.IGNORECASE)
        answer = answer_match.group(1).strip() if answer_match else ""
        
        # Extract solution/explanation - try multiple patterns
        solution_match = re.search(r'📝\s*Solution:\s*(.+?)(?:\n|═|$)', block, re.DOTALL | re.IGNORECASE)
        if not solution_match:
            solution_match = re.search(r'SOLUTION:\s*(.+?)(?:\n|═|$)', block, re.DOTALL | re.IGNORECASE)
        explanation = solution_match.group(1).strip() if solution_match else ""
        
        # Build translated item
        translated_item = {**original_item}
        if question_text:
            translated_item[f"question_text_{lang_lower}"] = question_text
            translated_item[f"question_body_{lang_lower}"] = question_text
        if options:
            translated_item[f"options_{lang_lower}"] = options
        if answer:
            translated_item[f"answer_{lang_lower}"] = answer
        if explanation:
            translated_item[f"explanation_{lang_lower}"] = explanation
        
        translated_items.append(translated_item)
    
    # Handle case where we have fewer translated blocks than original items
    # This can happen if translation was truncated or incomplete
    if len(translated_items) < len(original_items):
        logger.warning(f"Translation incomplete: {len(translated_items)} items translated, {len(original_items)} expected. Adding untranslated items.")
        for idx in range(len(translated_items), len(original_items)):
            # Keep original item without translation
            translated_items.append(original_items[idx])
    
    # Handle case where we have more blocks than items (shouldn't happen, but safety)
    if len(translated_items) > len(original_items):
        logger.warning(f"More translated blocks ({len(translated_items)}) than original items ({len(original_items)}). Truncating.")
        translated_items = translated_items[:len(original_items)]
    
    return translated_items


def _translate_items_individually(items: list, target_language: str, lang_lower: str) -> list:
    """Fallback: Translate items individually."""
    translated = []
    for item in items:
        q = item.get("question_body", item.get("question_text", ""))
        a = item.get("answer", "")
        e = item.get("explanation", "")
        
        prompt = f"""
Translate the following solved MCQ into {target_language}.

Keep all numbers, symbols, and math expressions unchanged.

Return output strictly as JSON like:
{{
  "question_text_{lang_lower}": "...",
  "answer_{lang_lower}": "...",
  "explanation_{lang_lower}": "..."
}}

Question: {q}
Answer: {a}
Explanation: {e}
"""
        try:
            response = _call_generative_model(prompt)
            parsed = extract_inner_json(response.text.strip())
            if not parsed:
                parsed = json.loads(extract_json_block(response.text))
            if parsed:
                merged = {**item, **parsed}
                if f"options_{lang_lower}" not in parsed and item.get("options"):
                    merged[f"options_{lang_lower}"] = item.get("options")
            else:
                merged = {
                    **item,
                    f"raw_translation_{lang_lower}": response.text.strip(),
                }
            translated.append(merged)
        except Exception as exc:
            item[f"translation_error_{lang_lower}"] = str(exc)
            translated.append(item)
    
    return translated


def _build_solution_docx_text(translated_items, lang_lower: str):
    """Build DOCX text content from translated items."""
    ans_label, exp_label, title_label = PIPELINE_LABELS.get(
        lang_lower, PIPELINE_LABELS["telugu"]
    )
    suffix = f"_{lang_lower}"
    lines: list[str] = [f"**{title_label}**", ""]

    for idx, item in enumerate(translated_items, start=1):
        question_label = item.get("question_number") or idx
        
        q_body = _clean_text(
            item.get(f"question_body{suffix}", "") or 
            item.get("question_body", "") or
            item.get(f"question_text{suffix}", "") or 
            item.get("question_text", "")
        )
        
        options = item.get(f"options_{lang_lower}", item.get("options", []))
        
        if not options or len(options) == 0:
            q_full = _clean_text(item.get(f"question_text{suffix}", "") or item.get("question_text", ""))
            if q_full and q_full != q_body:
                option_pattern1 = re.compile(r"(?m)^\s*(\d+)\)\s*(.+?)(?=\n\s*\d+\)|$)", re.MULTILINE)
                option_matches = list(option_pattern1.finditer(q_full))
                if not option_matches:
                    option_pattern2 = re.compile(r"(?m)^\s*(\d+)\.\s*(.+?)(?=\n\s*\d+\.|$)", re.MULTILINE)
                    option_matches = list(option_pattern2.finditer(q_full))
                if not option_matches:
                    option_pattern3 = re.compile(r"(?m)\((\d+)\)\s*(.+?)(?=\((\d+)\)|$)", re.MULTILINE)
                    option_matches = list(option_pattern3.finditer(q_full))
                
                if option_matches:
                    options = [
                        {"label": opt.group(1).strip(), "text": opt.group(2).strip()}
                        for opt in option_matches
                    ]
        
        ans = _clean_text(item.get(f"answer{suffix}", "") or item.get("answer", ""))
        answer_option = item.get("answer_option", "")
        
        if not answer_option and ans:
            option_match = re.search(r"option\s*(\d+)|(\d+)\)", ans, re.IGNORECASE)
            if option_match:
                answer_option = option_match.group(1) or option_match.group(2)
        
        # Find the actual answer text from options if answer_option is available
        actual_answer_text = None
        if answer_option and options and isinstance(options, list) and len(options) > 0:
            for opt in options:
                opt_label = str(opt.get("label", "")).strip()
                if str(opt_label) == str(answer_option):
                    actual_answer_text = _clean_text(opt.get("text", "")).strip()
                    break
        
        exp = _clean_text(
            item.get(f"explanation{suffix}", "") or item.get("explanation", "")
        )

        if not (q_body or ans or exp):
            continue

        lines.append(f"**Question {question_label}:**")
        lines.append("")
        
        if q_body:
            lines.append(q_body)
            lines.append("")
        
        if options and isinstance(options, list) and len(options) > 0:
            for opt in options:
                opt_label = str(opt.get("label", "")).strip()
                opt_text = _clean_text(opt.get("text", "")).strip()
                if opt_text:
                    if answer_option and str(opt_label) == str(answer_option):
                        lines.append(f"✓ {opt_label}) {opt_text}")
                    else:
                        lines.append(f"{opt_label}) {opt_text}")
            lines.append("")
        
        # Show just the answer option number (not the full text)
        if answer_option:
            lines.append(f"{ans_label}: {answer_option}")
        elif actual_answer_text:
            lines.append(f"{ans_label}: {actual_answer_text}")
        elif ans:
                lines.append(f"{ans_label}: {ans}")
        lines.append("")
        
        if exp:
            lines.append(f"{exp_label}: {exp}")
        
        lines.append("═══")

    return "\n".join(lines).strip()


def run_solution_generation_pipeline(uploaded_file, target_language: str, status_callback=None, job_id: str = None):
    """Main pipeline for solution generation.
    
    Args:
        uploaded_file: File object or bytes containing PDF data
        target_language: Target language label (e.g., "Telugu", "Hindi")
        status_callback: Optional callback function(status_callback(progress: int, message: str, status: str))
            - progress: 0-100
            - message: Status message
            - status: "processing" | "completed" | "failed"
        job_id: Optional job ID for storing debug data
    """
    lang_lower = target_language.lower()
    job_dir = SOLUTION_JOBS_ROOT / str(uuid.uuid4())
    job_dir.mkdir(parents=True, exist_ok=True)
    input_pdf = job_dir / uploaded_file.name
    _write_uploaded_file(uploaded_file, input_pdf)

    def _update(label, fraction):
        if status_callback:
            progress = int(min(max(fraction * 100, 0), 100))
            status_callback(progress, label, "processing")

    _update("Extracting PDF...", 0.05)
    pages, extracted_json = _pipeline_extract_pdf(input_pdf, job_dir)

    def solving_progress(current, total):
        progress = 0.1 + (current / (total or 1)) * 0.35
        _update("Solving questions...", progress)

    solved, solved_json = _pipeline_solve_pages(pages, job_dir, solving_progress, job_id=job_id)

    def translate_progress(current, total):
        progress = 0.5 + (current / (total or 1)) * 0.3
        _update(
            f"Translating to {target_language}...",
            progress,
        )

    translated, translated_json = _pipeline_translate_items(
        solved, target_language, job_dir, translate_progress
    )

    _update("Building DOCX output...", 0.9)
    docx_text = _build_solution_docx_text(translated, lang_lower)
    final_docx_path = job_dir / f"solutions_{lang_lower}.docx"
    docx_bytes = create_docx(
        docx_text or "No translated content generated.", f"Solutions - {target_language}"
    )
    if docx_bytes:
        final_docx_path.write_bytes(docx_bytes)
    else:
        final_docx_path = None
    _update("Pipeline complete!", 1.0)
    
    if status_callback:
        status_callback(100, "Pipeline complete!", "completed")

    return {
        "job_dir": str(job_dir),
        "extracted_json": str(extracted_json),
        "solved_json": str(solved_json),
        "translated_json": str(translated_json),
        "final_docx": str(final_docx_path) if final_docx_path else None,
        "sample": translated[:5],
        "language": target_language,
    }

