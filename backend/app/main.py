from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import live_scan, services
from app.config import get_settings
from app.database import Base, SessionLocal, engine, ensure_schema
from app.models import Device
from app.routers import app_api, dashboard, ingest, presentation

settings = get_settings()

Base.metadata.create_all(bind=engine)
ensure_schema()  # 기존 DB 파일에 새로 추가된 컬럼(가스 baseline 등) 채워넣기
settings.media_path.mkdir(parents=True, exist_ok=True)  # media 디렉토리 생성 보장

app = FastAPI(title="냉장고 지킴이 관리 백엔드")
# 모바일 앱이 터널 도메인(다른 origin)에서 /api/*를 호출하므로 CORS 허용.
# 관리자 대시보드(HTML)는 서버사이드 렌더링이라 이 설정의 영향을 받지 않음.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router)
app.include_router(ingest.router)
app.include_router(app_api.router)
app.include_router(presentation.router)

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
def resume_live_scans() -> None:
    """서버 재시작(--reload 포함) 시 live_scan의 인메모리 상태는 초기화되지만,
    문이 이미 열려있는 기기는 다음 door_open 전환 전까지 재시작 신호가 오지 않는다.
    그래서 시작 시점에 문이 열려있는 상태인 기기를 찾아 자동 스캔을 다시 붙여준다."""
    db = SessionLocal()
    try:
        for device in db.query(Device).all():
            reading = services.latest_reading(db, device.id)
            if reading and reading.door_open:
                live_scan.start(device.id)
    finally:
        db.close()
