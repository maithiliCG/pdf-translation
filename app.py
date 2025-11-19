"""
PDFMathTranslate - Main Streamlit Application
AI Study Assistant for solving PDFs, generating MCQs, and translating PDFs
"""
import os
import streamlit as st

from config.settings import LANGUAGES, GEMINI_API_KEY
from modules.solution_generator import run_solution_generation_pipeline
from modules.mcq_generator import (
    generate_mcqs,
    parse_mcqs,
    _translate_mcq_items,
    _iter_options,
)
from modules.pdf_translator import translate_pdf_with_pdf2zh
from modules.common import create_docx

# Check API key
if not GEMINI_API_KEY:
    st.error(
        "⚠️ **API Key Missing**\n\n"
        "Please add `GENAI_API_KEY` (or `GEMINI_API_KEY`) to your environment.\n\n"
        "**For local development:**\n"
        "1. Create a `.env` file in the project root\n"
        "2. Add: `GENAI_API_KEY=your_api_key_here`\n\n"
        "**For Streamlit Cloud:**\n"
        "1. Go to app settings\n"
        "2. Add secret: `GENAI_API_KEY`\n\n"
        "Get your API key from: https://makersuite.google.com/app/apikey"
    )
    st.stop()

# Session state defaults
SESSION_DEFAULTS = {
    "solution_result": None,
    "mcqs_data": None,
    "mcqs_topic": None,
    "translated_mcqs": None,
    "mcqs_translated_lang": None,
    "pdf_translation_result": None,
    "translated_pdf_lang": None,
}

for key, value in SESSION_DEFAULTS.items():
    st.session_state.setdefault(key, value)

# Streamlit UI
st.set_page_config(page_title="AI Study Assistant", page_icon="📚", layout="wide")

st.title("📚 AI Study Assistant - PDFMathTranslate")
st.markdown(
    "Solve PDFs, generate MCQs, and translate full PDFs with layout preservation."
)

# Check if babeldoc is available for PDF Translator
try:
    from pdf2zh_next.high_level import BABELDOC_AVAILABLE
    pdf_translator_available = BABELDOC_AVAILABLE
except (ImportError, AttributeError):
    pdf_translator_available = False

# Always show all three tabs with PDF Translator as first
tab1, tab2, tab3 = st.tabs(
    ["🌍 PDF Translator", "📄 Solution Generator", "❓ MCQ Generator"]
)

# Tab 1: PDF Translator (always shown as first tab)
with tab1:
    st.header("PDF Translator")
    
    # Show warning if babeldoc is not available
    if not pdf_translator_available:
        st.warning(
            "⚠️ **PDF Translator Feature Currently Unavailable**\n\n"
            "The PDF Translator requires the `babeldoc` library, which doesn't support Python 3.14 yet.\n\n"
            "**To use PDF Translator:**\n"
            "1. Use Python 3.13 or 3.12 instead of Python 3.14\n"
            "2. Create a new virtual environment with Python 3.13/3.12\n"
            "3. Reinstall dependencies\n\n"
            "**Note:** Solution Generator and MCQ Generator work perfectly with Python 3.14!"
        )
    
    translator_file = st.file_uploader("Upload PDF to translate", type="pdf", key="translator_pdf")
    translate_language = st.selectbox(
        "Target language",
        options=list(LANGUAGES.keys()),
        index=list(LANGUAGES.keys()).index("Hindi"),
    )

    if translator_file and st.button("🔄 Translate PDF", disabled=not pdf_translator_available):
        if not pdf_translator_available:
            st.error("PDF Translator is not available. Please use Python 3.13 or 3.12 to enable this feature.")
        else:
            progress = st.progress(0)
            status = st.empty()
            try:
                result = translate_pdf_with_pdf2zh(translator_file, translate_language, progress, status)
                st.session_state["pdf_translation_result"] = result
                st.session_state["translated_pdf_lang"] = translate_language
                st.success("PDF translated successfully!")
            except Exception as exc:
                progress.empty()
                status.empty()
                error_str = str(exc)
                # Check if it's a babeldoc error and format it nicely
                if "PDF Translator Feature Unavailable" in error_str:
                    st.error(error_str)
                else:
                    st.error(f"**PDF translation failed:**\n\n{error_str}")

    translation = st.session_state.get("pdf_translation_result")
    if translation:
        st.markdown("---")
        st.subheader(f"Downloads ({st.session_state.get('translated_pdf_lang')})")
        mono = translation.get("mono_pdf_path")
        dual = translation.get("dual_pdf_path")
        lang_code = translation.get("lang_code") or translation.get("lang_label") or "lang"
        
        col1, col2 = st.columns(2)
        
        if mono and os.path.exists(mono):
            with col1:
                st.download_button(
                    "📥 Monolingual PDF",
                    data=open(mono, "rb").read(),
                    file_name=f"translated_{lang_code}_mono.pdf",
                    mime="application/pdf",
                )
        if dual and os.path.exists(dual):
            with col2:
                st.download_button(
                    "📥 Bilingual PDF",
                    data=open(dual, "rb").read(),
                    file_name=f"translated_{lang_code}_dual.pdf",
                    mime="application/pdf",
                )

