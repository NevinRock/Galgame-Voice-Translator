from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from .fish import FishSpeechClient
from .io import (
    import_siglus_koe,
    merge_siglus_koe,
    read_json,
    read_lines,
    validate_lines,
    write_jsonl,
)
from .translate import Translator
from .adaptive import run_adaptive


EMOTION_TAGS = {
    "happy": "[happy]",
    "sad": "[sad]",
    "angry": "[angry]",
    "fearful": "[fearful]",
    "whisper": "[whisper]",
    "shouting": "[shouting]",
    "crying": "[crying]",
    "laughing": "[laughing]",
}


def _path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _load_characters(path: Path) -> dict[str, dict[str, Any]]:
    data = read_json(path)
    characters = data.get("characters")
    if not isinstance(characters, dict):
        raise ValueError(f"{path}: missing characters object")
    return characters


def _resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def cmd_validate(args: argparse.Namespace) -> int:
    rows = read_lines(args.lines)
    errors = validate_lines(rows, args.lines)
    characters = _load_characters(args.characters)
    for number, row in enumerate(rows, 1):
        speaker = str(row.get("speaker", "")).strip()
        if speaker and speaker not in characters:
            errors.append(f"{args.lines}:{number}: unknown speaker {speaker!r}")
        audio_value = str(row.get("reference_audio", "")).strip()
        if audio_value and not _resolve(args.lines.parent, audio_value).is_file():
            errors.append(f"{args.lines}:{number}: missing reference audio {audio_value}")
    for speaker, config in characters.items():
        audio_value = str(config.get("audio", "")).strip()
        text = str(config.get("text", "")).strip()
        if not audio_value or not _resolve(args.characters.parent, audio_value).is_file():
            errors.append(f"{args.characters}: {speaker}: missing audio")
        if not text:
            errors.append(f"{args.characters}: {speaker}: missing reference transcript")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    print(f"OK: {len(rows)} lines, {len(characters)} characters")
    return 0


def cmd_import_siglus(args: argparse.Namespace) -> int:
    if args.zh_koe_csv:
        line_count, character_count = merge_siglus_koe(
            args.koe_csv,
            args.zh_koe_csv,
            args.voice_dir,
            args.output,
            args.characters,
        )
    else:
        line_count, character_count = import_siglus_koe(
            args.koe_csv, args.voice_dir, args.output, args.characters
        )
    print(
        f"wrote {line_count} lines to {args.output} and "
        f"{character_count} characters to {args.characters}"
    )
    return 0


def _fish(args: argparse.Namespace) -> FishSpeechClient:
    return FishSpeechClient(
        args.url,
        args.api_key or os.environ.get("FISH_API_KEY", ""),
        args.timeout,
    )


def cmd_register(args: argparse.Namespace) -> int:
    client = _fish(args)
    client.health()
    characters = _load_characters(args.characters)
    for speaker, config in characters.items():
        audio = _resolve(args.characters.parent, str(config["audio"]))
        client.add_reference(speaker, audio, str(config["text"]))
        print(f"registered {speaker}: {audio.name}")
    return 0


def cmd_translate(args: argparse.Namespace) -> int:
    rows = read_lines(args.lines)
    errors = validate_lines(rows, args.lines)
    if errors:
        raise ValueError("\n".join(errors))
    glossary = read_json(args.glossary) if args.glossary else {}
    translator = Translator(
        args.url,
        args.model,
        args.api_key or os.environ.get("TRANSLATE_API_KEY", ""),
        args.timeout,
    )
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        item = dict(row)
        if str(item.get("zh_text", "")).strip() and not args.overwrite:
            result.append(item)
            continue
        previous = result[max(0, len(result) - args.context) :]
        context = [
            {
                "speaker": str(x.get("speaker", "")),
                "jp_text": str(x.get("jp_text", "")),
                "zh_text": str(x.get("zh_text", "")),
            }
            for x in previous
        ]
        translated, emotion = translator.translate(
            speaker=str(item["speaker"]),
            text=str(item["jp_text"]),
            context=context,
            glossary={str(k): str(v) for k, v in glossary.items()},
        )
        item["zh_text"] = translated
        item["emotion"] = emotion
        result.append(item)
        write_jsonl(args.output, result + rows[index + 1 :])
        print(f"[{index + 1}/{len(rows)}] {item['id']}: {translated}")
    write_jsonl(args.output, result)
    return 0


