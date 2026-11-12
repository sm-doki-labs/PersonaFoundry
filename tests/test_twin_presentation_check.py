"""D-0126 발표 점검: 모티브 패키지의 자동 점검·G9 사람 확인·승인 잠금. 외부 호출 없음."""

from pathlib import Path

import pytest

from character_factory_poc.common.errors import FactoryError
from character_factory_poc.common.store import read_json
from character_factory_poc.stages.s11_release import presentation
from character_factory_poc.stages.s11_release.package import build_package, verify_package_files
from character_factory_poc.stages.s11_release.presentation import (
    CHECK_FILE,
    DISCLOSURE,
    guard_g9,
)
from tests import test_twin_export as flow
from tests.support.export_flow import write_json


def _twin(tmp: Path, monkeypatch, mode: str = "PROMPT_ONLY", **pack_changes):
    """합성 모티브를 G9 대기까지. pack_changes는 출처 묶음 최상위 칸을 덮어쓴다."""
    original = flow._pack

    def pack(where: Path) -> Path:
        path = original(where)
        data = read_json(path)
        for key, value in pack_changes.items():
            if isinstance(value, dict) and isinstance(data.get(key), dict):
                data[key] = {**data[key], **value}
            else:
                data[key] = value
        write_json(path, data)
        return path

    monkeypatch.setattr(flow, "_pack", pack)
    ctx, cid, _ev, _adopted = flow._approved(tmp, mode, legacy_v3=True)
    rev_dir = build_package(ctx, cid)
    return ctx, cid, rev_dir


def _check(rev_dir: Path) -> dict:
    return read_json(rev_dir / CHECK_FILE)


def _by_id(data: dict) -> dict:
    return {c["id"]: c for c in data["checks"]}


def _approve(**checks) -> dict:
    return {"decision": "APPROVE", "reviewer": "u", "presentationChecks": checks}


def test_parent_prompt_only_passes_and_stays_outside_package(tmp_path, monkeypatch):
    ctx, cid, rev_dir = _twin(tmp_path, monkeypatch)
    data = _check(rev_dir)
    assert (data["schemaVersion"], data["status"], data["subjectKind"]) == (
        "twin-presentation-check-v1",
        "PASS",
        "PRIVATE_PERSON",
    )
    checks = _by_id(data)
    assert checks["disclosure"]["places"] == {"package": True, "appSeed": True, "chat": True}
    assert checks["consent"]["applies"] and checks["consent"]["ok"]
    assert DISCLOSURE in (rev_dir / "persona/long-prompt.txt").read_text("utf-8")
    # 동의한 사람 이름·동의 메모는 점검 파일에 옮기지 않는다.
    raw = (rev_dir / CHECK_FILE).read_text("utf-8")
    assert "공개하지 않을 동의 메모" not in raw
    # 검토 산출물이라 패키지 자산 목록에 없고, 내보내기 전 파일 대조도 깨지지 않는다.
    package = read_json(rev_dir / "package.json")
    assert CHECK_FILE not in {f["path"] for f in package["files"]}
    from character_factory_poc.common.schema import validate

    assert verify_package_files(validate("character-package-v1", package), rev_dir) == []
    # 카톡 출처라 가림 확인(권장)만 붙고, 공인 항목은 없다. 권장은 체크하지 않아도 승인된다.
    assert [(h["id"], h["required"]) for h in data["humanChecks"]] == [("chatMasked", False)]
    shown, note = guard_g9(ctx, cid, rev_dir, _approve())
    assert shown == [rev_dir / CHECK_FILE]
    assert "자동 3개 통과" in note and "[아니오] 발표 화면에 나오는 카톡" in note


