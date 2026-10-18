"""Orchestrates the NLP phases for ONE product (used by the demo now and the API in Phase 9)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from app.llm.payload import build_payload
from app.nlp.aspects import AspectExtraction, extract_aspects
from app.nlp.embeddings import Embedder, get_embedder
from app.nlp.opinions import OpinionAggregation, aggregate_opinions
from app.nlp.sentiment import SentimentAnalyzer, get_analyzer
from app.services.cleaning import dataset_stats
from app.services.sentiment_service import add_sentiment, summarize_sentiment
from app.utils.errors import DataValidationError


@dataclass
class Findings:
    product_id: str
    product_name: str
    stats: dict
    sentiment: dict
    reviews: pd.DataFrame
    extraction: AspectExtraction
    opinions: OpinionAggregation
    notes: list

    def payload(self) -> dict:
        return build_payload(self.product_name, self.stats, self.sentiment, self.extraction,
                             self.opinions, self.notes)


def analyze_product(clean_df: pd.DataFrame, product_id: str, analyzer: SentimentAnalyzer | None = None,
                    embedder: Embedder | None = None, notes: list | None = None,
                    progress: Callable[[str, int], None] | None = None) -> Findings:
    sub = clean_df[clean_df["product_id"] == product_id]
    if sub.empty:
        raise DataValidationError("product_not_found", f"No reviews found for product '{product_id}'.",
                                  status_code=404)
    report = progress or (lambda stage, pct: None)
    report("Loading language models", 8)
    analyzer = analyzer or get_analyzer()
    embedder = embedder or get_embedder()
    report("Analysing sentiment", 15)
    scored = add_sentiment(sub, analyzer)
    report("Extracting aspects", 40)
    extraction = extract_aspects(scored, analyzer)
    report("Grouping recurring opinions", 62)
    opinions = aggregate_opinions(extraction, embedder)
    notes = list(notes or [])
    if len(sub) < 20:
        notes.append(f"Only {len(sub)} reviews analysed; treat percentages as rough.")
    return Findings(product_id, str(sub["product_name"].iloc[0]), dataset_stats(sub),
                    summarize_sentiment(scored), scored, extraction, opinions, notes)
