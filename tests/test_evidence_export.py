"""Synthetic, offline evidence-prompt transport through the chat-svc exporter."""

import hashlib
import json

import pytest

from character_factory_poc.contracts.release import CharacterPackage, PackageFile
from character_factory_poc.stages.export.doki_app import chat_svc
from character_factory_poc.stages.s11_release.presentation import CHAT_DISCLOSURE

MARKER = "builtin:evidence-pipeline-v1"
HEADERS = (
    "FACTS",
    "LIFE_AND_TASTES",
    "DISPOSITION",
    "WANTS_AND_FEARS",
    "READING_AND_TENSION",
    "CHOICES",
    "VOICE",
    "KNOWS_AND_LIMITS",
)
PREAMBLE = "역할: 가상의 유리다.\n\n장면: 첫 통화다. 모르는 공동 과거는 만들지 않는다."
NEUTRAL = "자료가 부족하므로 이 영역의 인물 특성을 정하지 않는다."
BODIES = [
    "유리는 31세 제본사다.",
    NEUTRAL,
    "먼저 조건을 확인한다.",
    NEUTRAL,
    "재촉받으면 이유를 묻는다.",
    "조건이 바뀌면 선택을 다시 한다.",
    "반말로 답한다.\n조건과 결론을 나눠 말한다.",
    "모르는 정보는 모른다고 한다.",
]
PROMPT = (
    PREAMBLE
    + "\n\n"
    + "\n\n".join(f"[{header}]\n{body}" for header, body in zip(HEADERS, BODIES, strict=True))
    + "\n"
)


