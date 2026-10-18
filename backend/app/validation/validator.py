"""Phase 8: evidence / consistency validation of the LLM summary.

The summary is checked against the processed statistics, not against the LLM itself:

  1. sentiment      - does the stated overall sentiment match the computed one?
  2. claims         - is every pro / con / issue / aspect statement supported by aspect counts?
  3. contradictions - does the prose say something the counts contradict ("love the mic" vs 7 neg / 1 pos)?
  4. numbers        - are the quoted percentages / counts real?
  5. omissions      - were major recurring issues left out?

Verdict: "Evidence-backed" if no check fails and the score >= 75, else "Needs Review".
Rule-based on purpose: transparent, deterministic, and explainable on the dashboard.
"""
from __future__ import annotations

import re

from app.llm.schemas import LLMSummary
from app.nlp.clauses import split_clauses
from app.services.pipeline import Findings
from app.validation.lexicon import claim_direction
from app.validation.matching import AspectMatcher
from app.validation.report import (EVIDENCE_BACKED, NEEDS_REVIEW, CheckResult, ClaimResult,
                                   ValidationReport)

WEIGHTS = {"supported": 1.0, "weak": 0.5, "unverified": 0.5, "unsupported": 0.0, "contradicted": 0.0,
           "pass": 1.0, "warn": 0.5, "fail": 0.0}
RANK = {"supported": 4, "weak": 3, "unverified": 2, "unsupported": 1, "contradicted": 0}
PASS_SCORE = 75


