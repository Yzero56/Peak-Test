# 3번 파트 백엔드 설계

## 1. 권장 기술 스택

| 영역 | 기술 | 선택 이유 |
| --- | --- | --- |
| API | Python 3.12, FastAPI | 비동기 처리와 자동 OpenAPI 문서 지원 |
| 검증 | Pydantic v2 | 요청·응답 타입 검증 및 날짜 처리 |
| ORM/마이그레이션 | SQLAlchemy 2, Alembic | PostgreSQL과의 안정적인 연동 |
| DB | PostgreSQL 16 | 날짜, JSONB, 인덱스, 트랜잭션 지원 |
| 이미지 저장 | MinIO 또는 S3 호환 스토리지 | DB에 이미지 바이너리를 저장하지 않음 |
| VLM | OpenAI 호환 멀티모달 API 어댑터 | 모델 교체 시 API 계층 변경 최소화 |
| 작업 큐 | 초기에는 FastAPI BackgroundTasks, 운영 시 Redis + Celery/RQ | VLM 호출은 긴 작업이므로 API 요청과 분리 |
| 테스트 | pytest, httpx | 서비스·API 통합 테스트 |

초기 개발에서는 SQLite로 시작할 수 있지만 JSONB, 동시성, 운영 환경을 고려하면 최종 DB는 PostgreSQL을 사용한다.

## 2. 핵심 처리 흐름

1. 카메라 또는 웹 클라이언트가 음식 이미지를 업로드한다.
2. 서버가 이미지를 스토리지에 저장하고 `analysis_job`을 생성한다.
3. 백그라운드 작업이 VLM에 이미지를 전달한다.
4. VLM이 음식명, 제조일, 개봉일, 표시 유통기한, 보관 방법을 JSON으로 추출한다.
5. 서버가 날짜 형식을 정규화하고 신뢰도와 원본 응답을 저장한다.
6. 표시 유통기한이 없으면 식품 종류별 `shelf_life_rule`과 제조일·개봉일을 이용해 추정한다.
7. 재고의 `expires_at`과 현재 시각을 비교해 `fresh`, `expiring_soon`, `expired` 상태를 반환한다.

VLM이 날짜를 읽지 못한 경우 날짜를 추측하지 않고 `null`로 저장한다. 추정값은 반드시 `date_source=estimated`와 `confidence`로 구분한다.

## 3. 데이터베이스 스키마

### `food_products`

식품 종류의 기준 정보다. 예: 우유, 김치, 닭가슴살.

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 식품 종류 ID |
| `name` | VARCHAR(200) | NOT NULL | 표준 식품명 |
| `category` | VARCHAR(50) | NULL | dairy, meat, vegetable 등 |
| `default_storage` | VARCHAR(30) | NULL | room, refrigerator, freezer |
| `created_at` | TIMESTAMPTZ | NOT NULL | 생성 시각 |

### `food_items`

사용자가 실제로 보관 중인 개별 식품이다.

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 재고 ID |
| `product_id` | UUID | FK, NULL | `food_products.id` |
| `display_name` | VARCHAR(200) | NOT NULL | 화면 표시명 |
| `quantity` | NUMERIC(10,2) | NOT NULL DEFAULT 1 | 수량 |
| `unit` | VARCHAR(20) | NULL | 개, g, ml 등 |
| `storage_type` | VARCHAR(30) | NOT NULL | 보관 방식 |
| `purchased_at` | DATE | NULL | 구매일 |
| `opened_at` | DATE | NULL | 개봉일 |
| `manufactured_at` | DATE | NULL | 제조일 |
| `expires_at` | DATE | NULL | 최종 유통기한 또는 소비기한 |
| `date_source` | VARCHAR(20) | NOT NULL | label, estimated, manual, unknown |
| `confidence` | NUMERIC(4,3) | NULL | 0.000~1.000 |
| `status` | VARCHAR(20) | NOT NULL | active, consumed, discarded |
| `notes` | TEXT | NULL | 사용자 메모 |
| `created_at` | TIMESTAMPTZ | NOT NULL | 생성 시각 |
| `updated_at` | TIMESTAMPTZ | NOT NULL | 수정 시각 |

인덱스: `(status, expires_at)`, `(storage_type, status)`. `expires_at`이 없는 항목도 저장 가능하지만 대시보드에서는 `unknown` 상태로 표시한다.

### `food_images`

분석에 사용한 원본 및 결과 이미지의 메타데이터다.

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 이미지 ID |
| `food_item_id` | UUID | FK, NULL | 연결된 재고 |
| `object_key` | VARCHAR(500) | NOT NULL | 스토리지 경로 |
| `content_type` | VARCHAR(100) | NOT NULL | image/jpeg 등 |
| `sha256` | CHAR(64) | NOT NULL | 중복 확인용 해시 |
| `created_at` | TIMESTAMPTZ | NOT NULL | 업로드 시각 |

