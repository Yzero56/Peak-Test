// PainlessMesh + MQTT Hybrid Network
// ESP32-C6 Mesh Network that connects to classroom MQTT broker
//
// Mesh Settings:
// - Prefix: pick-mesh
// - Password: 12345678
// - Port: 5555

#include <WiFi.h>
#include <PubSubClient.h>
#include "painlessMesh.h"

#define LED_PIN 15                  // XIAO user LED, active LOW
#define A0_PIN  A0                  // D0 / GPIO0

// Mesh Configuration
#define   MESH_PREFIX     "pick-mesh"
#define   MESH_PASSWORD   "12345678"
#define   MESH_PORT       5555

// MQTT Configuration
const char* MQTT_HOST = "192.168.0.49";
const int MQTT_PORT = 1883;

// Device Configuration
const char* DEVICE_NAME = "jyp";

// Mesh and MQTT clients
painlessMesh  mesh;
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

String deviceId;
String topicLedSet, topicLedState, topicSensor, topicStatus, topicMeshInfo;

// Timer variables
unsigned long lastSensorUpdate = 0;
unsigned long lastStatusUpdate = 0;
unsigned long lastMeshUpdate = 0;
const unsigned long sensorInterval = 2000;  // 2초마다 센서 값 전송
const unsigned long statusInterval = 10000; // 10초마다 상태 전송
const unsigned long meshInfoInterval = 5000; // 5초마다 메시 정보 전송

// LED state
bool ledState = false;

// Mesh node list for tracking
SimpleList<uint32_t> nodes;

// ---------------------------------------------------------------- callbacks

// Callback for when a new node joins the mesh
void newConnectionCallback(uint32_t nodeId) {
    Serial.printf("New Connection, nodeId = %u\n", nodeId);
}

// Callback for when a node leaves the mesh
void changedConnectionCallback() {
    Serial.printf("Changed connections\n");
    nodes = mesh.getNodeList();
    Serial.printf("Num nodes: %d\n", nodes.size());
}

// Callback for receiving mesh messages
void receivedCallback(uint32_t from, String &msg) {
    Serial.printf("Received from %u msg=%s\n", from, msg.c_str());

    // Parse LED control messages
    if (msg == "led_on") {
        setLed(true);
    } else if (msg == "led_off") {
        setLed(false);
    } else if (msg == "led_toggle") {
        setLed(!ledState);
    } else if (msg.startsWith("sensor:")) {
        // Forward sensor data from other nodes to MQTT
        String payload = msg.substring(7);
        mqtt.publish("classroom/mesh/sensor", payload.c_str());
    } else {
        // Display received text messages
        Serial.printf("📨 Mesh message from %u: %s\n", from, msg.c_str());
    }
}

// Callback for node time adjustment
void nodeTimeAdjustedCallback(int32_t offset) {
    Serial.printf("Adjusted time %u. Offset = %d\n", mesh.getNodeTime(), offset);
}

// MQTT callback
void onMqttMessage(char* topic, byte* payload, unsigned int length) {
    String msg;
    msg.reserve(length);
    for (unsigned int i = 0; i < length; i++) msg += (char)payload[i];
    msg.trim();

    Serial.printf("MQTT RX %s = %s\n", topic, msg.c_str());

    // Handle LED control
    if (String(topic) == topicLedSet) {
        if (msg == "on" || msg == "1" || msg == "true") {
            setLed(true);
        } else if (msg == "off" || msg == "0" || msg == "false") {
            setLed(false);
        } else if (msg == "toggle") {
            setLed(!ledState);
        }

        // Broadcast LED state to mesh
        mesh.sendBroadcast(ledState ? "led_on" : "led_off");
    }

    // Handle mesh control commands
    if (String(topic) == "classroom/mesh/command") {
        // Broadcast commands to all mesh nodes
        mesh.sendBroadcast(msg.c_str());
        Serial.printf("Broadcasted to mesh: %s\n", msg.c_str());
    }
}

// ---------------------------------------------------------------- helpers

void setLed(bool on) {
    ledState = on;
    digitalWrite(LED_PIN, on ? LOW : HIGH);
    mqtt.publish(topicLedState.c_str(), on ? "on" : "off", true);
    Serial.printf("LED -> %s\n", on ? "ON" : "OFF");
}

void publishSensorData() {
    int raw = analogRead(A0_PIN);
    int mv  = analogReadMilliVolts(A0_PIN);

    char payload[64];
    snprintf(payload, sizeof(payload), "{\"raw\":%d,\"mv\":%d,\"node\":\"jyp\"}", raw, mv);

    mqtt.publish(topicSensor.c_str(), payload);
    Serial.printf("TX %s = %s\n", topicSensor.c_str(), payload);

    // Also publish to mesh topic
    String meshPayload = String(payload);
    mesh.sendBroadcast("sensor:" + meshPayload);
}

