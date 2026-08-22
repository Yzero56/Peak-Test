# XIAO ESP32-S3 Sense — Wi-Fi 카메라 업로더

USB 시리얼로 PC에 사진을 넘기는 방식이 아니라, 보드가 **자체 Wi-Fi로 백엔드에
직접 접속**해서 주기적으로 촬영한 사진을 업로드합니다. USB는 최초 펌웨어
업로드와 시리얼 디버그 로그 확인 용도로만 씁니다.

## 1. Arduino IDE 준비

1. Arduino IDE 환경설정 > 추가 보드 매니저 URL에 아래 주소 추가:
   `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
2. 보드 매니저에서 **esp32 by Espressif Systems** 설치 (최신 안정 버전)
3. 보드 선택: **Tools > Board > XIAO_ESP32S3**
4. **Tools > PSRAM > OPI PSRAM**로 설정 (카메라 프레임버퍼에 필요, Sense 보드는 PSRAM 내장)

## 2. 기기 등록 & 설정 파일

1. 백엔드 대시보드(`backend/README.md` 참고)에서 로그인 후 **기기 등록**으로
   새 기기를 만들고, 한 번만 보여지는 토큰을 복사해둡니다.
2. 이 폴더의 `secrets.h.example`을 같은 폴더에 `secrets.h`로 복사한 뒤 값을 채웁니다:
   - `WIFI_SSID` / `WIFI_PASSWORD` — ESP32가 접속할 Wi-Fi (2.4GHz만 지원)
   - `DEVICE_ID` / `DEVICE_TOKEN` — 1번에서 등록한 기기 정보
   - `BACKEND_BASE_URL` — 백엔드가 실행 중인 PC의 **LAN IP**:포트
     (예: `http://192.168.0.10:8000`. `localhost`/`127.0.0.1`은 ESP32 입장에서
     자기 자신을 가리키므로 동작하지 않습니다. PC와 ESP32가 같은 Wi-Fi에
     연결되어 있어야 하고, PC 방화벽에서 8000번 포트 인바운드를 허용해야 합니다.)

`secrets.h`는 `.gitignore`에 등록되어 있어 커밋되지 않습니다.

## 3. 업로드 & 확인

1. USB로 보드를 연결하고 `xiao-esp32s3-cam.ino`를 업로드합니다.
2. **Tools > Serial Monitor** (115200 baud)를 열면 Wi-Fi 연결/촬영/업로드
   로그가 출력됩니다 — 이건 디버그용이고, 실제 사진 데이터는 Wi-Fi로만 전송됩니다.
3. 백엔드 대시보드의 개요/캡처 화면에서 새 캡처와 인식된 객체(현재는 목업)가
   올라오는지 확인합니다.

## 촬영 주기 조정

기본은 60초(`CAPTURE_INTERVAL_MS`)마다 촬영합니다. 스케치 상단의
`#define CAPTURE_INTERVAL_MS` 값을 바꾸면 됩니다.

## 참고

- 카메라 핀맵은 Seeed XIAO ESP32-S3 Sense의 공개된 표준 핀 배치를 사용합니다.
  다른 보드(OV5640 업그레이드 등)로 교체 시 핀맵을 다시 확인하세요.
- 센서(BME680 온습도/가스, 도어 리드 스위치) 업로드 펌웨어는 아직 포함되어
  있지 않습니다 — 필요해지면 같은 방식(`POST /api/devices/{id}/sensors`)으로
  추가하면 됩니다.
