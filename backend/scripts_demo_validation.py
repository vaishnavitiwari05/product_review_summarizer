"""Manual check: python scripts_demo_validation.py [P001|P002] [--flawed]
--flawed validates a deliberately wrong summary so you can see the validator catch it."""
import json, sys
from pathlib import Path
from app.services.ingestion import ingest_file
from app.services.cleaning import clean_dataframe
from app.services.pipeline import analyze_product
from app.llm.summarizer import generate_summary
from app.llm.schemas import LLMSummary
from app.validation.validator import validate_summary
from app.utils.errors import DataValidationError

pid = next((a for a in sys.argv[1:] if not a.startswith("--")), "P001")
FLAWED = LLMSummary(
    overall_summary="Customers are overwhelmingly positive and generally love the microphone. Battery life is amazing.",
    pros=["Crystal-clear microphone", "Excellent battery life", "Great touch controls"],
    cons=["Slightly expensive"], recurring_issues=[],
    important_aspects=[{"aspect": "Microphone", "note": "Praised by 92% of users."}],
    sentiment_explanation="92% of reviews are positive.")
try:
    f = analyze_product(clean_dataframe(ingest_file(Path(__file__).parents[1] / "data" / "sample_reviews.csv").df).df, pid)
    summary = FLAWED if "--flawed" in sys.argv else generate_summary(f.payload()).summary
    r = validate_summary(summary, f)
    print(f"VERDICT: {r.verdict}   score {r.score}/100\n{r.headline}\n")
    for k in r.checks:
        print(f"[{k.status.upper():4}] {k.name}: {k.message}")
        for d in k.details[:3]: print("         -", d)
    print("\nCLAIMS")
    for c in r.claims:
        print(f"  {c.status:<12} {c.section:<17} {c.text[:70]!r} -> {c.aspect}")
except DataValidationError as e:
    print("ERROR:", e.message); sys.exit(1)
