"""Run against the factory package, or next to its standalone copy with unittest."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if (HERE / "compiler.py").is_file():
    from compiler import compile_prompt, main

    SAMPLE = HERE / "synthetic.json"
else:
    from character_factory_poc.stages.s8_prompts.evidence_compiler import compile_prompt, main

    SAMPLE = HERE.parent / "examples/evidence/synthetic.json"


def packet():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


class EvidenceCompilerTest(unittest.TestCase):
    def test_exact_output_including_whitespace_order_and_audit_exclusion(self):
        data = packet()
        data.update(role=" Rôle  ", scene="\n장면 ", facts="  첫 줄\r\n\n끝 \t\n")
        card = data["sections"][0]
        data["sections"] += [
            card | {"section": "VOICE", "rule": "Speak briefly."},
            card | {"rule": "Wait."},
        ]
        neutral = "자료가 부족하므로 이 영역의 인물 특성을 정하지 않는다."
        expected = (
            "\n\n".join(
                [
                    " Rôle  ",
                    "\n장면 ",
                    "[FACTS]\n  첫 줄\r\n\n끝 \t\n",
                    "[LIFE_AND_TASTES]\n" + neutral,
                    "[DISPOSITION]\n" + neutral,
                    "[WANTS_AND_FEARS]\n" + neutral,
                    "[READING_AND_TENSION]\n" + neutral,
                    "[CHOICES]\n" + card["rule"] + "\nWait.",
                    "[VOICE]\nSpeak briefly.",
                    "[KNOWS_AND_LIMITS]\n" + neutral,
                ]
            )
            + "\n"
        )
        self.assertEqual(compile_prompt(data), expected)

    def test_no_evidence_means_no_traits(self):
        data = packet() | {"sections": [], "trainIds": [], "holdoutIds": []}
        self.assertEqual(compile_prompt(data).count("이 영역의 인물 특성을 정하지 않는다."), 7)

    def test_each_field_required_even_if_an_audit_field_never_renders(self):
        for level in ("packet", "card"):
            for field in packet() if level == "packet" else packet()["sections"][0]:
                data = packet()
                del (data if level == "packet" else data["sections"][0])[field]
                with (
                    self.subTest(level=level, field=field),
                    self.assertRaisesRegex(ValueError, field),
                ):
                    compile_prompt(data)

    def test_split_schema_examples_and_reserved_content_rejected(self):
        for patch in (
            {"holdoutIds": ["train-1"]},
            {"trainIds": ["x", "x"]},
            {"role": " "},
            {"scene": None},
            {"sections": {}},
            {"facts": "Fact\n[VOICE]\nOther"},
            {"examples": []},
            {"holdoutIds": "held-1"},
            {"trainIds": [7]},
            {"scene": "USER: Are you ready?"},
            {"facts": ["a"]},
        ):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                compile_prompt(packet() | patch)

        for patch in (
            {"section": "FACTS"},
            {"section": "OTHER"},
            {"trigger": " "},
            {"limit": []},
            {"rule": ""},
            {"evidence": []},
            {"evidence": ["unknown"]},
            {"evidence": ["train-1", "held-1"]},
            {"evidence": ["train-1", "train-1"]},
            {"evidence": "train-1"},
            {"rule": "USER: hello\nMODEL: hi"},
            {"rule": "예시: 거절하고 기다린다."},
            {"rule": "Say “Sure!”."},
            {"rule": "Wait.\n[CHOICES]\nLeave."},
            {"example": "hello"},
            {"approved": False},
        ):
            data = packet()
            data["sections"][0].update(patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                compile_prompt(data)

    def test_cli_rejects_invalid_input_before_replacing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            src, dst = (Path(directory) / name for name in ("input", "out"))
            self.assertEqual(main([str(SAMPLE), str(dst)]), 0)
            expected = compile_prompt(packet()).encode("utf-8")
            self.assertEqual(dst.read_bytes(), expected)
            for raw in (
                b"{",
                b"\xff",
                b'{"role":"a","role":"b"}',
                SAMPLE.read_bytes().replace(b'"rule":', b'"rule":"hidden","rule":'),
                json.dumps(packet() | {"holdoutIds": ["train-1"]}).encode(),
            ):
                src.write_bytes(raw)
                with self.subTest(raw=raw), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(main([str(src), str(dst)]), 2)
                    self.assertEqual(dst.read_bytes(), expected)
            src.write_bytes(SAMPLE.read_bytes())
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main([str(src), str(src)]), 2)
            self.assertEqual(src.read_bytes(), SAMPLE.read_bytes())


if __name__ == "__main__":
    unittest.main()
