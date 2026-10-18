# Code walkthrough

A guided tour of how the project works, written so you can explain every part in a demo or viva. Read it next to the
code: each section names the file and the function to open.

## 1. The idea in one paragraph

Thousands of reviews are too many to read, and asking an LLM to summarise them directly is expensive and unreliable.
So the system does the counting with classic NLP, hands the LLM only the **findings** (counts, percentages, a few typical
phrases), and then **checks the LLM's answer against those same numbers**. The LLM writes; the statistics decide what is true.

```
CSV -> ingestion -> cleaning -> sentiment -> aspects -> recurring opinions -> LLM summary -> evidence validator -> dashboard
```

## 2. Request flow (what happens when you press Analyze)

1. The React app calls `POST /analyze {product_id}`. The server creates a row in `analysis_runs` and returns a `run_id` at once (HTTP 202).
2. A background task (`services/analysis_service.py: run_analysis`) loads that product's reviews from the database and runs the pipeline, updating the run's `stage` and `progress` as it goes.
3. The browser polls `GET /analyze/{run_id}` every ~0.7 s and shows the stage and a progress bar.
4. When the run is `done`, the browser calls `GET /results/{product_id}` and draws the dashboard.

Progress values you will see: 3 loading, 8 models, 15 sentiment, 40 aspects, 62 opinion grouping, 68 saving, 72 AI summary, 90 validation, 100 done.
Only one analysis runs at a time (a lock), which keeps memory use predictable.

## 3. Module map

### Ingestion and cleaning
| File | What it does |
|---|---|
| `services/ingestion.py` | Validates the upload (extension, size, encoding, delimiter) and maps column names (`Review Text`, `stars`, `asin` ...) to `product_id, product_name, review, rating, review_date`. Only `review` is mandatory. Bad ratings or dates become empty with a warning instead of failing the file. |
| `utils/text.py` | `clean_text` strips HTML, URLs, emoji and repeated punctuation but keeps case and punctuation (sentiment models use them). `dedupe_key` and `token_signature` build the keys for duplicate detection. |
| `services/cleaning.py` | Removes empty reviews, noise-only reviews, **exact duplicates** (same text ignoring case and punctuation) and **near duplicates** (same set of words), always per product. Computes the dataset statistics. Warns if 40% or more of the reviews were duplicates. |

