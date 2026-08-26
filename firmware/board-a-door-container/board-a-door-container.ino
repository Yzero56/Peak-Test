// Board A — 문 감지 + 용기 인식 통합 보드
//
// 팀 통합 결정(2026-08-26): 실제 시연에서 리드스위치(문 감지, Part1/YJ)와
// 용기 인식용 카메라(Part2/Wa)를 물리적으로 같은 보드 하나로 운용하기로 함.
//
// [중요 정정] 이 스케치는 처음에 /jpg + /reed 라는 새로 지어낸 엔드포인트로
// 작성됐었는데, 그건 틀렸다 — YJ는 이미 리드스위치+카메라를 한 보드에서 같이
// 써왔고(실제 펌웨어 webcam_ap_capture.ino, Wi-Fi 비밀번호 때문에 git에는 없음),
// 그 결과로 튜닝된 실측 파이프라인이 part1-inout/tools/inout_classifier/server.py에
// 그대로 살아있다. 그 스크립트가 실제로 요청하는 계약은:
//   GET /door                      -> {"open": bool}
//   GET /capture?quality=standard  -> JPEG (800x600, quality=12 — 학습 데이터와
//                                     동일한 압축률이어야 함. 다르면 오분류 편향
//                                     생김 — server.py의 fetch_preview_frame() 주석 참고)
//   GET /preview                   -> JPEG (항상 quality=16, 라이브 뷰용 저부담 버전)
// 이 스케치는 그 계약을 그대로 구현한다(추측 아님 — 파이썬 클라이언트 코드에서
// 그대로 가져온 값). 여기에 Wa의 기존 계약 GET /jpg(용기 인식 스크립트가 그대로
// 쓰는 것)를 추가해서, 두 파이썬 클라이언트 다 코드 수정 없이 이 보드 하나에
// 동시에 붙을 수 있게 한다.
//
// Wi-Fi: secrets.h.example을 secrets.h로 복사해서 채울 것 (git에 커밋되지 않음).
// STA(WIFI_STA_SSID)를 채우면 시연장 공유 와이파이에 합류하고, 비워두거나
// 접속 실패 시 자체 핫스팟(AP, 기본 SSID "FridgeCam")으로 자동 폴백한다.
// mDNS로 http://fridgecam.local/ 로도 접속 가능(STA 모드일 때).
//
// 배선:
//   D0 (GPIO1) — 리드스위치 한쪽 다리, 반대쪽 다리는 GND (INPUT_PULLUP, LOW=닫힘)
//   D1 (GPIO2) — 상태 LED(선택, 문 열림 표시)
//
// 보드: XIAO ESP32-S3 Sense + OV3660 (Tools > PSRAM: OPI PSRAM)
//
// ⚠ 검증 필요: 리드스위치(D0)와 카메라를 "이 스케치 코드 형태로" 동시에 쓰는 건
// 처음이다(원본 webcam_ap_capture.ino의 실제 GPIO 배선이 여기와 100% 같다는
// 보장이 없음 — 그 파일 자체를 볼 수 없어서 reed_switch_test.ino의 D0/D1 배선을
// 그대로 가져온 것). 업로드 후 시리얼 모니터로 door 상태 로그와 /capture,
// /preview, /jpg 응답을 실제로 확인할 것.

#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include "esp_camera.h"
#include "secrets.h"

#define XCLK_GPIO_NUM  10
#define SIOD_GPIO_NUM  40
#define SIOC_GPIO_NUM  39
#define Y9_GPIO_NUM    48
#define Y8_GPIO_NUM    11
#define Y7_GPIO_NUM    12
#define Y6_GPIO_NUM    14
#define Y5_GPIO_NUM    16
#define Y4_GPIO_NUM    18
#define Y3_GPIO_NUM    17
#define Y2_GPIO_NUM    15
#define VSYNC_GPIO_NUM 38
#define HREF_GPIO_NUM  47
#define PCLK_GPIO_NUM  13

#define REED_PIN D0
#define LED_PIN  D1
#define REED_DEBOUNCE_MS 20

// tools/web_capture/serial_cam.py QUALITY_PRESETS와 server.py의 실측 코멘트를
// 그대로 반영한 값 — 바꾸지 말 것(바꾸면 학습 데이터와 압축률이 달라져서
// 정확도가 실측된 76.1%에서 벗어난다).
#define JPEG_QUALITY_STANDARD 12
#define JPEG_QUALITY_FAST     20
#define JPEG_QUALITY_HIGH     8
#define JPEG_QUALITY_PREVIEW  16

WebServer server(80);

bool doorOpen = true;           // true = 열림(리드스위치 미감지)
bool reedCandidate = true;
uint32_t reedCandidateSince = 0;
uint32_t doorChangedAt = 0;

// esp_camera_fb_get()으로 받은 프레임을 지정한 JPEG 품질로 즉시 서빙한다.
// PIXFORMAT_JPEG라 인코딩은 센서가 하고, 품질은 요청 직전에 set_quality()로
// 바꾼 뒤 새로 캡처한다(오래된 프레임 재활용 안 함 — 항상 "지금" 상태).
void serveCapture(int quality) {
  sensor_t *s = esp_camera_sensor_get();
  if (s) s->set_quality(s, quality);

  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) { server.send(503, "text/plain", "capture failed"); return; }
  server.setContentLength(fb->len);
  server.send(200, "image/jpeg", "");
  server.client().write(fb->buf, fb->len);
  esp_camera_fb_return(fb);
}

