from pydantic import BaseModel, Field


class SensorIngest(BaseModel):
    door_open: bool | None = None
    temperature_c: float | None = None
    humidity_pct: float | None = None
    gas_resistance_ohm: float | None = Field(default=None, ge=0)


class DeviceCreate(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=1, max_length=120)
