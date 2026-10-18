"""Central configuration loaded from environment variables (.env)."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    llm_provider: str = os.getenv("LLM_PROVIDER", "anthropic")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "")
    use_mock_llm: bool = os.getenv("USE_MOCK_LLM", "true").lower() == "true"
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./reviews.db")
    sentiment_backend: str = os.getenv("SENTIMENT_BACKEND", "auto")  # auto | transformer | vader
    sentiment_model: str = os.getenv("SENTIMENT_MODEL", "cardiffnlp/twitter-roberta-base-sentiment-latest")
    sentiment_batch_size: int = int(os.getenv("SENTIMENT_BATCH_SIZE", "32"))
    embedding_backend: str = os.getenv("EMBEDDING_BACKEND", "auto")  # auto | sbert | tfidf
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "")            # optional (OpenAI-compatible servers)
    llm_timeout: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
    llm_max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "2"))
    sample_data_path: str = os.getenv(
        "SAMPLE_DATA_PATH", str(Path(__file__).resolve().parents[3] / "data" / "sample_reviews.csv"))
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "25"))
    cors_origins: list[str] = field(
        default_factory=lambda: _split(os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"))
    )


settings = Settings()
