# ESP32-S3 AP Camera Collector

This firmware creates a standalone Wi-Fi access point. It does not require internet access.

## Current settings

- Serial/upload port: `COM10`
- AP SSID: `PEAK-CAMERA`
- AP password: `peakcamera`
- Device IP: `192.168.4.1`
- Storage: microSD via `SD_MMC` 1-bit mode
- Camera pin map: common ESP32-S3-EYE layout

## Arduino IDE

1. Install the Espressif ESP32 board package and select an ESP32-S3 board.
2. Open `esp32s3_ap_capture.ino`.
3. Select the correct ESP32-S3 board and `COM10`.
4. Upload the sketch.
5. Insert a FAT32 microSD card before booting if images should be saved.
6. Open Serial Monitor at `115200` baud.
7. Connect a phone or laptop to `PEAK-CAMERA` with password `peakcamera`.
8. Open `http://192.168.4.1/`.

If the SSID is not visible, open Serial Monitor at `115200` and check whether `AP started: yes` appears. The AP is now started before camera initialization, so a camera pin-map error should not prevent the SSID from appearing. If `AP started: yes` appears but the SSID is still missing, power-cycle the board and scan specifically for 2.4 GHz networks.

With Arduino CLI, replace the FQBN if your board is not a generic ESP32-S3 Dev Module:

```powershell
arduino-cli compile --fqbn esp32:esp32:esp32s3 firmware/esp32s3_ap_capture
arduino-cli upload -p COM10 --fqbn esp32:esp32:esp32s3 firmware/esp32s3_ap_capture
```

The `Capture preview` button displays a frame. Enter a label and press `Save to SD` to write:

```text
/dataset/<label>/img_000001.jpg
```

## Board-specific camera pins

The sketch uses the ESP32-S3-EYE pin map. If the board is not ESP32-S3-EYE, replace the pin definitions near the top of the sketch with the board's camera schematic values. The camera pin map cannot be inferred from `COM10`.

## User test checklist

- Camera initializes without a `Camera init failed` message.
- The AP appears while the laptop/phone has no internet connection.
- `http://192.168.4.1/` loads.
- Preview image is visible.
- A labeled JPEG appears on the SD card.
- Repeated captures increment the filename instead of overwriting it.
