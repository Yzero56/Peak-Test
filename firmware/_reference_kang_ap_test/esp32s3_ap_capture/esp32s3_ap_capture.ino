#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <SD_MMC.h>
#include "esp_camera.h"

// Upload target: ESP32-S3 board connected as COM10.
// These pins are for the common ESP32-S3-EYE camera module.
// Change this block if your ESP32-S3 camera board uses another pin map.
#define PWDN_GPIO_NUM -1
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 15
#define SIOD_GPIO_NUM 4
#define SIOC_GPIO_NUM 5
#define Y9_GPIO_NUM 16
#define Y8_GPIO_NUM 17
#define Y7_GPIO_NUM 18
#define Y6_GPIO_NUM 12
#define Y5_GPIO_NUM 10
#define Y4_GPIO_NUM 8
#define Y3_GPIO_NUM 9
#define Y2_GPIO_NUM 11
#define VSYNC_GPIO_NUM 6
#define HREF_GPIO_NUM 7
#define PCLK_GPIO_NUM 13

const char *AP_SSID = "PEAK-CAMERA";
const char *AP_PASSWORD = "peakcamera";
const IPAddress AP_IP(192, 168, 4, 1);
const IPAddress AP_GATEWAY(192, 168, 4, 1);
const IPAddress AP_SUBNET(255, 255, 255, 0);

WebServer server(80);
bool cameraReady = false;
bool storageReady = false;

const char INDEX_HTML[] PROGMEM = R"HTML(
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>PEAK Camera Collector</title>
  <style>
    body { font-family: sans-serif; max-width: 720px; margin: 24px auto; padding: 0 16px; }
    img { width: 100%; max-height: 60vh; object-fit: contain; background: #222; }
    input, button { font-size: 1rem; padding: 10px; margin: 6px 4px 6px 0; }
    button { cursor: pointer; }
    #status { white-space: pre-wrap; min-height: 2em; }
  </style>
</head>
<body>
  <h1>PEAK Camera Collector</h1>
  <p>Connect to the device AP, enter a label, capture a preview, then save it to SD.</p>
  <input id="label" placeholder="food label, e.g. milk" value="unknown">
  <button onclick="capture()">Capture preview</button>
  <button onclick="save()">Save to SD</button>
  <p id="status"></p>
  <img id="preview" alt="Latest camera frame">
  <script>
    let latest = false;
    async function capture() {
      const response = await fetch('/capture?ts=' + Date.now());
      if (!response.ok) { document.querySelector('#status').textContent = await response.text(); return; }
      document.querySelector('#preview').src = URL.createObjectURL(await response.blob());
      latest = true;
      document.querySelector('#status').textContent = 'Preview captured.';
    }
    async function save() {
      if (!latest) await capture();
      const label = encodeURIComponent(document.querySelector('#label').value);
      const response = await fetch('/save?label=' + label, { method: 'POST' });
      document.querySelector('#status').textContent = await response.text();
    }
  </script>
</body>
</html>
)HTML";

bool initCamera() {
  camera_config_t config;
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
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_SVGA;
  config.jpeg_quality = 10;
  config.fb_count = psramFound() ? 2 : 1;
  config.grab_mode = CAMERA_GRAB_LATEST;

  esp_err_t result = esp_camera_init(&config);
  if (result != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", result);
    return false;
  }
  return true;
}

bool initStorage() {
  // 1-bit mode uses fewer pins and is suitable for data collection prototypes.
  if (!SD_MMC.begin("/sdcard", true)) {
    Serial.println("SD_MMC mount failed");
    return false;
  }
  if (SD_MMC.cardType() == CARD_NONE) {
    Serial.println("No SD card detected");
    return false;
  }
  return true;
}

String safeLabel(String label) {
  label.trim();
  if (label.length() == 0) label = "unknown";
  String safe;
  for (size_t i = 0; i < label.length(); ++i) {
    char c = label[i];
    if (isalnum(static_cast<unsigned char>(c)) || c == '_' || c == '-') safe += c;
    else if (c == ' ') safe += '_';
  }
  return safe.length() ? safe : "unknown";
}

