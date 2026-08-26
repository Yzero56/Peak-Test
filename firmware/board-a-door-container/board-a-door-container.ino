// Board A — 문 감지 + 용기 인식 통합 보드
//
// 팀 통합 결정(2026-08-26): 실제 시연에서 리드스위치(문 감지, Part1/YJ)와
// 용기 인식용 카메라(Part2/Wa)를 물리적으로 같은 보드 하나로 운용하기로 함.
// 이 스케치는 그 통합 보드용 최종본으로, 기존 3개 프로토타입을 대체한다:
//   - part1-inout/firmware/reed_switch_test        (리드스위치 단독 테스트)
//   - part1-inout/firmware/webcam_ap_collect        (카메라 단독, 리드스위치 없음)
//   - part2-container/01_container_collector        (카메라 단독, 용기 인식용 /jpg)
//
// 설계: 카메라는 /jpg 스냅샷 하나만 제공하고(YJ·Wa 두 파이썬 클라이언트가 각자
// 자기 페이스로 폴링 — 실제로 기존 두 스케치가 이미 동일한 /jpg 계약을 썼기
// 때문에 두 클라이언트 모두 코드 수정 없이 이 보드 하나에 붙을 수 있다),
// 리드스위치 상태는 새로 추가한 /reed 로 노출해서 파이썬 쪽에서 문 열림/닫힘
// 세션을 판단할 수 있게 한다(기존에는 시리얼 직결이었지만, 이제 보드가 Wi-Fi로
// 두 클라이언트를 동시에 상대해야 하므로 HTTP로 전환).
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

WebServer server(80);

bool doorClosed = false;       // true = 닫힘(자석 감지)
bool reedCandidate = false;
uint32_t reedCandidateSince = 0;
uint32_t doorChangedAt = 0;

// ---- 카메라 스냅샷: 기존 두 프로토타입과 동일한 계약(GET /jpg -> image/jpeg) ----
void handleJpg() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) { server.send(503, "text/plain", "capture failed"); return; }
  uint8_t *jpg = NULL; size_t jpgLen = 0;
  bool ok = frame2jpg(fb, 85, &jpg, &jpgLen);
  esp_camera_fb_return(fb);
  if (!ok) { server.send(500, "text/plain", "jpeg failed"); return; }
  server.setContentLength(jpgLen);
  server.send(200, "image/jpeg", "");
  server.client().write(jpg, jpgLen);
  free(jpg);
}

// ---- 리드스위치 상태: Part1 파이썬 쪽에서 문 열림/닫힘 세션 판단용(신규) ----
void handleReed() {
  char buf[96];
  snprintf(buf, sizeof(buf),
    "{\"door_closed\":%s,\"since_ms\":%lu}",
    doorClosed ? "true" : "false",
    (unsigned long)(millis() - doorChangedAt));
  server.send(200, "application/json", buf);
}

void handleRoot() {
  server.send(200, "text/plain", "board-a-door-container: GET /jpg (snapshot), GET /reed (door state)");
}

void pollReed() {
  bool reading = (digitalRead(REED_PIN) == LOW);
  if (reading != reedCandidate) {
    reedCandidate = reading;
    reedCandidateSince = millis();
  }
  if (reedCandidate != doorClosed && millis() - reedCandidateSince > REED_DEBOUNCE_MS) {
    doorClosed = reedCandidate;
    doorChangedAt = millis();
    digitalWrite(LED_PIN, doorClosed ? LOW : HIGH);  // 문 열림일 때 LED ON(눈으로 확인용)
    Serial.printf("[%lu ms] door -> %s\n", millis(), doorClosed ? "closed" : "open");
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
  doorClosed = (digitalRead(REED_PIN) == LOW);
  digitalWrite(LED_PIN, doorClosed ? LOW : HIGH);
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
  config.frame_size = FRAMESIZE_VGA;      // 용기 인식(YOLO-World)에 여유있는 해상도 —
                                           // Part1 diff 인코딩 쪽은 파이썬에서 필요시 축소
  config.pixel_format = PIXFORMAT_JPEG;
  config.jpeg_quality = 12;
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
  server.on("/jpg", handleJpg);
  server.on("/reed", handleReed);
  server.begin();
  Serial.println("board-a-door-container ready");
}

void loop() {
  server.handleClient();
  pollReed();
  delay(5);
}
