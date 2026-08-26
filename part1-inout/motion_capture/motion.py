"""
motion.py — 프레임 차분 기반 모션 감지 + In/Out 판정 (1번 파트 핵심 로직).

카메라(ESP32, webcam_ap_capture.ino)가 계속 보내주는 JPEG 프레임을 받아서:
  1. 이전 프레임과 그레이스케일 차분 → 움직임 시작/종료를 이벤트로 묶는다
  2. 이벤트 동안 "변화한 영역의 중심(centroid)"이 프레임 안에서 어떻게 움직였는지
     궤적으로 기록한다 (5.1절 재설계 사항 — 문틀 각도라 단순 전/후 비교로는
     안 되고 궤적 기반이 필요함)
  3. 궤적의 시작→끝 방향으로 In/Out을 1차 추정한다

주의 — 이 IN/OUT 판정은 초벌 휴리스틱이다. "아래(카메라 진입부)→위(선반 안쪽)
이동 = 넣는 동작"이라는 축 가정은 실제 문틀 마운트 각도로 촬영해보기 전까지는
추측이고, 진짜 이벤트 몇 개를 눈으로 본 다음 축/부호를 조정해야 한다.
나중에 2번 파트(YOLOE/DINOv3)가 붙으면 이 궤적 휴리스틱은 "언제 캡처할지"
트리거 용도로만 남고, 실제 물체 식별은 그쪽으로 넘어가는 게 맞다.

프레임워크 독립적으로 짜서 FastAPI(지금) 든 나중에 3번 파트 백엔드든
그대로 재사용할 수 있게 했다.
"""
import io
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

# 손-물체 구분용 MediaPipe HandLandmarker. mediapipe 1.0.1(최신)은 이 맥/파이썬
# 조합에서 GPU(Metal) 델리게이트 관련 네이티브 크래시가 나서(DrishtiMetalHelper
# "Service is unavailable"), 구버전(0.10.35)으로 고정해서 쓴다 — 그건 CPU
# 델리게이트로 문제없이 동작 확인함.
try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    _MEDIAPIPE_AVAILABLE = True
except ImportError:
    _MEDIAPIPE_AVAILABLE = False

_HAND_MODEL_PATH = Path(__file__).parent / "models" / "hand_landmarker.task"


