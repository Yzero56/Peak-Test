# XIAO ESP32-S3 Sense — Wi-Fi 라이브 카메라 서버

사진을 찍어 백엔드에 계속 쌓아두는 방식이 아니라, 보드가 **자체 Wi-Fi로 HTTP
서버를 열어 실시간 라이브 뷰(`/stream`)와 정지 프레임(`/capture`)을 직접
서빙**합니다. 백엔드는 대시보드에서 "지금 스캔하기"를 누른 순간에만
`/capture`를 가져가 인식하고, 라이브 영상은 대시보드가 `/stream`을 그대로
`<img>`로 띄워 보여줍니다. USB는 최초 펌웨어 업로드와 시리얼 디버그 로그
확인 용도로만 씁니다.

> **보안 참고**: `/stream`, `/capture`에는 인증이 없습니다. 같은 Wi-Fi(LAN)에
> 있으면 누구나 볼 수 있어요 — 로컬 데모 범위로만 쓰세요.

**리드스위치로 실시간 탐지 on/off**: 보드의 D10(GPIO9)에 리드스위치를 연결하면
(한쪽 핀 → D10, 다른 쪽 핀 → GND) 문 개폐를 감지해 `POST /api/devices/{id}/sensors`로
`door_open` 값을 보고합니다. 백엔드는 `door_open=true`를 받으면 몇 초 간격으로
`/capture`를 자동으로 가져가 인식하는 루프를 시작하고, `door_open=false`를 받으면
멈춥니다 — 대시보드 기기 상세 페이지의 "최근 스캔 결과" 카드에 실시간 탐지 중 여부와
결과가 5초마다 자동 갱신되어 표시됩니다.

**문 닫히면 카메라 전원도 절약**: 문이 닫히면(`door_open=false`) 보드가
`esp_camera_deinit()`으로 카메라 자체를 끄고, 문이 열리면 다시 켭니다. XIAO ESP32-S3
Sense는 카메라 PWDN 핀이 배선되어 있지 않아 완전한 전원 차단은 아니고 클럭/DMA를
끄는 소프트웨어 레벨 절전입니다. 꺼져있는 동안 `/capture`, `/stream`은 503을
응답하고, 대시보드 라이브 뷰는 "문이 열리면 라이브 영상이 여기에 표시돼요" 안내로
바뀝니다.

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
2. **Tools > Serial Monitor** (115200 baud)를 열면 Wi-Fi 연결 IP와
   `/capture`(포트 80), `/stream`(포트 81) 서버가 뜬 것을 확인할 수 있습니다.
   두 포트로 나눈 이유: `/stream`은 연결이 계속 열려있는 핸들러라 같은 서버에
   `/capture`를 같이 두면 누군가 라이브 영상을 보는 동안 스캔 요청이 응답을 못 받습니다.
3. 브라우저에서 `http://<보드의-IP>:81/stream`을 열어 라이브 영상이 바로 뜨는지
   확인합니다 (시리얼 로그의 IP 사용).
4. 보드는 15초마다 백엔드에 "하트비트"(사진 없이 상태만)를 보냅니다. 백엔드
   대시보드의 기기 상세 페이지가 온라인으로 뜨고 라이브 뷰가 표시되는지,
   "지금 스캔하기"를 눌렀을 때 방금 찍은 프레임과 인식 결과(현재는 목업)가
   뜨는지 확인합니다.

## 촬영 해상도 / 하트비트 주기 조정

- 라이브 스트리밍이 매끄럽도록 기본 해상도를 SVGA(800x600, PSRAM 있을 때)로
  낮췄습니다. `initCamera()`의 `config.frame_size`를 바꾸면 됩니다.
- 하트비트 주기는 기본 15초(`HEARTBEAT_INTERVAL_MS`)입니다. 스케치 상단의
  `#define HEARTBEAT_INTERVAL_MS` 값을 바꾸면 됩니다.

## 참고

- 카메라 핀맵은 Seeed XIAO ESP32-S3 Sense의 공개된 표준 핀 배치를 사용합니다.
  다른 보드(OV5640 업그레이드 등)로 교체 시 핀맵을 다시 확인하세요.
- 리드스위치는 D10(GPIO9)에 연결되어 있고(`REED_GPIO_NUM`), 폴링 주기(`DOOR_POLL_INTERVAL_MS`,
  기본 300ms)와 디바운스 시간(`DOOR_DEBOUNCE_MS`, 기본 150ms)은 스케치 상단에서 조정 가능합니다.
- BME680 온습도/가스 센서는 I2C(SDA/SCL, 보드 기본 D4/D5)로 연결하면 됩니다.
  `bme680_sensor.h`/`.cpp`에 분리되어 있고(esp_camera.h와 Adafruit_Sensor.h를 같은
  파일에서 include하면 둘 다 정의하는 `sensor_t` 타입이 충돌해서 별도 파일로 뺐습니다),
  기본 10초 주기(`ENV_POLL_INTERVAL_MS`)로 읽어 door_open과 함께 `/sensors`로 보고합니다.
  주소는 0x76/0x77을 자동으로 둘 다 시도합니다.
