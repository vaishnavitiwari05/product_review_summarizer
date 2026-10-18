#!/usr/bin/env python3
"""Process-level robustness checks against REAL server processes (things TestClient cannot do).

    python scripts/robustness_live.py

Starts/stops its own uvicorn servers on temporary databases (offline NLP backends, mock LLM unless a check
says otherwise). Checks:
  1. hard crash (kill -9) in the middle of an analysis, restart on the same DB -> run reported as interrupted,
     data intact, re-analysis works
  2. three analyses requested at once -> all finish (serialised), none fail
  3. real LLM call with an INVALID key -> friendly error, NLP results kept, key never echoed
     (needs internet; offline you will see llm_unavailable, which is also accepted)
  4. LLM enabled but no key -> rejected up-front with a clear message
  5. oversized upload and a garbage "CSV" -> clean 4xx errors, server stays healthy
"""
from __future__ import annotations

import os
import random
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  - {detail}" if detail else ""), flush=True)


class Server:
    def __init__(self, port: int, db: Path, **env: str):
        self.port, self.db, self.env = port, db, env
        self.proc: subprocess.Popen | None = None
        self.http = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=300)

    def start(self) -> "Server":
        env = {**os.environ, "DATABASE_URL": f"sqlite:///{self.db}", "SENTIMENT_BACKEND": "vader",
               "EMBEDDING_BACKEND": "tfidf", "USE_MOCK_LLM": "true", "MAX_UPLOAD_MB": "100",
               "CORS_ORIGINS": "http://localhost:5173", **self.env}
        env.pop("LLM_API_KEY", None) if "LLM_API_KEY" not in self.env else None
        self.proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(self.port),
                                      "--log-level", "warning"], cwd=ROOT / "backend", env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(80):
            try:
                if self.http.get("/health").status_code == 200:
                    return self
            except httpx.HTTPError:
                time.sleep(0.25)
        raise RuntimeError("server did not start")

    def kill9(self) -> None:
        if self.proc:
            self.proc.send_signal(signal.SIGKILL)
            self.proc.wait()

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def wait_run(self, run_id: str, timeout: float = 240) -> dict:
        end = time.time() + timeout
        while time.time() < end:
            run = self.http.get(f"/analyze/{run_id}").json()
            if run["status"] in ("done", "failed"):
                return run
            time.sleep(0.3)
        raise TimeoutError(run_id)


def synthetic_csv(n: int, tmp: Path) -> Path:
    out = tmp / "synthetic.csv"
    subprocess.run([sys.executable, str(ROOT / "data" / "generate_synthetic.py"), "--reviews", str(n), "--out", str(out)],
                   check=True, stdout=subprocess.DEVNULL)
    return out


