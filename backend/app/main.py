from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.database import Base, engine
from app.routers import app_api, auth, dashboard, ingest

settings = get_settings()

Base.metadata.create_all(bind=engine)
settings.media_path.mkdir(parents=True, exist_ok=True)  # media 디렉토리 생성 보장

app = FastAPI(title="냉장고 지킴이 관리 백엔드")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
# 모바일 앱이 터널 도메인(다른 origin)에서 /api/*를 호출하므로 CORS 허용.
# 관리자 대시보드(HTML)는 서버사이드 렌더링이라 이 설정의 영향을 받지 않음.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(ingest.router)
app.include_router(app_api.router)

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
