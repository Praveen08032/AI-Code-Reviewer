import google.generativeai as genai
import os
from dotenv import load_dotenv
import re

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def get_gemini_feedback(language: str, code: str) -> str:
    prompt = f"""Analyze this {language} code. Reply in Markdown using exactly these headings and formats:

### Bugs
* one bullet per bug (write "* None" if there are no bugs)

### Suggestions
* one bullet per suggestion

### Scores
Readability: X/10
Efficiency: X/10

### Improved Version
```{language}
the full improved code
```

Code:
{code}"""

    model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "models/gemini-flash-latest"))
    response = model.generate_content(prompt)
    return response.text


def _section(text: str, keyword: str) -> str:
    # Text under the first heading that contains the keyword, up to the next heading
    match = re.search(rf"^#{{2,6}}[^\n]*{keyword}[^\n]*\n(.*?)(?=^#{{2,6}}\s|\Z)", text,
                      re.IGNORECASE | re.MULTILINE | re.DOTALL)
    return match.group(1) if match else ""


def _bullets(block: str) -> list:
    items = re.findall(r"^\s*[\*\-]\s+(.+)", block, re.MULTILINE)
    items = [i.replace("**", "").strip() for i in items]
    return [i for i in items if i and i.lower().rstrip(".") != "none"]


def parse_ai_feedback(text: str) -> dict:
    # Extract scores (also matches "**Readability:** 8/10" or "Readability score: 8 / 10")
    readability_match = re.search(r"Readability\W*(?:score\W*)?(\d+)\s*/\s*10", text, re.IGNORECASE)
    efficiency_match = re.search(r"Efficiency\W*(?:score\W*)?(\d+)\s*/\s*10", text, re.IGNORECASE)

    readability_score = int(readability_match.group(1)) if readability_match else 0
    efficiency_score = int(efficiency_match.group(1)) if efficiency_match else 0

    # Extract Suggestions and Bugs
    suggestions = _bullets(_section(text, "Suggestions"))
    errors = _bullets(_section(text, "Bugs"))

    # Extract corrected code: first code block after the Improved Version heading
    # (search everything after the heading, since code comments can look like headings)
    corrected_code = None
    match = re.search(r"^#{2,6}[^\n]*Improved[^\n]*\n(.*)", text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
    improved_block = match.group(1) if match else ""
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
