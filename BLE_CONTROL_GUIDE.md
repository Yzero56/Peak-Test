# BLE Control Guide for XIAO ESP32C6

## Overview
This guide will help you set up Bluetooth Low Energy (BLE) control for your XIAO ESP32C6, allowing you to:
- Control LED ON/OFF from your phone
- Read A0 analog sensor values from your phone
- Device name: **jyp**

## Requirements
- XIAO ESP32C6 development board
- USB-C cable for programming
- Arduino IDE
- nRF Connect app (Android: Google Play, iOS: App Store)
- ESP32 on COM3 port

## Step 1: Arduino IDE Setup

### Install ESP32 Board Support
1. Open Arduino IDE
2. Go to **File > Preferences**
3. In "Additional Board Manager URLs", add:
   ```
   https://espressif.github.io/arduino-esp32/package_esp32_index.json
   ```
4. Click **OK**
5. Go to **Tools > Board > Boards Manager**
6. Search for "esp32" and install "esp32 by Espressif Systems"

### Select XIAO ESP32C6 Board
1. Go to **Tools > Board > esp32 > XIAO_ESP32C6**

### Select COM3 Port
1. Go to **Tools > Port**
2. Select **COM3** (or your ESP32's port)

## Step 2: Upload the Code

### Upload Process
1. Open the file: `ble_control_jyp/ble_control_jyp.ino`
2. Click the **Upload** button (→)
3. Wait for compilation and upload to complete
4. Open **Serial Monitor** (Tools > Serial Monitor)
5. Set baud rate to **115200**

### Expected Serial Output
```
========================================
   BLE Control - XIAO ESP32C6
   Device Name: jyp
========================================

🔌 Hardware initialized:
   LED Pin: 15
   A0 Pin: A0

📡 Initializing BLE...
✅ BLE Server started!
📻 Advertising as 'jyp'

📋 Service & Characteristic UUIDs:
   Service UUID: 4fafc201-1fb5-459e-8fcc-c5c9c331914b
   LED Characteristic UUID: beb5483e-36e1-4688-b7f5-ea07361b26a8
   A0 Characteristic UUID: c9b4e3c8-8f4b-4b3a-9c4d-5e8f7a2b1c0d

========================================

📱 Ready to connect via nRF Connect app!
========================================
```

## Step 3: Using nRF Connect App

### Android Setup
1. Download from Google Play: "nRF Connect for Mobile"
2. Open the app and grant Bluetooth permissions

### iOS Setup  
1. Download from App Store: "nRF Connect for Mobile"
2. Open the app and grant Bluetooth permissions

### Connection Process

#### 1. Scan for Devices
- Tap **SCAN** button
- Look for device named **"jyp"**
- Tap **CONNECT** on the "jyp" device

#### 2. Discover Services
- Once connected, you'll see the service:
  - **Service UUID**: `4fafc201-1fb5-459e-8fcc-c5c9c331914b`
- Tap the service to expand it

#### 3. LED Control
- Find **LED Characteristic**: `beb5483e-36e1-4688-b7f5-ea07361b26a8`
- Tap the characteristic to expand it
- Tap the **Down Arrow (▼)** icon to write values
- **Send "on"** - Turns LED ON
- **Send "off"** - Turns LED OFF  
- **Send "toggle"** - Toggles LED state

#### 4. Read A0 Values
- Find **A0 Characteristic**: `c9b4e3c8-8f4b-4b3a-9c4d-5e8f7a2b1c0d`
- Tap the **Up Arrow (▲)** icon to enable notifications
- Values will update automatically every second
- **Value format**: Raw ADC value (0-4095)
- **Real conversion**: Value × 3300 / 4095 = millivolts

## Step 4: Testing

### Test LED Control
1. Connect to "jyp" device
2. Write "on" to LED characteristic
3. Verify LED turns ON (check board LED)
4. Write "off" to LED characteristic  
5. Verify LED turns OFF

### Test A0 Reading
1. Enable notifications on A0 characteristic
2. Observe values changing (try connecting sensor to A0)
3. Values update every second automatically

## Step 5: Hardware Connections

### LED (Built-in)
- The built-in LED is on GPIO 15
- No external connection needed

### A0 Analog Input
- A0 is the built-in analog pin
- Connect sensors to A0 pin:
  - Voltage range: 0-3.3V
  - Resolution: 12-bit (0-4095)
  - Example sensors: potentiometer, light sensor, temperature sensor

### Example Sensor Connection
```
Potentiometer → A0
  - Left pin: 3.3V
  - Middle pin: A0
  - Right pin: GND
```

## Troubleshooting

### Device Not Found in nRF Connect
1. Check Serial Monitor - verify "Advertising as 'jyp'" message
2. Restart ESP32 (power cycle)
3. Make sure Bluetooth is enabled on phone
4. Try moving closer to ESP32

### Connection Drops
1. Check power supply stability
2. Reduce update interval in code if needed
3. Check for interference from other Bluetooth devices

### A0 Values Not Updating
1. Verify notifications are enabled (tap ▲ icon)
2. Check Serial Monitor for A0 value updates
3. Verify hardware connection to A0 pin
4. Try different sensor or potentiometer

### LED Not Responding
1. Check Serial Monitor for command messages
2. Verify correct characteristic is being written
3. Try "on", "off", "toggle" commands
4. Check LED pin connection (GPIO 15)

## Code Modifications

### Change Update Interval
```cpp
const unsigned long a0UpdateInterval = 1000; // Change to 500 for faster updates
```

### Change Device Name
```cpp
BLEDevice::init("your_custom_name"); // Replace "jyp" with desired name
```

### Add More Characteristics
Follow the pattern in the code to add more sensors or controls.

## Technical Details

### BLE Architecture
- **Server**: ESP32 (advertises services and characteristics)
- **Client**: Phone (nRF Connect app)
- **Communication**: GATT protocol over BLE

### Characteristic Properties
- **LED**: Read | Write | Notify
- **A0**: Read | Notify

### UUID Reference
- Service UUID: `4fafc201-1fb5-459e-8fcc-c5c9c331914b`
- LED Characteristic UUID: `beb5483e-36e1-4688-b7f5-ea07361b26a8`
- A0 Characteristic UUID: `c9b4e3c8-8f4b-4b3a-9c4d-5e8f7a2b1c0d`

## Safety Notes
- Keep input voltage to A0 within 0-3.3V range
- Use appropriate current limiting resistors for LEDs
- Ensure stable power supply during operation
- Avoid high-power Bluetooth interference sources

## Next Steps
- Add more sensors (temperature, humidity, etc.)
- Implement data logging
- Create custom mobile app
- Add multiple device support
- Implement OTA updates

## Support
For issues or questions:
- Check Serial Monitor output for error messages
- Verify all connections and power supply
- Test with simple potentiometer on A0 first
- Check nRF Connect app permissions

---

**Created by**: Claude Code  
**Device**: XIAO ESP32C6  
**Firmware**: ble_control_jyp  
**Version**: 1.0