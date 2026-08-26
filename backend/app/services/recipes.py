"""식품안전나라 Open API(COOKRCP01, 조리식품 레시피 DB) 연동.

HJ 브랜치(4번 파트)의 `backend/app/recipes.py`를 그대로 포팅한 것 — 앱(mobile-app)의
`GET /api/recipes` 계약을 유지하기 위해 kang 백엔드(legacy 라우터)에서 재사용한다.

키가 없거나 요청이 실패하면 빈 리스트를 반환한다 — 호출부(legacy 라우터)가 이걸 보고
앱의 목업 레시피로 폴백한다. 조리식품 DB는 자주 바뀌지 않으므로 결과를 한동안
메모리에 캐시해서 매 요청마다 외부 API를 두드리지 않는다.
"""

import json
import re
import time
import urllib.error
import urllib.request

from app.core.config import get_settings

API_BASE = "http://openapi.foodsafetykorea.go.kr/api"
SERVICE_ID = "COOKRCP01"
FETCH_COUNT = 30  # 앱에 내려줄 레시피 개수
CACHE_TTL_SECONDS = 60 * 60  # 1시간

_cache: dict = {"fetched_at": 0.0, "recipes": []}

# "돼지고기 300g, 양파 1/2개, 다진마늘 1큰술" 같은 자유 텍스트를 항목별로 쪼갠 뒤
# 이름과 수량을 분리한다 — API가 구조화된 재료 목록을 주지 않아서 최선을 다한 추정치다.
_INGREDIENT_SPLIT_PATTERN = re.compile(r"[,\n]")
_INGREDIENT_NAME_PATTERN = re.compile(r"^([^\d]+?)\s*([\d].*)?$")
_MANUAL_NUMBERING_PATTERN = re.compile(r"^\d+\.\s*")


def _parse_ingredients(raw: str | None) -> list[dict]:
    if not raw:
        return []
    ingredients = []
    for segment in _INGREDIENT_SPLIT_PATTERN.split(raw):
        segment = segment.strip().strip("•·- ")
        if not segment:
            continue
        match = _INGREDIENT_NAME_PATTERN.match(segment)
        name = (match.group(1) if match else segment).strip()
        amount = (match.group(2) or "").strip() if match else ""
        if not name:
            continue
        # essential 여부는 자유 텍스트만으로는 신뢰성 있게 구분할 수 없어 항상 False로 둔다
        # (레시피 조리 시 재고를 잘못 자동 소진시키지 않기 위한 보수적인 선택).
        ingredients.append({"name": name, "amount": amount or "적당량", "essential": False})
    return ingredients


def _parse_steps(row: dict) -> list[str]:
    steps = []
    for i in range(1, 21):
        text = (row.get(f"MANUAL{i:02d}") or "").strip()
        if text:
            steps.append(_MANUAL_NUMBERING_PATTERN.sub("", text))
    return steps


def _row_to_recipe(row: dict) -> dict | None:
    title = (row.get("RCP_NM") or "").strip()
    if not title:
        return None
    uses = _parse_ingredients(row.get("RCP_PARTS_DTLS"))
    steps = _parse_steps(row)
    if not uses or not steps:
        return None
    try:
        kcal = int(float((row.get("INFO_ENG") or "0").strip()))
    except ValueError:
        kcal = 0
    return {
        "id": f"fsk-{row.get('RCP_SEQ', title)}",
        "title": title,
        "time": "20분",  # API가 조리시간을 제공하지 않아 고정값 사용
        "level": "보통",  # API가 난이도를 제공하지 않아 고정값 사용
        "kcal": kcal,
        "note": "식품안전나라 조리식품 레시피 DB 제공",
        "uses": uses,
        "steps": steps,
    }


def fetch_recipes() -> list[dict]:
    """캐시된 레시피 목록을 반환한다. 만료됐으면 API를 새로 호출해서 갱신한다.

    키가 없으면 빈 리스트, 요청이 실패하면 마지막으로 성공했던 캐시(있다면)를 반환한다.
    """
    settings = get_settings()
    api_key = getattr(settings, "food_safety_api_key", "") or ""
    if not api_key:
        return []

    now = time.time()
    if _cache["recipes"] and now - _cache["fetched_at"] < CACHE_TTL_SECONDS:
        return _cache["recipes"]

    url = f"{API_BASE}/{api_key}/{SERVICE_ID}/json/1/{FETCH_COUNT}"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return _cache["recipes"]

    rows = data.get(SERVICE_ID, {}).get("row", [])
    recipes = [r for r in (_row_to_recipe(row) for row in rows) if r is not None]
    if recipes:
        _cache["recipes"] = recipes
        _cache["fetched_at"] = now
    return _cache["recipes"]
