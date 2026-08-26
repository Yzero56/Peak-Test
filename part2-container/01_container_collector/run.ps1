<#
.SYNOPSIS
  냉장고 용기 데이터 수집기 - 컴파일/업로드/AP 확인을 한 번에 실행.

.DESCRIPTION
  XIAO ESP32-S3 Sense 보드에 01_container_collector.ino를 컴파일 후 업로드하고,
  AP 핫스팟(ESP32-Camera)이 정상적으로 뜨는지 Wi-Fi 스캔으로 확인합니다.
  보드가 시리얼 리셋 후 멈춰 있는 경우를 대비해 업로드를 통해 리셋을 정리합니다.

.PARAMETER Port
  보드가 연결된 COM 포트. 기본값 COM8.

.EXAMPLE
  .\run.ps1
  .\run.ps1 -Port COM8
#>
param(
    [string]$Port = "COM8"
)

$ErrorActionPreference = "Stop"
$sketchDir = $PSScriptRoot
$fqbn = "esp32:esp32:XIAO_ESP32S3"

Write-Host "=== 1/3 컴파일 ===" -ForegroundColor Cyan
arduino-cli compile --fqbn $fqbn --board-options PSRAM=opi $sketchDir
if ($LASTEXITCODE -ne 0) { Write-Host "컴파일 실패" -ForegroundColor Red; exit 1 }

Write-Host "=== 2/3 업로드 ($Port) ===" -ForegroundColor Cyan
arduino-cli upload -p $Port --fqbn $fqbn --board-options PSRAM=opi $sketchDir
if ($LASTEXITCODE -ne 0) { Write-Host "업로드 실패 - 보드가 $Port 에 연결되어 있는지 확인하세요 (arduino-cli board list)" -ForegroundColor Red; exit 1 }

Write-Host "=== 3/3 AP 확인 (핫스팟 부팅 대기) ===" -ForegroundColor Cyan
Start-Sleep -Seconds 6
netsh wlan disconnect | Out-Null
Start-Sleep -Seconds 3
$found = netsh wlan show networks | Select-String -Pattern "ESP32-Camera"

if ($found) {
    Write-Host ""
    Write-Host "성공: ESP32-Camera 핫스팟이 켜졌습니다." -ForegroundColor Green
    Write-Host "PC/폰 Wi-Fi에서 'ESP32-Camera' (비번: 12345678) 연결 후 브라우저에서 http://192.168.4.1 접속하세요."
} else {
    Write-Host ""
    Write-Host "경고: 핫스팟이 아직 안 보입니다. netsh 캐시일 수 있으니 10초 후 다시 확인해보세요:" -ForegroundColor Yellow
    Write-Host "  netsh wlan show networks | Select-String ESP32-Camera"
}
