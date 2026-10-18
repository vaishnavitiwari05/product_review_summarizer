"""Phase 4: apply sentiment to a cleaned DataFrame and summarise it."""
from __future__ import annotations

import pandas as pd

from app.nlp.sentiment import SentimentAnalyzer, get_analyzer

# Net sentiment = %positive - %negative
OVERALL_BANDS = [(40, "Positive"), (15, "Mostly Positive"), (-15, "Mixed"), (-40, "Mostly Negative")]


def overall_label(pos_pct: float, neg_pct: float) -> str:
    net = pos_pct - neg_pct
    for threshold, label in OVERALL_BANDS:
        if net >= threshold:
            return label
    return "Negative"


def add_sentiment(df: pd.DataFrame, analyzer: SentimentAnalyzer | None = None) -> pd.DataFrame:
    """Adds sentiment, sentiment_score (-1..1), sentiment_confidence columns."""
    analyzer = analyzer or get_analyzer()
    out = df.copy()
    preds = analyzer.predict(out["review_clean"].tolist()) if len(out) else []
    out["sentiment"] = [p.label for p in preds]
    out["sentiment_score"] = [p.score for p in preds]
    out["sentiment_confidence"] = [p.confidence for p in preds]
    out.attrs["sentiment_backend"] = analyzer.name
    return out


def _rating_agreement(df: pd.DataFrame) -> dict:
    """Diagnostic only: how often text sentiment and stars disagree strongly.
    Ratings NEVER feed into the sentiment label."""
    r = pd.to_numeric(df["rating"], errors="coerce")
    rated = df[r.notna()]
    if rated.empty:
        return {"rated_reviews": 0, "agreement_pct": None, "mismatches": 0}
    rr = r[r.notna()]
    expected = pd.Series("neutral", index=rated.index)
    expected[rr >= 4] = "positive"
    expected[rr <= 2] = "negative"
    agree = (expected == rated["sentiment"])
    strong = ((rr >= 4) & (rated["sentiment"] == "negative")) | ((rr <= 2) & (rated["sentiment"] == "positive"))
    return {"rated_reviews": int(len(rated)), "agreement_pct": round(float(agree.mean() * 100), 1),
            "mismatches": int(strong.sum())}


def summarize_sentiment(df: pd.DataFrame) -> dict:
    n = len(df)
    counts = {k: int((df["sentiment"] == k).sum()) for k in ("positive", "neutral", "negative")}
    pct = {k: round(v / n * 100, 1) if n else 0.0 for k, v in counts.items()}
    return {
        "total": n,
        "counts": counts,
        "percentages": pct,
        "overall": overall_label(pct["positive"], pct["negative"]) if n else "Unknown",
        "net_sentiment": round(pct["positive"] - pct["negative"], 1),
        "average_score": round(float(df["sentiment_score"].mean()), 3) if n else 0.0,
        "backend": df.attrs.get("sentiment_backend", "unknown"),
        "rating_check": _rating_agreement(df) if n else {},
    }
