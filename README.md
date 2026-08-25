# Peak-Test — 냉장고 용기 인식

XIAO ESP32-S3 Sense 카메라로 용기(텀블러/반찬 용기/생수병)를 실시간으로 인식하는 프로젝트.
YOLO-World로 물체를 탐지하고, DINOv2 임베딩 + 학습된 분류기로 종류를 판별한다.

## 준비

```bash
pip install -r requirements.txt
```

- YOLO-World 가중치(`yolov8s-worldv2.pt`, `yolov8m-worldv2.pt`)는 최초 실행 시 `ultralytics`가
  자동으로 다운로드한다 (용량이 커서 저장소에는 포함하지 않음).
- ESP32(XIAO ESP32-S3 Sense)는 `01_container_collector/01_container_collector.ino` 스케치를
  업로드하면 자체 Wi-Fi 핫스팟(SSID `ESP32-Camera`, 비밀번호 `12345678`)이 된다. PC를 이 Wi-Fi에
  연결한 뒤 아래 서버를 실행한다.

## 실행

- 단일 물체 실시간 분류 (포트 5003):
  ```powershell
  powershell -File run_browser_category_realtime.ps1
  ```
- 다중 물체(최대 6개) 동시 실시간 분류 (포트 5005):
  ```powershell
  powershell -File run_browser_category_realtime_multi.ps1
  ```

실행 후 브라우저에서 `http://127.0.0.1:5003` 또는 `http://127.0.0.1:5005` 접속.

## 학습된 모델

- `category_classifier.joblib` — 종류 분류기(텀블러/반찬 용기/생수병), DINOv2 임베딩 기반.
  바로 사용 가능하며, 재학습이 필요하면 `prepare_category_dataset.py` → `train_category_classifier.py`
  순서로 실행 (학습 데이터: `category_dataset_prepared_v2/`).

## 프로젝트 전체 구조

용기 종류 분류 외에도 같은 냉장고 프로젝트의 이전 단계(YOLO 위치 탐지, DINOv2 기반 개체
재식별/자동 등록 DB, 여러 실시간 프로토타입)가 함께 들어있다. 전체 배경과 각 파일의 역할,
진행 이력은 `project_handoff.md`를 참고.
