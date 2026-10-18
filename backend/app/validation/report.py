from __future__ import annotations

from dataclasses import asdict, dataclass, field

EVIDENCE_BACKED, NEEDS_REVIEW = "Evidence-backed", "Needs Review"


@dataclass
class ClaimResult:
    section: str          # pros | cons | recurring_issues | overall_summary | important_aspects
    text: str
    aspect: str | None
    status: str           # supported | weak | unverified | unsupported | contradicted
    message: str
    evidence: dict = field(default_factory=dict)
    examples: list = field(default_factory=list)


@dataclass
class CheckResult:
    id: str
    name: str
    status: str           # pass | warn | fail
    message: str
    details: list = field(default_factory=list)


@dataclass
class ValidationReport:
    verdict: str
    score: int
    headline: str
    checks: list[CheckResult]
    claims: list[ClaimResult]

    def to_dict(self) -> dict:
        return asdict(self)
