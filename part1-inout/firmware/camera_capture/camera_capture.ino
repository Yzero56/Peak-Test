/*
 * camera_capture.ino
 *
 * XIAO ESP32S3 Sense + OV3660 — 시리얼 기반 촬영 도구
 *
 * 목적:
 *   1) 냉장고 문틀 각도 FOV 실측 (v3 스펙 §1.4)
 *   2) 이후 자체 데이터셋 촬영에도 동일 스케치/스크립트 재사용
 *
 * WiFi 없이 USB 시리얼(네이티브 USB CDC)로 한 글자 명령을 받으면
 * 사진 한 장을 찍어 [4바이트 길이][JPEG 바이트열] 형식으로 전송한다.
 *
 * 명령:
 *   'p'         미리보기 — 저장 안 함, 실시간 뷰파인더용
 *   '0'/'1'/'2' 저장용 촬영 — 화질(압축률) 프리셋 (빠름/표준/고화질)
 *
 * 해상도(프레임 크기)는 부팅 시 한 번만 정하고 이후 절대 바꾸지 않는다.
 * sensor->set_framesize()로 런타임에 해상도를 바꾸는 걸 여러 방식(제자리 전환,
 * 완전 재초기화, 전환 후 프레임 버리기 등)으로 시도했는데 esp32-camera가
 * DMA 파이프라인을 새로 세팅하는 타이밍에 따라 간헐적으로 "FB-OVF"가 나며
 * 시리얼 프로토콜이 깨졌다. 반면 set_quality()(압축률만 바꿈)는 DMA/해상도를
 * 건드리지 않는 가벼운 설정이라 안정적이다. 그래서 "화질" 버튼은 해상도가
 * 아니라 압축률만 바꾸고, 애초에 끊김의 원인이었던 "UXGA라 프레임레이트가
 * 낮음" 문제는 상시 해상도를 SVGA로 낮춰서 해결한다.
 *
 * 호스트 쪽은 tools/capture_image.py 또는 tools/web_capture/ 로 받는다.
 */

#include "esp_camera.h"

// XIAO ESP32S3 Sense 핀맵 (esp32 코어 예제 camera_pins.h의 CAMERA_MODEL_XIAO_ESP32S3 동일)
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

// 상시 해상도 — 절대 바꾸지 않는다. SVGA는 UXGA보다 프레임레이트가 훨씬 높아
// 미리보기가 부드럽고, 데이터셋용으로도 충분한 해상도다.
static const framesize_t FIXED_FRAMESIZE = FRAMESIZE_SVGA; // 800x600

static const int PREVIEW_QUALITY = 16; // 미리보기는 항상 빠르게

// 저장용 촬영 화질 프리셋 (버튼 3개). 해상도는 그대로, 압축률(0~63, 낮을수록 고화질)만 다르다.
static const int CAPTURE_QUALITY[3] = {
  18, // '0' 빠름   — 압축 많이, 용량 작음
  12, // '1' 표준   — 데이터셋 기본값
  6,  // '2' 고화질 — 압축 적게, 용량 큼, 디테일 최대
};

static bool cameraReady = false;
static sensor_t *sensor = nullptr;
static int currentQuality = -1;

bool initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
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
  config.grab_mode = CAMERA_GRAB_LATEST;

  bool hasPsram = psramFound();
  config.frame_size = hasPsram ? FIXED_FRAMESIZE : FRAMESIZE_CIF;
  config.jpeg_quality = PREVIEW_QUALITY;
  config.fb_count = hasPsram ? 2 : 1;
  config.fb_location = hasPsram ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("ERR camera init failed 0x%x\n", err);
    return false;
  }

  sensor = esp_camera_sensor_get();
  Serial.printf("INFO sensor PID=0x%02x (OV3660=0x3660 id ok if not 0)\n", sensor ? sensor->id.PID : 0);

  // OV3660은 기본 방향이 뒤집혀 나오는 경우가 많아 상하반전/좌우반전 보정.
  if (sensor && sensor->id.PID == OV3660_PID) {
    sensor->set_vflip(sensor, 1);
    sensor->set_hmirror(sensor, 0);
  }

  currentQuality = config.jpeg_quality;
  return true;
}

void setQuality(int quality) {
  if (quality == currentQuality) return;
  sensor->set_quality(sensor, quality);
  currentQuality = quality;
}

void sendFrame() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("ERR capture failed");
    return;
  }

  uint32_t len = fb->len;
  Serial.write((uint8_t *)&len, 4);
  Serial.write(fb->buf, fb->len);
  Serial.flush();

  esp_camera_fb_return(fb);
}

void setup() {
  Serial.begin(115200);
  unsigned long t0 = millis();
  while (!Serial && millis() - t0 < 3000) { delay(10); }

  cameraReady = initCamera();
  Serial.println(cameraReady ? "READY" : "CAMERA_INIT_FAILED");
}

void loop() {
  if (Serial.available()) {
    char cmd = Serial.read();

    if (!cameraReady) {
      Serial.println("ERR camera not ready");
      return;
    }

    if (cmd == 'p') {
      setQuality(PREVIEW_QUALITY);
      sendFrame();
    } else if (cmd >= '0' && cmd <= '2') {
      setQuality(CAPTURE_QUALITY[cmd - '0']);
      sendFrame();
    }
  } else if (cameraReady) {
    // 유휴 상태에서도 DMA는 계속 채워진다. 계속 비워주지 않으면 링버퍼가 밀려
    // "FB-OVF" 경고가 우리 바이너리 프로토콜과 같은 시리얼 라인에 섞여 들어온다.
    camera_fb_t *fb = esp_camera_fb_get();
    if (fb) esp_camera_fb_return(fb);
  }
}
