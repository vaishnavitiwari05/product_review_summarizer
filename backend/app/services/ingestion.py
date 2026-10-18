"""Phase 2: CSV ingestion + validation.

Loads raw bytes/path into a DataFrame with canonical columns:
  product_id, product_name, review, rating, review_date
Only `review` is mandatory; everything else degrades gracefully with warnings.
Cleaning (duplicates, noise, normalisation) happens in Phase 3, not here.
"""
from __future__ import annotations

import csv
import io
import warnings
from pathlib import Path

import pandas as pd

from app.models.schemas import IngestionResult, ValidationReport
from app.utils.config import settings
from app.utils.errors import DataValidationError

CANONICAL = ["product_id", "product_name", "review", "rating", "review_date"]
REQUIRED = ["review"]
DEFAULT_PRODUCT_ID = "P000"
DEFAULT_PRODUCT_NAME = "Unnamed Product"
MAX_ROWS = 200_000

ALIASES = {
    "product_id": ["product_id", "productid", "asin", "sku", "item_id", "id_product"],
    "product_name": ["product_name", "product", "productname", "title", "item_name", "name"],
    "review": ["review", "review_text", "reviewtext", "text", "comment", "comments",
               "review_body", "body", "content", "feedback"],
    "rating": ["rating", "stars", "star_rating", "score", "overall", "review_rating"],
    "review_date": ["review_date", "date", "reviewdate", "review_time", "created_at",
                    "timestamp", "reviewed_at", "unixreviewtime"],
}
_ALIAS_LOOKUP = {a: canon for canon, names in ALIASES.items() for a in names}


