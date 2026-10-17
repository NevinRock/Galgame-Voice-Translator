#!/usr/bin/env bash
set -euo pipefail

project_dir="${1:-/ssd/BNW/Galgame_voice}"
gpu="${FISH_GPU:-3}"
port="${FISH_PORT:-8080}"
log_dir="$project_dir/logs/fish_api"
pid_file="$log_dir/fish.pid"
mkdir -p "$log_dir"

if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
  echo "Fish Speech is already running as PID $(cat "$pid_file")"
  exit 0
fi

FISH_DEVICE="cuda:$gpu" FISH_LISTEN="127.0.0.1:$port" \
  nohup bash "$project_dir/scripts/a800_run_fish.sh" "$project_dir" drama-3 \
    > "$log_dir/fish.log" 2>&1 < /dev/null &
echo "$!" > "$pid_file"
echo "started Fish Speech on GPU $gpu, port $port, PID $!"
