"""Build the STRUCTURED findings sent to the LLM.

The LLM never sees raw reviews - only counts, percentages and a few short theme phrases
per recurring opinion. The payload size is bounded (top-N lists), so it stays small for
5 reviews or 500,000.
"""
from __future__ import annotations

import re

from app.nlp.aspects import AspectExtraction
from app.nlp.opinions import OpinionAggregation

TOP_ASPECTS, TOP_OPINIONS, MAX_PHRASES, MAX_PHRASE_LEN = 8, 5, 2, 120


def _phrase(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()[:MAX_PHRASE_LEN]


def _opinion(g: dict, count_key: str, opposite: dict) -> dict:
    return {
        "aspect": g["aspect"],
        count_key: g["count"],
        "opposite_mentions": opposite.get(g["aspect"], 0),      # mentions on the other side of this aspect
        "share_of_aspect_mentions_pct": round(g["share_of_aspect"] * 100),
        "also_has_opposite_opinion": g["contested"],
        "typical_phrases": [_phrase(t["label"]) for t in g["themes"][:MAX_PHRASES]],
    }


def build_payload(product_name: str, stats: dict, sentiment: dict, extraction: AspectExtraction,
                  opinions: OpinionAggregation, notes: list[str] | None = None) -> dict:
    pos_side = {c["aspect"]: c["negative"] for c in opinions.contested}    # for strengths: negative count
    neg_side = {c["aspect"]: c["positive"] for c in opinions.contested}    # for issues: positive count
    return {
        "product": _phrase(product_name),
        "total_reviews_analyzed": stats["total_reviews"],
        "average_rating": stats.get("average_rating"),
        "sentiment": {
            "positive_pct": sentiment["percentages"]["positive"],
            "neutral_pct": sentiment["percentages"]["neutral"],
            "negative_pct": sentiment["percentages"]["negative"],
            "overall": sentiment["overall"],
        },
        "major_aspects": [
            {"aspect": a["aspect"], "reviews_mentioning": a["frequency"], "positive": a["positive"],
             "neutral": a["neutral"], "negative": a["negative"]}
            for a in extraction.aspects[:TOP_ASPECTS]],
        "recurring_strengths": [_opinion(g, "positive_mentions", pos_side) for g in opinions.strengths[:TOP_OPINIONS]],
        "recurring_issues": [_opinion(g, "negative_mentions", neg_side) for g in opinions.issues[:TOP_OPINIONS]],
        "contested_aspects": [{"aspect": c["aspect"], "positive": c["positive"], "negative": c["negative"]}
                              for c in opinions.contested[:TOP_OPINIONS]],
        "data_notes": [_phrase(n) for n in (notes or [])][:5],
    }
