# ESP32 실시간 용기 탐지·인식 사용법

이 프로그램은 ESP32 카메라 사진을 계속 받아 다음 순서로 처리합니다.

`YOLO로 용기 위치 찾기 → DINOv2로 기존/신규 용기 판단 → SQLite에 저장`

## 연결 후 실행 순서

1. ESP32 카메라 전원을 켭니다.
2. PC를 카메라와 같은 네트워크에 연결합니다.
3. 브라우저에서 카메라 화면이 열리는지 확인합니다.
4. PowerShell에서 아래 명령을 실행합니다.

ESP32 자체 핫스팟(AP) 방식:

```powershell
cd C:\Users\PKNU-ICEE\Desktop\project
python browser_container_recognition.py 192.168.4.1
```

현재 준비된 펌웨어는 공유기 연결에 실패하면 약 15초 뒤 Wi-Fi 이름
`XIAO_STREAM_AP`, 비밀번호 `12345678`로 핫스팟을 만듭니다.

공유기(STA) 방식의 예:

```powershell
cd C:\Users\PKNU-ICEE\Desktop\project
python browser_container_recognition.py xiaostream.local
```

브라우저에서 사용하던 IP가 따로 있다면 `xiaostream.local` 대신 그 IP를 입력합니다.

5. 브라우저에서 `http://127.0.0.1:5000`을 엽니다.

## 화면 조작

- 실시간 카메라 화면을 확인합니다.
- 용기를 화면에 놓고 `현재 용기 분석` 버튼을 누릅니다.
- 같은 페이지에서 YOLO 탐지 확률, 기존 용기 유사도, ID와 등록 목록을 확인합니다.

빈 화면에서는 분석 버튼을 누르지 않습니다. 처음 본 용기면 `NEW`, 다시 본 용기면
`MATCH`와 기존 ID가 표시됩니다.

현재 카메라 서버에는 한 장의 JPEG를 반환하는 `/jpg` 주소가 필요합니다. 프로그램이 입력한
주소 뒤에 `/jpg`를 자동으로 붙입니다.

## 연결 문제를 확인할 때

- AP 방식: PC가 ESP32가 만든 Wi-Fi에 연결되어 있어야 하며 주소는 보통 `192.168.4.1`
- STA 방식: PC와 ESP32가 같은 2.4GHz 공유기에 연결되어 있어야 함
- 카메라 펌웨어를 다시 올릴 때는 컴파일과 업로드 모두 `PSRAM=opi` 설정 필수
- 시리얼 확인은 보드를 재시작할 수 있으므로 브라우저 주소 확인을 우선 사용
