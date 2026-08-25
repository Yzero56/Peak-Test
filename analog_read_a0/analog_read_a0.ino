void setup() {
  // 시리얼 통신 시작: 115200 보율
  Serial.begin(115200);

  // 시리얼 모니터가 준비될 때까지 대기
  while (!Serial) {
    ; // 시리얼 포트가 연결될 때까지 대기
  }
}

void loop() {
  // A0 핀 값 읽기 (0-1023 범위)
  int sensorValue = analogRead(A0);

  // 시리얼로 출력
  Serial.println(sensorValue);

  // 100ms 대기
  delay(100);
}
