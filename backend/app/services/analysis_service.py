"""Background analysis job: DB reviews -> NLP -> LLM -> validation -> DB, with progress reporting."""
from __future__ import annotations

import logging
import threading
import time
import uuid

from app.llm.summarizer import generate_summary
from app.services import repository as repo
from app.services.pipeline import analyze_product
from app.utils import config
from app.utils.database import session_scope
from app.utils.errors import DataValidationError
from app.validation.validator import validate_summary
from datetime import datetime, timezone

log = logging.getLogger(__name__)
_LOCK = threading.Lock()          # one analysis at a time keeps memory use predictable


def preflight() -> None:
    """Fail fast (before queueing) when the LLM is not usable."""
    cfg = config.settings
    if not cfg.use_mock_llm and not cfg.llm_api_key:
        raise DataValidationError(
            "llm_api_key_missing",
            "No LLM API key configured. Set LLM_API_KEY in backend/.env, "
            "or set USE_MOCK_LLM=true to use the offline demo mode.", status_code=400)


def new_run_id() -> str:
    return str(uuid.uuid4())


def _progress(run_id: str, stage: str, pct: int) -> None:
    with session_scope() as s:
        repo.update_run(s, run_id, status="running", stage=stage, progress=pct)


def _fail(run_id: str, err: dict) -> None:
    with session_scope() as s:
        repo.update_run(s, run_id, status="failed", error=err, stage="Failed",
                        finished_at=datetime.now(timezone.utc))


def run_analysis(run_id: str, product_id: str) -> None:
    """Never raises: every failure is stored on the run so the UI can show it."""
    try:
        with _LOCK:
            t0 = time.time()
            _progress(run_id, "Loading reviews", 3)
            with session_scope() as s:
                df = repo.load_product_df(s, product_id)
            findings = analyze_product(df, product_id, progress=lambda st, p: _progress(run_id, st, p))
            meta = {"sentiment_backend": findings.sentiment.get("backend"),
                    "embedding_backend": findings.opinions.embedder}
            _progress(run_id, "Saving analysis", 68)
            with session_scope() as s:
                repo.save_nlp_results(s, product_id, findings, meta)

            _progress(run_id, "Generating AI summary", 72)
            payload = findings.payload()
            try:
                result = generate_summary(payload, config.settings)
            except DataValidationError as exc:      # NLP results stay available without a summary
                with session_scope() as s:
                    p = s.get(repo.Product, product_id)
                    p.meta = {**(p.meta or {}), "duration_seconds": round(time.time() - t0, 1)}
                _fail(run_id, {**exc.to_dict(), "stage": "summary"})
                return

            _progress(run_id, "Validating summary against the data", 90)
            report = validate_summary(result.summary, findings)
            with session_scope() as s:
                repo.save_summary_and_validation(s, product_id, result, payload, report)
                p = s.get(repo.Product, product_id)
                p.meta = {**(p.meta or {}), "llm_mode": result.mode,
                          "duration_seconds": round(time.time() - t0, 1)}
                repo.update_run(s, run_id, status="done", stage="Complete", progress=100, error=None,
                                finished_at=datetime.now(timezone.utc))
    except DataValidationError as exc:
        _fail(run_id, exc.to_dict())
    except Exception:                                     # noqa: BLE001
        log.exception("Analysis run %s failed", run_id)
        _fail(run_id, {"error": "internal_error",
                       "message": "The analysis failed unexpectedly. Check the server logs and try again."})
