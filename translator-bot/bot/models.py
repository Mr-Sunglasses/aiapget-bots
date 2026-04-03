"""Data models for the bilingual bot."""

from dataclasses import dataclass, field


@dataclass
class Question:
    num: int
    serial: str                     # e.g. "1/25"
    question: str                   # raw text, \n for line breaks
    options: dict[str, str]         # {"A": "...", "B": "...", "C": "...", "D": "..."}
    correct_answer: str             # "A"/"B"/"C"/"D"
    solution: str                   # never translate
    tag: str                        # never translate
    serial_line: str = ""           # full "[N/25] @HANDLE" line, stripped from question text
    para_indices: list[int] = field(default_factory=list)
    right_answer_int: int | None = None  # original integer from XLSX (1-4)


@dataclass
class TranslatedQuestion:
    original: Question
    question_bilingual: str
    options_bilingual: dict[str, str]


@dataclass
class PipelineStats:
    total_questions: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cache_hit: bool
    errors: list[str] = field(default_factory=list)
