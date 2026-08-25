// MPU-6050 / MPU-6500 6축 IMU — 웹 기반 자이로 센서 테스트 (AP 모드)
//
// 칩 자동 판별: "MPU-6050"으로 판매되는 모듈 상당수가 실제로는 MPU-6500이다.
//       I2C 주소(0x68)와 데이터 레지스터 배치가 같아 스캔으로는 구분되지 않고,
//       WHO_AM_I(0x75)를 읽어야 드러난다. 0x68=6050, 0x70=6500.
//
// 배선: VCC -> XIAO 3V3 / GND -> GND / SDA -> D4(GPIO5) / SCL -> D5(GPIO6)
//
// 웹 접속: "ESP32_Camera" 핫스팟 연결 (비밀번호: 12345678)
//          http://192.168.4.1 접속

#include <Wire.h>
#include <WiFi.h>
#include <WebServer.h>

const uint8_t IMU_ADDR = 0x68;

// 레지스터
const uint8_t REG_SMPLRT_DIV   = 0x19;
const uint8_t REG_CONFIG       = 0x1A;
const uint8_t REG_GYRO_CONFIG  = 0x1B;
const uint8_t REG_ACCEL_CONFIG = 0x1C;
const uint8_t REG_ACCEL_CONFIG2= 0x1D;
const uint8_t REG_ACCEL_XOUT_H = 0x3B;
const uint8_t REG_PWR_MGMT_1   = 0x6B;
const uint8_t REG_WHO_AM_I     = 0x75;

// 측정 스케일
const float ACCEL_SCALE = 4096.0;   // ±8g -> 4096 LSB/g
const float GYRO_SCALE  = 65.5;     // ±500 dps -> 65.5 LSB/(deg/s)
const float G_TO_MS2    = 9.80665;

// 움직임 판정 문턱값
const float ACCEL_THRESHOLD = 0.5;  // m/s^2
const float GYRO_THRESHOLD  = 5.0;  // deg/s

const int USER_LED = 21;

// 자이로 영점 보정값
float gyroBiasX = 0, gyroBiasY = 0, gyroBiasZ = 0;

// 감지된 칩 종류
enum ChipType { CHIP_UNKNOWN, CHIP_MPU6050, CHIP_MPU6500 };
ChipType chip = CHIP_UNKNOWN;

// 정지 시 가속도 크기 기준선
float gravityBaseline = G_TO_MS2;

WebServer server(80);

void writeReg(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(IMU_ADDR);
  Wire.write(reg);
  Wire.write(val);
  Wire.endTransmission();
}

uint8_t readReg(uint8_t reg) {
  Wire.beginTransmission(IMU_ADDR);
  Wire.write(reg);
  Wire.endTransmission(false);
  Wire.requestFrom((uint8_t)IMU_ADDR, (uint8_t)1);
  return Wire.available() ? Wire.read() : 0xFF;
}

bool readAll(int16_t* ax, int16_t* ay, int16_t* az,
             int16_t* t,
             int16_t* gx, int16_t* gy, int16_t* gz) {
  Wire.beginTransmission(IMU_ADDR);
  Wire.write(REG_ACCEL_XOUT_H);
  if (Wire.endTransmission(false) != 0) return false;

  if (Wire.requestFrom((uint8_t)IMU_ADDR, (uint8_t)14) != 14) return false;

  *ax = (Wire.read() << 8) | Wire.read();
  *ay = (Wire.read() << 8) | Wire.read();
  *az = (Wire.read() << 8) | Wire.read();
  *t  = (Wire.read() << 8) | Wire.read();
  *gx = (Wire.read() << 8) | Wire.read();
  *gy = (Wire.read() << 8) | Wire.read();
  *gz = (Wire.read() << 8) | Wire.read();
  return true;
}

void calibrate(int samples) {
  float sx = 0, sy = 0, sz = 0, sMag = 0;
  int n = 0;
  int16_t ax, ay, az, t, gx, gy, gz;

  for (int i = 0; i < samples; i++) {
    if (readAll(&ax, &ay, &az, &t, &gx, &gy, &gz)) {
      sx += gx; sy += gy; sz += gz;

      float fax = ax / ACCEL_SCALE * G_TO_MS2;
      float fay = ay / ACCEL_SCALE * G_TO_MS2;
      float faz = az / ACCEL_SCALE * G_TO_MS2;
      sMag += sqrt(fax * fax + fay * fay + faz * faz);
      n++;
    }
    delay(5);
  }

  if (n == 0) return;

  gyroBiasX = sx / n;
  gyroBiasY = sy / n;
  gyroBiasZ = sz / n;
  gravityBaseline = sMag / n;
}

