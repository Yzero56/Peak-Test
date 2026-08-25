import uuid
import logging
from datetime import datetime, timezone

from openai import AuthenticationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.analysis import AnalysisJob, AnalysisJobStatus
from app.models.food import FoodImage, FoodItem, FoodItemStatus, ShelfLifeRule, StorageType
from app.schemas.analysis import AnalysisJobCreate, ExtractedFoodInfo
from app.services.storage_service import storage_service
from app.services.expiry_service import calculate_expiry
from app.services.vlm.factory import get_vlm_adapter

logger = logging.getLogger(__name__)


async def get_analysis_job(session: AsyncSession, job_id: uuid.UUID) -> AnalysisJob | None:
    return await session.scalar(
        select(AnalysisJob)
        .options(selectinload(AnalysisJob.image))
        .where(AnalysisJob.id == job_id)
    )


async def create_analysis_job(session: AsyncSession, data: AnalysisJobCreate) -> AnalysisJob:
    image = await session.get(FoodImage, data.image_id)
    if image is None:
        raise ValueError("image_not_found")
    if data.food_item_id is not None:
        food_item = await session.get(FoodItem, data.food_item_id)
        if food_item is None:
            raise ValueError("food_item_not_found")
        image.food_item_id = food_item.id

    job = AnalysisJob(
        image_id=data.image_id,
        model=settings.vlm_model or settings.vlm_provider,
        status=AnalysisJobStatus.QUEUED,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def process_analysis_job(job_id: uuid.UUID) -> None:
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        job = await get_analysis_job(session, job_id)
        if job is None or job.status != AnalysisJobStatus.QUEUED:
            return

        job.status = AnalysisJobStatus.PROCESSING
        job.started_at = datetime.now(timezone.utc)
        await session.commit()

        try:
            adapter = get_vlm_adapter()
            image = await storage_service.read(job.image.object_key)
            result = await adapter.extract_food_info(image, job.image.content_type)
            job.result = result.model_dump(mode="json")
            job.needs_review = result.confidence < 0.75 or result.labeled_expires_at is None
            job.status = AnalysisJobStatus.SUCCEEDED
        except AuthenticationError:
            logger.exception("VLM authentication failed for job %s", job_id)
            job.status = AnalysisJobStatus.FAILED
            job.error_code = "vlm_auth_error"
        except Exception:
            logger.exception("VLM analysis failed for job %s", job_id)
            job.status = AnalysisJobStatus.FAILED
            job.error_code = "vlm_error"
        finally:
            job.finished_at = datetime.now(timezone.utc)
            await session.commit()


async def apply_analysis_job(session: AsyncSession, job: AnalysisJob) -> FoodItem:
    if job.status != AnalysisJobStatus.SUCCEEDED or job.result is None:
        raise ValueError("analysis_not_ready")
    if job.applied_food_item_id is not None:
        raise ValueError("analysis_already_applied")

    result = ExtractedFoodInfo.model_validate(job.result)
    storage_type = result.storage_type or StorageType.REFRIGERATOR
    rule = None
    if result.category is not None:
        rule = await session.scalar(
            select(ShelfLifeRule).where(
                ShelfLifeRule.category == result.category,
                ShelfLifeRule.storage_type == storage_type,
                ShelfLifeRule.active.is_(True),
            )
        )
    expires_at, date_source = calculate_expiry(
        result.labeled_expires_at,
        result.manufactured_at,
        result.category,
        storage_type,
        rule,
    )
    item = FoodItem(
        display_name=result.food_name or "분석된 식품",
        category=result.category,
        storage_type=storage_type,
        manufactured_at=result.manufactured_at,
        expires_at=expires_at,
        date_source=date_source,
        confidence=result.confidence,
        status=FoodItemStatus.ACTIVE,
    )
    session.add(item)
    await session.flush()
    job.applied_food_item_id = item.id
    job.applied_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(item)
    return item