### `analysis_jobs`

VLM 분석 작업의 상태와 결과를 추적한다.

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 작업 ID |
| `image_id` | UUID | FK, NOT NULL | 분석 이미지 |
| `status` | VARCHAR(20) | NOT NULL | queued, processing, succeeded, failed |
| `model` | VARCHAR(100) | NOT NULL | 사용 모델명 |
| `result` | JSONB | NULL | 정규화 전 VLM 결과 |
| `needs_review` | BOOLEAN | NOT NULL DEFAULT FALSE | 낮은 신뢰도 또는 날짜 검토 필요 여부 |
| `error_code` | VARCHAR(50) | NULL | 실패 코드 |
| `started_at` | TIMESTAMPTZ | NULL | 시작 시각 |
| `finished_at` | TIMESTAMPTZ | NULL | 종료 시각 |
| `created_at` | TIMESTAMPTZ | NOT NULL | 생성 시각 |

### `shelf_life_rules`

표시 날짜가 없을 때 사용하는 추정 규칙이다. 운영자가 수정할 수 있게 별도 테이블로 둔다.

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 규칙 ID |
| `category` | VARCHAR(50) | NOT NULL | 식품 카테고리 |
| `storage_type` | VARCHAR(30) | NOT NULL | 보관 방식 |
| `days_after_open` | INTEGER | NULL | 개봉 후 보관 가능 일수 |
| `days_after_manufacture` | INTEGER | NULL | 제조 후 보관 가능 일수 |
| `source` | VARCHAR(200) | NULL | 규칙 출처 |
| `active` | BOOLEAN | NOT NULL DEFAULT TRUE | 사용 여부 |

## 4. API 설계

기본 prefix는 `/api/v1`로 한다. 모든 시간은 UTC ISO 8601, 날짜는 `YYYY-MM-DD`를 사용한다.

### 식품 등록 및 조회

`POST /api/v1/food-items`

```json
{
  "display_name": "서울우유 1L",
  "storage_type": "refrigerator",
  "quantity": 1,
  "unit": "개",
  "purchased_at": "2026-08-21",
  "opened_at": null,
  "expires_at": "2026-08-28",
  "date_source": "manual"
}
```

응답: `201 Created`, 생성된 `food_item` 전체.

`GET /api/v1/food-items?status=active&storage_type=refrigerator&sort=expires_at`

응답에는 `days_remaining`과 `expiry_status`를 계산해 포함한다.

`GET /api/v1/food-items/{food_item_id}`

`PATCH /api/v1/food-items/{food_item_id}`

`DELETE /api/v1/food-items/{food_item_id}`

삭제 대신 기본적으로 `status=discarded`로 변경하는 soft delete를 사용한다.

### 이미지 업로드 및 VLM 분석

`POST /api/v1/food-images`

- `multipart/form-data`의 `file` 필드 사용
- 허용 형식: JPEG, PNG, WEBP
- 용량 제한: 10 MB
- 응답: `201 Created`와 `image_id`, `object_key`

`POST /api/v1/analysis-jobs`

```json
{
  "image_id": "7b7d4f42-2fb4-4d0d-9c9a-000000000001",
  "food_item_id": null
}
```

응답: `202 Accepted`

```json
{
  "job_id": "0d7c0c45-2fb4-4d0d-9c9a-000000000002",
  "status": "queued"
}
```

`GET /api/v1/analysis-jobs/{job_id}`

성공 시 `extracted`에 다음 필드를 반환한다.

```json
{
  "food_name": "우유",
  "category": "dairy",
  "manufactured_at": "2026-08-10",
  "opened_at": null,
  "labeled_expires_at": "2026-08-28",
  "storage_type": "refrigerator",
  "confidence": 0.94,
  "date_source": "label"
}
```

`POST /api/v1/analysis-jobs/{job_id}/apply`

분석 결과를 검토한 뒤 `food_items`에 반영한다. 자동 반영하지 않고 이 확인 단계를 두어 VLM 오인식으로 인한 잘못된 유통기한 등록을 방지한다.

### 대시보드용 조회

`GET /api/v1/dashboard/summary`

```json
{
  "total_active": 12,
  "fresh": 8,
  "expiring_soon": 3,
  "expired": 1,
  "unknown_expiry": 0,
  "items": []
}
```

`GET /api/v1/food-items/{food_item_id}/expiry`

```json
{
  "expires_at": "2026-08-28",
  "days_remaining": 7,
  "expiry_status": "fresh",
  "date_source": "label",
  "confidence": 0.94
}
```

