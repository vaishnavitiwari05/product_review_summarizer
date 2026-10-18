"""Low-level text cleaning helpers (pure functions, no pandas)."""
from __future__ import annotations

import html
import re
import unicodedata

_TAG = re.compile(r"<[^>]+>")
_URL = re.compile(r"(?:https?://|www\.)\S+", re.I)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\U0000FE0F\U0000200D]+")
_REPEAT_PUNCT = re.compile(r"([!?.,])\1{1,}")
_REPEAT_CHAR = re.compile(r"([A-Za-z])\1{3,}")          # soooooo -> soo
_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9\s]")
_QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
                         "\u2013": "-", "\u2014": "-", "\u00a0": " "})


def clean_text(text: str) -> str:
    """Remove obvious noise while keeping the review readable and case intact
    (transformer sentiment models use casing/punctuation as signal)."""
    if not isinstance(text, str):
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = html.unescape(t)
    t = _TAG.sub(" ", t)
    t = _URL.sub(" ", t)
    t = _EMAIL.sub(" ", t)
    t = _EMOJI.sub(" ", t)
    t = t.translate(_QUOTES)
    t = "".join(ch for ch in t if ch.isprintable() or ch.isspace())
    t = _REPEAT_PUNCT.sub(r"\1", t)
    t = _REPEAT_CHAR.sub(r"\1\1", t)
    return _WS.sub(" ", t).strip()


def dedupe_key(text: str) -> str:
    """Case/punctuation/spacing-insensitive key for duplicate detection."""
    t = _NON_ALNUM.sub(" ", clean_text(text).lower())
    return _WS.sub(" ", t).strip()


def token_signature(text: str) -> str:
    """Order-insensitive signature: catches re-ordered / re-punctuated copies."""
    return " ".join(sorted(set(dedupe_key(text).split())))


def has_content(text: str, min_words: int = 1, min_chars: int = 3) -> bool:
    """False for reviews that are only symbols/numbers or too short to analyse."""
    words = re.findall(r"[A-Za-z]{2,}", text)
    return len(words) >= min_words and len(text) >= min_chars
