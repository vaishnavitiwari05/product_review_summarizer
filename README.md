# Product Review Intelligence
### LLM-Based Product Review Summarization Tool — a hybrid NLP + LLM system

Upload thousands of raw product reviews and get back a concise, sentiment-balanced, **evidence-checked** summary:
what customers like, what they dislike, which aspects matter most, which complaints keep coming back, and whether
the AI-written summary is actually supported by the data.

```
Raw reviews → Cleaning → Sentiment → Aspects → Recurring opinions → LLM synthesis → Evidence validation → Dashboard
```

> **Quick start (no API key, no downloads):** `docker compose up --build`, open http://localhost:8080, click
> **Try sample data**, then **Analyze**. Local (non-Docker) steps are in [section 7](#7-installation).

---

## Table of contents
1. [Project overview](#1-project-overview)
2. [Problem statement](#2-problem-statement)
3. [Proposed solution](#3-proposed-solution)
4. [Architecture](#4-architecture)
5. [Workflow](#5-workflow)
6. [Technology stack](#6-technology-stack)
7. [Installation](#7-installation)
8. [Environment variables](#8-environment-variables)
9. [How to run the backend](#9-how-to-run-the-backend)
10. [How to run the frontend](#10-how-to-run-the-frontend)
11. [How to upload data](#11-how-to-upload-data)
12. [How the NLP pipeline works](#12-how-the-nlp-pipeline-works)
13. [How the LLM is used](#13-how-the-llm-is-used)
14. [How validation works](#14-how-validation-works)
15. [Example output](#15-example-output)
16. [Future scope](#16-future-scope)
- [Testing and verification status](#testing-and-verification-status) · [API reference](#api-reference) · [Project structure](#project-structure) · [Troubleshooting](#troubleshooting)

---

## 1. Project overview

Product Review Intelligence turns a CSV of customer reviews into a one-page analysis for **online shoppers**,
**product analysts** and **e-commerce businesses**. It answers:

- What do customers like? What do they dislike?
- Which aspects (battery, sound, price, …) are discussed most?
- Which complaints recur?
- What is the overall sentiment, and what is a short plain-language summary of the opinions?
- **Can the summary be trusted?** Every claim is checked against the computed statistics.

It is a working end-to-end application (FastAPI backend, React dashboard, database, real NLP processing, a
configurable LLM, a validation layer), not a mock-up. Nothing on the dashboard is a static value: all numbers
are computed from the uploaded file.

## 2. Problem statement

Popular products have thousands of reviews. Nobody reads them all, star averages hide the detail
("4.1★" does not say *the microphone is bad*), and the obvious automated shortcut, pasting every review into a
large language model, has three problems:

1. **Scale and cost.** Thousands of reviews do not fit in a prompt, and truncating or sampling silently skews the result.
2. **No grounding.** An LLM asked to "summarize" will happily write fluent text that over-states, under-states or
   invents what customers said, and nothing tells the reader when that happens.
3. **No numbers.** A paragraph cannot tell you *how many* customers complained, or whether a complaint is a
   widespread problem or two outliers.

## 3. Proposed solution

A **hybrid** pipeline in which classical NLP does the counting and the LLM only does the writing:

| Job | Done by | Why |
|---|---|---|
| Clean, de-duplicate, count | Pandas + rules | exact, reproducible |
| Sentiment (positive / neutral / negative) | pretrained model (RoBERTa), VADER fallback | measured from the text, never inferred from stars |
| Discover aspects, sentiment *per aspect* | spaCy + clause splitting | "great sound but terrible mic" is two opinions |
| Group paraphrases into recurring opinions | sentence embeddings (TF-IDF fallback) + clustering | "lasts all day" ≈ "battery life is amazing" |
| Write a readable summary | LLM, given **only the structured findings** (≈2–3 KB, independent of review count) | fluent prose without raw-review overload |
| Check the summary | rule-based **evidence validator** | catches unsupported or contradicted claims |

The LLM never sees the raw review set, and its output is treated as a *claim to be verified*, not as truth.

## 4. Architecture

```
User
 ↓
React Dashboard (Vite)                          frontend/
 ↓  HTTP / JSON  (CORS, or same-origin via Vite proxy / nginx)
FastAPI                                         backend/app/api, main.py
 ↓
Data Ingestion          (CSV → DataFrame)       services/ingestion.py
 ↓
Cleaning & Validation   (dedupe, noise)         services/cleaning.py, utils/text.py
 ↓
Sentiment + Aspect Analysis                     nlp/sentiment.py, nlp/clauses.py, nlp/aspects.py
 ↓
Aggregation             (recurring opinions)    nlp/opinions.py, nlp/embeddings.py
 ↓
LLM Synthesis           (structured payload)    llm/payload.py, prompts.py, client.py, summarizer.py
 ↓
Evidence Validator                              validation/validator.py
 ↓
Results  (SQLite / PostgreSQL)                  services/repository.py, models/db.py
 ↓
Dashboard
```

Design decisions worth knowing:

- **Background jobs with polling.** `POST /analyze` returns `202` and a `run_id`; the UI polls `GET /analyze/{run_id}`
  for the stage name and a 0–100 progress value. Analyses are serialised by a lock, so run the backend with **one worker**.
- **Every heavy component has a lightweight fallback** (VADER for the transformer, TF-IDF for sentence embeddings,
  a deterministic mock for the LLM). The whole app therefore runs offline, with no keys and no model downloads.
  `auto` mode tries the real component and falls back with a logged warning; the strict modes fail with a clear message.
- **Partial results survive failures.** If only the LLM step fails, sentiment, aspects and recurring opinions are
  kept and shown, with the error explained.
- **Portable database layer.** SQLAlchemy with generic column types: SQLite by default, PostgreSQL by changing one URL.

## 5. Workflow

1. **Load data**: upload a CSV (or click *Try sample data*). The server validates, cleans, de-duplicates and stores
   the reviews, and returns a data-quality report (rows, valid reviews, duplicates removed, warnings).
2. **Pick a product** from the selector (one file can contain many products).
3. **Analyze**: the server runs, with live progress: *Loading models → Sentiment → Aspects → Recurring opinions →
   AI summary → Validation*.
4. **Read the dashboard**: overview, sentiment, most-discussed aspects (click one for example quotes), pros,
   cons, recurring strengths, recurring issues, the AI summary and the **Evidence-backed / Needs Review** verdict
   with per-check details and every flagged statement.
5. Results are stored; reopening a product loads them from the database without re-running. *Re-analyze* replaces them.

## 6. Technology stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, **FastAPI**, Uvicorn, **Pandas**, SQLAlchemy 2, Pydantic 2, httpx |
| NLP | **spaCy** (`en_core_web_sm`), **VADER**, Hugging Face **Transformers** (`cardiffnlp/twitter-roberta-base-sentiment-latest`), **sentence-transformers** (`all-MiniLM-L6-v2`), scikit-learn (TF-IDF, agglomerative clustering) |
| LLM | Anthropic Messages API, or any OpenAI-compatible API (`LLM_PROVIDER=openai`, `LLM_BASE_URL`), plus an offline mock |
| Database | SQLite (default) / PostgreSQL 16 |
| Frontend | **React 18**, Vite 5, plain CSS, hand-written SVG charts (no chart library) |
| Testing | pytest, Vitest + Testing Library, live end-to-end and process-level scripts |
| Deployment | Docker, Docker Compose, nginx |

## 7. Installation

**Prerequisites:** Python 3.11+ (tests were run on 3.12–3.13; the Docker image uses 3.11), Node.js 20+ (22 tested). Docker is optional. PostgreSQL is optional (SQLite works out of the box).

### Option A: Docker (whole stack, PostgreSQL)
```bash
docker compose up --build        # open http://localhost:8080
```
Defaults to the lightweight NLP fallbacks and the mock LLM, so it needs no keys or model downloads.
Variants (see the header of `docker-compose.yml`):
```bash
INSTALL_ML=true SENTIMENT_BACKEND=auto EMBEDDING_BACKEND=auto docker compose up --build   # real transformer models (large image)
USE_MOCK_LLM=false LLM_API_KEY=your-key docker compose up --build                         # real LLM
```

### Option B: local development
```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-lite.txt                     # light: VADER + TF-IDF fallbacks
#   or: pip install -r requirements.txt                  # full: + torch, transformers, sentence-transformers
python -m spacy download en_core_web_sm
cp .env.example .env

# frontend
cd ../frontend
npm install
cp .env.example .env
```
CPU-only PyTorch is far smaller: `pip install torch --index-url https://download.pytorch.org/whl/cpu`.

## 8. Environment variables

Backend: `backend/.env` (copy from `.env.example`). **Never commit real keys.**

| Variable | Default | Meaning |
|---|---|---|
| `USE_MOCK_LLM` | `true` | `true` = offline demo summarizer (no key needed). Set `false` to call a real LLM. |
| `LLM_PROVIDER` | `anthropic` | `anthropic` or `openai` (also any OpenAI-compatible server). |
| `LLM_API_KEY` | *(empty)* | Your provider key. If `USE_MOCK_LLM=false` and this is empty, `/analyze` fails fast with a clear message. |
| `LLM_MODEL` | *(empty)* | Model name. Optional for `anthropic` (defaults to `claude-sonnet-5-5`); **required** for `openai`. |
| `LLM_BASE_URL` | *(empty)* | Custom API base URL, e.g. `http://localhost:11434/v1`. |
| `LLM_TIMEOUT_SECONDS` / `LLM_MAX_RETRIES` | `60` / `2` | Per-call timeout; retries (with backoff) for 429/5xx/timeouts. |
| `DATABASE_URL` | `sqlite:///./reviews.db` | e.g. `postgresql://postgres:postgres@localhost:5432/reviews`. |
| `SENTIMENT_BACKEND` | `auto` | `auto` (model, falls back to VADER) · `transformer` (strict) · `vader`. |
| `SENTIMENT_MODEL` / `SENTIMENT_BATCH_SIZE` | RoBERTa sentiment model / `32` | Hugging Face model id; inference batch size. |
| `EMBEDDING_BACKEND` | `auto` | `auto` (sentence-transformers, falls back to TF-IDF) · `sbert` (strict) · `tfidf`. |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Hugging Face model id. |
| `MAX_UPLOAD_MB` | `25` | Upload size limit (413 above it). nginx's limit (30 MB) must stay ≥ this. |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated browser origins allowed to call the API. |
| `SAMPLE_DATA_PATH` | `../data/sample_reviews.csv` | CSV loaded by `POST /sample`. |

Frontend: `frontend/.env`

| Variable | Default | Meaning |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8000` | Backend address. **Empty** = same origin (the Vite dev proxy or nginx forwards API calls, so no CORS is involved). |
| `VITE_PROXY_TARGET` | `http://localhost:8000` | Where the Vite dev proxy forwards to (only used when `VITE_API_URL` is empty). |

## 9. How to run the backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000        # API docs: http://localhost:8000/docs · health: /health
```
Keep a **single worker**. Tables are created automatically on start-up. Runs left "running" by a crashed or
restarted server are marked *interrupted* on the next start.

## 10. How to run the frontend

```bash
cd frontend
npm run dev                                       # http://localhost:5173
npm run build && npm run preview                  # production bundle
```
The header shows **Demo mode · mock LLM** or **Live LLM** according to the backend's configuration.

## 11. How to upload data

Click **Upload CSV** (or drag a file onto the control bar), or **Try sample data**.

- **Format:** `.csv`, UTF-8 (UTF-8-BOM, cp1252 and latin-1 are also read), comma / semicolon / tab / pipe separated.
- **Only the review text is required.** Everything else degrades gracefully with a warning.
- **Recognised columns** (case-insensitive; aliases accepted):

| Canonical | Accepted names (examples) | If missing |
|---|---|---|
| `review` *(required)* | review, review_text, text, comment, body, content, feedback | upload rejected, listing the columns it found |
| `product_id` | product_id, asin, sku, item_id | generated from the product name |
| `product_name` | product_name, product, title, name | falls back to the id, or "Unnamed Product" |
| `rating` | rating, stars, score, overall | no average rating; sentiment is unaffected (it never uses stars) |
| `review_date` | review_date, date, created_at, timestamp | no date range |

- Ratings outside 1–5 and unparseable dates are blanked with a warning (the review is kept).
- **Limits:** 25 MB by default (`MAX_UPLOAD_MB`), 200,000 rows.
- **Product ids are global:** uploading a file whose `product_id` already exists *replaces* that product's reviews
  and analysis. Re-uploading the same file is safe.
- **Extra columns** (brand, category, price, …) are tolerated and ignored; see [Future scope](#16-future-scope).
- Friendly errors are returned for: wrong file type, empty file, header-only file, missing review column,
  all-empty reviews, oversized file, unreadable CSV.

A 109-row demo file (`data/sample_reviews.csv`; headphones and a smartphone) is included. It contains positive,
negative and neutral reviews, repeated opinions, contradictory opinions, duplicates, blank reviews, a missing rating,
a missing date and a review full of HTML, a URL and emoji. `python data/check_sample.py` validates it.

## 12. How the NLP pipeline works

**1. Ingestion** (`services/ingestion.py`). Checks the extension and size, decodes the text, sniffs the delimiter
(restricted to `, ; tab |`, since unrestricted sniffing mis-parses single-column files), maps column aliases, coerces
ratings and dates, and produces a validation report with counts and warnings.

**2. Cleaning** (`services/cleaning.py`, `utils/text.py`). Removes HTML tags, URLs, emails and emoji; normalises Unicode,
quotes and whitespace; collapses `!!!` and `soooooo`. Casing and punctuation are kept (sentiment models use them).
Blank and noise-only reviews are dropped. Duplicates are removed **per product**: exact (ignoring case/punctuation/spacing)
and near-duplicates (same words, different order). A warning is raised when ≥40% of reviews are duplicates.
The original text is kept (`review_raw`) for showing evidence.

**3. Sentiment** (`nlp/sentiment.py`). A pretrained 3-class model labels each review *from its text*. Stars are never an
input; they are only used for a diagnostic "text agrees with the stars X% of the time". A rule-based VADER backend
(thresholds ±0.25) is the offline fallback. Overall sentiment comes from net sentiment (% positive − % negative):
≥40 *Positive*, ≥15 *Mostly Positive*, within ±15 *Mixed*, ≤−15 *Mostly Negative*, ≤−40 *Negative*.

**4. Aspect extraction** (`nlp/clauses.py`, `nlp/aspects.py`). Aspects are **discovered from the data**, not looked up:
1. Reviews are split into clauses ("Sound is great **but** the mic is terrible" → two clauses).
2. spaCy tags each clause; noun sequences are collected, with fixes for words the small tagger mislabels
   (clause-initial "mic", gerund subjects like "Pairing is terrible", compounds like "sound quality").
3. Candidates are normalised: lemmas, generic suffixes stripped ("battery life" → battery), a small synonym map
   (mic → microphone, display → screen), adjective-implied aspects (comfortable → comfort), and stop-nouns removed.
4. A candidate becomes an **aspect** only if enough distinct reviews mention it: `max(3, 3% of reviews)`.
5. Every clause is scored on its own, and clause scores are combined per (review, aspect). For lexicon-based scorers
   the aspect word itself is masked first, because VADER rates the word "support" as positive.
6. Output per aspect: frequency, positive / neutral / negative counts, polarity, and example clauses.

**5. Recurring-opinion aggregation** (`nlp/opinions.py`, `nlp/embeddings.py`). For each (aspect, polarity) group that
reaches the minimum count (`max(3, 3%)`), clauses are embedded and clustered (agglomerative, cosine distance) into
*themes*: "battery lasts all day", "battery backup is excellent" and "battery life is amazing" collapse into one
recurring **strength**; "mic is terrible", "microphone quality is poor" and "voice sounds unclear" into one recurring
**issue**. An aspect with both a strength and an issue is flagged **contested**. Clustering is capped at 1,500 clauses per
group (sampled, counts scaled) to bound memory.

## 13. How the LLM is used

The LLM is the *last* step and sees **only structured findings** (`llm/payload.py`), never the review set:

```json
{ "product": "AuraBeat X1 Wireless Headphones", "total_reviews_analyzed": 67, "average_rating": 3.48,
  "sentiment": { "positive_pct": 58.2, "neutral_pct": 17.9, "negative_pct": 23.9, "overall": "Mostly Positive" },
  "major_aspects": [ { "aspect": "microphone", "reviews_mentioning": 10, "positive": 1, "neutral": 2, "negative": 7 } ],
  "recurring_strengths": [ { "aspect": "sound", "positive_mentions": 14, "opposite_mentions": 0,
                             "typical_phrases": ["Sound was great at first", "Sound is good"] } ],
  "recurring_issues":    [ { "aspect": "microphone", "negative_mentions": 7, "opposite_mentions": 0,
                             "typical_phrases": ["Mic is horrible", "Mic sounds terrible"] } ] }
```

- The payload is bounded (top 8 aspects, top 5 strengths and issues, ≤2 short phrases each), so it stays at roughly **2–3 KB whether
  there are 70 reviews or 70,000**. (`opposite_mentions` is the other side's count for *contested* aspects, so the model can tell a
  genuine strength from a mixed one.)
- The system prompt tells the model to use only the findings, not to praise an aspect with more negative than positive
  mentions (or vice-versa), to match the computed overall sentiment, to include strong recurring issues, to quote numbers
  only as given, and to treat phrases from reviews as untrusted data (a prompt-injection guard).
- It returns JSON with the six required outputs: **overall summary, key pros, key cons, recurring issues,
  important aspects, sentiment explanation**.
- **Providers:** Anthropic or OpenAI-compatible, selected by environment variables. Transient failures (429 / 5xx /
  timeouts) are retried with backoff; invalid JSON gets one automatic repair attempt; a rejected key, unknown model or
  bad request fails immediately with a friendly message. API keys are never echoed.
- **Missing key:** with `USE_MOCK_LLM=false` and no `LLM_API_KEY`, `/analyze` returns `400 llm_api_key_missing` with
  instructions *before* any work is queued.
- **Mock mode** (`USE_MOCK_LLM=true`, the default) builds the same JSON deterministically from the statistics so the
  whole dashboard can be demonstrated offline. It is labelled "Demo summary" in the UI.
- If the LLM step fails, the run is marked failed *at the summary step*, but sentiment, aspects and recurring opinions
  are still saved and shown.

## 14. How validation works

The summary is **never trusted**. `validation/validator.py` checks it against the computed statistics (rule-based,
deterministic, explainable):

| Check | What it verifies |
|---|---|
| **Overall sentiment** | The sentiment stated in the text agrees with the computed label. Positive vs negative is a *fail*; overstating ("overwhelmingly positive" for *Mostly Positive*) is a *warning*. |
| **Pros** | Each pro maps to an aspect with enough positive evidence. |
| **Cons / recurring issues** | Each con maps to an aspect with enough negative evidence (for the *recurring issues* list, repetition of the complaint is the test). |
| **Summary text** | Opinion statements about an aspect in the prose are judged clause by clause, handling negation ("not great") and hedging ("some users"). |
| **Quoted figures** | Every percentage, count and star rating quoted must match a computed value. |
| **Omissions** | Major recurring issues must be presented *as problems*. Praising the microphone does not cover a microphone complaint. |

Each statement gets a status: **supported · weak · unverified** (no analysed aspect matches, so it cannot be checked) **·
unsupported · contradicted**, with the counts and example review text behind it. The score gives full credit for supported,
half for weak/unverified, none for unsupported/contradicted. The verdict is **Evidence-backed** when no check fails and
the score is ≥ 75, otherwise **Needs Review**.

Example from the spec: data says *microphone: 7 negative, 1 positive*; a summary saying "customers generally love the
microphone" is flagged **contradicted** and the verdict becomes *Needs Review*.

Limits: the cue-word lists are English-only and hand-built; sarcasm is not understood; claims about things the
aspect extractor did not discover can only be marked *unverified*.

## 15. Example output

Real output for the bundled sample data (headphones; VADER + TF-IDF backends and the mock LLM, i.e. the default offline setup):

```
UPLOAD            109 rows → 2 empty, 4 duplicates removed → 103 valid reviews
PRODUCT           AuraBeat X1 Wireless Headphones · 67 reviews · average 3.48★ · Jan 2024 – Dec 2025
SENTIMENT         58.2% positive · 17.9% neutral · 23.9% negative → Mostly Positive (net +34.3)

MOST DISCUSSED ASPECTS               mentions  positive  neutral  negative
  Sound                                  16        14        2        0
  Battery                                13        10        3        0
  Comfort                                12        12        0        0
  Microphone                             10         1        2        7
  Price                                   8         6        1        1
  Durability                              5         1        1        3

RECURRING STRENGTHS   Sound ×14 · Comfort ×12 · Battery ×10 · Price ×6
RECURRING ISSUES      Microphone ×7 · Durability ×3 · Hinge ×3

AI SUMMARY   Customers are mostly positive about AuraBeat X1 Wireless Headphones: 58% of 67 reviews are
             positive and 24% negative. Most praised: sound, comfort, battery. Main concerns: microphone,
             durability, hinge.
PROS         Sound: 14 positive mentions (88% of reviews that discuss it) · Comfort: 12 … · Battery: 10 …
CONS         Microphone: 7 negative mentions (70% …) · Durability: 3 … · Hinge: 3 …

EVIDENCE VALIDATION   ✓ Evidence-backed · 100/100
                      pass: sentiment · pros · cons · summary text · quoted figures · omissions
```

The same data with a deliberately wrong summary ("overwhelmingly positive… love the microphone… 92% positive…", ignoring the
microphone complaints) gives **Needs Review, 22/100**: the microphone claims are *contradicted* (7 negative vs 1 positive),
"great touch controls" is *unverified*, "92%" matches no computed figure, and the recurring microphone issue is ignored.
Try it: `cd backend && python scripts_demo_validation.py P001 --flawed`.

## 16. Future scope

- **Product metadata.** Extra CSV columns (brand, category, price, image URL) are currently tolerated but ignored; storing and showing them is the main unimplemented input feature.
- **More sources:** JSON / Excel upload, review-site APIs, scheduled re-ingestion.
- **Better models:** fine-tuned aspect-based sentiment (ABSA), multilingual support, sarcasm handling, a learned (NLI / cross-encoder) claim verifier alongside the rule-based one.
- **Trends over time:** sentiment and aspect trends by month, release-version comparison, and alerts when a new complaint starts to recur.
- **Product comparison:** side-by-side analysis of competing products.
- **Fake-review detection:** burst and similarity analysis beyond duplicate removal.
- **Accounts and sharing:** authentication, per-user workspaces, exportable PDF/CSV reports.
- **Scaling:** a job queue (Celery / RQ) with multiple workers, streaming progress (SSE/WebSocket) instead of polling, caching of embeddings.

---

## Testing and verification status

What was run, and what was **not** (so nothing here is a surprise):

| Suite | Command | Count |
|---|---|---|
| Backend unit + API tests | `cd backend && python -m pytest tests -q` | 142 |
| Frontend component + flow tests (mocked `fetch`) | `cd frontend && npm test` | 30 |
| Live end-to-end (real server, real HTTP) | `./scripts/e2e.sh` | 10 |
| Process-level robustness (kill -9 mid-analysis, concurrent runs, bad key, oversize, garbage file) | `python scripts/robustness_live.py` | 16 checks |
| Scale / accuracy benchmark vs synthetic ground truth | `python scripts/benchmark.py --reviews 5000` (needs a running backend) | see below |

**Benchmark** (offline backends: VADER + TF-IDF + mock LLM; measured in the build sandbox; hardware unknown, so treat as relative):

| Reviews in file | Valid after cleaning | Whole run (upload + 3 products) | Peak server memory | Aspects with correct dominant polarity |
|---|---|---|---|---|
| 5,000 | 4,694 | 11 s | ≈ 345 MB | 23 / 27 |
| 20,000 | 17,809 | 33 s | ≈ 385 MB | 22 / 27 |

Time scales roughly linearly. The synthetic reviews use common opinion vocabulary, so the accuracy figure is optimistic for
messy real-world text, and most misses come from VADER labelling mild negatives as neutral (the transformer backend should
do better but was not measured).

**Not verified in the build environment** (please check these on your machine): the Hugging Face transformer and
sentence-embedding models (blocked there; the offline fallbacks were used); **PostgreSQL** (SQLite was used throughout);
the **Docker build and compose stack** (no Docker available; YAML syntax was validated); real LLM *summaries* (a real call with an
invalid key was verified, giving a clean `llm_auth_failed`; no valid key was available); and the UI in a **real browser**
(layout, dark mode and mobile widths are untested; tests run in a simulated DOM).

## API reference

| Method & path | Purpose |
|---|---|
| `GET /health` | status, LLM mode/readiness, database, active NLP backends |
| `POST /upload` | multipart CSV → validate, clean, store. Returns `validation`, `cleaning`, `uploaded_product_ids`, `products` |
| `POST /sample` | load the bundled demo dataset (same response as `/upload`) |
| `GET /products` | stored products with review count, average rating, `analyzed` flag |
| `POST /analyze` `{"product_id": "..."}` | start a background analysis → `202` + `run_id` (reuses a run already in progress) |
| `GET /analyze/{run_id}` | `status` (queued/running/done/failed), `stage`, `progress` 0–100, `error` |
| `GET /results/{product_id}` | product, sentiment, aspects, recurring strengths/issues, contested aspects, summary, validation, run info |

Errors always look like `{"error": "<code>", "message": "<human text>", "details": {...}}`, for example
`missing_columns`, `unsupported_file`, `file_too_large` (413), `product_not_found` (404), `not_analyzed` (404),
`llm_api_key_missing` (400), `llm_unavailable` (503), `llm_auth_failed` (502). Interactive docs: `/docs`.

## Project structure

```
product-review-summarizer/
├── backend/
│   ├── app/
│   │   ├── main.py                 app, error handlers, start-up (creates tables, fails stale runs)
│   │   ├── api/routes.py           HTTP endpoints
│   │   ├── models/                 db.py (ORM tables) · schemas.py (report dataclasses)
│   │   ├── services/               ingestion · cleaning · sentiment_service · pipeline · analysis_service · repository
│   │   ├── nlp/                    sentiment · clauses · aspects · embeddings · opinions
│   │   ├── llm/                    payload · prompts · client · summarizer · mock · schemas
│   │   ├── validation/             validator · lexicon · matching · report
│   │   └── utils/                  config · database · errors · text · serialization
│   ├── tests/                      142 tests (ingestion, cleaning, sentiment, aspects, opinions, LLM, validation, API, robustness)
│   ├── scripts_demo_*.py           run any single pipeline stage from the command line
│   ├── requirements.txt            full install        requirements-lite.txt   light install
│   ├── Dockerfile · .env.example
├── frontend/
│   ├── src/                        App.jsx · api.js · hooks/useAnalysis.js · components/ · utils/ · styles.css
│   ├── src/__tests__/              component and flow tests (real API responses as fixtures)
│   ├── src/e2e/                    live tests against a running backend
│   ├── package.json · vite.config.js · Dockerfile · nginx.conf · .env.example
├── data/
│   ├── sample_reviews.csv          109-row demo dataset
│   ├── check_sample.py             validates the demo dataset
│   └── generate_synthetic.py       large synthetic datasets with ground truth (for scale/accuracy tests)
├── scripts/
│   ├── e2e.sh                      starts a real backend and runs the live end-to-end tests
│   ├── benchmark.py                upload → analyse → compare with ground truth, against a running backend
│   └── robustness_live.py          crash / concurrency / bad-key / oversize checks on real server processes
├── docker-compose.yml              PostgreSQL + backend + frontend (nginx)
└── README.md
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| UI banner: *Cannot reach the analysis server* | Backend not running, or wrong `VITE_API_URL`. Start `uvicorn app.main:app --port 8000`. |
| Browser console shows a CORS error | Add the frontend's address to `CORS_ORIGINS` in `backend/.env`, or set `VITE_API_URL=` (empty) to use the proxy. |
| *No LLM API key configured* | Set `USE_MOCK_LLM=true`, or set `LLM_API_KEY` (and `LLM_MODEL` for `openai`) and restart the backend. |
| *The sentiment model could not be loaded* | Only in strict mode (`SENTIMENT_BACKEND=transformer`): check internet access and that `transformers`/`torch` are installed, or use `auto`/`vader`. |
| *The spaCy English model is not installed* | `python -m spacy download en_core_web_sm`. |
| Uploading returns 413 | File larger than `MAX_UPLOAD_MB` (and nginx's `client_max_body_size` if you use Docker). |
| An analysis shows *interrupted* | The server restarted mid-run. Press **Re-analyze**. |
| Results look wrong for my data | Check the data-quality notes under the upload summary; try the transformer backends (`requirements.txt`, `SENTIMENT_BACKEND=auto`). |

> Insights are generated automatically from the uploaded reviews and checked against the review statistics; they are an aid to reading
> the reviews, not a guarantee.

## Attribution, originality checks and code walkthrough

- [`THIRD_PARTY.md`](THIRD_PARTY.md): every library, model and dataset with its license, which parts are original, and the automated originality checks that were run (`python scripts/check_duplicates.py`).
- [`docs/CODE_WALKTHROUGH.md`](docs/CODE_WALKTHROUGH.md): a module-by-module tour of the code, design decisions, honest limitations, likely viva questions with answers, and a five-minute demo script.
