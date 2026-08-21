import pytest

from voxforge.config import get_settings


@pytest.fixture(autouse=True)
def mock_voice_stack(monkeypatch):
    """Use mock providers and disable memory embeddings for pipeline-backed integration tests."""
    monkeypatch.setenv("STT_PROVIDER", "mock")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("TTS_PROVIDER", "mock")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("MEMORY_ENABLED", "false")
    monkeypatch.setenv("EVALUATION_HALLUCINATION_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
