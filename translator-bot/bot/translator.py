"""LLM translation with caching and cost tracking. Supports OpenAI-compatible APIs and Anthropic."""

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from bot.models import Question, TranslatedQuestion, PipelineStats
from bot.utils import normalise_options, strip_serial_line

logger = logging.getLogger(__name__)

INPUT_PRICE_PER_M = 3.0   # $/M tokens (Sonnet pricing, ignored for local models)
OUTPUT_PRICE_PER_M = 5.0


TRANSLATION_PROMPT = """You are an expert in Ayurvedic medicine and Sanskrit, helping make a medical exam quiz bilingual (English + Hindi).

Your task: take each question and return it with bilingual text added, following these exact rules.

CRITICAL STRUCTURAL RULES:
- You must return EXACTLY {question_count} objects in the JSON array.
- The i-th object in your output MUST correspond to the i-th object in the input.
- Never merge, split, reorder, or skip any question.
- Each output object's "num" field must match the input object's "num" field exactly.

═══════════════════════════════════════════════════
RULE 1 — NEVER DROP CONTENT:
Your output question text must contain ALL content from the input question text.
If the input has a match table + a question sentence, your output must have BOTH — translate each part inline.
If the input has multiple lines or sections, every line must appear in the output.
If your translated question is shorter than the original, you have made an error — go back and include all content.

Example input:
  "Match the following धातु with it's रस\\nA. स्वर्ण. 1.कषाय\\nB. रजत. 2. तिक्त\\nव्यापन्न and अव्यापन्न ऋतुकृत is the भेद of _ व्याधि"
Correct output:
  "Match the following धातु (Metal) with it's रस (Taste)\\nA. स्वर्ण (Gold). 1.कषाय (Astringent)\\nB. रजत (Silver). 2. तिक्त (Bitter)\\nव्यापन्न (Abnormal) and अव्यापन्न (Normal) ऋतुकृत (Seasonal) is the भेद (Type) of _ व्याधि (Disease)\\nयह किस व्याधि का भेद है?"
WRONG: dropping the match table and only keeping the last sentence.
═══════════════════════════════════════════════════

═══════════════════════════════════════════════════
RULE 2 — HINDI LINE MUST BE COMPLETE AND MEANINGFUL:
Only add a Hindi translation line (after \\n) if it forms a complete, grammatically correct sentence that adds value.
Never add a line that merely echoes the Sanskrit term with "है" or "हैं" appended.
If the question is already mostly in Sanskrit/Hindi with just a few English connectors, the inline bracket translations may be sufficient — do NOT add a redundant Hindi line.

BAD:  "कदम्बपुष्प आकृति है" (just echoes Sanskrit with "is" — meaningless)
BAD:  "यह है" (too vague)
GOOD: "यह किसकी आकृति है?" (complete question in Hindi)
GOOD: "यह किस रोग का लक्षण है?" (meaningful)

If you cannot form a complete meaningful Hindi sentence, do NOT add a Hindi line — just keep the inline bracket translations.
═══════════════════════════════════════════════════

═══════════════════════════════════════════════════
RULE 3 — TRANSLATE EACH STATEMENT, NOT JUST THE HEADER:
For "Find the correct statements" type questions where numbered statements are in Hindi/Sanskrit:
- Translate EACH individual numbered statement into English (add English after each Hindi statement)
- Do NOT just translate the header "Find the correct statements" → "सही कथन ज्ञात कीजिये" and leave the actual statements untouched.

For shloka/verse questions (a full Sanskrit verse as the question text):
- Add the English meaning of the verse in brackets or on the next line.
- NEVER copy the Sanskrit shloka text again as the "Hindi translation" — it IS already Sanskrit/Hindi.

WRONG for shloka: copying "वृत्तोन्नतं विग्रथितं तु शोफं..." as the Hindi line
RIGHT for shloka: adding "(Circular, elevated, knotted swelling is caused by...)" as the English meaning
═══════════════════════════════════════════════════

═══════════════════════════════════════════════════
RULE 4 — OPTIONS NEED ENGLISH MEANINGS, NOT ROMANISATION:
For Sanskrit/Hindi options, always provide the actual English MEANING in brackets — not just a romanised transliteration.
A romanised transliteration gives no information to someone who does not know Sanskrit.

WRONG: "कालबल प्रवृत्त (Kalabalapravritta)" ← just romanisation, meaningless
RIGHT: "कालबल प्रवृत्त (Disease caused by seasonal/time force)"

WRONG: "वातज अर्श (Vataja Arsha)" ← still Sanskrit in Roman script
RIGHT: "वातज अर्श (Vata type hemorrhoids)"

For English options, add the Hindi term in brackets as before:
RIGHT: "Raktaja (रक्तज)" ✓
═══════════════════════════════════════════════════

BILINGUAL RULES:
1. Question text:
   - If English dominant → keep English, add Hindi translation on next line (separated by \\n)
   - If Sanskrit/Hindi dominant → add English meaning in brackets inline
   - For questions that are MOSTLY Sanskrit/Hindi but have English connector words ("is the lakshana of", "is used in", "according to", "is the feature of", etc.): keep the inline bracket translations for Sanskrit terms, AND ALSO add a pure Hindi version of the full sentence on a new line (separated by \\n) — but ONLY if the Hindi line is complete and meaningful (see RULE 2)
   - Example A: "Number of Yantra dosha\\nयंत्र दोष की संख्या?"
   - Example B: "त्वक् विवर्णता (Discolouration of skin) is the lakshana of\\nयह किसका लक्षण है?"
   - Example C: "अलाबुवत् लम्बते (Hanging like a bottle gourd) is the lakshana of which type of गलगण्ड (Goitre)\\nयह किस प्रकार के गलगण्ड का लक्षण है?"

2. Options:
   - Pure Sanskrit/Hindi term → add English MEANING in brackets (not romanisation): "शिशिर (Winter season)"
   - Pure English term → add Hindi in brackets: "Laghu anna (लघु अन्न)"
   - True/False style "(A) 1 incorrect 2 correct" → append "/ 1 गलत 2 सही"
   - Numbers, match codes (A2 B1 C3, 1b 2c 3a), numeric combos (12,8) → leave EXACTLY as-is

3. READ-ONLY FIELDS — copy EXACTLY character-for-character from input, no modifications:
   - The `solution` field must be copied EXACTLY character-for-character from the input. Do not translate it, add brackets to it, restructure it, or modify it in any way. Treat it as a read-only field.
   - The `tag` field must be copied EXACTLY from the input.
   - The `correct_answer` field must be copied EXACTLY from the input.
   - The `num` field must be copied EXACTLY from the input.

4. Preserve all existing text — only ADD the translation, never remove or rephrase original.

5. NEVER leave the `question` field empty or null. If you cannot translate it, return the original text unchanged.

INPUT (JSON array of {question_count} questions):
{questions_json}

OUTPUT: Return ONLY a valid JSON array of EXACTLY {question_count} objects with the same structure.
Each object must have these exact keys: num, question, options (dict A/B/C/D), correct_answer, solution, tag.
The question and options values should now be bilingual.
No explanation, no markdown, no code fences. Raw JSON only."""