def put(package, root, rel, content):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode() if isinstance(content, str) else json.dumps(content).encode()
    path.write_bytes(data)
    package.files = [item for item in package.files if item.path != rel] + [
        PackageFile(path=rel, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
    ]


def fixture_package(root, *, marker="metadata", prompt=PROMPT):
    package = CharacterPackage.model_validate(
        dict(
            characterId="cf-evidence-export",
            packageRev="pk1",
            builtAt="2026-11-11T00:00:00Z",
            profile=dict(name="유리", gender="female", age="31", job="제본사"),
            appearance=dict(appearanceRev="ar1", heroImage="hero.png", spec="appearance.json"),
            chapters=[
                dict(
                    chapterNo=i,
                    chapterId=f"ch{i}",
                    title="첫 통화",
                    relationshipStage="STRANGER",
                    facts=f"chapters/ch{i}.json",
                    frame="frame.png",
                )
                for i in range(1, 4)
            ],
            videos=[],
            persona=dict(
                personaVersion="pv7",
                traitSheet="persona/trait-sheet.json",
                longPrompt="persona/long-prompt.txt",
            ),
            gates=[],
            files=[],
        )
    )
    put(
        package,
        root,
        package.persona.traitSheet,
        {
            "choice": {"primaryResponse": "STALE_S7_GUESS"},
            "card": {
                "stance": "STALE_S7_GUESS",
                "dialogueHabits": {"order": "STALE_S7_GUESS"},
                "experiences": [{"event": "PRIVATE_S7_STORY"}],
            },
        },
    )
    for i in range(1, 4):
        put(package, root, f"chapters/ch{i}.json", {"sceneFacts": ["첫 통화다."]})
    put(package, root, package.persona.longPrompt, prompt)
    if marker == "metadata":
        put(
            package,
            root,
            "persona/prompt-compiler.json",
            {
                "systemRulesRef": MARKER,
                "personaVersion": "pv7",
                "longPromptSha256": hashlib.sha256(prompt.encode()).hexdigest(),
            },
        )
    elif marker == "pair":
        put(
            package,
            root,
            "persona/prompt-pair.json",
            {
                "schemaVersion": "prompt-pair-v1",
                "characterId": package.characterId,
                "systemRulesRef": MARKER,
                "personaVersion": "pv7",
                "long": {"text": PROMPT, "sha256": hashlib.sha256(PROMPT.encode()).hexdigest()},
                "privateReview": "PRIVATE_PAIR_REVIEW",
            },
        )
    return package


def persona(tree):
    return next(v for k, v in tree.files.items() if k.startswith("personas/"))


@pytest.mark.parametrize("marker", ["metadata", "pair"])
@pytest.mark.parametrize("disclosure", [False, True])
def test_compiled_sections_and_preamble_reach_runtime(tmp_path, marker, disclosure):
    prompt = PROMPT + ("\n" + CHAT_DISCLOSURE + "\n" if disclosure else "")
    package = fixture_package(tmp_path, marker=marker, prompt=prompt)
    # These files must never be loaded or serialized by the exporter.
    (tmp_path / "persona/evidence-review.json").write_text("PRIVATE_REVIEW invalid JSON")
    (tmp_path / "persona/records.jsonl").write_text("PRIVATE_RECORD invalid JSON")
    tree = chat_svc.build_tree(package, tmp_path)
    result = persona(tree)
    for field, body in zip(chat_svc.PERSONA_SECTIONS[:-1], BODIES[:-1], strict=True):
        assert result[field] == [body]
    assert result["boundaries"] == [PREAMBLE, BODIES[-1]] + (
        [CHAT_DISCLOSURE] if disclosure else []
    )
    assert result["identity"] == {"age": 31, "occupation": "제본사", "homeBase": "미상"}
    serialized = json.dumps(tree.files, ensure_ascii=False)
    assert "STALE_S7_GUESS" not in serialized
    assert "PRIVATE_" not in serialized
    assert not chat_svc.validate_content_tree(tree.files)


@pytest.mark.parametrize(
    "bad_prompt",
    [
        PROMPT.replace("[VOICE]\n" + BODIES[6] + "\n\n", ""),
        PROMPT.replace("[VOICE]\n" + BODIES[6], "[VOICE]\n"),
        PROMPT + "\n[VOICE]\nDuplicate\n",
        PROMPT + "\n[REVIEW]\nPrivate review\n",
        PROMPT.replace(PREAMBLE, ""),
    ],
    ids=["missing", "empty", "duplicate", "extra", "no-preamble"],
)
def test_malformed_evidence_never_falls_back_to_traits(tmp_path, bad_prompt):
    package = fixture_package(tmp_path, prompt=bad_prompt)
    with pytest.raises(ValueError, match="evidence"):
        chat_svc.build_tree(package, tmp_path)


@pytest.mark.parametrize("fault", ["revision", "digest", "unlisted", "tampered"])
def test_compiler_metadata_must_be_pinned(tmp_path, fault):
    package = fixture_package(tmp_path)
    rel = "persona/prompt-compiler.json"
    data = json.loads((tmp_path / rel).read_text())
    if fault == "revision":
        data["personaVersion"] = "pv8"
        put(package, tmp_path, rel, data)
    elif fault == "digest":
        data["longPromptSha256"] = "0" * 64
        put(package, tmp_path, rel, data)
    elif fault == "unlisted":
        package.files = [p for p in package.files if p.path != rel]
    else:
        (tmp_path / rel).write_text(json.dumps(data) + " ")
    with pytest.raises(ValueError, match="evidence"):
        chat_svc.build_tree(package, tmp_path)


def test_headers_alone_do_not_change_legacy_export(tmp_path):
    package = fixture_package(tmp_path, marker=None)
    before = chat_svc.build_tree(package, tmp_path)
    put(package, tmp_path, package.persona.longPrompt, "legacy prompt")
    after = chat_svc.build_tree(package, tmp_path)
    assert before.files == after.files
    assert persona(before) == chat_svc._persona(
        package,
        "cf-evidence-export",
        before.persona_revision,
        json.loads((tmp_path / package.persona.traitSheet).read_text()),
    )


def test_unknown_age_is_not_invented(tmp_path):
    package = fixture_package(tmp_path)
    package.profile.age = "미상"
    with pytest.raises(ValueError, match="evidence"):
        chat_svc.build_tree(package, tmp_path)


def test_invalid_compiler_marker_cannot_silently_select_legacy(tmp_path):
    package = fixture_package(tmp_path)
    rel = "persona/prompt-compiler.json"
    data = json.loads((tmp_path / rel).read_text())
    data["systemRulesRef"] = "builtin:unknown-compiler"
    put(package, tmp_path, rel, data)
    with pytest.raises(ValueError, match="evidence"):
        chat_svc.build_tree(package, tmp_path)


@pytest.mark.parametrize("fault", ["revision", "character", "text", "public-text"])
def test_packaged_pair_must_match_public_prompt_and_identity(tmp_path, fault):
    package = fixture_package(tmp_path, marker="pair")
    rel = "persona/prompt-pair.json"
    data = json.loads((tmp_path / rel).read_text())
    if fault == "revision":
        data["personaVersion"] = "pv8"
    elif fault == "character":
        data["characterId"] = "another-character"
    elif fault == "text":
        data["long"]["text"] += "altered"
    else:
        put(package, tmp_path, package.persona.longPrompt, PROMPT + "altered")
    put(package, tmp_path, rel, data)
    with pytest.raises(ValueError, match="evidence"):
        chat_svc.build_tree(package, tmp_path)


@pytest.mark.parametrize("version", [1, 2, 3, 4])
def test_real_evidence_pipeline_through_public_package_and_chat_tree(tmp_path, version):
    """Actual stage functions, fake providers, synthetic sources; no hand-built metadata."""
    from character_factory_poc.common.store import read_json
    from character_factory_poc.stages.s11_release.package import build_package
    from tests.test_twin_export import _approved

    ctx, cid, _, _ = _approved(
        tmp_path,
        "PROMPT_ONLY",
        full_evidence=version == 2,
        atomic_evidence=version == 3,
        tendency_evidence=version == 4,
    )
    marker = f"builtin:evidence-pipeline-v{version}"
    revision = ctx.state(cid).gate("G6").rev
    source = ctx.character_dir(cid) / "s8-prompts" / revision
    pair = read_json(source / "persona-version.json")
    assert pair["systemRulesRef"] == marker
    original = pair["long"]["text"]
    directory = build_package(ctx, cid)
    package = CharacterPackage.model_validate(read_json(directory / "package.json"))
    metadata_path = "persona/prompt-compiler.json"
    assert metadata_path in {item.path for item in package.files}
    public = (directory / package.persona.longPrompt).read_bytes()
    assert read_json(directory / metadata_path) == {
        "systemRulesRef": marker,
        "personaVersion": revision,
        "longPromptSha256": hashlib.sha256(public).hexdigest(),
    }
    assert not (directory / "persona/prompt-pair.json").exists()
    assert not any("evidence-" in item.path for item in package.files)

    tree = chat_svc.build_tree(package, directory)
    exported = persona(tree)
    preamble, _, remaining = original.partition("[FACTS]\n")
    expected = {}
    for i, field in enumerate(chat_svc.PERSONA_SECTIONS):
        if i + 1 < len(HEADERS):
            body, separator, remaining = remaining.partition(f"[{HEADERS[i + 1]}]\n")
            assert separator
        else:
            body = remaining
        expected[field] = [body.strip()]
    expected["boundaries"] = [preamble.strip(), *expected["boundaries"], CHAT_DISCLOSURE]
    assert {field: exported[field] for field in chat_svc.PERSONA_SECTIONS} == expected
    assert not chat_svc.validate_content_tree(tree.files)
    serialized = json.dumps(tree.files, ensure_ascii=False)
    review = read_json(source / "evidence-review.json")
    assert review["cards"]
    for card in review["cards"]:
        for ref in card["evidence"]:
            assert ref not in serialized


def test_v4_compiler_transports_exact_conditions(tmp_path, monkeypatch):
    monkeypatch.setattr(
        __import__(__name__, fromlist=["MARKER"]), "MARKER", "builtin:evidence-pipeline-v4"
    )
    package = fixture_package(tmp_path)
    tree = chat_svc.build_tree(package, tmp_path)
    result = persona(tree)
    assert result["voice"] == [BODIES[6]] and result["boundaries"] == [PREAMBLE, BODIES[-1]]
