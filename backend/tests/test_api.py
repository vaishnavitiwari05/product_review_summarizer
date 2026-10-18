import io
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import spacy
    spacy.load("en_core_web_sm")
    import sklearn  # noqa: F401
    import python_multipart  # noqa: F401
except Exception:
    pytest.skip("spaCy model / scikit-learn / python-multipart not installed", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from app.utils import config  # noqa: E402
from app.utils.database import configure_engine, new_session  # noqa: E402
from app.utils.errors import DataValidationError  # noqa: E402


@pytest.fixture()
def client(tmp_path):
    configure_engine(f"sqlite:///{tmp_path/'test.db'}")
    from app.main import app
    with TestClient(app) as c:
        yield c


def csv_file(text, name="reviews.csv"):
    return {"file": (name, io.BytesIO(text.encode()), "text/csv")}


def load_sample(client):
    r = client.post("/sample")
    assert r.status_code == 200, r.text
    return r.json()


def analyze(client, pid="P001"):
    r = client.post("/analyze", json={"product_id": pid})
    assert r.status_code == 202, r.text
    run = client.get(f"/analyze/{r.json()['run_id']}").json()     # bg task has finished in TestClient
    return r.json()["run_id"], run


# ---------------------------------------------------------------- basics / upload
def test_health(client):
    j = client.get("/health").json()
    assert j["status"] == "ok" and j["llm_mode"] == "mock" and j["llm_ready"] is True


def test_sample_upload_and_products(client):
    j = load_sample(client)
    assert j["cleaning"]["valid_reviews"] == 103 and j["cleaning"]["duplicates_removed"] == 4
    assert j["validation"]["empty_reviews"] == 2
    prods = {p["product_id"]: p for p in client.get("/products").json()["products"]}
    assert set(prods) == {"P001", "P002"} and prods["P001"]["analyzed"] is False
    assert prods["P001"]["review_count"] == 67


def test_custom_csv_upload_with_column_aliases(client):
    csv = "Review Text,Stars\n" + "\n".join(["Great battery life"] * 2 + [f"Battery is great number {i}" for i in range(5)])
    r = client.post("/upload", files=csv_file(csv))
    assert r.status_code == 200 and r.json()["products"][0]["product_name"] == "Unnamed Product"


@pytest.mark.parametrize("name,body,status,code", [
    ("data.xlsx", "a,b\n1,2", 400, "unsupported_file"),
    ("x.csv", "", 400, "empty_file"),
    ("x.csv", "product,rating\nA,5\n", 400, "missing_columns"),
    ("x.csv", "review,rating\n", 400, "empty_dataset"),
    ("x.csv", "review\n\n  \n", 400, "empty_dataset"),
    ("x.csv", "review,rating\n,5\n , 4\n", 400, "no_valid_reviews"),
])
def test_upload_errors_are_friendly(client, name, body, status, code):
    r = client.post("/upload", files=csv_file(body, name))
    assert r.status_code == status and r.json()["error"] == code and r.json()["message"]


def test_missing_file_field(client):
    r = client.post("/upload")
    assert r.status_code == 422 and r.json()["error"] == "invalid_request"


def test_oversized_upload_rejected(client, monkeypatch):
    monkeypatch.setattr(config, "settings", replace(config.settings, max_upload_mb=0))
    r = client.post("/upload", files=csv_file("review\n" + "hello there\n" * 10))
    assert r.status_code == 413 and r.json()["error"] == "file_too_large"


def test_duplicate_heavy_upload_warns(client):
    csv = "review\n" + "Love it\n" * 30 + "Hate the battery a lot\n"
    j = client.post("/upload", files=csv_file(csv)).json()
    assert j["cleaning"]["valid_reviews"] == 2 and any("duplicates" in w for w in j["cleaning"]["warnings"])


# ---------------------------------------------------------------- analysis
def test_analyze_unknown_product(client):
    r = client.post("/analyze", json={"product_id": "NOPE"})
    assert r.status_code == 404 and r.json()["error"] == "product_not_found"
    assert client.post("/analyze", json={}).status_code == 422


def test_results_before_analysis(client):
    load_sample(client)
    r = client.get("/results/P001")
    assert r.status_code == 404 and r.json()["error"] == "not_analyzed"
    assert client.get("/results/NOPE").json()["error"] == "product_not_found"


def test_missing_api_key_reported_before_queueing(client, monkeypatch):
    load_sample(client)
    monkeypatch.setattr(config, "settings", replace(config.settings, use_mock_llm=False, llm_api_key=""))
    r = client.post("/analyze", json={"product_id": "P001"})
    assert r.status_code == 400 and r.json()["error"] == "llm_api_key_missing"
    assert "LLM_API_KEY" in r.json()["message"]
    assert client.get("/health").json()["llm_ready"] is False


def test_full_pipeline_end_to_end(client):
    load_sample(client)
    _, run = analyze(client)
    assert run["status"] == "done" and run["progress"] == 100 and run["error"] is None
    res = client.get("/results/P001")
    assert res.status_code == 200
    j = res.json()
    json.dumps(j, allow_nan=False)                                   # strictly JSON-safe
    assert j["product"]["product_name"].startswith("AuraBeat") and j["product"]["total_reviews"] == 67
    assert j["product"]["rows_in_file"] == 71 and j["product"]["removed_as_empty_noise_or_duplicate"] == 4
    pct = j["sentiment"]["percentages"]
    assert abs(sum(pct.values()) - 100) < 0.5 and j["sentiment"]["overall"]
    names = [a["aspect"] for a in j["aspects"]]
    assert {"sound", "battery", "microphone"} <= set(names)
    assert j["recurring_issues"][0]["aspect"] == "microphone"
    assert j["summary"]["mode"] == "mock" and j["summary"]["pros"]
    assert j["validation"]["verdict"] in ("Evidence-backed", "Needs Review") and j["validation"]["checks"]
    assert j["analysis"]["run"]["status"] == "done"
    assert client.get("/products").json()["products"][0]["analyzed"] in (True, False)


def test_reanalysis_replaces_results_not_duplicates(client):
    load_sample(client)
    analyze(client)
    n1 = len(client.get("/results/P001").json()["aspects"])
    analyze(client)
    j = client.get("/results/P001").json()
    assert len(j["aspects"]) == n1
    from app.models.db import Summary, Validation
    with new_session() as s:
        assert s.query(Summary).filter_by(product_id="P001").count() == 1
        assert s.query(Validation).filter_by(product_id="P001").count() == 1


def test_second_product_is_independent(client):
    load_sample(client)
    analyze(client, "P002")
    assert client.get("/results/P002").json()["product"]["product_name"].startswith("Nova")
    assert client.get("/results/P001").status_code == 404


def test_reupload_replaces_product_and_clears_results(client):
    load_sample(client)
    analyze(client)
    load_sample(client)
    assert client.get("/results/P001").json()["error"] == "not_analyzed"
    assert next(p for p in client.get("/products").json()["products"] if p["product_id"] == "P001")["review_count"] == 67


def test_active_run_is_reused_not_duplicated(client):
    load_sample(client)
    from app.models.db import AnalysisRun
    with new_session() as s:
        s.add(AnalysisRun(id="running-1", product_id="P001", status="running", stage="x", progress=10))
        s.commit()
    r = client.post("/analyze", json={"product_id": "P001"})
    assert r.status_code == 202 and r.json()["run_id"] == "running-1"


def test_llm_failure_keeps_nlp_results_and_reports_error(client, monkeypatch):
    load_sample(client)

    def boom(*a, **k):
        raise DataValidationError("llm_unavailable", "The LLM service could not be reached.", status_code=503)
    monkeypatch.setattr("app.services.analysis_service.generate_summary", boom)
    _, run = analyze(client)
    assert run["status"] == "failed" and run["error"]["error"] == "llm_unavailable"
    j = client.get("/results/P001").json()
    assert j["summary"] is None and j["validation"] is None and j["aspects"]     # NLP results survive
    assert j["analysis"]["run"]["error"]["stage"] == "summary"


def test_unexpected_pipeline_error_is_contained(client, monkeypatch):
    load_sample(client)
    monkeypatch.setattr("app.services.analysis_service.analyze_product",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret internals")))
    _, run = analyze(client)
    assert run["status"] == "failed" and run["error"]["error"] == "internal_error"
    assert "secret" not in json.dumps(run)
    assert client.get("/health").status_code == 200                # server still healthy


def test_unknown_run_and_unknown_route(client):
    assert client.get("/analyze/nope").json()["error"] == "run_not_found"
    assert client.get("/nothing").json()["error"] == "http_error"


def test_unhandled_exception_returns_generic_500(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.repo.list_products", lambda s: 1 / 0)
    c = TestClient(client.app, raise_server_exceptions=False)
    r = c.get("/products")
    assert r.status_code == 500 and r.json()["error"] == "internal_error" and "division" not in r.text


def test_reviews_store_sentiment_after_analysis(client):
    load_sample(client)
    analyze(client)
    from app.models.db import Review
    with new_session() as s:
        rows = s.query(Review).filter_by(product_id="P001").all()
        assert len(rows) == 67 and all(r.sentiment in ("positive", "neutral", "negative") for r in rows)


# ---------------------------------------------------------------- Phase 11: restart safety + CORS
def test_interrupted_runs_are_failed_on_startup(tmp_path):
    configure_engine(f"sqlite:///{tmp_path/'restart.db'}")
    from app.main import app
    from app.models.db import AnalysisRun
    with TestClient(app):                                     # first "process"
        pass
    with new_session() as s:
        s.add_all([AnalysisRun(id="stuck-1", product_id="P1", status="running", stage="x", progress=40),
                   AnalysisRun(id="stuck-2", product_id="P2", status="queued"),
                   AnalysisRun(id="ok-1", product_id="P3", status="done", progress=100)])
        s.commit()
    with TestClient(app) as c:                                # "restart"
        r1, r2, r3 = (c.get(f"/analyze/{i}").json() for i in ("stuck-1", "stuck-2", "ok-1"))
    assert r1["status"] == "failed" and r1["error"]["error"] == "interrupted" and r2["status"] == "failed"
    assert r3["status"] == "done"                              # finished runs untouched


def test_cors_allows_the_frontend_origin_only(client):
    ok = client.options("/analyze", headers={"Origin": "http://localhost:5173",
                                             "Access-Control-Request-Method": "POST",
                                             "Access-Control-Request-Headers": "content-type"})
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "POST" in ok.headers["access-control-allow-methods"]
    bad = client.options("/analyze", headers={"Origin": "http://evil.example",
                                              "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bad.headers
    simple = client.get("/health", headers={"Origin": "http://127.0.0.1:5173"})
    assert simple.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_upload_reports_which_products_came_from_this_file(client):
    load_sample(client)
    csv = "product_id,product_name,review\n" + "\n".join(f"W1,Widget,Battery is great number {i}" for i in range(4))
    j = client.post("/upload", files=csv_file(csv)).json()
    assert j["uploaded_product_ids"] == ["W1"]
    assert {p["product_id"] for p in j["products"]} == {"P001", "P002", "W1"}      # older products still listed
