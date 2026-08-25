// BLE Control for XIAO ESP32C6
// Device Name: jyp
// Features: LED ON/OFF control + A0 analog reading via nRF Connect app

#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEServer.h>
#include <BLE2902.h>

// Define UUIDs for Service and Characteristics
#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define LED_CHAR_UUID      "beb5483e-36e1-4688-b7f5-ea07361b26a8"
#define A0_CHAR_UUID       "c9b4e3c8-8f4b-4b3a-9c4d-5e8f7a2b1c0d"

// Hardware pins
const int ledPin = 15;  // XIAO ESP32C6 built-in LED pin
const int a0Pin = A0;   // Analog input pin

// BLE Characteristics
BLECharacteristic *pLedCharacteristic;
BLECharacteristic *pA0Characteristic;

// Connection state
bool deviceConnected = false;
bool oldDeviceConnected = false;

// Timer for A0 updates
unsigned long lastA0Update = 0;
const unsigned long a0UpdateInterval = 1000; // Update every 1 second

// LED state
bool ledState = false;

// Server callbacks
class MyServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) {
        deviceConnected = true;
        Serial.println("📱 Device connected!");
    }

    void onDisconnect(BLEServer* pServer) {
        deviceConnected = false;
        Serial.println("📱 Device disconnected!");
        oldDeviceConnected = true;
    }
};

// LED Characteristic callbacks
class LedCallbacks: public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *pCharacteristic) {
        std::string value = pCharacteristic->getValue();

        if (value.length() > 0) {
            Serial.print("💡 LED command received: ");
            Serial.println(value.c_str());

            if (value == "on") {
                ledState = true;
                digitalWrite(ledPin, HIGH);
                Serial.println("🟢 LED turned ON");
            } else if (value == "off") {
                ledState = false;
                digitalWrite(ledPin, LOW);
                Serial.println("🔴 LED turned OFF");
            } else if (value == "toggle") {
                ledState = !ledState;
                digitalWrite(ledPin, ledState ? HIGH : LOW);
                Serial.printf("%s LED toggled\n", ledState ? "🟢" : "🔴");
            }

            // Update LED characteristic to reflect current state
            pLedCharacteristic->setValue(ledState ? "on" : "off");
            pLedCharacteristic->notify();
        }
    }
};

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println("\n========================================");
    Serial.println("   BLE Control - XIAO ESP32C6");
    Serial.println("   Device Name: jyp");
    Serial.println("========================================\n");

    // Initialize hardware
    pinMode(ledPin, OUTPUT);
    digitalWrite(ledPin, LOW);

    Serial.println("🔌 Hardware initialized:");
    Serial.print("   LED Pin: ");
    Serial.println(ledPin);
    Serial.print("   A0 Pin: ");
    Serial.println(a0Pin);

    // Initialize BLE
    Serial.println("\n📡 Initializing BLE...");
    BLEDevice::init("jyp");

    // Create BLE Server
    BLEServer *pServer = BLEDevice::createServer();
    pServer->setCallbacks(new MyServerCallbacks());

    // Create BLE Service
    BLEService *pService = pServer->createService(SERVICE_UUID);

    // Create LED Characteristic (Read | Write | Notify)
    pLedCharacteristic = pService->createCharacteristic(
        LED_CHAR_UUID,
        BLECharacteristic::PROPERTY_READ |
        BLECharacteristic::PROPERTY_WRITE |
        BLECharacteristic::PROPERTY_NOTIFY
    );
    pLedCharacteristic->setCallbacks(new LedCallbacks());
    pLedCharacteristic->setValue("off");  // Initial LED state

    // Create A0 Characteristic (Read | Notify)
    pA0Characteristic = pService->createCharacteristic(
        A0_CHAR_UUID,
        BLECharacteristic::PROPERTY_READ |
        BLECharacteristic::PROPERTY_NOTIFY
    );
    pA0Characteristic->addDescriptor(new BLE2902());

    // Start the service
    pService->start();

    // Start advertising
    BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
    pAdvertising->addServiceUUID(SERVICE_UUID);
    pAdvertising->setScanResponse(true);
    pAdvertising->setMinPreferred(0x06);  // Help with iPhone connections
    pAdvertising->setMinPreferred(0x12);
    BLEDevice::startAdvertising();

    Serial.println("✅ BLE Server started!");
    Serial.println("📻 Advertising as 'jyp'");
    Serial.println("\n📋 Service & Characteristic UUIDs:");
    Serial.print("   Service UUID: ");
    Serial.println(SERVICE_UUID);
    Serial.print("   LED Characteristic UUID: ");
    Serial.println(LED_CHAR_UUID);
    Serial.print("   A0 Characteristic UUID: ");
    Serial.println(A0_CHAR_UUID);
    Serial.println("\n========================================\n");
    Serial.println("📱 Ready to connect via nRF Connect app!");
    Serial.println("========================================\n");
}

void loop() {
    // Handle connection/disconnection
    if (!deviceConnected && oldDeviceConnected) {
        delay(500);  // Give the bluetooth stack the chance to get things ready
        pServer->startAdvertising();  // Restart advertising
        Serial.println("📻 Restarting advertising...");
        oldDeviceConnected = false;
    }

    // Update A0 value periodically
    if (deviceConnected && millis() - lastA0Update >= a0UpdateInterval) {
        lastA0Update = millis();

        // Read A0 value
        int rawValue = analogRead(a0Pin);
        float mvValue = rawValue * 3300.0 / 4095.0;  // Convert to millivolts

        // Create value string
        char a0Value[32];
        snprintf(a0Value, sizeof(a0Value), "%d", rawValue);

        // Update characteristic
        pA0Characteristic->setValue(a0Value);
        pA0Characteristic->notify();

        Serial.print("📊 A0 Value: ");
        Serial.print(rawValue);
        Serial.print(" (raw) | ");
        Serial.print(mvValue);
        Serial.println(" mV");
    }

    delay(10);  // Small delay to prevent congestion
}