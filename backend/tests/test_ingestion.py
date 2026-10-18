import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.ingestion import ingest_bytes, ingest_file, list_products  # noqa: E402
from app.utils.errors import DataValidationError  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[2] / "data" / "sample_reviews.csv"


def code(fn, *a):
    with pytest.raises(DataValidationError) as e:
        fn(*a)
    return e.value.code


def test_sample_dataset_loads():
    r = ingest_file(SAMPLE)
    assert r.report.total_rows == 109
    assert r.report.empty_reviews == 2
    assert r.report.valid_reviews == 107
    assert r.report.missing_ratings == 1
    assert r.report.missing_dates == 1
    assert r.report.products_found == 2
    assert {p["product_id"] for p in list_products(r.df)} == {"P001", "P002"}


def test_wrong_extension():
    assert code(ingest_bytes, b"a,b\n1,2", "data.xlsx") == "unsupported_file"


def test_empty_file():
    assert code(ingest_bytes, b"   \n", "x.csv") == "empty_file"


def test_headers_only():
    assert code(ingest_bytes, b"review,rating\n", "x.csv") == "empty_dataset"


def test_missing_review_column():
    assert code(ingest_bytes, b"product,rating\nA,5\n", "x.csv") == "missing_columns"


def test_all_reviews_empty():
    assert code(ingest_bytes, b"review,rating\n,5\n  ,4\n", "x.csv") == "no_valid_reviews"


def test_column_aliases_and_defaults():
    r = ingest_bytes(b"Review Text,Stars\nGreat phone,5\nBad battery,1\n", "x.csv")
    assert list(r.df.columns) == ["product_id", "product_name", "review", "rating", "review_date"]
    assert r.report.products_found == 1
    assert r.df["product_name"].iloc[0] == "Unnamed Product"
    assert r.df["rating"].tolist() == [5.0, 1.0]


def test_invalid_ratings_and_dates_are_kept_with_warnings():
    raw = b"review,rating,date\nok,9,not-a-date\nfine,abc,2025-01-02\n"
    r = ingest_bytes(raw, "x.csv")
    assert r.report.invalid_ratings == 2
    assert r.report.invalid_dates == 1
    assert r.report.valid_reviews == 2


def test_semicolon_and_latin1():
    raw = "review;rating\nTrès bon produit;5\n".encode("cp1252")
    r = ingest_bytes(raw, "x.csv")
    assert "Très" in r.df["review"].iloc[0]


def test_too_large(monkeypatch):
    from app.services import ingestion
    from dataclasses import replace
    monkeypatch.setattr(ingestion, "settings", replace(ingestion.settings, max_upload_mb=0))
    assert code(ingest_bytes, b"review\nhello\n", "x.csv") == "file_too_large"


def test_file_not_found():
    assert code(ingest_file, "nope.csv") == "file_not_found"


def test_single_column_csv_regression():
    r = ingest_bytes(b"review\nvery nice\nreally bad\nmeh overall\n", "x.csv")
    assert r.report.total_rows == 3


def test_too_many_rows(monkeypatch):
    from app.services import ingestion
    monkeypatch.setattr(ingestion, "MAX_ROWS", 3)
    assert code(ingest_bytes, b"review\na a\nb b\nc c\nd d\n", "x.csv") == "too_many_rows"
