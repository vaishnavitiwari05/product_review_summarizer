#!/usr/bin/env python3
"""End-to-end benchmark against a RUNNING backend: upload -> analyze every product -> compare to ground truth.

    python scripts/benchmark.py --reviews 5000 [--api http://127.0.0.1:8000]
"""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reviews", type=int, default=5000)
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    tmp = Path(tempfile.mkdtemp()) / "bench.csv"
    subprocess.run([sys.executable, str(ROOT / "data" / "generate_synthetic.py"), "--reviews", str(a.reviews),
                    "--out", str(tmp), "--seed", str(a.seed)], check=True)
    truth = json.loads(tmp.with_suffix(".truth.json").read_text())

    c = httpx.Client(base_url=a.api, timeout=900)
    t0 = time.time()
    up = c.post("/upload", files={"file": ("bench.csv", tmp.read_bytes(), "text/csv")})
    if up.status_code != 200:
        print("UPLOAD FAILED:", up.status_code, up.text[:300])
        return 1
    up = up.json()
    cl = up["cleaning"]
    print(f"upload+clean: {time.time() - t0:.1f}s | {cl['total_reviews']} rows -> {cl['valid_reviews']} valid "
          f"({cl['duplicates_removed']} duplicates, {cl['empty_removed']} empty, {cl['noise_removed']} noise)")

    ok_count = n_count = 0
    for pid in up["uploaded_product_ids"]:
        t1 = time.time()
        run = c.post("/analyze", json={"product_id": pid}).json()
        while run["status"] not in ("done", "failed"):
            time.sleep(0.5)
            run = c.get(f"/analyze/{run['run_id']}").json()
        took = time.time() - t1
        if run["status"] != "done":
            print(f"{pid}: FAILED {run['error']}")
            return 1
        r = c.get(f"/results/{pid}").json()
        print(f"\n=== {r['product']['product_name']} | {r['product']['total_reviews']} reviews | analysed in {took:.1f}s "
              f"| sentiment {r['sentiment']['overall']} | {r['validation']['verdict']} ({r['validation']['score']}) ===")
        found = {x["aspect"]: x for x in r["aspects"]}
        print(f"{'aspect':<18}{'truth pos/neg/neu':>20}{'found pos/neg/neu':>20}  dominant polarity")
        for asp, t in truth[pid].items():
            tp, tn, tu = t.get("positive", 0), t.get("negative", 0), t.get("neutral", 0)
            f = found.get(asp)
            n_count += 1
            if not f:
                print(f"{asp:<18}{f'{tp}/{tn}/{tu}':>20}{'(not found)':>20}  MISSING")
                continue
            td = "positive" if tp > 2 * tn else "negative" if tn > 2 * tp else "mixed"
            ok = f["polarity"] == td
            ok_count += ok
            print(f"{asp:<18}{f'{tp}/{tn}/{tu}':>20}{str(f['positive']) + '/' + str(f['negative']) + '/' + str(f['neutral']):>20}"
                  f"  truth={td:<9} found={f['polarity']:<9} {'OK' if ok else 'DIFF'}")
    print(f"\naspects found with the correct dominant polarity: {ok_count}/{n_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
