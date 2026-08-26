# 정적 사진 통합 인식 사용법

이 프로그램은 사진에서 YOLO가 용기를 찾고, DINOv2와 SQLite가 처음 본 용기인지 전에 본
용기인지 판단합니다.

```powershell
cd C:\Users\PKNU-ICEE\Desktop\project
python container_pipeline.py "사진파일경로"
```

처음 실행하면 `containers.db`가 만들어집니다. 같은 용기의 다른 사진으로 명령을 다시
실행하면 기존 ID로 인식하는지 확인할 수 있습니다. 네모와 ID가 표시된 결과는
`pipeline_result.jpg`에 저장됩니다.

시험할 때 실제 정보를 저장하고 싶지 않다면 별도 DB를 지정합니다.

```powershell
python container_pipeline.py "사진파일경로" --db test_pipeline.db
```