def test_public_figure_needs_human_reuse_check(tmp_path, monkeypatch):
    ctx, cid, rev_dir = _twin(
        tmp_path, monkeypatch, "BIND_EXISTING", subject={"kind": "PUBLIC_FIGURE"}
    )
    data = _check(rev_dir)
    assert data["status"] == "PASS" and data["subjectKind"] == "PUBLIC_FIGURE"
    assert _by_id(data)["consent"]["applies"] is False
    human = {h["id"]: h["required"] for h in data["humanChecks"]}
    assert human == {
        "noReuse": True,
        "subjectPermission": False,
        "legalReview": False,
        "chatMasked": False,
    }
    with pytest.raises(FactoryError, match="사람 확인이 빠졌다"):
        guard_g9(ctx, cid, rev_dir, _approve(subjectPermission=True))
    with pytest.raises(FactoryError, match="사람 확인이 빠졌다"):
        guard_g9(ctx, cid, rev_dir, _approve(noReuse="yes"))
    shown, note = guard_g9(ctx, cid, rev_dir, _approve(noReuse=True, legalReview=True))
    assert shown == [rev_dir / CHECK_FILE]
    assert "[예] 이 캐릭터가 나오는 장면을 홍보물" in note
    assert "[예] 법무 검토" in note and "[아니오] 본인 측 사용 허락" in note
    # 반려는 사람 확인 없이 받는다.
    assert guard_g9(ctx, cid, rev_dir, {"decision": "REJECT", "reviewer": "u"})[1] == ""


def test_parent_scope_without_presentation_blocks_approve(tmp_path, monkeypatch):
    ctx, cid, rev_dir = _twin(tmp_path, monkeypatch, usageBasis={"scope": "가족끼리만 보는 시험"})
    data = _check(rev_dir)
    consent = _by_id(data)["consent"]
    assert data["status"] == "FAIL" and not consent["ok"]
    assert "가족끼리만 보는 시험" in consent["detail"]
    # 패키지는 만들어지고 G9 대기다. 승인만 막힌다.
    assert ctx.state(cid).gate("G9").status == "AWAITING_HUMAN"
    with pytest.raises(FactoryError, match="공개 동의"):
        guard_g9(ctx, cid, rev_dir, _approve())


def test_banned_terms_come_from_config_and_cover_video_prompts(tmp_path, monkeypatch):
    original = flow._approved

    def approved(tmp, mode, *, legacy_v3=False):
        ctx, *rest = original(tmp, mode, legacy_v3=legacy_v3)
        # 합성 영상 프롬프트에 늘 있는 낱말을 금지어로 두어 영상 프롬프트까지 읽는지 본다.
        ctx.config.stages["s11"] = {"presentation_banned_terms": ["camera", "제본사"]}
        return (ctx, *rest)

    monkeypatch.setattr(flow, "_approved", approved)
    ctx, cid, rev_dir = _twin(tmp_path, monkeypatch)
    endorsement = _by_id(_check(rev_dir))["endorsement"]
    assert endorsement["terms"] == ["camera", "제본사"] and not endorsement["ok"]
    where = {h["where"] for h in endorsement["hits"]}
    assert "프로필 · 직업" in where
    assert any(w.startswith("영상 프롬프트") for w in where), where
    with pytest.raises(FactoryError, match="추천·협력"):
        guard_g9(ctx, cid, rev_dir, _approve())


def test_default_terms_catch_endorsement_but_skip_shared_rule(tmp_path, monkeypatch):
    ctx, cid, rev_dir = _twin(tmp_path, monkeypatch)
    package = presentation.CharacterPackage.model_validate(read_json(rev_dir / "package.json"))
    # 모든 프롬프트에 붙는 공통 규칙("매 턴 채울 공식이 아니다")은 걸리지 않는다.
    prompt = rev_dir / "persona/long-prompt.txt"
    prompt.write_text(prompt.read_text("utf-8") + "\n매 턴 채울 공식이 아니다.\n", "utf-8")
    assert _by_id(_check(rev_dir))["endorsement"]["ok"]
    tagged = package.model_copy(
        update={
            "profile": package.profile.model_copy(
                update={"tagline": "본인이 직접 함께한 공식 캐릭터", "job": "Officially endorsed"}
            )
        }
    )
    result = presentation.run_checks(ctx, cid, rev_dir, tagged)
    hits = _by_id(result)["endorsement"]["hits"]
    expected = {"본인이 직접", "함께한", "공식 캐릭터", "Official", "endorsed"}
    assert {h["term"] for h in hits} == expected
    assert result["status"] == "FAIL"


