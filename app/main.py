from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes.food_items import router as food_items_router
from app.api.routes.health import router as health_router
from app.api.routes.images import router as images_router
from app.api.routes.analysis_jobs import router as analysis_jobs_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.rules import router as rules_router
from app.api.routes.cooking import router as cooking_router
from app.api.routes.advertisements import router as advertisements_router
from app.api.routes.detections import router as detections_router
from app.api.routes.sensors import router as sensors_router
from app.api.routes.legacy import (
    recipe_router as legacy_recipe_router,
    router as legacy_router,
    scan_router as legacy_scan_router,
)
from app.api.routes.refrigerator import router as refrigerator_router
from app.core.config import settings

app = FastAPI(
    title="PEAK Smart Backend",
    version="0.1.0",
    description="Food recognition and expiry-date management API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    # 개발용 터널(Expo, Cloudflare, ngrok)은 재시작마다 랜덤 서브도메인을 새로 받으므로
    # 매번 CORS_ORIGINS를 수정하지 않도록 이 도메인 패턴들은 통째로 허용한다.
    allow_origin_regex=r"^https://[a-z0-9-]+\.(exp\.direct|trycloudflare\.com|ngrok-free\.(dev|app))$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(food_items_router, prefix=settings.api_v1_prefix)
app.include_router(images_router, prefix=settings.api_v1_prefix)
app.include_router(analysis_jobs_router, prefix=settings.api_v1_prefix)
app.include_router(dashboard_router, prefix=settings.api_v1_prefix)
app.include_router(rules_router, prefix=settings.api_v1_prefix)
app.include_router(cooking_router, prefix=settings.api_v1_prefix)
app.include_router(advertisements_router, prefix=settings.api_v1_prefix)
app.include_router(detections_router, prefix=settings.api_v1_prefix)
app.include_router(sensors_router, prefix=settings.api_v1_prefix)
app.include_router(legacy_router, prefix="/api")
app.include_router(legacy_scan_router, prefix="/api")
app.include_router(legacy_recipe_router, prefix="/api")
app.include_router(refrigerator_router, prefix=settings.api_v1_prefix)
app.mount("/dashboard", StaticFiles(directory="app/static", html=True), name="dashboard")
app.mount("/presentation", StaticFiles(directory="docs", html=True), name="presentation")
