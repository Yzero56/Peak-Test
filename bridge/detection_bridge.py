"""detection_bridge.py — Part1(YJ)과 Part2(Wa)의 탐지 이력을 매칭해서
실제 재고 입출고 이벤트(POST /api/v1/events/refrigerator)로 승격시키는 브릿지.

## 왜 필요한가

board-a-door-container 한 보드에 YJ(리드스위치+IN/OUT 판정)와 Wa(용기 재식별)가
같이 붙어 있지만, 둘은 서로 다른 파이썬 프로세스로 독립적으로 돈다:

  - YJ의 tools/inout_classifier/server.py  → "뭔가 들어갔다/나갔다"(motion_direction)는
    알지만 "그게 뭔지"(container_id)는 모른다.
  - Wa의 browser_container_realtime.py     → "이 용기가 뭔지"(container_id)는 알지만
    "들어가는 중인지 나가는 중인지"(motion_direction)는 모른다.

둘 다 --backend-url을 켜두면 각자 아는 것만 POST /api/v1/detections로 남긴다(이미
연결해둠 — INTEGRATION_NOTES.md 참고). 이 브릿지는 그렇게 쌓인 detections를 device_id별로
계속 지켜보다가, "컨테이너 이벤트"와 "모션 이벤트"가 서로 가까운 시각(--window-seconds,
기본 25초 — YJ의 문 세션 프레임 버퍼 길이 FRAME_LOG_MAX_S와 맞춤, 2026-08-27 8초→25초로
늘어난 것 반영)에 나오면 짝지어서 최종
POST /api/v1/events/refrigerator 한 번을 호출해 실제로 재고를 등록/소진시킨다.

## 한계 (의도적으로 단순하게 만든 부분)

- **순수 시간 매칭이다** — 진짜 "같은 문 세션"인지 door 세션 ID로 확인하는 게 아니라,
  그냥 "가까운 시각에 둘 다 나왔다"만 본다. 냉장고를 아주 빠르게 연속으로 여닫으면
  잘못 짝지어질 수 있다. 더 정확하게 하려면 board-a-door-container의 GET /reed가
  주는 문 세션 시작 시각을 두 스크립트가 같이 detections에 실어 보내고, 여기서는
  시각이 아니라 세션 ID로 매칭하는 편이 낫다 — 지금은 안 함(스코프 밖).
- **상태는 메모리에만 있다** — 브릿지를 재시작하면 매칭 대기 중이던 미완료 이벤트는
  버려진다(재고에는 아무 영향 없음 — 애초에 반영 전이었으므로).
- **디바이스 1개 가정 아님** — device_id별로 독립적으로 매칭하므로 여러 냉장고를
  동시에 운영해도 서로 섞이지 않는다.

## 실행

    python bridge/detection_bridge.py --backend-url http://localhost:8000 \\
        --device-id board-a-door-container
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import requests


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@dataclass
class PendingEvent:
    detection_id: str
    detected_at: datetime
    confidence: float
    # motion 이벤트면 motion_direction만, container 이벤트면 container_id/label만 채워짐
    motion_direction: str | None = None
    container_id: str | None = None
    label: str | None = None


class DeviceMatcher:
    """device_id 하나에 대한 매칭 상태 — "미완료 motion 이벤트 최대 1개, 미완료 container
    이벤트 최대 1개"만 들고 있다가 짝이 맞으면 즉시 소비한다."""

    def __init__(self, window_seconds: float):
        self.window_seconds = window_seconds
        self.pending_motion: PendingEvent | None = None
        self.pending_container: PendingEvent | None = None

    def _expire_stale(self, now: datetime) -> None:
        for attr in ("pending_motion", "pending_container"):
            ev: PendingEvent | None = getattr(self, attr)
            if ev is not None and (now - ev.detected_at).total_seconds() > self.window_seconds * 2:
                print(f"[bridge] 짝을 못 찾고 만료됨: {attr} detection_id={ev.detection_id}")
                setattr(self, attr, None)

    def feed(self, ev: PendingEvent) -> tuple[PendingEvent, PendingEvent] | None:
        """새 이벤트를 넣는다. motion+container가 window_seconds 안에서 짝지어지면
        (motion, container) 튜플을 반환하고 내부 상태를 비운다. 아니면 None."""
        self._expire_stale(ev.detected_at)

        if ev.motion_direction is not None:
            partner = self.pending_container
            if partner is not None and abs((ev.detected_at - partner.detected_at).total_seconds()) <= self.window_seconds:
                self.pending_container = None
                return ev, partner
            self.pending_motion = ev
            return None

        if ev.container_id is not None:
            partner = self.pending_motion
            if partner is not None and abs((ev.detected_at - partner.detected_at).total_seconds()) <= self.window_seconds:
                self.pending_motion = None
                return partner, ev
            self.pending_container = ev
            return None

        return None  # motion도 container_id도 없는 detection은 이 브릿지가 다룰 대상이 아님


