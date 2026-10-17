#!/usr/bin/env bash
set -euo pipefail

project_dir="${1:-/ssd/BNW/Galgame_voice}"
model="${2:-drama-3}"
listen="${FISH_LISTEN:-0.0.0.0:8080}"
cd "$project_dir/fish-speech"
. .venv/bin/activate

if [[ "$model" == "drama-3" ]]; then
  # One 80 GB A800 has enough memory for Drama 3 and its codec.
  exec python tools/api_server.py \
    --listen "$listen" \
    --llama-checkpoint-path checkpoints/drama-3 \
    --device "${FISH_DEVICE:-cuda:0}"
fi

exec python tools/api_server.py \
  --listen "$listen" \
  --llama-checkpoint-path checkpoints/s2-pro \
  --decoder-checkpoint-path checkpoints/s2-pro/codec.pth \
  --decoder-config-name modded_dac_vq \
  --device "${FISH_DEVICE:-cuda:0}"

