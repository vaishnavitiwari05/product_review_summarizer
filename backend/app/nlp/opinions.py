"""Phase 6: recurring opinion aggregation.

Takes the Phase-5 aspect mentions and answers: which (aspect, opinion) pairs recur often
enough to be a real strength or a real issue?

  Level 1  group by (aspect, polarity)          ->  "Battery: Positive x 13"
  Level 2  cluster the clauses inside a group   ->  themes: "lasts all day" x 6, "charges fast" x 3

Classification (thresholds scale with dataset size):
  strength   positive group with count >= min_count
  issue      negative group with count >= min_count
  contested  aspect that has BOTH a strength and an issue group
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.nlp.aspects import AspectExtraction
from app.nlp.embeddings import Embedder, get_embedder


@dataclass
class OpinionAggregation:
    strengths: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    contested: list[dict] = field(default_factory=list)
    min_count: int = 0
    embedder: str = ""


MAX_CLUSTER = 1500     # agglomerative clustering is O(n^2): cluster a sample above this size


def _themes(clauses: list[str], ids: list[int], embedder: Embedder, max_themes: int = 3) -> list[dict]:
    """Cluster clauses of one (aspect, polarity) group into recurring sub-opinions."""
    total = len(clauses)
    if total < 2:
        return []
    scale = 1.0
    if total > MAX_CLUSTER:
        pick = np.random.default_rng(42).choice(total, MAX_CLUSTER, replace=False)
        clauses, ids = [clauses[i] for i in pick], [ids[i] for i in pick]
        scale = total / MAX_CLUSTER
    from sklearn.cluster import AgglomerativeClustering
    vecs = embedder.embed(clauses)
    labels = AgglomerativeClustering(n_clusters=None, metric="cosine", linkage="average",
                                     distance_threshold=embedder.distance_threshold).fit_predict(vecs)
    out = []
    for lab in np.unique(labels):
        idx = np.where(labels == lab)[0]
        sub = vecs[idx]
        centroid = sub.mean(axis=0)
        rep = idx[int(np.argmax(sub @ centroid))] if np.linalg.norm(centroid) else idx[0]
        out.append({"label": clauses[rep], "count": int(round(len(idx) * scale)),
                    "review_ids": [ids[i] for i in idx]})
    out.sort(key=lambda t: t["count"], reverse=True)
    return out[:max_themes]


def aggregate_opinions(extraction: AspectExtraction, embedder: Embedder | None = None,
                       min_count: int | None = None, max_examples: int = 3) -> OpinionAggregation:
    m: pd.DataFrame = extraction.mentions
    n_reviews = extraction.review_count
    if m.empty:
        return OpinionAggregation()
    embedder = embedder or get_embedder()
    min_count = min_count or max(3, math.ceil(0.03 * n_reviews))
    freq = m.groupby("aspect").size().to_dict()

    groups: dict[tuple[str, str], dict] = {}
    for (aspect, sentiment), g in m[m["sentiment"].isin(["positive", "negative"])].groupby(["aspect", "sentiment"]):
        if len(g) < min_count:
            continue
        g = g.assign(a=g["score"].abs()).sort_values("a", ascending=False)
        groups[(aspect, sentiment)] = {
            "aspect": aspect,
            "sentiment": sentiment,
            "count": int(len(g)),
            "share_of_aspect": round(len(g) / freq[aspect], 3),
            "share_of_reviews": round(len(g) / n_reviews * 100, 1),
            "themes": _themes(g["clause"].tolist(), g["review_id"].astype(int).tolist(), embedder),
            "examples": [{"review_id": int(r.review_id), "clause": r.clause, "review": r.review_raw}
                         for r in g.head(max_examples).itertuples()],
        }
    # keep only theme clusters that actually recur; if none do, the group's examples speak for it
    for gr in groups.values():
        gr["themes"] = [t for t in gr["themes"] if t["count"] >= 2]
        for t in gr["themes"]:
            t["label"] = t["label"][:1].upper() + t["label"][1:]

    strengths = sorted([g for g in groups.values() if g["sentiment"] == "positive"], key=lambda g: -g["count"])
    issues = sorted([g for g in groups.values() if g["sentiment"] == "negative"], key=lambda g: -g["count"])
    for g in strengths + issues:
        g["type"] = "strength" if g["sentiment"] == "positive" else "issue"

    s_asp = {g["aspect"]: g for g in strengths}
    i_asp = {g["aspect"]: g for g in issues}
    contested = []
    for a in s_asp.keys() & i_asp.keys():
        p, n = s_asp[a]["count"], i_asp[a]["count"]
        contested.append({"aspect": a, "positive": p, "negative": n,
                          "dominant": "positive" if p > n else "negative" if n > p else "split"})
    contested.sort(key=lambda c: -(c["positive"] + c["negative"]))
    for g in issues:
        g["contested"] = g["aspect"] in s_asp
    for g in strengths:
        g["contested"] = g["aspect"] in i_asp
    return OpinionAggregation(strengths=strengths, issues=issues, contested=contested,
                              min_count=min_count, embedder=embedder.name)
