"""Phase 5: data-driven aspect extraction with aspect-level sentiment.

Pipeline (per product):
 1. split every review into clauses                       (nlp/clauses.py)
 2. POS-tag clauses with spaCy; collect noun sequences ("battery life", "ear cushion")
 3. normalise candidates: lemma, strip generic suffixes ("battery life" -> "battery"),
    apply a small synonym map ("mic" -> "microphone")
 4. DISCOVER aspects = candidates mentioned in enough distinct reviews (no fixed aspect list)
 5. link every clause to the aspects it mentions
 6. score each clause with the sentiment model, then aggregate per (review, aspect)
 7. per aspect: frequency, positive / neutral / negative counts, example evidence

Only the *normalisation* helpers (generic suffixes, synonyms, stop nouns) are hand-written;
which aspects exist is decided by the data.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import NamedTuple

import pandas as pd

from app.nlp.clauses import split_clauses
from app.nlp.sentiment import SentimentAnalyzer, get_analyzer
from app.utils.errors import DataValidationError

# words that end a noun phrase but are not the aspect itself: "battery LIFE", "sound QUALITY"
GENERIC_SUFFIXES = {"quality", "life", "performance", "backup", "level", "experience", "capability",
                    "feature", "issue", "problem", "part", "aspect", "setting"}
# nouns that never make useful aspects
STOP_NOUNS = {"thing", "product", "item", "one", "time", "day", "way", "lot", "bit", "kind", "sort",
              "year", "month", "week", "hour", "minute", "purchase", "order", "buy", "use", "user",
              "review", "star", "money", "people", "person", "guy", "everyone", "anyone", "something",
              "anything", "nothing", "everything", "others", "case", "point", "end", "start", "least",
              "couple", "while", "moment", "fact", "reason", "family", "friend", "friends", "husband",
              "wife", "son", "daughter", "gift", "amazon", "store", "brand", "company", "model",
              "version", "deal", "job", "work", "phone", "headphone", "headphones", "device",
              "colleague", "colleagues", "commute", "call", "gym", "monday", "tuesday", "wednesday",
              "thursday", "friday", "saturday", "sunday", "unit", "pair", "side", "hand", "head",
              "song", "music", "game", "app", "series", "price range", "range",
              # generic evaluative / relational nouns ("exceeded my expectations", "gift for my brother")
              "expectation", "disappointment", "letdown", "improvement", "recommendation", "opinion",
              "brother", "sister", "mom", "mother", "dad", "father", "kid", "child", "girlfriend",
              "boyfriend", "partner", "niece", "nephew", "wife", "husband"}
SYNONYMS = {"audio": "sound", "photo": "camera", "value": "price", "charge": "battery", "voice": "microphone", "mic": "microphone", "mike": "microphone", "cam": "camera", "display": "screen",
            "anc": "noise cancellation", "cancellation": "noise cancellation",
            "cancelling": "noise cancellation", "canceling": "noise cancellation",
            "support": "customer service", "service": "customer service",
            "bluetooth": "connectivity", "connection": "connectivity", "pairing": "connectivity",
            "shipping": "delivery", "package": "packaging", "box": "packaging",
            "look": "design", "cost": "price", "charging": "charging", "charger": "charging"}

# adjectives that name an aspect implicitly: "very comfortable" -> comfort
ADJ_ASPECTS = {"comfortable": "comfort", "comfy": "comfort", "uncomfortable": "comfort",
               "durable": "durability", "sturdy": "durability", "flimsy": "durability",
               "fragile": "durability", "expensive": "price", "cheap": "price", "overpriced": "price",
               "affordable": "price", "lightweight": "weight", "heavy": "weight",
               "loud": "volume", "fast": "speed", "slow": "speed", "laggy": "performance",
               "stylish": "design", "sleek": "design"}

_NLP = None


def _load_spacy():
    global _NLP
    if _NLP is None:
        try:
            import spacy
            _NLP = spacy.load("en_core_web_sm", disable=["ner", "parser"])
        except Exception as exc:
            raise DataValidationError(
                "nlp_model_missing",
                "The spaCy English model is not installed. Run: python -m spacy download en_core_web_sm",
                status_code=503, details={"reason": str(exc)[:200]})
    return _NLP


@dataclass
class AspectExtraction:
    aspects: list[dict] = field(default_factory=list)   # sorted by frequency
    mentions: pd.DataFrame = field(default_factory=pd.DataFrame)  # one row per (review, aspect)
    clauses: pd.DataFrame = field(default_factory=pd.DataFrame)   # one row per clause (+aspects, sentiment)
    review_count: int = 0
    min_support: int = 0


def _norm_phrase(tokens: list[str]) -> str:
    """Lemma tokens of a noun sequence -> normalised aspect key."""
    toks = [t for t in tokens if t]
    while len(toks) > 1 and toks[-1] in GENERIC_SUFFIXES:
        toks = toks[:-1]
    phrase = " ".join(toks)
    if phrase in SYNONYMS:
        return SYNONYMS[phrase]
    if len(toks) > 1 and toks[-1] in SYNONYMS:       # the head noun decides: "bluetooth connection"
        return SYNONYMS[toks[-1]]
    return phrase


class _Tok(NamedTuple):
    """The few token attributes the noun-sequence logic needs. Keeping these instead of whole spaCy Docs
    cuts memory ~4x on large review sets (a Doc costs ~20 KB; this costs well under 1 KB)."""
    i: int
    text: str
    lower_: str
    lemma_: str
    pos_: str
    is_alpha: bool


def _compact(doc) -> list[_Tok]:
    return [_Tok(t.i, t.text, t.lower_, t.lemma_, t.pos_, t.is_alpha) for t in doc]


def _noun_sequences(doc, known_nouns: frozenset | set = frozenset()) -> list[tuple[list[str], list[str] | None]]:
    """Noun sequences of a clause as (lemmas, surface text). Adjective-derived aspects
    ("comfortable" -> comfort) have surface None: the adjective IS the opinion, so it is never masked.

    `known_nouns` = lemmas the tagger labelled NOUN/PROPN somewhere in the same review set. It lets us
    recover words the small model mis-tags as ADJ inside noun compounds ("sound quality")."""
    seqs: list[tuple[list[str], list[str] | None]] = []
    cur: list = []
    gerunds: set[int] = set()        # token indexes recovered from a VERB tag: keep the surface form, not the verb lemma

    def lemma(t) -> str:
        return t.lower_ if t.i in gerunds else t.lemma_.lower()

    def flush():
        if cur:
            # words to mask later: the aspect words only. Generic suffixes ("problem", "issue", "quality")
            # stay visible because they carry sentiment ("durability problems").
            words = [t.text for t in cur if lemma(t) not in GENERIC_SUFFIXES]
            seqs.append(([lemma(t) for t in cur], words or None))

    for tok in doc:
        # tagger fix: a clause-initial word that a small model mislabels ADJ ("mic is terrible")
        # but that is directly followed by a verb/copula is the subject noun.
        nxt = doc[tok.i + 1] if tok.i + 1 < len(doc) else None
        at_subject = tok.i == 0 or doc[tok.i - 1].pos_ in ("DET", "PRON")
        misfire = (tok.pos_ == "ADJ" and nxt is not None and nxt.pos_ in ("AUX", "VERB")
                   and tok.lower_ not in ADJ_ASPECTS and at_subject)
        # a clause-initial gerund used as the subject is mis-tagged VERB: "Pairing is terrible", "Charging is slow"
        gerund = (tok.pos_ == "VERB" and tok.lower_.endswith("ing") and at_subject
                  and nxt is not None and nxt.pos_ == "AUX")
        if gerund:
            gerunds.add(tok.i)
        misfire = misfire or gerund
        # noun compound whose first word is mis-tagged ADJ: "sound quality", "I love the camera quality".
        # Only when the next word is a generic suffix AND this word is a noun elsewhere in the data, so
        # opinion adjectives that are never nouns ("decent quality", "premium quality") are left alone.
        misfire = misfire or (tok.pos_ == "ADJ" and nxt is not None and nxt.pos_ == "NOUN"
                              and nxt.lemma_.lower() in GENERIC_SUFFIXES and tok.lower_ not in ADJ_ASPECTS
                              and tok.lemma_.lower() in known_nouns)
        if (tok.pos_ in ("NOUN", "PROPN") or misfire) and tok.is_alpha and len(tok.lemma_) > 2:
            cur.append(tok)
        else:
            flush()
            cur = []
            if tok.pos_ == "ADJ" and tok.lower_ in ADJ_ASPECTS:
                seqs.append(([ADJ_ASPECTS[tok.lower_]], None))
    flush()
    return seqs


def _mask_terms(clause: str, surfaces: list[str]) -> str:
    """Replace aspect words with 'it' so a lexicon-based scorer is not swayed by the aspect word itself
    (VADER rates 'support' as positive, so 'Support was a letdown, truly bad' would otherwise score mixed)."""
    out = clause
    for surf in sorted(set(surfaces), key=len, reverse=True):
        out = re.sub(rf"\b{re.escape(surf)}\b", "it", out, flags=re.I)
    return out


def _candidates(seq: list[str]) -> list[str]:
    """Candidate keys for one noun sequence, most specific first."""
    keys = [_norm_phrase(seq)]
    if len(seq) > 1:                         # fall back to the head noun: "ear cushion" -> "cushion"
        head, first = _norm_phrase([seq[-1]]), _norm_phrase([seq[0]])
        keys.append(head if head not in STOP_NOUNS else first)
    return [k for k in dict.fromkeys(keys) if k and k not in STOP_NOUNS and len(k) > 2]


def extract_aspects(df: pd.DataFrame, analyzer: SentimentAnalyzer | None = None, top_k: int = 15,
                    min_support: int | None = None, max_examples: int = 3) -> AspectExtraction:
    """df must be a cleaned frame for ONE product (columns: review_clean, review_raw)."""
    n_reviews = len(df)
    if n_reviews == 0:
        return AspectExtraction()
    analyzer = analyzer or get_analyzer()
    nlp = _load_spacy()

    # 1. clauses
    rows = []
    for rid, text in zip(df.index, df["review_clean"]):
        for c in split_clauses(text):
            rows.append((rid, c))
    cl = pd.DataFrame(rows, columns=["review_id", "clause"])

    # 2-3. noun sequences -> candidate keys per clause
    cand_per_clause: list[list[tuple[list[str], list[str] | None]]] = []   # clause -> sequences -> (keys, words)
    tokens = [_compact(d) for d in nlp.pipe([c[:1].upper() + c[1:] for c in cl["clause"]], batch_size=256)]
    known_nouns = {t.lemma_.lower() for toks in tokens for t in toks if t.pos_ in ("NOUN", "PROPN")}
    for toks in tokens:
        cand_per_clause.append([(_candidates(lem), surf) for lem, surf in _noun_sequences(toks, known_nouns)])
    del tokens

    # 4. discovery: document frequency of the PRIMARY candidate of each sequence
    df_counter: Counter = Counter()
    seen: dict[int, set] = defaultdict(set)
    for rid, seqs in zip(cl["review_id"], cand_per_clause):
        for keys, _surf in seqs:
            if keys:
                seen[rid].add(keys[0])
                for k in keys[1:]:                  # sub-parts count too, at lower priority
                    seen[rid].add(k)
    for keys in seen.values():
        df_counter.update(keys)
    support = min_support or max(3, math.ceil(0.03 * n_reviews))
    vocab = {k for k, c in df_counter.items() if c >= support}

    # 5. link clauses -> aspects (most specific candidate present in vocab wins per sequence)
    clause_aspects: list[list[str]] = []
    clause_surfaces: list[list[str]] = []
    for seqs in cand_per_clause:
        found, surfaces = [], []
        for keys, surf in seqs:
            hit = next((k for k in keys if k in vocab), None)
            if hit:
                found.append(hit)
                if surf:
                    surfaces.extend(surf)
        clause_aspects.append(list(dict.fromkeys(found)))
        clause_surfaces.append(surfaces)
    cl["aspects"] = clause_aspects

    # 6. clause sentiment (only clauses that mention an aspect need scoring)
    need = cl["aspects"].map(len) > 0
    texts = [(_mask_terms(c, sf) if getattr(analyzer, "lexicon_based", False) else c)
             for c, sf, n in zip(cl["clause"], clause_surfaces, need) if n]
    preds = analyzer.predict(texts) if need.any() else []
    cl["sentiment"], cl["score"] = None, 0.0
    cl.loc[need, "sentiment"] = [p.label for p in preds]
    cl.loc[need, "score"] = [p.score for p in preds]

    # aggregate per (review, aspect): mean clause score -> label; keep strongest clause as evidence
    ex = cl[need].explode("aspects").rename(columns={"aspects": "aspect"})
    if ex.empty:
        return AspectExtraction(clauses=cl, review_count=n_reviews, min_support=support)
    ex["abs_score"] = ex["score"].abs()
    best = ex.sort_values("abs_score", ascending=False).drop_duplicates(["review_id", "aspect"])
    agg = ex.groupby(["review_id", "aspect"]).agg(score=("score", "mean")).reset_index()

    # per-review label: majority of that review's clause labels about the aspect (tie of pos/neg -> neutral)
    def label_from(group_labels: pd.Series) -> str:
        counts = group_labels.value_counts()
        if counts.get("positive", 0) and counts.get("negative", 0) and counts["positive"] == counts["negative"]:
            return "neutral"        # genuinely mixed inside one review about one aspect
        return counts.idxmax()

    labels = ex.groupby(["review_id", "aspect"])["sentiment"].apply(label_from).reset_index(name="sentiment")
    mentions = agg.merge(labels, on=["review_id", "aspect"]).merge(
        best[["review_id", "aspect", "clause"]], on=["review_id", "aspect"])
    mentions["review_raw"] = mentions["review_id"].map(df["review_raw"]) if "review_raw" in df else ""

    # 7. per-aspect summary
    aspects = []
    for aspect, g in mentions.groupby("aspect"):
        counts = g["sentiment"].value_counts()
        entry = {
            "aspect": aspect,
            "frequency": int(len(g)),
            "mention_pct": round(len(g) / n_reviews * 100, 1),
            "positive": int(counts.get("positive", 0)),
            "neutral": int(counts.get("neutral", 0)),
            "negative": int(counts.get("negative", 0)),
            "avg_score": round(float(g["score"].mean()), 3),
            "examples": {},
        }
        pos, neg = entry["positive"], entry["negative"]
        entry["polarity"] = ("positive" if pos > 2 * neg else "negative" if neg > 2 * pos else "mixed")
        for lab in ("positive", "negative", "neutral"):
            sub = g[g["sentiment"] == lab].copy()
            sub["a"] = sub["score"].abs()
            sub = sub.sort_values("a", ascending=lab != "neutral")   # neutral: closest to 0 first
            entry["examples"][lab] = [{"review_id": int(r.review_id), "clause": r.clause,
                                       "review": r.review_raw} for r in sub.head(max_examples).itertuples()]
        aspects.append(entry)
    aspects.sort(key=lambda a: a["frequency"], reverse=True)
    keep = {a["aspect"] for a in aspects[:top_k]}
    aspects = aspects[:top_k]
    mentions = mentions[mentions["aspect"].isin(keep)].reset_index(drop=True)
    return AspectExtraction(aspects=aspects, mentions=mentions, clauses=cl,
                            review_count=n_reviews, min_support=support)
