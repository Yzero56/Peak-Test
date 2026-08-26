# 통합 작업 노트

`YJ`, `Wa`, `kang`, `HJ` 4개 브랜치를 `integration` 브랜치로 합치면서 내린 결정과,
아직 손대지 않고 남겨둔 것을 정리한다. 다음에 이어서 작업할 사람(팀원이든 나중의
나든)이 "왜 이렇게 했는지" 다시 조사하지 않아도 되게 하는 게 목적.

## 왜 kang 백엔드를 기준으로 삼았나

`kang` 브랜치의 백엔드(`app/`)에 이미 4번 파트(HJ) 앱과의 호환 레이어
(`app/api/routes/legacy.py` — `/api/inventory`, `/api/scan-candidates`)와, 1·2번 파트
이벤트를 받는 스키마(`RefrigeratorEventCreate`, `DetectionBatchCreate`)가 구현돼 있었다.
반대 방향(HJ 백엔드를 기준으로 kang 기능을 이식)은 처음부터 다시 만들어야 해서
비효율적 — 그래서 kang을 단일 백엔드로 확정하고, HJ 자신의 `backend/`(FastAPI+SQLite)는
이 통합본에 포함하지 않았다.

## 실제로 한 작업

1. **디렉터리 재구성**: `app/`, `alembic*`, `tests/`, `data/`, `pyproject.toml`, `scripts/`
   → `backend/`로 이동. `docs/`는 루트에 그대로 두고 `backend/app/main.py`의
   `StaticFiles(directory="docs")` → `"../docs"`로 수정(발표자료 mount 유지).
2. **HJ 앱 이식**: `mobile-app/`으로 복사 (자체 `backend/`는 제외). **`src/lib/api.ts`는
   한 글자도 안 고쳤다** — `/api/inventory`, `/api/scan-candidates`는 kang의 legacy
   라우터가 이미 같은 필드명·숫자 ID로 응답하기 때문(직접 코드 대조로 확인함).
3. **레거시 엔드포인트 2개 추가**(`backend/app/api/routes/legacy.py`):
   - `GET /api/climate` — 가장 최근 `SensorReading` 하나를 `{temperatureC, humidityPct}`로.
   - `GET /api/recipes` — HJ의 `backend/app/recipes.py`(식품안전나라 Open API 연동,
     `backend/app/services/recipes.py`로 그대로 포팅)를 호출.
   - `Settings.food_safety_api_key` 필드와 `.env.example`의 `FOOD_SAFETY_API_KEY` 추가.
4. **YJ/Wa 이식**: `part1-inout/`, `part2-container/`로 복사. Wa의 학습용 원본 이미지
   데이터셋(`category_dataset_prepared_v2/`, `학습용 데이터/`, `v2_registration_debug/`,
   `retest_data/`, `cropped_dataset/`, `yolo_world_evaluation/`, 총 80MB+)은 시연에
   필요 없어서 제외했다 — 필요하면 `origin/Wa` 브랜치에 그대로 있다. 학습된 모델
   (`category_classifier.joblib`), 컨테이너 등록 DB, 임베딩 캐시(.npz)는 포함.
5. **신규 통합 펌웨어** `firmware/board-a-door-container/board-a-door-container.ino`:
   YJ의 `reed_switch_test.ino` + `webcam_ap_collect.ino`와 Wa의 `01_container_collector.ino`를
   합친 새 스케치. 근거: 두 팀의 카메라 스냅샷 계약이 이미 동일(`GET /jpg` →
   `image/jpeg`)했기 때문에, 리드스위치 상태를 새 `GET /reed`로 노출하는 것 말고는
   합치는 데 코드 충돌이 없었다. AP+STA 겸용 Wi-Fi는 YJ의 커밋 메시지(`92367d4`)에
   설명된 동작을 재구성한 것 — **실제 STA 접속·mDNS 동작은 하드웨어로 검증 안 됨**
   (아래 "검증 필요" 참고).
6. **board-b-sensor**: HJ의 `firmware/xiao-esp32s3-cam`을 그대로 가져오되, 센서 보고
   endpoint를 kang 백엔드 계약(`POST /api/v1/sensor-readings`, 인증 헤더 없음)으로
   교체. 하트비트(`/api/devices/{id}/heartbeat`)는 대응하는 kang 엔드포인트가 없어서
   no-op 처리(아래 "미해결" 참고).

