"""Manual check: python scripts_demo_sentiment.py [file.csv] [--backend vader|transformer|auto]"""
import json, sys
from pathlib import Path
from app.services.ingestion import ingest_file
from app.services.cleaning import clean_dataframe
from app.services.sentiment_service import add_sentiment, summarize_sentiment
from app.nlp.sentiment import get_analyzer
from app.utils.errors import DataValidationError

args = [a for a in sys.argv[1:] if not a.startswith("--")]
backend = next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--backend"), None)
if backend in args: args.remove(backend)
path = args[0] if args else Path(__file__).parents[1] / "data" / "sample_reviews.csv"
try:
    df = clean_dataframe(ingest_file(path).df).df
    df = add_sentiment(df, get_analyzer(backend))
except DataValidationError as e:
    print("ERROR:", json.dumps(e.to_dict(), indent=2)); sys.exit(1)
for pid, g in df.groupby("product_name"):
    print(f"\n== {pid} ==")
    print(json.dumps(summarize_sentiment(g), indent=2))
print("\nSample predictions:")
print(df[["review_clean", "rating", "sentiment", "sentiment_score"]].head(8).to_string(max_colwidth=60))
