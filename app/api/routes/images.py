import hashlib
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.food import FoodImage
from app.schemas.image import FoodImageResponse
from app.services.storage_service import storage_service

router = APIRouter(prefix="/food-images", tags=["food-images"])

ALLOWED_CONTENT_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


@router.post("", response_model=FoodImageResponse, status_code=status.HTTP_201_CREATED)
async def upload_food_image(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
) -> FoodImageResponse:
    extension = ALLOWED_CONTENT_TYPES.get(file.content_type or "")
    if extension is None:
        raise HTTPException(status_code=415, detail="Only JPEG, PNG, and WEBP images are supported")

    content = await file.read(settings.max_image_size_bytes + 1)
    if len(content) > settings.max_image_size_bytes:
        raise HTTPException(status_code=413, detail="Image must be 10 MB or smaller")

    image_id = uuid.uuid4()
    object_key = f"images/{image_id}{extension}"
    await storage_service.save(object_key, content)

    image = FoodImage(
        id=image_id,
        object_key=object_key,
        content_type=file.content_type,
        sha256=hashlib.sha256(content).hexdigest(),
    )
    session.add(image)
    await session.commit()
    await session.refresh(image)
    return image
