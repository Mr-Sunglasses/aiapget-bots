"""Pipeline: parse → translate → build → stats."""

import logging
import os
import tempfile
from pathlib import Path

from bot.models import PipelineStats, TranslatedQuestion
from bot.parser import parse_docx, parse_xlsx
from bot.translator import translate_quiz
from bot.builder import build_docx, build_xlsx

logger = logging.getLogger(__name__)


def _output_name(source: str, suffix: str = "_bilingual") -> str:
    p = Path(source)
    return str(p.parent / f"{p.stem}{suffix}{p.suffix}")


def process_docx(
    docx_path: str,
    cache_path: str = ".translation_cache.json",
    usage_log_path: str = ".usage_log.json",
) -> tuple[str, PipelineStats]:
    """Process a single DOCX file end-to-end. Returns (output_path, stats)."""
    questions = parse_docx(docx_path)
    if not questions:
        raise ValueError("No questions found in DOCX")

    translated, stats = translate_quiz(questions, cache_path, usage_log_path)
    output_path = _output_name(docx_path)
    build_docx(docx_path, translated, output_path)

    logger.info("DOCX done: %d questions, cache_hit=%s", stats.total_questions, stats.cache_hit)
    return output_path, stats


def process_xlsx(
    xlsx_path: str,
    cache_path: str = ".translation_cache.json",
    usage_log_path: str = ".usage_log.json",
) -> tuple[str, PipelineStats]:
    """Process a single XLSX file end-to-end. Returns (output_path, stats)."""
    questions = parse_xlsx(xlsx_path)
    if not questions:
        raise ValueError("No questions found in XLSX")

    translated, stats = translate_quiz(questions, cache_path, usage_log_path)
    output_path = _output_name(xlsx_path)
    build_xlsx(xlsx_path, translated, output_path)

    logger.info("XLSX done: %d questions, cache_hit=%s", stats.total_questions, stats.cache_hit)
    return output_path, stats


def process_pair(
    docx_path: str,
    xlsx_path: str,
    cache_path: str = ".translation_cache.json",
    usage_log_path: str = ".usage_log.json",
) -> tuple[str, str, PipelineStats]:
    """Process a DOCX+XLSX pair using one translation call. Returns (docx_out, xlsx_out, stats)."""
    questions = parse_docx(docx_path)
    if not questions:
        raise ValueError("No questions found in DOCX")

    translated, stats = translate_quiz(questions, cache_path, usage_log_path)

    docx_out = _output_name(docx_path)
    build_docx(docx_path, translated, docx_out)

    xlsx_out = _output_name(xlsx_path)
    build_xlsx(xlsx_path, translated, xlsx_out)

    logger.info(
        "Pair done: %d questions, cache_hit=%s, cost=$%.4f",
        stats.total_questions, stats.cache_hit, stats.cost_usd,
    )
    return docx_out, xlsx_out, stats
