import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.food_items import to_response
from app.core.database import get_db
from app.models.analysis import AnalysisJob
from app.schemas.analysis import AnalysisJobAccepted, AnalysisJobCreate, AnalysisJobResponse
from app.schemas.food import FoodItemResponse
from app.services.analysis_service import (
    apply_analysis_job,
    create_analysis_job,
    get_analysis_job,
    process_analysis_job,
)

router = APIRouter(prefix="/analysis-jobs", tags=["analysis-jobs"])


@router.post("", response_model=AnalysisJobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    data: AnalysisJobCreate,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
) -> AnalysisJobAccepted:
    try:
        job = await create_analysis_job(session, data)
    except ValueError as error:
        if str(error) in {"image_not_found", "food_item_not_found"}:
            raise HTTPException(status_code=404, detail=str(error)) from error
        raise
    background_tasks.add_task(process_analysis_job, job.id)
    return AnalysisJobAccepted(job_id=job.id, status="queued")


@router.get("/{job_id}", response_model=AnalysisJobResponse)
async def get_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> AnalysisJobResponse:
    job = await get_analysis_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found")
    return AnalysisJobResponse.model_validate(job)


@router.post("/{job_id}/apply", response_model=FoodItemResponse)
async def apply_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> FoodItemResponse:
    job = await get_analysis_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found")
    try:
        item = await apply_analysis_job(session, job)
    except ValueError as error:
        code = str(error)
        if code == "analysis_already_applied":
            raise HTTPException(status_code=409, detail=code) from error
        raise HTTPException(status_code=409, detail=code) from error
    return to_response(item)
