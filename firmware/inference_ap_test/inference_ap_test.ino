/*
 * inference_ap_test.ino — 학습된 Edge Impulse 모델로 실물 인식률 테스트.
 *
 * XIAO ESP32S3 Sense + OV3660. 문틀 브링업 때 검증한 것과 같은 핫스팟
 * (FridgeCam / FridgeCamTest)을 그대로 띄우고, 이번엔 촬영 대신 실시간으로
 * soymilk/ham/egg 중 뭘 보고 있는지 판별해서 화면에 보여준다.
 *
 * xiao-webcam-ap 스킬의 web_infer.ino.tpl을 베이스로 두 가지를 우리 하드웨어에
 * 맞게 고쳤다:
 *   1) OV3660 방향 보정 추가 — 템플릿은 기본 OV2640 기준이라 이게 없으면 뒤집혀 나옴.
 *   2) 템플릿의 "CW 90도 회전 보정"을 뺐다 — 그 보정은 그쪽 실물 보드가 책상에
 *      돌려 놓여있던 상황에 맞춘 값이고, 우리는 데이터 수집 때부터 이미
 *      vflip/hmirror로 똑바로 나온 이미지를 그대로 업로드해서 학습시켰기 때문에
 *      (webcam_ap_collect.ino와 동일 파이프라인) 추가 회전을 넣으면 오히려
 *      학습 때 안 보던 각도가 돼서 틀어진다. 대신 단순 비율 리사이즈(squash)만 한다.
 *
 * 접속: WiFi "FridgeCam"(비번 FridgeCamTest) 연결 → http://192.168.4.1
 */
#include <Fridge-AI_inferencing.h>
#include <WiFi.h>
#include <WebServer.h>
#include "esp_camera.h"
#include "esp_heap_caps.h"

// 텐서 아레나를 PSRAM에 올린다 (SDK의 약한 심볼 오버라이드 — 스킬 Step 5-3)
void *ei_malloc(size_t size) {
  void *p = heap_caps_aligned_alloc(16, size, MALLOC_CAP_SPIRAM);
  if (!p) p = heap_caps_aligned_alloc(16, size, MALLOC_CAP_DEFAULT);
  return p;
}
void *ei_calloc(size_t nitems, size_t size) {
  void *p = ei_malloc(nitems * size);
  if (p) memset(p, 0, nitems * size);
  return p;
}
void ei_free(void *ptr) { heap_caps_free(ptr); }

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
static float features[EI_CLASSIFIER_INPUT_WIDTH * EI_CLASSIFIER_INPUT_HEIGHT];

static int get_feature_data(size_t offset, size_t length, float *out_ptr) {
  memcpy(out_ptr, features + offset, length * sizeof(float));
  return 0;
}

static const char PAGE[] PROGMEM = R"HTML(
<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FridgeCam 인식 테스트</title>
<style>
body{font-family:sans-serif;background:#111;color:#eee;text-align:center;margin:0;padding:16px}
#wrap{position:relative;display:inline-block}
img{width:320px;height:320px;object-fit:cover;border-radius:8px;display:block}
#box{position:absolute;inset:0;border:5px solid #4c8bf5;border-radius:8px;pointer-events:none;
     transition:border-color .3s}
#tag{position:absolute;left:0;top:0;background:#4c8bf5;color:#fff;font-weight:bold;
     padding:4px 10px;border-radius:8px 0 8px 0;font-size:18px;transition:background .3s}
