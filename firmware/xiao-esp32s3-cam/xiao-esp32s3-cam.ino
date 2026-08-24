// XIAO ESP32-S3 Sense — Wi-Fi 라이브 카메라 서버
//
// 사진을 찍어 백엔드에 계속 쌓아두는 대신, 보드가 자체 Wi-Fi로 HTTP 서버를 열어
// 실시간 라이브 뷰(/stream)와 정지 프레임(/capture)을 직접 서빙한다.
// 백엔드는 "지금 스캔하기"를 누른 순간에만 /capture를 가져가 인식하고,
// 대시보드는 /stream을 <img>로 그대로 띄워 라이브 영상을 보여준다.
// 이 서버에는 별도 인증이 없다 — 같은 Wi-Fi(LAN)에 있으면 누구나 접근 가능하니
// 로컬 데모 범위로만 사용할 것.
//
// 보드는 주기적으로 백엔드에 "하트비트"만 보낸다(사진 없음) — 이걸로 백엔드가
// last_seen_at과 자신의 IP를 기억해서 대시보드가 /stream, /capture 주소를 알 수 있다.
//
// 리드스위치(D10/GPIO9)로 문 개폐를 감지해 /api/devices/{id}/sensors로
// door_open 값을 보고한다. 백엔드는 door_open=true를 받으면 자동 스캔 루프를
// 시작하고(문이 열려있는 동안 몇 초 간격으로 /capture를 가져가 인식), false를
// 받으면 멈춘다 — 즉 "실시간 탐지 on/off"는 이 door_open 신호로 제어된다.
//
// 문이 닫히면(=실시간 탐지 off) 전력 절약을 위해 카메라 자체도 esp_camera_deinit()으로
// 꺼버리고, 문이 열리면 다시 esp_camera_init()으로 켠다. XIAO ESP32-S3 Sense는
// 카메라 PWDN 핀이 배선되어 있지 않아(PWDN_GPIO_NUM = -1) 완전한 전원 차단은 아니고
// 클럭(XCLK)·DMA 등 소프트웨어 레벨에서 끄는 것이다. 카메라가 꺼져있는 동안
// /capture, /stream은 503을 응답한다(HTTP 서버 자체는 계속 떠 있음).
//
// 준비물:
//   - Arduino IDE의 "esp32 by Espressif Systems" 보드 패키지 설치
//   - 보드: "XIAO_ESP32S3" 선택 후 Tools > PSRAM: "OPI PSRAM"으로 설정
//   - secrets.h.example을 secrets.h로 복사해 Wi-Fi/기기 토큰/백엔드 주소 채우기
// 자세한 절차는 firmware/xiao-esp32s3-cam/README.md 참고.

#include "esp_camera.h"
#include "esp_http_server.h"
#include <WiFi.h>
#include <HTTPClient.h>

// BME680 관련 코드(Wire.h, Adafruit_BME680.h)는 bme680_sensor.cpp로 분리되어 있다.
// esp_camera.h와 Adafruit_Sensor.h를 같은 번역 단위에서 include하면 둘 다 정의하는
// sensor_t 타입 이름이 충돌해서 컴파일이 깨지기 때문 — 원시 타입만 노출하는
// 이 헤더를 통해서만 접근한다.
#include "bme680_sensor.h"

#include "secrets.h"

// ===== XIAO ESP32-S3 Sense 카메라(OV2640) 핀맵 =====
#define PWDN_GPIO_NUM -1
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 10
#define SIOD_GPIO_NUM 40
#define SIOC_GPIO_NUM 39
#define Y9_GPIO_NUM 48
#define Y8_GPIO_NUM 11
#define Y7_GPIO_NUM 12
#define Y6_GPIO_NUM 14
#define Y5_GPIO_NUM 16
#define Y4_GPIO_NUM 18
#define Y3_GPIO_NUM 17
#define Y2_GPIO_NUM 15
#define VSYNC_GPIO_NUM 38
#define HREF_GPIO_NUM 47
#define PCLK_GPIO_NUM 13

// 하트비트 주기(ms).
#ifndef HEARTBEAT_INTERVAL_MS
#define HEARTBEAT_INTERVAL_MS 15000
#endif