def cmd_synthesize(args: argparse.Namespace) -> int:
    rows = read_lines(args.lines)
    errors = validate_lines(rows, args.lines)
    if errors:
        raise ValueError("\n".join(errors))
    if args.id:
        wanted = set(args.id)
        rows = [row for row in rows if str(row.get("id", "")) in wanted]
        missing = wanted - {str(row.get("id", "")) for row in rows}
        if missing:
            raise ValueError(f"unknown line id(s): {', '.join(sorted(missing))}")
    if args.speaker:
        rows = [
            row
            for row in rows
            if str(row.get("speaker", "")) == args.speaker
            or str(row.get("speaker_name", "")) == args.speaker
        ]
    if args.limit is not None:
        rows = rows[: args.limit]
    if not rows:
        raise ValueError("no lines matched the requested filters")
    client = _fish(args)
    client.health()
    characters_path = args.characters
    if characters_path is None:
        candidate = args.lines.parent / "characters.json"
        characters_path = candidate if candidate.is_file() else None
    characters = _load_characters(characters_path) if characters_path else {}
    failures = 0
    for index, row in enumerate(rows, 1):
        translated = str(row.get("zh_text", "")).strip()
        if not translated:
            print(f"skip {row['id']}: no zh_text", file=sys.stderr)
            failures += 1
            continue
        relative = str(row.get("output", "")).strip() or f"{row['id']}.{args.format}"
        output = (args.output_dir / relative).resolve()
        if args.output_dir not in output.parents:
            raise ValueError(f"output escapes output directory: {relative}")
        if output.exists() and output.stat().st_size > 44 and not args.overwrite:
            print(f"[{index}/{len(rows)}] cached {output.name}")
            continue
        emotion = str(row.get("emotion", "neutral")).strip().lower()
        tag = EMOTION_TAGS.get(emotion, "") if args.emotion_tags else ""
        synthesis_text = f"{args.instruction} {tag} {translated}".strip()
        audio_value = str(row.get("reference_audio", "")).strip()
        line_audio = _resolve(args.lines.parent, audio_value) if audio_value else None
        character = characters.get(str(row["speaker"]), {})
        character_audio_value = str(character.get("audio", "")).strip()
        character_audio = (
            _resolve(characters_path.parent, character_audio_value)
            if characters_path and character_audio_value
            else None
        )
        if args.reference_mode == "character":
            # The exact Japanese line can overpower a short Mandarin target
            # and make Drama 3 repeat its Japanese prompt. A single, longer
            # character reference is safer for cross-lingual synthesis.
            line_audio = None
        elif args.reference_mode == "line":
            character_audio = None
        last_error: Exception | None = None
        for attempt in range(1, args.retries + 1):
            try:
                client.synthesize(
                    text=synthesis_text,
                    output=output,
                    reference_id=str(row["speaker"]),
                    reference_audio=line_audio,
                    reference_text=str(row["jp_text"]),
                    character_audio=character_audio,
                    character_text=str(character.get("text", "")),
                    seed=(
                        args.seed
                        if args.seed is not None
                        else int(row["seed"])
                        if str(row.get("seed", "")).strip()
                        else None
                    ),
                    temperature=args.temperature,
                    top_p=args.top_p,
                    max_new_tokens=args.max_new_tokens,
                )
                print(f"[{index}/{len(rows)}] wrote {output}")
                last_error = None
                break
            except Exception as exc:  # keep a long batch resumable
                last_error = exc
                print(f"attempt {attempt} failed for {row['id']}: {exc}", file=sys.stderr)
                if attempt < args.retries:
                    time.sleep(min(2 ** attempt, 10))
        if last_error is not None:
            failures += 1
            if args.fail_fast:
                raise last_error
    return 1 if failures else 0