### NLP
| File | What it does |
|---|---|
| `nlp/sentiment.py` | One interface, two backends. `TransformerSentimentAnalyzer` (pretrained RoBERTa, 3 classes). `VaderSentimentAnalyzer` (rule-based fallback; neutral band is +-0.25 because VADER's default over-labels reviews). `get_analyzer` picks one from `SENTIMENT_BACKEND`. Star ratings are never used to decide sentiment. |
| `services/sentiment_service.py` | Adds a label to each review, then the counts, percentages and overall label from **net sentiment = %positive - %negative**: Positive (>= 40), Mostly Positive (>= 15), Mixed, Mostly Negative (<= -15), Negative (<= -40). |
| `nlp/clauses.py` | Splits a review into clauses at "but/however/although", semicolons, and at "and" / commas only when a new clause follows. This is what lets "sound is great but the mic is terrible" count as one positive and one negative. |
| `nlp/aspects.py` | **Aspect discovery.** spaCy tags each clause, noun sequences become candidates ("battery life" -> "battery", "mic" -> "microphone" through a small synonym map), and a candidate becomes an aspect only if at least `max(3, 3% of reviews)` different reviews mention it. Adjectives that name an aspect ("comfortable" -> comfort) are handled too. Each clause is scored for sentiment, so the same review can be positive on one aspect and negative on another. |
| `nlp/embeddings.py` | Turns clauses into vectors: sentence-transformers (semantic) or TF-IDF (word overlap, offline). |
| `nlp/opinions.py` | **Recurring opinions.** Groups mentions by (aspect, polarity); a group with at least `min_count` mentions is a **strength** (positive) or **issue** (negative); an aspect with both is **contested**. Inside a group, agglomerative clustering with cosine distance finds the typical phrasings ("Mic is horrible", "The mic is really bad"). Large groups are sampled at 1,500 clauses so clustering stays fast. |

### LLM
| File | What it does |
|---|---|
| `llm/payload.py` | Builds the **only** thing the LLM sees: sentiment split, top 8 aspects with counts, top 5 strengths and issues with counts and 2 short phrases each, contested aspects. Its size stays about 2-4 KB whether there are 100 or 100,000 reviews. |
| `llm/prompts.py` | The instructions: use only the findings, do not praise an aspect with more negatives than positives, match the stated sentiment to the numbers, include strong recurring issues, treat review phrases as untrusted data, answer as JSON. |
| `llm/client.py` | Calls Anthropic or any OpenAI-compatible API with `httpx`. Retries timeouts and 429/5xx errors with exponential backoff; a bad key (401/403), unknown model (404) or rejected request fails at once. Error messages never contain the key. |
| `llm/summarizer.py` | Chooses mock or live mode, checks the key exists, parses the JSON, and makes **one repair attempt** if the model answers with something that is not valid JSON. |
| `llm/mock.py` | A deterministic offline summariser built from the same payload, so the full dashboard works with no API key. |

### Validation
| File | What it does |
|---|---|
| `validation/lexicon.py` | Reads the direction of a sentence (positive / negative, with negation such as "not great" and hedging such as "some users"). |
| `validation/matching.py` | Finds which analysed aspects a sentence is talking about ("audio quality" -> sound). |
| `validation/validator.py` | Five checks: (1) stated sentiment vs computed, (2) each pro/con/issue vs the aspect counts, (3) prose that contradicts the counts, (4) quoted percentages, counts and ratings that match no computed number, (5) major recurring issues left out. A claim is **supported / weak / unverified / unsupported / contradicted**. Verdict is **Needs Review** if any check fails or the score is under 75, otherwise **Evidence-backed**. |

### Storage and API
| File | What it does |
|---|---|
| `models/db.py` | Tables: uploads, products, reviews (with sentiment), aspects, insights, summaries, validations, analysis_runs. Only portable column types, so it runs on SQLite and PostgreSQL. |
| `services/repository.py` | All database reads and writes. Re-uploading a product replaces its data; re-analysing replaces its results. On startup `fail_stale_runs` marks runs that were "running" when the server died as interrupted. |
| `services/pipeline.py` | `analyze_product`: sentiment -> aspects -> opinions for one product, with a progress callback. |
| `api/routes.py`, `main.py` | Seven endpoints (`/upload /sample /products /analyze /analyze/{id} /results/{id} /health`) and one error format for everything: `{error, message, details}`. |

### Frontend
| File | What it does |
|---|---|
| `src/api.js` | The only place that calls `fetch`. Every failure becomes an `ApiError` with a readable message. |
| `src/hooks/useAnalysis.js` | All state and flows: load data, pick product, start analysis, poll progress, load results, handle errors. |
| `src/components/*` | One component per dashboard card: overview, sentiment donut (plain SVG), aspect bars, AI summary, pros/cons/issues, validation. No chart library. |

## 4. Design decisions you can defend

- **Hybrid, not LLM-only.** Counting is done deterministically and is checkable; the LLM only writes prose from a small structured payload.
- **Aspects are discovered, not listed.** Only the *clean-up* helpers (synonyms, stop words) are hand-written; which aspects exist is decided by the data.
- **Clause-level sentiment** because review-level sentiment hides mixed opinions.
- **Rule-based validator on purpose.** It is deterministic, free, and can show *why* a claim was flagged, with example review text. An LLM judging an LLM would be harder to trust and explain.
- **Two backends for sentiment and embeddings.** Real models when available, small offline fallbacks so the whole app and test suite run anywhere.
- **If the LLM fails, the NLP results are kept.** The dashboard still shows sentiment and aspects with a clear error.

## 5. Honest limitations (say these before they are asked)

- The VADER/TF-IDF fallbacks are weaker than the transformer models; the benchmark (23 of 27 aspects with the correct dominant polarity) was measured with the fallbacks on synthetic data and is optimistic for messy real reviews.
- The transformer and sentence-embedding backends, a live LLM summary, PostgreSQL, and the Docker stack were not run in the build sandbox. Test them on your machine.
- The validator checks consistency with the *extracted statistics*; if sentiment or aspect extraction is wrong, the validator inherits that error.
- English only. No login or per-user data. One server process by design.

## 6. Likely questions and short answers

**Why not send all reviews to the LLM?** Cost, context limits, and no way to verify the answer. Here the LLM sees about 2-4 KB of findings and its output is checked against them.

**How do you find aspects without a fixed list?** POS-tag clauses, collect noun phrases, normalise them, and keep those mentioned in at least 3% of reviews (minimum 3). The threshold scales with dataset size.

**How is "battery lasts all day" tied to "battery life is amazing"?** Both normalise to the aspect *battery* and are scored positive; clustering then groups their phrasings as a theme of that strength.

**How do you handle a review that praises one thing and criticises another?** Reviews are split into clauses; each clause is scored and attached to its aspect.

**What does "Evidence-backed" mean exactly?** No check failed and the score is at least 75: sentiment wording matches, pros and cons have enough supporting counts, no contradictions, numbers are real, and major complaints were not ignored.

**What if the LLM invents something?** An aspect that is not in the data is marked *unverified*; a wrong number is flagged by the numbers check; praise for an aspect customers mostly criticise is marked *contradicted* and the verdict becomes Needs Review.

**How do you avoid duplicate or fake reviews skewing results?** Exact and near duplicates are removed per product, and a warning appears when 40% or more were duplicates.

**Why SQLite and PostgreSQL?** SQLite needs no setup for development; the schema uses portable types and `DATABASE_URL` switches to PostgreSQL.

**What happens if the server crashes mid-analysis?** On restart the unfinished run is marked failed ("interrupted"), the uploaded data is intact, and you can re-run. This is covered by `scripts/robustness_live.py` (a real `kill -9`).

**How is this tested?** 142 backend tests, 30 frontend tests, 10 live end-to-end tests against a running server, 16 process-level robustness checks, and a benchmark against synthetic ground truth. See "Testing and verification status" in the README for what was *not* verified.

**What would you improve next?** Per-aspect trends over time, multilingual support, a trained aspect-sentiment model, authentication, and a proper job queue instead of an in-process background task.

## 7. A five-minute demo script

1. Open the dashboard, click **Try sample data**: show the upload summary (109 rows -> 103 valid, 4 duplicates, 2 empty).
2. Pick the headphones, click **Analyze**: point at the progress stages.
3. Walk down the dashboard: overview, sentiment donut, aspect bars (click *Microphone* for example quotes), pros/cons, recurring issues.
4. Open **Evidence validation**: show the score and the checks, then "Show all checked statements".
5. Upload a CSV with no review column to show the friendly error; mention that with the LLM switched on but no key, the app says so before starting.
