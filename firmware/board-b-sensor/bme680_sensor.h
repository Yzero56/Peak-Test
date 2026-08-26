#pragma once

// BME680 온습도/가스 센서 접근용 얇은 인터페이스.
// esp_camera.h와 Adafruit_Sensor.h를 같은 번역 단위에서 include하면 둘 다 정의하는
// sensor_t 타입이 충돌해서 컴파일이 깨진다 — 그래서 Adafruit_BME680 의존성을
// bme680_sensor.cpp 안에 가두고, 여기서는 원시 타입만 노출한다.

bool bme680Init();
bool bme680Read(float &temperatureC, float &humidityPct, float &gasResistanceOhm);
