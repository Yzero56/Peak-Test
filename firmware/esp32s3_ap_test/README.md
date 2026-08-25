# ESP32-S3 AP-only diagnostic

This sketch intentionally does not use the camera or SD card. It starts a minimal HTTP server so AP connectivity can be tested in a phone browser.

Upload to `COM10` with the board FQBN matching the selected ESP32-S3 board:

```powershell
arduino-cli compile --fqbn esp32:esp32:esp32s3 firmware/esp32s3_ap_test
arduino-cli upload -p COM10 --fqbn esp32:esp32:esp32s3 firmware/esp32s3_ap_test
arduino-cli monitor -p COM10 -c baudrate=115200
```

Expected serial output:

```text
AP started: yes
SSID: PEAK-ESP32S3-TEST
IP: 192.168.4.1
```

Scan for `PEAK-ESP32S3-TEST` from a phone or laptop. If this SSID is not visible, do not debug the camera sketch yet. Check the selected board, upload success, boot/reset state, USB cable, power, and whether `COM10` is the native USB port or a USB-UART port.

After connecting, open `http://192.168.4.1/`. The expected page is `PEAK ESP32-S3 AP OK`.