def fire_refrigerator_event(backend_url: str, motion: PendingEvent, container: PendingEvent) -> bool:
    try:
        r = requests.post(
            f"{backend_url.rstrip('/')}/api/v1/events/refrigerator",
            json={
                "container_id": container.container_id,
                "motion_direction": motion.motion_direction,
                "confidence": min(container.confidence, 1.0),
                "recognition_status": "matched",
            },
            timeout=5,
        )
        if r.status_code >= 300:
            print(f"[bridge] refrigerator 이벤트 거부됨 ({r.status_code}): {r.text}")
            return False
        body = r.json()
        print(f"[bridge] ✅ {container.container_id} {motion.motion_direction} "
              f"→ action={body.get('action')} food_id={body.get('food_id')}")
        return True
    except requests.RequestException as e:
        print(f"[bridge] refrigerator 이벤트 전송 실패: {e}")
        return False


def run(backend_url: str, device_id: str, window_seconds: float, poll_interval: float) -> None:
    matcher = DeviceMatcher(window_seconds)
    seen_ids: set[str] = set()
    print(f"[bridge] {backend_url} 의 device_id={device_id} detections를 {poll_interval}s 간격으로 지켜봅니다 "
          f"(매칭 시간창 {window_seconds}s).")

    while True:
        try:
            r = requests.get(
                f"{backend_url.rstrip('/')}/api/v1/detections",
                params={"device_id": device_id, "limit": 50},
                timeout=5,
            )
            r.raise_for_status()
            rows = r.json()
        except requests.RequestException as e:
            print(f"[bridge] 조회 실패, {poll_interval}s 후 재시도: {e}")
            time.sleep(poll_interval)
            continue

        # API는 최신순(desc)으로 주므로, 오래된 것부터 순서대로 처리한다.
        new_rows = [row for row in rows if row["id"] not in seen_ids]
        for row in reversed(new_rows):
            seen_ids.add(row["id"])
            ev = PendingEvent(
                detection_id=row["id"],
                detected_at=_parse_ts(row["detected_at"]),
                confidence=float(row["confidence"]),
                motion_direction=row.get("motion_direction"),
                container_id=row.get("container_id"),
                label=row.get("label"),
            )
            matched = matcher.feed(ev)
            if matched is not None:
                motion, container = matched
                fire_refrigerator_event(backend_url, motion, container)

        if len(seen_ids) > 2000:  # 데모 세션이 길어져도 메모리가 무한정 늘지 않게
            seen_ids = set(list(seen_ids)[-500:])

        time.sleep(poll_interval)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("##")[0])
    ap.add_argument("--backend-url", default="http://localhost:8000")
    ap.add_argument("--device-id", default="board-a-door-container")
    ap.add_argument("--window-seconds", type=float, default=25.0,
                     help="motion/container 이벤트를 같은 사건으로 볼 최대 시간 간격")
    ap.add_argument("--poll-interval", type=float, default=1.0)
    args = ap.parse_args()
    try:
        run(args.backend_url, args.device_id, args.window_seconds, args.poll_interval)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
