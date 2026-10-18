"""Generate a large, realistic-ish review CSV with KNOWN ground truth, for scale and accuracy tests.

    python data/generate_synthetic.py --reviews 5000 --out data/synthetic_reviews.csv

Writes the CSV plus <out>.truth.json (expected positive/negative/neutral mention counts per aspect).
Reviews mix 1-3 aspects with positive / negative / neutral phrasing, and include noise
(exact duplicates, empty rows, emoji/HTML/URLs, one-word reviews).
NOTE: opinion words are chosen from common vocabulary, so sentiment accuracy measured on this data is
optimistic compared with messy real-world reviews.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

POS = ["great", "excellent", "amazing", "fantastic", "superb", "wonderful", "awesome", "brilliant",
       "impressive", "outstanding", "lovely", "terrific"]
NEG = ["terrible", "awful", "poor", "horrible", "disappointing", "bad", "useless", "unreliable",
       "frustrating", "lousy", "dreadful", "pathetic"]
NEU = ["average", "okay", "standard", "acceptable", "typical", "ordinary", "as expected", "so-so"]
POS_T = ["The {a} is {w}.", "{A} is really {w}.", "I love the {a}, it is {w}.", "Honestly the {a} is {w}.",
         "{A} exceeded my expectations, truly {w}.", "The {a} turned out {w}."]
NEG_T = ["The {a} is {w}.", "{A} is really {w}.", "I am unhappy with the {a}, it is {w}.",
         "Honestly the {a} is {w}.", "{A} was a letdown, truly {w}.", "The {a} turned out {w}."]
NEU_T = ["The {a} is {w}.", "{A} is {w}, nothing special.", "I would call the {a} {w}.",
         "The {a} was {w} for me."]
FILLER = ["", "", "", " Bought it last month.", " Using it daily.", " Arrived on time.", " Would think twice.",
          " Gift for my brother.", " Second one I own."]

# product -> (name, aspect group -> (surface forms, P(pos), P(neg)); remainder is neutral, mention weights)
# Each surface form is (text written in the review, aspect key the pipeline is EXPECTED to report).
# Synonyms the pipeline merges share a key (mic/microphone, audio/sound); domain-dependent terms stay
# separate (fit vs comfort, build quality vs durability, speed vs performance).
def F(*items):
    out = []
    for it in items:
        text, _, key = it.partition("->")
        out.append((text, key or text))
    return out


PRODUCTS = {
    "S101": ("SonicPods Pro Wireless Earbuds", {
        "sound": (F("sound quality->sound", "sound", "audio->sound"), .80, .08),
        "battery": (F("battery life->battery", "battery"), .82, .06),
        "microphone": (F("microphone", "mic->microphone"), .08, .74),
        "comfort": (F("comfort", "fit"), .70, .16),
        "durability": (F("build quality->build", "durability"), .22, .45),
        "price": (F("price", "value for money->price"), .45, .25),
        "connectivity": (F("bluetooth connection->connectivity", "pairing->connectivity"), .60, .20),
        "design": (F("design"), .75, .05)},
     {"sound": .6, "battery": .45, "microphone": .4, "comfort": .35, "durability": .2, "price": .25,
      "connectivity": .15, "design": .15}),
    "L201": ("AeroBook 14 Laptop", {
        "screen": (F("screen", "display->screen"), .78, .08), "keyboard": (F("keyboard"), .55, .30),
        "performance": (F("performance", "speed"), .70, .12),
        "battery": (F("battery life->battery", "battery"), .30, .52),
        "price": (F("price"), .35, .40), "design": (F("design"), .72, .06),
        "speaker": (F("speakers->speaker"), .18, .55),
        "customer service": (F("customer service", "support->customer service"), .25, .50)},
     {"screen": .5, "keyboard": .35, "performance": .5, "battery": .45, "price": .3, "design": .2,
      "speaker": .15, "customer service": .12}),
    "P301": ("Lumina Smartphone X", {
        "camera": (F("camera", "photo quality->camera"), .85, .06),
        "battery": (F("battery life->battery", "battery"), .55, .30),
        "screen": (F("screen", "display->screen"), .80, .05), "performance": (F("performance"), .75, .10),
        "delivery": (F("delivery", "shipping->delivery"), .65, .22), "packaging": (F("packaging"), .60, .15),
        "price": (F("price"), .40, .35), "software": (F("software"), .35, .40)},
     {"camera": .55, "battery": .45, "screen": .35, "performance": .35, "delivery": .15, "packaging": .1,
      "price": .25, "software": .2}),
}


def make_review(rng, aspects, weights, truth):
    n = rng.choices([1, 2, 3], [.45, .38, .17])[0]
    names = list(aspects)
    chosen = []
    while len(chosen) < n:
        a = rng.choices(names, [weights[x] for x in names])[0]
        if a not in chosen:
            chosen.append(a)
    parts, tone_sum = [], 0
    for a in chosen:
        forms, p_pos, p_neg = aspects[a]
        r = rng.random()
        pol = "positive" if r < p_pos else "negative" if r < p_pos + p_neg else "neutral"
        surface, key = rng.choice(forms)
        truth[key][pol] += 1
        tone_sum += {"positive": 1, "negative": -1, "neutral": 0}[pol]
        if pol == "positive":
            t, w = rng.choice(POS_T), rng.choice(POS)
        elif pol == "negative":
            t, w = rng.choice(NEG_T), rng.choice(NEG)
        else:
            t, w = rng.choice(NEU_T), rng.choice(NEU)
        parts.append(t.format(a=surface, A=surface[0].upper() + surface[1:], w=w))
    text = " ".join(parts) + rng.choice(FILLER)
    rating = (5 if rng.random() < .6 else 4) if tone_sum > 0 else 3 if tone_sum == 0 else (2 if rng.random() < .5 else 1)
    return text.strip(), rating


def generate(n_reviews: int, seed: int = 42):
    rng = random.Random(seed)
    rows, truth = [], {pid: defaultdict(Counter) for pid in PRODUCTS}
    pids = list(PRODUCTS)
    for _ in range(n_reviews):
        pid = rng.choices(pids, [.4, .3, .3])[0]
        name, aspects, weights = PRODUCTS[pid]
        roll = rng.random()
        date = f"{rng.choice([2023, 2024, 2025])}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
        if roll < .01:                                              # empty review
            rows.append([pid, name, "", rng.randint(1, 5), date])
            continue
        if roll < .05:                                              # exact duplicate of an earlier review
            pool = [r for r in rows[-300:] if r[0] == pid and r[2] and not r[2].startswith("[")]
            if pool:
                src = rng.choice(pool)
                rows.append([pid, name, src[2], src[3], date])
                continue
        text, rating = make_review(rng, aspects, weights, truth[pid])
        if roll < .07:
            text += " \U0001F600\U0001F600 <br> visit http://spam.example.com"
        rows.append([pid, name, text, rating, date])
    return rows, {pid: {a: dict(c) for a, c in d.items()} for pid, d in truth.items()}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reviews", type=int, default=5000)
    ap.add_argument("--out", default="data/synthetic_reviews.csv")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    rows, truth = generate(a.reviews, a.seed)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["product_id", "product_name", "review", "rating", "review_date"])
        w.writerows(rows)
    out.with_suffix(".truth.json").write_text(json.dumps(truth, indent=1))
    print(f"wrote {len(rows)} reviews to {out} ({out.stat().st_size / 1024:.0f} KB) + ground truth")
