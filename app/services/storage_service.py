import asyncio
from pathlib import Path

from app.core.config import settings


class StorageService:
    async def save(self, object_key: str, content: bytes) -> None:
        if settings.storage_backend != "local":
            raise NotImplementedError("Only local storage is configured")

        target = Path(settings.local_storage_path) / object_key
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_bytes, content)

    async def read(self, object_key: str) -> bytes:
        if settings.storage_backend != "local":
            raise NotImplementedError("Only local storage is configured")

        target = Path(settings.local_storage_path) / object_key
        return await asyncio.to_thread(target.read_bytes)


storage_service = StorageService()
