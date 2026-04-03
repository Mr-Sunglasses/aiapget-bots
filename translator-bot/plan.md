
```
Build a Telegram bot called `BilingualBot` that converts Ayurvedic exam quiz DOCX and XLSX files into bilingual English+Hindi versions using the Claude API for translation.

---

## CONTEXT

These are Ayurveda/medical exam quiz files for a test series called "Sangharsh 2026".
Content is a mix of Sanskrit, Hindi, and English — domain-specific Ayurvedic terminology.
Files come in pairs: one .docx (for a custom parser) + one .xlsx (for a quiz platform importer).
Both contain the same 25 questions and must stay in sync.

Target scale: ~100 DOCX + 100 XLSX files total. Budget: ~$1 total.

---

## DOCX FORMAT (parser-critical, structure must be exact)

Each question block in plain text:

```
 #English_directions
 #Question 1 

[1/25] @AIPGETMADEEASY
<Question text>

#Options ###A
<Option A>
###B
<Option B>
###C
<Option C>
###D
<Option D>
###E

#Correct_option
A

#Solution
<Solution text>

#tag
Quiz no. 01 Date 1/8/2025  Topic - Sushruta brief notes 1-8 संघर्ष 2026 TEST SERIES
```

XML rules (must be exact):
- Every field = plain `<w:p><w:r><w:t>text</w:t></w:r></w:p>`
- Multi-line content = `<w:br/>` inside the same `<w:r>`, NOT separate paragraphs
- Section header has special font runs (Courier New + Times Bold) — always copy from original, never regenerate
- `sectPr` (page size/margins) copied verbatim from original
- All XML namespaces copied from original document opening tag

---

## XLSX FORMAT

Single sheet "Questions", 21 columns A–U:

| Col | Header | Rule |
|-----|--------|------|
| A | S No. | Row number |
| B | SUBJECT | null |
| C | TOPIC | null |
| D | TAGS | Never translate |
| E | QUESTION TYPE | Always "SINGLECORRECT" |
| F | QUESTION TEXT | Bilingual |
| G–J | OPTION1–4 | Bilingual |
| K–P | OPTION5–10 | Always null |
| Q | RIGHT ANSWER | Integer 1/2/3/4 only |
| R | EXPLANATION | Never translate |
| S | CORRECT MARKS | Always 4 |
| T | NEGATIVE MARKS | Always 1 |
| U | DIFFICULTY | Always "Medium" |

Styling: header fill #4472C4, white bold Arial, wrap_text=True, freeze pane A2, data row height 80px.

---

## BILINGUAL RULES

### Never translate
- `#tag` line / TAGS column
- `#Solution` / EXPLANATION column (citation references like "Sushruta Sara pg 4, Su su 14/38")
- `#Correct_option` / RIGHT ANSWER
- Pure numbers or numeric combos: `12,8` / `2021-2026`
- Match codes: `A2 B1 C3` / `1b 2c 3a`
- Ayurvedic reference codes containing `Su su`, `pg`, `/` patterns

### Bilingual format
**Question text:**
- English dominant → add Hindi below: `"How many Yantra dosha?\nयंत्र दोष की संख्या कितनी है?"`
- Sanskrit/Hindi dominant → add English meaning in brackets inline: `"त्वक् विवर्णता (Discolouration of skin) is the lakshana of"`
- Multi-line questions → translate each meaningful segment

**Options:**
- Pure Sanskrit/Hindi → add English in brackets: `"शिशिर (Winter)"`
- Pure English → add Hindi in brackets: `"Laghu anna (लघु अन्न)"`
- True/False style → append slash+Hindi: `"(A) 1 incorrect 2 correct / 1 गलत 2 सही"`
- Numeric / match codes → leave untouched

---

## TRANSLATION: CLAUDE API

Use Claude to translate — NOT Google Translate.
Claude handles Sanskrit/Ayurvedic terminology far better than generic MT.

### Implementation

One API call per quiz file (all 25 questions in one prompt):