# Tab 2: Solution Generator
with tab2:
    st.header("Solution Generator")
    st.info("Generates extracted/solved/translated JSON plus a formatted DOCX.")

    solution_file = st.file_uploader("Upload question paper PDF", type="pdf", key="solution_pdf")
    solution_language = st.selectbox(
        "Target language", 
        options=list(LANGUAGES.keys()), 
        index=list(LANGUAGES.keys()).index("Telugu")
    )
    
    if solution_file and st.button("🚀 Run Solution Pipeline"):
        progress = st.progress(0)
        status = st.empty()
        try:
            result = run_solution_generation_pipeline(solution_file, solution_language, progress, status)
            st.session_state["solution_result"] = result
            st.success("Pipeline completed successfully!")
        except Exception as exc:
            progress.empty()
            status.empty()
            st.error(f"Solution pipeline failed: {exc}")

    result = st.session_state.get("solution_result")
    if result:
        final_docx_path = result.get("final_docx")
        if final_docx_path and os.path.exists(final_docx_path):
            st.markdown("---")
            st.download_button(
                "📥 Download Final DOCX",
                data=open(final_docx_path, "rb").read(),
                file_name=f"solutions_{result['language']}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

# Tab 3: MCQ Generator
with tab3:
    st.header("MCQ Generator")
    topic = st.text_input("Topic", placeholder="e.g., Photosynthesis, Algebra, WW-II")
    num_questions = st.number_input("How many questions?", min_value=1, max_value=10, value=5)
    mcq_translate_lang = st.selectbox(
        "Generate MCQs in",
        options=list(LANGUAGES.keys()),
        index=list(LANGUAGES.keys()).index("English"),
        key="mcq_translate_lang",
    )

    if st.button("🎯 Generate MCQs"):
        if not topic.strip():
            st.warning("Please type a topic first.")
        else:
            with st.spinner(f"Generating MCQs in {mcq_translate_lang}..."):
                # Generate MCQs directly in the selected language
                raw = generate_mcqs(topic, num_questions, mcq_translate_lang)
            mcqs = parse_mcqs(raw) if raw else None
            if mcqs:
                # If language is not English, translate the generated MCQs
                if mcq_translate_lang != "English":
                    with st.spinner(f"Translating MCQs to {mcq_translate_lang}..."):
                        translated_items = _translate_mcq_items(mcqs, mcq_translate_lang)
                    st.session_state["translated_mcqs"] = translated_items
                    st.session_state["mcqs_translated_lang"] = mcq_translate_lang
                else:
                    st.session_state["translated_mcqs"] = None
                    st.session_state["mcqs_translated_lang"] = "English"
                st.session_state["mcqs_data"] = mcqs
                st.session_state["mcqs_topic"] = topic
            else:
                st.error("Failed to parse MCQ output. Please retry.")

    mcqs = st.session_state.get("mcqs_data") or []

    if mcqs:
        topic_name = st.session_state.get("mcqs_topic", "Topic")
        current_lang = st.session_state.get("mcqs_translated_lang", mcq_translate_lang)
        st.success(f"Generated {len(mcqs)} MCQs on '{topic_name}' in {current_lang}")
        
        # Get translated items if available
        translated_items = None
        if (
            st.session_state.get("translated_mcqs")
            and st.session_state.get("mcqs_translated_lang") == mcq_translate_lang
        ):
            translated_items = st.session_state.get("translated_mcqs")

        # Prepare DOCX content - only include translated content if available
        docx_content = [f"MCQs on: {topic_name} ({current_lang})", ""]
        
        # Display and prepare content
        for idx, mcq in enumerate(mcqs, start=1):
            # Use translated content if available, otherwise use original
            if translated_items and idx - 1 < len(translated_items):
                translated_block = translated_items[idx - 1]
                # Display translated version
                st.markdown(
                    f"<div style='background:#eef7ff;padding:0.75rem;border-left:4px solid #2196F3;border-radius:8px;margin-bottom:1rem;'>"
                    f"<b>Q{idx}.</b> {translated_block.get('question','')}</div>",
                    unsafe_allow_html=True,
                )
                for opt in translated_block.get("options", []):
                    st.write(f"- {opt['label']}. {opt['text']}")
                with st.expander("Answer & Explanation"):
                    st.write(f"**Answer:** {translated_block.get('answer','')}")
                    st.write(f"**Explanation:** {translated_block.get('explanation','')}")
                
                # Add only translated content to DOCX
                docx_content.extend(
                    [
                        f"Question {idx}: {translated_block.get('question','')}",
                    ]
                )
                for opt in translated_block.get("options", []):
                    docx_content.append(f"{opt['label']}. {opt['text']}")
                docx_content.extend(
                    [
                        f"Correct Answer: {translated_block.get('answer','')}",
                        f"Explanation: {translated_block.get('explanation','')}",
                        "═══",
                    ]
                )
            else:
                # Display original English version
                st.markdown(
                    f"<div style='background:#f7f9fc;padding:1rem;border-left:4px solid #4CAF50;border-radius:8px;margin-bottom:1rem;'><b>Q{idx}.</b> {mcq.get('question','')}</div>",
                    unsafe_allow_html=True,
                )
                options = _iter_options(mcq.get("options"))
                for letter, text in options:
                    st.write(f"- {letter}. {text}")
                with st.expander("Answer & Explanation"):
                    st.write(f"**Answer:** {mcq.get('correct_answer','')}")
                    st.write(f"**Explanation:** {mcq.get('explanation','')}")
                
                # Add original content to DOCX
                docx_content.extend(
                    [
                        f"Question {idx}: {mcq.get('question','')}",
                    ]
                )
                options = _iter_options(mcq.get("options"))
                for letter, text in options:
                    docx_content.append(f"{letter}. {text}")
                docx_content.extend(
                    [
                        f"Correct Answer: {mcq.get('correct_answer','')}",
                        f"Explanation: {mcq.get('explanation','')}",
                        "═══",
                    ]
                )

        docx_bytes = create_docx("\n".join(docx_content), f"MCQs - {topic_name} ({current_lang})")
        if docx_bytes:
            st.download_button(
                "📥 Download MCQs (DOCX)",
                data=docx_bytes,
                file_name=f"mcqs_{topic_name.replace(' ', '_')}_{current_lang}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:#666;'>Powered by Google Gemini AI</div>",
    unsafe_allow_html=True,
)
