# Edge Impulse 수동 설정 가이드

## 🎯 목표
ESP32S3 카메라로 캡처한 데이터셋으로 AI 추론 시스템 구축

## 📋 단계별 진행

### 1단계: 데이터셋 업로드

1. **링크 접속**: https://studio.edgeimpulse.com/studio/1084517
2. **Data acquisition** → **Upload existing data**
3. `C:\Users\PKNU-ICEE\Desktop\project\xiao_dataset` 폴더 선택
4. **Upload** 클릭

### 2단계: Impulse 생성

1. **Impulse design** → **Create impulse**
2. **Image** 블록 추가 (처리 블록)
3. **Learning block** 추가 → **MobileNetV2**
4. **Save impulse**

### 3단계: 데이터 처리

1. **Generate features** 클릭
2. 모든 이미지가 처리될 때까지 대기

### 4단계: 모델 훈련

1. **Train model** 클릭
2. **Training cycles**: 10
3. **Start training** 클릭
4. 훈련 완료 대기 (5-10분)

### 5단계: 라이브러리 다운로드

1. **Deployment** → **Arduino library**
2. **Download** 클릭
3. 다운로드된 zip 파일에서 `ei_esp32s3_camera-_inferencing.zip` 찾기

### 6단계: 코드 생성

1. 라이브러리 파일 경로 확인:
   ```
   Documents/Arduino/libraries/ei_esp32s3_camera-_inferencing
   ```
2. 이 경로를 나에게 알려주면 추론 코드 생성

## ⏱️ 예상 시간
- 업로드: 5분
- Impulse 설정: 5분
- 훈련: 10분
- **총 약 20분**

## 🔗 유용한 링크
- 프로젝트: https://studio.edgeimpulse.com/studio/1084517
- Edge Impulse 문서: https://docs.edgeimpulse.com/