String nextFilePath(const String &label) {
  String directory = "/dataset/" + label;
  if (!SD_MMC.exists("/dataset")) SD_MMC.mkdir("/dataset");
  if (!SD_MMC.exists(directory)) SD_MMC.mkdir(directory);

  for (unsigned long index = 1; index < 1000000; ++index) {
    char name[40];
    snprintf(name, sizeof(name), "/dataset/%s/img_%06lu.jpg", label.c_str(), index);
    if (!SD_MMC.exists(name)) return String(name);
  }
  return "";
}

camera_fb_t *captureFrame() {
  camera_fb_t *frame = esp_camera_fb_get();
  if (!frame) Serial.println("Camera capture failed");
  return frame;
}

void sendFrame(camera_fb_t *frame) {
  server.sendHeader("Content-Length", String(frame->len));
  server.send(200, "image/jpeg", "");
  server.client().write(frame->buf, frame->len);
}

void handleRoot() {
  server.send_P(200, "text/html", INDEX_HTML);
}

void handleCapture() {
  if (!cameraReady) {
    server.send(503, "text/plain", "Camera is not initialized. Check the camera pin map and serial log.");
    return;
  }
  camera_fb_t *frame = captureFrame();
  if (!frame) {
    server.send(503, "text/plain", "Camera capture failed");
    return;
  }
  sendFrame(frame);
  esp_camera_fb_return(frame);
}

void handleSave() {
  if (!cameraReady) {
    server.send(503, "text/plain", "Camera is not initialized. Check the camera pin map and serial log.");
    return;
  }
  if (!storageReady || !SD_MMC.cardSize()) {
    server.send(503, "text/plain", "SD card is not available");
    return;
  }

  String label = safeLabel(server.arg("label"));
  String path = nextFilePath(label);
  if (path.isEmpty()) {
    server.send(507, "text/plain", "No free filename");
    return;
  }

  camera_fb_t *frame = captureFrame();
  if (!frame) {
    server.send(503, "text/plain", "Camera capture failed");
    return;
  }

  File file = SD_MMC.open(path, FILE_WRITE);
  if (!file) {
    esp_camera_fb_return(frame);
    server.send(500, "text/plain", "Could not open SD file");
    return;
  }
  size_t frameLength = frame->len;
  size_t written = file.write(frame->buf, frameLength);
  file.close();
  esp_camera_fb_return(frame);

  if (written != frameLength) {
    server.send(500, "text/plain", "Incomplete SD write");
    return;
  }
  server.send(201, "text/plain", "Saved: " + path);
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\nPEAK ESP32-S3 AP camera collector");

  WiFi.mode(WIFI_AP);
  WiFi.softAPConfig(AP_IP, AP_GATEWAY, AP_SUBNET);
  bool apReady = WiFi.softAP(AP_SSID, AP_PASSWORD, 6, false, 4);

  // Start the AP before hardware initialization so pin-map errors remain diagnosable.
  cameraReady = initCamera();
  storageReady = initStorage();

  server.on("/", HTTP_GET, handleRoot);
  server.on("/capture", HTTP_GET, handleCapture);
  server.on("/save", HTTP_POST, handleSave);
  server.begin();

  Serial.printf("AP started: %s\n", apReady ? "yes" : "no");
  Serial.printf("AP SSID: %s\n", AP_SSID);
  Serial.printf("AP password: %s\n", AP_PASSWORD);
  Serial.printf("Open http://%s/\n", AP_IP.toString().c_str());
  Serial.printf("Camera ready: %s\n", cameraReady ? "yes" : "no");
  Serial.printf("Storage ready: %s\n", storageReady ? "yes" : "no");
}

void loop() {
  server.handleClient();
  delay(2);
}