@dataclass
class MotionEvent:
    id: str
    start_ts: float
    end_ts: float | None = None
    trajectory: list = field(default_factory=list)  # [(ts, cx, cy), ...] cx/cy는 0~1 정규화
    flow_samples: list = field(default_factory=list)  # [(ts, dy_norm, mag_norm), ...] 옵티컬 플로우
    start_frame: bytes | None = None
    end_frame: bytes | None = None
    bbox: list | None = None  # [x0,y0,x1,y1] 0~1 정규화 — 시작 vs 끝 프레임을 비교해서 나온 변화 영역
    start_crop: bytes | None = None  # bbox로 잘라낸 시작/끝 프레임 — 배경 없이 물체 위주로 보려는 용도
    end_crop: bytes | None = None
    classification: str = "unknown"       # 궤적 회귀 기반 판정 — "in" | "out" | "unknown"
    confidence: float = 0.0
    flow_classification: str = "unknown"  # 옵티컬 플로우 기반 판정 — 실측해보니 이쪽이 더 잘 맞음
    flow_confidence: float = 0.0
    final_classification: str = "unknown"  # 실제 채택되는 답 — 플로우 우선, 플로우가 "모름"일 때만
    final_confidence: float = 0.0          # 궤적 결과로 폴백 (둘 다 계산은 항상 해두고 비교 가능하게 유지)
    final_source: str = "none"             # "flow" | "trajectory" | "none" — final이 어디서 왔는지
    state_classification: str = "unknown"  # 시작/끝 프레임 직접 비교(방향이 아니라 '생겼나/없어졌나') — 세 번째 신호, 비교용
    state_confidence: float = 0.0

    # ---- 손-소지물 비교 판정(4번째 신호, 방향 축 가정이 없는 새 방식) ----
    # 궤적/플로우는 둘 다 "위/아래 어느 쪽으로 움직였나"를 보는데, 이건 카메라
    # 마운트 각도에 따라 부호가 달라져서 실측으로 두 번이나 뒤집었는데도 여전히
    # 안 맞는다는 피드백을 받았다. 이 신호는 방향을 아예 안 본다 — 손이 세션
    # 안에서 "처음 보였을 때"와 "마지막으로 보였을 때" 옆에 물체(질량)가
    # 있었는지만 비교한다. 손 자체는 _detect_hand_boxes로 제외하고 남는 픽셀
    # 양을 "들고 있음 점수"로 쓴다.
    hand_seen: bool = False           # 이 세션에서 손이 한 번이라도 감지됐는지
    hand_first_ts: float | None = None  # 손이 처음 보인 시각 — 문 열림~손 등장까지의 "죽은 시간" 확인용
    hand_carry_samples: list = field(default_factory=list)  # [(ts, obj_score), ...] 손 감지된 프레임마다
    carry_classification: str = "unknown"
    carry_confidence: float = 0.0

    # ---- 세션 내내 추적된 프레임별 기록 (개발자 모드 UI에서 "실제로 뭘 찍었는지" 필름스트립으로 보여주는 용도) ----
    # 각 항목: {"ts": float, "bbox": [x0,y0,x1,y1], "ratio": float, "obj_score": int,
    #           "hand_count": int, "crop": bytes|None}
    frames: list = field(default_factory=list)
    best_crop: bytes | None = None   # frames 중 obj_score가 가장 큰(가장 또렷하게 잡힌) 프레임의 크롭
    best_bbox: list | None = None
    best_ts: float | None = None

    def to_dict(self):
        return {
            "id": self.id,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "duration_s": round((self.end_ts or time.time()) - self.start_ts, 2),
            "trajectory_len": len(self.trajectory),
            # 로그 화면에서 실제로 뭘 보고 판정했는지 눈으로 확인할 수 있게 궤적 좌표
            # 자체를 남긴다 (전에는 개수만 남아서 나중에 재검증이 안 됐음)
            "trajectory": [[round(t - self.start_ts, 2), round(cx, 3), round(cy, 3)]
                           for t, cx, cy in self.trajectory],
            "classification": self.classification,
            "confidence": round(self.confidence, 2),
            "flow_classification": self.flow_classification,
            "flow_confidence": round(self.flow_confidence, 2),
            "state_classification": self.state_classification,
            "state_confidence": round(self.state_confidence, 2),
            "carry_classification": self.carry_classification,
            "carry_confidence": round(self.carry_confidence, 2),
            "carry_samples": [[round(t - self.start_ts, 2), score] for t, score in self.hand_carry_samples],
            "final_classification": self.final_classification,
            "final_confidence": round(self.final_confidence, 2),
            "final_source": self.final_source,
            "bbox": [round(v, 3) for v in self.bbox] if self.bbox else None,
            "hand_seen": self.hand_seen,
            "hand_first_ts": round(self.hand_first_ts - self.start_ts, 2) if self.hand_first_ts else None,
            "frames": [
                {
                    "i": i,
                    "t": round(fr["ts"] - self.start_ts, 2),
                    "bbox": [round(v, 3) for v in fr["bbox"]] if fr["bbox"] else None,
                    "ratio": round(fr["ratio"], 4),
                    "obj_score": fr["obj_score"],
                    "hand_count": fr["hand_count"],
                    "has_crop": fr["crop"] is not None,
                }
                for i, fr in enumerate(self.frames)
            ],
            "best_ts": round(self.best_ts - self.start_ts, 2) if self.best_ts is not None else None,
            "best_bbox": [round(v, 3) for v in self.best_bbox] if self.best_bbox else None,
            "has_best_crop": self.best_crop is not None,
        }


