// Local Inference Demo - Placeholder for Edge Impulse model
// This is a demo version that shows the inference workflow
// Replace the "run_classifier" call with actual Edge Impulse library

#include <WiFi.h>
#include <WebServer.h>
#include "esp_camera.h"

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

WebServer server(80);
int captureCount = 0;

// Simple placeholder inference function
String run_demo_inference() {
  captureCount++;
  if (captureCount % 3 == 0) return "mugy";
  if (captureCount % 3 == 1) return "unknown";
  return "analyzing";
}

static const char PAGE[] PROGMEM = R"HTML(
<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>XIAO Live Inference Demo</title>
<style>
body{font-family:sans-serif;background:#111;color:#eee;text-align:center;margin:0;padding:16px}
img{width:320px;height:320px;object-fit:cover;border-radius:8px;display:block;margin:10px auto}
#result{font-size:24px;font-weight:bold;margin:10px 0;padding:15px;background:#222;border-radius:8px}
.demo-note{color:#ff9f43;font-size:14px;margin:20px 0;padding:15px;background:#333;border-radius:8px}
</style></head><body>
<h2>🔍 XIAO 추론 데모</h2>
<img id="cam" src="/jpg">
<div id="result">분석 중...</div>
<div class="demo-note">
  <b>⚠️ 데모 모드</b><br>
  Edge Impulse 라이브러리가 필요합니다.<br>
  훈련된 모델로 실제 추론을 하려면:<br>
  1. Edge Impulse에서 모델 훈련<br>
  2. Arduino 라이브러리 다운로드<br>
  3. 코드에 라이브러리 추가
</div>
<script>
setInterval(()=>{fetch('/classify').then(r=>r.json()).then(d=>{
  document.getElementById('result').textContent=d.label+' ('+(d.confidence*100).toFixed(0)+'%)';
})},500);
setInterval(()=>{cam.src='/jpg?t='+Date.now()},800);
</script></body></html>
)HTML";

void handleRoot() { server.send_P(200, "text/html", PAGE); }

void handleJpg() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) { server.send(503, "text/plain", "no frame"); return; }
  uint8_t *jpg = NULL; size_t jpgLen = 0;
  bool ok = frame2jpg(fb, 85, &jpg, &jpgLen);
  esp_camera_fb_return(fb);
  if (!ok) { server.send(500, "text/plain", "jpeg failed"); return; }
  server.setContentLength(jpgLen);
  server.send(200, "image/jpeg", "");
  server.client().write(jpg, jpgLen);
  free(jpg);
}

void handleClassify() {
  String label = run_demo_inference();
  float confidence = 0.5 + (captureCount % 10) * 0.05;
  String json = "{\"label\":\"" + label + "\",\"confidence\":" + String(confidence, 3) + "}";
  server.send(200, "application/json", json);
}

void setup() {
  Serial.begin(115200);
  delay(2000);

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
  config.frame_size = FRAMESIZE_240X240;
  config.pixel_format = PIXFORMAT_RGB565;
  config.grab_mode = CAMERA_GRAB_LATEST;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.fb_count = 2;

  if (esp_camera_init(&config) != ESP_OK) {
    Serial.println("Camera init failed");
    while (true) delay(1000);
  }
  for (int i = 0; i < 10; i++) { camera_fb_t *w = esp_camera_fb_get(); if (w) esp_camera_fb_return(w); delay(60); }

  WiFi.mode(WIFI_AP);
  WiFi.softAP("ESP32_CAMERA_AP", "ie2026app", 1);
  Serial.print("AP started. Open http://");
  Serial.println(WiFi.softAPIP());

  server.on("/", handleRoot);
  server.on("/jpg", handleJpg);
  server.on("/classify", handleClassify);
  server.begin();
  Serial.println("Demo inference ready");
}

void loop() { server.handleClient(); }
