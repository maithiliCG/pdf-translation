"""
MCQ Generator Module - Generate and translate multiple-choice questions
"""
import json
import logging

from modules.common import _call_generative_model, create_docx

logger = logging.getLogger(__name__)


def generate_mcqs(topic, num_questions=5, language="English"):
    """Generate MCQs on a given topic directly in the specified language."""
    prompt = f"""
Generate {num_questions} high-quality multiple-choice questions (MCQs) on the topic: "{topic}".

IMPORTANT: Generate all content directly in {language} language. Do not generate in English first.
- Questions must be in {language}
- All options must be in {language}
- Correct answer must be in {language}
- Explanations must be in {language}

Return a valid JSON array with the following structure:
[
  {{
    "question": "Question text in {language}",
    "options": ["Option 1 in {language}", "Option 2 in {language}", "Option 3 in {language}", "Option 4 in {language}"],
    "correct_answer": "Correct answer text in {language}",
    "explanation": "Explanation text in {language}"
  }}
]

Ensure:
- Options array contains exactly 4 string options
- All text is in {language} language
- JSON is valid and parseable
"""
    response = _call_generative_model(prompt)
    return response.text


def parse_mcqs(raw_text):
    """Parse MCQs from raw text."""
    try:
        start = raw_text.find("[")
        end = raw_text.rfind("]") + 1
        if start == -1 or end <= start:
            return None
        return json.loads(raw_text[start:end])
    except Exception:
        return None


def translate_text(text, target_language="English"):
    """Translate text to target language."""
    if target_language == "English":
        return text
    prompt = f"""
Translate the following text to {target_language}.
Return only the translation, no labels or explanations.

Text:
{text}
"""
    try:
        response = _call_generative_model(prompt)
        return (response.text or "").strip()
    except Exception as exc:
        logger.error(f"Translation error: {exc}")
        raise RuntimeError(f"Failed to translate text: {exc}") from exc


def _iter_options(raw_options):
    """Iterate over options in various formats."""
    if isinstance(raw_options, dict):
        return list(raw_options.items())
    if isinstance(raw_options, list):
        return [
            (f"{chr(64 + idx)}", value)
            for idx, value in enumerate(raw_options, start=1)
            if isinstance(value, str)
        ]
    return []


def _maybe_translate_text(text: str, target_language: str) -> str:
    """Translate text if target language is not English."""
    if not text or target_language == "English":
        return text
    return translate_text(text, target_language)


def _translate_mcq_items(mcqs, target_language: str):
    """Translate MCQ items to target language."""
    translated = []
    if not mcqs:
        return translated

    for mcq in mcqs:
        options_translated = []
        for letter, text in _iter_options(mcq.get("options")):
            options_translated.append(
                {"label": letter, "text": _maybe_translate_text(text, target_language)}
            )

        translated.append(
            {
                "question": _maybe_translate_text(mcq.get("question", ""), target_language),
                "options": options_translated,
                "answer": _maybe_translate_text(str(mcq.get("correct_answer", "")), target_language),
                "explanation": _maybe_translate_text(
                    mcq.get("explanation", ""), target_language
                ),
            }
        )

    return translated

