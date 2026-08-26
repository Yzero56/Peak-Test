#!/usr/bin/env bash
# 통합 스택 전체를 한 번에 띄운다 — 백엔드 + mock 보드(하드웨어 없을 때) + YJ + Wa + bridge.
# 각 파트의 의존성 설치(README의 pip install -r requirements.txt / npm install 등)는
# 이 스크립트가 대신 해주지 않는다 — 최초 1회는 각자 README대로 세팅해야 함.
#
# 실제 ESP32 보드가 있으면 mock 보드 대신 그 IP를 ESP_HOST로 넘기면 된다:
#   ESP_HOST=192.168.0.42 ./dev/run_all.sh --no-mock
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/dev/logs"; PID_DIR="$ROOT/dev/pids"
mkdir -p "$LOG_DIR" "$PID_DIR"

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
DEVICE_ID="${DEVICE_ID:-board-a-door-container}"
ESP_HOST="${ESP_HOST:-localhost:9000}"
USE_MOCK=1
[[ "${1:-}" == "--no-mock" ]] && USE_MOCK=0

start() {  # name  workdir  cmd...
  local name="$1" dir="$2"; shift 2
  if [[ -f "$PID_DIR/$name.pid" ]] && kill -0 "$(cat "$PID_DIR/$name.pid")" 2>/dev/null; then
    echo "[dev] $name 이미 실행 중 (pid $(cat "$PID_DIR/$name.pid")) — 건너뜀"
    return
  fi
  echo "[dev] $name 시작..."
  ( cd "$dir" && "$@" ) > "$LOG_DIR/$name.log" 2>&1 &
  echo $! > "$PID_DIR/$name.pid"
}

start backend "$ROOT/backend" \
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

if [[ "$USE_MOCK" == "1" ]]; then
  start mock-board "$ROOT/firmware/board-a-door-container" \
    python3 mock_server.py --port 9000
fi

start yj "$ROOT/part1-inout" \
  .venv/bin/python -u tools/inout_classifier/server.py \
    --esp-host "$ESP_HOST" --http-port 8601 \
    --backend-url "$BACKEND_URL" --device-id "$DEVICE_ID"

start wa "$ROOT/part2-container" \
  .venv/bin/python -u browser_instance_realtime_multi.py "$ESP_HOST" --port 5007 \
    --backend-url "$BACKEND_URL" --device-id "$DEVICE_ID"

start bridge "$ROOT" \
  .venv/bin/python -u bridge/detection_bridge.py \
    --backend-url "$BACKEND_URL" --device-id "$DEVICE_ID"

sleep 2
echo
echo "[dev] 전부 시작됨. 로그: $LOG_DIR/*.log, 종료는 ./dev/stop_all.sh"
echo "  백엔드:      $BACKEND_URL  (문서: $BACKEND_URL/docs, 대시보드: $BACKEND_URL/dashboard/)"
[[ "$USE_MOCK" == "1" ]] && echo "  mock 보드:   http://localhost:9000"
echo "  YJ(IN/OUT):  http://localhost:8601"
echo "  Wa(용기):    http://localhost:5007"