상태 기준은 `expired: days_remaining < 0`, `expiring_soon: 0 <= days_remaining <= 3`, `fresh: days_remaining > 3`, `unknown: expires_at is null`로 둔다. 이 기준은 환경변수 또는 설정 테이블로 변경 가능하게 구현한다.

## 5. VLM 출력 계약

모델 프롬프트는 자유로운 문장이 아니라 아래 JSON Schema를 강제한다.

```json
{
  "food_name": "string|null",
  "category": "string|null",
  "manufactured_date_text": "string|null",
  "expiration_date_text": "string|null",
  "manufactured_at": "YYYY-MM-DD|null",
  "labeled_expires_at": "YYYY-MM-DD|null",
  "storage_type": "room|refrigerator|freezer|null",
  "confidence": "number 0..1",
  "notes": "string|null"
}
```

날짜 문자열이 `2026.08.28`, `26.08.28`, `20260828`처럼 들어와도 서버의 파서가 하나의 날짜로 정규화한다. 연도 해석이 불확실하면 자동 변환하지 않고 검토 대상으로 둔다.

## 6. 보안 및 운영 기준

- 이미지 파일은 확장자가 아니라 실제 MIME 타입과 크기를 검증한다.
- VLM API 키는 `.env`에 두고 저장소에 커밋하지 않는다.
- 업로드 이미지의 원본 URL을 외부에 그대로 노출하지 않고 만료되는 signed URL을 사용한다.
- VLM 원본 응답에는 개인정보가 포함될 수 있으므로 접근 권한을 제한한다.
- 실패한 작업은 최대 3회 재시도하고, 잘못된 이미지 형식이나 날짜 파싱 실패는 재시도하지 않는다.
- API 오류는 `400` 입력 오류, `404` 리소스 없음, `409` 상태 충돌, `422` 검증 오류, `502` VLM 외부 오류로 구분한다.

## 7. 구현 순서

1. SQLAlchemy 모델과 Alembic 초기 마이그레이션 작성
2. `food-items` CRUD와 만료 상태 계산 구현
3. 이미지 업로드 및 MinIO/S3 저장 구현
4. VLM adapter와 구조화된 출력 검증 구현
5. 분석 job 백그라운드 처리 및 결과 적용 API 구현
6. pytest로 날짜 계산, VLM 실패, 중복 이미지, API 권한을 검증

## 8. 다음 단계 상세 설계

### 8.1 MVP 범위

1차 구현에서는 사용자 인증, 여러 사용자 계정, 실시간 알림은 제외한다. 먼저 한 개의 주방 또는 냉장고를 기준으로 아래 흐름을 완성한다.

`이미지 업로드 -> VLM 분석 -> 결과 확인 -> 식품 등록 -> 대시보드 조회`

카메라 장치 연동은 이미지 업로드 API를 호출하는 클라이언트로 취급한다. 따라서 백엔드는 카메라 종류와 독립적으로 개발할 수 있다.

### 8.2 권장 디렉터리 구조

```text
app/
  main.py
  core/
    config.py          # 환경변수와 앱 설정
    database.py        # async engine, session
  models/
    food.py            # SQLAlchemy 모델
    analysis.py
  schemas/
    food.py            # Pydantic 요청·응답 모델
    analysis.py
  api/
    routes/
      food_items.py
      images.py
      analysis_jobs.py
      dashboard.py
  services/
    food_service.py    # 식품 CRUD와 상태 계산
    analysis_service.py
    expiry_service.py  # 유통기한 계산 규칙
    storage_service.py # MinIO/S3 업로드
    vlm/
      base.py          # VLMAdapter Protocol
      openai_adapter.py
  workers/
    analysis_worker.py
alembic/
tests/
  test_expiry_service.py
  test_food_items_api.py
  test_analysis_api.py
```

라우터는 HTTP 입출력만 담당하고, DB 조회·유통기한 계산·VLM 호출은 `services`에 둔다. 이렇게 분리하면 VLM 없이도 유통기한 계산과 API 테스트를 실행할 수 있다.

### 8.3 핵심 서비스 인터페이스

```python
class VLMAdapter(Protocol):
    async def extract_food_info(self, image_url: str) -> ExtractedFoodInfo:
        """이미지에서 구조화된 식품 정보를 추출한다."""
```

```python
class ExpiryService:
    def calculate(
        self,
        labeled_expires_at: date | None,
        manufactured_at: date | None,
        opened_at: date | None,
        category: str | None,
        storage_type: str | None,
    ) -> ExpiryResult:
        ...
```

유통기한 우선순위는 다음과 같다.

1. 사용자가 직접 입력한 날짜
2. 제품 라벨에서 추출한 날짜
3. 제조일 + 제조 후 보관 규칙
4. 개봉일 + 개봉 후 보관 규칙
5. 계산 불가: `unknown`

