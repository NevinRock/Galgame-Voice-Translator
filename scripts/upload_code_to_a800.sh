#!/usr/bin/env bash
set -euo pipefail

source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
destination="${1:-/ssd/BNW/Galgame_voice}"
ssh_config="${SSH_CONFIG:-$HOME/.ssh/config}"

ssh -F "$ssh_config" a800 "mkdir -p '$destination'"
rsync -az --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude 'fish-speech/.git/' \
  --exclude 'fish-speech/checkpoints/' \
  --exclude 'jobs/' \
  --exclude 'logs/' \
  --exclude 'extracted_voice/' \
  --exclude 'generated_voice/' \
  --exclude 'work/' \
  --exclude '終のステラ/' \
  -e "ssh -F $ssh_config" \
  "$source_dir/" "a800:$destination/"

echo "Uploaded code only to a800:$destination"

