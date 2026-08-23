# 냉장고 지킴이 백엔드

ESP32-S3 카메라 · reed 도어 센서 · BME680 온습도/가스 센서를 받아 저장하고,
팀이 확인할 수 있는 관리자 대시보드(FastAPI + Jinja2 + HTMX)를 제공합니다.
별도 프론트엔드 빌드 없이 `uvicorn` 하나로 실행됩니다.

## 실행

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
copy .env.example .env        # Windows: copy, macOS/Linux: cp
# .env 파일을 열어 ADMIN_PASSWORD, SECRET_KEY를 실제 값으로 채우기

uvicorn app.main:app --reload --port 8000
```

브라우저에서 http://localhost:8000 접속 → `.env`에 설정한 `ADMIN_PASSWORD`로 로그인.

## 기기 등록 & 인입 API

1. 대시보드 상단의 "기기 등록"에서 기기 ID(예: `fridge-01`)와 이름을 입력하면 **토큰이 한 번만** 표시됩니다.
   이 토큰을 ESP32 펌웨어(`firmware/xiao-esp32s3-cam/`)의 `X-Device-Token` 헤더 값으로 저장하세요.
2. 센서값 전송 (도어/온습도/가스 — 필드는 모두 선택):

   ```bash
   curl -X POST http://localhost:8000/api/devices/fridge-01/sensors \
     -H "X-Device-Token: <발급받은 토큰>" \
     -H "Content-Type: application/json" \
     -d '{"door_open": false, "temperature_c": 4.2, "humidity_pct": 55, "gas_resistance_ohm": 62000}'
   ```

3. 하트비트 (기기가 살아있음 + 자신의 IP를 알림 — ESP32가 15초마다 자동 전송):

   ```bash
   curl -X POST http://localhost:8000/api/devices/fridge-01/heartbeat \
     -H "X-Device-Token: <발급받은 토큰>"
   ```

카메라 이미지는 더 이상 기기가 백엔드로 push하지 않습니다. ESP32가 자체
HTTP 서버로 `/stream`(라이브 MJPEG), `/capture`(정지 프레임)를 직접 서빙하고,
대시보드에서 "지금 스캔하기"를 누르면 백엔드가 그 순간 `/capture`를
pull해서 인식·저장합니다(기기당 최신 1건만 유지, 쌓이지 않음).

또한 리드스위치로 감지한 `door_open` 값이 `/sensors`로 들어오면(값이 실제로
바뀌었을 때만) `app/live_scan.py`가 기기별 백그라운드 스레드를 시작/중단합니다:
문이 열려있는 동안 몇 초 간격으로 자동으로 `/capture`를 가져가 인식하고,
닫히면 멈춥니다. 즉 "지금 스캔하기"는 수동 1회 트리거, 리드스위치는
문이 열려있는 동안의 자동 반복 트리거입니다. 자세한 흐름은
`firmware/xiao-esp32s3-cam/README.md` 참고.

## 구조

- `app/models.py` — Device(+ip_address) / SensorReading / DoorEvent / Capture / DetectedObject (SQLite, 파일: `backend/fridge.db`)
- `app/detection.py` — 객체 인식(VLM) 연동 지점. 지금은 `mock_detector`가 더미 라벨을 반환하며,
  실제 VLM(Claude/OpenAI/Gemini)을 붙일 때는 `detect_objects()` 내부만 교체하면 됩니다.
- `app/services.py`의 `save_capture()` — "지금 스캔하기" 시 호출되는 곳. 기기의 기존 캡처를
  지우고 새 캡처 1건으로 교체한 뒤 `detect_objects()`를 실행합니다.
- `app/live_scan.py` — 문 열림/닫힘에 따른 자동 스캔 반복 루프(기기별 백그라운드 스레드).
  `routers/ingest.py`의 `/sensors`에서 `door_open` 상태 전환을 감지해 시작/중단시킵니다.
- `app/security.py` — 관리자 대시보드는 공용 비밀번호 세션 로그인, 기기 인입 API는 기기별 토큰(SHA-256 해시 저장) 인증.
- 미디어(캡처 이미지)는 `backend/media/captures/{device_id}/latest.jpg`에 저장되고, 로그인한 관리자만
  `/media/captures/{capture_id}`로 조회할 수 있습니다 (공개 정적 경로 아님). 단, ESP32 자체의
  `/stream`·`/capture`는 인증이 없으니 로컬 데모 범위로만 사용하세요.

`backend/.env`, `backend/media/`, `backend/fridge.db`는 커밋하지 않습니다 (`.gitignore` 참고).
