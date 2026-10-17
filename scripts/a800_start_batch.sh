#!/usr/bin/env bash
set -euo pipefail

project_dir="${1:-/ssd/BNW/Galgame_voice}"
job_name="${2:-tsui_no_stella}"
output_name="${3:-generated_voice}"
gpu="${FISH_GPU:-3}"
port="${FISH_PORT:-8080}"
job_dir="$project_dir/jobs/$job_name"
output_dir="$job_dir/$output_name"
log_dir="$project_dir/logs/$job_name"
python_bin="$project_dir/fish-speech/.venv/bin/python"

mkdir -p "$output_dir" "$log_dir"

if ! curl --fail --silent --max-time 5 \
  "http://127.0.0.1:$port/v1/health" >/dev/null; then
  echo "GPU $gpu API on port $port is not healthy" >&2
  exit 1
fi

cd "$project_dir"
pid_file="$log_dir/worker_0.pid"
if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
  echo "worker already running as PID $(cat "$pid_file")"
  exit 0
fi

nohup "$python_bin" -m galgame_voice synthesize-adaptive \
  --lines "$job_dir/job/lines.jsonl" \
  --characters "$job_dir/job/characters.json" \
  --output-dir "$output_dir" \
  --num-shards 1 \
  --shard-index 0 \
  --max-attempts "${MAX_ATTEMPTS:-8}" \
  --url "http://127.0.0.1:$port" \
  > "$log_dir/worker_0.log" 2>&1 < /dev/null &
echo "$!" > "$pid_file"
echo "started one worker on GPU $gpu as PID $!"
