"""Plain dataclasses describing ingestion output."""
from dataclasses import dataclass, field, asdict
import pandas as pd


@dataclass
class ValidationReport:
    filename: str
    total_rows: int = 0
    empty_reviews: int = 0
    valid_reviews: int = 0
    missing_ratings: int = 0
    invalid_ratings: int = 0
    missing_dates: int = 0
    invalid_dates: int = 0
    products_found: int = 0
    columns_detected: dict = field(default_factory=dict)   # original name -> canonical name
    columns_missing_optional: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IngestionResult:
    df: pd.DataFrame
    report: ValidationReport


@dataclass
class CleaningStats:
    total_reviews: int = 0           # rows in uploaded file
    empty_removed: int = 0           # blank reviews
    noise_removed: int = 0           # nothing left after cleaning (only emoji/urls/symbols)
    exact_duplicates_removed: int = 0
    near_duplicates_removed: int = 0
    duplicates_removed: int = 0      # exact + near
    valid_reviews: int = 0           # reviews that survive cleaning
    duplicate_ratio: float = 0.0     # duplicates_removed / non-empty reviews
    average_rating: float | None = None
    rated_reviews: int = 0
    date_min: str | None = None
    date_max: str | None = None
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CleaningResult:
    df: pd.DataFrame                 # cleaned rows only
    stats: CleaningStats
