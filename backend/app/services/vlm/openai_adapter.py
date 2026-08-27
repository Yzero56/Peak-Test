import base64
import json
import re

from openai import AsyncOpenAI

from app.core.config import settings
from app.schemas.analysis import ExtractedFoodInfo

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)
_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)

# 일부 VLM(예: MiniMax-M3)은 response_format=json_schema를 강제해도 필드 이름을
# 스키마와 다르게 준다 — 흔히 쓰는 대체 키를 우리 스키마 키로 맞춰준다.
_KEY_ALIASES = {
    "expiration_date": "labeled_expires_at",
    "manufactured_date": "manufactured_at",
}


def _extract_json_object(content: str) -> dict:
    """느슨한 JSON 추출: <think> 블록/마크다운 코드펜스로 감싸져 오는 응답도 파싱한다."""
    stripped = _THINK_BLOCK.sub("", content).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    fence_match = _JSON_FENCE.search(stripped)
    if fence_match:
        return json.loads(fence_match.group(1))
    brace_start, brace_end = stripped.find("{"), stripped.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        return json.loads(stripped[brace_start : brace_end + 1])
    raise ValueError(f"VLM response has no parseable JSON object: {content[:200]!r}")


def _normalize_extracted_fields(data: dict) -> dict:
    for alt_key, real_key in _KEY_ALIASES.items():
        if alt_key in data and real_key not in data:
            data[real_key] = data.pop(alt_key)
    data.setdefault("confidence", 0.5)  # 모델이 누락하면 검토 필요로 처리
    return data

NULLABLE_STRING = {"anyOf": [{"type": "string"}, {"type": "null"}]}
NULLABLE_DATE = {"anyOf": [{"type": "string"}, {"type": "null"}]}

EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "food_name": NULLABLE_STRING,
        "category": NULLABLE_STRING,
        "manufactured_date_text": NULLABLE_STRING,
        "expiration_date_text": NULLABLE_STRING,
        "manufactured_at": NULLABLE_DATE,
        "labeled_expires_at": NULLABLE_DATE,
        "storage_type": {
            "anyOf": [
                {"type": "string", "enum": ["room", "refrigerator", "freezer"]},
                {"type": "null"},
            ],
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "notes": NULLABLE_STRING,
    },
    "required": [
        "food_name",
        "category",
        "manufactured_date_text",
        "expiration_date_text",
        "manufactured_at",
        "labeled_expires_at",
        "storage_type",
        "confidence",
        "notes",
    ],
}

SYSTEM_PROMPT = """You extract food and expiry information from a kitchen food image.
Respond with ONLY a single raw JSON object — no <think> blocks, no markdown code
fences, no commentary before or after it.
Use exactly these keys: food_name, category, manufactured_date_text,
expiration_date_text, manufactured_at, labeled_expires_at, storage_type,
confidence, notes. Do not use any other key names.
Use only information visible in the image. Never guess a date.
If a value is unreadable or absent, return null.
Normalize dates to YYYY-MM-DD only when the printed date is unambiguous.
Keep the original printed date in manufactured_date_text or expiration_date_text.
confidence is a number from 0 to 1 for how certain you are overall.
"""


class OpenAIVLMAdapter:
    def __init__(self) -> None:
        api_key = (
            settings.minimax_api_key
            if settings.vlm_provider == "minimax"
            else settings.vlm_api_key
        )
        if not api_key:
            raise RuntimeError("VLM_API_KEY or MINIMAX_API_KEY is required for the configured VLM provider")
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=settings.vlm_base_url,
        )
        self.model = settings.vlm_model or "gpt-4o-mini"

    async def extract_food_info(self, image: bytes, content_type: str) -> ExtractedFoodInfo:
        encoded_image = base64.b64encode(image).decode("ascii")
        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "food_expiry_extraction",
                    "strict": True,
                    "schema": EXTRACTION_SCHEMA,
                },
            },
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract the food name, storage type, manufacture date, and expiry date.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{content_type};base64,{encoded_image}",
                            },
                        },
                    ],
                },
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("VLM returned an empty response")
        data = _normalize_extracted_fields(_extract_json_object(content))
        return ExtractedFoodInfo.model_validate(data)