# ------------------------------------------------------------------ evidence base
class Evidence:
    def __init__(self, f: Findings):
        self.total = f.extraction.review_count
        self.sent = f.sentiment
        self.stats = f.stats
        self.min_count = f.opinions.min_count or max(3, -(-self.total * 3 // 100))
        self.aspects = {a["aspect"]: a for a in f.extraction.aspects}
        self.issues = f.opinions.issues
        self.strengths = f.opinions.strengths
        self.matcher = AspectMatcher(list(self.aspects))

    def examples(self, aspect: str, direction: str) -> list[str]:
        a = self.aspects.get(aspect)
        return [e["clause"] for e in (a or {}).get("examples", {}).get(direction, [])[:2]]

    def counts(self, aspect: str) -> dict:
        a = self.aspects[aspect]
        return {"aspect": aspect, "mentions": a["frequency"], "positive": a["positive"],
                "neutral": a["neutral"], "negative": a["negative"]}


def assess(direction: str, a: dict, min_count: int, hedged: bool = False) -> tuple[str, str]:
    """Is a claim of `direction` about aspect stats `a` supported?"""
    pos, neg = a["positive"], a["negative"]
    if direction == "positive":
        if pos >= 2 and pos >= 2 * neg:
            return ("supported", "") if pos >= min_count else ("weak", "positive but only a few mentions")
        if pos > neg and pos >= 2:
            return ("supported", "") if hedged else ("weak", f"opinions are mixed ({pos} positive, {neg} negative)")
        if neg >= pos and neg >= 1:
            if hedged and pos >= 2:
                return "weak", f"only {pos} positive vs {neg} negative mentions"
            return "contradicted", f"customers mostly complain: {neg} negative vs {pos} positive mentions"
        return "unsupported", "too few positive mentions in the reviews"
    # negative claim
    if neg >= 2 and neg >= 2 * pos:
        return ("supported", "") if neg >= min_count else ("weak", "negative but only a few mentions")
    if neg > pos and neg >= 2:
        return ("supported", "") if hedged else ("weak", f"opinions are mixed ({pos} positive, {neg} negative)")
    if neg == 0:
        return "contradicted", f"no negative mentions found ({pos} positive)"
    if neg == 1:
        return "unsupported", f"only 1 negative mention vs {pos} positive"
    if hedged:
        return "weak", f"{neg} negative vs {pos} positive mentions"
    return "unsupported", f"customers mostly like it: {pos} positive vs {neg} negative"


# ------------------------------------------------------------------ 1. sentiment
_STRONG = {"overwhelmingly", "extremely", "very", "highly", "universally", "unanimously", "entirely"}
_SENT_WORD = re.compile(r"\b(?:(overwhelmingly|extremely|very|highly|universally|unanimously|entirely|mostly|generally|"
                        r"largely|mainly|broadly|predominantly|somewhat|slightly|fairly|quite)\s+)?"
                        r"(positive|negative|favou?rable|unfavou?rable|mixed|divided|polarized)\b", re.I)
_PCT_CONTEXT = re.compile(r"\d[\d.,]*\s?%[^.;:\n]*?\b(?:positive|negative|neutral)\b", re.I)
COMPUTED = {"Positive": ("positive", True), "Mostly Positive": ("positive", False), "Mixed": ("mixed", False),
            "Mostly Negative": ("negative", False), "Negative": ("negative", True)}


def check_sentiment(s: LLMSummary, ev: Evidence) -> CheckResult:
    computed = ev.sent["overall"]
    pol, strong_ok = COMPUTED.get(computed, ("mixed", False))
    text = _PCT_CONTEXT.sub("PCT", f"{s.overall_summary}\n{s.sentiment_explanation}")
    claims = []
    for m in _SENT_WORD.finditer(text):
        q, w = (m.group(1) or "").lower(), m.group(2).lower()
        cls = "positive" if w in ("positive", "favorable", "favourable") else \
              "negative" if w in ("negative", "unfavorable", "unfavourable") else "mixed"
        claims.append((cls, q in _STRONG))
    if not claims:
        return CheckResult("sentiment", "Overall sentiment matches data", "warn",
                           f"The summary never states the overall sentiment (data: {computed}).")
    problems, notes = [], []
    for cls, strong in claims:
        if {cls, pol} == {"positive", "negative"}:
            problems.append(f"Summary says '{cls}' but the reviews are {computed.lower()} "
                            f"({ev.sent['percentages']['positive']}% positive, {ev.sent['percentages']['negative']}% negative).")
        elif cls != pol:
            notes.append(f"Summary says '{cls}' but data says {computed}.")
        elif strong and not strong_ok:
            notes.append(f"Wording is stronger than the data supports ({computed}).")
    if problems:
        return CheckResult("sentiment", "Overall sentiment matches data", "fail", problems[0], problems)
    if notes:
        return CheckResult("sentiment", "Overall sentiment matches data", "warn", notes[0], notes)
    return CheckResult("sentiment", "Overall sentiment matches data", "pass",
                       f"Stated sentiment agrees with the computed result: {computed}.")


# ------------------------------------------------------------------ 2. claims
def _judge_line(section: str, text: str, direction: str, ev: Evidence) -> ClaimResult:
    aspects = ev.matcher.match(text)
    if not aspects:
        return ClaimResult(section, text, None, "unverified",
                           "No analysed aspect matches this statement, so it cannot be checked against the data.")
    best = None
    for asp in aspects:
        status, why = assess(direction, ev.aspects[asp], ev.min_count, hedged=claim_direction(text)[1])
        # A "recurring issue" means the complaint REPEATS (enough negative mentions), not that most customers
        # dislike the aspect, so recurrence is the test for that list. Cons and prose keep the stricter
        # "negative outweighs positive" test above.
        if (section == "recurring_issues" and direction == "negative" and status in ("weak", "unsupported")
                and ev.aspects[asp]["negative"] >= ev.min_count):
            status, why = "supported", ""
        cand = (RANK[status], asp, status, why)
        if best is None or cand[0] > best[0]:
            best = cand
    _, asp, status, why = best
    c = ev.counts(asp)
    ok = f"{c['positive']} positive / {c['negative']} negative of {c['mentions']} mentions"
    msg = {"supported": f"Supported: {ok}.", "weak": f"Partly supported: {why}.",
           "unsupported": f"Not supported: {why}.", "contradicted": f"Contradicted by the data: {why}."}[status]
    opp = "negative" if direction == "positive" else "positive"
    return ClaimResult(section, text, asp, status, msg, c,
                       ev.examples(asp, direction if status in ("supported", "weak") else opp))


def check_claims(s: LLMSummary, ev: Evidence) -> list[ClaimResult]:
    out: list[ClaimResult] = []
    for line in s.pros:
        out.append(_judge_line("pros", line, "positive", ev))
    for line in s.cons:
        out.append(_judge_line("cons", line, "negative", ev))
    for line in s.recurring_issues:
        out.append(_judge_line("recurring_issues", line, "negative", ev))

    # prose: overall summary + aspect notes, judged clause by clause
    prose = [("overall_summary", u) for sent in re.split(r"(?<=[.!?])\s+", s.overall_summary) if sent
             for u in split_clauses(sent)]
    prose += [("important_aspects", f"{a.aspect}: {a.note}") for a in s.important_aspects]
    for section, unit in prose:
        direction, hedged = claim_direction(unit)
        aspects = ev.matcher.match(unit)
        if not direction or not aspects:
            continue                                  # no aspect-level opinion stated
        for asp in aspects:
            status, why = assess(direction, ev.aspects[asp], ev.min_count, hedged)
            if status == "supported":
                continue                              # only surface prose problems + weak spots
            c = ev.counts(asp)
            msg = {"weak": f"Partly supported: {why}.", "unsupported": f"Not supported: {why}.",
                   "contradicted": f"Contradicted by the data: {why}."}[status]
            opp = "negative" if direction == "positive" else "positive"
            out.append(ClaimResult(section, unit, asp, status, msg, c, ev.examples(asp, opp)))
    return out


# ------------------------------------------------------------------ 4. numbers
_PCT = re.compile(r"(\d+(?:\.\d+)?)\s?%")
_COUNT = re.compile(r"\b(\d[\d,]*)\s+(?:(?:positive|negative|neutral|total|unique|analy[sz]ed)\s+)*"
                    r"(?:reviews?|mentions?|complaints?|customers?|reviewers?|users?|people|ratings?)\b", re.I)
_RATING = re.compile(r"(\d(?:\.\d+)?)\s*(?:/\s*5|stars?|out of 5)", re.I)


def check_numbers(s: LLMSummary, ev: Evidence) -> CheckResult:
    text = " \n".join([s.overall_summary, s.sentiment_explanation, *s.pros, *s.cons, *s.recurring_issues,
                       *[f"{a.aspect} {a.note}" for a in s.important_aspects]])
    pcts = set(ev.sent["percentages"].values())
    counts = {ev.total, *ev.sent["counts"].values(), ev.stats.get("total_reviews", ev.total)}
    for a in ev.aspects.values():
        counts |= {a["frequency"], a["positive"], a["neutral"], a["negative"]}
        f = a["frequency"] or 1
        pcts |= {a["mention_pct"], *(round(a[k] / f * 100, 1) for k in ("positive", "neutral", "negative"))}
    for g in ev.issues + ev.strengths:
        counts.add(g["count"])
        pcts |= {g["share_of_aspect"] * 100, g["share_of_reviews"]}
    bad = []
    for m in _PCT.finditer(text):
        v = float(m.group(1))
        if not any(abs(v - p) <= 1.0 for p in pcts):
            bad.append(f"{m.group(0)} does not match any computed percentage")
    for m in _COUNT.finditer(text):
        v = int(m.group(1).replace(",", ""))
        if v not in counts:
            bad.append(f"'{m.group(0)}' does not match any computed count")
    avg = ev.stats.get("average_rating")
    for m in _RATING.finditer(text):
        if avg is None or abs(float(m.group(1)) - avg) > 0.06:
            bad.append(f"rating '{m.group(0)}' does not match the average rating ({avg})")
    if bad:
        return CheckResult("numbers", "Quoted figures are real", "warn" if len(bad) < 2 else "fail",
                           f"{len(bad)} figure(s) in the summary are not backed by the data.", bad[:5])
    return CheckResult("numbers", "Quoted figures are real", "pass", "All quoted figures match the computed statistics.")


# ------------------------------------------------------------------ 5. omissions
def check_omissions(s: LLMSummary, ev: Evidence) -> CheckResult:
    # An issue counts as "covered" only if the summary presents it as a problem:
    # listed under cons / recurring issues, or described negatively in the prose.
    # (Praising the microphone does not cover a microphone complaint.)
    covered = set(ev.matcher.match(" ".join([*s.cons, *s.recurring_issues])))
    prose = [u for sent in re.split(r"(?<=[.!?])\s+", s.overall_summary) if sent for u in split_clauses(sent)]
    prose += [f"{a.aspect}: {a.note}" for a in s.important_aspects]
    for unit in prose:
        if claim_direction(unit)[0] == "negative":
            covered |= set(ev.matcher.match(unit))
    major_min = max(ev.min_count, -(-ev.total * 5 // 100))
    major = [g for g in ev.issues if g["count"] >= major_min and g["share_of_aspect"] >= 0.5]
    minor = [g for g in ev.issues if g not in major]
    missing = [g for g in major if g["aspect"] not in covered]
    if missing:
        names = ", ".join(f"{g['aspect']} ({g['count']} negative mentions)" for g in missing)
        return CheckResult("omissions", "Major recurring issues are mentioned", "fail",
                           f"The summary ignores a major recurring issue: {names}.",
                           [f"{g['aspect']}: {g['count']} negative mentions, {g['share_of_reviews']}% of reviews"
                            for g in missing])
    notes = [f"Minor recurring issue not mentioned: {g['aspect']} ({g['count']})"
             for g in minor if g["aspect"] not in covered]
    if notes:
        return CheckResult("omissions", "Major recurring issues are mentioned", "pass",
                           "All major issues are covered (some minor ones are not).", notes[:4])
    return CheckResult("omissions", "Major recurring issues are mentioned", "pass",
                       "All recurring issues found in the data are covered." if ev.issues
                       else "No major recurring issues exist in the data.")


# ------------------------------------------------------------------ entry point
def validate_summary(summary: LLMSummary, findings: Findings) -> ValidationReport:
    ev = Evidence(findings)
    claims = check_claims(summary, ev)
    contradicted = [c for c in claims if c.status == "contradicted"]
    unsupported = [c for c in claims if c.status == "unsupported"]

    checks = [check_sentiment(summary, ev)]
    n_pro = [c for c in claims if c.section == "pros"]
    n_con = [c for c in claims if c.section in ("cons", "recurring_issues")]
    for cid, name, subset in (("pros", "Pros are backed by positive evidence", n_pro),
                              ("cons", "Cons and issues are backed by negative evidence", n_con)):
        bad = [c for c in subset if c.status in ("contradicted", "unsupported")]
        weak = [c for c in subset if c.status in ("weak", "unverified")]
        st = "fail" if any(c.status == "contradicted" for c in subset) else "warn" if bad or weak else "pass"
        msg = (f"{len(bad)} unsupported/contradicted, {len(weak)} weak/unverified of {len(subset)}." if st != "pass"
               else (f"All {len(subset)} statements are supported." if subset else "Nothing to check."))
        checks.append(CheckResult(cid, name, st, msg, [f"{c.text} -> {c.message}" for c in bad + weak][:6]))
    prose_bad = [c for c in claims if c.section in ("overall_summary", "important_aspects")
                 and c.status in ("contradicted", "unsupported")]
    st = "fail" if any(c.status == "contradicted" for c in prose_bad) else "warn" if prose_bad else "pass"
    checks.append(CheckResult("prose", "Summary text does not contradict the data", st,
                              "No contradictions found in the summary text." if st == "pass"
                              else f"{len(prose_bad)} statement(s) in the summary text conflict with the data.",
                              [f"'{c.text}' -> {c.message}" for c in prose_bad][:6]))
    checks.append(check_numbers(summary, ev))
    checks.append(check_omissions(summary, ev))

    items = [WEIGHTS[c.status] for c in claims if c.section in ("pros", "cons", "recurring_issues")]
    items += [WEIGHTS[c.status] for c in claims if c.section in ("overall_summary", "important_aspects")]
    items += [WEIGHTS[k.status] for k in checks if k.id in ("sentiment", "numbers", "omissions")]
    score = round(100 * sum(items) / len(items)) if items else 100
    failed = [k for k in checks if k.status == "fail"]
    verdict = NEEDS_REVIEW if failed or score < PASS_SCORE else EVIDENCE_BACKED
    if verdict == EVIDENCE_BACKED:
        headline = "The summary is consistent with the analysed review data."
    elif failed:
        headline = failed[0].message
    else:
        headline = f"Several statements are only weakly supported (score {score}/100)."
    if ev.total < 20:
        headline += f" Note: only {ev.total} reviews were analysed."
    return ValidationReport(verdict, score, headline, checks, claims)
