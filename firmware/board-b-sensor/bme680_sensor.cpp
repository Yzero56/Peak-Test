#include "bme680_sensor.h"

#include <Wire.h>
#include <Adafruit_BME680.h>

// XIAO ESP32-S3 Sense의 보드 라벨 SDA/SCL 핀(D4=GPIO5, D5=GPIO6, 보드 기본 Wire 핀)에
// 그대로 연결했다고 가정 — Wire.begin()에 핀을 안 넘기면 보드 변형(variant) 기본값을 쓴다.

static Adafruit_BME680 bme680;
static bool ready = false;

bool bme680Init() {
  Wire.begin();
  // 주소는 SDO 핀 상태에 따라 0x76(LOW, 기본) 또는 0x77(HIGH)이라 둘 다 시도한다.
  if (!bme680.begin(0x76) && !bme680.begin(0x77)) {
    ready = false;
    return false;
  }
  bme680.setTemperatureOversampling(BME680_OS_8X);
  bme680.setHumidityOversampling(BME680_OS_2X);
  bme680.setPressureOversampling(BME680_OS_4X);
  bme680.setIIRFilterSize(BME680_FILTER_SIZE_3);
  bme680.setGasHeater(320, 150);  // 320도씨로 150ms 가열 후 가스 저항 측정
  ready = true;
  return true;
}

bool bme680Read(float &temperatureC, float &humidityPct, float &gasResistanceOhm) {
  if (!ready) return false;
  if (!bme680.performReading()) return false;
  temperatureC = bme680.temperature;
  humidityPct = bme680.humidity;
  gasResistanceOhm = bme680.gas_resistance;
  return true;
}
