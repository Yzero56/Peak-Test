"""
http_cam.py — webcam_ap_capture.ino와 통신하는 HTTP 카메라 클라이언트.

serial_cam.SerialCamera와 동일한 인터페이스(.preview() / .capture(quality) /
.close() / .port)를 제공한다 — server.py가 시리얼이냐 WiFi냐만 다르고
나머지는 똑같이 쓸 수 있게 하기 위함.

ESP32가 FridgeCam이라는 자기 핫스팟을 띄우고(webcam_ap_capture.ino), 이 코드를
쓰려면 이 스크립트를 실행하는 컴퓨터가 그 핫스팟에 접속돼있어야 한다
(집 와이파이 비밀번호를 쓰지 않기 위한 선택 — 자세한 이유는 상위 대화 참고).
"""
import requests

from serial_cam import QUALITY_PRESETS, DEFAULT_QUALITY, SerialCameraError  # noqa: F401 (재사용)


class HttpCamera:
    def __init__(self, host: str = "192.168.4.1", timeout: float = 6.0):
        self.host = host
        self.port = host  # server.py의 status 응답이 이 필드를 그대로 보여줌
        self.timeout = timeout
        # requests.get()을 매번 새로 부르면 요청마다 TCP 연결을 새로 맺어서(AP
        # 모드 WiFi라 핸드셰이크가 특히 느림) 녹화처럼 짧은 간격으로 연속 요청할 때
        # 왕복시간이 크게 늘어난다(실측: 프레임당 0.12초를 기대했는데 실제론
        # 0.7~1.7초씩 걸림). Session으로 연결을 재사용해서 이 오버헤드를 없앤다.
        self._session = requests.Session()
        # 바로 한 번 찔러봐서 연결 안 되면 여기서 바로 실패시킨다 (server.py의
        # ensure_camera()가 이걸 잡아서 재시도 루프를 돈다)
        self._get("/")

    def _get(self, path: str, **params) -> bytes:
        url = f"http://{self.host}{path}"
        try:
            r = self._session.get(url, params=params or None, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            raise SerialCameraError(
                f"FridgeCam({self.host})에 연결할 수 없습니다 — 이 컴퓨터가 "
                f"FridgeCam WiFi에 접속돼있는지 확인해주세요: {e}"
            ) from e
        if r.status_code != 200:
            raise SerialCameraError(f"HTTP {r.status_code}: {r.text[:200]}")
        return r.content

    def preview(self) -> bytes:
        data = self._get("/preview")
        if not data.startswith(b"\xff\xd8"):
            raise SerialCameraError("미리보기 응답이 JPEG가 아닙니다")
        return data

    def capture(self, quality: str = DEFAULT_QUALITY) -> bytes:
        q = quality if quality in QUALITY_PRESETS else DEFAULT_QUALITY
        data = self._get("/capture", quality=q)
        if not data.startswith(b"\xff\xd8"):
            raise SerialCameraError("촬영 응답이 JPEG가 아닙니다")
        return data

    def close(self):
        self._session.close()