단, 라벨 날짜가 있으면 제조일이나 개봉일 기반의 추정값으로 덮어쓰지 않는다.

### 8.4 분석 작업 상태 전이

```text
queued -> processing -> succeeded
                   -> failed
```

- `queued`: 이미지와 작업이 생성된 상태
- `processing`: VLM 호출 중인 상태
- `succeeded`: 구조화·날짜 검증까지 완료된 상태
- `failed`: 재시도 가능한 외부 오류 또는 최종 실패

`POST /analysis-jobs/{id}/apply`는 `succeeded` 상태에서만 허용한다. 적용이 완료된 작업을 다시 적용할 때는 `409 Conflict`를 반환하거나 동일 결과를 반환하는 방식 중 하나를 선택해야 하며, MVP에서는 `409 Conflict`를 사용한다.

### 8.5 VLM 프롬프트와 신뢰도 처리

VLM에는 다음 규칙을 시스템 프롬프트로 전달한다.

- 이미지에 보이는 정보만 반환한다.
- 날짜를 추측하거나 보정하지 않는다.
- 읽을 수 없는 값은 `null`로 반환한다.
- 반드시 지정된 JSON Schema만 반환한다.
- 날짜와 함께 원문 날짜 문자열을 반환한다.

서버는 VLM의 `confidence`를 그대로 신뢰하지 않고 다음 검사를 수행한다.

- `0 <= confidence <= 1`인지 확인
- `expiration_date_text`와 정규화 날짜가 일치하는지 확인
- 유통기한이 제조일보다 빠르지 않은지 확인
- 과거 날짜라도 라벨에 실제로 표시되어 있으면 저장하되 `expired`로 표시

신뢰도가 `0.75` 미만이거나 날짜 파싱에 실패하면 작업은 성공시키되 `needs_review=true`로 표시한다. 날짜를 임의로 계산하지 않는다.

### 8.6 API 구현 우선순위

#### 1단계: DB와 식품 CRUD

- SQLAlchemy 모델 작성
- Alembic 초기 마이그레이션
- `POST`, `GET`, `PATCH`, soft delete 구현
- `days_remaining`, `expiry_status` 단위 테스트

#### 2단계: 이미지와 분석 작업

- 파일 MIME 타입·용량 검증
- 로컬 저장소를 사용한 개발용 `StorageService` 구현
- `analysis_jobs` 생성 및 상태 조회
- 먼저 `MockVLMAdapter`로 전체 흐름 검증

#### 3단계: 실제 VLM 연결

- OpenAI 호환 API adapter 구현
- timeout, 재시도, 응답 JSON 검증
- 원본 응답과 정규화 결과 저장
- 분석 결과 적용 API 구현

#### 4단계: 대시보드 연동

- 요약 통계 API 구현
- 만료 임박 정렬 조회
- 프론트엔드가 사용할 응답 예시와 OpenAPI 문서 확인

### 8.7 개발 환경 환경변수

```env
APP_ENV=development
DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/food_expiry
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=./data/uploads
VLM_PROVIDER=mock
VLM_MODEL=
VLM_API_KEY=
VLM_BASE_URL=
EXPIRING_SOON_DAYS=3
```

개발 초기에는 `VLM_PROVIDER=mock`, `STORAGE_BACKEND=local`로 설정해 외부 서비스 없이 API를 검증한다. 실제 배포 시에만 PostgreSQL, S3/MinIO, VLM API 설정으로 교체한다.

### 8.8 완료 기준

- 이미지 하나로 분석 작업을 생성하고 상태를 조회할 수 있다.
- Mock VLM 결과가 `food_items`로 적용된다.
- 라벨 날짜가 있으면 그 날짜가 최종 날짜로 저장된다.
- 날짜가 없으면 `unknown` 상태로 남고 임의 날짜가 생성되지 않는다.
- 만료 임박 기준과 음수 날짜가 테스트로 검증된다.
- OpenAPI 문서(`/docs`)에서 모든 MVP API를 확인할 수 있다.

## 9. Alembic 사용법

가상환경을 만든 뒤 의존성을 설치한다.

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
```

PostgreSQL이 실행 중이고 `DATABASE_URL`이 설정된 상태에서 마이그레이션을 적용한다.

```bash
alembic upgrade head
```

모델 변경 후 새 마이그레이션을 생성한다.

```bash
alembic revision --autogenerate -m "describe change"
```

현재 초기 리비전은 `alembic/versions/20260821_0001_initial.py`다. 적용 전 생성될 SQL을 확인하려면 다음 명령을 사용한다.

```bash
alembic upgrade head --sql
```
