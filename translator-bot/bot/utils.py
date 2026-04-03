"""Utility functions for the bilingual bot."""

import re
import unicodedata


DEVANAGARI_RANGE = range(0x0900, 0x097F + 1)

UNTRANSLATABLE_PATTERNS = [
    re.compile(r"^[\d\s,.\-/]+$"),
    re.compile(r"^[A-D]\d[\s,]*", re.IGNORECASE),
    re.compile(r"^\d+[a-d][\s,]*", re.IGNORECASE),
    re.compile(r"(Su\s+su|pg\s+\d|/\d)", re.IGNORECASE),
]

MATCH_CODE_PATTERN = re.compile(
    r"^[A-D]\d(\s+[A-D]\d)+$|^\d+[a-d](\s+\d+[a-d])+$", re.IGNORECASE
)


def is_untranslatable(text: str) -> bool:
    """Check if text should never be translated (numbers, match codes, references)."""
    text = text.strip()
    if not text:
        return True
    if MATCH_CODE_PATTERN.match(text):
        return True
    for pat in UNTRANSLATABLE_PATTERNS:
        if pat.match(text):
            return True
    return False


def detect_script(text: str) -> str:
    """Detect dominant script: 'devanagari', 'latin', or 'mixed'."""
    devanagari_count = 0
    latin_count = 0
    for ch in text:
        if ord(ch) in DEVANAGARI_RANGE:
            devanagari_count += 1
        elif unicodedata.category(ch).startswith("L") and ord(ch) < 0x0900:
            latin_count += 1

    total = devanagari_count + latin_count
    if total == 0:
        return "latin"
    if devanagari_count / total > 0.6:
        return "devanagari"
    if latin_count / total > 0.6:
        return "latin"
    return "mixed"


def esc_xml(text: str) -> str:
    """Escape special characters for XML text nodes."""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&apos;")
    return text


SERIAL_LINE_RE = re.compile(r"^\[\d+/\d+\]\s*@\w+.*$", re.MULTILINE)


def strip_serial_line(text: str) -> str:
    """Remove serial header like '[7/25] @AIPGETMADEEASY' from question text."""
    return SERIAL_LINE_RE.sub("", text).strip()


OPTION_NORMALISATION: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^1\s*incorrect\s+2\s*correct$", re.IGNORECASE),
     "1 incorrect 2 correct / 1 गलत 2 सही"),
    (re.compile(r"^1\s*correct\s+2\s*incorrect$", re.IGNORECASE),
     "1 correct 2 incorrect / 1 सही 2 गलत"),
    (re.compile(r"^both\s*incorrect$", re.IGNORECASE),
     "Both incorrect / दोनों गलत"),
    (re.compile(r"^both\s*correct$", re.IGNORECASE),
     "Both correct / दोनों सही"),
]

OPTION_NORMALISATION_PARTIAL: list[tuple[re.Pattern, str]] = [
    (re.compile(r"1\s*incorrect\s+2\s*correct\b", re.IGNORECASE),
     "1 incorrect 2 correct / 1 गलत 2 सही"),
    (re.compile(r"1\s*correct\s+2\s*incorrect\b", re.IGNORECASE),
     "1 correct 2 incorrect / 1 सही 2 गलत"),
    (re.compile(r"\bboth\s*incorrect\b", re.IGNORECASE),
     "Both incorrect / दोनों गलत"),
    (re.compile(r"\bboth\s*correct\b", re.IGNORECASE),
     "Both correct / दोनों सही"),
]


def normalise_options(text: str) -> str:
    """Normalise True/False style options to consistent capitalisation with Hindi."""
    stripped = text.strip()

    # Try exact match first (option is just the T/F phrase)
    for pattern, replacement in OPTION_NORMALISATION:
        if pattern.match(stripped):
            return replacement

    # Partial match: e.g. "(A) 1 incorrect 2 correct" → "(A) 1 incorrect 2 correct / ..."
    for pattern, replacement in OPTION_NORMALISATION_PARTIAL:
        m = pattern.search(stripped)
        if m:
            already_has_hindi = "/" in stripped[m.end():]
            if not already_has_hindi:
                hindi_part = replacement.split(" / ", 1)[1]
                return stripped[:m.start()] + replacement.split(" / ", 1)[0] + " / " + hindi_part + stripped[m.end():]
            else:
                # Already has a slash — normalise the English part's capitalisation
                before = stripped[:m.start()]
                after = stripped[m.end():]
                return before + replacement.split(" / ", 1)[0] + after

    return text
