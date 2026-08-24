from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    # SQLite에는 타임존 타입이 없어 tz-aware 값이 읽기 시 naive로 돌아오므로,
    # 저장/비교를 모두 naive UTC로 통일한다.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    token_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 하트비트 요청의 소스 IP — 대시보드가 기기의 라이브 스트림(/stream, /capture)에 접근할 때 사용
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    # 추세 기반 가스 이상 감지용 baseline — 재료를 새로 넣은 시점(재고 추가)의 가스 저항값을
    # 저장해두고, 이후 값이 여기서 일정 %만큼 떨어지면 "이상 신호"로 본다(절대 임계값 대신).
    baseline_gas_resistance_ohm: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_gas_set_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    readings: Mapped[list["SensorReading"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    door_events: Mapped[list["DoorEvent"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    captures: Mapped[list["Capture"]] = relationship(back_populates="device", cascade="all, delete-orphan")


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    door_open: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    gas_resistance_ohm: Mapped[float | None] = mapped_column(Float, nullable=True)

    device: Mapped[Device] = relationship(back_populates="readings")


class DoorEvent(Base):
    __tablename__ = "door_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    is_open: Mapped[bool] = mapped_column(Boolean)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    device: Mapped[Device] = relationship(back_populates="door_events")


class Capture(Base):
    __tablename__ = "captures"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    image_path: Mapped[str] = mapped_column(String(255))

    device: Mapped[Device] = relationship(back_populates="captures")
    objects: Mapped[list["DetectedObject"]] = relationship(back_populates="capture", cascade="all, delete-orphan")


class DetectedObject(Base):
    __tablename__ = "detected_objects"

    id: Mapped[int] = mapped_column(primary_key=True)
    capture_id: Mapped[int] = mapped_column(ForeignKey("captures.id"), index=True)
    label: Mapped[str] = mapped_column(String(80))
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    capture: Mapped[Capture] = relationship(back_populates="objects")


class InventoryItem(Base):
    """앱(모바일)이 공유하는 재고 항목. 단일 냉장고를 가정해 기기에 종속되지 않는다."""

    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[str] = mapped_column(String(40))
    expires_at: Mapped[str] = mapped_column(String(10))  # "YYYY-MM-DD" — 프론트와 동일 포맷 그대로 저장
    location: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
