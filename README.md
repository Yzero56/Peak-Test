# PEAK Smart

냉장고가 유통기한을 대신 기억해주는 스마트 키친 서비스. 사진 한 장으로 식품을 등록하면
AI가 식품명·유통기한을 읽고, 카메라·센서가 냉장고 입출고를 자동으로 감지해 오늘 먼저
먹어야 할 것과 남은 재료로 만들 수 있는 레시피를 알려준다.

이 브랜치(`integration`)는 4개 파트 브랜치(`YJ`, `Wa`, `kang`, `HJ`)를 하나의 시연
가능한 시스템으로 합친 결과물이다. 프로젝트 전체 배경·설계 원칙·발표 대본은
[`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md), 통합 과정에서 내린 결정과
아직 안 끝난 작업은 [`INTEGRATION_NOTES.md`](INTEGRATION_NOTES.md) 참고.

## 구조

```
backend/            단일 백엔드 (FastAPI + PostgreSQL) — kang 브랜치 기반, 원래 4번 파트(HJ)
                     자체 백엔드는 폐기하고 여기로 통일. /api/v1/* + 레거시 /api/* 호환 라우터.
mobile-app/          앱 (Expo + React Native + NativeWind) — HJ 브랜치. backend/에 그대로 붙는다.
part1-inout/         냉장고 IN/OUT 판정 — YJ 브랜치. 리드스위치+카메라 프로토타입, 분류기, 리포트.
part2-container/     용기 종류 인식 — Wa 브랜치. YOLO-World+DINOv2 스크립트, 학습된 분류기.
                     (원본 학습 데이터셋 이미지 수십MB는 용량상 제외 — 필요하면 origin/Wa 브랜치 참고)
firmware/
  board-a-door-container/   신규 통합 스케치 — 리드스위치(Part1) + 카메라(Part1/Part2 겸용) 한 보드.
  board-b-sensor/            BME680 온습도·가스 센서 + 카메라(HJ 브랜치 원본, 백엔드 주소만 재배선).
  _reference_kang_ap_test/   kang의 초기 진단용 스케치(참고용, 시연에는 미사용).
docs/                발표 자료, 파트별 연동 계약, 프로젝트 개요 (kang 브랜치 + 신규 통합 문서).
```

## 로컬에서 통합 시스템 띄우기

1. **백엔드**
   ```bash
   cd backend
   cp .env.example .env   # DATABASE_URL 등 채우기 (PostgreSQL 필요)
   pip install -e .
   alembic upgrade head
   python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
   - API 문서: `http://localhost:8000/docs`
   - 대시보드: `http://localhost:8000/dashboard/`
   - 발표자료: `http://localhost:8000/presentation/`

2. **앱** — 백엔드가 뜬 PC의 LAN IP로 설정
   ```bash
   cd mobile-app
   npm install
   npx expo start
   ```
   앱 설정 탭 → "백엔드 연결"에 `http://<노트북 LAN IP>:8000`과 토큰(아무 값이나 — 현재
   백엔드는 인증을 검사하지 않는다) 입력.

3. **보드 A(문 감지+용기 인식)** — `firmware/board-a-door-container/secrets.h.example`을
   `secrets.h`로 복사해 채운 뒤 업로드. 이후 파이썬 클라이언트 실행 — `--backend-url`을
   주면 결과를 kang 백엔드에 자동 보고한다:
   ```bash
   # Part1 IN/OUT 판정 대시보드
   cd part1-inout && ./.venv/bin/python tools/inout_classifier/server.py \
     --esp-host <board-a-ip> --backend-url http://<backend-host>:8000
   # Part2 용기 인식
   cd part2-container && python browser_container_realtime.py <board-a-ip> \
     --backend-url http://<backend-host>:8000
   # 위 둘의 결과(모션 방향 + 용기 종류)를 시간창으로 매칭해서 실제 재고에 반영
   python bridge/detection_bridge.py --backend-url http://<backend-host>:8000
   ```
   세 프로세스가 다 떠 있어야 "문 열고 용기를 보여주면 앱 재고가 자동으로 바뀌는" 전체
   흐름이 완성된다. 매칭 로직의 한계는 [`INTEGRATION_NOTES.md`](INTEGRATION_NOTES.md) 참고.

4. **보드 B(BME680 센서)** — `firmware/board-b-sensor/secrets.h.example`을 `secrets.h`로
   복사해 `BACKEND_BASE_URL`을 위 백엔드 주소로 채운 뒤 업로드. 온습도/가스 값이 자동으로
   `POST /api/v1/sensor-readings`로 올라간다.

## 담당

| 브랜치 | 담당 | Part |
|---|---|---|
| `YJ` | YJ | Part 1 — IN/OUT 판정 |
| `Wa` | Wa | Part 2 — 용기 종류 인식 |
| `kang` | kang | Part 3·4 — 백엔드/VLM |
| `HJ` | HJ | Part 4 — 앱 |
