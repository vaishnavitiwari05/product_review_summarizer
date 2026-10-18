"""Manual check: python scripts_demo_clean.py [path/to/file.csv]"""
import json, sys
from pathlib import Path
from app.services.ingestion import ingest_file
from app.services.cleaning import clean_dataframe
from app.utils.errors import DataValidationError

path = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parents[1] / "data" / "sample_reviews.csv"
try:
    res = clean_dataframe(ingest_file(path).df)
except DataValidationError as e:
    print("ERROR:", json.dumps(e.to_dict(), indent=2)); sys.exit(1)
print(json.dumps(res.stats.to_dict(), indent=2))
print(res.df[["product_id", "review_raw", "review"]].head(5).to_string())
