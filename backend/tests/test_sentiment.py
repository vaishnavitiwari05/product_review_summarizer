import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.nlp.sentiment import (SentimentAnalyzer, SentimentPrediction,  # noqa: E402
                               VaderSentimentAnalyzer, get_analyzer)
from app.services.cleaning import clean_dataframe  # noqa: E402
from app.services.ingestion import ingest_file  # noqa: E402
from app.services.sentiment_service import add_sentiment, overall_label, summarize_sentiment  # noqa: E402
from app.utils.errors import DataValidationError  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[2] / "data" / "sample_reviews.csv"


class FakeAnalyzer(SentimentAnalyzer):
    name = "fake"

    def predict(self, texts):
        m = {"good": ("positive", .8), "bad": ("negative", -.8), "meh": ("neutral", 0.0)}
        return [SentimentPrediction(m[t][0], m[t][1], .9) for t in texts]


def _df(texts, ratings=None):
    return pd.DataFrame({"review_clean": texts, "rating": ratings or [None] * len(texts)})


def test_vader_basic_labels():
    p = VaderSentimentAnalyzer().predict([
        "Absolutely fantastic sound, I love it.",
        "Terrible microphone, awful quality, very disappointed.",
        "It arrived on Tuesday."])
    assert [x.label for x in p] == ["positive", "negative", "neutral"]
    assert p[0].score > 0 > p[1].score


def test_summary_counts_and_percentages():
    df = add_sentiment(_df(["good"] * 6 + ["meh"] + ["bad"] * 3), FakeAnalyzer())
    s = summarize_sentiment(df)
    assert s["counts"] == {"positive": 6, "neutral": 1, "negative": 3}
    assert s["percentages"] == {"positive": 60.0, "neutral": 10.0, "negative": 30.0}
    assert s["net_sentiment"] == 30.0 and s["overall"] == "Mostly Positive"
    assert s["backend"] == "fake"


@pytest.mark.parametrize("pos,neg,label", [(80, 5, "Positive"), (50, 30, "Mostly Positive"),
                                            (35, 35, "Mixed"), (20, 50, "Mostly Negative"), (5, 80, "Negative")])
def test_overall_label(pos, neg, label):
    assert overall_label(pos, neg) == label


def test_rating_never_decides_sentiment():
    # 5-star rating but negative text stays negative
    df = add_sentiment(_df(["bad"], [5]), FakeAnalyzer())
    s = summarize_sentiment(df)
    assert df["sentiment"].iloc[0] == "negative"
    assert s["rating_check"]["mismatches"] == 1


def test_empty_frame():
    df = add_sentiment(_df([]), FakeAnalyzer())
    assert summarize_sentiment(df)["overall"] == "Unknown"


def test_full_pipeline_on_sample_with_vader():
    cleaned = clean_dataframe(ingest_file(SAMPLE).df).df
    df = add_sentiment(cleaned, VaderSentimentAnalyzer())
    s = summarize_sentiment(df)
    assert s["total"] == 103 and sum(s["counts"].values()) == 103
    assert s["counts"]["positive"] > 0 and s["counts"]["negative"] > 0 and s["counts"]["neutral"] > 0
    assert s["rating_check"]["agreement_pct"] > 55
    assert abs(sum(s["percentages"].values()) - 100) < 0.5


def test_transformer_missing_gives_friendly_error(monkeypatch):
    # In offline/sandbox environments strict mode must fail with a clear message.
    try:
        import transformers  # noqa: F401
        pytest.skip("transformers installed; strict-mode failure not reproducible offline")
    except ImportError:
        with pytest.raises(DataValidationError) as e:
            get_analyzer("transformer", use_cache=False)
        assert e.value.code == "sentiment_model_unavailable"


def test_auto_falls_back_to_vader():
    try:
        import transformers  # noqa: F401
        pytest.skip("transformers installed")
    except ImportError:
        assert get_analyzer("auto", use_cache=False).name == "vader"
