#include <Arduino.h>
#include <WiFi.h>

const char *AP_SSID = "PEAK-ESP32S3-TEST";
const char *AP_PASSWORD = "peaktest8";
WiFiServer server(80);

void setup() {
  Serial.begin(115200);
  delay(1500);

  Serial.println();
  Serial.println("ESP32-S3 AP-only test");
  Serial.printf("Chip: %s\n", ESP.getChipModel());
  Serial.printf("USB/flash test port expected: COM10\n");

  WiFi.mode(WIFI_AP);
  WiFi.setSleep(false);

  bool started = WiFi.softAP(AP_SSID, AP_PASSWORD, 1, false, 4);
  server.begin();
  Serial.printf("AP started: %s\n", started ? "yes" : "no");
  Serial.printf("SSID: %s\n", AP_SSID);
  Serial.printf("IP: %s\n", WiFi.softAPIP().toString().c_str());
  Serial.printf("MAC: %s\n", WiFi.softAPmacAddress().c_str());
}

void loop() {
  WiFiClient client = server.available();
  if (client) {
    unsigned long deadline = millis() + 1000;
    while (client.connected() && !client.available() && millis() < deadline) delay(1);
    while (client.available()) client.read();
    client.println("HTTP/1.1 200 OK");
    client.println("Content-Type: text/html; charset=utf-8");
    client.println("Connection: close");
    client.println();
    client.println("<h1>PEAK ESP32-S3 AP OK</h1><p>AP and HTTP server are working.</p>");
    delay(2);
    client.stop();
  }

  static unsigned long lastLog = 0;
  if (millis() - lastLog >= 5000) {
    lastLog = millis();
    Serial.printf("AP clients: %d, IP: %s\n", WiFi.softAPgetStationNum(), WiFi.softAPIP().toString().c_str());
  }
  delay(10);
}
