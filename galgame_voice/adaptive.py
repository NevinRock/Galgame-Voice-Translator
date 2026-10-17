from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import zlib
from pathlib import Path
from typing import Any

from .fish import FishSpeechClient
from .io import read_json, read_lines, validate_lines


def audio_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def max_tokens_for_duration(seconds: float) -> int:
    return max(64, min(512, math.ceil(seconds * 28)))


def duration_is_acceptable(candidate: float, target: float) -> bool:
    return abs(candidate - target) <= max(0.25, target * 0.15)


def instruction_for_ratio(ratio: float | None) -> str:
    if ratio is None:
        return "[clear Mandarin][natural pace]"
    if ratio < 0.85:
        return "[clear Mandarin][slow]"
    if ratio > 1.15:
        return "[clear Mandarin][concise][fast]"
    return "[clear Mandarin][natural pace]"


def _resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def _write_status(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _align(source: Path, output: Path, source_duration: float, target: float) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".part.wav")
    tempo = source_duration / target
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-filter:a",
            f"atempo={tempo:.8f}",
            "-ar",
            "44100",
            "-ac",
            "1",
            str(temporary),
        ],
        check=True,
    )
    temporary.replace(output)


def run_adaptive(args: Any) -> int:
    rows = read_lines(args.lines)
    errors = validate_lines(rows, args.lines)
    if errors:
        raise ValueError("\n".join(errors))
    if not 0 <= args.shard_index < args.num_shards:
        raise ValueError("shard-index must be between 0 and num-shards - 1")

    characters_data = read_json(args.characters)
    characters = characters_data.get("characters", {})
    rows = [row for index, row in enumerate(rows) if index % args.num_shards == args.shard_index]
    if args.limit is not None:
        rows = rows[: args.limit]
    client = FishSpeechClient(args.url, args.api_key, args.timeout)
    client.health()

    candidate_dir = args.output_dir / ".candidates" / f"worker_{args.shard_index}"
    rejected_dir = args.output_dir / ".rejected"
    status_path = args.output_dir / f"_status_worker_{args.shard_index}.json"
    manifest_path = args.output_dir / f"_results_worker_{args.shard_index}.jsonl"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    completed = failed = cached = 0

    for position, row in enumerate(rows, 1):
        output = (args.output_dir / str(row["output"])).resolve()
        if args.output_dir not in output.parents:
            raise ValueError(f"output escapes output directory: {row['output']}")
        if output.exists() and output.stat().st_size > 44:
            cached += 1
            _write_status(
                status_path,
                {
                    "worker": args.shard_index,
                    "total": len(rows),
                    "processed": position,
                    "completed": completed,
                    "cached": cached,
                    "failed": failed,
                    "current_id": row["id"],
                },
            )
            print(
                f"worker {args.shard_index} [{position}/{len(rows)}] "
                f"{row['id']}: cached",
                flush=True,
            )
            continue

        line_audio = _resolve(args.lines.parent, str(row["reference_audio"]))
        target_duration = audio_duration(line_audio)
        text = str(row.get("zh_text", "")).strip()
        result: dict[str, Any] = {
            "id": row["id"],
            "speaker": row["speaker"],
            "target_duration": target_duration,
            "attempts": [],
        }

        # Preserve breaths, sighs and silence instead of asking TTS to invent words.
        if not re.search(r"[\w\u3400-\u9fff]", text, flags=re.UNICODE):
            _align(line_audio, output, target_duration, target_duration)
            result.update(status="nonverbal_preserved", output=str(output))
            completed += 1
        else:
            character = characters.get(str(row["speaker"]), {})
            character_audio = _resolve(
                args.characters.parent, str(character.get("audio", ""))
            )
            if not character_audio.is_file():
                raise ValueError(f"missing character reference for {row['speaker']}")

            base_seed = zlib.crc32(str(row["id"]).encode("utf-8")) & 0x7FFFFFFF
            best: tuple[float, Path, float, int] | None = None
            previous_ratio: float | None = None
            made: list[Path] = []
            for attempt in range(args.max_attempts):
                seed = base_seed + attempt * 1009
                instruction = instruction_for_ratio(previous_ratio)
                candidate = candidate_dir / f"{row['id']}_{attempt}.wav"
                made.append(candidate)
                client.synthesize(
                    text=f"{instruction} {text}",
                    output=candidate,
                    reference_audio=None,
                    reference_text="",
                    character_audio=character_audio,
                    character_text=str(character.get("text", "")),
                    seed=seed,
                    temperature=args.temperature,
                    top_p=args.top_p,
                    max_new_tokens=max_tokens_for_duration(target_duration),
                )
                candidate_duration = audio_duration(candidate)
                difference = abs(candidate_duration - target_duration)
                previous_ratio = candidate_duration / target_duration
                result["attempts"].append(
                    {
                        "seed": seed,
                        "instruction": instruction,
                        "duration": candidate_duration,
                        "ratio": previous_ratio,
                    }
                )
                if best is None or difference < best[0]:
                    best = (difference, candidate, candidate_duration, seed)
                if duration_is_acceptable(candidate_duration, target_duration):
                    break

            assert best is not None
            _, best_path, best_duration, best_seed = best
            if duration_is_acceptable(best_duration, target_duration):
                _align(best_path, output, best_duration, target_duration)
                result.update(
                    status="complete",
                    output=str(output),
                    selected_seed=best_seed,
                    selected_duration=best_duration,
                    aligned_duration=audio_duration(output),
                )
                completed += 1
                for path in made:
                    path.unlink(missing_ok=True)
            else:
                rejected_dir.mkdir(parents=True, exist_ok=True)
                rejected = rejected_dir / f"{row['id']}.wav"
                shutil.copy2(best_path, rejected)
                result.update(
                    status="rejected_duration",
                    closest_duration=best_duration,
                    rejected=str(rejected),
                )
                failed += 1

        with manifest_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
        _write_status(
            status_path,
            {
                "worker": args.shard_index,
                "total": len(rows),
                "processed": position,
                "completed": completed,
                "cached": cached,
                "failed": failed,
                "current_id": row["id"],
            },
        )
        print(
            f"worker {args.shard_index} [{position}/{len(rows)}] {row['id']}: "
            f"{result['status']}",
            flush=True,
        )
    return 1 if failed else 0
