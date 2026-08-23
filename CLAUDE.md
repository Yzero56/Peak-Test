# [CLAUDE.md](http://CLAUDE.md)

@AGENTS.md

## 프로젝트 개요

스마트 냉장고 시스템 — 카메라 기반 재료 인식(VLM) + 자동 재고 관리 + 유통기한 알림 + 레시피 추천. 3인~4인 팀 프로젝트, 발표용 데모 포함. 

핵심 파이프라인: `ESP32-S3가 라이브 영상(/stream)·정지 프레임(/capture)을 직접 서빙 → 리드스위치가 문 열림을 감지해 door_open=true 보고 → 백엔드가 문이 열려있는 동안 몇 초 간격으로 /capture를 자동 pull(실시간 탐지 on), 문 닫히면 자동 중단(off) — 별도로 대시보드 "지금 스캔하기"로 수동 1회 스캔도 가능 → 두 경우 모두 VLM API(재료 인식) → DB 업데이트(기기당 최신 1건, 쌓지 않음) → React Native 앱 푸시 알림 / 웹 대시보드 표시(5초 주기 자동 갱신)`

## 기술 스택

- **엣지 디바이스**: XIAO ESP32-S3 Sense (OV2640, 필요시 OV5640 업그레이드), BME680 가스센서, RTC, 도어/PIR 트리거 센서. 카메라 펌웨어(`firmware/xiao-esp32s3-cam/`)는 USB 시리얼이 아니라 **자체 Wi-Fi로 라이브 영상을 직접 서빙**한다(`/stream`, `/capture` — 인증 없음, LAN 전용). 이미지를 백엔드로 쌓아 올리지 않고, 백엔드가 스캔 시점에만 프레임을 가져간다(pull). Wi-Fi/기기 토큰은 커밋되지 않는 `secrets.h`로 분리(`secrets.h.example` 참고). 설정 방법은 해당 폴더 README 참고
- **통신**: ESP32 → Wi-Fi → FastAPI 백엔드, **HTTP REST로 확정**. 센서값은 JSON(`POST /api/devices/{id}/sensors`), 기기 하트비트는 `POST /api/devices/{id}/heartbeat`(IP·생존 갱신). 카메라 이미지는 기기가 push하지 않고 백엔드가 `GET http://{기기IP}/capture`로 pull. 기기별 토큰(`X-Device-Token` 헤더)으로 인증
- **백엔드**: `backend/` 디렉토리, FastAPI (Python) + Jinja2/HTMX 관리자 대시보드(별도 프론트엔드 빌드 없음). VLM API 연동(Claude / OpenAI / Gemini 중 택)은 아직 목업(`backend/app/detection.py`)이며 교체 지점만 분리해둠. 대시보드 로그인은 공용 비밀번호 세션 인증, 실행 방법은 `backend/README.md` 참고
- **프론트엔드**: React Native (Expo) + TypeScript + NativeWind — 단일 코드베이스로 모바일 앱(iOS/Android)과 웹 대시보드(`react-native-web`, 발표용)를 동시 대응
- **초기 개발 단계**: 센서(도어/가스)·식재료 데이터는 목업(mock) 데이터로 시작, 이후 FastAPI 연동으로 교체

## 프론트엔드 구조 (React Native / Expo)

- `src/app/` — expo-router 파일 기반 라우팅. `index.tsx` = 홈 대시보드, `explore.tsx` = 식재료 전체 목록(카테고리별)
- `src/components/dashboard/` — 대시보드 UI 컴포넌트 (센서 상태 카드, 식재료 행, 레시피 카드, 알림 항목)
- `src/data/mock-fridge-data.ts` — 센서/식재료/알림/레시피 목업 데이터. 실제 API 연동 시 이 모듈을 교체
- `src/types/fridge.ts` — 도메인 타입 정의 (DoorStatus, GasStatus, FoodItem, NotificationDigest, RecipeSuggestion)
- `src/utils/dday.ts` — D-day 계산 및 신선도 상태(색상) 매핑
- 스타일링은 NativeWind(Tailwind) `className`을 사용. 기존 템플릿의 `ThemedText`/`ThemedView`(StyleSheet 기반)는 대시보드 화면 밖(스캐폴딩 잔여 컴포넌트)에서만 남아있음 — 대시보드 관련 신규 컴포넌트는 NativeWind로 통일

## 하드웨어 셋업 메모

| 항목     | 내용                                                 |
| ------ | -------------------------------------------------- |
| 카메라    | 냉장고 문틈에서 내부를 정면으로 바라보는 각도, 20~40cm 근접, FOV 120° 권장 |
| 트리거    | 도어 개폐 센서 또는 PIR 모션 센서                              |
| 가스센서   | BME680, 냉장고 내부 방수 처리 후 부착                          |
| RTC    | ESP32 연결, 배터리 백업 필수 확인                             |
| 보조 LED | 조건부 — 조명 테스트 후 필요시만 추가                             |

## 대시보드 / 앱 UX 규칙

- 현재 냉장고 상태 : 이름 있는 항목은 텍스트, 없는 항목은 사진 썸네일로 표시
- 아이템 이름 수정은 아이콘 선택 방식 (텍스트 직접 입력 없음)
- 알림은 실시간이 아니라 하루 단위로 요약해서 묶어 전송
- 유통기한은 D-day 형식으로 상태 시각화
- 오늘의 추천 레시피 카드 포함

## 하지 말아야 할 것 (Boundaries)

- API 키, VLM 요청용 크레덴셜을 코드에 하드코딩하지 않기 — `.env` 사용
- `/firmware` 하위 로우레벨 타이밍 코드는 별도 요청 없이 리팩터링하지 않기
- 생성된 빌드 산출물(`/build`, `/dist` 등)은 수정 대상 아님
