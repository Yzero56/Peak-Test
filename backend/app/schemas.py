from pydantic import BaseModel, ConfigDict, Field


class SensorIngest(BaseModel):
    door_open: bool | None = None
    temperature_c: float | None = None
    humidity_pct: float | None = None
    gas_resistance_ohm: float | None = Field(default=None, ge=0)


class DeviceCreate(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=1, max_length=120)


class InventoryItemIn(BaseModel):
    """앱의 InventoryItem 타입과 동일한 필드명(camelCase)을 그대로 사용한다."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(min_length=1, max_length=120)
    category: str
    quantity: str
    expiresAt: str = Field(min_length=1, max_length=10)
    location: str


class InventoryItemPatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    quantity: str | None = None
    expiresAt: str | None = None


class InventoryItemOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: str
    category: str
    quantity: str
    expiresAt: str
    location: str


class ScanCandidateOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    quantity: str
    expiresAt: str
    category: str
    location: str
