"""
Solution Generator Module - PDF question solving and translation
"""
import json
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


def _segment_questions_from_text(full_text: str):
    """Segment questions from text."""
    if not full_text:
        return []

    question_pattern = re.compile(
        r"(?sm)^\s*(\d{1,3})\.\s*(.*?)(?=^\s*\d{1,3}\.\s*|$)"
    )
    option_pattern = re.compile(r"(?s)(\d)\)\s*(.*?)(?=(?:\n\s*\d\)|$))")

    blocks = []
    for match in question_pattern.finditer(full_text):
        number = match.group(1).strip()
        raw_block = match.group(2).strip()
        if not raw_block:
            continue

        option_matches = list(option_pattern.finditer(raw_block))
        if option_matches:
            first_option_start = option_matches[0].start()
            question_prompt = raw_block[:first_option_start].strip()
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
                "raw_block": raw_block,
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


def _pipeline_solve_pages(pages, job_dir: Path, progress_callback=None):
    """Solve questions from PDF pages."""
    combined_text = "\n".join(page.get("text", "") for page in pages if page.get("text"))
    answer_key, key_start = _extract_answer_key_from_text(combined_text)
    questions_text = combined_text if key_start is None else combined_text[:key_start]
    question_blocks = _segment_questions_from_text(questions_text)

    results = []
    total = len(question_blocks) or 1

    for idx, block in enumerate(question_blocks, start=1):
        qnum = block.get("question_number", "")
        options = block.get("options", [])
        answer = ""
        answer_option = None
        explanation = ""
        method = "answer_key" if answer_key else "llm"
        used_answer_key = False

        try:
            qnum_int = int(qnum)
        except (TypeError, ValueError):
            qnum_int = None

        if qnum_int is not None and answer_key:
            opt_digit = answer_key.get(qnum_int)
            if opt_digit:
                answer_option = opt_digit
                selected_option = next(
                    (opt for opt in options if opt.get("label") == opt_digit), None
                )
                if selected_option:
                    answer = f"{selected_option['label']}) {selected_option['text']}"
                else:
                    answer = f"Option {opt_digit}"
                used_answer_key = True
                method = "answer_key"

        block_text = block.get("raw_block", "")

        if not answer:
            sympy_solution = _solve_simple_equation(block_text)
            if sympy_solution:
                answer = str(sympy_solution)
                explanation = "Solved automatically with SymPy."
                method = "sympy"
            else:
                prompt = f"""
You are an expert exam solver. Read the following question and return JSON with fields
"answer" and "explanation".

QUESTION:
{block_text}
"""
                try:
                    response = _call_generative_model(prompt)
                    parsed = extract_inner_json(response.text.strip())
                    if not parsed:
                        parsed = json.loads(extract_json_block(response.text))
                    answer = parsed.get("answer", "")
                    explanation = parsed.get("explanation", "")
                    method = "gemini"
                except Exception as exc:
                    answer = ""
                    explanation = f"Failed to solve: {exc}"
                    method = "error"

        question_body = block.get("question_text", "").strip()
        
        # Build formatted question with options for display
        question_lines = []
        if question_body:
            question_lines.append(question_body)
        if options:
            for opt in options:
                question_lines.append(f"{opt['label']}) {opt['text']}")
        formatted_question = "\n".join(line for line in question_lines if line).strip()

        if used_answer_key and answer:
            explanation = _generate_llm_explanation(
                formatted_question or block_text, answer
            )

        results.append(
            {
                "question_number": qnum,
                "question_text": formatted_question or block.get("raw_block", ""),
                "question_body": question_body or block.get("question_text", "").strip(),
                "options": options if options else [],
                "answer": answer,
                "answer_option": answer_option,
                "explanation": explanation,
                "method": method,
            }
        )

        if progress_callback:
            progress_callback(idx, total)

    solved_file = job_dir / "solved_extracted_data.json"
    with solved_file.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    return results, solved_file


