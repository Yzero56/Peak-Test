/*
 * webcam_ap_capture.ino — camera_capture.ino의 검증된 카메라 코어를
 * 시리얼 대신 WiFi AP + HTTP로 노출한 버전.
 *
 * 목적: ESP32를 노트북 USB에서 완전히 떼어(보조배터리 전원) 자유롭게
 * 들고 다니며 데이터셋을 찍기 위함. 노트북은 이 보드가 띄우는 핫스팟
 * (FridgeCam / FridgeCamTest — 우리가 직접 정한 값이라 개인정보 아님)에
 * 붙어서 tools/web_capture/server.py가 시리얼 대신 HTTP로 통신한다.
 *
 * 카메라 설정(해상도 SVGA 고정, 화질만 프리셋으로 전환, 유휴 시 프레임
 * 드레인)은 camera_capture.ino에서 여러 번의 실패 끝에 검증한 것과 동일 —
 * 이유는 그 파일의 주석 참고. 여기서 새로 바꾼 건 전송 계층(시리얼→HTTP)뿐.
 *
 * 라우트:
 *   GET /preview            — 저장 안 하는 빠른 미리보기 프레임
 *   GET /capture?quality=fast|standard|high — 저장용 촬영, 화질 프리셋 선택
 */

#include <WiFi.h>
#include <WebServer.h>
#include "esp_camera.h"

// XIAO ESP32S3 Sense 핀맵
#define PWDN_GPIO_NUM  -1
#define RESET_GPIO_NUM -1
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

// 리드스위치(도어 감지, NO타입) — D0(GPIO1)에 배선함 (ESP32S3.md Sense pin map 기준).
// NO타입: 문 닫힘(자석 붙음)=회로 연결=LOW, 문 열림(자석 떨어짐)=회로 끊김=HIGH.
#define REED_SWITCH_PIN 1

// 조명 LED — D1(GPIO2)에 배선함. 문 열려있는 동안 켜서 안쪽을 비춘다.
#define LED_PIN 2

static const framesize_t FIXED_FRAMESIZE = FRAMESIZE_SVGA; // 800x600, 절대 안 바꿈
static const int PREVIEW_QUALITY = 16;
static const int CAPTURE_QUALITY_FAST = 18;
static const int CAPTURE_QUALITY_STANDARD = 12;
static const int CAPTURE_QUALITY_HIGH = 6;

WebServer server(80);
static bool cameraReady = false;
static sensor_t *sensor = nullptr;
static int currentQuality = -1;

bool initCameraOnce() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;   config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM; config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM; config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM; config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.grab_mode = CAMERA_GRAB_LATEST;

  bool hasPsram = psramFound();
  config.frame_size = hasPsram ? FIXED_FRAMESIZE : FRAMESIZE_CIF;
  config.jpeg_quality = PREVIEW_QUALITY;
  config.fb_count = hasPsram ? 2 : 1;
  config.fb_location = hasPsram ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;

  if (esp_camera_init(&config) != ESP_OK) {
    Serial.println("Camera init failed");
    return false;
  }

  sensor = esp_camera_sensor_get();
  if (sensor && sensor->id.PID == OV3660_PID) {
    sensor->set_vflip(sensor, 1);
    sensor->set_hmirror(sensor, 0);
  }

  // 냉장고/냉동고 내부의 흰색 반사면 때문에 기본 자동노출(AEC)이 화면 전체를
  // 하얗게 날려버리는 문제 대응. aec2(고대비 장면에 강한 DSP AEC 모드) 켜고,
  // 노출 타겟을 어둡게 눌러서 밝은 면이 있어도 덜 날아가게 한다.
  if (sensor) {
    sensor->set_aec2(sensor, 1);
    sensor->set_ae_level(sensor, -2);   // -2~2, 낮을수록 어둡게 노출
    sensor->set_gainceiling(sensor, GAINCEILING_4X); // 게인 과다로 밝아지는 것도 제한
  }

  currentQuality = config.jpeg_quality;
  return true;
}

// FPC 케이블 접촉 불량이나 전원이 순간 불안정할 때 esp_camera_init()이
// 간헐적으로 실패하는 걸 겪었다(하드웨어 연결은 멀쩡한데도) — 한 번 실패했다고
// 바로 포기하지 않고 잠깐 쉬었다 몇 번 더 시도한다.
bool initCamera() {
  const int MAX_ATTEMPTS = 4;
  for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    if (initCameraOnce()) {
      if (attempt > 1) Serial.printf("INFO camera init succeeded on attempt %d\n", attempt);
      return true;
    }
    Serial.printf("WARN camera init attempt %d/%d failed, retrying...\n", attempt, MAX_ATTEMPTS);
    esp_camera_deinit();  // 실패한 상태 정리하고 재시도 (안전하게 무시 가능한 반환값)
    delay(300);
  }
  return false;
}

