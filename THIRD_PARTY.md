# Third-party software, models and data

This file lists everything in the project that was **not written for it**, with its license, and states what
was checked. Versions are the ones installed when this file was written (2026-10-07).

## 1. What is original

- The application code under `backend/app`, `backend/tests`, `frontend/src`, `scripts` and `data/*.py`
  was written for this project and is not taken from another repository or tutorial. This is the author's
  statement, supported (not proven) by the checks in section 6.
- The hand-written word lists are original work for this project: aspect normalisation (`backend/app/nlp/aspects.py`:
  `GENERIC_SUFFIXES`, `STOP_NOUNS`, `SYNONYMS`, `ADJ_ASPECTS`), claim-direction cue words
  (`backend/app/validation/lexicon.py`) and aspect aliases (`backend/app/validation/matching.py`).
- `data/sample_reviews.csv` and everything produced by `data/generate_synthetic.py` is **synthetic**: the review
  sentences were written for this project, and the products (AuraBeat, Nova S5, SonicPods, AeroBook, Lumina)
  are fictional. No real customer reviews or scraped data are included.

## 2. Python dependencies (installed via `requirements*.txt`)

| Package | Version | License |
|---|---|---|
| fastapi | 0.115.14 | MIT |
| starlette (via fastapi) | 0.46.2 | BSD-3-Clause |
| uvicorn | 0.32.1 | BSD-3-Clause |
| python-multipart | 0.0.32 | Apache-2.0 |
| pandas | 2.2.3 | BSD-3-Clause |
| numpy | 2.5.3 | BSD-3-Clause (and bundled permissive licenses) |
| python-dotenv | 1.0.1 | BSD-3-Clause |
| SQLAlchemy | 2.0.54 | MIT |
| psycopg2-binary | 2.9.13 | LGPL-3.0 with exceptions (used unmodified as a library) |
| pydantic | 2.13.5 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |
| vaderSentiment | 3.3.2 | MIT (includes the VADER lexicon) |
| spaCy | 3.8.16 | MIT |
| en_core_web_sm (spaCy model) | 3.8.0 | MIT |
| scikit-learn | 1.9.1 | BSD-3-Clause |
| pytest (tests only) | 9.1.1 | MIT |

Optional, installed only with the full `requirements.txt` (not present when this file was written, so their
licenses were **not** checked here; confirm on their PyPI pages): `transformers`, `torch`, `sentence-transformers`.

## 3. Pretrained models downloaded at run time (optional)

| Model | Used for | License / notes |
|---|---|---|
| `cardiffnlp/twitter-roberta-base-sentiment-latest` | transformer sentiment backend | **Not verified.** Read the license and the suggested citation on its Hugging Face model card before submitting. |
| `sentence-transformers/all-MiniLM-L6-v2` | embedding backend for opinion grouping | **Not verified.** Believed Apache-2.0; confirm on the model card. |

The default (offline) configuration uses VADER and TF-IDF and downloads neither model.

## 4. External services

The optional live summary calls an LLM provider API (Anthropic or an OpenAI-compatible server) chosen by the
user through environment variables. Use is governed by that provider's terms. No API key is stored in the repository.

## 5. Frontend dependencies

Direct dependencies: react 18.3.1, react-dom 18.3.1, vite 5.4.21, @vitejs/plugin-react 4.7.0, vitest 2.1.9,
jsdom 24.1.3, @testing-library/react 16.3.3, @testing-library/jest-dom 6.9.1, @testing-library/user-event 14.6.7
(all MIT).

License mix of every installed npm package (including transitive ones, all development-time except React):
MIT 156, ISC 7, Apache-2.0 4, BSD-2-Clause 2, BSD-3-Clause 2, MIT-0 1, CC-BY-4.0 1. The single CC-BY-4.0 package is
`caniuse-lite` (browser-support data used by the build tooling); it does not appear in the production bundle
(checked by searching `dist/assets`). If you redistribute `node_modules`, keep its attribution.

## 6. Automated originality checks that were run (2026-10-07)

| Check | Result |
|---|---|
| Scan of all source files for copy markers (`stackoverflow`, `github.com`, `copied from`, `adapted from`, copyright / license headers, author tags) | No hits in project code (one false positive: the phrase "taken from reviews" in an LLM prompt). |
| Every URL in the source | Only localhost, example domains used in tests, and the two LLM API base URLs. |
| Internal duplicate code, 8-line windows (`python scripts/check_duplicates.py`) | 0 repeated blocks across 89 files / about 4,460 significant lines. |
| Internal duplicate code, 6-line windows | 4 repeated blocks, all test or demo-script boilerplate. |

Re-run the duplicate check yourself with `python scripts/check_duplicates.py --window 8`.

## 7. What these checks do not show

- They look for copied markers and duplicated blocks **inside this repository**. They do not compare the code against
  every public repository, and nothing here certifies the result of an external plagiarism or AI-text detector.
- Common patterns (FastAPI route handlers, pandas calls, React hooks) naturally resemble code in documentation and
  tutorials. If your institution runs a similarity tool, expect matches on boilerplate like that.
