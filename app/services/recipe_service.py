import re
import time
from typing import Any

import httpx
from fastapi import HTTPException

from app.core.config import settings

_API_BASE = "http://openapi.foodsafetykorea.go.kr/api"
_SERVICE_ID = "COOKRCP01"
_CACHE_TTL_SECONDS = 60 * 60  # HJ 앱의 fridge-store.tsx 주석 기준: "백엔드도 1시간 캐시"

_cache: dict[str, Any] = {"data": None, "fetched_at": 0.0}

# 식품안전나라 API에는 없는, 직접 등록한 레시피. 매 응답에 항상 합쳐서 내려준다.
_LOCAL_RECIPES: list[dict[str, Any]] = [
    {
        "id": "local-spam-fried-rice",
        "title": "간단 볶음밥",
        "time": "15분",
        "level": "쉬움",
        "kcal": 480,
        "note": "당근과 양파를 잘게 썰어 볶고 계란과 밥을 더해 간단하게 완성한다.",
        "uses": [
            {"name": "밥", "amount": "1공기(210g)", "essential": True},
            {"name": "양파", "amount": "1/4개", "essential": True},
            {"name": "대파", "amount": "1/2대", "essential": True},
            {"name": "당근", "amount": "1/6개", "essential": True},
            {"name": "계란", "amount": "1개", "essential": True},
        ],
        "steps": [
            "1. 양파와 당근은 사방 1cm로 작게 썰고, 대파는 송송 썬다.",
            "2. 팬에 식용유를 두르고 중간 불에서 양파, 당근, 대파 흰 부분을 넣어 양파가 투명해질 때까지 볶는다.",
            "3. 밥을 넣고 주걱으로 누르듯 펴가며 알알이 풀어지도록 3~4분 볶는다.",
            "4. 계란을 풀어 팬 한쪽에 붓고 스크램블하듯 익힌 뒤 나머지 재료와 섞는다.",
            "5. 대파 푸른 부분을 넣고 소금으로 간을 맞춘 뒤 한 번 더 섞어 불을 끈다.",
        ],
    },
]


def _merge_local_recipes(recipes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    local_ids = {r["id"] for r in _LOCAL_RECIPES}
    return _LOCAL_RECIPES + [r for r in recipes if r["id"] not in local_ids]

_BRACKET_RE = re.compile(r"\[[^\]]*\]")
_LABEL_PREFIX_RE = re.compile(r"^[·•]?\s*[^\d,:()]{1,20}:\s*")
_NAME_AMOUNT_RE = re.compile(r"^(?P<name>[^\d]+?)\s*(?P<amount>\d.*)$")
_TRAILING_ANCHOR_RE = re.compile(r"(?<=\.)[a-t]$")


def _parse_ingredients(raw: str) -> list[dict[str, Any]]:
    """RCP_PARTS_DTLS는 자유 텍스트라 완벽한 파싱은 불가능하다 — 숫자가 없는
    줄(예: 소제목 '고명')은 재료가 아니라고 보고 건너뛴다."""
    text = _BRACKET_RE.sub("", raw or "")
    segments = [seg.strip() for line in text.split("\n") for seg in line.split(",")]
    ingredients: list[dict[str, Any]] = []
    for segment in segments:
        segment = _LABEL_PREFIX_RE.sub("", segment).strip()
        if not segment or not any(ch.isdigit() for ch in segment):
            continue
        match = _NAME_AMOUNT_RE.match(segment)
        name = match.group("name").strip() if match else segment
        amount = match.group("amount").strip() if match else ""
        if not name:
            continue
        ingredients.append({"name": name, "amount": amount, "essential": True})
    return ingredients


def _parse_steps(row: dict[str, Any]) -> list[str]:
    steps: list[str] = []
    for i in range(1, 21):
        text = (row.get(f"MANUAL{i:02d}") or "").strip()
        if not text:
            continue
        steps.append(_TRAILING_ANCHOR_RE.sub("", text))
    return steps


def _estimate_level(step_count: int) -> str:
    """API에 난이도 필드가 없어 조리 단계 수로 근사한다."""
    if step_count <= 4:
        return "쉬움"
    if step_count <= 8:
        return "보통"
    return "어려움"


def _to_recipe_def(row: dict[str, Any]) -> dict[str, Any] | None:
    name = (row.get("RCP_NM") or "").strip()
    seq = (row.get("RCP_SEQ") or "").strip()
    if not name or not seq:
        return None
    steps = _parse_steps(row)
    try:
        kcal = int(float(row.get("INFO_ENG") or 0))
    except ValueError:
        kcal = 0
    note = (row.get("RCP_NA_TIP") or row.get("HASH_TAG") or "").strip()
    return {
        "id": seq,
        "title": name,
        "time": "-",  # API에 조리 시간 필드가 없음
        "level": _estimate_level(len(steps)),
        "kcal": kcal,
        "note": note,
        "uses": _parse_ingredients(row.get("RCP_PARTS_DTLS") or ""),
        "steps": steps,
    }


async def _fetch_from_api() -> list[dict[str, Any]]:
    if not settings.foodsafety_api_key:
        raise HTTPException(status_code=503, detail="FOODSAFETY_API_KEY is not configured")
    end_idx = max(1, min(settings.foodsafety_recipe_count, 1000))
    url = f"{_API_BASE}/{settings.foodsafety_api_key}/{_SERVICE_ID}/json/1/{end_idx}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Recipe API is unreachable") from exc

    body = payload.get(_SERVICE_ID) or {}
    result = body.get("RESULT") or {}
    code = result.get("CODE", "")
    if code and not code.startswith("INFO-"):
        raise HTTPException(status_code=502, detail=f"Recipe API error: {result.get('MSG', code)}")

    rows = body.get("row") or []
    return [recipe for row in rows if (recipe := _to_recipe_def(row)) is not None]


async def get_recipes() -> list[dict[str, Any]]:
    now = time.monotonic()
    if _cache["data"] is not None and now - _cache["fetched_at"] < _CACHE_TTL_SECONDS:
        return _cache["data"]
    recipes = _merge_local_recipes(await _fetch_from_api())
    _cache["data"] = recipes
    _cache["fetched_at"] = now
    return recipes
