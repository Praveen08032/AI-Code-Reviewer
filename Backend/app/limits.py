"""Shared request sizes and supported language IDs."""
SUPPORTED_LANGUAGES = frozenset({"python", "javascript", "typescript", "java", "cpp", "csharp", "go", "rust", "php", "ruby"})
MAX_CODE_CHARS = 20000
MAX_TASK_CHARS = 4000
MAX_TITLE_CHARS = 120


def language_id(value: str) -> str:
    value = value.strip().lower()
    if value not in SUPPORTED_LANGUAGES:
        raise ValueError("Choose one of the ten supported programming languages.")
    return value


def non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("This field cannot be blank.")
    return value
