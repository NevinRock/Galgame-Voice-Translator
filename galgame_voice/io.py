from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Iterable


REQUIRED_FIELDS = ("id", "speaker", "jp_text")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def read_lines(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8-sig") as handle:
            for number, raw in enumerate(handle, 1):
                if not raw.strip():
                    continue
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ValueError(f"{path}:{number}: expected a JSON object")
                rows.append(value)
        return rows
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    raise ValueError(f"{path}: only .jsonl and .csv are supported")


def validate_lines(rows: Iterable[dict[str, Any]], source: Path) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for number, row in enumerate(rows, 1):
        for field in REQUIRED_FIELDS:
            if not str(row.get(field, "")).strip():
                errors.append(f"{source}:{number}: missing {field}")
        line_id = str(row.get("id", "")).strip()
        if line_id in seen:
            errors.append(f"{source}:{number}: duplicate id {line_id!r}")
        seen.add(line_id)
    return errors


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(path)


def import_siglus_koe(
    csv_path: Path,
    voice_dir: Path,
    lines_path: Path,
    characters_path: Path,
) -> tuple[int, int]:
    """Convert siglus-ssu's koe_master.csv into pipeline manifests."""
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    audio_by_name = {
        path.name.casefold(): path.resolve()
        for path in voice_dir.rglob("KOE(*).ogg")
        if path.is_file()
    }
    speaker_ids: dict[str, str] = {}
    best_reference: dict[str, tuple[float, Path, str]] = {}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in source_rows:
        raw_number = str(source.get("koe_no", "")).strip()
        text = str(source.get("text", "")).strip()
        character = str(source.get("character", "")).strip() or "旁白"
        if not raw_number.isdigit() or not text:
            continue
        line_id = f"koe_{int(raw_number):09d}"
        if line_id in seen:
            continue
        audio = audio_by_name.get(f"KOE({int(raw_number):09d}).ogg".casefold())
        if audio is None:
            continue
        seen.add(line_id)
        speaker_id = speaker_ids.setdefault(character, f"voice_{len(speaker_ids) + 1:03d}")
        relative_audio = os.path.relpath(audio, lines_path.parent)
        rows.append(
            {
                "id": line_id,
                "speaker": speaker_id,
                "speaker_name": character,
                "jp_text": text,
                "zh_text": "",
                "emotion": "neutral",
                "reference_audio": relative_audio,
                "output": f"{line_id}.wav",
                "callsite": str(source.get("callsite", "")),
            }
        )
        try:
            duration = float(source.get("duration_sec", 0) or 0)
        except ValueError:
            duration = 0
        current = best_reference.get(speaker_id)
        if current is None or duration > current[0]:
            best_reference[speaker_id] = (duration, audio, text)
    write_jsonl(lines_path, rows)
    characters: dict[str, dict[str, str]] = {}
    names_by_id = {value: key for key, value in speaker_ids.items()}
    for speaker_id, (_, audio, text) in best_reference.items():
        characters[speaker_id] = {
            "name": names_by_id[speaker_id],
            "audio": os.path.relpath(audio, characters_path.parent),
            "text": text,
        }
    characters_path.parent.mkdir(parents=True, exist_ok=True)
    characters_path.write_text(
        json.dumps({"characters": characters}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return len(rows), len(characters)


def merge_siglus_koe(
    jp_csv_path: Path,
    zh_csv_path: Path,
    voice_dir: Path,
    lines_path: Path,
    characters_path: Path,
) -> tuple[int, int]:
    """Align original and translated Siglus KOE rows by global voice number."""
    def preferred_rows(path: Path) -> dict[str, dict[str, str]]:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        selected: dict[str, dict[str, str]] = {}
        for row in rows:
            number = str(row.get("koe_no", "")).strip()
            if not number.isdigit() or not str(row.get("text", "")).strip():
                continue
            old = selected.get(number)
            # Production scenes take precedence over bundled developer/test scenes.
            score = int("99999_" not in str(row.get("callsite", "")))
            old_score = int(
                old is not None and "99999_" not in str(old.get("callsite", ""))
            )
            if old is None or score > old_score:
                selected[number] = row
        return selected

    jp_rows = preferred_rows(jp_csv_path)
    zh_rows = preferred_rows(zh_csv_path)
    audio_by_name = {
        path.name.casefold(): path.resolve()
        for path in voice_dir.rglob("KOE(*).ogg")
        if path.is_file()
    }
    speaker_ids: dict[str, str] = {}
    best_reference: dict[str, tuple[float, Path, str]] = {}
    result: list[dict[str, Any]] = []
    for number in sorted(jp_rows, key=int):
        jp = jp_rows[number]
        zh = zh_rows.get(number)
        if zh is None:
            continue
        audio = audio_by_name.get(f"KOE({int(number):09d}).ogg".casefold())
        if audio is None:
            continue
        character = str(jp.get("character", "")).strip() or "旁白"
        speaker_id = speaker_ids.setdefault(character, f"voice_{len(speaker_ids) + 1:03d}")
        line_id = f"koe_{int(number):09d}"
        result.append(
            {
                "id": line_id,
                "speaker": speaker_id,
                "speaker_name": character,
                "jp_text": str(jp["text"]).strip(),
                "zh_text": str(zh["text"]).strip(),
                "emotion": "neutral",
                "reference_audio": os.path.relpath(audio, lines_path.parent),
                "output": f"{line_id}.wav",
                "callsite": str(jp.get("callsite", "")),
            }
        )
        try:
            duration = float(jp.get("duration_sec", 0) or 0)
        except ValueError:
            duration = 0
        current = best_reference.get(speaker_id)
        if current is None or duration > current[0]:
            best_reference[speaker_id] = (duration, audio, str(jp["text"]).strip())
    write_jsonl(lines_path, result)
    names_by_id = {value: key for key, value in speaker_ids.items()}
    characters = {
        speaker_id: {
            "name": names_by_id[speaker_id],
            "audio": os.path.relpath(values[1], characters_path.parent),
            "text": values[2],
        }
        for speaker_id, values in best_reference.items()
    }
    characters_path.parent.mkdir(parents=True, exist_ok=True)
    characters_path.write_text(
        json.dumps({"characters": characters}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return len(result), len(characters)

