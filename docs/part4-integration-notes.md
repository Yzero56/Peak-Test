# 4번 파트 연동 메모

## 확인된 현재 구조

4번 파트 `HJ` 브랜치의 Expo 앱은 현재 자체 백엔드를 사용한다.

- 앱: Expo + React Native + NativeWind
- 기존 API base: 설정 화면에서 입력
- 기존 재고 API: `/api/inventory`
- 기존 스캔 API: `/api/scan-candidates`
- 기존 인증 헤더: `X-App-Token`
- 기존 식품 ID: 숫자형
- 기존 저장소: 4번 파트 백엔드의 SQLite

우리 3번 파트 백엔드는 별도 계약을 사용한다.

- API base: `/api/v1`
- 식품 목록: `GET /api/v1/food-items`
- 식품 생성: `POST /api/v1/food-items`
- 이미지 업로드: `POST /api/v1/food-images`
- VLM 작업 생성: `POST /api/v1/analysis-jobs`
- 대시보드: `GET /api/v1/dashboard/summary`
- 조리 가능 여부: `GET /api/v1/food-items/{id}/cooking-status`
- 식품 ID: UUID
- 인증: 현재 개발 단계에서는 없음

## 권장 연결 방식

4번 파트 앱의 목업 데이터를 유지하는 대신, 앱의 `src/lib/api.ts`를 우리 API 계약에 맞추는 방식을 권장한다. 두 백엔드를 동시에 사용하면 재고 데이터가 분리되므로 사용하지 않는다.

### 화면별 API 매핑

| 4번 앱 기능 | 사용할 3번 API |
| --- | --- |
| 재고 목록 | `GET /api/v1/food-items?status=active` |
| 재고 추가 | `POST /api/v1/food-items` |
| 재고 수정 | `PATCH /api/v1/food-items/{id}` |
| 재고 삭제 | `DELETE /api/v1/food-items/{id}` |
| D-day | 응답의 `days_remaining`, `expiry_status` |
| 조리 가능 표시 | 응답의 `can_cook`, `requires_confirmation` |
| 대시보드 요약 | `GET /api/v1/dashboard/summary` |
| 사진 인식 | 이미지 업로드 후 `analysis-jobs` 호출 |

## 프론트엔드 변환 규칙

4번 파트의 화면 타입과 백엔드 타입은 다음처럼 변환한다.

| 4번 앱 필드 | 3번 API 필드 |
| --- | --- |
| `id: number` | `id: string` UUID로 변경 |
| `name` | `display_name` |
| `expiresAt` | `expires_at` |
| `location` | `storage_type` 변환: 냉장=`refrigerator`, 냉동=`freezer`, 실온=`room` |
| `category` | `category` 값 변환: 유제품=`dairy`, 육류·계란=`meat`, 채소=`vegetable`, 수산물=`seafood`, 기타=`other` |
| `quantity` | `quantity` |

## 사진 인식 흐름

```text
핸드폰 사진 선택
-> POST /api/v1/food-images (multipart file)
-> POST /api/v1/analysis-jobs { image_id }
-> GET /api/v1/analysis-jobs/{job_id}
-> POST /api/v1/analysis-jobs/{job_id}/apply
-> GET /api/v1/dashboard/summary
```

분석 상태가 `succeeded`가 되기 전에는 결과를 재고 목록에 반영하지 않는다. `failed`이면 사용자에게 재촬영 또는 수동 입력을 안내한다.

## 실행과 네트워크

3번 백엔드 실행:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

핸드폰이 같은 Wi-Fi에 있을 때 `localhost`는 핸드폰 자신을 가리키므로 노트북의 사설 IP를 앱 설정에 입력해야 한다.

ESP32가 AP 모드인 경우에는 핸드폰이 ESP32 AP에 연결되는 동안 노트북의 인터넷을 사용할 수 없는 경우가 있다. OpenAI VLM 호출은 인터넷이 필요하므로, 실제 VLM 요청은 인터넷이 가능한 백엔드 경로에서 수행해야 한다.

## 적용 완료된 변경 (4번 앱 로컬 clone)

- `src/types/fridge.ts`의 `InventoryItem.id`를 `string`(UUID)으로 변경
- `src/lib/api.ts`를 3번 백엔드 `/api/v1` 계약으로 교체하고 필드 변환 함수 추가
- `src/types/peak-api.ts` 추가: 백엔드 응답 타입 정의
- `src/data/mock-fridge-data.ts`의 목업 id를 문자열로 변경
- `src/state/fridge-store.tsx`의 시트 id와 신규 항목 id를 문자열로 변경
- `src/app/add.tsx`의 미리보기·후보 id를 문자열로 변경
- `npx tsc --noEmit` 통과 (기존 CSS 모듈 타입 오류 2건은 원본에도 존재)

3번 백엔드에는 `food_items.category` 컬럼과 API 필드를 추가했다(마이그레이션 `20260824_0005`).

## 팀원에게 전달할 내용

3번 백엔드는 PostgreSQL과 OpenAI VLM을 담당하고, 4번 앱은 화면을 담당한다. 4번 앱의 `src/lib/api.ts`와 타입에서 위 매핑을 적용하면 재고·D-day·조리 가능 여부를 공유할 수 있다. 기존 4번 백엔드와 3번 백엔드를 동시에 실행해 서로 다른 재고를 쓰지 않는다.
