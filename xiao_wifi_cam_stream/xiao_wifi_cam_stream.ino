#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include "esp_camera.h"

// ============================================================================
// [사용자 설정] 공유기(WiFi) 정보 입력
// - 만약 15초 이내에 공유기 연결이 실패하면, 보드는 자동으로 자체 핫스팟(AP)을 실행합니다.
// ============================================================================
const char* ssid     = "YOUR_WIFI_SSID";       // 2.4GHz WiFi SSID
const char* password = "YOUR_WIFI_PASSWORD";   // WiFi Password
const char* mdnsName = "xiaostream";           // mDNS 호스트네임 (http://xiaostream.local 로 접속 가능)

// ============================================================================
// [하드웨어 정의] Seeed Studio XIAO ESP32-S3 Sense 카메라 핀 맵
// ============================================================================
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

// ============================================================================
// [Web UI HTML/JS] 스킬의 다크 테마 디자인 규격을 따르는 실시간 스트리밍 페이지
// ============================================================================
static const char STREAM_PAGE[] PROGMEM = R"HTML(
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>XIAO ESP32-S3 Camera Stream</title>
  <style>
    body {
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      background: #111;
      color: #eee;
      text-align: center;
      margin: 0;
      padding: 16px;
    }
    h2 {
      color: #4c8bf5;
      margin-bottom: 8px;
    }
    .container {
      max-width: 500px;
      margin: 0 auto;
      background: #1e1e1e;
      padding: 20px;
      border-radius: 12px;
      box-shadow: 0 4px 15px rgba(0,0,0,0.5);
    }
    #wrap {
      position: relative;
      display: inline-block;
      margin: 15px 0;
      background: #000;
      border-radius: 8px;
      overflow: hidden;
      border: 3px solid #333;
    }
    img {
      width: 320px;
      height: 320px;
      object-fit: cover;
      display: block;
    }
    .controls {
      display: flex;
      flex-direction: column;
      gap: 12px;
      margin-top: 15px;
      padding: 15px;
      background: #252525;
      border-radius: 8px;
    }
    .control-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    label {
      font-size: 14px;
      color: #aaa;
    }
    select, input[type="range"] {
      background: #333;
      color: #eee;
      border: 1px solid #444;
      padding: 6px 10px;
      border-radius: 6px;
      outline: none;
    }
    input[type="range"] {
      width: 150px;
      cursor: pointer;
    }
    .btn {
      background: #4c8bf5;
      color: #fff;
      border: none;
      padding: 10px 16px;
      font-size: 15px;
      font-weight: bold;
      border-radius: 6px;
      cursor: pointer;
      transition: background 0.2s;
    }
    .btn:hover {
      background: #357ae8;
    }
    .btn.stop {
      background: #e04c4c;
    }
    .btn.stop:hover {
      background: #c03939;
    }
    #status {
      font-size: 13px;
      color: #888;
      margin-top: 10px;
    }
    .badge {
      display: inline-block;
      padding: 3px 8px;
      background: #333;
      border-radius: 4px;
      font-size: 12px;
      color: #4cf58b;
      margin: 4px;
    }
  </style>
