"""Small cue lexicons for reading the direction of a claim in generated text."""
from __future__ import annotations

import re

POS_CUES = ("love", "great", "excellent", "prais", "strong", "good", "impress", "amaz", "best", "positive",
            "comfortable", "comfy", "reliable", "superb", "fantastic", "standout", "favorite", "favourite",
            "solid", "crisp", "smooth", "sturdy", "recommend", "delight", "happy", "satisf", "outstanding",
            "exceptional", "pleasant", "rich", "punchy", "clear", "fast", "worth", "enjoy", "like", "appreciat",
            "highlight", "well")
NEG_CUES = ("poor", "bad", "terrible", "awful", "horrible", "weak", "complain", "concern", "issue", "problem",
            "disappoint", "unreliable", "unclear", "muffled", "fail", "broke", "break", "flimsy", "frustrat",
            "lack", "negative", "critic", "drawback", "downside", "defect", "faulty", "worst", "unusable",
            "useless", "crack", "annoying", "buggy", "laggy", "overpriced", "drain", "overheat", "unhappy",
            "dissatisf", "struggle", "mediocre", "subpar", "dislike", "hate", "unsatisf", "trouble", "fault")
NEGATIONS = {"not", "no", "never", "hardly", "without", "n't", "cannot", "neither", "nor"}
HEDGES = {"some", "mixed", "few", "several", "certain", "occasionally", "sometimes", "divided", "split",
          "a few", "minority", "small", "isolated", "slightly", "somewhat"}

_TOKEN = re.compile(r"[a-z']+")


def _cue(tok: str, cues: tuple) -> bool:
    return any(tok.startswith(c) for c in cues)


def claim_direction(text: str) -> tuple[str | None, bool]:
    """Return ('positive'|'negative'|None, hedged) for a clause of text."""
    toks = _TOKEN.findall(text.lower())
    pos = neg = 0
    for i, t in enumerate(toks):
        is_pos, is_neg = _cue(t, POS_CUES), _cue(t, NEG_CUES)
        if not (is_pos or is_neg):
            continue
        negated = any(p in NEGATIONS or p.endswith("n't") for p in toks[max(0, i - 3):i])
        if is_pos:
            neg, pos = (neg + 1, pos) if negated else (neg, pos + 1)
        else:
            pos, neg = (pos + 1, neg) if negated else (pos, neg + 1)
    hedged = any(t in HEDGES for t in toks) or "a few" in text.lower()
    if pos == neg:
        return None, hedged
    return ("positive" if pos > neg else "negative"), hedged
