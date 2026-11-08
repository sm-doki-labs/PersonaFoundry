"""트윈 이미지·영상 프롬프트에 '가상 인물' 문구가 들어가지 않는지, 성별이 고정되지 않는지 본다."""

from pathlib import Path

from character_factory_poc.stages.s5_intro.first_frame import build_prompt
from character_factory_poc.stages.s6_actions.catalog import NEUTRAL_PROMPT, neutral_prompt
from tests.test_twin_export import _approved

FICTION = ("fictional", "not based on any real individual")


def test_first_frame_follows_subject_and_origin():
    original = build_prompt("9:16", "Korean man")
    assert "same fictional Korean man" in original and FICTION[1] in original
    twin = build_prompt("9:16", "Korean man", twin=True)
    assert "same Korean man" in twin and "identity exactly" in twin
    assert not any(word in twin for word in FICTION)
    # 기본값은 예전 문구(여성 오리지널)와 같다.
    assert "same fictional Korean woman" in build_prompt("9:16")


def test_neutral_prompt_twin_drops_fiction():
    assert neutral_prompt() == NEUTRAL_PROMPT
    assert not any(word in neutral_prompt(twin=True) for word in FICTION)


def test_twin_flow_saved_prompts_have_no_fiction(tmp_path: Path):
    ctx, cid, _, _ = _approved(tmp_path, "PROMPT_ONLY")
    root = ctx.character_dir(cid)
    texts = [
        p.read_text("utf-8", errors="ignore")
        for stage in ("s4-frames", "s5-intro", "s6-actions")
        for p in (root / stage).rglob("*.json")
    ]
    prompts = [t for t in texts if "Keep the person's identity exactly" in t]
    assert prompts, "트윈 이미지 프롬프트 기록을 찾지 못했다"
    assert not any(word in t for t in texts for word in FICTION)