def _pipeline_translate_items(items, target_language: str, job_dir: Path, progress_callback=None):
    """Translate solved items to target language."""
    lang_lower = target_language.lower()
    translated_path = job_dir / f"translated_{lang_lower}_auto.json"
    translated = []
    total = len(items) or 1
    processed = 0
    batch_size = 5

    for batch_start in range(0, len(items), batch_size):
        batch = items[batch_start : batch_start + batch_size]
        payload = []
        for idx, entry in enumerate(batch):
            item_payload = {
                "question_number": entry.get("question_number") or f"{batch_start + idx + 1}",
                "question_body": entry.get("question_body", entry.get("question_text", "")),
                "options": entry.get("options", []),
                "answer": entry.get("answer", ""),
                "answer_option": entry.get("answer_option", ""),
                "explanation": entry.get("explanation", ""),
            }
            payload.append(item_payload)
        
        prompt = f"""
Translate the following solved MCQs into {target_language}. Preserve numbers, math symbols,
and option labels (1), 2), 3), etc.). Return a JSON array where each object contains:
{{
  "question_number": "...",
  "question_body_{lang_lower}": "...",
  "options_{lang_lower}": [{{"label": "1", "text": "..."}}, {{"label": "2", "text": "..."}}, ...],
  "answer_{lang_lower}": "...",
  "explanation_{lang_lower}": "..."
}}

Input questions:
{json.dumps(payload, ensure_ascii=False)}
"""
        batch_success = False
        try:
            response = _call_generative_model(prompt)
            parsed = extract_inner_json(response.text.strip())
            if not parsed:
                parsed = json.loads(extract_json_block(response.text))
            if isinstance(parsed, dict):
                parsed = [parsed]
            if len(parsed) == len(batch):
                for original_item, translated_fields in zip(batch, parsed):
                    merged = {**original_item, **translated_fields}
                    if f"options_{lang_lower}" not in translated_fields and original_item.get("options"):
                        merged[f"options_{lang_lower}"] = original_item.get("options")
                    translated.append(merged)
                batch_success = True
            else:
                batch_success = False
        except Exception:
            batch_success = False

        if not batch_success:
            for item in batch:
                prompt_single = f"""
Translate the following solved MCQ into {target_language}.
Keep numbers, symbols, and formulas untouched. Preserve option labels.
Return output strictly as JSON like:
{{
  "question_body_{lang_lower}": "...",
  "options_{lang_lower}": [{{"label": "1", "text": "..."}}, ...],
  "answer_{lang_lower}": "...",
  "explanation_{lang_lower}": "..."
}}

Question Body: {item.get("question_body", item.get("question_text", ""))}
Options: {json.dumps(item.get("options", []), ensure_ascii=False)}
Answer: {item.get("answer", "")}
Explanation: {item.get("explanation", "")}
"""
                try:
                    response = _call_generative_model(prompt_single)
                    parsed = extract_inner_json(response.text.strip())
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
        processed += len(batch)
        if progress_callback:
            progress_callback(processed, total)

    with translated_path.open("w", encoding="utf-8") as f:
        json.dump(translated, f, ensure_ascii=False, indent=2)

    return translated, translated_path


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
                        lines.append(f"  ✓ {opt_label}) {opt_text}  ← {ans_label}")
                    else:
                        lines.append(f"    {opt_label}) {opt_text}")
            lines.append("")
        else:
            if ans:
                lines.append(f"{ans_label}: {ans}")
            lines.append("")
        
        if exp:
            lines.append(f"{exp_label}: {exp}")
        
        lines.append("═══")

    return "\n".join(lines).strip()


def run_solution_generation_pipeline(uploaded_file, target_language: str, progress_bar, status_placeholder):
    """Main pipeline for solution generation."""
    lang_lower = target_language.lower()
    job_dir = SOLUTION_JOBS_ROOT / str(uuid.uuid4())
    job_dir.mkdir(parents=True, exist_ok=True)
    input_pdf = job_dir / uploaded_file.name
    _write_uploaded_file(uploaded_file, input_pdf)

    def _update(label, fraction):
        fraction = min(max(fraction, 0.0), 1.0)
        progress_bar.progress(fraction, text=label)
        status_placeholder.info(label)

    _update("Extracting PDF...", 0.05)
    pages, extracted_json = _pipeline_extract_pdf(input_pdf, job_dir)

    def solving_progress(current, total):
        _update("Solving questions...", 0.1 + (current / (total or 1)) * 0.35)

    solved, solved_json = _pipeline_solve_pages(pages, job_dir, solving_progress)

    def translate_progress(current, total):
        _update(
            f"Translating to {target_language}...",
            0.5 + (current / (total or 1)) * 0.3,
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

    return {
        "job_dir": str(job_dir),
        "extracted_json": str(extracted_json),
        "solved_json": str(solved_json),
        "translated_json": str(translated_json),
        "final_docx": str(final_docx_path) if final_docx_path else None,
        "sample": translated[:5],
        "language": target_language,
    }

