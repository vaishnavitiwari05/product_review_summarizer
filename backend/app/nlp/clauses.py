"""Split reviews into clauses so each opinion can be scored on its own.

"Sound is great but the mic is terrible"  ->  ["Sound is great", "the mic is terrible"]
"""
from __future__ import annotations

import re

_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])|\n+")
_CONTRAST = re.compile(r"\s*(?:;|,?\s+\b(?:but|however|although|though|while|whereas|yet|except)\b)\s+", re.I)
_VERBS = (r"is|are|was|were|has|have|had|feels?|sounds?|looks?|works?|lasts?|does|doesn't|isn't|aren't|"
          r"wasn't|weren't|comes?|arrived|took|broke|stopped|keeps?|gets?|got|runs?|charges?|drains?|"
          r"connects?|blocks?|cuts?")
# split on "and" only when what follows looks like a NEW clause: "... and the battery is ..."
_AND_CLAUSE = re.compile(
    rf"\s*,?\s+\band\b\s+(?=(?:the\s+|my\s+|its\s+|it\s+|a\s+)?[\w-]+(?:\s+[\w-]+){{0,2}}?\s+(?:{_VERBS})\b)", re.I)
# comma splice: "The sound is amazing, the microphone is awful"
_COMMA_CLAUSE = re.compile(
    rf",\s+(?=(?:the\s+|my\s+|its\s+|it\s+|a\s+)?[\w-]+(?:\s+[\w-]+){{0,2}}?\s+(?:{_VERBS})\b)", re.I)
_MIN_WORDS = 2


def split_clauses(text: str) -> list[str]:
    clauses: list[str] = []
    for sent in _SENT.split(text.strip()):
        for part in _CONTRAST.split(sent):
            for piece in _COMMA_CLAUSE.split(part):
                for sub in _AND_CLAUSE.split(piece):
                    sub = sub.strip(" ,.-!?")
                    if len(sub.split()) >= _MIN_WORDS:
                        clauses.append(sub)
    return clauses or ([text.strip()] if text.strip() else [])