def upload(srv: Server, path: Path) -> dict:
    r = srv.http.post("/upload", files={"file": (path.name, path.read_bytes(), "text/csv")})
    r.raise_for_status()
    return r.json()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="robust_"))
    csv_path = synthetic_csv(20000, tmp)

    print("1. crash (kill -9) during an analysis, then restart on the same database")
    db = tmp / "crash.db"
    srv = Server(8781, db).start()
    try:
        up = upload(srv, csv_path)
        pid = up["uploaded_product_ids"][0]
        run_id = srv.http.post("/analyze", json={"product_id": pid}).json()["run_id"]
        for _ in range(100):
            if srv.http.get(f"/analyze/{run_id}").json()["status"] == "running":
                break
            time.sleep(0.1)
        time.sleep(1.0)
        srv.kill9()
        srv = Server(8781, db).start()
        run = srv.http.get(f"/analyze/{run_id}").json()
        record("interrupted run is reported as failed, not 'running' forever",
               run["status"] == "failed" and (run["error"] or {}).get("error") == "interrupted", str(run["error"])[:80])
        prods = srv.http.get("/products").json()["products"]
        record("uploaded data survived the crash", len(prods) == 3 and all(p["review_count"] > 0 for p in prods))
        rerun = srv.wait_run(srv.http.post("/analyze", json={"product_id": pid}).json()["run_id"])
        record("re-analysing after the crash works", rerun["status"] == "done")
    finally:
        srv.stop()

    print("2. three analyses requested at the same moment")
    srv = Server(8782, tmp / "conc.db").start()
    try:
        up = upload(srv, csv_path)
        runs = [srv.http.post("/analyze", json={"product_id": p}).json()["run_id"] for p in up["uploaded_product_ids"]]
        t0 = time.time()
        outcomes = [srv.wait_run(r)["status"] for r in runs]
        record("all concurrent analyses finish", outcomes == ["done"] * 3, f"{outcomes} in {time.time() - t0:.0f}s")
        record("all products show as analysed", all(p["analyzed"] for p in srv.http.get("/products").json()["products"]))
        verdicts = [srv.http.get(f"/results/{p}").json()["validation"]["verdict"] for p in up["uploaded_product_ids"]]
        record("every result has a validation verdict", all(verdicts), str(verdicts))
    finally:
        srv.stop()

    print("3. real LLM call with an invalid API key")
    key = "sk-ant-THIS-IS-NOT-A-REAL-KEY-12345"
    srv = Server(8783, tmp / "badkey.db", USE_MOCK_LLM="false", LLM_PROVIDER="anthropic", LLM_API_KEY=key,
                 LLM_MAX_RETRIES="1", LLM_TIMEOUT_SECONDS="20").start()
    try:
        up = srv.http.post("/sample").json()
        run = srv.wait_run(srv.http.post("/analyze", json={"product_id": "P001"}).json()["run_id"])
        err = (run["error"] or {})
        record("run fails cleanly at the summary step", run["status"] == "failed" and err.get("stage") == "summary",
               err.get("error", ""))
        record("error is auth failure (or 'unavailable' when offline)", err.get("error") in ("llm_auth_failed", "llm_unavailable"))
        record("the API key is never echoed in the error", key not in str(run))
        res = srv.http.get("/results/P001").json()
        record("sentiment/aspects survive the LLM failure", bool(res.get("aspects")) and res["summary"] is None)
    finally:
        srv.stop()

    print("4. LLM enabled but no key configured")
    srv = Server(8784, tmp / "nokey.db", USE_MOCK_LLM="false", LLM_API_KEY="").start()
    try:
        srv.http.post("/sample")
        r = srv.http.post("/analyze", json={"product_id": "P001"})
        record("rejected up-front with a clear message", r.status_code == 400 and r.json()["error"] == "llm_api_key_missing"
               and "LLM_API_KEY" in r.json()["message"])
        h = srv.http.get("/health").json()
        record("/health reports the LLM is not ready", h["llm_ready"] is False)
    finally:
        srv.stop()

    print("5. oversized upload and a garbage file")
    srv = Server(8785, tmp / "limits.db", MAX_UPLOAD_MB="1").start()
    try:
        big = ("review\n" + "A reasonably long review sentence about the battery and the screen quality. \n" * 20000).encode()
        r = srv.http.post("/upload", files={"file": ("big.csv", big, "text/csv")})
        record("file over the limit -> 413 with a friendly message", r.status_code == 413 and r.json()["error"] == "file_too_large")
        junk = random.Random(1).randbytes(50_000)
        r = srv.http.post("/upload", files={"file": ("junk.csv", junk, "text/csv")})
        record("binary garbage named .csv -> clean 4xx (not 500)", 400 <= r.status_code < 500, f"{r.status_code} {r.json().get('error')}")
        r = srv.http.post("/upload", files={"file": ("x.csv", b"review\n", "text/csv")})
        record("headers-only CSV -> clean 4xx", 400 <= r.status_code < 500)
        record("server still healthy afterwards", srv.http.get("/health").status_code == 200)
    finally:
        srv.stop()

    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
