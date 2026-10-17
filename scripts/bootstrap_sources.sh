#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fish_commit="541566932abbaebcb0a40e562a1f846738383f38"
siglus_commit="85700715aed8695a95183bb973f981a61ae9d9c7"

clone_at_commit() {
  local url="$1"
  local destination="$2"
  local commit="$3"
  if [[ ! -d "$destination/.git" ]]; then
    git clone --filter=blob:none "$url" "$destination"
  fi
  git -C "$destination" fetch --depth 1 origin "$commit"
  git -C "$destination" checkout --detach "$commit"
}

clone_at_commit \
  https://github.com/fishaudio/fish-speech.git \
  "$project_dir/fish-speech" \
  "$fish_commit"
git -C "$project_dir/fish-speech" apply --check \
  "$project_dir/patches/fish-speech-headless.patch" 2>/dev/null && \
  git -C "$project_dir/fish-speech" apply \
    "$project_dir/patches/fish-speech-headless.patch"

clone_at_commit \
  https://github.com/Jirehlov/SiglusSceneScriptUtility.git \
  "$project_dir/tools/SiglusSceneScriptUtility" \
  "$siglus_commit"

echo "Pinned Fish Speech and SiglusSceneScriptUtility sources are ready."
