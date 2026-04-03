"""Tests for the DOCX and XLSX parser."""

from pathlib import Path

from bot.parser import parse_docx, parse_xlsx


class TestParseDocx:
    def test_question_count(self, sample_docx: Path):
        questions = parse_docx(str(sample_docx))
        assert len(questions) == 3

    def test_para_indices_populated(self, sample_docx: Path):
        questions = parse_docx(str(sample_docx))
        for q in questions:
            assert len(q.para_indices) > 0

    def test_question_text(self, sample_docx: Path):
        questions = parse_docx(str(sample_docx))
        assert questions[0].question == "How many Yantra dosha?"
        assert "त्वक् विवर्णता" in questions[1].question

    def test_options(self, sample_docx: Path):
        questions = parse_docx(str(sample_docx))
        assert set(questions[0].options.keys()) == {"A", "B", "C", "D"}
        assert questions[0].options["B"] == "6"

    def test_correct_answer(self, sample_docx: Path):
        questions = parse_docx(str(sample_docx))
        assert questions[0].correct_answer == "B"
        assert questions[2].correct_answer == "D"

    def test_solution_preserved(self, sample_docx: Path):
        questions = parse_docx(str(sample_docx))
        assert "Sushruta Sara pg 4" in questions[0].solution

    def test_tag_preserved(self, sample_docx: Path):
        questions = parse_docx(str(sample_docx))
        assert "संघर्ष 2026" in questions[0].tag

    def test_serial(self, sample_docx: Path):
        questions = parse_docx(str(sample_docx))
        assert questions[0].serial == "1/3"
        assert questions[2].serial == "3/3"

    def test_serial_line_extracted(self, sample_docx: Path):
        questions = parse_docx(str(sample_docx))
        assert "[1/3] @AIPGETMADEEASY" in questions[0].serial_line
        assert "[3/3] @AIPGETMADEEASY" in questions[2].serial_line

    def test_serial_line_not_in_question_text(self, sample_docx: Path):
        questions = parse_docx(str(sample_docx))
        for q in questions:
            assert "@AIPGETMADEEASY" not in q.question


class TestParseXlsx:
    def test_question_count(self, sample_xlsx: Path):
        questions = parse_xlsx(str(sample_xlsx))
        assert len(questions) == 3

    def test_right_answer_converted_to_letter(self, sample_xlsx: Path):
        questions = parse_xlsx(str(sample_xlsx))
        assert questions[0].correct_answer == "B"
        assert questions[2].correct_answer == "D"

    def test_right_answer_int_preserved(self, sample_xlsx: Path):
        questions = parse_xlsx(str(sample_xlsx))
        assert questions[0].right_answer_int == 2
        assert questions[2].right_answer_int == 4

    def test_options_a_to_d(self, sample_xlsx: Path):
        questions = parse_xlsx(str(sample_xlsx))
        for q in questions:
            assert set(q.options.keys()) == {"A", "B", "C", "D"}

    def test_question_text(self, sample_xlsx: Path):
        questions = parse_xlsx(str(sample_xlsx))
        assert questions[0].question == "How many Yantra dosha?"

    def test_solution_preserved(self, sample_xlsx: Path):
        questions = parse_xlsx(str(sample_xlsx))
        assert "Sushruta Sara pg 4" in questions[0].solution

    def test_tag_preserved(self, sample_xlsx: Path):
        questions = parse_xlsx(str(sample_xlsx))
        assert "संघर्ष 2026" in questions[0].tag
