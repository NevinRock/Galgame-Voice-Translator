#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 LOCAL_JOB_DIR [REMOTE_PROJECT_DIR]" >&2
  exit 2
fi

job_dir="$(cd "$1" && pwd)"
destination="${2:-/ssd/BNW/Galgame_voice}"
ssh_config="${SSH_CONFIG:-$HOME/.ssh/config}"

# Intentionally sync only extracted clips/manifests supplied in LOCAL_JOB_DIR,
# never the game installation directory.
ssh -F "$ssh_config" a800 "mkdir -p '$destination/jobs/$(basename "$job_dir")'"
rsync -az --info=progress2 -e "ssh -F $ssh_config" \
  "$job_dir/" "a800:$destination/jobs/$(basename "$job_dir")/"
ssh -F "$ssh_config" a800 \
  "touch '$destination/jobs/$(basename "$job_dir")/.upload_complete'"

