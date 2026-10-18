"""Deterministic offline summariser (development / demo mode, no API key needed).

Builds the same JSON structure as the real LLM, straight from the structured payload."""
from __future__ import annotations

from app.llm.schemas import AspectNote, LLMSummary


def _t(aspect: str) -> str:
    return aspect[:1].upper() + aspect[1:]


def _dominant(g: dict, key: str) -> bool:
    """True when this side outweighs the opposite side of the same aspect."""
    return g[key] > g.get("opposite_mentions", 0)


def mock_summary(p: dict) -> LLMSummary:
    s = p["sentiment"]
    strengths, issues = p["recurring_strengths"], p["recurring_issues"]
    n = p["total_reviews_analyzed"]
    main_pros = [g for g in strengths if _dominant(g, "positive_mentions")]
    main_cons = [g for g in issues if _dominant(g, "negative_mentions")]
    mixed = [g["aspect"] for g in strengths + issues
             if g not in main_pros and g not in main_cons]
    mixed = list(dict.fromkeys(mixed))

    parts = [f"Customers are {s['overall'].lower()} about {p['product']}: "
             f"{s['positive_pct']:.0f}% of {n} reviews are positive and {s['negative_pct']:.0f}% negative."]
    if main_pros:
        parts.append("Most praised: " + ", ".join(g["aspect"] for g in main_pros[:3]) + ".")
    if main_cons:
        parts.append("Main concerns: " + ", ".join(g["aspect"] for g in main_cons[:3]) + ".")
    elif not issues:
        parts.append("No complaint recurs often enough to stand out.")
    if mixed:
        parts.append("Opinions are mixed on " + ", ".join(mixed[:3]) + ".")

    def line(g, key, word):
        return (f"{_t(g['aspect'])}: {g[key]} {word} mentions"
                f" ({g['share_of_aspect_mentions_pct']}% of reviews that discuss it)"
                + (" - opinions are mixed" if g["also_has_opposite_opinion"] else ""))

    notes = []
    for a in p["major_aspects"][:5]:
        lean = "mostly positive" if a["positive"] > 2 * a["negative"] else \
               "mostly negative" if a["negative"] > 2 * a["positive"] else "mixed"
        notes.append(AspectNote(aspect=_t(a["aspect"]),
                                note=f"Discussed in {a['reviews_mentioning']} reviews; {lean} "
                                     f"({a['positive']} positive, {a['negative']} negative)."))
    net = s["positive_pct"] - s["negative_pct"]
    return LLMSummary(
        overall_summary=" ".join(parts),
        pros=[line(g, "positive_mentions", "positive") for g in main_pros[:5]],
        cons=[line(g, "negative_mentions", "negative") for g in main_cons[:5]],
        recurring_issues=[f"{_t(g['aspect'])} ({g['negative_mentions']} complaints"
                          + ("" if g in main_cons else ", but feedback is mixed") + ")" for g in issues[:5]],
        important_aspects=notes,
        sentiment_explanation=(f"{s['positive_pct']:.0f}% positive versus {s['negative_pct']:.0f}% negative "
                               f"gives a net sentiment of {net:+.0f} points, which is labelled '{s['overall']}'."))