// GET /capture?quality=fast|standard|high — YJ tools/web_capture, tools/inout_classifier 계약
void handleCapture() {
  String q = server.hasArg("quality") ? server.arg("quality") : "standard";
  int quality = JPEG_QUALITY_STANDARD;
  if (q == "fast") quality = JPEG_QUALITY_FAST;
  else if (q == "high") quality = JPEG_QUALITY_HIGH;
  serveCapture(quality);
}

// GET /preview — 라이브 뷰용, 항상 고정 압축률(YJ 계약)
void handlePreview() {
  serveCapture(JPEG_QUALITY_PREVIEW);
}

// GET /jpg — Wa의 browser_container_realtime.py 등이 그대로 쓰는 계약
void handleJpg() {
  serveCapture(JPEG_QUALITY_STANDARD);
}

// GET /door — YJ tools/inout_classifier/server.py의 check_door()가 그대로 쓰는 계약
void handleDoor() {
  char buf[16];
  snprintf(buf, sizeof(buf), "{\"open\":%s}", doorOpen ? "true" : "false");
  server.send(200, "application/json", buf);
}

void handleRoot() {
  server.send(200, "text/plain", "board-a-door-container: GET /door, /capture?quality=, /preview, /jpg");
}

void pollReed() {
  bool reading = (digitalRead(REED_PIN) != LOW);  // true = 열림(자석 없음)
  if (reading != reedCandidate) {
    reedCandidate = reading;
    reedCandidateSince = millis();
  }
  if (reedCandidate != doorOpen && millis() - reedCandidateSince > REED_DEBOUNCE_MS) {
    doorOpen = reedCandidate;
    doorChangedAt = millis();
    digitalWrite(LED_PIN, doorOpen ? HIGH : LOW);  // 문 열림일 때 LED ON(눈으로 확인용)
    Serial.printf("[%lu ms] door -> %s\n", millis(), doorOpen ? "open" : "closed");
  }
}

void setupWiFi() {
  WiFi.mode(WIFI_AP_STA);

#ifdef WIFI_STA_SSID
  if (strlen(WIFI_STA_SSID) > 0) {
    WiFi.begin(WIFI_STA_SSID, WIFI_STA_PASSWORD);
    Serial.printf("STA 접속 시도: %s\n", WIFI_STA_SSID);
    uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < 8000) { delay(200); Serial.print("."); }
    Serial.println();
  }
#endif

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("STA 연결됨, IP: ");
    Serial.println(WiFi.localIP());
    if (MDNS.begin("fridgecam")) {
      Serial.println("mDNS: http://fridgecam.local/");
    }
  } else {
    Serial.println("STA 실패(또는 미설정) -> AP 핫스팟 폴백");
  }

  // STA 성공 여부와 무관하게 AP도 항상 켜둔다 — 노트북이 시연장 와이파이에
  // 못 붙는 비상 상황에서도 보드에 직접 붙어 디버그할 수 있도록.
  WiFi.softAP(AP_SSID, AP_PASSWORD, 1);
  Serial.print("AP: ");
  Serial.print(AP_SSID);
  Serial.print(" / IP: ");
  Serial.println(WiFi.softAPIP());
}

void setup() {
  Serial.begin(115200);
  uint32_t start = millis();
  while (!Serial && millis() - start < 3000) delay(10);

  pinMode(REED_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  doorOpen = (digitalRead(REED_PIN) != LOW);
  digitalWrite(LED_PIN, doorOpen ? HIGH : LOW);
  doorChangedAt = millis();

  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;   config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM; config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM; config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = -1; config.pin_reset = -1;
  config.xclk_freq_hz = 20000000;
  // 800x600(SVGA) — YJ의 학습 데이터·server.py 주석("해상도는 둘 다 800x600으로
  // 같고 압축률만 다르다")과 동일하게 맞춤. 임의로 바꾸면 안 됨.
  config.frame_size = FRAMESIZE_SVGA;
  config.pixel_format = PIXFORMAT_JPEG;
  config.jpeg_quality = JPEG_QUALITY_STANDARD;
  config.grab_mode = CAMERA_GRAB_LATEST;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.fb_count = 2;

  if (esp_camera_init(&config) != ESP_OK) {
    Serial.println("Camera init failed");
    while (true) delay(1000);
  }

  // OV3660 방향 보정 (YJ 프로토타입에서 검증된 값)
  sensor_t *s = esp_camera_sensor_get();
  if (s && s->id.PID == OV3660_PID) {
    s->set_vflip(s, 1);
    s->set_hmirror(s, 0);
  }

  for (int i = 0; i < 10; i++) { camera_fb_t *w = esp_camera_fb_get(); if (w) esp_camera_fb_return(w); delay(60); }

  setupWiFi();

  server.on("/", handleRoot);
  server.on("/door", handleDoor);
  server.on("/capture", handleCapture);
  server.on("/preview", handlePreview);
  server.on("/jpg", handleJpg);
  server.begin();
  Serial.println("board-a-door-container ready");
}

void loop() {
  server.handleClient();
  pollReed();
  delay(5);
}
