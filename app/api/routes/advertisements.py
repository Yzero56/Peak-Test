from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.core.config import settings

router = APIRouter(prefix="/advertisements", tags=["advertisements"])

TEST_AD_PROMPT = (
    "A cinematic commercial set in a Minecraft-inspired voxel world. "
    "The scene opens inside a cozy modern smart kitchen built entirely from "
    "detailed voxel blocks. The kitchen looks playful and game-like, but the "
    "smart appliances feel futuristic and premium. A voxel character walks into "
    "the kitchen and places a container of food on the smart kitchen counter. "
    "The kitchen automatically detects the food using a small camera sensor. A "
    "futuristic holographic interface appears above the counter, displaying: "
    "Food detected; Freshness: Good; Expiration: D-3. The refrigerator door opens "
    "automatically. Inside, organized food containers are neatly arranged. Each "
    "container has a small glowing status indicator showing its freshness. The "
    "camera smoothly moves through the kitchen, showing the smart refrigerator, "
    "food containers, sensors, camera module, and a small digital dashboard. "
    "Suddenly, one food container starts glowing red. The holographic display "
    "shows: Warning: Expiration approaching. The voxel character looks surprised "
    "and moves the food container to the front of the refrigerator. End with a "
    "dramatic wide shot of the entire smart kitchen. The kitchen transforms into "
    "a futuristic Minecraft-style smart home. Final text: 당신의 주방이, 스스로 "
    "음식을 관리한다. SMART KITCHEN. High-end product commercial, cinematic "
    "lighting, smooth camera movement, dramatic close-ups, detailed voxel "
    "environment, polished Minecraft-inspired aesthetic, futuristic holographic "
    "UI, visually engaging, premium advertisement. Avoid logos or copyrighted "
    "characters; use an original voxel game aesthetic."
)


def _headers() -> dict[str, str]:
    if not settings.minimax_api_key:
        raise HTTPException(status_code=503, detail="MINIMAX_API_KEY is not configured")
    return {"Authorization": f"Bearer {settings.minimax_api_key}"}


async def _minimax_request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(
            base_url=settings.minimax_video_base_url.rstrip("/"), timeout=60
        ) as client:
            response = await client.request(method, path, headers=_headers(), **kwargs)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500]
        raise HTTPException(status_code=502, detail=f"MiniMax video API error: {detail}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="MiniMax video API is unreachable") from exc


@router.post("/test-video")
async def create_test_ad_video() -> dict[str, Any]:
    return await _minimax_request(
        "POST",
        "/v2/video_generation",
        json={
            "model": settings.minimax_video_model,
            "content": [{"type": "text", "text": TEST_AD_PROMPT}],
            "resolution": "768P",
            "duration": 15,
            "ratio": "9:16",
            "aigc_watermark": True,
        },
    )


@router.get("/test-video/{task_id}")
async def get_test_ad_video(task_id: str) -> dict[str, Any]:
    return await _minimax_request("GET", f"/v2/query/video_generation/{task_id}")


@router.get("/test-video/{task_id}/stream")
async def stream_test_ad_video(task_id: str) -> Response:
    result = await get_test_ad_video(task_id)
    task = result.get("task", {})
    video_url = task.get("content", {}).get("url")
    if task.get("status") != "succeeded" or not video_url:
        raise HTTPException(status_code=409, detail="Video is not ready")
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(video_url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Generated video download failed") from exc
    return Response(content=response.content, media_type="video/mp4")
