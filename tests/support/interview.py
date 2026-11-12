"""Synthetic responses for the interview editor model ports."""

import json


def interview_author(req):
    data = json.loads(req.messages[-1].content)
    if req.ref.endswith("/classify"):
        assert all(set(q) == {"id", "question"} for q in data["questions"])
        return {"labels": ["기타"] * len(data["questions"])}
    assert req.ref.endswith("/author")
    row = data["records"][0]
    return {
        "cards": [
            dict(
                section="VOICE",
                scope="LOCAL",
                trigger="가까운 상대가 일상의 선택을 물을 때",
                first="상대가 물은 내용부터 답한다.",
                shift="",
                stop="",
                limit="공적인 판단을 묻는 장면까지 넓히지 않는다.",
                evidence=[row["id"]],
            )
        ],
        "unresolved": [],
    }


def interview_judge(req):
    data = json.loads(req.messages[-1].content)
    return {
        "decisions": [
            dict(id=c["id"], decision="APPROVE", reason="범위와 근거가 맞는다.")
            for c in data["cards"]
        ]
    }