def _norm_col(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_").replace("-", "_")


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise DataValidationError("bad_encoding", "Could not read the file's text encoding. "
                              "Please save the CSV as UTF-8 and try again.")


def _check_file(filename: str, raw: bytes) -> None:
    if not filename or Path(filename).suffix.lower() != ".csv":
        raise DataValidationError("unsupported_file",
                                  "Unsupported file type. Please upload a .csv file.")
    limit = settings.max_upload_mb * 1024 * 1024
    if len(raw) > limit:
        raise DataValidationError(
            "file_too_large",
            f"File is {len(raw) / 1024 / 1024:.1f} MB; the limit is {settings.max_upload_mb} MB.",
            status_code=413)
    if not raw.strip():
        raise DataValidationError("empty_file", "The uploaded file is empty.")


def _detect_delimiter(text: str) -> str:
    """Sniff only among common delimiters. (Unrestricted sniffing can pick a letter
    as the separator for single-column files.)"""
    sample = "\n".join(text.splitlines()[:20])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _parse(text: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(io.StringIO(text), sep=_detect_delimiter(text), engine="python",
                         dtype=str, keep_default_na=False, on_bad_lines="skip")
    except pd.errors.EmptyDataError:
        raise DataValidationError("empty_file", "The CSV has no data.")
    except (pd.errors.ParserError, csv.Error) as exc:
        raise DataValidationError("invalid_csv", "The file is not a valid CSV.",
                                  details={"reason": str(exc)[:200]})
    return df


def _map_columns(df: pd.DataFrame, report: ValidationReport) -> pd.DataFrame:
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for col in df.columns:
        canon = _ALIAS_LOOKUP.get(_norm_col(col))
        if canon and canon not in used:
            mapping[col] = canon
            used.add(canon)
    report.columns_detected = {k: v for k, v in mapping.items()}

    missing_required = [c for c in REQUIRED if c not in used]
    if missing_required:
        raise DataValidationError(
            "missing_columns",
            f"Required column(s) missing: {', '.join(missing_required)}. "
            f"Found columns: {', '.join(map(str, df.columns))}. "
            f"Accepted names for 'review': {', '.join(ALIASES['review'])}.",
            details={"missing": missing_required, "found": [str(c) for c in df.columns]})

    df = df.rename(columns=mapping)[list(mapping.values())]
    for col in CANONICAL:
        if col not in df.columns:
            report.columns_missing_optional.append(col)
            df[col] = ""
    return df[CANONICAL]


def ingest_bytes(raw: bytes, filename: str) -> IngestionResult:
    report = ValidationReport(filename=filename)
    _check_file(filename, raw)
    df = _parse(_decode(raw))

    if df.empty:
        raise DataValidationError("empty_dataset", "The CSV has headers but no rows.")
    if len(df) > MAX_ROWS:
        raise DataValidationError(
            "too_many_rows", f"The file has {len(df):,} rows; the limit is {MAX_ROWS:,}.",
            status_code=413)

    df = _map_columns(df, report)
    report.total_rows = len(df)

    # --- review text ---
    df["review"] = df["review"].astype(str).str.strip()
    empty_mask = df["review"] == ""
    report.empty_reviews = int(empty_mask.sum())
    report.valid_reviews = int((~empty_mask).sum())
    if report.valid_reviews == 0:
        raise DataValidationError("no_valid_reviews",
                                  "Every review in the file is empty, so there is nothing to analyze.")
    if report.empty_reviews:
        report.warnings.append(f"{report.empty_reviews} empty review(s) will be ignored.")

    # --- rating ---
    raw_rating = df["rating"].astype(str).str.strip()
    numeric = pd.to_numeric(raw_rating.replace("", pd.NA), errors="coerce")
    report.missing_ratings = int((raw_rating == "").sum())
    bad = numeric.isna() & (raw_rating != "")
    out_of_range = numeric.notna() & ((numeric < 1) | (numeric > 5))
    report.invalid_ratings = int(bad.sum() + out_of_range.sum())
    numeric[out_of_range] = pd.NA
    df["rating"] = numeric.astype("float64")
    if report.missing_ratings or report.invalid_ratings:
        report.warnings.append(
            f"{report.missing_ratings} missing and {report.invalid_ratings} invalid rating(s) "
            "(valid range 1-5); these reviews are kept and sentiment is computed from text.")
    if "rating" in report.columns_missing_optional:
        report.warnings.append("No rating column found; average rating will not be available.")

    # --- date ---
    raw_date = df["review_date"].astype(str).str.strip()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # mixed date formats are expected
        parsed = pd.to_datetime(raw_date.replace("", pd.NA), errors="coerce")
    report.missing_dates = int((raw_date == "").sum())
    report.invalid_dates = int((parsed.isna() & (raw_date != "")).sum())
    df["review_date"] = parsed
    if "review_date" in report.columns_missing_optional:
        report.warnings.append("No date column found; date range will not be available.")
    elif report.invalid_dates:
        report.warnings.append(f"{report.invalid_dates} review date(s) could not be parsed.")

    # --- product identity ---
    pid = df["product_id"].astype(str).str.strip()
    pname = df["product_name"].astype(str).str.strip()
    if "product_id" in report.columns_missing_optional and "product_name" in report.columns_missing_optional:
        pid[:] = DEFAULT_PRODUCT_ID
        pname[:] = DEFAULT_PRODUCT_NAME
        report.warnings.append("No product columns found; all reviews are treated as one product.")
    elif "product_id" in report.columns_missing_optional:
        codes = {n: f"P{i:03d}" for i, n in enumerate(pd.unique(pname), start=1)}
        pid = pname.map(codes)
    elif "product_name" in report.columns_missing_optional:
        pname = pid.copy()
    pid = pid.where(pid != "", DEFAULT_PRODUCT_ID)
    pname = pname.where(pname != "", pid)
    df["product_id"], df["product_name"] = pid, pname
    report.products_found = int(df["product_id"].nunique())

    return IngestionResult(df=df.reset_index(drop=True), report=report)


def ingest_file(path: str | Path) -> IngestionResult:
    p = Path(path)
    if not p.exists():
        raise DataValidationError("file_not_found", f"File not found: {p.name}", status_code=404)
    return ingest_bytes(p.read_bytes(), p.name)


def list_products(df: pd.DataFrame) -> list[dict]:
    """Products with review counts, for the product selector."""
    g = (df[df["review"] != ""].groupby(["product_id", "product_name"])
         .agg(review_count=("review", "size"), avg_rating=("rating", "mean")).reset_index())
    return [{"product_id": r.product_id, "product_name": r.product_name,
             "review_count": int(r.review_count),
             "avg_rating": None if pd.isna(r.avg_rating) else round(float(r.avg_rating), 2)}
            for r in g.itertuples()]
