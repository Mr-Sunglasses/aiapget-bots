"""Tests for the translator module (mocked LLM backends)."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bot.models import Question
from bot.translator import (
    translate_quiz,
    _compute_cache_key,
    _questions_to_json,
    _validate_and_fix_response,
    _parse_response,
)
from bot.utils import strip_serial_line


MOCK_RESPONSE_DATA = [
    {
        "num": 1,
        "question": "How many Yantra dosha?\nयंत्र दोष की संख्या कितनी है?",
        "options": {"A": "4", "B": "6", "C": "8", "D": "10"},
        "correct_answer": "B",
        "solution": "Sushruta Sara pg 4, Su su 14/38",
        "tag": "Quiz no. 01 Date 1/8/2025",
    },
    {
        "num": 2,
        "question": "त्वक् विवर्णता (Discolouration of skin) is the lakshana of",
        "options": {"A": "वात (Vata)", "B": "पित्त (Pitta)", "C": "कफ (Kapha)", "D": "रक्त (Rakta)"},
        "correct_answer": "A",
        "solution": "Reference: Su su 21/18",
        "tag": "Quiz no. 01 Date 1/8/2025",
    },
    {
        "num": 3,
        "question": "Laghu anna is indicated in\nलघु अन्न किसमें निर्दिष्ट है?",
        "options": {"A": "Jwara (ज्वर)", "B": "Atisara (अतिसार)", "C": "Gulma (गुल्म)", "D": "All (सभी)"},
        "correct_answer": "D",
        "solution": "Charaka Samhita Su 25/40",
        "tag": "Quiz no. 01 Date 1/8/2025",
    },
]


def _mock_call_llm(data=None):
    """Return a mock _call_llm that returns (json_text, input_tokens, output_tokens)."""
    text = json.dumps(data or MOCK_RESPONSE_DATA, ensure_ascii=False)
    return MagicMock(return_value=(text, 1840, 1120))


class TestTranslateQuiz:
    @patch("bot.translator._call_llm")
    def test_basic_translation(self, mock_llm, sample_questions, tmp_path):
        mock_llm.side_effect = _mock_call_llm()

        cache_path = str(tmp_path / "cache.json")
        usage_path = str(tmp_path / "usage.json")

        translated, stats = translate_quiz(sample_questions, cache_path, usage_path)

        assert len(translated) == 3
        assert stats.total_questions == 3
        assert not stats.cache_hit
        assert stats.input_tokens == 1840
        assert stats.output_tokens == 1120
        mock_llm.assert_called_once()

    @patch("bot.translator._call_llm")
    def test_cache_hit_skips_api(self, mock_llm, sample_questions, tmp_path):
        mock_llm.side_effect = _mock_call_llm()

        cache_path = str(tmp_path / "cache.json")
        usage_path = str(tmp_path / "usage.json")

        translate_quiz(sample_questions, cache_path, usage_path)
        mock_llm.reset_mock()

        translated, stats = translate_quiz(sample_questions, cache_path, usage_path)

        assert stats.cache_hit
        assert stats.cost_usd == 0.0
        mock_llm.assert_not_called()

    @patch("bot.translator._call_llm")
    def test_solution_always_overwritten_from_original(self, mock_llm, sample_questions, tmp_path):
        """Solution and tag are always forced back to original values."""
        modified_data = json.loads(json.dumps(MOCK_RESPONSE_DATA))
        modified_data[0]["solution"] = "MODIFIED SOLUTION"
        modified_data[0]["tag"] = "MODIFIED TAG"
        mock_llm.side_effect = _mock_call_llm(modified_data)

        cache_path = str(tmp_path / "cache.json")
        usage_path = str(tmp_path / "usage.json")

        translated, _ = translate_quiz(sample_questions, cache_path, usage_path)

        assert translated[0].original.solution == "Sushruta Sara pg 4, Su su 14/38"
        assert translated[0].original.tag.startswith("Quiz no. 01")

    @patch("bot.translator._call_llm")
    def test_numeric_options_unchanged(self, mock_llm, sample_questions, tmp_path):
        mock_llm.side_effect = _mock_call_llm()

        cache_path = str(tmp_path / "cache.json")
        usage_path = str(tmp_path / "usage.json")

        translated, _ = translate_quiz(sample_questions, cache_path, usage_path)

        q1_opts = translated[0].options_bilingual
        assert q1_opts["A"] == "4"
        assert q1_opts["B"] == "6"

    @patch("bot.translator._call_llm")
    def test_cost_calculation(self, mock_llm, sample_questions, tmp_path):
        mock_llm.side_effect = _mock_call_llm()

        cache_path = str(tmp_path / "cache.json")
        usage_path = str(tmp_path / "usage.json")

        _, stats = translate_quiz(sample_questions, cache_path, usage_path)

        expected_cost = (1840 * 3.0 + 1120 * 5.0) / 1_000_000
        assert abs(stats.cost_usd - expected_cost) < 0.0001

    @patch("bot.translator._call_llm")
    def test_usage_log_written(self, mock_llm, sample_questions, tmp_path):
        mock_llm.side_effect = _mock_call_llm()

        cache_path = str(tmp_path / "cache.json")
        usage_path = str(tmp_path / "usage.json")

        translate_quiz(sample_questions, cache_path, usage_path)

        usage_log = json.loads(Path(usage_path).read_text())
        assert len(usage_log) == 1
        assert usage_log[0]["input_tokens"] == 1840
        assert usage_log[0]["output_tokens"] == 1120


class TestValidateAndFix:
    """Tests for Bug 1/2: validation, empty question fallback, count/num checks."""

    def test_empty_question_uses_original(self, sample_questions):
        data = json.loads(json.dumps(MOCK_RESPONSE_DATA))
        data[0]["question"] = ""

        fixed, warnings = _validate_and_fix_response(data, sample_questions)

        assert fixed[0]["question"] == "How many Yantra dosha?"
        assert any("empty question" in w for w in warnings)

    def test_null_question_uses_original(self, sample_questions):
        data = json.loads(json.dumps(MOCK_RESPONSE_DATA))
        data[1]["question"] = None

        fixed, warnings = _validate_and_fix_response(data, sample_questions)

        assert "त्वक् विवर्णता" in fixed[1]["question"]
        assert any("empty question" in w for w in warnings)

    def test_count_mismatch_returns_all_originals(self, sample_questions):
        data = json.loads(json.dumps(MOCK_RESPONSE_DATA[:2]))

        fixed, warnings = _validate_and_fix_response(data, sample_questions)

        assert len(fixed) == 3
        assert any("Count mismatch" in w for w in warnings)
        assert fixed[0]["question"] == "How many Yantra dosha?"

    def test_num_mismatch_returns_all_originals(self, sample_questions):
        data = json.loads(json.dumps(MOCK_RESPONSE_DATA))
        data[1]["num"] = 99

        fixed, warnings = _validate_and_fix_response(data, sample_questions)

        assert len(fixed) == 3
        assert any("num mismatch" in w for w in warnings)

    def test_solution_always_overwritten(self, sample_questions):
        data = json.loads(json.dumps(MOCK_RESPONSE_DATA))
        data[0]["solution"] = "MODIFIED BY CLAUDE"

        fixed, _ = _validate_and_fix_response(data, sample_questions)

        assert fixed[0]["solution"] == "Sushruta Sara pg 4, Su su 14/38"

    def test_tag_always_overwritten(self, sample_questions):
        data = json.loads(json.dumps(MOCK_RESPONSE_DATA))
        data[0]["tag"] = "CHANGED"

        fixed, _ = _validate_and_fix_response(data, sample_questions)

        assert "संघर्ष 2026" in fixed[0]["tag"]

    def test_serial_line_stripped_from_question(self, sample_questions):
        data = json.loads(json.dumps(MOCK_RESPONSE_DATA))
        data[0]["question"] = "[1/3] @AIPGETMADEEASY\nHow many Yantra dosha?\nयंत्र दोष?"

        fixed, _ = _validate_and_fix_response(data, sample_questions)

        assert "[1/3]" not in fixed[0]["question"]
        assert "AIPGETMADEEASY" not in fixed[0]["question"]
        assert "Yantra dosha" in fixed[0]["question"]


class TestContentDropGuard:
    """Tests for Bug 1 (round 2): content-drop detection when Claude shortens question text."""

    def test_short_translation_reverts_to_original(self, sample_questions):
        """If translated question is <70% of original length, revert to original."""
        data = json.loads(json.dumps(MOCK_RESPONSE_DATA))
        # Original Q3: "Laghu anna is indicated in" (26 chars without spaces)
        # Replace with something very short
        data[2]["question"] = "Short"

        fixed, warnings = _validate_and_fix_response(data, sample_questions)

        assert fixed[2]["question"] == "Laghu anna is indicated in"
        assert any("content dropped" in w for w in warnings)

    def test_longer_translation_is_kept(self, sample_questions):
        """Translation that's longer than original should be kept."""
        data = json.loads(json.dumps(MOCK_RESPONSE_DATA))
        # This is longer than original — should be kept
        data[0]["question"] = "How many Yantra dosha?\nयंत्र दोष की संख्या कितनी है?"

        fixed, warnings = _validate_and_fix_response(data, sample_questions)

        assert "यंत्र दोष" in fixed[0]["question"]
        assert not any("content dropped" in w for w in warnings)

    def test_match_table_dropped_triggers_revert(self, sample_questions):
        """Simulates Bug 1: Claude drops a match-table prefix, only keeps last sentence."""
        long_original = (
            "Match the following धातु with it's रस\n"
            "A. स्वर्ण. 1.कषाय\nB. रजत. 2. तिक्त\n"
            "C. कांस्य. 3. मधुर\nD. ताम्र 4. अम्ल\n"
            "व्यापन्न and अव्यापन्न ऋतुकृत is the भेद of _ व्याधि"
        )
        questions = [
            Question(
                num=7, serial="7/25", question=long_original,
                options={"A": "opt", "B": "opt", "C": "opt", "D": "opt"},
                correct_answer="A", solution="ref", tag="tag",
                serial_line="[7/25] @AIAPGETMADEEASY",
            )
        ]
        data = [{
            "num": 7,
            "question": "व्यापन्न (Abnormal) and अव्यापन्न (Normal) is the भेद of _ व्याधि",
            "options": {"A": "opt", "B": "opt", "C": "opt", "D": "opt"},
            "correct_answer": "A",
            "solution": "ref",
            "tag": "tag",
        }]

        fixed, warnings = _validate_and_fix_response(data, questions)

        assert "Match the following" in fixed[0]["question"]
        assert any("content dropped" in w for w in warnings)


