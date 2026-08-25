// MPU-6050/MPU-6500 자이로 센서 + AP 웹 서버
// ESP32-S3에서 자이로 센서 데이터를 웹으로 확인
// AP: esp32-c6-ja / Password: 12345678
// IP: http://192.168.4.1

#include <WiFi.h>
#include <NetworkClient.h>
#include <WiFiAP.h>
#include <Wire.h>

// AP 설정
const char *ssid = "esp32-c6-ja";
const char *password = "12345678";

// MPU6050/MPU6500 설정
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

// 스케일 계수
const float ACCEL_SCALE = 4096.0;   // ±8g
const float GYRO_SCALE  = 65.5;     // ±500 deg/s
const float G_TO_MS2    = 9.80665;

// 사용자 LED
const int USER_LED = 21;

// 자이로 영점 보정값
float gyroBiasX = 0, gyroBiasY = 0, gyroBiasZ = 0;

// 칩 종류
enum ChipType { CHIP_UNKNOWN, CHIP_MPU6050, CHIP_MPU6500 };
ChipType chip = CHIP_UNKNOWN;

// 중력 기준선
float gravityBaseline = G_TO_MS2;

// 움직임 감지
bool moving = false;

// 최신 센서 데이터 (전역 변수)
float latestAx = 0, latestAy = 0, latestAz = 0;
float latestGx = 0, latestGy = 0, latestGz = 0;
float latestTemp = 0;
float latestAccelMag = 0;

NetworkServer server(80);

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
  Serial.printf("calibrating (%d samples) - keep still...\n", samples);
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

  if (n == 0) {
    Serial.println("calibration failed - no samples");
    return;
  }

  gyroBiasX = sx / n;
  gyroBiasY = sy / n;
  gyroBiasZ = sz / n;
  gravityBaseline = sMag / n;

  Serial.printf("gyro bias (LSB): %.1f %.1f %.1f\n", gyroBiasX, gyroBiasY, gyroBiasZ);
  Serial.printf("gravity baseline: %.2f m/s^2\n", gravityBaseline);
}

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000) { }

  pinMode(USER_LED, OUTPUT);
  digitalWrite(USER_LED, HIGH);

  // I2C 초기화
  Wire.begin(D4, D5);  // SDA=D4(GPIO5), SCL=D5(GPIO6)
  Wire.setClock(400000);

  // 칩 ID 확인
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

  // MPU6050 초기화
  writeReg(REG_PWR_MGMT_1, 0x80);  // 리셋
  delay(100);
  writeReg(REG_PWR_MGMT_1, 0x01);  // 슬립 해제
  delay(50);

  writeReg(REG_CONFIG, 0x03);         // DLPF ~41Hz
  writeReg(REG_SMPLRT_DIV, 0x04);     // 200Hz
  writeReg(REG_GYRO_CONFIG, 0x08);    // ±500 deg/s
  writeReg(REG_ACCEL_CONFIG, 0x10);   // ±8g

  if (chip != CHIP_MPU6050) {
    writeReg(REG_ACCEL_CONFIG2, 0x03);
  }
  delay(50);

  calibrate(200);

  Serial.println("\n=== MPU6050 initialized ===");

  // AP 모드 시작
  Serial.println("\n=== Starting AP Mode ===");
  if (!WiFi.softAP(ssid, password)) {
    Serial.println("softAP failed!");
    while (true) delay(1000);
  }

  Serial.print("AP IP address: ");
  Serial.println(WiFi.softAPIP());
  Serial.printf("Connect to: %s / %s\n", ssid, password);
  Serial.println("Open: http://192.168.4.1");

  server.begin();
  Serial.println("Server started!");

  Serial.println("\n=== Ready for sensor test ===");
}

