import google.generativeai as genai
import os
from dotenv import load_dotenv
import re

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def get_gemini_feedback(language: str, code: str) -> str:
    prompt = f"Analyze this {language} code and provide:\n- Bugs\n- Suggestions\n- Readability and efficiency score (1-10)\n- Improved version if needed.\n\nCode:\n{code}"

    model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "models/gemini-flash-latest"))
    response = model.generate_content(prompt)
    return response.text


def parse_ai_feedback(text: str) -> dict:
    # Extract scores
    readability_match = re.search(r"Readability[:\-]?\s*(\d+)/10", text, re.IGNORECASE)
    efficiency_match = re.search(r"Efficiency[:\-]?\s*(\d+)/10", text, re.IGNORECASE)

    readability_score = int(readability_match.group(1)) if readability_match else 0
    efficiency_score = int(efficiency_match.group(1)) if efficiency_match else 0

    # Extract Suggestions
    suggestions = []
    if "### Suggestions" in text:
        suggestions_block = text.split("### Suggestions")[1].split("###")[0]
        suggestions = re.findall(r"\*{1,2}\s*(.+)", suggestions_block)

    # Extract Bugs
    errors = []
    if "### Bugs" in text:
        bugs_block = text.split("### Bugs")[1].split("###")[0]
        errors = re.findall(r"\*{1,2}\s*(.+)", bugs_block)

    # Extract corrected code from Improved Version
    corrected_code = None
    if "### Improved Version" in text:
        improved_block = text.split("### Improved Version", 1)[1]

        # Match the first code block inside that section
        code_match = re.search(r"```(?:[^\n]*)\n(.*?)```", improved_block, re.DOTALL)
        if code_match:
            corrected_code = code_match.group(1).strip()

    return {
        "readability_score": readability_score,
        "efficiency_score": efficiency_score,
        "suggestions": suggestions,
        "errors": errors,
        "corrected_code": corrected_code
    }
