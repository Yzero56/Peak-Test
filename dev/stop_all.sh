#!/usr/bin/env bash
# run_all.sh로 띄운 프로세스를 전부 종료한다.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_DIR="$ROOT/dev/pids"

shopt -s nullglob
for f in "$PID_DIR"/*.pid; do
  name="$(basename "$f" .pid)"
  pid="$(cat "$f")"
  if kill "$pid" 2>/dev/null; then
    echo "[dev] $name 종료 (pid $pid)"
  else
    echo "[dev] $name 이미 죽어있음 (pid $pid)"
  fi
  rm -f "$f"
done
echo "[dev] 완료"
