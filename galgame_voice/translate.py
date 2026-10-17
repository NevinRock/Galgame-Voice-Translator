from __future__ import annotations

import json
import re
from typing import Any

import requests


SYSTEM_PROMPT = """你是资深日中视觉小说本地化译者。把日文台词译成自然的简体中文普通话口语。
必须保持人物性格、敬语关系、潜台词、停顿、感叹、口吃和情绪强度；不要添加原文没有的信息。
姓名和术语遵循 glossary。结合 context 判断省略的主语。只输出一个 JSON 对象：
{"zh_text":"译文","emotion":"neutral|happy|sad|angry|fearful|whisper|shouting|crying|laughing"}
emotion 只选最接近的一项，用于语音合成，不要把它写进译文。"""


class Translator:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout: float = 300.0,
    ):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.timeout = timeout
        self.session = requests.Session()
        if api_key:
            self.session.headers["Authorization"] = f"Bearer {api_key}"

    def translate(
        self,
        *,
        speaker: str,
        text: str,
        context: list[dict[str, str]],
        glossary: dict[str, str],
    ) -> tuple[str, str]:
        content = json.dumps(
            {
                "speaker": speaker,
                "jp_text": text,
                "context": context,
                "glossary": glossary,
            },
            ensure_ascii=False,
        )
        response = self.session.post(
            self.url,
            json={
                "model": self.model,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": content},
                ],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]
        result = _parse_json(raw)
        translated = str(result.get("zh_text", "")).strip()
        emotion = str(result.get("emotion", "neutral")).strip().lower()
        allowed = {
            "neutral", "happy", "sad", "angry", "fearful", "whisper",
            "shouting", "crying", "laughing",
        }
        if not translated:
            raise ValueError(f"translator returned no zh_text: {raw[:500]}")
        if emotion not in allowed:
            emotion = "neutral"
        return translated, emotion


def _parse_json(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise ValueError(f"translator returned invalid JSON: {raw[:500]}")
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("translator response must be a JSON object")
    return value

