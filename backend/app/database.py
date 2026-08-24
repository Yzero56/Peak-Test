from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema() -> None:
    """Alembic 없이 SQLite를 쓰므로, 이미 존재하는 테이블에 새로 추가된 컬럼을
    가볍게 채워넣는다(멱등 — 이미 있으면 아무것도 하지 않음). 새 DB는 create_all()이
    최신 모델 그대로 만들기 때문에 여기선 기존 DB 파일만 대상이 된다.
    """
    inspector = inspect(engine)
    if "devices" not in inspector.get_table_names():
        return
    existing_cols = {c["name"] for c in inspector.get_columns("devices")}
    with engine.begin() as conn:
        if "baseline_gas_resistance_ohm" not in existing_cols:
            conn.execute(text("ALTER TABLE devices ADD COLUMN baseline_gas_resistance_ohm FLOAT"))
        if "baseline_gas_set_at" not in existing_cols:
            conn.execute(text("ALTER TABLE devices ADD COLUMN baseline_gas_set_at DATETIME"))