</head>
<body>
  <div class="container">
    <h2>📷 XIAO 실시간 스트림</h2>
    <div>
      <span class="badge" id="net-mode">연결 확인 중...</span>
      <span class="badge" id="resolution-badge">240x240</span>
    </div>

    <div id="wrap">
      <img id="cam" src="/jpg" alt="카메라 피드">
    </div>

    <div class="controls">
      <div class="control-row">
        <label for="res-select">해상도 설정</label>
        <select id="res-select" onchange="changeResolution()">
          <option value="240">240x240 (정사각형)</option>
          <option value="QVGA">QVGA (320x240)</option>
          <option value="VGA">VGA (640x480)</option>
          <option value="SVGA">SVGA (800x600)</option>
        </select>
      </div>

      <div class="control-row">
        <label for="speed-range">새로고침 간격: <span id="speed-val">100ms</span></label>
        <input type="range" id="speed-range" min="50" max="1000" step="50" value="100" oninput="updateSpeed()">
      </div>

      <div class="control-row" style="justify-content: center; margin-top: 5px;">
        <button id="stream-btn" class="btn" onclick="toggleStream()">스트림 중지</button>
      </div>
    </div>

    <div id="status">프레임 요청 대기 중...</div>
  </div>

  <script>
    let streamTimer = null;
    let streamInterval = 100;
    let isStreaming = true;
    let frameCount = 0;
    let lastTime = Date.now();

    // 네트워크 모드 및 IP 정보 감지
    fetch('/status')
      .then(r => r.json())
      .then(data => {
        document.getElementById('net-mode').textContent = data.ssid + ' (' + data.ip + ')';
        document.getElementById('res-select').value = data.resolution;
        document.getElementById('resolution-badge').textContent = data.resolution_str;
      })
      .catch(() => {
        document.getElementById('net-mode').textContent = '연결됨';
      });

    // 이미지 단일 프레임 불러오기 및 FPS 계산
    function fetchFrame() {
      if (!isStreaming) return;
      const startTime = Date.now();
      const img = document.getElementById('cam');
      
      // 캐시 방지를 위해 타임스탬프 추가
      img.src = '/jpg?t=' + startTime;
      
      img.onload = () => {
        frameCount++;
        const now = Date.now();
        const duration = now - startTime;
        if (now - lastTime >= 1000) {
          const fps = ((frameCount * 1000) / (now - lastTime)).toFixed(1);
          document.getElementById('status').textContent = '지연 시간: ' + duration + 'ms | FPS: ' + fps;
          frameCount = 0;
          lastTime = now;
        }
      };
    }

    // 스트리밍 시작 및 간격 설정
    function startStream() {
      if (streamTimer) clearInterval(streamTimer);
      streamTimer = setInterval(fetchFrame, streamInterval);
    }

    // 스트림 On/Off 토글
    function toggleStream() {
      const btn = document.getElementById('stream-btn');
      if (isStreaming) {
        isStreaming = false;
        clearInterval(streamTimer);
        btn.textContent = '스트림 시작';
        btn.className = 'btn';
        document.getElementById('status').textContent = '스트림 중지됨';
      } else {
        isStreaming = true;
        btn.textContent = '스트림 중지';
        btn.className = 'btn stop';
        startStream();
      }
    }

    // 스트리밍 주기 속도 조절
    function updateSpeed() {
      const val = document.getElementById('speed-range').value;
      document.getElementById('speed-val').textContent = val + 'ms';
      streamInterval = parseInt(val);
      if (isStreaming) {
        startStream();
      }
    }

    // 해상도 조절 요청
    function changeResolution() {
      const res = document.getElementById('res-select').value;
      document.getElementById('status').textContent = '해상도 변경 요청 중...';
      fetch('/config?res=' + res)
        .then(r => r.json())
        .then(data => {
          document.getElementById('resolution-badge').textContent = data.resolution_str;
          document.getElementById('status').textContent = '해상도 변경 완료!';
          
          // 해상도에 맞게 뷰어 크기 조절
          const img = document.getElementById('cam');
          if (res === '240') {
            img.style.width = '320px';
            img.style.height = '320px';
          } else {
            img.style.width = '100%';
            img.style.height = 'auto';
            img.style.maxWidth = '480px';
          }
        })
        .catch(err => {
          document.getElementById('status').textContent = '해상도 변경 실패';
        });
    }

    // 초기 스트림 시작
    startStream();
  </script>
</body>
</html>
)HTML";

// ============================================================================
// [핸들러 함수들] Web Server API 구현
// ============================================================================

// HTML 메인 페이지 전송
void handleRoot() {
  server.send_P(200, "text/html", STREAM_PAGE);
}

// 실시간 카메라 스냅샷 JPEG 전송
void handleJpg() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    server.send(503, "text/plain", "Capture failed");
    return;
  }
  
  uint8_t *jpg = NULL;
  size_t jpgLen = 0;
  bool ok = frame2jpg(fb, 80, &jpg, &jpgLen); // 퀄리티 80으로 JPEG 인코딩
  esp_camera_fb_return(fb);
  
  if (!ok) {
    server.send(500, "text/plain", "JPEG conversion failed");
    return;
  }
  
  server.setContentLength(jpgLen);
  server.send(200, "image/jpeg", "");
  server.client().write(jpg, jpgLen);
  free(jpg);
}

// 보드 상태 반환 (JSON)
void handleStatus() {
  String ipStr = WiFi.getMode() == WIFI_AP ? WiFi.softAPIP().toString() : WiFi.localIP().toString();
  String modeStr = WiFi.getMode() == WIFI_AP ? "XIAO_HOTSPOT_AP" : WiFi.SSID();
  
  sensor_t * s = esp_camera_sensor_get();
  String resStr = "Unknown";
  String resVal = "240";
  
  if (s) {
    framesize_t fs = s->status.framesize;
    if (fs == FRAMESIZE_240X240) { resStr = "240x240"; resVal = "240"; }
    else if (fs == FRAMESIZE_QVGA) { resStr = "320x240 (QVGA)"; resVal = "QVGA"; }
    else if (fs == FRAMESIZE_VGA)  { resStr = "640x480 (VGA)"; resVal = "VGA"; }
    else if (fs == FRAMESIZE_SVGA) { resStr = "800x600 (SVGA)"; resVal = "SVGA"; }
  }

  String json = "{\"ssid\":\"" + modeStr + "\",\"ip\":\"" + ipStr + 
                "\",\"resolution\":\"" + resVal + "\",\"resolution_str\":\"" + resStr + "\"}";
  server.send(200, "application/json", json);
}

