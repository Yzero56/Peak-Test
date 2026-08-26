"""screen_capture_sender.py — 화면 일부(iOS는 QuickTime, Android는 scrcpy로 띄운
폰 미러링 창)를 캡처해서 phone_mirror_relay.py로 WebSocket 전송한다. 이 스크립트
자체는 iOS/Android를 구분하지 않는다 — 그냥 화면의 한 영역을 계속 캡처해서 보낼
뿐이라, 그 영역에 뭐가 떠 있든(QuickTime든 scrcpy든) 똑같이 동작한다.

⚠ macOS 화면 기록 권한이 필요하다 — 반드시 **일반 터미널 앱(Terminal.app/iTerm 등)에서
직접 실행**해야 한다. Claude Code 세션 안에서는 실행해도 권한이 없어서 캡처가
안 된다(카메라와 동일한 종류의 TCC 제한 — 이 스크립트 자체는 정상이니, 그냥 다른
터미널 창에서 실행하면 된다). 처음 실행하면 시스템 설정 > 개인정보 보호 및 보안 >
화면 기록에서 터미널 앱 허용이 필요할 수 있다.

준비 — iOS:
  1. iPhone을 USB로 이 맥에 연결하고 "신뢰"를 눌러둔다.
  2. QuickTime Player 실행 → 파일 > 새로운 동영상 녹화 → 녹화 버튼 옆 ⌄ 눌러서
     카메라를 iPhone으로 선택 (녹화는 시작 안 해도 됨, 미리보기만 떠도 충분).

준비 — Android:
  1. 폰 설정 > 개발자 옵션에서 USB 디버깅을 켠다(개발자 옵션이 안 보이면
     설정 > 휴대전화 정보 > 빌드 번호를 7번 연속 탭).
  2. `brew install scrcpy android-platform-tools` (adb 포함) 후 폰을 USB로 연결,
     연결 확인 팝업에서 허용.
  3. 터미널에서 `scrcpy` 실행 — 폰 화면이 새 창으로 뜬다.

공통: 그 미러링 창(QuickTime 또는 scrcpy)을 화면 한쪽에 고정해두고, 이 스크립트의
--region으로 그 창의 좌표/크기를 알려준다(모르면 --monitor로 화면 전체를 일단
캡처해도 됨).

실행:
  pip install mss pillow websockets
  python dev/screen_capture_sender.py --relay ws://localhost:9600/ingest
  # 특정 영역만(미러링 창 좌표를 알 때, macOS 스크린샷 도구(Cmd+Shift+4)로
  # 좌상단 좌표를 화면에서 읽을 수 있다):
  python dev/screen_capture_sender.py --relay ws://localhost:9600/ingest \\
      --region 100,100,400,860
"""

from __future__ import annotations

import argparse
import asyncio
import io
import time

import mss
import websockets
from PIL import Image


async def run(relay_url: str, region: tuple[int, int, int, int] | None, monitor: int,
               fps: float, quality: int) -> None:
    interval = 1.0 / fps
    with mss.mss() as sct:
        if region:
            left, top, width, height = region
            bbox = {"left": left, "top": top, "width": width, "height": height}
        else:
            bbox = sct.monitors[monitor]

        print(f"[sender] 캡처 영역: {bbox}")
        print(f"[sender] 릴레이로 연결 시도: {relay_url}")
        async with websockets.connect(relay_url, max_size=None) as ws:
            print("[sender] 연결됨 — 전송 시작 (Ctrl+C로 중지)")
            while True:
                t0 = time.monotonic()
                shot = sct.grab(bbox)
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=quality)
                await ws.send(buf.getvalue())
                elapsed = time.monotonic() - t0
                await asyncio.sleep(max(0.0, interval - elapsed))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("준비")[0])
    ap.add_argument("--relay", default="ws://localhost:9600/ingest")
    ap.add_argument("--region", default=None,
                     help="left,top,width,height (QuickTime/scrcpy 창 좌표) — 안 주면 --monitor 전체 캡처")
    ap.add_argument("--monitor", type=int, default=1, help="mss 모니터 인덱스(0=전체 가상화면, 1=주 모니터)")
    ap.add_argument("--fps", type=float, default=8.0)
    ap.add_argument("--quality", type=int, default=75, help="JPEG 품질(1-95)")
    args = ap.parse_args()

    region = None
    if args.region:
        parts = [int(x) for x in args.region.split(",")]
        if len(parts) != 4:
            raise SystemExit("--region은 left,top,width,height 형식이어야 합니다")
        region = tuple(parts)  # type: ignore[assignment]

    try:
        asyncio.run(run(args.relay, region, args.monitor, args.fps, args.quality))
    except KeyboardInterrupt:
        pass
    except OSError as e:
        raise SystemExit(
            f"화면 캡처 실패: {e}\n"
            "macOS 시스템 설정 > 개인정보 보호 및 보안 > 화면 기록에서 이 터미널 앱을 허용했는지 확인하세요."
        )


if __name__ == "__main__":
    main()
