import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import spacy
    spacy.load("en_core_web_sm")
    import sklearn  # noqa: F401
except Exception:
    pytest.skip("spaCy model / scikit-learn not installed", allow_module_level=True)

from dataclasses import replace  # noqa: E402

from app.llm.mock import mock_summary  # noqa: E402
from app.llm.schemas import LLMSummary  # noqa: E402
from app.nlp.embeddings import TfidfEmbedder  # noqa: E402
from app.nlp.sentiment import VaderSentimentAnalyzer  # noqa: E402
from app.services.cleaning import clean_dataframe  # noqa: E402
from app.services.ingestion import ingest_file  # noqa: E402
from app.services.pipeline import analyze_product  # noqa: E402
from app.validation.lexicon import claim_direction  # noqa: E402
from app.validation.report import EVIDENCE_BACKED, NEEDS_REVIEW  # noqa: E402
from app.validation.validator import assess, validate_summary  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[2] / "data" / "sample_reviews.csv"


@pytest.fixture(scope="module")
def f():
    clean = clean_dataframe(ingest_file(SAMPLE).df).df
    return analyze_product(clean, "P001", VaderSentimentAnalyzer(), TfidfEmbedder())


def summ(**kw):
    base = dict(overall_summary="Customers are mostly positive: praised sound, comfort and battery. "
                                "Main concerns: microphone.",
                pros=["Sound quality is praised", "Comfortable fit"], cons=["Microphone quality problems"],
                recurring_issues=["Microphone"], important_aspects=[], sentiment_explanation="")
    base.update(kw)
    return LLMSummary(**base)


def check(rep, cid):
    return next(k for k in rep.checks if k.id == cid)


def claim(rep, text_part):
    return next(c for c in rep.claims if text_part.lower() in c.text.lower())


# ---------- happy path ----------
def test_generated_mock_summary_is_evidence_backed(f):
    rep = validate_summary(mock_summary(f.payload()), f)
    assert rep.verdict == EVIDENCE_BACKED and rep.score >= 90
    assert all(k.status == "pass" for k in rep.checks)


def test_paraphrased_llm_style_summary_passes(f):
    s = summ(pros=["Audio quality is praised", "Very comfortable for long sessions", "Battery backup is excellent"])
    rep = validate_summary(s, f)
    assert rep.verdict == EVIDENCE_BACKED
    assert claim(rep, "Audio quality").aspect == "sound" and claim(rep, "Audio quality").status == "supported"


# ---------- the spec's example ----------
def test_customers_love_the_microphone_is_flagged(f):
    s = summ(overall_summary="Customers are mostly positive and generally love the microphone.",
             pros=["Crystal-clear microphone"], cons=[], recurring_issues=[])
    rep = validate_summary(s, f)
    assert rep.verdict == NEEDS_REVIEW
    assert claim(rep, "Crystal-clear").status == "contradicted"
    assert any(c.status == "contradicted" and c.section == "overall_summary" for c in rep.claims)
    assert check(rep, "prose").status == "fail"
    assert claim(rep, "Crystal-clear").examples             # shows negative evidence clauses


# ---------- other failure modes ----------
def test_wrong_overall_sentiment_fails(f):
    rep = validate_summary(summ(overall_summary="Customers are mostly negative about this product. "
                                                "Main concerns: microphone."), f)
    assert check(rep, "sentiment").status == "fail" and rep.verdict == NEEDS_REVIEW


def test_overstated_sentiment_warns(f):
    rep = validate_summary(summ(overall_summary="Customers are overwhelmingly positive. Main concerns: microphone."), f)
    assert check(rep, "sentiment").status == "warn"


def test_sentiment_percentages_do_not_confuse_the_check(f):
    text = "Customers are mostly positive: 58% of 67 reviews are positive and 24% negative. Main concerns: microphone."
    assert check(validate_summary(summ(overall_summary=text), f), "sentiment").status == "pass"


