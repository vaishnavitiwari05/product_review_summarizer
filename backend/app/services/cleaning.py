"""Phase 3: cleaning, duplicate removal and dataset statistics.

Input : DataFrame from ingestion (canonical columns)
Output: cleaned DataFrame with extra columns
        review_clean  - readable cleaned text (used by NLP models)
        review_raw    - original text (used for evidence display)
plus CleaningStats.

Duplicates are detected PER PRODUCT (the same sentence on two products is legitimate).
The first occurrence is kept.
"""
from __future__ import annotations

import pandas as pd

from app.models.schemas import CleaningResult, CleaningStats
from app.utils.errors import DataValidationError
from app.utils.text import clean_text, dedupe_key, has_content, token_signature

HIGH_DUPLICATE_RATIO = 0.4


def _date_range(dates: pd.Series) -> tuple[str | None, str | None]:
    d = pd.to_datetime(dates, errors="coerce").dropna()
    if d.empty:
        return None, None
    return d.min().strftime("%Y-%m-%d"), d.max().strftime("%Y-%m-%d")


def dataset_stats(df: pd.DataFrame) -> dict:
    """Stats for any (already cleaned) frame - used per product on the dashboard."""
    rating = pd.to_numeric(df["rating"], errors="coerce").dropna()
    dmin, dmax = _date_range(df["review_date"])
    return {
        "total_reviews": int(len(df)),
        "average_rating": round(float(rating.mean()), 2) if len(rating) else None,
        "rated_reviews": int(len(rating)),
        "date_min": dmin,
        "date_max": dmax,
    }


def clean_dataframe(df: pd.DataFrame) -> CleaningResult:
    stats = CleaningStats(total_reviews=len(df))
    work = df.copy()
    work["review_raw"] = work["review"].astype(str)
    work["review_clean"] = work["review_raw"].map(clean_text)

    # 1. blank reviews
    blank = work["review_raw"].str.strip() == ""
    stats.empty_removed = int(blank.sum())
    work = work[~blank]

    # 2. noise: nothing meaningful left after cleaning
    noisy = ~work["review_clean"].map(has_content)
    stats.noise_removed = int(noisy.sum())
    work = work[~noisy]
    non_empty = len(work)

    # 3. exact duplicates (case / punctuation / whitespace-insensitive), per product
    work["_key"] = work["review_clean"].map(dedupe_key)
    before = len(work)
    work = work.drop_duplicates(subset=["product_id", "_key"], keep="first")
    stats.exact_duplicates_removed = before - len(work)

    # 4. near duplicates (same words in a different order / with extra filler punctuation)
    work["_sig"] = work["review_clean"].map(token_signature)
    before = len(work)
    work = work.drop_duplicates(subset=["product_id", "_sig"], keep="first")
    stats.near_duplicates_removed = before - len(work)

    stats.duplicates_removed = stats.exact_duplicates_removed + stats.near_duplicates_removed
    stats.valid_reviews = len(work)
    stats.duplicate_ratio = round(stats.duplicates_removed / non_empty, 3) if non_empty else 0.0

    if stats.valid_reviews == 0:
        raise DataValidationError(
            "no_valid_reviews",
            "No usable reviews remain after cleaning (all were empty, noise, or duplicates).")

    if stats.duplicate_ratio >= HIGH_DUPLICATE_RATIO:
        stats.warnings.append(
            f"{stats.duplicate_ratio:.0%} of reviews were duplicates. The data may contain "
            "copied or bot-generated reviews; insights use only the unique reviews.")
    if stats.noise_removed:
        stats.warnings.append(f"{stats.noise_removed} review(s) contained no readable text and were removed.")
    if stats.valid_reviews < 20:
        stats.warnings.append("Fewer than 20 usable reviews: aspect and sentiment statistics may be unreliable.")

    work = work.drop(columns=["_key", "_sig", "review"]).rename(columns={"review_clean": "review"})
    work["review_clean"] = work["review"]
    work = work.reset_index(drop=True)

    ds = dataset_stats(work)
    stats.average_rating, stats.rated_reviews = ds["average_rating"], ds["rated_reviews"]
    stats.date_min, stats.date_max = ds["date_min"], ds["date_max"]
    return CleaningResult(df=work, stats=stats)