void publishStatus() {
    char statusMsg[256];
    int nodeCount = nodes.size();

    snprintf(statusMsg, sizeof(statusMsg),
             "{\"status\":\"online\",\"nodes\":%d,\"mesh_id\":%u,\"rssi\":%d}",
             nodeCount, mesh.getNodeId(), WiFi.RSSI());

    mqtt.publish(topicStatus.c_str(), statusMsg, true);
    Serial.printf("Status: %s\n", statusMsg);
}

void publishMeshInfo() {
    char meshMsg[512];
    int nodeCount = nodes.size();

    // Build node list string
    String nodeList = "[";
    bool first = true;
    for (auto node : nodes) {
        if (!first) nodeList += ",";
        nodeList += String(node);
        first = false;
    }
    nodeList += "]";

    snprintf(meshMsg, sizeof(meshMsg),
             "{\"mesh_id\":%u,\"prefix\":\"%s\",\"port\":%d,\"nodes\":%d,\"node_list\":%s,\"rssi\":%d}",
             mesh.getNodeId(), MESH_PREFIX, MESH_PORT, nodeCount, nodeList.c_str(), WiFi.RSSI());

    mqtt.publish(topicMeshInfo.c_str(), meshMsg);
    Serial.printf("Mesh Info: %s\n", meshMsg);
}

void connectMqtt() {
    while (!mqtt.connected()) {
        Serial.printf("MQTT: connecting to %s:%d as %s ... ",
                      MQTT_HOST, MQTT_PORT, deviceId.c_str());

        if (mqtt.connect(deviceId.c_str(),
                         nullptr, nullptr,
                         topicStatus.c_str(), 0, true, "{\"status\":\"offline\"}")) {
            Serial.println("connected");

            mqtt.publish(topicStatus.c_str(), "{\"status\":\"online\"}", true);
            mqtt.subscribe(topicLedSet.c_str(), 1);
            mqtt.subscribe("classroom/mesh/command", 1);

            Serial.printf("subscribed to %s and classroom/mesh/command\n", topicLedSet.c_str());
            setLed(ledState);
        } else {
            Serial.printf("failed rc=%d, retrying in 5s\n", mqtt.state());
            delay(5000);
        }
    }
}

// ---------------------------------------------------------------- sketch

void setup() {
    Serial.begin(115200);
    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, HIGH);   // start off
    pinMode(A0_PIN, INPUT);

    delay(500);

    deviceId = DEVICE_NAME;

    // Setup MQTT topics
    topicLedSet   = "classroom/" + deviceId + "/led/set";
    topicLedState = "classroom/" + deviceId + "/led/state";
    topicSensor   = "classroom/" + deviceId + "/sensor/a0";
    topicStatus   = "classroom/" + deviceId + "/status";
    topicMeshInfo = "classroom/" + deviceId + "/mesh/info";

    Serial.printf("\n=== PainlessMesh + MQTT Node ===\n");
    Serial.printf("Device ID: %s\n", deviceId.c_str());
    Serial.printf("Mesh: %s:%d\n", MESH_PREFIX, MESH_PORT);
    Serial.printf("MQTT: %s:%d\n", MQTT_HOST, MQTT_PORT);
    Serial.printf("===============================\n\n");

    // Initialize mesh
    mesh.setDebugMsgTypes(ERROR | STARTUP | CONNECTION);
    mesh.init(MESH_PREFIX, MESH_PASSWORD, MESH_PORT);

    mesh.onNewConnection(&newConnectionCallback);
    mesh.onChangedConnections(&changedConnectionCallback);
    mesh.onNodeTimeAdjusted(&nodeTimeAdjustedCallback);
    mesh.onReceive(&receivedCallback);

    // Bridge to WiFi
    mesh.stationManual("ICEE", "icee2026");
    mesh.setHostname(deviceId.c_str());

    // Initialize MQTT
    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    mqtt.setCallback(onMqttMessage);
    mqtt.setKeepAlive(30);
    mqtt.setSocketTimeout(10);

    // Connect to MQTT broker
    connectMqtt();

    Serial.println("Setup complete!");
}

void loop() {
    mesh.update();
    mqtt.loop();

    // Handle serial input for mesh broadcasting
    if (Serial.available()) {
        String input = Serial.readStringUntil('\n');
        input.trim();

        if (input.length() > 0) {
            Serial.printf("Broadcasting to mesh: %s\n", input.c_str());
            mesh.sendBroadcast(input.c_str());
        }
    }

    // Auto-reconnect MQTT if disconnected
    if (!mqtt.connected()) {
        connectMqtt();
    }

    unsigned long now = millis();

    // Publish sensor data
    if (now - lastSensorUpdate >= sensorInterval) {
        lastSensorUpdate = now;
        publishSensorData();
    }

    // Publish status
    if (now - lastStatusUpdate >= statusInterval) {
        lastStatusUpdate = now;
        publishStatus();
    }

    // Publish mesh information
    if (now - lastMeshUpdate >= meshInfoInterval) {
        lastMeshUpdate = now;
        publishMeshInfo();
    }
}