// 해상도 조절 핸들러 (API)
void handleConfig() {
  if (!server.hasArg("res")) {
    server.send(400, "application/json", "{\"error\":\"Missing parameter\"}");
    return;
  }
  
  String res = server.arg("res");
  sensor_t * s = esp_camera_sensor_get();
  
  if (!s) {
    server.send(500, "application/json", "{\"error\":\"Sensor not found\"}");
    return;
  }
  
  String resStr = "Unknown";
  if (res == "240") {
    s->set_framesize(s, FRAMESIZE_240X240);
    resStr = "240x240";
  } else if (res == "QVGA") {
    s->set_framesize(s, FRAMESIZE_QVGA);
    resStr = "320x240 (QVGA)";
  } else if (res == "VGA") {
    s->set_framesize(s, FRAMESIZE_VGA);
    resStr = "640x480 (VGA)";
  } else if (res == "SVGA") {
    s->set_framesize(s, FRAMESIZE_SVGA);
    resStr = "800x600 (SVGA)";
  } else {
    server.send(400, "application/json", "{\"error\":\"Invalid resolution\"}");
    return;
  }
  
  // 프레임 버퍼 동기화를 위한 간단한 웜업
  for (int i = 0; i < 5; i++) {
    camera_fb_t *w = esp_camera_fb_get();
    if (w) esp_camera_fb_return(w);
    delay(30);
  }

  String json = "{\"status\":\"success\",\"resolution_str\":\"" + resStr + "\"}";
  server.send(200, "application/json", json);
}

// ============================================================================
// [초기화 및 메인 루프]
// ============================================================================
void setup() {
  Serial.begin(115200);
  delay(2000);
  Serial.println("\n--- XIAO ESP32-S3 Stream Server Start ---");

  // 카메라 설정 구조체 채우기
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
  
  // 기본 설정: AI 모델 수집에 친화적인 240x240 정사각 해상도 및 RGB565 포맷
  config.frame_size = FRAMESIZE_240X240;
  config.pixel_format = PIXFORMAT_RGB565;
  config.grab_mode = CAMERA_GRAB_LATEST;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.fb_count = 2; // 끊김 없는 스트리밍을 위한 더블 버퍼링

  // 카메라 초기화
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x\n", err);
    while (true) { delay(1000); }
  }
  Serial.println("Camera initialized successfully!");

  // 센서 제어 포인터를 통해 부가 설정 미세 조정 (화질 향상)
  sensor_t * s = esp_camera_sensor_get();
  if (s) {
    s->set_vflip(s, 1);      // 상하 반전 방지 (필요 시 0 또는 1)
    s->set_hmirror(s, 0);    // 좌우 반전
    s->set_brightness(s, 1); // 밝기 조절 (-2 ~ 2)
    s->set_contrast(s, 0);   // 대비 조절 (-2 ~ 2)
  }

  // 센서 웜업 (노출/화이트밸런스 조절을 위한 초반 유휴 프레임 캡처 후 폐기)
  for (int i = 0; i < 15; i++) {
    camera_fb_t *w = esp_camera_fb_get();
    if (w) esp_camera_fb_return(w);
    delay(50);
  }

  // Wi-Fi 연결 시도 (STA 모드)
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  Serial.print("Connecting to Wi-Fi '");
  Serial.print(ssid);
  Serial.print("' ");

  int attempts = 0;
  // 15초 동안 연결 대기 (30 x 500ms)
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  Serial.println();

  // 만약 연결 실패 시, SoftAP 핫스팟 모드로 자동 대체 (Fail-Safe 설계)
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi connection failed. Switching to Hotspot (AP) Mode...");
    WiFi.disconnect();
    WiFi.mode(WIFI_AP);
    WiFi.softAP("XIAO_STREAM_AP", "12345678", 1);
    Serial.print("Hotspot started. Connect to SSID 'XIAO_STREAM_AP' (PW: 12345678)\n");
    Serial.print("Then open browser at: http://");
    Serial.println(WiFi.softAPIP());
  } else {
    Serial.println("Wi-Fi connected successfully!");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());

    // mDNS 네임 서비스 등록
    if (MDNS.begin(mdnsName)) {
      Serial.print("mDNS registered! You can also connect via: http://");
      Serial.print(mdnsName);
      Serial.println(".local");
    }
  }

  // Web Server 라우팅 매핑
  server.on("/", handleRoot);
  server.on("/jpg", handleJpg);
  server.on("/status", handleStatus);
  server.on("/config", handleConfig);

  server.begin();
  Serial.println("Stream Server started! Ready for clients.");
}

void loop() {
  server.handleClient();
  delay(2); // 백그라운드 Wi-Fi 태스크가 유휴 시간을 가질 수 있도록 보장
}
