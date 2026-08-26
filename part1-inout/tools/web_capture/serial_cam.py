"""
serial_cam.py — camera_capture.ino와 통신하는 시리얼 카메라 클라이언트.

tools/capture_image.py와 동일한 프로토콜([4바이트 길이][JPEG])을 쓰지만,
서버가 포트를 계속 열어두고 여러 요청을 순서대로 처리할 수 있도록
락(lock)을 두고 재사용 가능한 클래스로 감싼 버전.

펌웨어(camera_capture.ino)는 해상도를 부팅 시 SVGA로 고정해두고, 명령에 따라
압축률(화질)만 바꾼다:
  'p'         미리보기 — 빠른 압축률, 저장하지 않는 뷰파인더용
  '0'/'1'/'2' 저장용 촬영 — 빠름/표준/고화질 (셋 다 SVGA, 압축률만 다름)

문틀에 마운트하고 각도를 잡느라 케이블이 흔들리면 USB 연결이 순간적으로
끊겼다 잡히는 일이 흔해서 (macOS에서 "Device not configured" 에러로 나타남),
읽기/쓰기 중 그런 에러가 나면 포트를 한 번 재연결해서 재시도한다.
"""
import threading
import time

import serial

QUALITY_PRESETS = {
    "fast": "0",
    "standard": "1",
    "high": "2",
}
DEFAULT_QUALITY = "standard"

# USB가 끊겼을 때 나는 에러들 — 이게 잡히면 재연결을 시도한다.
_TRANSIENT_ERRORS = (serial.SerialException, OSError)


class SerialCameraError(RuntimeError):
    pass


class SerialCamera:
    def __init__(self, port: str, baud: int = 115200):
        self.port = port
        self.baud = baud
        self._lock = threading.Lock()
        self._ser = self._open()

    def _open(self) -> serial.Serial:
        ser = serial.Serial(self.port, self.baud, timeout=5)
        time.sleep(2.0)  # USB CDC 재연결(=보드 리셋) 대기
        ser.reset_input_buffer()
        return ser

    def _reconnect(self):
        try:
            self._ser.close()
        except Exception:
            pass
        self._ser = self._open()

    def _read_frame(self, cmd: bytes) -> bytes:
        with self._lock:
            try:
                return self._read_frame_once(cmd)
            except _TRANSIENT_ERRORS as e:
                # 케이블 흔들림 등으로 연결이 잠깐 끊긴 경우 한 번 재연결해서 재시도
                try:
                    self._reconnect()
                except _TRANSIENT_ERRORS as reconnect_err:
                    raise SerialCameraError(
                        f"카메라 연결이 끊겼고 재연결도 실패했습니다 (포트: {self.port}) — "
                        f"케이블/전원을 확인해주세요: {reconnect_err}"
                    ) from reconnect_err
                try:
                    return self._read_frame_once(cmd)
                except _TRANSIENT_ERRORS as e2:
                    raise SerialCameraError(f"재연결 후에도 통신 실패: {e2}") from e2

    def _read_frame_once(self, cmd: bytes) -> bytes:
        self._ser.reset_input_buffer()
        self._ser.write(cmd)

        len_bytes = self._ser.read(4)
        if len(len_bytes) < 4:
            raise SerialCameraError("device did not respond (길이 헤더 없음)")
        length = int.from_bytes(len_bytes, "little")
        if length == 0 or length > 5_000_000:
            raise SerialCameraError(f"비정상 길이 값: {length}")

        data = self._ser.read(length)
        if len(data) < length:
            raise SerialCameraError(f"수신 부족: {len(data)}/{length} bytes")

        return data

    def preview(self) -> bytes:
        """저장하지 않는 빠른 미리보기 프레임."""
        return self._read_frame(b"p")

    def capture(self, quality: str = DEFAULT_QUALITY) -> bytes:
        """사진 한 장을 찍어 JPEG 바이트를 반환한다. quality: fast/standard/high."""
        cmd = QUALITY_PRESETS.get(quality, QUALITY_PRESETS[DEFAULT_QUALITY])
        return self._read_frame(cmd.encode())

    def close(self):
        with self._lock:
            self._ser.close()
