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


class ClimateOut(BaseModel):
    """앱 홈 화면에 보여줄 냉장고 온습도 — 단일 냉장고 가정이라 기기 구분 없이 하나만 내려준다."""

    temperatureC: float | None = None
    humidityPct: float | None = None


class RecipeIngredientOut(BaseModel):
    name: str
    amount: str
    essential: bool


class RecipeOut(BaseModel):
    id: str
    title: str
    time: str
    level: str
    kcal: int
    note: str
    uses: list[RecipeIngredientOut]
    steps: list[str]
