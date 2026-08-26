/*
 * reed_switch_test.ino
 *
 * XIAO ESP32S3 — 리드스위치(D0) + LED(D1) 배선 검증용 테스트 펌웨어
 *
 * 배선:
 *   D0 (GPIO1) — 리드스위치 한쪽 다리, 반대쪽 다리는 GND
 *   D1 (GPIO2) — LED 애노드(+) → 저항(220Ω~1kΩ 권장) → LED → GND
 *
 * 동작:
 *   D0을 INPUT_PULLUP으로 설정하므로 평상시(자석 없음, 스위치 열림)에는
 *   내부 풀업으로 HIGH, 자석이 가까워져 스위치가 닫히면 GND로 당겨져 LOW.
 *   → LOW(닫힘/자석 감지)일 때 LED(D1) ON, HIGH(열림)일 때 LED OFF.
 *   상태가 바뀔 때마다 시리얼(115200bps)로 로그를 남겨서 눈으로도,
 *   시리얼 모니터로도 정상 동작을 확인할 수 있게 한다.
 *
 * 확인 방법:
 *   1) 업로드 후 시리얼 모니터(115200bps) 열기
 *   2) 자석을 리드스위치에 가까이/멀리 하며 LED와 시리얼 로그가
 *      "닫힘(감지)"/"열림" 으로 정확히 반전되는지 확인
 */

const int REED_PIN = D0;
const int LED_PIN  = D1;

bool lastClosed = false;  // 마지막으로 확인된 상태 (true = 닫힘/자석 감지)

void setup() {
  Serial.begin(115200);
  // 네이티브 USB CDC라 포트 열릴 때까지 대기 (최대 3초, 시리얼 모니터 없이도 동작은 함)
  uint32_t start = millis();
  while (!Serial && millis() - start < 3000) {
    delay(10);
  }

  pinMode(REED_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  lastClosed = (digitalRead(REED_PIN) == LOW);
  digitalWrite(LED_PIN, lastClosed ? HIGH : LOW);

  Serial.println("=== 리드스위치 테스트 시작 (D0=리드스위치, D1=LED) ===");
  Serial.printf("초기 상태: %s\n", lastClosed ? "닫힘(자석 감지)" : "열림");
}

void loop() {
  // 간단한 디바운스: 20ms 안정적으로 같은 값이 읽혀야 상태 변경으로 인정
  bool reading = (digitalRead(REED_PIN) == LOW);
  static bool candidate = false;
  static uint32_t candidateSince = 0;

  if (reading != candidate) {
    candidate = reading;
    candidateSince = millis();
  }

  if (candidate != lastClosed && millis() - candidateSince > 20) {
    lastClosed = candidate;
    digitalWrite(LED_PIN, lastClosed ? HIGH : LOW);
    Serial.printf("[%lu ms] 상태 변경 -> %s\n", millis(),
                  lastClosed ? "닫힘(자석 감지) - LED ON" : "열림 - LED OFF");
  }

  delay(5);
}
