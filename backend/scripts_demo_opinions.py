"""Manual check: python scripts_demo_opinions.py [file.csv] [--sentiment vader|...] [--embedding tfidf|sbert|auto]"""
import sys
from pathlib import Path
from app.services.ingestion import ingest_file
from app.services.cleaning import clean_dataframe
from app.nlp.aspects import extract_aspects
from app.nlp.opinions import aggregate_opinions
from app.nlp.sentiment import get_analyzer
from app.nlp.embeddings import get_embedder
from app.utils.errors import DataValidationError

def opt(name):
    return next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == name), None)
args = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and not sys.argv[i - 1].startswith("--")]
path = args[0] if args else Path(__file__).parents[1] / "data" / "sample_reviews.csv"
try:
    df = clean_dataframe(ingest_file(path).df).df
    an, emb = get_analyzer(opt("--sentiment")), get_embedder(opt("--embedding"))
    for name, g in df.groupby("product_name"):
        ex = extract_aspects(g, an)
        agg = aggregate_opinions(ex, emb)
        print(f"\n== {name} ({ex.review_count} reviews; min_count={agg.min_count}; embedder={agg.embedder}) ==")
        for title, items in (("RECURRING STRENGTHS", agg.strengths), ("RECURRING ISSUES", agg.issues)):
            print(f"\n{title}")
            for it in items:
                flag = "  [contested]" if it["contested"] else ""
                print(f"  {it['aspect']:<20} x{it['count']:<3} ({it['share_of_aspect']:.0%} of mentions){flag}")
                for t in it["themes"]:
                    print(f"      - {t['label']}  (x{t['count']})")
        print("\nCONTESTED:", [(c["aspect"], c["positive"], c["negative"]) for c in agg.contested])
except DataValidationError as e:
    print("ERROR:", e.message); sys.exit(1)
