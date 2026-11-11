"""검증한 V3 편집 지시로 승인 자료를 조립한다. 예시와 팩트는 모델이 다시 쓰지 않는다."""

from __future__ import annotations

import json
from collections import Counter
from importlib.resources import files
from statistics import median

from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import read_json
from character_factory_poc.providers.base import ChatRequest, Message, extract_json_object
from character_factory_poc.stages.s0_source.run import load_approved_source
from character_factory_poc.stages.s8_prompts.twin import motif_facts, voice_lines

VERSION = "motif-assembler-v3"


def instructions():
    return files("character_factory_poc.resources").joinpath(VERSION + ".md").read_text("utf-8")


def packet(ctx, cid, plan, sheet, voice, facts, ledger):
    pack, index, rows = load_approved_source(ctx, cid)
    folder = ctx.character_dir(cid) / "s0-source" / index.sourceRev
    flagged = {x["msgId"] for x in read_json(folder / "digest.json")["piiFlags"]}
    chat = all(src.kind == "KAKAO_EXPORT" for src in pack.texts)
    if pack.chapterTemplate == "FRIEND_CHAT":
        scene = "오래된 친구와 메신저로 대화한다. 원문에서 확인된 말높임을 따른다."
    elif pack.chapterTemplate == "INTERVIEW":
        scene = (
            "질문자가 인터뷰의 주제와 진행 순서를 정하고 인물은 질문에 답한다. "
            "원문에서 확인된 말높임을 따른다."
        )
    else:
        scene = (
            "익숙한 상대와 카톡으로 대화. 말높임과 거리는 원문에 맞춘다."
            if chat
            else "처음 만나는 팬과 통화. 해요체."
            if pack.chapterTemplate == "FAN_CALL"
            else "가족과 통화. 원문의 관계와 말높임."
        )
    examples = {}
    refs = {x["msgId"] for x in voice["examples"]}
    texts = []
    for i, row in enumerate(rows):
        mid, text = row["msgId"], row["text"]
        if row["speaker"] != "SUBJECT" or mid in flagged:
            continue
        texts.append(text)
        if mid not in refs or len(text) > 450:
            continue
        prev = rows[i - 1] if i else {}
        if (
            prev.get("speaker") == "USER"
            and prev["convId"] == row["convId"]
            and prev["textId"] == row["textId"]
            and prev["msgId"] not in flagged
            and len(prev["text"]) <= 250
        ):
            text = prev["text"] + " → " + text
        examples[mid] = text
    if not examples:
        raise ValueError("모티브 V3에 쓸 검토된 본인 발화가 없다")
    analysis = {
        "voice": voice_lines(plan.voiceSummary, voice),
        "disposition": plan.coreTraits,
        "choices": [dump(c) for c in plan.choices],
        "communication": dump(sheet.choice),
        "boundaries": plan.boundaries,
        "observedTraits": [t for t in ledger.get("traits", []) if t.get("basis") != "INFERRED"],
        "messageLengthMedian": median(map(len, texts)),
        "frequentShortForms": Counter(t for t in texts if len(t) <= 5).most_common(12),
    }
    info = [f"이 대화 상대는 {plan.name}에서 모티브를 얻은 AI 캐릭터다. 실제 본인은 아니다."]
    info += [
        v
        for k, v in pack.knownFacts.items()
        if k in {"age", "gender", "job", "background", "relation"}
    ]
    info += motif_facts(facts)
    # 공인의 G3 생활·취향도 본인 원문 근거가 있는 항목만 전달.
    if pack.subject.kind == "PUBLIC_FIGURE":
        info.extend(
            t
            for t, e in zip(plan.lifeAndTastes, plan.evidence.get("lifeAndTastes", []), strict=True)
            if e.kind == "SOURCE" and e.ref not in flagged
        )
    return dict(
        identity=plan.name + " 모티브",
        scene=scene + " 화면에 AI 모티브임이 표시된다.",
        analysis=analysis,
        examples=examples,
        facts="\n".join(dict.fromkeys(info)),
    )


def assemble(model, data, ref, rework=None):
    instruction = instructions()
    payload = {**data, **({"editorRevision": rework} if rework else {})}
    response = model.complete(
        ChatRequest(
            kind="AGENT",
            stage="s8",
            ref=ref,
            max_output_tokens=6000,
            response_json=True,
            messages=(
                Message("system", instruction),
                Message("user", json.dumps(payload, ensure_ascii=False)),
            ),
        )
    )
    out = extract_json_object(response.text)
    ids, frame = out.get("ids"), out.get("frame")
    if (
        not isinstance(frame, str)
        or not frame.strip()
        or not isinstance(ids, list)
        or not 1 <= len(ids) <= 3
        or not all(isinstance(k, str) and k in data["examples"] for k in ids)
        or len(set(ids)) != len(ids)
    ):
        raise ValueError("모티브 V3: frame과 서로 다른 원문 예시 키 1~3개가 필요하다")
    text = (
        frame.strip()
        + "\n\n[확인된 설정과 정보]\n"
        + data["facts"]
        + "\n\n[자료에서 고른 발화 참고]\n"
        + "\n".join(data["examples"][k] for k in ids)
    )
    return text, {"frame": frame.strip(), "ids": ids, "responseModel": response.model}
