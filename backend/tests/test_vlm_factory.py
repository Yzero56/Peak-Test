import pytest

from app.core.config import settings
from app.services.vlm.factory import get_vlm_adapter
from app.services.vlm.mock_adapter import MockVLMAdapter
from app.services.vlm.openai_adapter import OpenAIVLMAdapter


def test_mock_provider_returns_mock_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "vlm_provider", "mock")

    assert isinstance(get_vlm_adapter(), MockVLMAdapter)


def test_unknown_provider_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "vlm_provider", "unknown")

    with pytest.raises(RuntimeError, match="Unsupported VLM_PROVIDER"):
        get_vlm_adapter()


def test_minimax_provider_returns_openai_compatible_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "vlm_provider", "minimax")

    assert isinstance(get_vlm_adapter(), OpenAIVLMAdapter)
