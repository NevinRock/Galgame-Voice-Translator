#!/usr/bin/env bash
set -euo pipefail

project_dir="${1:-/ssd/BNW/Galgame_voice}"
model="${2:-drama-3}"
cd "$project_dir/fish-speech"
. .venv/bin/activate
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
# hf-xet high-performance mode raises range-request concurrency and buffer
# sizes.  The a800 host has fast NVMe and ample RAM, so it materially shortens
# the 41.5 GB Drama 3 download while retaining resumability.
export HF_XET_HIGH_PERFORMANCE="${HF_XET_HIGH_PERFORMANCE:-1}"
model_source="${MODEL_SOURCE:-modelscope}"

case "$model" in
  drama-3)
    if [[ "$model_source" == "modelscope" ]]; then
      # ModelScope is the preferred mainland-China source. Its Drama 3
      # snapshot includes codec.pth, so no second model download is needed.
      modelscope download --model fishaudio/drama-3 \
        --local_dir checkpoints/drama-3
    elif [[ "$model_source" == "huggingface" ]]; then
      hf download fishaudio/drama-3 --local-dir checkpoints/drama-3
    else
      echo "unknown MODEL_SOURCE: $model_source (expected modelscope or huggingface)" >&2
      exit 2
    fi
    ;;
  s2-pro)
    hf download fishaudio/s2-pro --local-dir checkpoints/s2-pro
    ;;
  *)
    echo "unknown model: $model (expected drama-3 or s2-pro)" >&2
    exit 2
    ;;
esac

