import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.cleaning import clean_dataframe, dataset_stats  # noqa: E402
from app.services.ingestion import ingest_file, ingest_bytes  # noqa: E402
from app.utils.errors import DataValidationError  # noqa: E402
from app.utils.text import clean_text, dedupe_key  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[2] / "data" / "sample_reviews.csv"


def test_clean_text_removes_noise():
    t = clean_text("Great sound!!! <br> visit http://spam.example.com now \U0001F600\U0001F600  soooooo good")
    assert t == "Great sound! visit now soo good"
    assert clean_text("It&amp;s   fine\u2019s") == "It&s fine's"
    assert clean_text(None) == ""


def test_dedupe_key_ignores_case_punct_space():
    assert dedupe_key("  BATTERY lasts, all day!! ") == dedupe_key("battery lasts all day")


def test_sample_dataset_stats():
    res = clean_dataframe(ingest_file(SAMPLE).df)
    s = res.stats
    assert s.total_reviews == 109
    assert s.empty_removed == 2
    assert s.exact_duplicates_removed == 4
    assert s.valid_reviews == 103
    assert s.average_rating is not None and 1 <= s.average_rating <= 5
    assert s.date_min and s.date_max and s.date_min <= s.date_max
    assert res.df["review"].str.len().min() > 0
    assert "review_raw" in res.df.columns


def test_duplicates_are_per_product():
    raw = b"product_id,review\nA,Great battery life\nB,Great battery life\nA,great BATTERY life!\n"
    res = clean_dataframe(ingest_bytes(raw, "x.csv").df)
    assert res.stats.valid_reviews == 2
    assert res.stats.duplicates_removed == 1


def test_near_duplicate_reordered_words():
    raw = b"review\nbattery life is great\nGreat battery life is\nsomething different entirely\n"
    res = clean_dataframe(ingest_bytes(raw, "x.csv").df)
    assert res.stats.near_duplicates_removed == 1


def test_noise_only_reviews_removed():
    raw = "review\n\U0001F600\U0001F600\n12345\nhttp://a.com\nGood phone overall\n".encode()
    res = clean_dataframe(ingest_bytes(raw, "x.csv").df)
    assert res.stats.noise_removed == 3
    assert res.stats.valid_reviews == 1


def test_duplicate_heavy_dataset_warns():
    raw = ("review\n" + "Love it\n" * 9 + "Hate it a lot\n").encode()
    res = clean_dataframe(ingest_bytes(raw, "x.csv").df)
    assert res.stats.valid_reviews == 2
    assert any("duplicates" in w for w in res.stats.warnings)


def test_everything_removed_raises():
    df = pd.DataFrame({"product_id": ["A"], "product_name": ["A"], "review": ["\U0001F600"],
                       "rating": [5.0], "review_date": [pd.NaT]})
    with pytest.raises(DataValidationError) as e:
        clean_dataframe(df)
    assert e.value.code == "no_valid_reviews"


def test_dataset_stats_without_ratings_or_dates():
    res = clean_dataframe(ingest_bytes(b"review\nnice product\nbad product\n", "x.csv").df)
    assert res.stats.average_rating is None and res.stats.date_min is None
    assert dataset_stats(res.df)["total_reviews"] == 2