def _questions_to_json(questions: list[Question]) -> str:
    data = [
        {
            "num": q.num,
            "question": strip_serial_line(q.question),
            "options": q.options,
            "correct_answer": q.correct_answer,
            "solution": q.solution,
            "tag": q.tag,
        }
        for q in questions
    ]
    return json.dumps(data, ensure_ascii=False, indent=2)


def _compute_cache_key(questions_json: str) -> str:
    return hashlib.sha256(questions_json.encode("utf-8")).hexdigest()


def _load_cache(cache_path: str) -> dict:
    p = Path(cache_path)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache_path: str, cache: dict) -> None:
    Path(cache_path).write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _log_usage(usage_log_path: str, input_tokens: int, output_tokens: int, cost: float) -> None:
    p = Path(usage_log_path)
    log_entries = []
    if p.exists():
        log_entries = json.loads(p.read_text(encoding="utf-8"))

    log_entries.append({
        "date": datetime.now(timezone.utc).isoformat(),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6),
    })
    p.write_text(json.dumps(log_entries, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# LLM backend abstraction
# ---------------------------------------------------------------------------

def _call_openai(prompt_text: str, model: str) -> tuple[str, int, int]:
    """Call an OpenAI-compatible endpoint. Returns (text, input_tokens, output_tokens)."""
    from openai import OpenAI

    base_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    api_key = os.environ.get("LLM_API_KEY", "not-needed")

    client = OpenAI(base_url=base_url, api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        max_tokens=8192,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt_text}],
    )

    raw_text = response.choices[0].message.content or ""
    usage = response.usage
    input_tokens = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0
    return raw_text.strip(), input_tokens, output_tokens


def _call_anthropic(prompt_text: str, model: str) -> tuple[str, int, int]:
    """Call the Anthropic API. Returns (text, input_tokens, output_tokens)."""
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt_text}],
    )

    raw_text = response.content[0].text.strip()
    return raw_text, response.usage.input_tokens, response.usage.output_tokens


def _call_llm(prompt_text: str) -> tuple[str, int, int]:
    """Route to the configured LLM backend. Returns (text, input_tokens, output_tokens)."""
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()
    model = os.environ.get("LLM_MODEL", "")

    if provider == "anthropic":
        model = model or "claude-sonnet-4-5"
        return _call_anthropic(prompt_text, model)
    else:
        model = model or "qwen-plus"
        return _call_openai(prompt_text, model)


# ---------------------------------------------------------------------------
# Validation & parsing
# ---------------------------------------------------------------------------