def add_fish_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--timeout", type=float, default=600)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="galgame-voice")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate manifests and local files")
    validate.add_argument("--lines", type=_path, required=True)
    validate.add_argument("--characters", type=_path, required=True)
    validate.set_defaults(func=cmd_validate)

    importer = sub.add_parser("import-siglus", help="convert siglus-ssu koe_master.csv")
    importer.add_argument("--koe-csv", type=_path, required=True)
    importer.add_argument("--zh-koe-csv", type=_path)
    importer.add_argument("--voice-dir", type=_path, required=True)
    importer.add_argument("--output", type=_path, required=True)
    importer.add_argument("--characters", type=_path, required=True)
    importer.set_defaults(func=cmd_import_siglus)

    register = sub.add_parser("register", help="upload reusable character voices")
    register.add_argument("--characters", type=_path, required=True)
    add_fish_options(register)
    register.set_defaults(func=cmd_register)

    translate = sub.add_parser("translate", help="translate Japanese lines with an OpenAI-compatible LLM")
    translate.add_argument("--lines", type=_path, required=True)
    translate.add_argument("--output", type=_path, required=True)
    translate.add_argument("--glossary", type=_path)
    translate.add_argument("--url", required=True, help="base URL ending in /v1")
    translate.add_argument("--model", required=True)
    translate.add_argument("--api-key", default="")
    translate.add_argument("--timeout", type=float, default=300)
    translate.add_argument("--context", type=int, default=8)
    translate.add_argument("--overwrite", action="store_true")
    translate.set_defaults(func=cmd_translate)

    synth = sub.add_parser("synthesize", help="generate Mandarin audio")
    synth.add_argument("--lines", type=_path, required=True)
    synth.add_argument(
        "--characters",
        type=_path,
        help="character references; defaults to characters.json beside --lines",
    )
    synth.add_argument("--output-dir", type=_path, required=True)
    synth.add_argument("--id", action="append", help="generate one line ID; repeatable")
    synth.add_argument("--speaker", help="filter by speaker ID or original name")
    synth.add_argument("--limit", type=int, help="generate at most this many matching lines")
    synth.add_argument(
        "--reference-mode",
        choices=("character", "line", "dual"),
        default="character",
        help=(
            "reference strategy; character is safest for Japanese-to-Chinese, "
            "while dual adds the exact source line for stronger prosody"
        ),
    )
    synth.add_argument("--format", choices=("wav", "mp3", "opus"), default="wav")
    synth.add_argument("--temperature", type=float)
    synth.add_argument("--top-p", type=float)
    synth.add_argument("--seed", type=int, help="override the per-line random seed")
    synth.add_argument("--max-new-tokens", type=int)
    synth.add_argument(
        "--instruction",
        default="",
        help="optional inline natural-language control tag",
    )
    synth.add_argument("--retries", type=int, default=3)
    synth.add_argument("--overwrite", action="store_true")
    synth.add_argument("--fail-fast", action="store_true")
    synth.add_argument("--no-emotion-tags", action="store_false", dest="emotion_tags")
    add_fish_options(synth)
    synth.set_defaults(func=cmd_synthesize)

    adaptive = sub.add_parser(
        "synthesize-adaptive",
        help="generate, duration-check, retry and rhythm-align a resumable shard",
    )
    adaptive.add_argument("--lines", type=_path, required=True)
    adaptive.add_argument("--characters", type=_path, required=True)
    adaptive.add_argument("--output-dir", type=_path, required=True)
    adaptive.add_argument("--shard-index", type=int, required=True)
    adaptive.add_argument("--num-shards", type=int, default=1)
    adaptive.add_argument("--max-attempts", type=int, default=8)
    adaptive.add_argument("--limit", type=int, help="process at most this many shard rows")
    adaptive.add_argument("--temperature", type=float, default=0.55)
    adaptive.add_argument("--top-p", type=float, default=0.65)
    add_fish_options(adaptive)
    adaptive.set_defaults(func=run_adaptive)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        raise SystemExit(args.func(args))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)

