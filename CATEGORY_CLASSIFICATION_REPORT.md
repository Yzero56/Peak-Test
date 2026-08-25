# 텀블러·반찬 용기 종류 분류 1차 실험

## 목표

YOLO-World가 찾고 크롭한 물체를 `drink_container`(텀블러)와
`food_container`(반찬 용기) 중 하나로 분류한다.

## 데이터

- 원본: 반찬 용기 7종 71장, 텀블러 4종 39장, 총 110장
- YOLO 자동 크롭 성공: 93장, 제외: 17장
- 학습 57장 / 검증 19장 / 시험 17장
- 같은 실제 물건의 사진이 학습용과 시험용에 섞이지 않도록 물건 ID 단위로 분리
- 시험 물건: 학습 때 보지 않은 텀블러 1종과 반찬 용기 1종

## 방법

- YOLO-World: 사진에서 대상 위치 자동 탐지·크롭
- DINOv2 ViT-S/14: 크롭 사진의 384차원 특징 추출
- 로지스틱 회귀: 두 종류 분류
- 클래스 수 불균형은 `class_weight=balanced`로 보정

## 결과

- 검증 정확도: 89.5%
- 독립 시험 정확도: **94.1% (16/17)**
- 텀블러: 7/7 정답
- 반찬 용기: 9/10 정답
- 오답 1장: 반찬 용기의 바닥면만 크게 보이는 특수 각도. 텀블러 확률 50.1%로 매우 불확실한 판정

## 해석 및 한계

현재 자료로 두 종류를 구분할 가능성은 확인했다. 다만 실제 물건 수가 반찬 용기 7종,
텀블러 4종으로 적고 시험 세트도 17장뿐이므로 94.1%를 제품 최종 정확도로 해석하면 안 된다.
특히 텀블러 종류를 추가하고 손에 든 상태·실제 냉장고 배경의 독립 시험 사진으로 재평가해야 한다.

## 산출물

- 준비 데이터: `category_dataset_prepared/`
- 데이터 목록: `category_dataset_prepared/manifest.csv`
- 분류 모델: `category_classifier.joblib`
- 특징 캐시: `category_classifier_embeddings.npz`
- 평가 결과: `category_classifier_evaluation.json`
- 사진별 예측: `category_classifier_predictions.csv`