```python
import anthropic, json

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

def translate_quiz(questions: list[dict]) -> list[dict]:
    prompt = f"""You are an expert in Ayurvedic medicine and Sanskrit, helping make a medical exam quiz bilingual (English + Hindi).

Your task: take each question and return it with bilingual text added, following these exact rules.

BILINGUAL RULES:
1. Question text:
   - If English dominant → keep English, add Hindi translation on next line (separated by \\n)
   - If Sanskrit/Hindi dominant → add English meaning in brackets inline
   - Example A: "Number of Yantra dosha\\nयंत्र दोष की संख्या?"
   - Example B: "त्वक् विवर्णता (Discolouration of skin) is the lakshana of"

2. Options:
   - Pure Sanskrit/Hindi term → add English in brackets: "शिशिर (Winter)"
   - Pure English term → add Hindi in brackets: "Laghu anna (लघु अन्न)"
   - True/False style "(A) 1 incorrect 2 correct" → append "/ 1 गलत 2 सही"
   - Numbers, match codes (A2 B1 C3, 1b 2c 3a), numeric combos (12,8) → leave EXACTLY as-is

3. NEVER translate or modify:
   - solution field (it contains reference citations like "Sushruta Sara pg 4, Su su 14/38")
   - tag field
   - correct_answer field
   - Any field you are not explicitly asked to translate

4. Preserve all existing text — only ADD the translation, never remove or rephrase original.

INPUT (JSON array of questions):
{json.dumps(questions, ensure_ascii=False, indent=2)}

OUTPUT: Return ONLY a valid JSON array with the same structure. 
Each object must have these exact keys: num, question, options (dict A/B/C/D), correct_answer, solution, tag.
The question and options values should now be bilingual.
No explanation, no markdown, no code fences. Raw JSON only."""

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    return json.loads(raw)
```

### Caching (important for re-runs)
- Cache translation results in `.translation_cache.json`
- Key: `sha256(json.dumps(questions, sort_keys=True))`  ← hash of the entire quiz input
- On cache hit: skip API call entirely
- On cache miss: call API, store result, save cache
- This means re-processing the same file costs $0

### Cost tracking
- Log input + output tokens per call (from `response.usage`)
- Keep a running total in `.usage_log.json`: `{date, input_tokens, output_tokens, cost_usd}`
- Print cost summary after each file: `"💰 This call: ~$0.008 | Total so far: ~$0.23"`
- Pricing: input $3/M tokens, output $5/M tokens (Sonnet)

---

## PROJECT STRUCTURE

```
bilingual-bot/
├── bot/
│   ├── __init__.py
│   ├── main.py          # entrypoint, register handlers
│   ├── handlers.py      # Telegram handlers
│   ├── pipeline.py      # parse → translate → build → stats
│   ├── parser.py        # DOCX XML + XLSX → List[Question]
│   ├── translator.py    # Claude API call, cache, cost tracking
│   ├── builder.py       # write bilingual DOCX + XLSX
│   └── utils.py         # is_untranslatable(), esc_xml(), detect_script()
├── tests/
│   ├── conftest.py
│   ├── test_parser.py
│   ├── test_translator.py    # mock anthropic client
│   ├── test_builder.py
│   └── samples/
│       ├── sample.docx       # 3-question test docx
│       └── sample.xlsx       # matching xlsx
├── .env.example
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## DATA MODELS

```python
from dataclasses import dataclass, field

@dataclass
class Question:
    num: int
    serial: str                   # "1/25"
    question: str                 # raw text, \n for line breaks
    options: dict[str, str]       # {"A": "...", "B": "...", "C": "...", "D": "..."}
    correct_answer: str           # "A"/"B"/"C"/"D"
    solution: str                 # never translate
    tag: str                      # never translate
    para_indices: list[int]       # paragraph indices in DOCX XML

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
```

---

## MODULE SPECS

### parser.py
```python
def parse_docx(path: str) -> list[Question]
def parse_xlsx(path: str) -> list[Question]
```

**parse_docx:**
- Unzip DOCX, parse `word/document.xml` with lxml
- Walk `<w:p>` elements, join `<w:t>` text, replace `<w:br/>` with `\n`
- State machine:
  - ` #Question N ` → new question, record para index
  - text before `#Options` → question text  
  - `#Options ###A` → option A = next para
  - `###B/C/D/E` → next option
  - `#Correct_option` → next para is answer
  - `#Solution` → next para(s) until `#tag`
  - `#tag` → next para is tag
- Store all para indices for this question in `para_indices`

**parse_xlsx:**
- openpyxl, sheet "Questions", map columns by header name
- RIGHT ANSWER is integer: 1→A, 2→B, 3→C, 4→D (convert to letter for Question.correct_answer)
- Store original integer in a separate field for builder to write back

### translator.py
```python
def translate_quiz(questions: list[Question], cache_path: str, usage_log_path: str) -> tuple[list[TranslatedQuestion], PipelineStats]
```