// ===== 리드스위치 (도어 센서) =====
// D10 = GPIO9. 카메라가 GPIO 10~18/38~40/47/48을 이미 쓰고 있어서 D10을 사용.
// 배선: 한쪽 핀을 D10, 다른 쪽을 GND에 연결하고 INPUT_PULLUP을 쓴다.
// 리드스위치가 붙어있으면(자력으로 접점이 붙어 회로가 닫힘) GND로 끌려가
// LOW = 문 닫힘. 떨어지면(접점 개방) 풀업으로 HIGH = 문 열림.
#define REED_GPIO_NUM 9
#ifndef DOOR_POLL_INTERVAL_MS
#define DOOR_POLL_INTERVAL_MS 300
#endif
#ifndef DOOR_DEBOUNCE_MS
#define DOOR_DEBOUNCE_MS 150
#endif

// ===== BME680 온습도/가스 센서 (I2C) =====
// XIAO ESP32-S3 Sense의 보드 라벨 SDA/SCL 핀(D4=GPIO5, D5=GPIO6, 보드 기본 Wire 핀)에
// 그대로 연결했다고 가정 — Wire.begin()에 핀을 안 넘기면 보드 변형(variant) 기본값을 쓴다.
// 주소는 SDO 핀 상태에 따라 0x76(LOW, 기본) 또는 0x77(HIGH)이라 둘 다 시도한다.
#ifndef ENV_POLL_INTERVAL_MS
#define ENV_POLL_INTERVAL_MS 10000
#endif

static const char *STREAM_BOUNDARY = "frame";
static const char *STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=frame";
static const char *STREAM_PART_HEADER = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

httpd_handle_t camServer = NULL;     // 포트 80 — /capture (짧은 요청)
httpd_handle_t streamServer = NULL;  // 포트 81 — /stream (연결이 계속 열려있음)
unsigned long lastHeartbeatAt = 0;

bool doorOpen = false;
bool doorStateKnown = false;
bool doorRawLast = false;
unsigned long doorStableSince = 0;
unsigned long lastDoorPollAt = 0;

bool envSensorReady = false;
bool envReadingValid = false;
float lastTemperatureC = 0;
float lastHumidityPct = 0;
float lastGasResistanceOhm = 0;
unsigned long lastEnvPollAt = 0;

// 카메라 전원 상태. deinit/init을 캡처·스트림 핸들러의 esp_camera_fb_get()과
// 동시에 호출하면 드라이버 내부 상태가 깨질 수 있어 뮤텍스로 직렬화한다.
volatile bool cameraActive = false;
SemaphoreHandle_t cameraMutex = nullptr;

bool initCamera() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // 라이브 스트리밍이 매끄럽도록 정지 캡처보다 낮은 해상도를 기본값으로 사용.
  if (psramFound()) {
    config.frame_size = FRAMESIZE_SVGA;  // 800x600
    config.jpeg_quality = 12;
    config.fb_count = 2;
  } else {
    config.frame_size = FRAMESIZE_VGA;  // 640x480
    config.jpeg_quality = 14;
    config.fb_count = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[cam] 초기화 실패: 0x%x\n", err);
    return false;
  }
  return true;
}

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.printf("[wifi] 연결 시도: %s\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[wifi] 연결됨, IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n[wifi] 연결 실패, 다음 루프에서 재시도");
  }
}

