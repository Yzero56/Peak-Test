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
// 준비물:
//   - Arduino IDE의 "esp32 by Espressif Systems" 보드 패키지 설치
//   - 보드: "XIAO_ESP32S3" 선택 후 Tools > PSRAM: "OPI PSRAM"으로 설정
//   - secrets.h.example을 secrets.h로 복사해 Wi-Fi/기기 토큰/백엔드 주소 채우기
// 자세한 절차는 firmware/xiao-esp32s3-cam/README.md 참고.

#include "esp_camera.h"
#include "esp_http_server.h"
#include <WiFi.h>
#include <HTTPClient.h>

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

static const char *STREAM_BOUNDARY = "frame";
static const char *STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=frame";
static const char *STREAM_PART_HEADER = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

httpd_handle_t camServer = NULL;     // 포트 80 — /capture (짧은 요청)
httpd_handle_t streamServer = NULL;  // 포트 81 — /stream (연결이 계속 열려있음)
unsigned long lastHeartbeatAt = 0;

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
  camera_fb_t *fb = esp_camera_fb_get();
  if (fb == nullptr) {
    httpd_resp_send_500(req);
    return ESP_FAIL;
  }
  httpd_resp_set_type(req, "image/jpeg");
  esp_err_t res = httpd_resp_send(req, (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return res;
}

// GET /stream — MJPEG 라이브 스트림 (multipart/x-mixed-replace)
static esp_err_t streamHandler(httpd_req_t *req) {
  esp_err_t res = httpd_resp_set_type(req, STREAM_CONTENT_TYPE);
  if (res != ESP_OK) return res;

  char partHeader[64];
  while (true) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (fb == nullptr) {
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

  if (!initCamera()) {
    Serial.println("[cam] 카메라 초기화 실패 — 배선/보드 설정을 확인하세요");
  }

  connectWiFi();
  startCameraServer();
}

void loop() {
  connectWiFi();

  if (millis() - lastHeartbeatAt >= HEARTBEAT_INTERVAL_MS) {
    lastHeartbeatAt = millis();
    sendHeartbeat();
  }
}