def test_career_uses_of_gongsik_are_not_endorsement(tmp_path, monkeypatch):
    # D-0213: 2026-11-13 손흥민 프롬프트에서 걸렸던 경력·자리 문장은 보증 표현이 아니다.
    ctx, cid, rev_dir = _twin(tmp_path, monkeypatch)
    prompt = rev_dir / "persona/long-prompt.txt"
    prompt.write_text(
        prompt.read_text("utf-8")
        + "\n토트넘 홋스퍼로 공식 이적했다. 초면이거나 공식 석상에서는 말을 아낀다."
        + " 공식 발표나 공식 기자회견에서는 문장을 맺는다.\n",
        "utf-8",
    )
    assert _by_id(_check(rev_dir))["endorsement"]["ok"]
    package = presentation.CharacterPackage.model_validate(read_json(rev_dir / "package.json"))
    tagged = package.model_copy(
        update={"profile": package.profile.model_copy(update={"tagline": "구단 공식캐릭터"})}
    )
    hits = _by_id(presentation.run_checks(ctx, cid, rev_dir, tagged))["endorsement"]["hits"]
    assert [h["term"] for h in hits] == ["공식캐릭터"]


def test_missing_chat_disclosure_fails(tmp_path, monkeypatch):
    import shutil

    ctx, cid, rev_dir = _twin(tmp_path, monkeypatch)
    copy = tmp_path / "copy" / "pk1"
    shutil.copytree(rev_dir, copy)
    prompt = copy / "persona/long-prompt.txt"
    prompt.write_text(prompt.read_text("utf-8").replace(DISCLOSURE, "기술 시연"), "utf-8")
    package = presentation.CharacterPackage.model_validate(read_json(copy / "package.json"))
    result = presentation.run_checks(ctx, cid, copy, package)
    disclosure = _by_id(result)["disclosure"]
    assert disclosure["places"]["chat"] is False and disclosure["places"]["appSeed"] is True
    assert "대화 프롬프트" in disclosure["detail"] and result["status"] == "FAIL"


def test_missing_check_file_blocks_twin_approve(tmp_path, monkeypatch):
    ctx, cid, rev_dir = _twin(tmp_path, monkeypatch)
    (rev_dir / CHECK_FILE).unlink()
    view = presentation.view(rev_dir, read_json(rev_dir / "package.json"))
    assert view["status"] == "MISSING" and not view["checks"][0]["ok"]
    with pytest.raises(FactoryError, match="발표 점검 결과"):
        guard_g9(ctx, cid, rev_dir, _approve())


def test_g9_items_show_presentation_for_twin_only(tmp_path, monkeypatch):
    from character_factory_poc.web.gate_items import release_package
    from tests.support.export_flow import full_flow

    for name in ("twin", "original"):
        (tmp_path / name).mkdir()
    ctx, cid, rev_dir = _twin(tmp_path / "twin", monkeypatch)
    items = release_package(ctx.character_dir(cid), cid, "s11-release", rev_dir.name)
    pres = items["presentation"]
    assert pres["status"] == "PASS" and pres["disclosure"] == DISCLOSURE
    assert [c["id"] for c in pres["checks"]] == ["disclosure", "endorsement", "consent"]

    octx, ocid = full_flow(tmp_path / "original")
    orev = build_package(octx, ocid)
    assert not (orev / CHECK_FILE).exists()
    oitems = release_package(octx.character_dir(ocid), ocid, "s11-release", orev.name)
    assert "presentation" not in oitems
    assert guard_g9(octx, ocid, orev, {"decision": "APPROVE", "reviewer": "u"}) == ([], "")


def test_public_figure_g9_web_decision_is_blocked_until_checked(tmp_path, monkeypatch):
    """화면이 아니라 서버 결정 경로가 막는지 본다(approve_g9 → guard_g9)."""
    from fastapi.testclient import TestClient

    from character_factory_poc.web import create_app

    ctx, cid, rev_dir = _twin(
        tmp_path, monkeypatch, "BIND_EXISTING", subject={"kind": "PUBLIC_FIGURE"}
    )
    url = f"/api/characters/{cid}/gates/G9/decision"
    with TestClient(create_app(tmp_path)) as client:
        res = client.post(url, json={"decision": "APPROVE", "reviewer": "u"})
        assert res.status_code >= 400 and "사람 확인이 빠졌다" in res.text
        assert ctx.state(cid).gate("G9").status == "AWAITING_HUMAN"
        res = client.post(url, json=_approve(noReuse=True))
        assert res.status_code == 200, res.text
    assert ctx.state(cid).gate("G9").status == "APPROVED"
    records = [read_json(p) for p in (ctx.character_dir(cid) / "gates").rglob("*.json")]
    g9 = [r for r in records if r.get("gate") == "G9"]
    assert g9 and "[예] 이 캐릭터가 나오는 장면을 홍보물" in str(g9[-1])
    assert any(CHECK_FILE in str(r) for r in g9)
