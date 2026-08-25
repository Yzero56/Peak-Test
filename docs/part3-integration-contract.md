# 3번 파트 연동 계약

백엔드 주소는 개발 환경에서 `http://localhost:8000`, API prefix는 `/api/v1`이다.

## 프론트엔드·대시보드 파트

### 대시보드 조회

```http
GET /api/v1/dashboard/summary
```

응답의 `items`에서 바로 사용할 수 있는 값:

```json
{
  "display_name": "우유",
  "expires_at": "2026-08-28",
  "days_remaining": 4,
  "expiry_status": "fresh",
  "can_cook": true,
  "requires_confirmation": false
}
```

상태 값은 `fresh`, `expiring_soon`, `expired`, `unknown`이다.

### 식품 상세 상태

```http
GET /api/v1/food-items/{food_item_id}/expiry
GET /api/v1/food-items/{food_item_id}/cooking-status
```

`expired`는 조리 불가, `unknown`은 유통기한 확인 필요로 표시한다. `expiring_soon`은 조리 가능하지만 확인 경고를 표시한다.

## ESP32·이미지 입력 파트

카메라 장치는 직접 OpenAI API를 호출하지 않는다. 촬영 이미지를 HTTP multipart로 백엔드에 전달한다.

```http
POST /api/v1/food-images
Content-Type: multipart/form-data
file=<image>
```

응답의 `id`로 분석 작업을 요청한다.

```http
POST /api/v1/analysis-jobs
Content-Type: application/json

{"image_id": "<image-id>"}
```

그 다음 작업 상태를 조회한다.

```http
GET /api/v1/analysis-jobs/{job_id}
```

`status=succeeded`이면 분석 결과를 확인하고 적용한다.

```http
POST /api/v1/analysis-jobs/{job_id}/apply
```

## 실행 정보

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API 문서: `http://localhost:8000/docs`
- 브라우저 대시보드: `http://localhost:8000/dashboard/`
- DB 상태: `http://localhost:8000/api/v1/health/db`

프론트엔드 개발 서버 주소가 다르면 `.env`의 `CORS_ORIGINS`에 쉼표로 추가한다.
