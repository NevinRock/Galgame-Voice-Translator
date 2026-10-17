import json
import tempfile
import unittest
from pathlib import Path

from galgame_voice.io import (
    import_siglus_koe,
    merge_siglus_koe,
    read_json,
    read_lines,
    validate_lines,
    write_jsonl,
)
from galgame_voice.translate import _parse_json
from galgame_voice.adaptive import (
    duration_is_acceptable,
    instruction_for_ratio,
    max_tokens_for_duration,
)


class PipelineTests(unittest.TestCase):
    def test_jsonl_round_trip_keeps_cjk(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lines.jsonl"
            rows = [{"id": "1", "speaker": "星", "jp_text": "行く？", "zh_text": "走吗？"}]
            write_jsonl(path, rows)
            self.assertEqual(read_lines(path), rows)
            self.assertNotIn("\\u", path.read_text(encoding="utf-8"))

    def test_validation_detects_duplicate(self):
        rows = [
            {"id": "1", "speaker": "a", "jp_text": "x"},
            {"id": "1", "speaker": "a", "jp_text": "y"},
        ]
        self.assertTrue(validate_lines(rows, Path("x.jsonl")))

    def test_translator_json_fence_fallback(self):
        result = _parse_json('prefix {"zh_text":"你好","emotion":"happy"} suffix')
        self.assertEqual(result["zh_text"], "你好")

    def test_import_siglus_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            voice = root / "voices" / "フィリア"
            voice.mkdir(parents=True)
            (voice / "KOE(000100001).ogg").write_bytes(b"OggS")
            csv_path = root / "koe_master.csv"
            csv_path.write_text(
                "koe_no,character,text,duration_sec,callsite\n"
                "100001,フィリア,行くの？,1.5,Scene.pck!s.dat:1\n",
                encoding="utf-8",
            )
            lines = root / "job" / "lines.jsonl"
            chars = root / "job" / "characters.json"
            count, speakers = import_siglus_koe(csv_path, root / "voices", lines, chars)
            self.assertEqual((count, speakers), (1, 1))
            self.assertEqual(read_lines(lines)[0]["speaker"], "voice_001")
            self.assertEqual(read_json(chars)["characters"]["voice_001"]["name"], "フィリア")

    def test_merge_prefers_non_test_translation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            voice = root / "voices" / "フィリア"
            voice.mkdir(parents=True)
            (voice / "KOE(000100001).ogg").write_bytes(b"OggS")
            header = "koe_no,character,text,duration_sec,callsite\n"
            jp = root / "jp.csv"
            jp.write_text(header + "100001,フィリア,行くの？,1.5,Scene.pck!main.dat:1\n", encoding="utf-8")
            zh = root / "zh.csv"
            zh.write_text(
                header
                + "100001,フィリア,行くの？,1.5,Scene.pck!99999_test.dat:1\n"
                + "100001,菲莉娅,要走吗？,1.5,Scene.pck!main.dat:1\n",
                encoding="utf-8",
            )
            lines = root / "job" / "lines.jsonl"
            chars = root / "job" / "characters.json"
            count, speakers = merge_siglus_koe(jp, zh, root / "voices", lines, chars)
            self.assertEqual((count, speakers), (1, 1))
            self.assertEqual(read_lines(lines)[0]["zh_text"], "要走吗？")

    def test_adaptive_duration_gate(self):
        self.assertTrue(duration_is_acceptable(5.5, 5.0))
        self.assertFalse(duration_is_acceptable(6.0, 5.0))
        self.assertTrue(duration_is_acceptable(1.2, 1.0))

    def test_adaptive_token_cap_and_pace(self):
        self.assertEqual(max_tokens_for_duration(1.0), 64)
        self.assertEqual(max_tokens_for_duration(100.0), 512)
        self.assertIn("slow", instruction_for_ratio(0.7))
        self.assertIn("fast", instruction_for_ratio(1.4))


if __name__ == "__main__":
    unittest.main()
