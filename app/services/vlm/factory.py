from app.core.config import settings
from app.services.vlm.base import VLMAdapter
from app.services.vlm.mock_adapter import MockVLMAdapter
from app.services.vlm.openai_adapter import OpenAIVLMAdapter


def get_vlm_adapter() -> VLMAdapter:
    if settings.vlm_provider == "mock":
        return MockVLMAdapter()
    if settings.vlm_provider in {"openai", "minimax"}:
        return OpenAIVLMAdapter()
    raise RuntimeError(f"Unsupported VLM_PROVIDER: {settings.vlm_provider}")
