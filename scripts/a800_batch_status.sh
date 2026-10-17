#!/usr/bin/env bash
set -euo pipefail

project_dir="${1:-/ssd/BNW/Galgame_voice}"
job_name="${2:-tsui_no_stella}"
output_name="${3:-generated_voice}"
output_dir="$project_dir/jobs/$job_name/$output_name"
log_dir="$project_dir/logs/$job_name"

printf 'worker_0 pid='
if [[ -f "$log_dir/worker_0.pid" ]]; then
  pid="$(cat "$log_dir/worker_0.pid")"
  if kill -0 "$pid" 2>/dev/null; then
    printf '%s running\n' "$pid"
  else
    printf '%s stopped\n' "$pid"
  fi
else
  echo missing
fi
if [[ -f "$output_dir/_status_worker_0.json" ]]; then
  cat "$output_dir/_status_worker_0.json"
fi

printf 'published_wav='
find "$output_dir" -maxdepth 1 -type f -name 'koe_*.wav' 2>/dev/null | wc -l
printf 'rejected_wav='
find "$output_dir/.rejected" -maxdepth 1 -type f -name 'koe_*.wav' 2>/dev/null | wc -l
