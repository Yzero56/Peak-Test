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
- 개별 물건(인스턴스) 다중 인식 — 학습해둔 실사용 물건 12종(달걀곽/당근/라떼/반찬용기/밥용기/
  사이다/스팸/아메리카노/우유/종이팩음료/콜라/파&마늘)을 화면에 여러 개 있어도 각각 구분 (포트 5007):
  ```bash
  python browser_instance_realtime_multi.py
  ```

- 주방 재료(양파/대파/당근/김치) 다중 인식 — 하늘에서 수직으로 내려다보는 카메라 전용,
  냉장고 용기 인식과는 별개 프로그램 (포트 5009):
  ```bash
  python browser_pantry_realtime_multi.py
  ```
- 주방 재료 인식 + 신규 등록 — 위와 같은 인식에 더해, 처음 보는 재료면 용기 단위로
  자동 등록해 SQLite(`pantry_registry.db`)에 기록하는 스트리밍 서버 (포트 5010).
  당근/대파/양파 → `A용기`, 김치 → `김치용기`로 자동 분류 등록되며, 당근(주황)/대파(초록)/
  양파(흰색+둥근 모양)는 분류기 확률이 낮아도 색상·모양으로 보정하는 안전장치가 들어있다:
  ```bash
  python browser_pantry_registration.py
  ```

실행 후 브라우저에서 `http://127.0.0.1:5003`, `5005`, `5007`, `5009`, `5010` 중 해당 주소로 접속.

## 학습된 모델

- `category_classifier.joblib` — 종류 분류기(텀블러/반찬 용기/생수병), DINOv2 임베딩 기반.
  바로 사용 가능하며, 재학습이 필요하면 `prepare_category_dataset.py` → `train_category_classifier.py`
  순서로 실행 (학습 데이터: `category_dataset_prepared_v2/`).
- `instance_classifier.joblib` — 실사용 물건 12종 개별 인식 분류기, DINOv2 임베딩 기반.
  바로 사용 가능하며, 새 물건을 추가/재학습하려면:
  1. `python browser_instance_collector.py` (포트 5006)로 물건 하나씩 냉장고에 넣고 라벨별로 사진 촬영
     (`instance_dataset_raw/<라벨>/`에 저장, 저장소에는 포함 안 됨 — 각자 촬영 필요)
  2. `python prepare_instance_dataset.py` — YOLO-World로 자동 크롭해 `instance_dataset_prepared/` 생성
  3. `python train_instance_classifier.py` — `instance_classifier.joblib` 재생성
  4. 자동 크롭이 실패한 사진은 `python manual_crop_tool.py`로 마우스 드래그해 수동으로 잘라
     보완할 수 있다 (`instance_dataset_manual_crop/<라벨>/`에 저장).
- `pantry_classifier.joblib` — 주방 재료 4종(양파/대파/당근/김치) 분류기, DINOv2 임베딩 기반.
  실제 시연에 쓸 용기·조명 조건 그대로 촬영해 학습했다. 재학습하려면:
  1. `python pantry_instance_collector.py` (포트 5008)로 재료 하나씩 라벨 버튼 클릭 후 촬영
     (`pantry_dataset_raw/<라벨>/`에 저장, 저장소에는 포함 안 됨)
  2. `python prepare_pantry_dataset.py` → `python train_pantry_classifier.py`

## 프로젝트 전체 구조

용기 종류 분류 외에도 같은 냉장고 프로젝트의 이전 단계(YOLO 위치 탐지, DINOv2 기반 개체
재식별/자동 등록 DB, 여러 실시간 프로토타입)가 함께 들어있다. 전체 배경과 각 파일의 역할,
진행 이력은 `project_handoff.md`를 참고.