void loop() {
  // 센서 데이터 읽기
  int16_t rax, ray, raz, rt, rgx, rgy, rgz;

  if (readAll(&rax, &ray, &raz, &rt, &rgx, &rgy, &rgz)) {
    latestAx = rax / ACCEL_SCALE * G_TO_MS2;
    latestAy = ray / ACCEL_SCALE * G_TO_MS2;
    latestAz = raz / ACCEL_SCALE * G_TO_MS2;

    latestGx = (rgx - gyroBiasX) / GYRO_SCALE;
    latestGy = (rgy - gyroBiasY) / GYRO_SCALE;
    latestGz = (rgz - gyroBiasZ) / GYRO_SCALE;

    latestTemp = (chip == CHIP_MPU6050) ? (rt / 340.0 + 36.53) : (rt / 333.87 + 21.0);

    latestAccelMag = sqrt(latestAx * latestAx + latestAy * latestAy + latestAz * latestAz);
    float accelDelta = fabs(latestAccelMag - gravityBaseline);
    float gyroMag = sqrt(latestGx * latestGx + latestGy * latestGy + latestGz * latestGz);

    moving = (accelDelta > 0.5) || (gyroMag > 5.0);
    digitalWrite(USER_LED, moving ? LOW : HIGH);
  }

  // 웹 요청 처리
  NetworkClient client = server.accept();
  if (client) {
    String currentLine = "";
    while (client.connected()) {
      if (!client.available()) continue;
      char c = client.read();

      if (c == '\n') {
        if (currentLine.length() == 0) {
          // HTTP 응답 헤더
          client.println("HTTP/1.1 200 OK");
          client.println("Content-type:text/html");
          client.println("Connection: close");
          client.println();

          // HTML 페이지
          client.println("<!DOCTYPE html>");
          client.println("<html lang='ko'>");
          client.println("<head>");
          client.println("<meta charset='UTF-8'>");
          client.println("<meta name='viewport' content='width=device-width, initial-scale=1.0'>");
          client.println("<title>MPU6050 자이로 센서 테스트</title>");
          client.println("<style>");
          client.println("body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f5f5f5; }");
          client.println("h1 { color: #333; text-align: center; }");
          client.println(".sensor-data { background: white; padding: 20px; border-radius: 10px; margin: 10px 0; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }");
          client.println(".data-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #eee; }");
          client.println(".data-row:last-child { border-bottom: none; }");
          client.println(".label { font-weight: bold; color: #555; }");
          client.println(".value { color: #007bff; font-family: monospace; font-size: 1.1em; }");
          client.println(".status { text-align: center; font-size: 1.5em; font-weight: bold; padding: 15px; border-radius: 5px; margin: 20px 0; }");
          client.println(".moving { background: #28a745; color: white; }");
          client.println(".still { background: #6c757d; color: white; }");
          client.println(".info { background: #17a2b8; color: white; padding: 10px; border-radius: 5px; margin: 10px 0; }");
          client.println("</style>");
          client.println("</head>");
          client.println("<body>");
          client.println("<h1>🎯 MPU6050 자이로 센서 테스트</h1>");

          // 센서 정보
          client.println("<div class='sensor-data'>");
          client.println("<h3>📊 실시간 센서 데이터</h3>");
          client.printf("<div class='data-row'><span class='label'>가속도 X:</span><span class='value'>%.2f m/s²</span></div>\n", latestAx);
          client.printf("<div class='data-row'><span class='label'>가속도 Y:</span><span class='value'>%.2f m/s²</span></div>\n", latestAy);
          client.printf("<div class='data-row'><span class='label'>가속도 Z:</span><span class='value'>%.2f m/s²</span></div>\n", latestAz);
          client.printf("<div class='data-row'><span class='label'>자이로 X:</span><span class='value'>%.2f deg/s</span></div>\n", latestGx);
          client.printf("<div class='data-row'><span class='label'>자이로 Y:</span><span class='value'>%.2f deg/s</span></div>\n", latestGy);
          client.printf("<div class='data-row'><span class='label'>자이로 Z:</span><span class='value'>%.2f deg/s</span></div>\n", latestGz);
          client.printf("<div class='data-row'><span class='label'>온도:</span><span class='value'>%.1f °C</span></div>\n", latestTemp);
          client.printf("<div class='data-row'><span class='label'>가속도 크기:</span><span class='value'>%.2f m/s²</span></div>\n", latestAccelMag);
          client.println("</div>");

          // 움직임 상태
          client.printf("<div class='status %s'>%s</div>\n", moving ? "moving" : "still", moving ? "🏃 움직임 감지!" : "🛑 정지 상태");

          // 장치 정보
          client.println("<div class='sensor-data'>");
          client.println("<h3>📱 장치 정보</h3>");
          client.printf("<div class='data-row'><span class='label'>칩:</span><span class='value'>%s</span></div>\n",
                         chip == CHIP_MPU6050 ? "MPU-6050" : (chip == CHIP_MPU6500 ? "MPU-6500" : "UNKNOWN"));
          client.printf("<div class='data-row'><span class='label'>중력 기준:</span><span class='value'>%.2f m/s²</span></div>\n", gravityBaseline);
          client.printf("<div class='data-row'><span class='label'>자이로 보정:</span><span class='value'>%.1f, %.1f, %.1f</span></div>\n", gyroBiasX, gyroBiasY, gyroBiasZ);
          client.println("</div>");

          client.println("<div class='info'>");
          client.println("📌 페이지 새로고침(F5)으로 실시간 데이터 확인!");
          client.println("</div>");

          client.println("</body>");
          client.println("</html>");
          client.println();
          break;
        }
        currentLine = "";
      } else if (c != '\r') {
        currentLine += c;
      }
    }
    client.stop();
    Serial.println("client disconnected");
  }

  delay(50);
}