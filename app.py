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
from modules.pdf_translator import translate_pdf_with_pdf2zh, create_docx_from_pdf
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

tab1, tab2, tab3 = st.tabs(
    ["🌍 PDF Translator", "📄 Solution Generator", "❓ MCQ Generator"]
)

# Tab 1: PDF Translator
with tab1:
    st.header("PDF Translator")
    translator_file = st.file_uploader("Upload PDF to translate", type="pdf", key="translator_pdf")
    translate_language = st.selectbox(
        "Target language",
        options=list(LANGUAGES.keys()),
        index=list(LANGUAGES.keys()).index("Hindi"),
    )

    if translator_file and st.button("🔄 Translate PDF"):
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
            st.error(f"PDF translation failed: {exc}")

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
        st.markdown("---")
        st.subheader(f"Outputs ({result['language']})")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.download_button(
                "📥 Extracted JSON",
                data=open(result["extracted_json"], "rb").read(),
                file_name="extracted_data.json",
                mime="application/json",
            )
        with col2:
            st.download_button(
                "📥 Solved JSON",
                data=open(result["solved_json"], "rb").read(),
                file_name="solved_data.json",
                mime="application/json",
            )
        with col3:
            st.download_button(
                "📥 Translated JSON",
                data=open(result["translated_json"], "rb").read(),
                file_name=f"translated_{result['language']}.json",
                mime="application/json",
            )
        final_docx_path = result.get("final_docx")
        if final_docx_path and os.path.exists(final_docx_path):
            st.download_button(
                "📥 Final DOCX",
                data=open(final_docx_path, "rb").read(),
                file_name=f"solutions_{result['language']}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        st.markdown("### Sample translated records")
        st.json(result.get("sample", [])[:3])

# Tab 3: MCQ Generator
with tab3:
    st.header("MCQ Generator")
    topic = st.text_input("Topic", placeholder="e.g., Photosynthesis, Algebra, WW-II")
    num_questions = st.number_input("How many questions?", min_value=1, max_value=10, value=5)
    mcq_translate_lang = st.selectbox(
        "Translate MCQs to",
        options=list(LANGUAGES.keys()),
        index=list(LANGUAGES.keys()).index("English"),
        key="mcq_translate_lang",
    )

    if st.button("🎯 Generate MCQs"):
        if not topic.strip():
            st.warning("Please type a topic first.")
        else:
            with st.spinner("Generating MCQs..."):
                raw = generate_mcqs(topic, num_questions)
            mcqs = parse_mcqs(raw) if raw else None
            if mcqs:
                st.session_state["mcqs_data"] = mcqs
                st.session_state["mcqs_topic"] = topic
                st.session_state["translated_mcqs"] = None
                st.session_state["mcqs_translated_lang"] = None
            else:
                st.error("Failed to parse MCQ output. Please retry.")

    mcqs = st.session_state.get("mcqs_data") or []

    if st.button("🌐 Translate MCQs", disabled=not mcqs):
        if not mcqs:
            st.info("Generate MCQs first, then translate.")
        else:
            with st.spinner(f"Translating MCQs to {mcq_translate_lang}..."):
                translated_items = _translate_mcq_items(mcqs, mcq_translate_lang)
            st.session_state["translated_mcqs"] = translated_items
            st.session_state["mcqs_translated_lang"] = mcq_translate_lang
            if mcq_translate_lang == "English":
                st.success("MCQs reset to English content.")
            else:
                st.success(f"Translated MCQs to {mcq_translate_lang}.")

    if mcqs:
        topic_name = st.session_state.get("mcqs_topic", "Topic")
        st.success(f"Generated {len(mcqs)} MCQs on '{topic_name}'")
        docx_content = [f"MCQs on: {topic_name}", ""]
        translated_items = None
        if (
            st.session_state.get("translated_mcqs")
            and st.session_state.get("mcqs_translated_lang") == mcq_translate_lang
        ):
            translated_items = st.session_state.get("translated_mcqs")

        for idx, mcq in enumerate(mcqs, start=1):
            st.markdown(
                f"<div style='background:#f7f9fc;padding:1rem;border-left:4px solid #4CAF50;border-radius:8px;margin-bottom:1rem;'><b>Q{idx}.</b> {mcq.get('question','')}</div>",
                unsafe_allow_html=True,
            )
            options = _iter_options(mcq.get("options"))
            for letter, text in options:
                st.write(f"- {letter}. {text}")
                docx_content.append(f"{letter}. {text}")

            with st.expander("Answer & Explanation"):
                st.write(f"**Answer:** {mcq.get('correct_answer','')}")
                st.write(f"**Explanation:** {mcq.get('explanation','')}")

            translated_block = None
            if translated_items and idx - 1 < len(translated_items):
                translated_block = translated_items[idx - 1]

            if translated_block and mcq_translate_lang != "English":
                st.markdown(
                    f"<div style='background:#eef7ff;padding:0.75rem;border-left:4px solid #2196F3;border-radius:8px;margin:0 0 1rem 1rem;'>"
                    f"<b>[{mcq_translate_lang}] Q{idx}.</b> {translated_block.get('question','')}</div>",
                    unsafe_allow_html=True,
                )
                for opt in translated_block.get("options", []):
                    st.write(f"- {opt['label']}. {opt['text']}")
                with st.expander(f"Answer & Explanation ({mcq_translate_lang})"):
                    st.write(f"**Answer:** {translated_block.get('answer','')}")
                    st.write(f"**Explanation:** {translated_block.get('explanation','')}")

            docx_content.extend(
                [
                    "",
                    f"Question {idx}: {mcq.get('question','')}",
                    f"Correct Answer: {mcq.get('correct_answer','')}",
                    f"Explanation: {mcq.get('explanation','')}",
                    "═══",
                ]
            )

            if translated_block and mcq_translate_lang != "English":
                docx_content.extend(
                    [
                        f"[{mcq_translate_lang}] Question {idx}: {translated_block.get('question','')}",
                        f"[{mcq_translate_lang}] Answer: {translated_block.get('answer','')}",
                        f"[{mcq_translate_lang}] Explanation: {translated_block.get('explanation','')}",
                        "═══",
                    ]
                )

        docx_bytes = create_docx("\n".join(docx_content), f"MCQs - {topic_name}")
        if docx_bytes:
            st.download_button(
                "📥 Download MCQs (DOCX)",
                data=docx_bytes,
                file_name=f"mcqs_{topic_name.replace(' ', '_')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:#666;'>Powered by Google Gemini AI</div>",
    unsafe_allow_html=True,
)
