"""Phase 4: sentiment classifiers.

Two interchangeable backends behind one interface:
  * TransformerSentimentAnalyzer - pretrained 3-class model (negative / neutral / positive)
  * VaderSentimentAnalyzer       - rule-based fallback, no download, used in tests/offline

Both classify TEXT ONLY. Star ratings are never used to decide sentiment.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.utils.errors import DataValidationError

log = logging.getLogger(__name__)
LABELS = ("negative", "neutral", "positive")


@dataclass
class SentimentPrediction:
    label: str            # negative | neutral | positive
    score: float          # signed polarity in [-1, 1] (P(pos) - P(neg))
    confidence: float     # probability of the chosen label, 0-1


class SentimentAnalyzer(ABC):
    name: str = "base"
    # True for word-list scorers: aspect words are masked before scoring (see aspects._mask_terms)
    lexicon_based: bool = False

    @abstractmethod
    def predict(self, texts: list[str]) -> list[SentimentPrediction]: ...


class VaderSentimentAnalyzer(SentimentAnalyzer):
    name = "vader"
    lexicon_based = True
    # Review-tuned thresholds (VADER's default +-0.05 over-labels reviews as non-neutral)
    POS, NEG = 0.25, -0.25

    def __init__(self) -> None:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        self._vader = SentimentIntensityAnalyzer()

    def predict(self, texts: list[str]) -> list[SentimentPrediction]:
        out = []
        for t in texts:
            c = self._vader.polarity_scores(t)["compound"]
            label = "positive" if c >= self.POS else "negative" if c <= self.NEG else "neutral"
            conf = min(1.0, 0.5 + abs(c) / 2) if label != "neutral" else 1 - abs(c) / self.POS * 0.5
            out.append(SentimentPrediction(label, round(c, 4), round(conf, 4)))
        return out


class TransformerSentimentAnalyzer(SentimentAnalyzer):
    name = "transformer"

    def __init__(self, model_name: str, batch_size: int = 32) -> None:
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("transformers/torch not installed") from exc
        self._torch = torch
        self.model_name = model_name
        self.batch_size = batch_size
        self._tok = AutoTokenizer.from_pretrained(model_name)
        self._model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self._model.eval()
        # map model output ids -> our labels by name (models order labels differently)
        id2label = {int(i): str(l).lower() for i, l in self._model.config.id2label.items()}
        self._idx = {}
        for i, l in id2label.items():
            key = ("negative" if l in ("negative", "neg", "label_0") else
                   "neutral" if l in ("neutral", "neu", "label_1") else
                   "positive" if l in ("positive", "pos", "label_2") else None)
            if key:
                self._idx[key] = i
        if set(self._idx) != set(LABELS):
            raise RuntimeError(f"Model labels {id2label} are not 3-class negative/neutral/positive")

    def predict(self, texts: list[str]) -> list[SentimentPrediction]:
        torch = self._torch
        out: list[SentimentPrediction] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            enc = self._tok(batch, padding=True, truncation=True, max_length=256, return_tensors="pt")
            with torch.no_grad():
                probs = torch.softmax(self._model(**enc).logits, dim=-1).cpu().numpy()
            for p in probs:
                pn, pu, pp = p[self._idx["negative"]], p[self._idx["neutral"]], p[self._idx["positive"]]
                label = LABELS[[pn, pu, pp].index(max(pn, pu, pp))]
                out.append(SentimentPrediction(label, round(float(pp - pn), 4),
                                               round(float(max(pn, pu, pp)), 4)))
        return out


_cached: SentimentAnalyzer | None = None


def get_analyzer(backend: str | None = None, model: str | None = None,
                 batch_size: int | None = None, use_cache: bool = True) -> SentimentAnalyzer:
    """Build the analyzer selected by config. 'auto' falls back to VADER with a warning."""
    global _cached
    from app.utils.config import settings
    backend = (backend or settings.sentiment_backend).lower()
    if use_cache and _cached is not None and backend == "auto":
        return _cached
    model = model or settings.sentiment_model
    batch_size = batch_size or settings.sentiment_batch_size

    if backend == "vader":
        an: SentimentAnalyzer = VaderSentimentAnalyzer()
    elif backend in ("transformer", "auto"):
        try:
            an = TransformerSentimentAnalyzer(model, batch_size)
        except Exception as exc:  # network, missing libs, bad model
            if backend == "transformer":
                raise DataValidationError(
                    "sentiment_model_unavailable",
                    "The sentiment model could not be loaded. Check your internet connection "
                    "and that 'transformers' and 'torch' are installed, or set SENTIMENT_BACKEND=vader.",
                    status_code=503, details={"reason": str(exc)[:200]})
            log.warning("Transformer sentiment unavailable (%s); falling back to VADER.", exc)
            an = VaderSentimentAnalyzer()
    else:
        raise ValueError(f"Unknown SENTIMENT_BACKEND '{backend}'")
    if use_cache and backend == "auto":
        _cached = an
    return an