void handleRoot() {
  int16_t ax, ay, az, t, gx, gy, gz;
  bool moving = false;
  String chipName = "UNKNOWN";
  float tempC = 0;
  String state = "still";

  if (!readAll(&ax, &ay, &az, &t, &gx, &gy, &gz)) {
    chipName = "READ ERROR";
    state = "ERROR";
  } else {
    float fax = ax / ACCEL_SCALE * G_TO_MS2;
    float fay = ay / ACCEL_SCALE * G_TO_MS2;
    float faz = az / ACCEL_SCALE * G_TO_MS2;
    float accelMag = sqrt(fax * fax + fay * fay + faz * faz);

    float fgx = (gx - gyroBiasX) / GYRO_SCALE;
    float fgy = (gy - gyroBiasY) / GYRO_SCALE;
    float fgz = (gz - gyroBiasZ) / GYRO_SCALE;
    float gyroMag = sqrt(fgx * fgx + fgy * fgy + fgz * fgz);

    moving = (fabs(accelMag - gravityBaseline) > ACCEL_THRESHOLD) || (gyroMag > GYRO_THRESHOLD);

    if (chip == CHIP_MPU6050) {
      chipName = "MPU-6050";
      tempC = t / 340.0 + 36.53;
    } else if (chip == CHIP_MPU6500) {
      chipName = "MPU-6500";
      tempC = t / 333.87 + 21.0;
    } else {
      chipName = "UNKNOWN";
      tempC = t / 333.87 + 21.0; // default to 6500
    }

    state = moving ? "MOVING" : "still";
  }

  digitalWrite(USER_LED, moving ? LOW : HIGH);

  String json = "{";
  json += "\"chip\":\"" + chipName + "\",";
  json += "\"state\":\"" + state + "\",";
  json += "\"temp\":" + String(tempC, 1) + ",";
  json += "\"accel\":{";
  json += "\"x\":" + String(ax / ACCEL_SCALE * G_TO_MS2, 2) + ",";
  json += "\"y\":" + String(ay / ACCEL_SCALE * G_TO_MS2, 2) + ",";
  json += "\"z\":" + String(az / ACCEL_SCALE * G_TO_MS2, 2);
  json += "},";
  json += "\"gyro\":{";
  json += "\"x\":" + String((gx - gyroBiasX) / GYRO_SCALE, 1) + ",";
  json += "\"y\":" + String((gy - gyroBiasY) / GYRO_SCALE, 1) + ",";
  json += "\"z\":" + String((gz - gyroBiasZ) / GYRO_SCALE, 1);
  json += "},";
  json += "\"calibration\":{";
  json += "\"gravity\":" + String(gravityBaseline, 2) + ",";
  json += "\"gyroBias\":{";
  json += "\"x\":" + String(gyroBiasX, 1) + ",";
  json += "\"y\":" + String(gyroBiasY, 1) + ",";
  json += "\"z\":" + String(gyroBiasZ, 1);
  json += "}}";
  json += "}";

  server.send(200, "application/json", json);
}

