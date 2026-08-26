"""demo_scenario.py — 실제 시연 대본 그대로 전체 파이프라인이 동작하는지 확인한다.

    [냉장고] 1. 식재료 OUT -> 2. (동시에) 용기인식 -> 3. 백엔드 등록 -> 4. 대시보드 확인
    [주방]   1. 식재료 용기 촬영 -> 2. 실제 음식 만들기
    [냉장고] 1. 만든 음식 IN     -> 2. 용기인식     -> 3. 백엔드 등록 -> 4. 대시보드 확인

이 스크립트는 YJ/Wa/보드가 보낼 이벤트를 그대로 흉내내서 실제로 떠 있는 백엔드 +
bridge/detection_bridge.py에 던지고, 매 단계마다 대시보드(GET /api/v1/dashboard/summary)를
조회해서 실제로 반영됐는지 확인한다 — 즉 카메라·모델 자체를 테스트하는 게 아니라
"인식 결과가 나온 뒤 백엔드/대시보드까지 제대로 이어지는지"를 검증하는 것.
bridge가 먼저(별도 터미널 또는 dev/run_all.sh로) 떠 있어야 한다.

⚠ 냉장고 OUT은 그 물건이 미리 "IN"되어 등록돼 있어야만 성공한다(백엔드 설계상
당연한 제약 — 없는 걸 뺄 수는 없으므로). 그래서 이 스크립트는 0단계로 먼저
재고를 하나 미리 심어둔다(실제 시연에서는 "어제 미리 넣어둔 재료"에 해당).

실행 (bridge가 이미 떠 있어야 함):
    python dev/demo_scenario.py --backend-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def _req(method: str, url: str, body: dict | None = None, files: dict | None = None) -> tuple[int, dict]:
    if files:
        boundary = uuid.uuid4().hex
        parts = []
        for field, (filename, content, content_type) in files.items():
            parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n".encode()
                + content
                + b"\r\n"
            )
        data = b"".join(p if isinstance(p, bytes) else p.encode() for p in parts) + f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    else:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def step(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def show_dashboard(backend: str) -> dict:
    status, body = _req("GET", f"{backend}/api/v1/dashboard/summary")
    print(f"[대시보드] GET /api/v1/dashboard/summary -> {status}")
    for item in body.get("items", []):
        print(f"    - {item['display_name']:<12} status={item['status']:<10} container_id={item.get('container_id')}")
    return body


def wait_for_food_item(backend: str, container_id: str, status_filter: str, timeout: float = 40.0) -> bool:
    """bridge가 매칭해서 재고에 반영할 때까지 기다린다(폴링 간격 1초, window 25초 기본)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _, body = _req("GET", f"{backend}/api/v1/food-items?status={status_filter}")
        if any(i.get("container_id") == container_id for i in body):
            return True
        time.sleep(1.5)
    return False


def send_detection(backend: str, device_id: str, **payload) -> None:
    status, _ = _req("POST", f"{backend}/api/v1/detections", {"device_id": device_id, **payload})
    print(f"  POST /api/v1/detections {payload} -> {status}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("실행")[0])
    ap.add_argument("--backend-url", default="http://localhost:8000")
    ap.add_argument("--device-id", default="board-a-door-container")
    ap.add_argument("--out-item", default="당근", help="OUT 시나리오에서 쓸 식재료 이름(=container_id)")
    ap.add_argument("--in-item", default="item1", help="IN 시나리오에서 쓸 완성 음식 이름(=container_id)")
    ap.add_argument("--photo", type=Path, default=None,
                     help="주방 단계에서 올릴 사진(없으면 board-a mock 목업 이미지 사용)")
    args = ap.parse_args()
    backend = args.backend_url.rstrip("/")

    step("0단계 (사전 준비) — 어제 미리 넣어둔 재료 시뮬레이션")
    status, body = _req("POST", f"{backend}/api/v1/food-items", {
        "display_name": args.out_item, "container_id": args.out_item,
        "category": "vegetable", "quantity": 1, "storage_type": "refrigerator",
    })
    print(f"  POST /api/v1/food-items ({args.out_item} 미리 등록) -> {status}")
    if status >= 300:
        print("  (이미 있으면 무시하고 계속 진행)")
    show_dashboard(backend)

    step(f"[냉장고] 1~3단계 — '{args.out_item}' OUT")
    print("1. 식재료 OUT + 2. (동시에) 용기인식 -> YJ/Wa가 각자 보냈을 이벤트를 흉내냄:")
    send_detection(backend, args.device_id, motion_direction="out",
                    detections=[{"label": "out-pair", "confidence": 0.8}])
    send_detection(backend, args.device_id,
                    detections=[{"label": args.out_item, "confidence": 0.9, "container_id": args.out_item}])
    print("3. bridge가 매칭해서 백엔드에 등록하길 기다리는 중 (최대 40초)...")
    ok = wait_for_food_item(backend, args.out_item, status_filter="consumed")
    print(f"  -> {'✅ consumed로 반영됨' if ok else '❌ 반영 안 됨 (bridge가 떠있는지 확인)'}")
    step("4. [냉장고] 대시보드 확인")
    show_dashboard(backend)

    step("[주방] 1단계 — 식재료 용기 촬영 (VLM 분석 흐름)")
    photo_path = args.photo or (Path(__file__).resolve().parents[1]
                                 / "firmware/board-a-door-container/mock_placeholder.jpg")
    content_type = mimetypes.guess_type(str(photo_path))[0] or "image/jpeg"
    status, body = _req("POST", f"{backend}/api/v1/food-images", None,
                         files={"file": (photo_path.name, photo_path.read_bytes(), content_type)})
    print(f"  POST /api/v1/food-images -> {status}")
    image_id = body.get("id")
    if image_id:
        status, body = _req("POST", f"{backend}/api/v1/analysis-jobs", {"image_id": image_id})
        job_id = body.get("job_id")
        print(f"  POST /api/v1/analysis-jobs -> {status} (job_id={job_id})")
        for _ in range(10):
            status, body = _req("GET", f"{backend}/api/v1/analysis-jobs/{job_id}")
            if body.get("status") in ("succeeded", "failed"):
                break
            time.sleep(1)
        print(f"  GET  /api/v1/analysis-jobs/{job_id} -> status={body.get('status')}")
    else:
        print("  (이미지 업로드 실패 — 아래 원인 확인)")
        print(" ", body)
    print("[주방] 2단계 — 실제 음식 만들기 (사람이 하는 일이라 자동화 대상 아님)")

    step(f"[냉장고] 1~3단계 — 만든 음식 '{args.in_item}' IN")
    send_detection(backend, args.device_id, motion_direction="in",
                    detections=[{"label": "in-pair", "confidence": 0.85}])
    send_detection(backend, args.device_id,
                    detections=[{"label": args.in_item, "confidence": 0.9, "container_id": args.in_item}])
    print("3. bridge가 매칭해서 백엔드에 등록하길 기다리는 중 (최대 40초)...")
    ok = wait_for_food_item(backend, args.in_item, status_filter="active")
    print(f"  -> {'✅ active로 등록됨' if ok else '❌ 반영 안 됨 (bridge가 떠있는지 확인)'}")
    step("4. [냉장고] 대시보드 확인")
    show_dashboard(backend)

    print("\n앱(mobile-app)이나 백엔드 대시보드(/dashboard/)를 새로고침해서 눈으로도 확인해보세요.")


if __name__ == "__main__":
    main()
