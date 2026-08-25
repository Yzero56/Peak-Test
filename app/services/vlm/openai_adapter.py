import base64
import json

from openai import AsyncOpenAI

from app.core.config import settings
from app.schemas.analysis import ExtractedFoodInfo

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
Return only JSON matching the supplied schema.
Use only information visible in the image. Never guess a date.
If a value is unreadable or absent, return null.
Normalize dates to YYYY-MM-DD only when the printed date is unambiguous.
Keep the original printed date in manufactured_date_text or expiration_date_text.
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
        return ExtractedFoodInfo.model_validate(json.loads(content))