.bar{display:flex;align-items:center;margin:4px auto;width:320px;font-size:14px}
.bar span{width:90px;text-align:right;padding-right:8px}
.bar .track{flex:1;background:#333;border-radius:4px;height:16px;overflow:hidden}
.bar .fill{height:100%;background:#4c8bf5;width:0%;transition:width .3s}
.bar b{width:48px;text-align:left;padding-left:6px}
#lat{color:#888;font-size:13px;margin-top:8px}
</style></head><body>
<h2>🧊 냉장고 물체 인식 테스트</h2>
<div id="wrap"><img id="cam" src="/jpg"><div id="box"></div><div id="tag">...</div></div>
<div id="bars"></div>
<div id="lat"></div>
<script>
const COLORS={soymilk:'#4cf58b',ham:'#f5734c',egg:'#f5c94c'};
setInterval(()=>{cam.src='/jpg?t='+Date.now()},900);
async function tick(){
  try{
    const r=await fetch('/classify'); const d=await r.json();
    let html='';
    for(const [k,v] of Object.entries(d.scores)){
      const c=COLORS[k]||'#4c8bf5';
      html+=`<div class="bar"><span>${k}</span><div class="track"><div class="fill" style="width:${(v*100).toFixed(0)}%;background:${c}"></div></div><b>${(v*100).toFixed(0)}%</b></div>`;
    }
    document.getElementById('bars').innerHTML=html;
    const c=COLORS[d.label]||'#4c8bf5';
    document.getElementById('box').style.borderColor=c;
    const tag=document.getElementById('tag');
    tag.style.background=c;
    tag.textContent=`${d.label} ${(d.confidence*100).toFixed(0)}%`;
    document.getElementById('lat').textContent=`dsp ${d.dsp_ms}ms + nn ${d.nn_ms}ms`;
  }catch(e){}
  setTimeout(tick,300);
}
tick();
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
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) { server.send(503, "application/json", "{\"error\":\"no frame\"}"); return; }

  // 단순 비율 리사이즈(squash) — 회전/미러 없음. 학습 데이터가 업로드된 그대로의
  // 방향(webcam_ap_collect.ino와 동일한 vflip 보정 이후)으로 들어왔으므로
  // 여기서도 같은 방향을 유지해야 한다.
  const int W = EI_CLASSIFIER_INPUT_WIDTH, H = EI_CLASSIFIER_INPUT_HEIGHT;
  const uint16_t *src = (const uint16_t *)fb->buf;
  for (int y = 0; y < H; y++) {
    for (int x = 0; x < W; x++) {
      int sx = x * fb->width / W;
      int sy = y * fb->height / H;
      uint16_t px = src[sy * fb->width + sx];
      px = (px >> 8) | (px << 8);  // 바이트 순서 보정
      uint8_t r = ((px >> 11) & 0x1F) << 3;
      uint8_t g = ((px >> 5) & 0x3F) << 2;
      uint8_t b = (px & 0x1F) << 3;
      features[y * W + x] = (float)((r << 16) | (g << 8) | b);
    }
  }
  esp_camera_fb_return(fb);

  signal_t signal;
  signal.total_length = W * H;
  signal.get_data = &get_feature_data;
  ei_impulse_result_t result = {0};
  if (run_classifier(&signal, &result, false) != EI_IMPULSE_OK) {
    server.send(500, "application/json", "{\"error\":\"classifier\"}");
    return;
  }

  int best = 0;
  String json = "{\"scores\":{";
  for (int i = 0; i < EI_CLASSIFIER_LABEL_COUNT; i++) {
    if (result.classification[i].value > result.classification[best].value) best = i;
    json += "\"" + String(ei_classifier_inferencing_categories[i]) + "\":" +
            String(result.classification[i].value, 3);
    if (i < EI_CLASSIFIER_LABEL_COUNT - 1) json += ",";
  }
  json += "},\"label\":\"" + String(ei_classifier_inferencing_categories[best]) + "\"";
  json += ",\"confidence\":" + String(result.classification[best].value, 3);
  json += ",\"dsp_ms\":" + String(result.timing.dsp);
  json += ",\"nn_ms\":" + String(result.timing.classification) + "}";
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

  // webcam_ap_collect.ino와 동일한 OV3660 방향 보정 — 학습 데이터와 방향을 맞춘다.
  {
    sensor_t *s = esp_camera_sensor_get();
    if (s && s->id.PID == OV3660_PID) {
      s->set_vflip(s, 1);
      s->set_hmirror(s, 0);
    }
  }

  for (int i = 0; i < 10; i++) { camera_fb_t *w = esp_camera_fb_get(); if (w) esp_camera_fb_return(w); delay(60); }

  WiFi.mode(WIFI_AP);
  WiFi.softAP("FridgeCam", "FridgeCamTest", 1);
  Serial.print("AP started. Open http://");
  Serial.println(WiFi.softAPIP());

  server.on("/", handleRoot);
  server.on("/jpg", handleJpg);
  server.on("/classify", handleClassify);
  server.begin();
  Serial.println("Inference viewer ready");
}

void loop() { server.handleClient(); }
