// XIAO ESP32-S3 Sense — Wi-Fi 카메라 캡처 업로더
//
// 배선/시리얼 케이블 없이, 보드가 자체 Wi-Fi로 백엔드(FastAPI)에 직접 접속해
// 주기적으로 사진을 찍어 POST /api/devices/{DEVICE_ID}/captures 로 업로드한다.
// 시리얼(115200)은 디버그 로그 출력용일 뿐, 데이터 전송 경로가 아니다.
//
// 준비물:
//   - Arduino IDE의 "esp32 by Espressif Systems" 보드 패키지 설치
//   - 보드: "XIAO_ESP32S3" 선택 후 Tools > PSRAM: "OPI PSRAM"으로 설정
//   - secrets.h.example을 secrets.h로 복사해 Wi-Fi/기기 토큰/백엔드 주소 채우기
// 자세한 절차는 firmware/xiao-esp32s3-cam/README.md 참고.

#include "esp_camera.h"
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

// 촬영 주기(ms). 필요에 맞게 조정.
#ifndef CAPTURE_INTERVAL_MS
#define CAPTURE_INTERVAL_MS 60000
#endif

static const char *UPLOAD_BOUNDARY = "----FridgeCamBoundary7d1c9";

unsigned long lastCaptureAt = 0;

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

  if (psramFound()) {
    config.frame_size = FRAMESIZE_UXGA;
    config.jpeg_quality = 10;
    config.fb_count = 2;
  } else {
    config.frame_size = FRAMESIZE_SVGA;
    config.jpeg_quality = 12;
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

bool uploadCapture(camera_fb_t *fb) {
  String head = String("--") + UPLOAD_BOUNDARY + "\r\n" +
                "Content-Disposition: form-data; name=\"file\"; filename=\"capture.jpg\"\r\n" +
                "Content-Type: image/jpeg\r\n\r\n";
  String tail = String("\r\n--") + UPLOAD_BOUNDARY + "--\r\n";

  size_t bodyLen = head.length() + fb->len + tail.length();
  uint8_t *body = (uint8_t *)malloc(bodyLen);
  if (body == nullptr) {
    Serial.println("[upload] 버퍼 할당 실패 (메모리 부족)");
    return false;
  }
  memcpy(body, head.c_str(), head.length());
  memcpy(body + head.length(), fb->buf, fb->len);
  memcpy(body + head.length() + fb->len, tail.c_str(), tail.length());

  HTTPClient http;
  String url = String(BACKEND_BASE_URL) + "/api/devices/" + DEVICE_ID + "/captures";
  http.begin(url);
  http.addHeader("X-Device-Token", DEVICE_TOKEN);
  http.addHeader("Content-Type", String("multipart/form-data; boundary=") + UPLOAD_BOUNDARY);

  int status = http.POST(body, bodyLen);
  if (status > 0) {
    Serial.printf("[upload] 응답 %d: %s\n", status, http.getString().c_str());
  } else {
    Serial.printf("[upload] 요청 실패: %s\n", http.errorToString(status).c_str());
  }

  http.end();
  free(body);
  return status == 201;
}

void captureAndUpload() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[cam] Wi-Fi 미연결, 촬영 건너뜀");
    return;
  }

  camera_fb_t *fb = esp_camera_fb_get();
  if (fb == nullptr) {
    Serial.println("[cam] 프레임 캡처 실패");
    return;
  }

  uploadCapture(fb);
  esp_camera_fb_return(fb);
}

void setup() {
  Serial.begin(115200);
  delay(300);

  if (!initCamera()) {
    Serial.println("[cam] 카메라 초기화 실패 — 배선/보드 설정을 확인하세요");
  }

  connectWiFi();
}

void loop() {
  connectWiFi();

  if (millis() - lastCaptureAt >= CAPTURE_INTERVAL_MS) {
    lastCaptureAt = millis();
    captureAndUpload();
  }
}
