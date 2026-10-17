#!/usr/bin/env bash
set -euo pipefail

project_dir="${1:-/ssd/BNW/Galgame_voice}"
job_name="${2:-tsui_no_stella}"
output_name="${3:-generated_voice}"
read -r -a ports <<< "${FISH_PORTS:-19081 8080 19082}"
output_dir="$project_dir/jobs/$job_name/$output_name"
log_dir="$project_dir/logs/$job_name"

for index in "${!ports[@]}"; do
  printf 'worker_%s pid=' "$index"
  if [[ -f "$log_dir/worker_${index}.pid" ]]; then
    pid="$(cat "$log_dir/worker_${index}.pid")"
    if kill -0 "$pid" 2>/dev/null; then
      printf '%s running\n' "$pid"
    else
      printf '%s stopped\n' "$pid"
    fi
  else
    echo missing
  fi
  if [[ -f "$output_dir/_status_worker_${index}.json" ]]; then
    cat "$output_dir/_status_worker_${index}.json"
  fi
done

printf 'published_wav='
find "$output_dir" -maxdepth 1 -type f -name 'koe_*.wav' 2>/dev/null | wc -l
printf 'rejected_wav='
find "$output_dir/.rejected" -maxdepth 1 -type f -name 'koe_*.wav' 2>/dev/null | wc -l
