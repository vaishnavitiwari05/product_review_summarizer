import json
import sys
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import spacy
    spacy.load("en_core_web_sm")
    import sklearn  # noqa: F401
except Exception:
    pytest.skip("spaCy model / scikit-learn not installed", allow_module_level=True)

from app.llm.client import AnthropicClient, OpenAIClient, build_client  # noqa: E402
from app.llm.mock import mock_summary  # noqa: E402
from app.llm.schemas import LLMOutputError, parse_summary  # noqa: E402
from app.llm.summarizer import generate_summary  # noqa: E402
from app.nlp.embeddings import TfidfEmbedder  # noqa: E402
from app.nlp.sentiment import VaderSentimentAnalyzer  # noqa: E402
from app.services.cleaning import clean_dataframe  # noqa: E402
from app.services.ingestion import ingest_file  # noqa: E402
from app.services.pipeline import analyze_product  # noqa: E402
from app.utils.config import settings  # noqa: E402
from app.utils.errors import DataValidationError  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[2] / "data" / "sample_reviews.csv"
GOOD = {"overall_summary": "Mostly positive.", "pros": ["Sound"], "cons": ["Mic"], "recurring_issues": ["Mic"],
        "important_aspects": [{"aspect": "Sound", "note": "Praised"}], "sentiment_explanation": "58% positive."}


@pytest.fixture(scope="module")
def findings():
    clean = clean_dataframe(ingest_file(SAMPLE).df).df
    return analyze_product(clean, "P001", VaderSentimentAnalyzer(), TfidfEmbedder())


def anthropic_reply(obj_or_text):
    text = obj_or_text if isinstance(obj_or_text, str) else json.dumps(obj_or_text)
    return httpx.Response(200, json={"content": [{"type": "text", "text": text}]})


def live_cfg(**kw):
    return replace(settings, use_mock_llm=False, llm_api_key="sk-test", llm_provider="anthropic",
                   llm_model="test-model", **kw)


def client_with(handler, provider="anthropic", retries=2):
    return build_client(provider, "sk-test", "test-model", max_retries=retries, backoff=0,
                        transport=httpx.MockTransport(handler))


# ---------- payload ----------
def test_payload_is_structured_and_has_no_raw_reviews(findings):
    p = findings.payload()
    assert p["total_reviews_analyzed"] == 67
    assert {"sentiment", "major_aspects", "recurring_strengths", "recurring_issues"} <= set(p)
    assert p["recurring_issues"][0]["aspect"] == "microphone"
    raw = " ".join(findings.reviews["review_raw"])
    blob = json.dumps(p)
    assert len(blob) < 4000 < len(raw)                     # far smaller than the reviews themselves
    for phrase in [ph for g in p["recurring_issues"] for ph in g["typical_phrases"]]:
        assert len(phrase) <= 120


def test_payload_size_does_not_grow_with_review_count():
    import pandas as pd
    clean = clean_dataframe(ingest_file(SAMPLE).df).df
    hp = clean[clean.product_id == "P001"]
    big = pd.concat([hp.assign(review_clean=hp["review_clean"] + f" #{i}",
                               review_raw=hp["review_raw"] + f" #{i}") for i in range(20)]).reset_index(drop=True)
    small_len = len(json.dumps(analyze_product(hp, "P001", VaderSentimentAnalyzer(), TfidfEmbedder()).payload()))
    big_len = len(json.dumps(analyze_product(big, "P001", VaderSentimentAnalyzer(), TfidfEmbedder()).payload()))
    assert big_len < small_len * 1.6


# ---------- mock mode ----------
def test_mock_mode_needs_no_key(findings):
    r = generate_summary(findings.payload(), replace(settings, use_mock_llm=True, llm_api_key=""))
    assert r.mode == "mock" and r.warnings
    assert "microphone" in r.summary.overall_summary.lower()
    assert any("Microphone" in c for c in r.summary.cons)
    assert r.summary.pros and r.summary.important_aspects


def test_mock_summary_reflects_data_not_static_text(findings):
    p = findings.payload()
    p["sentiment"]["overall"] = "Negative"
    assert "negative" in mock_summary(p).overall_summary.lower()


# ---------- missing key / config ----------
def test_missing_api_key_raises_clear_error(findings):
    with pytest.raises(DataValidationError) as e:
        generate_summary(findings.payload(), replace(settings, use_mock_llm=False, llm_api_key=""))
    assert e.value.code == "llm_api_key_missing" and "LLM_API_KEY" in e.value.message