class MotionDetector:
    def __init__(
        self,
        motion_threshold: int = 25,      # 픽셀 밝기 차 임계값 (0~255)
        pixel_ratio: float = 0.012,      # 이 비율 이상 픽셀이 변해야 "움직임"으로 침 — 0.02는
                                          # 너무 빡빡해서 실측해보니 프레임 사이 간격이 수 초씩
                                          # 뜨고 궤적 점이 30%는 4개 이하로 나옴 (신호 부족)
        cooldown_s: float = 0.8,         # 이만큼 조용하면 이벤트 종료
        min_event_s: float = 0.15,       # 너무 짧은 흔들림(노이즈) 무시
        max_event_s: float = 6.0,        # 이보다 길어지면 강제로 끊고 새 이벤트 시작
                                          # (실측해보니 여러 동작이 하나로 뭉쳐 37초짜리
                                          # 이벤트가 나왔음 — 그러면 시작/끝 방향이 섞여서
                                          # In/Out 판정이 의미 없어짐)
        analysis_size: tuple = (100, 75),  # 다운샘플 크기 — 속도용, 원본 비율(4:3)과 맞춤
        depth_axis_threshold: float = 0.08,  # 실제 기록 135개로 역산: 0.15는 79%가 "모름"으로
                                              # 나와서 너무 빡빡했고(원인: 판정 보류 문제),
                                              # 0.05는 오판이 잦았던 값. 0.08이 그 중간.
        flow_threshold: float = 0.003,   # 옵티컬 플로우 기반 판정 임계값 — 아직 실측 전 초기값,
        flow_scale: float = 0.02,        # 궤적 임계값처럼 실제 로그 쌓이면 다시 보정 필요
        state_threshold: float = 0.1,    # 시작/끝 프레임 비교 판정 임계값 — 마찬가지로 초기 추정치
        carry_threshold: float = 0.15,   # 손-소지물 비교 판정 임계값 — 초기 추정치, 실측 후 보정 필요
        bbox_padding: float = 0.15,      # 박스 크롭 여유분 — 딱 맞게 자르면 물체 일부가 잘릴 수 있어서
        max_session_frames: int = 150,   # 세션 프레임 기록 상한 — 5초 예상 대비 넉넉히 30초치(0.2s 간격) 정도
    ):
        self.motion_threshold = motion_threshold
        self.pixel_ratio = pixel_ratio
        self.cooldown_s = cooldown_s
        self.min_event_s = min_event_s
        self.max_event_s = max_event_s
        self.analysis_size = analysis_size
        self.depth_axis_threshold = depth_axis_threshold
        self.state_threshold = state_threshold
        self.carry_threshold = carry_threshold
        self.flow_threshold = flow_threshold
        self.flow_scale = flow_scale
        self.bbox_padding = bbox_padding
        self.max_session_frames = max_session_frames

        self.prev_gray = None
        self.state = "idle"  # "idle" | "motion" — 레거시(리드스위치 없을 때 폴백용) process_frame()이 씀
        self.current_event: MotionEvent | None = None
        self.last_motion_ts = 0.0
        self.events: list[MotionEvent] = []
        self.max_kept_events = 200

        # 리드스위치 기반 세션 추적용 상태 (start_session/track_session_frame/end_session)
        self.session_event: MotionEvent | None = None
        self.session_prev_gray: np.ndarray | None = None

        self._hand_landmarker = None  # 지연 로딩 (첫 사용 시 초기화, ~1초 걸림)
        self._hand_landmarker_load_failed = False

    def _to_gray(self, jpeg_bytes: bytes) -> np.ndarray:
        img = Image.open(io.BytesIO(jpeg_bytes)).convert("L").resize(self.analysis_size)
        return np.asarray(img, dtype=np.uint8)

    def _centroid(self, mask: np.ndarray):
        ys, xs = np.nonzero(mask)
        if len(xs) == 0:
            return 0.5, 0.5
        cx = float(xs.mean()) / mask.shape[1]
        cy = float(ys.mean()) / mask.shape[0]
        return cx, cy

    def _mask_bbox(self, mask: np.ndarray):
        """변한 픽셀들을 감싸는 사각형을 0~1 정규화 좌표로 돌려준다 (없으면 None)."""
        ys, xs = np.nonzero(mask)
        if len(xs) == 0:
            return None
        h, w = mask.shape
        return [float(xs.min()) / w, float(ys.min()) / h,
                float(xs.max() + 1) / w, float(ys.max() + 1) / h]

    def _get_hand_landmarker(self):
        if self._hand_landmarker is not None or self._hand_landmarker_load_failed:
            return self._hand_landmarker
        if not _MEDIAPIPE_AVAILABLE or not _HAND_MODEL_PATH.exists():
            self._hand_landmarker_load_failed = True
            return None
        try:
            base_options = mp_python.BaseOptions(
                model_asset_path=str(_HAND_MODEL_PATH),
                delegate=mp_python.BaseOptions.Delegate.CPU,  # GPU 델리게이트는 이 환경에서 크래시남
            )
            options = mp_vision.HandLandmarkerOptions(
                base_options=base_options,
                num_hands=2,
                min_hand_detection_confidence=0.4,
                running_mode=mp_vision.RunningMode.IMAGE,
            )
            self._hand_landmarker = mp_vision.HandLandmarker.create_from_options(options)
        except Exception:
            self._hand_landmarker_load_failed = True
        return self._hand_landmarker

    def _detect_hand_boxes(self, jpeg_bytes: bytes, padding: float = 0.04) -> list:
        """이 프레임에서 손이 있는 영역을 0~1 정규화 박스 리스트로 돌려준다 (없으면 []).
        움직임 마스크에서 이 영역을 빼면 "손 자체"가 아니라 "손이 들고 있는 물체"
        쪽만 남길 수 있다."""
        landmarker = self._get_hand_landmarker()
        if landmarker is None:
            return []
        try:
            img = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
            arr = np.asarray(img)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=arr)
            result = landmarker.detect(mp_image)
        except Exception:
            return []
        boxes = []
        for lm in result.hand_landmarks:
            xs = [p.x for p in lm]
            ys = [p.y for p in lm]
            boxes.append((
                max(0.0, min(xs) - padding), max(0.0, min(ys) - padding),
                min(1.0, max(xs) + padding), min(1.0, max(ys) + padding),
            ))
        return boxes

    def _mask_minus_boxes(self, mask: np.ndarray, boxes: list) -> np.ndarray:
        """mask(다운샘플 좌표계)에서 boxes(0~1 정규화, 원본 좌표계) 영역을 지운다."""
        if not boxes:
            return mask
        h, w = mask.shape
        out = mask.copy()
        for x0, y0, x1, y1 in boxes:
            px0, py0 = int(x0 * w), int(y0 * h)
            px1, py1 = max(px0 + 1, int(np.ceil(x1 * w))), max(py0 + 1, int(np.ceil(y1 * h)))
            out[py0:py1, px0:px1] = False
        return out

    def _crop_frame(self, jpeg_bytes: bytes, bbox: list) -> bytes | None:
        """bbox(0~1 정규화, 다운샘플 좌표계 기준)를 실제 프레임 해상도로 환산해서
        여유(padding)를 두고 잘라낸다. 배경 없이 물체 위주로 보고 싶을 때 씀."""
        try:
            img = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
        except Exception:
            return None
        w, h = img.size
        x0, y0, x1, y1 = bbox
        pw, ph = (x1 - x0) * self.bbox_padding, (y1 - y0) * self.bbox_padding
        x0, y0 = max(0.0, x0 - pw), max(0.0, y0 - ph)
        x1, y1 = min(1.0, x1 + pw), min(1.0, y1 + ph)
        box_px = (int(x0 * w), int(y0 * h), max(int(x1 * w), int(x0 * w) + 1), max(int(y1 * h), int(y0 * h) + 1))
        cropped = img.crop(box_px)
        buf = io.BytesIO()
        cropped.save(buf, format="JPEG", quality=88)
        return buf.getvalue()

    def _classify(self, event: MotionEvent):
        # 시작점 vs 끝점 딱 2개만 비교하면, "손이 들어갔다가 거의 같은 자리로
        # 빠져나오는" 흔한 동작에서 순간적인 흔들림 하나로 부호가 뒤집히기
        # 쉽다 (실측해보니 신뢰도 0.25~0.4대에서 오판이 몰림). 대신 궤적 전체에
        # 선형회귀를 돌려서 "시간에 따라 y가 전반적으로 어느 쪽으로 향했는지"
        # 추세선 기울기로 판정한다 — 점 하나하나의 잡음에 훨씬 덜 흔들린다.
        if len(event.trajectory) < 3:
            event.classification, event.confidence = "unknown", 0.0
            return
        ts = np.array([p[0] for p in event.trajectory], dtype=np.float64)
        ys = np.array([p[2] for p in event.trajectory], dtype=np.float64)
        span = ts[-1] - ts[0]
        if span <= 0:
            event.classification, event.confidence = "unknown", 0.0
            return
        t_norm = (ts - ts[0]) / span  # 0~1로 정규화 — 이벤트 길이에 상관없이 기울기 스케일을 맞춤
        slope, _ = np.polyfit(t_norm, ys, 1)

        if abs(slope) < self.depth_axis_threshold:
            event.classification, event.confidence = "unknown", 0.0
            return
        # 실측(2회 연속) 결과 원래 가정(아래→위=IN)이 반대로 나왔다 — 실제 마운트
        # 각도/방향에서는 위→아래 추세가 IN이었다. 부호를 뒤집어서 반영한다.
        event.classification = "out" if slope < 0 else "in"
        event.confidence = min(1.0, abs(slope) / 0.4)

    def _flow_dy(self, prev_gray: np.ndarray, gray: np.ndarray, mask: np.ndarray):
        """prev_gray→gray 사이 옵티컬 플로우(dense, Farneback)를 계산해서, 움직인
        영역(mask) 안에서의 평균 수직 이동 방향(dy)과 그 크기를 돌려준다.
        궤적(점을 이어붙여 추세를 "추측")과 달리, 프레임 한 장당 실제 이동 벡터를
        바로 얻는다 — 흔들림에 덜 흔들릴 것으로 기대하는 부분."""
        flow = cv2.calcOpticalFlowFarneback(
            prev_gray, gray, None,
            pyr_scale=0.5, levels=2, winsize=11, iterations=2,
            poly_n=5, poly_sigma=1.1, flags=0,
        )
        fy = flow[..., 1]  # 수직 성분 — 양수: 아래로 이동
        region = fy[mask] if mask.any() else fy.ravel()
        h = gray.shape[0]
        dy_norm = float(region.mean()) / h
        mag_norm = float(np.abs(region).mean()) / h
        return dy_norm, mag_norm

    def _classify_flow(self, event: MotionEvent):
        samples = event.flow_samples
        if not samples:
            event.flow_classification, event.flow_confidence = "unknown", 0.0
            return
        dys = np.array([s[1] for s in samples])
        mags = np.array([s[2] for s in samples])
        total_mag = float(mags.sum())
        if total_mag <= 1e-9:
            event.flow_classification, event.flow_confidence = "unknown", 0.0
            return
        # 많이 움직인 프레임일수록 더 크게 반영 (가중평균) — 살짝 떨린 프레임에
        # 덜 흔들리게 하려는 목적
        weighted_dy = float((dys * mags).sum() / total_mag)
        if abs(weighted_dy) < self.flow_threshold:
            event.flow_classification, event.flow_confidence = "unknown", 0.0
            return
        # _classify()와 동일한 이유로 부호 반전 (실측 2회 연속 반대로 나옴)
        event.flow_classification = "out" if weighted_dy < 0 else "in"
        event.flow_confidence = min(1.0, abs(weighted_dy) / self.flow_scale)

    def _classify_state(self, event: MotionEvent):
        """궤적/플로우는 둘 다 "움직임 방향"을 보는 같은 종류의 신호라 한계가 비슷했다.
        이건 다른 종류의 신호 — 시작 프레임과 끝 프레임을 직접 비교해서 그 자리에
        뭔가 "새로 생겼는지"(더 복잡해짐) "없어졌는지"(더 밋밋해짐)를 본다. 끝 프레임은
        cooldown 이후(손이 완전히 빠져나간 뒤)라 팔 움직임 노이즈가 안 낀 "정적인 결과"다."""
        if not event.start_frame or not event.end_frame:
            event.state_classification, event.state_confidence = "unknown", 0.0
            return
        start_gray = self._to_gray(event.start_frame)
        end_gray = self._to_gray(event.end_frame)
        if start_gray.shape != end_gray.shape:
            event.state_classification, event.state_confidence = "unknown", 0.0
            return

        # 실측해보니 시작~끝 사이에 자동노출(AEC)이 재조정되면서 화면 전체 밝기가
        # 10 이상 통째로 바뀌는 경우가 흔했다 — 그러면 물체랑 상관없이 전체 픽셀의
        # 30%+ 가 "바뀜"으로 잡혀서 박스가 전체 화면이 돼버린다. 전역 밝기 차이(평균
        # 오프셋)를 먼저 빼서, 국소적으로 진짜 달라진 곳만 남긴다.
        global_shift = float(end_gray.mean()) - float(start_gray.mean())
        end_compensated = end_gray.astype(np.float32) - global_shift
        diff = np.abs(start_gray.astype(np.float32) - end_compensated)
        mask = diff > self.motion_threshold
        if mask.sum() < 20:  # 변한 영역이 거의 없음 — 판정 근거 부족
            event.state_classification, event.state_confidence = "unknown", 0.0
            return

        # 시작/끝 프레임 어느 쪽이든 손이 걸려있으면 그 영역은 빼고 본다 — 크롭이
        # 손까지 같이 잡지 않게. 손 뺀 뒤에도 남는 게 있을 때만 쓰고, 다 사라지면
        # (예: 손이 화면 대부분을 가린 컷) 원래 마스크로 폴백해서 판정 자체가
        # 깨지지 않게 한다.
        hand_boxes = self._detect_hand_boxes(event.start_frame) + self._detect_hand_boxes(event.end_frame)
        obj_mask = self._mask_minus_boxes(mask, hand_boxes)
        if obj_mask.sum() >= 20:
            mask = obj_mask

        # 이 박스(시작 vs 끝 "정적인 두 장"의 차이 영역, 손 제외)를 크롭에도 그대로 쓴다.
        # 처음엔 이벤트 내내 움직인 전체 궤적을 합쳐서 박스를 만들었는데, 팔이
        # 프레임을 크게 휘저으면 그 합집합이 화면 대부분을 덮어버려 크롭이 사실상
        # 전체 프레임이 되는 문제가 있었다 (실측으로 확인). 시작/끝 두 장만 비교하면
        # "물체가 실제로 있는 자리"만 좁게 잡힌다.
        event.bbox = self._mask_bbox(mask)

        ys, xs = np.nonzero(mask)
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        start_patch = start_gray[y0:y1, x0:x1]
        end_patch = end_gray[y0:y1, x0:x1]

        # 라플라시안 분산 = "이 영역에 얼마나 윤곽/질감이 많은가" (사진이 얼마나
        # 또렷한지 잴 때 쓰는 흔한 지표를 여기선 "물체가 있을 법한 정도"로 재활용)
        start_detail = cv2.Laplacian(start_patch, cv2.CV_64F).var()
        end_detail = cv2.Laplacian(end_patch, cv2.CV_64F).var()
        total = start_detail + end_detail
        if total < 1e-6:
            event.state_classification, event.state_confidence = "unknown", 0.0
            return
        diff_ratio = (end_detail - start_detail) / total  # -1~1

        if abs(diff_ratio) < self.state_threshold:
            event.state_classification, event.state_confidence = "unknown", 0.0
            return
        # 끝 프레임 쪽이 디테일 많아짐(더 복잡해짐) = 뭔가 새로 생김 = IN
        # 끝 프레임 쪽이 디테일 적어짐(더 밋밋해짐) = 있던 게 사라짐 = OUT
        event.state_classification = "in" if diff_ratio > 0 else "out"
        event.state_confidence = min(1.0, abs(diff_ratio) / 0.3)

    def _classify_carry(self, event: MotionEvent):
        """방향(위/아래) 축을 아예 안 쓰는 판정. 손이 세션 안에서 처음 보였을 때
        옆에 물체가 있었는지(early), 마지막으로 보였을 때 있었는지(late)만 비교한다.
        - 처음엔 없다가(빈손으로 들어감) 나중에 생기면(뭔가 들고 나옴) → 꺼낸 것 → OUT
        - 처음엔 있다가(들고 들어감) 나중에 없어지면(놓고 나옴) → 넣은 것 → IN
        궤적/플로우는 마운트 각도가 바뀌면 부호가 뒤집혀야 해서 실측으로 두 번
        고쳐도 계속 틀렸다는 피드백을 받았다 — 이 신호는 마운트 각도와 무관하다."""
        samples = event.hand_carry_samples
        if len(samples) < 2:
            event.carry_classification, event.carry_confidence = "unknown", 0.0
            return
        n = len(samples)
        k = max(1, n // 3)
        early = float(np.mean([s[1] for s in samples[:k]]))
        late = float(np.mean([s[1] for s in samples[-k:]]))
        total = early + late
        if total < 1e-6:
            event.carry_classification, event.carry_confidence = "unknown", 0.0
            return
        diff_ratio = (late - early) / total  # -1~1
        if abs(diff_ratio) < self.carry_threshold:
            event.carry_classification, event.carry_confidence = "unknown", 0.0
            return
        event.carry_classification = "out" if diff_ratio > 0 else "in"
        event.carry_confidence = min(1.0, abs(diff_ratio) / 0.5)

    # ---- 리드스위치 기반 세션 추적: 문열림→계산시작→(실시간 박스 추적)→문닫힘→판정 ----
    #
    # 이전엔 process_frame()이 픽셀차분 임계값만으로 "지금 움직이기 시작했다/멈췄다"를
    # 추측해서 이벤트 경계를 스스로 잡아야 했다(cooldown_s, max_event_s 같은 휴리스틱
    # 필요). 이제 도어 신호가 "언제부터 언제까지가 한 세션인지"를 정확히 알려주니,
    # 그 안에서는 계속 프레임을 추적만 하면 되고(실시간 박스 표시용), 최종 판정은
    # 문 닫히는 순간 그동안 쌓인 궤적/플로우/시작-끝 비교를 종합해서 한 번만 내린다.

    def start_session(self, frame: bytes, ts: float) -> MotionEvent:
        ev = MotionEvent(id=uuid.uuid4().hex[:10], start_ts=ts)
        ev.start_frame = frame
        self.session_event = ev
        self.session_prev_gray = self._to_gray(frame)
        return ev

    def track_session_frame(self, frame: bytes, ts: float) -> dict:
        """세션 진행 중 프레임마다 호출. 반환값의 bbox는 "이번 프레임에서 방금 바뀐
        곳"이라 프론트엔드가 실시간 추적 박스로 그대로 그리면 된다 (object tracking
        화면처럼) — 세션 전체 판정용 궤적/플로우/손-소지물 샘플도 여기서 같이 쌓인다.

        문이 열리는 순간엔 "닫힌 문 → 열린 내부"로 화면 전체가 확 바뀌는 큰 변화가
        있는데, 이건 손이나 물체 움직임이 아니라 그냥 문이 열리며 선반 안쪽이
        드러나는 것뿐이다. 이걸 물체 움직임으로 착각해서 선반 위 정적인 물건까지
        크롭 박스에 잡히는 문제가 실측으로 확인됐다 — 그래서 이 세션에서 손이
        "한 번이라도" 감지되기 전까지는 궤적/플로우/크롭 어느 것도 쌓지 않는다."""
        ev = self.session_event
        if ev is None or self.session_prev_gray is None:
            return {"bbox": None, "ratio": 0.0, "hand_seen": False, "hand_boxes": [], "crop": None}
        gray = self._to_gray(frame)
        if gray.shape != self.session_prev_gray.shape:
            self.session_prev_gray = gray
            return {"bbox": None, "ratio": 0.0, "hand_seen": ev.hand_seen, "hand_boxes": [], "crop": None}

        diff = np.abs(gray.astype(np.int16) - self.session_prev_gray.astype(np.int16))
        mask = diff > self.motion_threshold
        ratio = float(mask.mean())  # 원본 마스크 기준 — "지금 뭔가 움직이는 중"인지는 그대로 판단
        bbox = None
        hand_boxes: list = []
        crop = None

        if ratio > self.pixel_ratio:
            hand_boxes = self._detect_hand_boxes(frame)
            if hand_boxes and not ev.hand_seen:
                ev.hand_seen = True
                ev.hand_first_ts = ts

            if not ev.hand_seen:
                # 아직 손이 한 번도 안 보였다 — 문이 열리며 내부가 드러나는 전환
                # 구간으로 간주하고 이번 프레임은 통째로 건너뛴다.
                self.session_prev_gray = gray
                return {"bbox": None, "ratio": ratio, "hand_seen": False, "hand_boxes": [], "crop": None}

            # 움직인 영역에서 손 부분을 빼서, 남는 게 있으면 그게 "물체 후보"다.
            obj_mask = self._mask_minus_boxes(mask, hand_boxes)
            obj_score = int(obj_mask.sum())
            ev.hand_carry_samples.append((ts, obj_score))

            if obj_score >= 8:
                cx, cy = self._centroid(obj_mask)
                bbox = self._mask_bbox(obj_mask)
                ev.trajectory.append((ts, cx, cy))
                dy_norm, mag_norm = self._flow_dy(self.session_prev_gray, gray, obj_mask)
                ev.flow_samples.append((ts, dy_norm, mag_norm))
                crop = self._crop_frame(frame, bbox)
                ev.frames.append({
                    "ts": ts, "bbox": bbox, "ratio": ratio, "obj_score": obj_score,
                    "hand_count": len(hand_boxes), "crop": crop,
                })
                if len(ev.frames) > self.max_session_frames:
                    ev.frames.pop(0)

        self.session_prev_gray = gray
        return {"bbox": bbox, "ratio": ratio, "hand_seen": ev.hand_seen, "hand_boxes": hand_boxes, "crop": crop}

    def end_session(self, frame: bytes, ts: float) -> MotionEvent | None:
        ev = self.session_event
        self.session_event = None
        self.session_prev_gray = None
        if ev is None:
            return None
        ev.end_ts = ts
        ev.end_frame = frame

        self._classify(ev)        # 궤적 회귀 (세션 전체) — 방향 축 가정, 참고용으로 계속 계산
        self._classify_flow(ev)   # 옵티컬 플로우 가중평균 (세션 전체) — 마찬가지로 방향 축 가정
        self._classify_state(ev)  # 시작 vs 끝 프레임 비교 — 손 등장 이전 프레임까지 포함되므로 참고용
        self._classify_carry(ev)  # 손-소지물 비교 — 방향 축 없이 판정, 아래서 최우선으로 채택

        # 궤적/플로우는 마운트 각도에 따라 부호가 뒤집혀야 해서 실측으로 두 번
        # 고쳐도 계속 틀렸다는 피드백을 받았다. carry(손-소지물 비교)는 방향
        # 축이 아예 없는 신호라 최우선으로 채택하고, 나머지는 비교/폴백용으로 남긴다.
        if ev.carry_classification != "unknown":
            ev.final_classification, ev.final_confidence, ev.final_source = ev.carry_classification, ev.carry_confidence, "carry"
        elif ev.flow_classification != "unknown":
            ev.final_classification, ev.final_confidence, ev.final_source = ev.flow_classification, ev.flow_confidence, "flow"
        elif ev.classification != "unknown":
            ev.final_classification, ev.final_confidence, ev.final_source = ev.classification, ev.confidence, "trajectory"
        elif ev.state_classification != "unknown":
            ev.final_classification, ev.final_confidence, ev.final_source = ev.state_classification, ev.state_confidence, "state"
        else:
            ev.final_classification, ev.final_confidence, ev.final_source = "unknown", 0.0, "none"

        if ev.bbox:
            ev.start_crop = self._crop_frame(ev.start_frame, ev.bbox)
            ev.end_crop = self._crop_frame(ev.end_frame, ev.bbox)

        # 세션 내내 손-제외 물체 후보가 가장 뚜렷했던(obj_score 최대) 프레임을
        # "가장 신뢰할 수 있는 물체 크롭"으로 뽑는다. start/end 두 장짜리 비교와
        # 달리 이건 5초 세션 내내 실시간으로 이미 찍어둔 것 중 고르는 거라 더
        # 빠르고(문 닫히길 기다릴 필요 없음), 손이 실제로 뭔가를 들고 있던
        # 순간의 크롭이라 배경 선반 물건이 섞일 가능성도 적다.
        if ev.frames:
            best = max(ev.frames, key=lambda fr: fr["obj_score"])
            ev.best_crop = best["crop"]
            ev.best_bbox = best["bbox"]
            ev.best_ts = best["ts"]

        self.events.append(ev)
        if len(self.events) > self.max_kept_events:
            self.events.pop(0)
        return ev

    def _finish_event(self, ev: MotionEvent, end_ts: float, end_frame: bytes) -> MotionEvent | None:
        ev.end_ts = end_ts
        ev.end_frame = end_frame
        if ev.end_ts - ev.start_ts < self.min_event_s:
            return None  # 너무 짧은 흔들림(노이즈) — 목록에 안 남김
        self._classify(ev)
        self._classify_flow(ev)
        self._classify_state(ev)

        # 실측 비교 결과 옵티컬 플로우가 더 정확해서 이걸 메인으로 채택.
        # 플로우가 "모름"으로 나온 경우에만(예: 이벤트가 너무 짧아 플로우 샘플이
        # 거의 없을 때) 궤적 판정으로 폴백 — 둘 다 계산은 항상 해둬서 로그에서
        # 계속 비교/재검증할 수 있게 유지한다.
        if ev.flow_classification != "unknown":
            ev.final_classification = ev.flow_classification
            ev.final_confidence = ev.flow_confidence
            ev.final_source = "flow"
        elif ev.classification != "unknown":
            ev.final_classification = ev.classification
            ev.final_confidence = ev.confidence
            ev.final_source = "trajectory"
        else:
            ev.final_classification = "unknown"
            ev.final_confidence = 0.0
            ev.final_source = "none"

        if ev.bbox:
            if ev.start_frame:
                ev.start_crop = self._crop_frame(ev.start_frame, ev.bbox)
            if ev.end_frame:
                ev.end_crop = self._crop_frame(ev.end_frame, ev.bbox)

        self.events.append(ev)
        if len(self.events) > self.max_kept_events:
            self.events.pop(0)
        return ev

    def process_frame(self, jpeg_bytes: bytes, ts: float | None = None) -> dict:
        ts = ts if ts is not None else time.time()
        gray = self._to_gray(jpeg_bytes)
        result = {"ts": ts, "state": self.state, "motion": False, "ratio": 0.0,
                  "event_started": False, "event_ended": False, "event": None}

        if self.prev_gray is not None and self.prev_gray.shape == gray.shape:
            diff = np.abs(gray.astype(np.int16) - self.prev_gray.astype(np.int16))
            mask = diff > self.motion_threshold
            ratio = float(mask.mean())
            result["ratio"] = ratio

            if ratio > self.pixel_ratio:
                result["motion"] = True
                cx, cy = self._centroid(mask)
                if self.state == "idle":
                    self.state = "motion"
                    self.current_event = MotionEvent(id=uuid.uuid4().hex[:10], start_ts=ts)
                    self.current_event.start_frame = jpeg_bytes
                    result["event_started"] = True
                self.current_event.trajectory.append((ts, cx, cy))
                dy_norm, mag_norm = self._flow_dy(self.prev_gray, gray, mask)
                self.current_event.flow_samples.append((ts, dy_norm, mag_norm))
                # bbox는 이벤트가 끝날 때 _classify_state()가 시작/끝 프레임 비교로
                # 다시(더 좁게) 계산해서 채운다 — 여기서 궤적 전체를 합집합으로
                # 누적하지 않는다 (그러면 크롭이 화면 전체가 돼버림, 실측으로 확인됨).
                self.last_motion_ts = ts

                # 계속 움직임이 이어져서 cooldown이 안 걸려도, 너무 오래 끌면
                # (여러 동작이 섞였을 가능성) 여기서 끊고 바로 다음 이벤트를 새로 연다.
                if ts - self.current_event.start_ts > self.max_event_s:
                    finished = self._finish_event(self.current_event, ts, jpeg_bytes)
                    if finished:
                        result["event_ended"] = True
                        result["event"] = finished
                    new_ev = MotionEvent(id=uuid.uuid4().hex[:10], start_ts=ts)
                    new_ev.start_frame = jpeg_bytes
                    new_ev.trajectory.append((ts, cx, cy))
                    self.current_event = new_ev

            elif self.state == "motion" and ts - self.last_motion_ts > self.cooldown_s:
                ev = self.current_event
                self.state = "idle"
                self.current_event = None
                finished = self._finish_event(ev, self.last_motion_ts, jpeg_bytes)
                if finished:
                    result["event_ended"] = True
                    result["event"] = finished

        self.prev_gray = gray
        result["state"] = self.state
        return result
