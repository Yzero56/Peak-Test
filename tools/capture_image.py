#!/usr/bin/env python3
"""
capture_image.py — camera_capture.ino와 짝을 이루는 호스트 측 촬영 도구.

용도:
  1) 문틀 FOV 실측 단계: 한 장씩 찍어보며 각도/높이 조절
  2) 이후 자체 데이터셋 촬영 단계: --loop 로 여러 장 연속 촬영

사용법:
  python3 tools/capture_image.py --port /dev/tty.usbmodem1101
  python3 tools/capture_image.py --port /dev/tty.usbmodem1101 --loop --out data/raw_captures --label empty
"""
import argparse
import sys
import time
from pathlib import Path

try:
    import serial
except ImportError:
    sys.exit("pyserial이 필요합니다: pip3 install pyserial")


def wait_for_ready(ser, timeout=2.0):
    """부팅 직후 나오는 READY/CAMERA_INIT_FAILED 로그를 잠깐 기다린다.
    업로드 직후처럼 이미 부팅 메시지가 지나가버린 경우엔 아무 것도 안 잡히는데,
    이땐 그냥 True를 반환하고 실제 촬영 시도에서 성공/실패를 판단한다."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        line = ser.readline().decode(errors="ignore").strip()
        if line:
            print(f"[device] {line}")
        if line == "READY":
            return True
        if line == "CAMERA_INIT_FAILED":
            return False
    return True


def capture_one(ser, out_path: Path) -> bool:
    ser.reset_input_buffer()
    ser.write(b"c")

    len_bytes = ser.read(4)
    if len(len_bytes) < 4:
        print("ERR 길이 헤더를 못 받음 (장치가 텍스트 로그를 보냈을 수 있음)")
        return False
    length = int.from_bytes(len_bytes, "little")
    if length == 0 or length > 5_000_000:
        print(f"ERR 비정상 길이 값: {length}")
        return False

    data = ser.read(length)
    if len(data) < length:
        print(f"ERR 수신 부족: {len(data)}/{length} 바이트")
        return False

    out_path.write_bytes(data)
    print(f"OK  {out_path}  ({length} bytes)")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/tty.usbmodem1101")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--out", default="data/raw_captures")
    ap.add_argument("--label", default="test", help="파일명 접두어 (예: empty, milk_carton 등)")
    ap.add_argument("--loop", action="store_true", help="Enter 누를 때마다 계속 촬영")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    ser = serial.Serial(args.port, args.baud, timeout=5)
    time.sleep(2.0)  # USB CDC 재연결 대기

    if not wait_for_ready(ser):
        sys.exit("카메라 초기화 실패 (CAMERA_INIT_FAILED 수신)")

    idx = 0
    while True:
        idx += 1
        fname = out_dir / f"{args.label}_{int(time.time())}_{idx:03d}.jpg"
        capture_one(ser, fname)
        if not args.loop:
            break
        input("다음 촬영: Enter (종료: Ctrl+C) ")


if __name__ == "__main__":
    main()
