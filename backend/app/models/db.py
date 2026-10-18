"""ORM tables (portable across SQLite and PostgreSQL: only generic column types are used)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Upload(Base):
    __tablename__ = "uploads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    validation: Mapped[dict] = mapped_column(JSON)      # ingestion report
    cleaning: Mapped[dict] = mapped_column(JSON)        # cleaning statistics


class Product(Base):
    __tablename__ = "products"
    product_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    product_name: Mapped[str] = mapped_column(String(512))
    upload_id: Mapped[int | None] = mapped_column(ForeignKey("uploads.id", ondelete="SET NULL"), nullable=True)
    raw_reviews: Mapped[int] = mapped_column(Integer, default=0)      # rows in the file for this product
    review_count: Mapped[int] = mapped_column(Integer, default=0)     # usable reviews after cleaning
    avg_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    date_min: Mapped[str | None] = mapped_column(String(10), nullable=True)
    date_max: Mapped[str | None] = mapped_column(String(10), nullable=True)
    sentiment: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # aggregated sentiment summary
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)        # backends used, contested aspects, notes
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id", ondelete="CASCADE"), index=True)
    text_clean: Mapped[str] = mapped_column(Text)
    text_raw: Mapped[str] = mapped_column(Text)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class Aspect(Base):
    __tablename__ = "aspects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id", ondelete="CASCADE"), index=True)
    aspect: Mapped[str] = mapped_column(String(128))
    frequency: Mapped[int] = mapped_column(Integer)
    mention_pct: Mapped[float] = mapped_column(Float)
    positive: Mapped[int] = mapped_column(Integer)
    neutral: Mapped[int] = mapped_column(Integer)
    negative: Mapped[int] = mapped_column(Integer)
    avg_score: Mapped[float] = mapped_column(Float)
    polarity: Mapped[str] = mapped_column(String(16))
    examples: Mapped[dict] = mapped_column(JSON)


class Insight(Base):
    """Aggregated recurring opinion (strength or issue)."""
    __tablename__ = "insights"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))                 # strength | issue
    aspect: Mapped[str] = mapped_column(String(128))
    sentiment: Mapped[str] = mapped_column(String(16))
    count: Mapped[int] = mapped_column(Integer)
    share_of_aspect: Mapped[float] = mapped_column(Float)
    share_of_reviews: Mapped[float] = mapped_column(Float)
    contested: Mapped[bool] = mapped_column(Boolean, default=False)
    themes: Mapped[list] = mapped_column(JSON)
    examples: Mapped[list] = mapped_column(JSON)


class Summary(Base):
    __tablename__ = "summaries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id", ondelete="CASCADE"), unique=True)
    mode: Mapped[str] = mapped_column(String(16))                 # live | mock
    model: Mapped[str] = mapped_column(String(128))
    warnings: Mapped[list] = mapped_column(JSON)
    content: Mapped[dict] = mapped_column(JSON)                   # LLMSummary
    payload: Mapped[dict] = mapped_column(JSON)                   # structured findings sent to the LLM
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Validation(Base):
    __tablename__ = "validations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id", ondelete="CASCADE"), unique=True)
    verdict: Mapped[str] = mapped_column(String(32))
    score: Mapped[int] = mapped_column(Integer)
    headline: Mapped[str] = mapped_column(Text)
    report: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")   # queued|running|done|failed
    stage: Mapped[str] = mapped_column(String(64), default="Queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


Index("ix_runs_product_created", AnalysisRun.product_id, AnalysisRun.created_at)
