#!/usr/bin/env bash
set -euo pipefail

project_dir="${1:-/ssd/BNW/Galgame_voice}"
cd "$project_dir/fish-speech"

python3 -m venv .venv
. .venv/bin/activate
# ModelScope 1.x still imports pkg_resources, which was removed from newer
# setuptools releases. Keep a compatible version in this isolated venv.
python -m pip install --upgrade pip wheel "setuptools<81"

# PyTorch wheels stay on the official CUDA index; ordinary packages use a
# mainland mirror. Fish Speech supports Python 3.10+, which is present on a800.
python -m pip install \
  --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
  --extra-index-url https://download.pytorch.org/whl/cu128 \
  -e ".[cu128]"
python -m pip install \
  --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
  -r "$project_dir/requirements.txt" "huggingface_hub[cli]" "modelscope==1.17.1"

echo "Fish Speech environment installed at $project_dir/fish-speech/.venv"

