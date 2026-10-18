"""Phase 1 sanity check: confirms the sample dataset loads and covers required cases."""
from pathlib import Path
import sys
import pandas as pd

path = Path(__file__).with_name("sample_reviews.csv")
df = pd.read_csv(path)

required = {"product_id", "product_name", "review", "rating", "review_date"}
missing = required - set(df.columns)
assert not missing, f"Missing columns: {missing}"

blank = df["review"].isna() | (df["review"].astype(str).str.strip() == "")
norm = df["review"].astype(str).str.lower().str.split().str.join(" ")
dupes = norm[~blank].duplicated().sum()

print(f"File            : {path.name}")
print(f"Total rows      : {len(df)}")
print(f"Products        : {df.groupby('product_name').size().to_dict()}")
print(f"Empty reviews   : {int(blank.sum())}")
print(f"Duplicates      : {int(dupes)}")
print(f"Missing ratings : {int(df['rating'].isna().sum())}")
print(f"Missing dates   : {int(df['review_date'].isna().sum())}")
print("Rating spread   :", df["rating"].value_counts().sort_index().to_dict())

ok = len(df) >= 50 and dupes > 0 and blank.sum() > 0 and df["product_id"].nunique() >= 2
print("\nRESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