def test_ignored_major_issue_fails(f):
    s = summ(overall_summary="Customers are mostly positive and praise the sound.", cons=[], recurring_issues=[])
    rep = validate_summary(s, f)
    assert check(rep, "omissions").status == "fail" and "microphone" in check(rep, "omissions").message
    assert rep.verdict == NEEDS_REVIEW


def test_false_praise_does_not_count_as_covering_an_issue(f):
    s = summ(overall_summary="Customers are mostly positive and love the microphone.", cons=[], recurring_issues=[],
             pros=["Great microphone"])
    assert check(validate_summary(s, f), "omissions").status == "fail"


def test_invented_aspect_is_unverified_not_supported(f):
    rep = validate_summary(summ(pros=["Sound quality is praised", "Great touch controls"]), f)
    c = claim(rep, "touch controls")
    assert c.status == "unverified" and c.aspect is None


def test_unsupported_con(f):
    c = claim(validate_summary(summ(cons=["Microphone problems", "Slightly expensive"]), f), "expensive")
    assert c.status == "unsupported" and c.aspect == "price"


def test_made_up_numbers_flagged(f):
    rep = validate_summary(summ(sentiment_explanation="92% of reviews are positive."), f)
    assert check(rep, "numbers").status in ("warn", "fail")
    ok = validate_summary(summ(sentiment_explanation="58% of reviews are positive and 24% are negative."), f)
    assert check(ok, "numbers").status == "pass"
    bad_avg = validate_summary(summ(sentiment_explanation="Average rating is 4.9 stars."), f)
    assert check(bad_avg, "numbers").status != "pass"


def test_hedged_claims_and_negation():
    assert claim_direction("Some users report durability problems") == ("negative", True)
    assert claim_direction("The microphone is not great")[0] == "negative"
    assert claim_direction("no complaints about the battery")[0] == "positive"
    assert claim_direction("It arrived on Tuesday")[0] is None


def test_hedged_negative_about_contested_aspect_ok(f):
    rep = validate_summary(summ(cons=["Microphone problems", "Some users report durability problems"]), f)
    assert claim(rep, "durability").status in ("supported", "weak")


def test_empty_lists_do_not_crash(f):
    rep = validate_summary(LLMSummary(overall_summary="Mostly positive."), f)
    assert rep.verdict == NEEDS_REVIEW            # ignores the microphone issue


# ---------- assess() unit behaviour ----------
@pytest.mark.parametrize("d,pos,neg,status", [
    ("positive", 10, 1, "supported"), ("positive", 1, 7, "contradicted"), ("positive", 5, 4, "weak"),
    ("positive", 1, 0, "unsupported"), ("negative", 1, 7, "supported"), ("negative", 8, 0, "contradicted"),
    ("negative", 6, 1, "unsupported"), ("negative", 2, 3, "weak")])
def test_assess_table(d, pos, neg, status):
    a = {"positive": pos, "negative": neg}
    assert assess(d, a, 3)[0] == status


# ---------- reversed data + end-to-end ----------
def test_reversed_reality_microphone_is_actually_loved():
    texts = ["The microphone is excellent and clear."] * 6 + ["Great battery, lasts long."] * 6
    df = pd.DataFrame({"product_id": "X", "product_name": "Y", "review_clean": texts, "review_raw": texts,
                       "rating": 5.0, "review_date": pd.NaT})
    fx = analyze_product(df, "X", VaderSentimentAnalyzer(), TfidfEmbedder())
    rep = validate_summary(summ(overall_summary="Mostly positive. The microphone is terrible.",
                                pros=[], cons=["Terrible microphone"], recurring_issues=[]), fx)
    assert claim(rep, "Terrible microphone").status == "contradicted" and rep.verdict == NEEDS_REVIEW


def test_small_dataset_note(f):
    small = replace(f)
    small.extraction = replace(f.extraction, review_count=10)
    assert "only 10 reviews" in validate_summary(mock_summary(f.payload()), small).headline