def test_unknown_provider_and_missing_openai_model():
    with pytest.raises(DataValidationError) as e:
        build_client("nope", "k", "m")
    assert e.value.code == "llm_provider_unsupported"
    with pytest.raises(DataValidationError) as e:
        build_client("openai", "k", "")
    assert e.value.code == "llm_model_missing"
    assert build_client("anthropic", "k", "").model            # anthropic has a default


# ---------- live path (mocked HTTP) ----------
def test_live_success_sends_payload_not_reviews(findings):
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        seen["key"] = req.headers["x-api-key"]
        return anthropic_reply(GOOD)
    r = generate_summary(findings.payload(), live_cfg(), client_with(handler))
    assert r.mode == "live" and r.summary.pros == ["Sound"] and seen["key"] == "sk-test"
    sent = json.dumps(seen["body"])
    assert "recurring_issues" in sent and "microphone" in sent
    assert "Keeps disconnecting from my laptop" not in sent   # raw review text never sent


def test_fenced_and_chatty_json_is_accepted():
    assert parse_summary("```json\n" + json.dumps(GOOD) + "\n```").pros == ["Sound"]
    assert parse_summary("Sure! Here you go: " + json.dumps(GOOD) + " Hope it helps.").cons == ["Mic"]
    with pytest.raises(LLMOutputError):
        parse_summary("no json here")
    with pytest.raises(LLMOutputError):
        parse_summary('{"pros": []}')                            # missing overall_summary


def test_retries_transient_errors_then_succeeds(findings):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(429) if calls["n"] < 3 else anthropic_reply(GOOD)
    assert generate_summary(findings.payload(), live_cfg(), client_with(handler)).mode == "live"
    assert calls["n"] == 3


def test_persistent_server_error_gives_friendly_error(findings):
    with pytest.raises(DataValidationError) as e:
        generate_summary(findings.payload(), live_cfg(), client_with(lambda r: httpx.Response(503)))
    assert e.value.code == "llm_unavailable" and "sk-test" not in e.value.message


def test_timeout_and_network_errors(findings):
    def boom(req):
        raise httpx.ConnectTimeout("slow")
    with pytest.raises(DataValidationError) as e:
        generate_summary(findings.payload(), live_cfg(), client_with(boom, retries=1))
    assert e.value.code == "llm_unavailable" and "timed out" in e.value.message


@pytest.mark.parametrize("status,code", [(401, "llm_auth_failed"), (404, "llm_model_not_found"),
                                         (400, "llm_request_rejected")])
def test_non_retryable_errors(findings, status, code):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(status, text="nope")
    with pytest.raises(DataValidationError) as e:
        generate_summary(findings.payload(), live_cfg(), client_with(handler))
    assert e.value.code == code and calls["n"] == 1             # no pointless retries


def test_bad_json_gets_one_repair_attempt(findings):
    replies = iter(["I cannot do that", json.dumps(GOOD)])
    assert generate_summary(findings.payload(), live_cfg(),
                            client_with(lambda r: anthropic_reply(next(replies)))).mode == "live"


def test_bad_json_twice_raises(findings):
    with pytest.raises(DataValidationError) as e:
        generate_summary(findings.payload(), live_cfg(), client_with(lambda r: anthropic_reply("still not json")))
    assert e.value.code == "llm_bad_output"


def test_openai_compatible_client(findings):
    def handler(req):
        assert req.url.path.endswith("/chat/completions") and req.headers["authorization"] == "Bearer sk-test"
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(GOOD)}}]})
    r = generate_summary(findings.payload(), live_cfg(), client_with(handler, provider="openai"))
    assert r.summary.overall_summary == "Mostly positive."
    assert isinstance(client_with(handler, "openai"), OpenAIClient)
    assert isinstance(client_with(handler), AnthropicClient)


def test_mock_separates_dominant_opinions_from_mixed_feedback(findings):
    p = findings.payload()
    p["recurring_issues"] = p["recurring_issues"] + [
        {"aspect": "keyboard", "negative_mentions": 68, "opposite_mentions": 181,
         "share_of_aspect_mentions_pct": 25, "also_has_opposite_opinion": True, "typical_phrases": []}]
    s = mock_summary(p)
    assert not any("Keyboard" in c for c in s.cons)                          # outweighed -> not a main con
    assert "mixed" in s.overall_summary.lower() and "keyboard" in s.overall_summary.lower()
    assert any("Keyboard" in i and "mixed" in i for i in s.recurring_issues)  # still listed as recurring, flagged mixed
    assert "opposite_mentions" in p["recurring_strengths"][0]