## 미해결 — 다음에 손봐야 할 것

### 1. Part1/Part2 결과가 아직 백엔드에 안 올라간다 (가장 큰 공백)

`part1-inout/tools/inout_classifier/server.py`와 `part2-container/browser_container_realtime.py`는
지금 각자 로컬 브라우저 대시보드에만 결과를 보여준다. kang 백엔드의
`POST /api/v1/events/refrigerator`가 정확히 이 두 파트의 결과를 받아서 자동 입출고 처리를
하도록 설계돼 있으니(스키마: `container_id`, `motion_direction`("in"/"out"),
`recognition_status`, `confidence`, `food_name` 등), 두 스크립트에 HTTP POST 한 줄만
추가하면 된다 — 다만 **실제 하드웨어로 재고가 정상 반영되는지 확인이 필요해서
일부러 자동으로 넣지 않았다.**

- YJ 쪽 삽입 지점: `part1-inout/tools/inout_classifier/server.py`의 `record_result()`
  (판정이 나올 때마다 호출됨, `result["label"]`이 `"in"`/`"out"`/`"hand_only-pair"`).
- Wa 쪽 삽입 지점: `part2-container/browser_container_realtime.py`의 `recognize_next()`
  라우트(분류 `result` dict를 만든 직후).

예시 POST (두 곳 공통으로 쓸 수 있는 형태):

```python
import requests

def report_to_backend(container_id: str, motion_direction: str, **extra):
    try:
        requests.post(
            "http://<backend-host>:8000/api/v1/events/refrigerator",
            json={
                "container_id": container_id,
                "motion_direction": motion_direction,  # "in" | "out"
                **extra,
            },
            timeout=3,
        )
    except requests.RequestException as e:
        print(f"[backend] 보고 실패: {e}")
```

### 2. board-b-sensor의 "지금 스캔하기" pull 흐름이 안 이어짐

HJ의 원래 설계는 백엔드가 필요할 때 보드의 `/capture`를 당겨가는 pull 방식이었는데,
kang 백엔드는 클라이언트가 `POST /api/v1/food-images`로 직접 올리는 push 방식이다.
지금은 board-b의 `/stream`, `/capture`는 로컬 LAN 접속용으로만 남겨두고 하트비트
전송은 껐다 — **VLM 식품 라벨 인식 흐름을 이 보드에서 시작할지, 아니면 폰 카메라
(앱의 사진 등록 화면)로만 할지 팀 결정이 필요.**

### 3. 검증 필요 — 실제 하드웨어에서 아직 안 돌려봄

- `firmware/board-a-door-container`의 STA/AP 폴백·mDNS. (YJ의 실제 최종 스케치
  `firmware/webcam_ap_capture/webcam_ap_capture.ino`는 Wi-Fi 비밀번호가 들어있어서
  `.gitignore`로 추적 해제돼 있었고 저장소 어디에도 없다 — 이번 통합 스케치는
  그 커밋 메시지 설명을 바탕으로 새로 작성한 것이라 원본과 미세하게 다를 수 있음)
- board-a에서 리드스위치(D0)와 카메라를 **동시에** 쓸 때 GPIO 충돌이 없는지
  (기존 두 프로토타입은 각각 카메라만 썼거나 리드스위치만 썼음, 동시 사용은 이번이 처음)
- board-b의 kang 백엔드 재배선(`/api/v1/sensor-readings`) 실물 테스트

### 4. PostgreSQL 인프라

kang 백엔드는 SQLite가 아니라 PostgreSQL이 필요하다(`backend/.env`의
`DATABASE_URL`). 시연 장소(공학 1관 공동강의실)에 인터넷이 없거나 불안정하면
로컬 Postgres를 노트북에 미리 띄워둬야 한다 — 클라우드 DB 의존은 금지.

### 5. 인증

kang 백엔드는 아직 인증이 없다(개발 단계 명시). 공용 네트워크에서 시연할 때
외부인이 `/api/v1/food-items` 등을 건드릴 수 있다는 뜻 — 데모 당일 네트워크
격리(자체 AP/핫스팟 사용 등)로 완화하거나, 최소한의 토큰 체크를 추가할지 결정 필요.
