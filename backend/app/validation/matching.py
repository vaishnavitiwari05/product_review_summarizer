"""Find which analysed aspects a piece of generated text talks about."""
from __future__ import annotations

import re

from app.nlp.aspects import ADJ_ASPECTS, SYNONYMS

# extra ways a writer may refer to an aspect (matching only - discovery is data-driven)
EXTRA_ALIASES = {
    "sound": ["audio", "sound quality", "audio quality"],
    "microphone": ["call quality", "mic", "voice pickup", "voice quality", "voice"],
    "battery": ["battery life", "battery backup", "charge", "battery lasts"],
    "durability": ["build quality", "build", "longevity", "sturdiness", "reliability", "hinge"],
    "comfort": ["comfortable", "comfy", "fit", "ear cushions"],
    "price": ["value", "cost", "affordable", "expensive", "worth"],
    "design": ["look", "looks", "style", "stylish", "sleek"],
    "camera": ["photo", "photos", "pictures"],
    "screen": ["display"],
    "performance": ["speed", "fast", "laggy"],
    "customer service": ["support", "service", "after-sales"],
    "connectivity": ["bluetooth", "connection", "pairing"],
    "delivery": ["shipping"],
    "packaging": ["package", "box"],
}


class AspectMatcher:
    def __init__(self, aspects: list[str]):
        self.patterns: dict[str, re.Pattern] = {}
        rev: dict[str, list[str]] = {}
        for src, dst in {**SYNONYMS, **ADJ_ASPECTS}.items():
            rev.setdefault(dst, []).append(src)
        for a in aspects:
            forms = {a, *rev.get(a, []), *EXTRA_ALIASES.get(a, [])}
            alt = "|".join(sorted((re.escape(f) for f in forms), key=len, reverse=True))
            self.patterns[a] = re.compile(rf"\b(?:{alt})(?:s|es)?\b", re.I)

    def match(self, text: str) -> list[str]:
        hits = [(m.start(), a) for a, p in self.patterns.items() for m in [p.search(text)] if m]
        return [a for _, a in sorted(hits)]
