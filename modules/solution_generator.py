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
    
    # Use new comprehensive prompt to solve all questions at once
    char_limit = 50000  # Limit to avoid token limits
    pdf_text_truncated = questions_text[:char_limit] if len(questions_text) > char_limit else questions_text
    
    prompt = f"""
You are an expert MCQ solver. Analyze ALL questions in the PDF and provide CONCISE, ACCURATE solutions for EVERY question.

**CRITICAL REQUIREMENTS:**

1. IDENTIFY AND PRESERVE section headers/titles from the PDF

2. Group questions under their respective sections

3. Solve ALL questions - d

on't stop halfway

4. Keep explanations CONCISE but COMPLETE (3-5 lines maximum per question)
   - Show ALL necessary calculation steps to reach the answer
   - Include both intermediate values and final calculation
   - For percentage questions: show both values being compared and the percentage formula
   - For ratio questions: show both parts and the ratio calculation
   - Never skip steps that are needed to understand how the answer was reached

5. Trust the given options - one of them is correct

6. Show COMPLETE calculation steps (all values and formulas needed to get the answer)

7. Use CLEAN formatting with clear separation

**OUTPUT FORMAT (Use EXACTLY this structure):**

========================================================================

SECTION: [Section Name/Title from PDF]

========================================================================

------------------------------------------------------------------------

Question [Number]: [Brief question text]

Options: 1) [ans] | 2) [ans] | 3) [ans] | 4) [ans] | 5) [ans]

CORRECT ANSWER: [Number]) [Answer text]

SOLUTION:

[3-5 line COMPLETE explanation showing ALL steps. For calculations, show: Given values -> Formula -> All intermediate calculations -> Final result. For percentage/ratio questions, show both values being compared and the complete calculation.]

------------------------------------------------------------------------

[... more questions in this section ...]

========================================================================

SECTION: [Next Section Name/Title from PDF]

========================================================================

------------------------------------------------------------------------

Question [Number]: [Question text]

...

------------------------------------------------------------------------

**EXAMPLE OUTPUT:**

========================================================================

SECTION: QUANTITATIVE APTITUDE

========================================================================

------------------------------------------------------------------------

Question 1: Find ratio of total students in 2012-2013 to 2014-2015

Options: 1) 11:15 | 2) 9:17 | 3) 13:14 | 4) 7:9 | 5) 10:17

CORRECT ANSWER: 2) 9:17

SOLUTION:

2012+2013: (20+30+40)+(30+40+20) = 180 Lakhs

2014+2015: (40+50+30)+(50+40+30) = 240 Lakhs  

Ratio = 180:240 = 9:17

------------------------------------------------------------------------

Question 2: Class B Group X students as percentage of Class C Group Y students?

Options: 1) 120% | 2) 140% | 3) 160% | 4) 125% | 5) 100%

CORRECT ANSWER: 3) 160%

SOLUTION:

Class B, Group X = (8/16) * 80 = 40 students

Class C, Group Y = (6/12) * 50 = 25 students

Percentage = (40/25) * 100 = 160%

------------------------------------------------------------------------

========================================================================

SECTION: LOGICAL REASONING

========================================================================

------------------------------------------------------------------------

Question 15: If P then Q logic problem...

Options: 1) A | 2) B | 3) C | 4) D

CORRECT ANSWER: 2) B

SOLUTION:

Uses Modus Ponens: If P then Q, P is true, therefore Q

------------------------------------------------------------------------

**GUIDELINES:**

- IDENTIFY section headers (they might be like "Quantitative Ability", "Reasoning", "English", "Data Interpretation", etc.)

- Group questions under appropriate section headers

- If no clear sections exist, create logical groups like "SECTION 1", "SECTION 2"

- Solve ALL questions in ALL sections

- Keep each solution under 5 lines but show COMPLETE reasoning

- Show ALL calculation steps needed (don't skip intermediate values)

- For series: show pattern (e.g., x2+5, +13, etc.)

- For calculations: show main steps only

- Recognize both formats: A,B,C,D OR 1,2,3,4,5

- Use double lines (========) for section separators

- Use single lines (--------) for question separators

- Use simple text: "CORRECT ANSWER:" and "SOLUTION:" (NO emojis or symbols)

- NO lengthy explanations about why options are wrong

- Trust that one option IS correct

- Format must be clean and PDF-export friendly

**Document Content:**

{pdf_text_truncated}

Now solve ALL MCQs with proper section organization!
"""
    
    # Try to solve all questions at once with the new prompt
    try:
        if progress_callback:
            progress_callback(0, 1)
        
        response = _call_generative_model(prompt)
        full_solution_text = response.text.strip()
        
        # Parse the structured output to extract questions
        results = _parse_structured_solution(full_solution_text, answer_key)
        
        if progress_callback:
            progress_callback(1, 1)
        
        # If we got results, return them
        if results:
            solved_file = job_dir / "solved_extracted_data.json"
            with solved_file.open("w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            return results, solved_file
    
    except Exception as exc:
        # Fallback to original method if new approach fails
        pass
    
    # Fallback to original segmentation method
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
You are an expert exam solver. Extract and solve every question and MCQ from the text below.

For each question:

- Detect the question number if present.

- Copy the full question text exactly as written.

- Identify the correct answer using reasoning.

- If the question is MCQ, DO NOT return "Option 1/2/3/4/5".

  Instead, return the ACTUAL ANSWER TEXT. Example:

  - Correct: "Carbon dioxide"

  - Wrong: "Option C" or "Option 3"

- For non-MCQs, return the solved final answer clearly.

- Provide a concise 2-line explanation for how you got the answer.

Output Format (STRICT):

Return ONLY a valid JSON array:

[
  {{
    "question_number": "...",
    "question_text": "...",
    "answer": "...",  
    "explanation": "..."
  }}
]

STRICT RULES:

- NO markdown, NO ```json blocks.

- JSON only.

- Do NOT translate or paraphrase questions.

- If options exist, extract the correct option *text*, not the option number.

- Produce the best possible answer with maximum accuracy.

TEXT:
{block_text}
"""
                try:
                    response = _call_generative_model(prompt)
                    parsed = extract_inner_json(response.text.strip())
                    if not parsed:
                        parsed = json.loads(extract_json_block(response.text))
                    
                    # Handle both array and single object responses
                    if isinstance(parsed, list) and len(parsed) > 0:
                        # If array, take the first item (since we're processing one block at a time)
                        parsed = parsed[0]
                    
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


def _parse_structured_solution(solution_text: str, answer_key: dict) -> list:
    """Parse structured solution output into question items."""
    results = []
    
    # Split by section separators
    sections = re.split(r'={10,}', solution_text)
    
    current_section = None
    question_number = None
    
    for section in sections:
        section = section.strip()
        if not section:
            continue
        
        # Check if this is a section header
        section_match = re.match(r'SECTION:\s*(.+)', section, re.IGNORECASE)
        if section_match:
            current_section = section_match.group(1).strip()
            continue
        
        # Parse questions in this section
        questions = re.split(r'-{10,}', section)
        
        for question_block in questions:
            question_block = question_block.strip()
            if not question_block:
                continue
            
            # Extract question number
            qnum_match = re.search(r'Question\s+(\d+):', question_block, re.IGNORECASE)
            if qnum_match:
                question_number = qnum_match.group(1)
            
            # Extract question text
            qtext_match = re.search(r'Question\s+\d+:\s*(.+?)(?:\n|Options:)', question_block, re.DOTALL | re.IGNORECASE)
            question_text = qtext_match.group(1).strip() if qtext_match else ""
            
            # Extract options
            options_match = re.search(r'Options:\s*(.+?)(?:\n|CORRECT)', question_block, re.DOTALL | re.IGNORECASE)
            options_text = options_match.group(1).strip() if options_match else ""
            options = []
            if options_text:
                # Parse options like "1) [ans] | 2) [ans]"
                option_parts = re.split(r'\s*\|\s*', options_text)
                for opt_part in option_parts:
                    opt_match = re.match(r'(\d+)\)\s*(.+)', opt_part.strip())
                    if opt_match:
                        options.append({"label": opt_match.group(1), "text": opt_match.group(2).strip()})
            
            # Extract correct answer
            answer_match = re.search(r'CORRECT ANSWER:\s*(\d+)\)\s*(.+)', question_block, re.IGNORECASE)
            if answer_match:
                answer_option = answer_match.group(1)
                answer_text = answer_match.group(2).strip()
            else:
                answer_option = None
                answer_text = ""
            
            # Extract solution/explanation
            solution_match = re.search(r'SOLUTION:\s*(.+?)(?:\n-{10,}|$)', question_block, re.DOTALL | re.IGNORECASE)
            explanation = solution_match.group(1).strip() if solution_match else ""
            
            # Use answer key if available
            if question_number and answer_key:
                try:
                    qnum_int = int(question_number)
                    opt_digit = answer_key.get(qnum_int)
                    if opt_digit:
                        answer_option = opt_digit
                        selected_option = next((opt for opt in options if opt.get("label") == opt_digit), None)
                        if selected_option:
                            answer_text = f"{selected_option['label']}) {selected_option['text']}"
                        else:
                            answer_text = f"Option {opt_digit}"
                except ValueError:
                    pass
            
            if question_number and (question_text or answer_text):
                results.append({
                    "question_number": question_number,
                    "question_text": question_text,
                    "question_body": question_text,
                    "options": options,
                    "answer": answer_text,
                    "answer_option": answer_option,
                    "explanation": explanation,
                    "method": "llm_structured",
                    "section": current_section,
                })
    
    return results


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

{batch_content[:char_limit]}

**Provide ONLY the translated content, maintaining exact structure.**
"""
            try:
                response = _call_generative_model(prompt)
                translated_text = response.text.strip()
                batch_translated = _parse_translated_content(translated_text, batch, lang_lower)
                translated.extend(batch_translated)
            except Exception as exc:
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
    
    # Split by separator
    question_blocks = re.split(r'═{3,}', translated_text)
    
    for idx, (block, original_item) in enumerate(zip(question_blocks, original_items)):
        if not block.strip():
            translated_items.append(original_item)
            continue
        
        block = block.strip()
        
        # Extract question number and text
        qnum_match = re.search(r'Q(\d+):\s*(.+?)(?:\n|Options:)', block, re.DOTALL | re.IGNORECASE)
        if qnum_match:
            question_text = qnum_match.group(2).strip()
        else:
            q_match = re.search(r'Q:\s*(.+?)(?:\n|Options:)', block, re.DOTALL | re.IGNORECASE)
            question_text = q_match.group(1).strip() if q_match else ""
        
        # Extract options
        options_match = re.search(r'Options:\s*(.+?)(?:\n|✅)', block, re.DOTALL | re.IGNORECASE)
        options = []
        if options_match:
            options_text = options_match.group(1).strip()
            # Parse options like "1) text | 2) text"
            opt_parts = re.split(r'\s*\|\s*', options_text)
            for opt_part in opt_parts:
                opt_match = re.match(r'(\d+)\)\s*(.+)', opt_part.strip())
                if opt_match:
                    options.append({"label": opt_match.group(1), "text": opt_match.group(2).strip()})
        
        # Extract answer
        answer_match = re.search(r'✅\s*Answer:\s*(.+?)(?:\n|📝)', block, re.DOTALL | re.IGNORECASE)
        answer = answer_match.group(1).strip() if answer_match else ""
        
        # Extract solution/explanation
        solution_match = re.search(r'📝\s*Solution:\s*(.+?)(?:\n|═|$)', block, re.DOTALL | re.IGNORECASE)
        explanation = solution_match.group(1).strip() if solution_match else ""
        
        # Build translated item
        translated_item = {**original_item}
        translated_item[f"question_text_{lang_lower}"] = question_text
        translated_item[f"question_body_{lang_lower}"] = question_text
        if options:
            translated_item[f"options_{lang_lower}"] = options
        translated_item[f"answer_{lang_lower}"] = answer
        translated_item[f"explanation_{lang_lower}"] = explanation
        
        translated_items.append(translated_item)
    
    # Handle case where we have more blocks than items (shouldn't happen, but safety)
    while len(translated_items) < len(original_items):
        translated_items.append(original_items[len(translated_items)])
    
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
                        lines.append(f"  ✓ {opt_label}) {opt_text}")
                    else:
                        lines.append(f"    {opt_label}) {opt_text}")
            lines.append("")
        
        # Show actual answer text instead of "Option X"
        if actual_answer_text:
            lines.append(f"{ans_label}: {actual_answer_text}")
        elif ans:
            # If we have answer but no actual text, try to clean it
            cleaned_ans = ans.replace("Option ", "").replace("option ", "").strip()
            if cleaned_ans and cleaned_ans != ans:
                # Try to find the option text
                if options and isinstance(options, list) and len(options) > 0:
                    for opt in options:
                        opt_label = str(opt.get("label", "")).strip()
                        if str(opt_label) == str(cleaned_ans):
                            actual_answer_text = _clean_text(opt.get("text", "")).strip()
                            if actual_answer_text:
                                lines.append(f"{ans_label}: {actual_answer_text}")
                                break
                    if not actual_answer_text:
                        lines.append(f"{ans_label}: {ans}")
                else:
                    lines.append(f"{ans_label}: {ans}")
            else:
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

