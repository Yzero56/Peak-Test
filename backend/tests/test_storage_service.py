from pathlib import Path

import pytest

from app.core.config import settings
from app.services.storage_service import StorageService


@pytest.mark.asyncio
async def test_local_storage_saves_image_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "local_storage_path", str(tmp_path))

    await StorageService().save("images/test.jpg", b"image-bytes")

    assert (tmp_path / "images" / "test.jpg").read_bytes() == b"image-bytes"