// GET /capture — 정지 프레임 1장
static esp_err_t captureHandler(httpd_req_t *req) {
  if (!cameraActive) {
    httpd_resp_set_status(req, "503 Service Unavailable");
    httpd_resp_set_type(req, "text/plain");
    return httpd_resp_sendstr(req, "camera off (door closed)");
  }

  xSemaphoreTake(cameraMutex, portMAX_DELAY);
  camera_fb_t *fb = cameraActive ? esp_camera_fb_get() : nullptr;
  if (fb == nullptr) {
    xSemaphoreGive(cameraMutex);
    httpd_resp_send_500(req);
    return ESP_FAIL;
  }
  httpd_resp_set_type(req, "image/jpeg");
  esp_err_t res = httpd_resp_send(req, (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  xSemaphoreGive(cameraMutex);
  return res;
}

// GET /stream — MJPEG 라이브 스트림 (multipart/x-mixed-replace)
static esp_err_t streamHandler(httpd_req_t *req) {
  if (!cameraActive) {
    httpd_resp_set_status(req, "503 Service Unavailable");
    httpd_resp_set_type(req, "text/plain");
    return httpd_resp_sendstr(req, "camera off (door closed)");
  }

  esp_err_t res = httpd_resp_set_type(req, STREAM_CONTENT_TYPE);
  if (res != ESP_OK) return res;

  char partHeader[64];
  while (true) {
    if (!cameraActive) {
      // 스트리밍 도중 문이 닫혀 카메라가 꺼진 경우 — 연결을 정리하고 빠져나간다.
      res = ESP_FAIL;
      break;
    }

    xSemaphoreTake(cameraMutex, portMAX_DELAY);
    camera_fb_t *fb = cameraActive ? esp_camera_fb_get() : nullptr;
    if (fb == nullptr) {
      xSemaphoreGive(cameraMutex);
      res = ESP_FAIL;
      break;
    }

    String boundary = String("--") + STREAM_BOUNDARY + "\r\n";
    res = httpd_resp_send_chunk(req, boundary.c_str(), boundary.length());
    if (res == ESP_OK) {
      size_t hlen = snprintf(partHeader, sizeof(partHeader), STREAM_PART_HEADER, fb->len);
      res = httpd_resp_send_chunk(req, partHeader, hlen);
    }
    if (res == ESP_OK) {
      res = httpd_resp_send_chunk(req, (const char *)fb->buf, fb->len);
    }
    if (res == ESP_OK) {
      res = httpd_resp_send_chunk(req, "\r\n", 2);
    }

    esp_camera_fb_return(fb);
    xSemaphoreGive(cameraMutex);
    if (res != ESP_OK) break;
  }
  return res;
}

void startCameraServer() {
  // /stream 핸들러는 연결이 끊길 때까지 반복문에서 계속 프레임을 보내며 서버의
  // 요청 처리 태스크를 점유한다. 같은 서버에 /capture를 같이 두면 누군가 라이브
  // 영상을 보고 있는 동안 스캔 요청이 응답을 못 받는다 — 그래서 포트를 분리한다
  // (Espressif 공식 CameraWebServer 예제와 동일한 이유의 동일한 해결책).
  httpd_config_t camConfig = HTTPD_DEFAULT_CONFIG();
  camConfig.server_port = 80;
  camConfig.ctrl_port = 32768;
  httpd_uri_t captureUri = { "/capture", HTTP_GET, captureHandler, nullptr };
  if (httpd_start(&camServer, &camConfig) == ESP_OK) {
    httpd_register_uri_handler(camServer, &captureUri);
    Serial.println("[cam] /capture 서버 시작됨 (포트 80)");
  } else {
    Serial.println("[cam] /capture 서버 시작 실패");
  }

  httpd_config_t streamConfig = HTTPD_DEFAULT_CONFIG();
  streamConfig.server_port = 81;
  streamConfig.ctrl_port = 32769;
  httpd_uri_t streamUri = { "/stream", HTTP_GET, streamHandler, nullptr };
  if (httpd_start(&streamServer, &streamConfig) == ESP_OK) {
    httpd_register_uri_handler(streamServer, &streamUri);
    Serial.println("[cam] /stream 서버 시작됨 (포트 81)");
  } else {
    Serial.println("[cam] /stream 서버 시작 실패");
  }
}

// 문이 열릴 때 카메라를 켠다. 스트림/캡처 핸들러와 동시에 esp_camera_init()이
// 실행되지 않도록 뮤텍스로 보호한다.
void powerUpCamera() {
  if (cameraActive) return;
  xSemaphoreTake(cameraMutex, portMAX_DELAY);
  bool ok = initCamera();
  cameraActive = ok;
  xSemaphoreGive(cameraMutex);
  Serial.println(ok ? "[cam] 카메라 켬 (문 열림)" : "[cam] 카메라 재초기화 실패");
}

// 문이 닫힐 때 전력 절약을 위해 카메라를 끈다(클럭/DMA 해제, 완전한 전원 차단은 아님).
void powerDownCamera() {
  if (!cameraActive) return;
  xSemaphoreTake(cameraMutex, portMAX_DELAY);
  cameraActive = false;  // 새 fb_get 진입을 막은 뒤에 deinit
  esp_camera_deinit();
  xSemaphoreGive(cameraMutex);
  Serial.println("[cam] 전력 절약을 위해 카메라 끔 (문 닫힘)");
}

// door_open + (있으면) 최근 BME680 값을 한 번에 백엔드로 보고한다.
// 문 상태만 따로 보내면 그 사이 온습도/가스 값이 대시보드에서 "-"로 비어 보이므로,
// 알고 있는 최신값을 매번 같이 실어 보내 하나의 완전한 스냅샷으로 유지한다.
void reportSensors() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String url = String(BACKEND_BASE_URL) + "/api/devices/" + DEVICE_ID + "/sensors";
  http.begin(url);
  http.addHeader("X-Device-Token", DEVICE_TOKEN);
  http.addHeader("Content-Type", "application/json");

  String body = String("{\"door_open\":") + (doorOpen ? "true" : "false");
  if (envReadingValid) {
    body += ",\"temperature_c\":" + String(lastTemperatureC, 2);
    body += ",\"humidity_pct\":" + String(lastHumidityPct, 2);
    body += ",\"gas_resistance_ohm\":" + String(lastGasResistanceOhm, 0);
  }
  body += "}";

  int status = http.POST(body);
  if (status <= 0) {
    Serial.printf("[sensors] 전송 실패: %s\n", http.errorToString(status).c_str());
  } else {
    Serial.printf("[sensors] door=%s 보고됨 (HTTP %d)\n", doorOpen ? "열림" : "닫힘", status);
  }
  http.end();
}

// BME680 초기화(실제 구현은 bme680_sensor.cpp — 주소 0x76/0x77 자동 시도).
void initEnvSensor() {
  envSensorReady = bme680Init();
  Serial.println(envSensorReady ? "[env] BME680 초기화 완료" : "[env] BME680 초기화 실패 (배선/주소 확인 필요)");
}

// 주기적으로 BME680을 읽고, 값을 캐시해둔 뒤 door_open과 함께 보고한다.
void pollEnvSensor() {
  if (!envSensorReady) return;
  if (millis() - lastEnvPollAt < ENV_POLL_INTERVAL_MS) return;
  lastEnvPollAt = millis();

  if (!bme680Read(lastTemperatureC, lastHumidityPct, lastGasResistanceOhm)) {
    Serial.println("[env] BME680 읽기 실패");
    return;
  }
  envReadingValid = true;
  Serial.printf("[env] 온도 %.1f C, 습도 %.1f %%, 가스 %.0f ohm\n", lastTemperatureC, lastHumidityPct, lastGasResistanceOhm);
  reportSensors();
}

// 리드스위치를 주기적으로 읽고, 짧은 디바운스 뒤 상태가 실제로 바뀌었을 때만 보고한다.
void pollDoorSensor() {
  if (millis() - lastDoorPollAt < DOOR_POLL_INTERVAL_MS) return;
  lastDoorPollAt = millis();

  bool raw = digitalRead(REED_GPIO_NUM) == HIGH;  // HIGH = 자석 없음 = 문 열림
  if (raw != doorRawLast) {
    doorRawLast = raw;
    doorStableSince = millis();
  }
  if (millis() - doorStableSince < DOOR_DEBOUNCE_MS) return;

  if (!doorStateKnown || raw != doorOpen) {
    doorOpen = raw;
    doorStateKnown = true;
    if (doorOpen) {
      powerUpCamera();  // 백엔드가 바로 /capture를 당겨갈 수 있도록 보고 전에 켠다
      reportSensors();
    } else {
      reportSensors();  // 꺼짐 보고가 확실히 나간 뒤에 끈다
      powerDownCamera();
    }
  }
}

void sendHeartbeat() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String url = String(BACKEND_BASE_URL) + "/api/devices/" + DEVICE_ID + "/heartbeat";
  http.begin(url);
  http.addHeader("X-Device-Token", DEVICE_TOKEN);
  http.addHeader("Content-Type", "application/json");

  int status = http.POST("{}");
  if (status <= 0) {
    Serial.printf("[heartbeat] 요청 실패: %s\n", http.errorToString(status).c_str());
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  delay(300);

  cameraMutex = xSemaphoreCreateMutex();

  pinMode(REED_GPIO_NUM, INPUT_PULLUP);
  doorRawLast = digitalRead(REED_GPIO_NUM) == HIGH;
  doorStableSince = millis();

  initEnvSensor();

  // 카메라는 여기서 바로 켜지 않는다 — 곧이어 loop()의 첫 pollDoorSensor() 호출이
  // 실제 문 상태를 판정해서 powerUpCamera()/powerDownCamera()로 맞춰준다.
  connectWiFi();
  startCameraServer();
}

void loop() {
  connectWiFi();
  pollDoorSensor();
  pollEnvSensor();

  if (millis() - lastHeartbeatAt >= HEARTBEAT_INTERVAL_MS) {
    lastHeartbeatAt = millis();
    sendHeartbeat();
  }
}
