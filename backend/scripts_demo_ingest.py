"""Manual check: python scripts_demo_ingest.py [path/to/file.csv]"""
import json, sys
from pathlib import Path
from app.services.ingestion import ingest_file, list_products
from app.utils.errors import DataValidationError

path = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parents[1] / "data" / "sample_reviews.csv"
try:
    res = ingest_file(path)
except DataValidationError as e:
    print("ERROR:", json.dumps(e.to_dict(), indent=2)); sys.exit(1)
print(json.dumps(res.report.to_dict(), indent=2, default=str))
print("\nProducts:", json.dumps(list_products(res.df), indent=2))
print("\n", res.df.head(3).to_string())
