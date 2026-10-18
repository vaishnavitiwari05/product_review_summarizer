"""Manual check: python scripts_demo_llm.py [P001|P002] [--payload-only]
Uses USE_MOCK_LLM / LLM_* from backend/.env (mock by default)."""
import json, sys
from pathlib import Path
from app.services.ingestion import ingest_file
from app.services.cleaning import clean_dataframe
from app.services.pipeline import analyze_product
from app.llm.summarizer import generate_summary
from app.utils.errors import DataValidationError

pid = next((a for a in sys.argv[1:] if not a.startswith("--")), "P001")
try:
    clean = clean_dataframe(ingest_file(Path(__file__).parents[1] / "data" / "sample_reviews.csv").df).df
    f = analyze_product(clean, pid)
    payload = f.payload()
    print("=== PAYLOAD SENT TO LLM (%d chars) ===" % len(json.dumps(payload)))
    print(json.dumps(payload, indent=2))
    if "--payload-only" not in sys.argv:
        r = generate_summary(payload)
        print(f"\n=== SUMMARY (mode={r.mode}, model={r.model}) ===")
        print(json.dumps(r.summary.model_dump(), indent=2))
        for w in r.warnings: print("NOTE:", w)
except DataValidationError as e:
    print("ERROR:", e.code, "-", e.message); sys.exit(1)
