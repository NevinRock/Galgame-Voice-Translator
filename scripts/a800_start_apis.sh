#!/usr/bin/env bash
set -euo pipefail

project_dir="${1:-/ssd/BNW/Galgame_voice}"
read -r -a gpus <<< "${FISH_GPUS:-0 3 7}"
read -r -a ports <<< "${FISH_PORTS:-19081 8080 19082}"
log_dir="$project_dir/logs/fish_apis"

if [[ ${#gpus[@]} -ne ${#ports[@]} ]]; then
  echo "FISH_GPUS and FISH_PORTS must contain the same number of values" >&2
  exit 2
fi
mkdir -p "$log_dir"

for index in "${!gpus[@]}"; do
  gpu="${gpus[$index]}"
  port="${ports[$index]}"
  pid_file="$log_dir/gpu_${gpu}.pid"
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "GPU $gpu API already running as PID $(cat "$pid_file")"
    continue
  fi
  FISH_DEVICE="cuda:$gpu" FISH_LISTEN="127.0.0.1:$port" \
    nohup bash "$project_dir/scripts/a800_run_fish.sh" "$project_dir" drama-3 \
      > "$log_dir/gpu_${gpu}.log" 2>&1 < /dev/null &
  echo "$!" > "$pid_file"
  echo "started GPU $gpu API on port $port as PID $!"
done
