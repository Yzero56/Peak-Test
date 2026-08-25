# 용기 자동 등록·재식별 사용법

이 프로그램은 사진을 숫자로 된 **디지털 지문**으로 바꿉니다. 기존 지문과 유사도가
0.44 이상이면 전에 본 용기로 판단하고, 그보다 낮으면 새 번호를 발급합니다.

여기서 디지털 지문은 사람의 지문이 아니라, 사진의 색·모양·무늬 특징을 숫자 목록으로
바꾼 것을 뜻합니다. 프로그램은 용기를 다시 볼 때마다 이 특징을 자동 보관합니다. 따라서
사용자가 용기 이름을 붙여 미리 학습시키는 방식이 아닙니다.

## 1. 사진 한 장으로 등록 또는 인식

PowerShell에서 프로젝트 폴더로 이동한 뒤 실행합니다.

```powershell
cd C:\Users\PKNU-ICEE\Desktop\project
python container_registry.py recognize "사진파일경로" --content "김치"
```

`--content`는 새 용기를 처음 등록할 때만 사용하면 됩니다. 두 번째부터는 다음처럼 사진만
지정해도 됩니다.

```powershell
python container_registry.py recognize "사진파일경로"
```

처음 실행할 때 DINOv2 모델을 준비하므로 시간이 조금 걸릴 수 있습니다. 등록 정보는
`containers.db`에 자동 저장됩니다.

## 2. 등록된 용기 목록 보기

```powershell
python container_registry.py list
```

## 3. 내용물 입력 또는 수정

```powershell
python container_registry.py set-content Container_001 "김치"
```

현재 유사도 기준 0.44는 임시 출발점입니다. 여러 사진으로 시험한 뒤 잘못 알아보는 사례를
확인해 조정해야 합니다.

## 4. 수집한 사진 전체로 정확도 다시 검사

```powershell
python validate_reidentification.py
```

사진이 바뀌지 않았다면 저장된 디지털 지문을 재사용하므로 두 번째 실행부터는 빠릅니다.
현재 300장 검사에서는 기준값 0.44의 균형 정확도가 76.24%로 나와, 실제 사용 전에 인식
방식을 더 개선해야 합니다.