static const char PAGE[] PROGMEM = R"HTML(
<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ESP32 IMU Sensor</title>
<style>
body{font-family:sans-serif;background:#111;color:#eee;text-align:center;margin:0;padding:16px}
.card{background:#222;border-radius:12px;padding:20px;margin:12px auto;max-width:500px}
h2{margin:0 0 16px 0}
.stat{display:flex;justify-content:space-between;margin:8px 0;padding:12px;background:#333;border-radius:8px}
.stat-label{color:#888;font-size:14px}
.stat-value{font-size:18px;font-weight:bold}
.axis{display:inline-block;width:80px;text-align:center;margin:4px 2px;padding:4px 8px;border-radius:4px;
       background:#444;font-size:14px}
.axis.x{color:#4c8bf5}
.axis.y{color:#f5734c}
.axis.z{color:#3fbf6f}
#state{font-size:24px;font-weight:bold;padding:12px;margin:16px 0;border-radius:8px}
#state.still{background:#3fbf6f}
#state.moving{background:#f5734c}
#chip{color:#888;font-size:14px;margin:8px 0}
</style></head><body>
<h2>🔮 ESP32 IMU 센서</h2>
<div id="state">정지 중...</div>
<div id="chip">칩: 확인 중...</div>

<div class="card">
  <h3>온도</h3>
  <div class="stat"><span class="stat-label">온도</span><span class="stat-value" id="temp">--</span></div>
</div>

<div class="card">
  <h3>가속도 (m/s²)</h3>
  <div class="axis x">X: <span id="ax">--</span></div>
  <div class="axis y">Y: <span id="ay">--</span></div>
  <div class="axis z">Z: <span id="az">--</span></div>
</div>

<div class="card">
  <h3>자이로 (deg/s)</h3>
  <div class="axis x">X: <span id="gx">--</span></div>
  <div class="axis y">Y: <span id="gy">--</span></div>
  <div class="axis z">Z: <span id="gz">--</span></div>
</div>

<div class="card">
  <h3>캘리브레이션</h3>
  <div class="stat"><span class="stat-label">중력</span><span class="stat-value" id="gravity">--</span></div>
  <div class="axis x">바이어스 X: <span id="gxb">--</span></div>
  <div class="axis y">바이어스 Y: <span id="gyb">--</span></div>
  <div class="axis z">바이어스 Z: <span id="gzb">--</span></div>
</div>

<script>
async function update(){
  try{
    const r=await fetch('/sensor');
    const d=await r.json();
    document.getElementById('state').textContent=d.state==='MOVING'?'🏃 움직임 중':'🛑 정지';
    document.getElementById('state').className='state '+d.state.toLowerCase();
    document.getElementById('chip').textContent='칩: '+d.chip;
    document.getElementById('temp').textContent=d.temp.toFixed(1)+'°C';
    document.getElementById('ax').textContent=d.accel.x.toFixed(2);
    document.getElementById('ay').textContent=d.accel.y.toFixed(2);
    document.getElementById('az').textContent=d.accel.z.toFixed(2);
    document.getElementById('gx').textContent=d.gyro.x.toFixed(1);
    document.getElementById('gy').textContent=d.gyro.y.toFixed(1);
    document.getElementById('gz').textContent=d.gyro.z.toFixed(1);
    document.getElementById('gravity').textContent=d.calibration.gravity.toFixed(2)+' m/s²';
    document.getElementById('gxb').textContent=d.calibration.gyroBias.x.toFixed(1);
    document.getElementById('gyb').textContent=d.calibration.gyroBias.y.toFixed(1);
    document.getElementById('gzb').textContent=d.calibration.gyroBias.z.toFixed(1);
  }catch(e){}
}
setInterval(update,100);
update();
</script></body></html>
)HTML";

void setup() {
  Serial.begin(115200);
  delay(3000);

  pinMode(USER_LED, OUTPUT);
  digitalWrite(USER_LED, HIGH); // 액티브 로우 -> 꺼짐

  Wire.begin(A4, A5);
  Wire.setClock(400000);

  uint8_t id = readReg(REG_WHO_AM_I);
  Serial.printf("WHO_AM_I = 0x%02X -> ", id);
  switch (id) {
    case 0x68:
      chip = CHIP_MPU6050;
      Serial.println("MPU-6050");
      break;
    case 0x70:
      chip = CHIP_MPU6500;
      Serial.println("MPU-6500");
      break;
    default:
      chip = CHIP_UNKNOWN;
      Serial.println("UNKNOWN chip");
      break;
  }

  writeReg(REG_PWR_MGMT_1, 0x80);
  delay(100);
  writeReg(REG_PWR_MGMT_1, 0x01);
  delay(50);

  writeReg(REG_CONFIG, 0x03);
  writeReg(REG_SMPLRT_DIV, 0x04);
  writeReg(REG_GYRO_CONFIG, 0x08);
  writeReg(REG_ACCEL_CONFIG, 0x10);

  if (chip != CHIP_MPU6050) {
    writeReg(REG_ACCEL_CONFIG2, 0x03);
  }
  delay(50);

  calibrate(200);

  Serial.println("IMU web interface ready");

  WiFi.mode(WIFI_AP);
  WiFi.softAP("ESP32_Camera", "12345678", 1);
  Serial.print("AP started. Open http://");
  Serial.println(WiFi.softAPIP());

  server.on("/", handleRoot);
  server.on("/sensor", handleRoot);
  server.begin();
  Serial.println("Web server ready");
}

void loop() {
  server.handleClient();
}