class TestEmptySourceWarning:
    """Tests for Bug 5 (round 2): warn when source question text is itself empty."""

    def test_empty_source_question_warns(self):
        questions = [
            Question(
                num=6, serial="6/25", question="",
                options={"A": "A3 B2 C1 D4", "B": "opt", "C": "opt", "D": "opt"},
                correct_answer="A", solution="ref", tag="tag",
                serial_line="[6/25] @AIAPGETMADEEASY",
            )
        ]
        data = [{
            "num": 6, "question": "", "options": {"A": "opt", "B": "opt", "C": "opt", "D": "opt"},
            "correct_answer": "A", "solution": "ref", "tag": "tag",
        }]

        fixed, warnings = _validate_and_fix_response(data, questions)

        assert any("source question text is empty" in w for w in warnings)

    def test_nonempty_source_no_empty_warning(self, sample_questions):
        data = json.loads(json.dumps(MOCK_RESPONSE_DATA))

        _, warnings = _validate_and_fix_response(data, sample_questions)

        assert not any("source question text is empty" in w for w in warnings)


class TestOptionNormalisation:
    """Tests for Bug 3: consistent True/False capitalisation."""

    def test_normalise_applied_in_validation(self, sample_questions):
        data = json.loads(json.dumps(MOCK_RESPONSE_DATA))
        data[0]["options"]["A"] = "1 Correct 2 incorrect"

        fixed, _ = _validate_and_fix_response(data, sample_questions)

        assert fixed[0]["options"]["A"] == "1 correct 2 incorrect / 1 सही 2 गलत"

    def test_both_correct_normalised(self, sample_questions):
        data = json.loads(json.dumps(MOCK_RESPONSE_DATA))
        data[0]["options"]["A"] = "Both Correct"

        fixed, _ = _validate_and_fix_response(data, sample_questions)

        assert fixed[0]["options"]["A"] == "Both correct / दोनों सही"

    def test_both_incorrect_normalised(self, sample_questions):
        data = json.loads(json.dumps(MOCK_RESPONSE_DATA))
        data[0]["options"]["A"] = "both incorrect"

        fixed, _ = _validate_and_fix_response(data, sample_questions)

        assert fixed[0]["options"]["A"] == "Both incorrect / दोनों गलत"


class TestStripSerialLine:
    """Tests for Bug 6: serial header removal."""

    def test_strip_basic(self):
        text = "[7/25] @AIPGETMADEEASY\nSome question text"
        assert strip_serial_line(text) == "Some question text"

    def test_strip_no_serial(self):
        text = "How many Yantra dosha?"
        assert strip_serial_line(text) == "How many Yantra dosha?"

    def test_strip_serial_only(self):
        text = "[1/25] @AIAPGETMADEEASY"
        assert strip_serial_line(text) == ""

    def test_strip_serial_in_middle(self):
        text = "Some text\n[7/25] @AIPGETMADEEASY\nMore text"
        result = strip_serial_line(text)
        assert "[7/25]" not in result
        assert "Some text" in result
        assert "More text" in result
