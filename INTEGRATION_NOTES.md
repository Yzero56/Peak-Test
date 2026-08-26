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
5. **신규 통합 펌웨어** `firmware/board-a-door-container/board-a-door-container.ino`.

   **[정정] 처음에 잘못 설계했던 부분**: 처음엔 "YJ는 리드스위치만, Wa는 카메라만
   써봤으니 새 계약(`GET /jpg`+`GET /reed`)으로 합치면 된다"고 판단하고 그렇게
   만들었었다 — **틀렸다.** YJ는 이미 실제 펌웨어(`webcam_ap_capture.ino`, Wi-Fi
   비밀번호 때문에 git에 없음)에서 리드스위치+카메라를 한 보드로 같이 써왔고,
   그 결과 튜닝된 계약이 `part1-inout/tools/inout_classifier/server.py`와
   `tools/web_capture/http_cam.py`에 실측값 그대로 남아있었다:
   `GET /door` → `{"open": bool}`, `GET /capture?quality=standard` → JPEG
   800x600 quality=12(`server.py`의 `check_door()`/`fetch_preview_frame()` 참고,
   화질이 학습 데이터와 다르면 오분류 편향이 생긴다는 실측 코멘트까지 있었음).
   이 사실은 git에 없는 파일 목록만 보고 "동시 사용 안 해봤다"고 결론 낸 게
   원인 — 실제로 그 firmware와 통신하는 **파이썬 클라이언트 코드**를 먼저
   확인했어야 했다.

   **지금 버전**은 이 실제 계약(`/door`, `/capture?quality=`, `/preview`)을 그대로
   구현하고, 여기에 Wa가 쓰는 기존 계약(`GET /jpg`)을 추가해서 두 파이썬 클라이언트
   다 코드 수정 없이 붙게 만들었다. 해상도(SVGA 800x600)·품질 값(12/16/20/8)도
   YJ 코드에 실측으로 박혀있던 값을 그대로 가져왔다 — 임의로 바꾸면 안 됨.
   AP+STA 겸용 Wi-Fi는 YJ의 커밋 메시지(`92367d4`)에 설명된 동작을 재구성한 것 —
   **실제 STA 접속·mDNS 동작, 그리고 리드스위치+카메라 동시 사용 자체는 여전히
   하드웨어로 검증 안 됨**(아래 "검증 필요" 참고 — 이번엔 최소한 계약은 맞춰놨지만
   실물 배선·GPIO 동작까지 보장하는 건 아님).
6. **board-b-sensor**: HJ의 `firmware/xiao-esp32s3-cam`을 그대로 가져오되, 센서 보고
   endpoint를 kang 백엔드 계약(`POST /api/v1/sensor-readings`, 인증 헤더 없음)으로
   교체. 하트비트(`/api/devices/{id}/heartbeat`)는 대응하는 kang 엔드포인트가 없어서
   no-op 처리(아래 "미해결" 참고).

## 미해결 — 다음에 손봐야 할 것

### 1. Part1/Part2 결과 → 백엔드 보고 (연결 완료, 재고 자동화는 아직)

`part1-inout/tools/inout_classifier/server.py`(`record_result()`)와
`part2-container/browser_container_realtime.py`(`recognize_next()`)에 백엔드 보고 코드를
추가했다. 둘 다 `--backend-url http://<host>:8000`을 주면(기본은 빈 문자열 = 비활성,
기존 동작 그대로) 결과가 나올 때마다 별도 스레드로 `POST /api/v1/detections`를 보낸다 —
실제 코드가 만드는 것과 동일한 payload로 로컬 백엔드에 쏴서 `GET /api/v1/detections`에
정상 조회되는 것까지 확인함(하드웨어 없이, 코드 레벨로 검증한 것 — 실물 카메라로
연속 호출될 때의 타이밍/스레드 동작은 아직 미검증).

**왜 `/api/v1/events/refrigerator`(재고 자동 등록)가 아니라 `/api/v1/detections`(탐지 이력)로
보내는지**: 재고를 등록/소진하려면 `container_id`(뭐가)와 `motion_direction`(들어갔는지
나갔는지)이 둘 다 필요한데, Part1은 motion_direction만 알고 Part2는 container_id만 안다 —
어느 한쪽도 혼자서는 유효한 `RefrigeratorEventCreate`를 못 만든다. 그래서 두 파트는
각자 아는 것만 detections로 남기고, **`bridge/detection_bridge.py`가 같은 device_id의
motion 이벤트와 container 이벤트를 시간창(기본 8초) 안에서 짝지어 최종
`/api/v1/events/refrigerator` 한 번을 호출한다** — 실제로 컨테이너 이벤트 → 3초 뒤
모션 이벤트를 넣어봐서 재고에 새 식품이 등록되는 것까지 확인함.

⚠️ 브릿지는 **순수 시간 매칭**이라(문 세션 ID로 확인하는 게 아님), 냉장고를 아주 빠르게
연속으로 여닫으면 잘못 짝지어질 수 있다 — 더 정확하게 하려면 board-a-door-container의
`GET /door`가 주는 문 상태 변화 시각을 두 스크립트가 detections에 같이 실어 보내고
세션 ID로 매칭하는 게 낫다(스크립트 docstring에 적어둠, 지금은 미구현).

- YJ: `--backend-url`, `--device-id`(기본 `board-a-door-container`) 인자 추가.
  `in-pair`/`out-pair`만 보고하고 `hand_only-pair`/`uncertain`은 보고 안 함.
- Wa: `--backend-url`, `--device-id` 인자 추가. `status == "matched"`(알려진 용기로
  확정 재식별됐을 때)만 보고.
- 브릿지: `python bridge/detection_bridge.py --backend-url http://<host>:8000`으로 실행
  (기본 device-id `board-a-door-container`, window 8초, poll 1초 — 전부 인자로 조정 가능).

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
  그 커밋 메시지 설명 + 파이썬 클라이언트가 실제로 요청하는 HTTP 계약을 바탕으로
  새로 작성한 것이라, GPIO 배선까지 원본과 100% 같다는 보장은 없음)
- board-a에서 리드스위치(D0)와 카메라를 **이 스케치 형태로** 동시에 쓸 때 GPIO
  충돌이 없는지(YJ의 원본 webcam_ap_capture.ino는 실제로 이미 검증된 조합이지만,
  그 파일 자체를 볼 수 없어서 D0/D1 배선은 reed_switch_test.ino에서 가져온 것 —
  원본과 배선이 같은지 실물로 확인 필요)
- board-b의 kang 백엔드 재배선(`/api/v1/sensor-readings`) 실물 테스트

### 4. PostgreSQL 인프라

kang 백엔드는 SQLite가 아니라 PostgreSQL이 필요하다(`backend/.env`의
`DATABASE_URL`). 시연 장소(공학 1관 공동강의실)에 인터넷이 없거나 불안정하면
로컬 Postgres를 노트북에 미리 띄워둬야 한다 — 클라우드 DB 의존은 금지.

### 5. 인증

kang 백엔드는 아직 인증이 없다(개발 단계 명시). 공용 네트워크에서 시연할 때
외부인이 `/api/v1/food-items` 등을 건드릴 수 있다는 뜻 — 데모 당일 네트워크
격리(자체 AP/핫스팟 사용 등)로 완화하거나, 최소한의 토큰 체크를 추가할지 결정 필요.