def _validate_and_fix_response(
    data: list[dict],
    questions: list[Question],
) -> tuple[list[dict], list[str]]:
    """Validate LLM response and fix common issues. Returns (fixed_data, warnings)."""
    warnings: list[str] = []

    if len(data) != len(questions):
        warnings.append(
            f"Count mismatch: expected {len(questions)}, got {len(data)}. "
            "Using original text for all questions."
        )
        return _fallback_all(questions), warnings

    for i, (item, orig) in enumerate(zip(data, questions)):
        item_num = item.get("num")
        if item_num != orig.num:
            warnings.append(
                f"Q{i+1}: num mismatch (expected {orig.num}, got {item_num}). "
                "Using original text for all questions."
            )
            return _fallback_all(questions), warnings

    for i, (item, orig) in enumerate(zip(data, questions)):
        orig_clean = strip_serial_line(orig.question)

        if not orig_clean.strip():
            warnings.append(f"Q{orig.num}: source question text is empty — kept as-is")

        q_text = item.get("question") or ""
        if not q_text.strip():
            warnings.append(f"Q{orig.num}: LLM returned empty question, using original")
            item["question"] = orig_clean
        else:
            item["question"] = strip_serial_line(item["question"])

            orig_len = len(orig_clean.replace(" ", ""))
            trans_len = len(item["question"].replace(" ", ""))
            if orig_len > 0 and trans_len < orig_len * 0.7:
                warnings.append(
                    f"Q{orig.num}: content dropped ({trans_len} vs {orig_len} chars), reverted to original"
                )
                item["question"] = orig_clean

        item["solution"] = orig.solution
        item["tag"] = orig.tag
        item["correct_answer"] = orig.correct_answer

        opts = item.get("options", {})
        for key in list(opts.keys()):
            opts[key] = normalise_options(opts[key])
        item["options"] = opts

    return data, warnings


def _fallback_all(questions: list[Question]) -> list[dict]:
    """Build a fallback response using all original question text."""
    return [
        {
            "num": q.num,
            "question": strip_serial_line(q.question),
            "options": dict(q.options),
            "correct_answer": q.correct_answer,
            "solution": q.solution,
            "tag": q.tag,
        }
        for q in questions
    ]


def _parse_response(raw_json: str, questions: list[Question]) -> tuple[list[TranslatedQuestion], list[str]]:
    """Parse LLM JSON response into TranslatedQuestion objects with validation."""
    data = json.loads(raw_json)
    data, warnings = _validate_and_fix_response(data, questions)
    q_map = {q.num: q for q in questions}

    translated: list[TranslatedQuestion] = []
    for item in data:
        num = item["num"]
        orig = q_map.get(num)
        if orig is None:
            continue
        translated.append(
            TranslatedQuestion(
                original=orig,
                question_bilingual=item["question"],
                options_bilingual=item.get("options", orig.options),
            )
        )
    return translated, warnings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def translate_quiz(
    questions: list[Question],
    cache_path: str = ".translation_cache.json",
    usage_log_path: str = ".usage_log.json",
) -> tuple[list[TranslatedQuestion], PipelineStats]:
    """Translate a list of questions using the configured LLM with caching."""
    questions_json = _questions_to_json(questions)
    cache_key = _compute_cache_key(questions_json)
    cache = _load_cache(cache_path)

    if cache_key in cache:
        logger.info("Cache hit — skipping API call")
        translated, warnings = _parse_response(
            json.dumps(cache[cache_key], ensure_ascii=False), questions
        )
        return translated, PipelineStats(
            total_questions=len(questions),
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            cache_hit=True,
            errors=warnings,
        )

    prompt_text = (
        TRANSLATION_PROMPT
        .replace("{questions_json}", questions_json)
        .replace("{question_count}", str(len(questions)))
    )

    max_retries = 2
    for attempt in range(max_retries):
        try:
            raw_text, input_tokens, output_tokens = _call_llm(prompt_text)

            # Strip markdown fences if LLM wraps them
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[1]
                if raw_text.endswith("```"):
                    raw_text = raw_text[: raw_text.rfind("```")]
                raw_text = raw_text.strip()

            translated, warnings = _parse_response(raw_text, questions)
            for w in warnings:
                logger.warning(w)

            cost = (input_tokens * INPUT_PRICE_PER_M + output_tokens * OUTPUT_PRICE_PER_M) / 1_000_000

            cache[cache_key] = json.loads(raw_text)
            _save_cache(cache_path, cache)
            _log_usage(usage_log_path, input_tokens, output_tokens, cost)

            provider = os.environ.get("LLM_PROVIDER", "openai")
            model = os.environ.get("LLM_MODEL", "")
            logger.info(
                "✅ [%s/%s] Tokens: %d in / %d out | Cost: ~$%.4f",
                provider, model, input_tokens, output_tokens, cost,
            )

            return translated, PipelineStats(
                total_questions=len(questions),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                cache_hit=False,
                errors=warnings,
            )
        except json.JSONDecodeError:
            logger.warning("JSON parse failed (attempt %d/%d)", attempt + 1, max_retries)
            if attempt == max_retries - 1:
                raise
        except Exception:
            logger.exception("Translation API error (attempt %d/%d)", attempt + 1, max_retries)
            if attempt == max_retries - 1:
                raise

    raise RuntimeError("Translation failed after retries")
