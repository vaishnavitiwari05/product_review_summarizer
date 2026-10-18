"""Manual check: python scripts_demo_aspects.py [file.csv] [--backend vader|transformer|auto]"""
import sys
from pathlib import Path
from app.services.ingestion import ingest_file
from app.services.cleaning import clean_dataframe
from app.nlp.aspects import extract_aspects
from app.nlp.sentiment import get_analyzer
from app.utils.errors import DataValidationError

args = [a for a in sys.argv[1:] if not a.startswith("--")]
backend = next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--backend"), None)
if backend in args: args.remove(backend)
path = args[0] if args else Path(__file__).parents[1] / "data" / "sample_reviews.csv"
try:
    df = clean_dataframe(ingest_file(path).df).df
    analyzer = get_analyzer(backend)
    for name, g in df.groupby("product_name"):
        res = extract_aspects(g, analyzer)
        print(f"\n== {name}  ({res.review_count} reviews, min support {res.min_support}) ==")
        print(f"{'aspect':<20}{'freq':>5}{'pos':>5}{'neu':>5}{'neg':>5}  polarity")
        for a in res.aspects:
            print(f"{a['aspect']:<20}{a['frequency']:>5}{a['positive']:>5}{a['neutral']:>5}{a['negative']:>5}  {a['polarity']}")
except DataValidationError as e:
    print("ERROR:", e.message); sys.exit(1)
