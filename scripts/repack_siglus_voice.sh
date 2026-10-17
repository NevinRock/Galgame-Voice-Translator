#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 ORIGINAL_KOE_DIR GENERATED_WAV_DIR OUTPUT_KOE_DIR" >&2
  exit 2
fi

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
original_dir="$(cd "$1" && pwd)"
generated_dir="$(cd "$2" && pwd)"
output_dir="$3"

if [[ "$original_dir" == "$(realpath -m "$output_dir")" ]]; then
  echo "refusing to overwrite the original KOE directory" >&2
  exit 2
fi
if [[ -e "$output_dir" ]] && find "$output_dir" -mindepth 1 -print -quit | grep -q .; then
  echo "output directory must be absent or empty: $output_dir" >&2
  exit 2
fi
mkdir -p "$output_dir"

stage_dir="$(mktemp -d /tmp/tsui_stella_ovk_XXXXXX)"
trap 'rm -rf "$stage_dir"' EXIT

export PYTHONPATH="$project_dir/tools/SiglusSceneScriptUtility/src"
python3 -m siglus_ssu --legacy-full -s --x "$original_dir" "$stage_dir"

converted=0
missing=0
while IFS= read -r -d '' wav; do
  base="$(basename "$wav" .wav)"
  number="${base#koe_}"
  if [[ ! "$number" =~ ^[0-9]{9}$ ]]; then
    echo "skip unexpected filename: $wav" >&2
    continue
  fi
  numeric=$((10#$number))
  scene=$((numeric / 100000))
  entry=$((numeric % 100000))
  target="$(printf '%s/z%04d_%d.ogg' "$stage_dir" "$scene" "$entry")"
  if [[ ! -f "$target" ]]; then
    echo "no original OVK entry for $base ($target)" >&2
    missing=$((missing + 1))
    continue
  fi
  rate="$(ffprobe -v error -select_streams a:0 -show_entries stream=sample_rate -of default=nk=1:nw=1 "$target")"
  channels="$(ffprobe -v error -select_streams a:0 -show_entries stream=channels -of default=nk=1:nw=1 "$target")"
  temporary="${target}.new.ogg"
  ffmpeg -nostdin -loglevel error -y -i "$wav" -map_metadata -1 \
    -ar "$rate" -ac "$channels" -c:a libvorbis -q:a 5 "$temporary"
  mv "$temporary" "$target"
  converted=$((converted + 1))
done < <(find "$generated_dir" -type f -name 'koe_?????????.wav' -print0 | sort -z)

if (( converted == 0 )); then
  echo "no generated WAV files were converted" >&2
  exit 1
fi
if (( missing > 0 )); then
  echo "$missing generated files did not match an original OVK entry" >&2
  exit 1
fi

python3 -m siglus_ssu --legacy-full -s --c "$stage_dir" "$output_dir"
printf 'Repacked %d generated lines into %s\n' "$converted" "$output_dir"