- Serialize questions to JSON (only: num, question, options, correct_answer, solution, tag)
- Check cache by SHA256 hash of input JSON
- On miss: call Claude API with prompt above
- Parse JSON response → list of TranslatedQuestion
- Save to cache
- Log usage + cost
- Return results + stats

### builder.py
```python
def build_docx(source_path: str, questions: list[TranslatedQuestion], output_path: str) -> None
def build_xlsx(source_path: str, questions: list[TranslatedQuestion], output_path: str) -> None
```

**build_docx:**
- Unzip source to tempdir
- Parse `word/document.xml` with lxml
- For each TranslatedQuestion, use `para_indices` to locate correct paragraphs
- Question text para: append `<w:br/><w:t xml:space="preserve">hindi line</w:t>` inside same `<w:r>`
- Option paras: replace `<w:t>` text with bilingual string
- Solution / tag paras: never touch
- Section header para (###Section AYURVEDA): copy verbatim, never touch
- Rezip entire DOCX, preserving all other files unchanged
- Output → output_path

**build_xlsx:**
- Load source with openpyxl
- For each data row: overwrite F (QUESTION TEXT) and G–J (OPTION1–4) with bilingual strings
- RIGHT ANSWER: write back as original integer
- All other cells, styles, widths: preserve exactly
- Save → output_path

### handlers.py

**Pairing flow:**
1. User sends `.docx` → bot replies:
   `"📄 Got your DOCX (Quiz_01.docx). Send the matching .xlsx now, or /skip to convert DOCX only."`
2. Bot stores pending docx in `context.user_data["pending_docx"]` with timestamp
3. User sends `.xlsx` within 10 minutes → process both, reply with both files
4. User sends `/skip` → process docx only
5. Pending expires after 10 min → auto-clear, notify user
6. User sends `.xlsx` first → same flow in reverse

**On completion, send:**
- The output file(s) as documents
- Stats message:
  `"✅ 25 questions converted\n💰 Cost: ~$0.008 | Tokens: 1,840 in / 1,120 out\n📦 Cached: No"`

**Errors:**
- Wrong type: `"❌ Please send a .docx or .xlsx file"`
- Too large (>20MB): `"❌ File too large (max 20MB)"`
- Zero questions: `"❌ Could not find any questions. Is this the correct format?"`
- JSON parse failure from Claude: retry once, then `"⚠️ Translation failed. File returned as-is."`
- Any crash: `"❌ Something went wrong. Please try again."`

---

## ENVIRONMENT

### .env.example
```
BOT_TOKEN=your_telegram_bot_token
ANTHROPIC_API_KEY=your_anthropic_api_key
TRANSLATION_CACHE_PATH=.translation_cache.json
USAGE_LOG_PATH=.usage_log.json
MAX_FILE_SIZE_MB=20
```

### requirements.txt
```
python-telegram-bot==20.7
anthropic==0.25.0
lxml==5.1.0
openpyxl==3.1.2
python-dotenv==1.0.0
```

### Dockerfile
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "bot.main"]
```

---

## TESTS

### test_translator.py (mock anthropic)
- Mock `anthropic.Anthropic().messages.create` to return fixed JSON
- Assert: solution and tag fields are never in the prompt's translatable content
- Assert: cache hit on second call with identical questions → zero API calls
- Assert: numeric-only options pass through unchanged
- Assert: cost calculated correctly from mock token counts

### test_parser.py
- Parse `samples/sample.docx` → assert question count, para_indices populated, \n preserved
- Parse `samples/sample.xlsx` → assert RIGHT ANSWER converted to letter, options has A–D keys

### test_builder.py
- Build docx from known TranslatedQuestion → re-parse → assert bilingual text present in question
- Build xlsx → re-read → assert QUESTION TEXT has \n, RIGHT ANSWER is still integer
- Assert: tag line never modified in either format

---

## README sections
1. What this bot does
2. Setup: clone → pip install → fill .env (BOT_TOKEN + ANTHROPIC_API_KEY)
3. Getting a Telegram bot token (BotFather steps)
4. Getting an Anthropic API key (console.anthropic.com)
5. Local run: `python -m bot.main`
6. Docker deploy: build + run command
7. Usage: send DOCX → send XLSX → get both back
8. Cost reference: 100 quizzes × $0.01 = ~$1 total
9. File format reference: DOCX parser format, XLSX column map
```

Note: Use python uv for packaging and also create makefile