void setQuality(int quality) {
  if (quality == currentQuality) return;
  sensor->set_quality(sensor, quality);
  currentQuality = quality;
}

void sendFrame(int quality) {
  if (!cameraReady) {
    server.send(503, "text/plain", "camera not ready");
    return;
  }
  setQuality(quality);
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    server.send(503, "text/plain", "capture failed");
    return;
  }
  server.setContentLength(fb->len);
  server.send(200, "image/jpeg", "");
  server.client().write(fb->buf, fb->len);
  esp_camera_fb_return(fb);
}

void handlePreview() { sendFrame(PREVIEW_QUALITY); }

void handleCapture() {
  int quality = CAPTURE_QUALITY_STANDARD;
  if (server.hasArg("quality")) {
    String q = server.arg("quality");
    if (q == "fast") quality = CAPTURE_QUALITY_FAST;
    else if (q == "high") quality = CAPTURE_QUALITY_HIGH;
    else quality = CAPTURE_QUALITY_STANDARD;
  }
  sendFrame(quality);
}

void handleRoot() {
  server.send(200, "text/plain", cameraReady ? "FridgeCam capture node ready" : "camera not ready");
}

bool isDoorOpen() {
  return digitalRead(REED_SWITCH_PIN) == HIGH;  // NO타입: 닫힘=LOW, 열림(또는 미배선)=HIGH
}

void handleDoor() {
  String json = String("{\"open\":") + (isDoorOpen() ? "true" : "false") + "}";
  server.send(200, "application/json", json);
}

void setup() {
  // 발열 대책 1: 기본 240MHz는 이 보드(카메라+WiFi AP 상시 구동)엔 과함.
  // 160MHz로도 HTTP 응답 속도 체감 차이 없이 충분하다. Serial.begin 전에
  // 걸어야 보레이트가 새 클럭 기준으로 맞게 설정된다.
  setCpuFrequencyMhz(160);

  pinMode(REED_SWITCH_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  Serial.begin(115200);
  unsigned long t0 = millis();
  while (!Serial && millis() - t0 < 3000) { delay(10); }

  cameraReady = initCamera();
  Serial.println(cameraReady ? "Camera ready" : "CAMERA_INIT_FAILED");

  WiFi.mode(WIFI_AP);
  WiFi.softAP("FridgeCam", "FridgeCamTest", 1);
  // 발열 잡으려고 송신출력을 11dBm까지 낮췄더니 폰이 아예 못 잡을 만큼
  // 신호가 약해졌다 — 발열의 진짜 원인은 busy-loop(아래 loop() 참고)였고
  // 이건 부수적인 조치였으니, 연결 안정성 우선으로 기본값(최대)으로 되돌린다.
  Serial.print("AP started. Open http://");
  Serial.println(WiFi.softAPIP());

  server.on("/", handleRoot);
  server.on("/preview", handlePreview);
  server.on("/capture", handleCapture);
  server.on("/door", handleDoor);
  server.begin();
  Serial.println("HTTP capture server ready");
}

void loop() {
  server.handleClient();

  // 문 열림 동안만 LED 점등 — 상태가 바뀔 때만 씀(digitalWrite 매 루프 호출 안 함)
  static bool lastDoorOpen = false;
  bool doorOpen = isDoorOpen();
  if (doorOpen != lastDoorOpen) {
    digitalWrite(LED_PIN, doorOpen ? HIGH : LOW);
    lastDoorOpen = doorOpen;
  }

  // 발열 대책 3(핵심): 예전엔 이 유휴 드레인을 매 loop() 마다, 즉 딜레이
  // 하나 없이 초당 수천 번씩 돌려서 카메라가 쉬지 않고 계속 새 프레임을
  // 찍고 JPEG 인코딩까지 하고 있었다 — 이게 발열의 제일 큰 원인이었다.
  // FB-OVF 안전망 목적은 유지하되, 250ms에 한 번씩만 비우도록 스로틀링한다.
  static unsigned long lastDrain = 0;
  if (cameraReady && millis() - lastDrain > 250) {
    lastDrain = millis();
    camera_fb_t *fb = esp_camera_fb_get();
    if (fb) esp_camera_fb_return(fb);
  }
}
