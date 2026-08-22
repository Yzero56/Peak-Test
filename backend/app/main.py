from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.database import Base, engine
from app.routers import auth, dashboard, ingest

settings = get_settings()

Base.metadata.create_all(bind=engine)
settings.media_path.mkdir(parents=True, exist_ok=True)  # media 디렉토리 생성 보장

app = FastAPI(title="냉장고 지킴이 관리 백엔드")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(ingest.router)

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
