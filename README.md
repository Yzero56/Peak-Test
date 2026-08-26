# Peak-Test — 냉장고 IN/OUT 판정 (Part 1)

XIAO ESP32-S3 Sense + OV3660 카메라와 리드스위치로 냉장고 문 개폐를 감지하고,
문이 열려있는 동안 손 위치를 추적해 물건이 **들어갔는지(IN) / 나갔는지(OUT) /
아무 일도 없었는지(hand_only)**를 실시간으로 판정하는 시스템.

결과·설계 요약은 [`docs/PART1_INOUT_REPORT.md`](docs/PART1_INOUT_REPORT.md)
(held-out 테스트 정확도 73.0%, confusion matrix 포함) 참고.

## 구성

- `firmware/webcam_ap_capture/` — ESP32 카메라 펌웨어(AP/STA 겸용, 리드스위치 연동)
- `motion_capture/` — 초기 휴리스틱 기반 모션 감지 프로토타입(참고용)
- `tools/web_capture/` — 학습용 사진 촬영 웹 도구 (before/after 3-step 촬영)
- `tools/edgeimpulse/` — Edge Impulse 업로드/학습 파이프라인
- `tools/inout_classifier/` — 실시간 IN/OUT 판정 웹 대시보드(로컬 모델 추론)

## 준비

```bash
brew install portaudio   # edge_impulse_linux(로컬 추론)가 의존하는 pyaudio 빌드에 필요 (macOS)
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

`.env`에 Edge Impulse API 키를 넣는다:

```
EI_API_KEY=<Edge Impulse 프로젝트 API 키>
```

ESP32는 `firmware/webcam_ap_capture/webcam_ap_capture.ino`를 업로드한다.
기본은 자체 핫스팟(AP 모드, SSID `FridgeCam`)으로 뜨고, 파일 상단의
`WIFI_STA_SSID`/`WIFI_STA_PASSWORD`를 채우면 집/현장 와이파이에 합류하는
STA 모드로 전환된다(연결 실패 시 자동으로 AP 모드 폴백). **이 값을 채운
`.ino` 파일은 git에 커밋하지 말 것** — 이미 `.gitignore`에 등록돼있다.

## 실행

데이터 수집(Mac이 ESP32와 같은 Wi-Fi에 있어야 함):

```bash
./.venv/bin/python tools/web_capture/server.py --esp-host 192.168.4.1 --http-port 8420
```

실시간 IN/OUT 판정 대시보드:

```bash
./.venv/bin/python tools/inout_classifier/server.py --esp-host 192.168.4.1 --http-port 8600
```

브라우저에서 `http://localhost:8420` (수집) / `http://localhost:8600` (판정) 접속.

## 핵심 설계

- **손 위치 기반 동적 크롭** — 냉장고 전체가 아니라 손이 닿은 선반만 비교
- **hand-free before/after** — 손을 뺀 상태로 전/후를 찍어 방향 신호가
  손에 가려지지 않게 함
- **diff 인코딩** — 전/후 변화량을 R(생김 후보)/B(없어짐 후보) 색으로
  인코딩한 한 장짜리 이미지로 학습 (좌우로 이어붙이는 방식은 CNN이 "비교"를
  학습 못 하는 문제가 있었음)
- **로컬 TFLite 추론** — 카메라가 자체 AP라 인터넷이 없는 환경에서도
  동작하도록 클라우드 대신 로컬 모델(.eim)로 판정
- **낮은 확신도는 "판단 애매함"으로 표시** — 확신 없는 판정을 확정적으로
  틀리게 보여주지 않기 위한 안전장치

자세한 배경과 시행착오는 `docs/PART1_INOUT_REPORT.md` 참고.
