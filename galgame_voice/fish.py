from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

import msgpack
import requests


class FishSpeechError(RuntimeError):
    pass


class FishSpeechClient:
    def __init__(self, base_url: str, api_key: str = "", timeout: float = 600.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        if api_key:
            self.session.headers["Authorization"] = f"Bearer {api_key}"

    def health(self) -> None:
        response = self.session.get(f"{self.base_url}/v1/health", timeout=15)
        self._check(response)

    def add_reference(self, reference_id: str, audio: Path, text: str) -> None:
        mime = mimetypes.guess_type(audio.name)[0] or "application/octet-stream"
        with audio.open("rb") as handle:
            response = self.session.post(
                f"{self.base_url}/v1/references/add",
                data={"id": reference_id, "text": text},
                files={"audio": (audio.name, handle, mime)},
                timeout=self.timeout,
            )
        self._check(response)

    def synthesize(
        self,
        *,
        text: str,
        output: Path,
        reference_id: str | None = None,
        reference_audio: Path | None = None,
        reference_text: str = "",
        character_audio: Path | None = None,
        character_text: str = "",
        seed: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_new_tokens: int | None = None,
    ) -> None:
        references: list[dict[str, Any]] = []
        if character_audio is not None:
            references.append(
                {
                    "audio": character_audio.read_bytes(),
                    "text": character_text,
                    "speaker": 0,
                }
            )
            reference_id = None
        if reference_audio is not None:
            if character_audio is None or reference_audio.resolve() != character_audio.resolve():
                references.append(
                    {
                        "audio": reference_audio.read_bytes(),
                        "text": reference_text,
                        "speaker": 0,
                    }
                )
            reference_id = None
        payload: dict[str, Any] = {
            "text": text,
            "format": output.suffix.lstrip(".").lower() or "wav",
            "references": references,
            "reference_id": reference_id,
            "normalize": True,
            "streaming": False,
            "use_memory_cache": "on",
        }
        for key, value in {
            "seed": seed,
            "temperature": temperature,
            "top_p": top_p,
            "max_new_tokens": max_new_tokens,
        }.items():
            if value is not None:
                payload[key] = value
        response = self.session.post(
            f"{self.base_url}/v1/tts",
            params={"format": "msgpack"},
            data=msgpack.packb(payload, use_bin_type=True),
            headers={"Content-Type": "application/msgpack"},
            timeout=self.timeout,
        )
        self._check(response)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".part")
        temporary.write_bytes(response.content)
        temporary.replace(output)

    @staticmethod
    def _check(response: requests.Response) -> None:
        if response.ok:
            return
        detail = response.text[:1000]
        raise FishSpeechError(
            f"Fish Speech returned HTTP {response.status_code}: {detail}"
        )

