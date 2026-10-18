import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pytest.importorskip("spacy")
from app.nlp.aspects import extract_aspects  # noqa: E402
from app.nlp.clauses import split_clauses  # noqa: E402
from app.nlp.sentiment import VaderSentimentAnalyzer  # noqa: E402
from app.services.cleaning import clean_dataframe  # noqa: E402
from app.services.ingestion import ingest_file  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[2] / "data" / "sample_reviews.csv"
try:
    import spacy
    spacy.load("en_core_web_sm")
except Exception:  # model missing
    pytest.skip("spaCy model en_core_web_sm not installed", allow_module_level=True)


def frame(texts):
    return pd.DataFrame({"review_clean": texts, "review_raw": texts})


def test_clause_split_contrast_and_and():
    assert split_clauses("Sound is great but the mic is terrible") == ["Sound is great", "the mic is terrible"]
    assert len(split_clauses("The sound is good and the mic is bad")) == 2
    assert len(split_clauses("Comfortable and light")) == 1          # 'and' inside one clause stays
    assert split_clauses("The sound is amazing, the mic is awful") == ["The sound is amazing", "the mic is awful"]


def test_aspects_are_discovered_from_data_not_a_fixed_list():
    texts = ["The zipper is broken and the zipper jams"] * 1 + [
        f"The zipper feels {w}" for w in ("great", "cheap", "awful")] + [
        "Love the zipper, really smooth", "zipper is fine"]
    res = extract_aspects(frame(texts), VaderSentimentAnalyzer(), min_support=3)
    assert "zipper" in [a["aspect"] for a in res.aspects]


def test_aspect_level_sentiment_within_one_review():
    texts = ["Sound is great but the microphone is terrible."] * 3 + \
            ["The sound is amazing, the microphone is awful."] * 3
    res = extract_aspects(frame(texts), VaderSentimentAnalyzer(), min_support=2)
    a = {x["aspect"]: x for x in res.aspects}
    assert a["sound"]["positive"] == 6 and a["sound"]["negative"] == 0
    assert a["microphone"]["negative"] == 6 and a["microphone"]["positive"] == 0


def test_synonyms_and_suffix_merge():
    texts = ["The mic is terrible", "Microphone quality is poor", "Mic is awful and unusable",
            "battery life is amazing", "Battery backup is excellent", "The battery is great"]
    res = extract_aspects(frame(texts), VaderSentimentAnalyzer(), min_support=2)
    names = {a["aspect"]: a for a in res.aspects}
    assert names["microphone"]["frequency"] == 3 and names["microphone"]["negative"] == 3
    assert names["battery"]["frequency"] == 3 and names["battery"]["positive"] == 3


def test_counts_sum_to_frequency_and_examples_present():
    res = extract_aspects(frame(["Great battery"] * 3 + ["Awful battery"] * 3), VaderSentimentAnalyzer(), min_support=2)
    a = res.aspects[0]
    assert a["positive"] + a["neutral"] + a["negative"] == a["frequency"]
    assert a["examples"]["positive"] and a["examples"]["negative"]
    assert a["examples"]["positive"][0]["review"]


def test_empty_and_aspectless_input():
    assert extract_aspects(frame([]), VaderSentimentAnalyzer()).aspects == []
    assert extract_aspects(frame(["ok", "fine then", "yes indeed"]), VaderSentimentAnalyzer()).aspects == []


def test_sample_dataset_finds_expected_aspects():
    df = clean_dataframe(ingest_file(SAMPLE).df).df
    hp = df[df["product_id"] == "P001"]
    res = extract_aspects(hp, VaderSentimentAnalyzer())
    a = {x["aspect"]: x for x in res.aspects}
    for expected in ("sound", "battery", "microphone", "comfort"):
        assert expected in a, expected
    assert a["microphone"]["negative"] > a["microphone"]["positive"]
    assert a["battery"]["positive"] > a["battery"]["negative"]
    assert res.mentions["review_id"].isin(hp.index).all()


# ---------------- Phase 12 regression tests (found by the 5,000-review benchmark) ----------------
def test_aspect_word_does_not_sway_lexicon_sentiment():
    # VADER scores the word 'support' as positive; masking the aspect word must stop that leaking in.
    # (avoid words like "honestly"/"truly": VADER's lexicon scores those positive too, which would hide the effect.
    #  Unmasked these score -0.13 = neutral; with 'support' masked they score -0.49 = negative.)
    texts = ["Support is disappointing."] * 3 + ["The support is disappointing."] * 3
    res = extract_aspects(frame(texts), VaderSentimentAnalyzer(), min_support=2)
    a = {x["aspect"]: x for x in res.aspects}["customer service"]
    assert a["negative"] == 6 and a["positive"] == 0


def test_sentiment_bearing_suffix_is_not_masked():
    texts = ["There are durability problems."] * 3 + ["Durability problems everywhere."] * 3
    a = {x["aspect"]: x for x in extract_aspects(frame(texts), VaderSentimentAnalyzer(), min_support=2).aspects}
    assert a["durability"]["negative"] >= 4


def test_head_noun_synonym_and_generic_nouns():
    texts = ["The bluetooth connection is awful."] * 3 + ["Pairing is terrible."] * 3 + \
            ["It exceeded my expectations, truly great."] * 4 + ["Gift for my brother, great."] * 4
    names = {a["aspect"]: a for a in extract_aspects(frame(texts), VaderSentimentAnalyzer(), min_support=2).aspects}
    assert names["connectivity"]["frequency"] == 6           # 'bluetooth connection' and 'pairing' merge
    assert "expectation" not in names and "brother" not in names


# ---------------- Phase 12: recall fixes for words the small tagger mislabels ----------------
def test_adjective_tagged_compound_head_is_recovered():
    # spaCy often tags 'sound' as ADJ in "sound quality"; it is a noun elsewhere in the data, so it must count.
    texts = ["The sound is great."] * 3 + ["I love the sound quality."] * 3 + ["Sound quality is really awesome."] * 3
    a = {x["aspect"]: x for x in extract_aspects(frame(texts), VaderSentimentAnalyzer(), min_support=2).aspects}
    assert a["sound"]["frequency"] == 9


def test_opinion_adjectives_are_not_promoted_to_aspects():
    # 'decent'/'premium' are never nouns in this data, so "decent quality" must not create a 'decent' aspect.
    texts = ["Decent quality for the price."] * 4 + ["Premium quality, the battery is great."] * 4
    names = {x["aspect"] for x in extract_aspects(frame(texts), VaderSentimentAnalyzer(), min_support=2).aspects}
    assert "decent" not in names and "premium" not in names and "battery" in names


def test_clause_initial_gerund_subject_is_an_aspect():
    texts = ["Pairing is terrible."] * 3 + ["Charging is slow and awful."] * 3
    names = {x["aspect"] for x in extract_aspects(frame(texts), VaderSentimentAnalyzer(), min_support=2).aspects}
    assert "connectivity" in names                          # 'pairing' maps to connectivity
    assert "charging" in names or "battery" in names        # 'charge'/'charging' are mapped to battery
