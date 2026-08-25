# PainlessMesh + MQTT Network

ESP32-C6 PainlessMesh 네트워크가 교실 MQTT 브로커와 연결되어 있습니다.

## 설정 정보

- **Mesh 이름**: `pick-mesh`
- **Mesh 비밀번호**: `12345678`
- **Mesh 포트**: `5555`
- **장치 이름**: `jyp`
- **MQTT 브로커**: `192.168.0.49:1883`
- **WiFi**: `ICEE`

## 주요 기능

### 메시 네트워크
- 자동 라우팅 및 네트워크 관리
- 노드 간 자동 시간 동기화
- LED 제어 메시지 브로드캐스트
- 센서 데이터 공유

### MQTT 통합
- 교실 브로커에 연결
- LED 제어 (classroom/jyp/led/set)
- 센서 데이터 전송 (classroom/jyp/sensor/a0)
- 상태 정보 전송 (classroom/jyp/status)
- 메시 네트워크 정보 (classroom/jyp/mesh/info)

### MQTT 토픽

| 토픽 | 방향 | 페이로드 |
|------|------|----------|
| `classroom/jyp/led/set` | 클라이언트 → 보드 | `on`, `off`, `toggle` |
| `classroom/jyp/led/state` | 보드 → 클라이언트 | `on`, `off` (유지) |
| `classroom/jyp/sensor/a0` | 보드 → 클라이언트 | `{"raw":2048,"mv":1650,"node":"jyp"}` |
| `classroom/jyp/status` | 보드 → 클라이언트 | `{"status":"online","nodes":1,"mesh_id":1234567890,"rssi":-50}` |
| `classroom/jyp/mesh/info` | 보드 → 클라이언트 | 메시 네트워크 상세 정보 |
| `classroom/mesh/command` | 클라이언트 → 모든 노드 | 모든 메시 노드에 브로드캐스트 |
| `classroom/mesh/sensor` | 보드 → 브로커 | 다른 노드의 센서 데이터 |

## 사용법

### LED 제어
```bash
./skill.sh led jyp on      # LED 켜기
./skill.sh led jyp off     # LED 끄기
./skill.sh led jyp toggle  # LED 토글
```

### 센서 데이터 확인
```bash
./skill.sh sensor jyp      # jyp의 센서 값 보기
```

### 메시 네트워크 명령
```bash
# 모든 메시 노드의 LED 켜기
mosquitto_pub -h 192.168.0.49 -p 1883 -t "classroom/mesh/command" -m "led_on"

# 모든 메시 노드의 LED 끄기
mosquitto_pub -h 192.168.0.49 -p 1883 -t "classroom/mesh/command" -m "led_off"

# 모든 메시 노드의 LED 토글
mosquitto_pub -h 192.168.0.49 -p 1883 -t "classroom/mesh/command" -m "led_toggle"
```

## 메시 네트워크 정보

### 메시 정보 토픽 예시
```json
{
  "mesh_id": 1234567890,
  "prefix": "pick-mesh",
  "port": 5555,
  "nodes": 3,
  "node_list": [1234567890, 2345678901, 3456789012],
  "rssi": -45
}
```

### 상태 토픽 예시
```json
{
  "status": "online",
  "nodes": 3,
  "mesh_id": 1234567890,
  "rssi": -45
}
```

## 다른 장치와 메시 네트워크 만들기

1. `config.h` 파일에서 `DEVICE_NAME` 변경
2. 각 장치에 펌웨어 업로드
3. 같은 WiFi 네트워크(ICEE)에 연결
4. 자동으로 메시 네트워크 형성

## 하드웨어

- **보드**: XIAO ESP32C6
- **LED 핀**: GPIO 15
- **센서 핀**: A0 (GPIO 0)
- **UART**: 115200 baud

## 라이브러리

- Painless Mesh 1.5.7
- PubSubClient 2.8
- ArduinoJson 7.4.3
- TaskScheduler 4.0.8
- AsyncTCP 1.1.4

## 문제 해결

### 메시 네트워크에 연결 안됨
- 같은 WiFi 네트워크에 있는지 확인
- Mesh 설정이 동일한지 확인
- 보드 간 거리가 너무 멀지 않은지 확인

### MQTT 연결 안됨
- 브로커 IP가 올바른지 확인
- WiFi 연결 상태 확인
- 방화벽 설정 확인