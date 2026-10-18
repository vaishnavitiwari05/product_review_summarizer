import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import spacy
    spacy.load("en_core_web_sm")
    import sklearn  # noqa: F401
except Exception:
    pytest.skip("spaCy model / scikit-learn not installed", allow_module_level=True)

from app.nlp.aspects import extract_aspects  # noqa: E402
from app.nlp.embeddings import TfidfEmbedder, get_embedder  # noqa: E402
from app.nlp.opinions import aggregate_opinions  # noqa: E402
from app.nlp.sentiment import VaderSentimentAnalyzer  # noqa: E402
from app.services.cleaning import clean_dataframe  # noqa: E402
from app.services.ingestion import ingest_file  # noqa: E402
from app.utils.errors import DataValidationError  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[2] / "data" / "sample_reviews.csv"


def frame(texts):
    return pd.DataFrame({"review_clean": texts, "review_raw": texts})


def run(texts, **kw):
    ex = extract_aspects(frame(texts), VaderSentimentAnalyzer(), min_support=2)
    return aggregate_opinions(ex, TfidfEmbedder(), **kw)


def test_battery_paraphrases_group_into_one_strength():
    # "battery lasts all day" has no sentiment word, so the VADER fallback scores it neutral;
    # the transformer model is expected to catch it. Here we test grouping of the rest.
    texts = ["battery lasts all day, love it", "battery backup is excellent", "battery life is amazing",
             "The battery is fantastic", "Great battery, lasts all day"]
    agg = run(texts, min_count=3)
    s = {g["aspect"]: g for g in agg.strengths}
    assert s["battery"]["count"] == 5 and s["battery"]["sentiment"] == "positive"
    assert agg.issues == []


def test_mic_variants_group_into_one_issue():
    texts = ["mic is terrible", "microphone quality is poor", "voice sounds unclear and awful",
             "The mic is really bad", "Terrible microphone"]
    agg = run(texts, min_count=3)
    i = {g["aspect"]: g for g in agg.issues}
    assert i["microphone"]["count"] >= 4          # 'voice' folds into microphone
    assert agg.strengths == []


def test_contested_aspect_detected():
    texts = ["Great battery"] * 4 + ["Terrible battery"] * 3
    agg = run(texts, min_count=3)
    assert [c["aspect"] for c in agg.contested] == ["battery"]
    assert agg.contested[0]["dominant"] == "positive"
    assert all(g["contested"] for g in agg.strengths + agg.issues)


def test_below_threshold_is_not_recurring():
    agg = run(["Great battery", "Great battery", "Terrible battery"] + ["Great screen"] * 5, min_count=3)
    assert "battery" not in [g["aspect"] for g in agg.strengths + agg.issues]


def test_min_count_scales_with_dataset_size():
    ex = extract_aspects(frame(["Great battery"] * 200), VaderSentimentAnalyzer())
    assert aggregate_opinions(ex, TfidfEmbedder()).min_count == 6      # 3% of 200


def test_negation_kept_by_tfidf():
    v = TfidfEmbedder().embed(["not great", "great"])
    assert float(v[0] @ v[1]) < 0.9


def test_empty_extraction():
    assert aggregate_opinions(extract_aspects(frame([]), VaderSentimentAnalyzer())).strengths == []


def test_embedder_selection_and_strict_error():
    assert get_embedder("tfidf").name == "tfidf"
    try:
        import sentence_transformers  # noqa: F401
        pytest.skip("sentence-transformers installed")
    except ImportError:
        assert get_embedder("auto").name == "tfidf"
        with pytest.raises(DataValidationError) as e:
            get_embedder("sbert")
        assert e.value.code == "embedding_model_unavailable"


def test_sample_dataset_strengths_and_issues():
    df = clean_dataframe(ingest_file(SAMPLE).df).df
    hp = df[df["product_id"] == "P001"]
    agg = aggregate_opinions(extract_aspects(hp, VaderSentimentAnalyzer()), TfidfEmbedder())
    strengths = [g["aspect"] for g in agg.strengths]
    issues = [g["aspect"] for g in agg.issues]
    assert {"sound", "battery", "comfort"} <= set(strengths)
    assert "microphone" in issues
    assert all(g["examples"] and g["examples"][0]["review"] for g in agg.strengths + agg.issues)
    assert agg.strengths[0]["count"] >= agg.strengths[-1]["count"]
