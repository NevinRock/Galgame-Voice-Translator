#!/usr/bin/env bash
set -euo pipefail

project_dir="${1:-/ssd/BNW/Galgame_voice}"
job_name="${2:-tsui_no_stella}"
output_name="${3:-generated_voice}"
read -r -a gpus <<< "${FISH_GPUS:-0 3 7}"
read -r -a ports <<< "${FISH_PORTS:-19081 8080 19082}"
job_dir="$project_dir/jobs/$job_name"
output_dir="$job_dir/$output_name"
log_dir="$project_dir/logs/$job_name"
python_bin="$project_dir/fish-speech/.venv/bin/python"

if [[ ${#gpus[@]} -ne ${#ports[@]} ]]; then
  echo "FISH_GPUS and FISH_PORTS must contain the same number of values" >&2
  exit 2
fi
mkdir -p "$output_dir" "$log_dir"

for index in "${!ports[@]}"; do
  port="${ports[$index]}"
  if ! curl --fail --silent --max-time 5 \
    "http://127.0.0.1:$port/v1/health" >/dev/null; then
    echo "GPU ${gpus[$index]} API on port $port is not healthy" >&2
    exit 1
  fi
done

cd "$project_dir"
for index in "${!ports[@]}"; do
  pid_file="$log_dir/worker_${index}.pid"
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "worker $index already running as PID $(cat "$pid_file")"
    continue
  fi
  nohup "$python_bin" -m galgame_voice synthesize-adaptive \
    --lines "$job_dir/job/lines.jsonl" \
    --characters "$job_dir/job/characters.json" \
    --output-dir "$output_dir" \
    --num-shards "${#ports[@]}" \
    --shard-index "$index" \
    --max-attempts "${MAX_ATTEMPTS:-8}" \
    --url "http://127.0.0.1:${ports[$index]}" \
    > "$log_dir/worker_${index}.log" 2>&1 < /dev/null &
  echo "$!" > "$pid_file"
  echo "started worker $index on GPU ${gpus[$index]} as PID $!"
done
