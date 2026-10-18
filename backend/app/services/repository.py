"""All database reads/writes (kept out of the routes and the NLP code)."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models.db import (Aspect, AnalysisRun, Insight, Product, Review, Summary, Upload, Validation)
from app.models.schemas import CleaningStats, ValidationReport
from app.utils.errors import DataValidationError
from app.utils.serialization import jsonable


def _none_if_nan(v):
    return None if v is None or (isinstance(v, float) and v != v) else v


# ------------------------------------------------------------------ upload
def save_upload(s: Session, filename: str, report: ValidationReport, stats: CleaningStats,
                raw_counts: dict, clean_df: pd.DataFrame) -> Upload:
    up = Upload(filename=filename, validation=jsonable(report.to_dict()), cleaning=jsonable(stats.to_dict()))
    s.add(up)
    s.flush()
    for pid, g in clean_df.groupby("product_id", sort=False):
        pid = str(pid)
        s.execute(delete(Product).where(Product.product_id == pid))     # replaces old data (cascade)
        s.execute(delete(AnalysisRun).where(AnalysisRun.product_id == pid))
        s.flush()
        rating = pd.to_numeric(g["rating"], errors="coerce").dropna()
        dates = pd.to_datetime(g["review_date"], errors="coerce").dropna()
        s.add(Product(
            product_id=pid, product_name=str(g["product_name"].iloc[0]), upload_id=up.id,
            raw_reviews=int(raw_counts.get(pid, len(g))), review_count=int(len(g)),
            avg_rating=round(float(rating.mean()), 2) if len(rating) else None,
            date_min=dates.min().strftime("%Y-%m-%d") if len(dates) else None,
            date_max=dates.max().strftime("%Y-%m-%d") if len(dates) else None))
        s.flush()
        rows = [{"product_id": pid, "text_clean": r.review_clean, "text_raw": r.review_raw,
                 "rating": _none_if_nan(None if pd.isna(r.rating) else float(r.rating)),
                 "review_date": None if pd.isna(r.review_date) else r.review_date.to_pydatetime()}
                for r in g.itertuples()]
        s.execute(Review.__table__.insert(), rows)
    s.commit()
    return up


def list_products(s: Session) -> list[dict]:
    last_runs = {}
    for run in s.scalars(select(AnalysisRun).order_by(AnalysisRun.created_at)):
        last_runs[run.product_id] = run
    out = []
    for p in s.scalars(select(Product).order_by(Product.product_name)):
        run = last_runs.get(p.product_id)
        out.append({"product_id": p.product_id, "product_name": p.product_name,
                    "review_count": p.review_count, "avg_rating": p.avg_rating,
                    "analyzed": p.analyzed_at is not None,
                    "analyzed_at": jsonable(p.analyzed_at),
                    "last_run": None if run is None else {"run_id": run.id, "status": run.status}})
    return out


# ------------------------------------------------------------------ runs
def create_run(s: Session, run_id: str, product_id: str) -> AnalysisRun:
    run = AnalysisRun(id=run_id, product_id=product_id)
    s.add(run)
    s.commit()
    return run


def active_run(s: Session, product_id: str) -> AnalysisRun | None:
    return s.scalars(select(AnalysisRun).where(AnalysisRun.product_id == product_id,
                                               AnalysisRun.status.in_(("queued", "running")))
                     .order_by(AnalysisRun.created_at.desc())).first()


def latest_run(s: Session, product_id: str) -> AnalysisRun | None:
    return s.scalars(select(AnalysisRun).where(AnalysisRun.product_id == product_id)
                     .order_by(AnalysisRun.created_at.desc())).first()


def run_dict(run: AnalysisRun) -> dict:
    return {"run_id": run.id, "product_id": run.product_id, "status": run.status, "stage": run.stage,
            "progress": run.progress, "error": run.error, "created_at": jsonable(run.created_at),
            "finished_at": jsonable(run.finished_at)}


def fail_stale_runs(s: Session) -> int:
    """Runs left 'queued'/'running' by a previous process can never finish: mark them failed."""
    res = s.execute(update(AnalysisRun).where(AnalysisRun.status.in_(("queued", "running"))).values(
        status="failed", stage="Interrupted", finished_at=datetime.now(timezone.utc),
        error={"error": "interrupted",
               "message": "The server restarted while this analysis was running. Please run it again."}))
    s.commit()
    return res.rowcount or 0


def update_run(s: Session, run_id: str, **fields) -> None:
    s.execute(update(AnalysisRun).where(AnalysisRun.id == run_id).values(**fields))
    s.commit()


# ------------------------------------------------------------------ analysis input / output
def load_product_df(s: Session, product_id: str) -> pd.DataFrame:
    p = s.get(Product, product_id)
    if p is None:
        raise DataValidationError("product_not_found", f"Unknown product '{product_id}'.", status_code=404)
    rows = s.scalars(select(Review).where(Review.product_id == product_id).order_by(Review.id)).all()
    df = pd.DataFrame({
        "product_id": product_id, "product_name": p.product_name,
        "review_clean": [r.text_clean for r in rows], "review_raw": [r.text_raw for r in rows],
        "rating": [r.rating for r in rows], "review_date": [r.review_date for r in rows]},
        index=pd.Index([r.id for r in rows], name="review_id"))
    df["review"] = df["review_clean"]
    return df


def save_nlp_results(s: Session, product_id: str, f, meta: dict) -> None:
    """Persist sentiment, aspects and aggregated insights (replaces any previous analysis)."""
    for model in (Aspect, Insight, Summary, Validation):
        s.execute(delete(model).where(model.product_id == product_id))
    rv = f.reviews
    s.execute(update(Review), [
        {"id": int(i), "sentiment": r.sentiment, "sentiment_score": float(r.sentiment_score),
         "sentiment_confidence": float(r.sentiment_confidence)} for i, r in rv.iterrows()])
    for a in f.extraction.aspects:
        s.add(Aspect(product_id=product_id, aspect=a["aspect"], frequency=a["frequency"],
                     mention_pct=a["mention_pct"], positive=a["positive"], neutral=a["neutral"],
                     negative=a["negative"], avg_score=a["avg_score"], polarity=a["polarity"],
                     examples=jsonable(a["examples"])))
    for g in f.opinions.strengths + f.opinions.issues:
        s.add(Insight(product_id=product_id, kind=g["type"], aspect=g["aspect"], sentiment=g["sentiment"],
                      count=g["count"], share_of_aspect=g["share_of_aspect"],
                      share_of_reviews=g["share_of_reviews"], contested=g["contested"],
                      themes=jsonable(g["themes"]), examples=jsonable(g["examples"])))
    p = s.get(Product, product_id)
    p.sentiment = jsonable(f.sentiment)
    p.meta = jsonable({**meta, "contested": f.opinions.contested, "min_count": f.opinions.min_count,
                       "notes": f.notes})
    p.analyzed_at = datetime.now(timezone.utc)
    s.commit()


def save_summary_and_validation(s: Session, product_id: str, summary_result, payload: dict, report) -> None:
    s.add(Summary(product_id=product_id, mode=summary_result.mode, model=summary_result.model,
                  warnings=summary_result.warnings, content=jsonable(summary_result.summary.model_dump()),
                  payload=jsonable(payload)))
    s.add(Validation(product_id=product_id, verdict=report.verdict, score=report.score,
                     headline=report.headline, report=jsonable(report.to_dict())))
    s.commit()


# ------------------------------------------------------------------ results
def get_results(s: Session, product_id: str) -> dict:
    p = s.get(Product, product_id)
    if p is None:
        raise DataValidationError("product_not_found", f"Unknown product '{product_id}'.", status_code=404)
    if p.analyzed_at is None:
        raise DataValidationError("not_analyzed", "This product has not been analyzed yet. "
                                  "Run the analysis first.", status_code=404)
    aspects = s.scalars(select(Aspect).where(Aspect.product_id == product_id)
                        .order_by(Aspect.frequency.desc())).all()
    insights = s.scalars(select(Insight).where(Insight.product_id == product_id)
                         .order_by(Insight.count.desc())).all()
    summary = s.scalars(select(Summary).where(Summary.product_id == product_id)).first()
    val = s.scalars(select(Validation).where(Validation.product_id == product_id)).first()
    run = latest_run(s, product_id)

    def ins(i: Insight) -> dict:
        return {"aspect": i.aspect, "sentiment": i.sentiment, "count": i.count,
                "share_of_aspect": i.share_of_aspect, "share_of_reviews": i.share_of_reviews,
                "contested": i.contested, "themes": i.themes, "examples": i.examples}

    meta = p.meta or {}
    return jsonable({
        "product": {"product_id": p.product_id, "product_name": p.product_name,
                    "total_reviews": p.review_count, "rows_in_file": p.raw_reviews,
                    "removed_as_empty_noise_or_duplicate": p.raw_reviews - p.review_count,
                    "average_rating": p.avg_rating, "date_min": p.date_min, "date_max": p.date_max},
        "sentiment": p.sentiment,
        "aspects": [{"aspect": a.aspect, "frequency": a.frequency, "mention_pct": a.mention_pct,
                     "positive": a.positive, "neutral": a.neutral, "negative": a.negative,
                     "avg_score": a.avg_score, "polarity": a.polarity, "examples": a.examples} for a in aspects],
        "recurring_strengths": [ins(i) for i in insights if i.kind == "strength"],
        "recurring_issues": [ins(i) for i in insights if i.kind == "issue"],
        "contested_aspects": meta.get("contested", []),
        "summary": None if summary is None else {"mode": summary.mode, "model": summary.model,
                                                 "warnings": summary.warnings, **summary.content},
        "validation": None if val is None else {"verdict": val.verdict, "score": val.score,
                                                "headline": val.headline, **val.report},
        "analysis": {"analyzed_at": p.analyzed_at, "run": None if run is None else run_dict(run),
                     "sentiment_backend": meta.get("sentiment_backend"),
                     "embedding_backend": meta.get("embedding_backend"),
                     "duration_seconds": meta.get("duration_seconds"), "notes": meta.get("notes", [])},
    })
