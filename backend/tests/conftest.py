"""Shared fixtures: keep tests offline and fast (VADER + TF-IDF + mock LLM) and use a temp database."""
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def offline_settings(monkeypatch):
    from app.utils import config
    monkeypatch.setattr(config, "settings", replace(config.settings, sentiment_backend="vader",
                                                    embedding_backend="tfidf", use_mock_llm=True,
                                                    llm_api_key=""))
