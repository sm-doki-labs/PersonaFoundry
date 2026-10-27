"""사람 관문 보고서 (LLD §5.21·§6.10, 명세 §7.4, FR-47, D-0049).

가짜 공급자 전체 흐름을 한 번 돌린 뒤(학습 없이 긴 프롬프트 경로) 관문 기록·state 파일·관문 사건
기록만으로 보고서가 다시 만들어지는지 본다. 네트워크를 쓰지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path

from character_factory_poc.cli import main
from character_factory_poc.pipeline.graph import GATES
from character_factory_poc.pipeline.hil_report import build_hil_report
from tests import test_offline_pipeline as flow


def run_to_export(tmp_path: Path) -> tuple[Path, Path, str]:
    """drive: 관문 결정을 모두 웹 API로 보내 sx까지 가는 경로(test_offline_pipeline 공용)."""
    root = tmp_path / "factory"
    ctx, cid, rounds, log = flow.drive(root, "female", submit_training=False, seen={})
    assert ctx.state(cid).stage("sx").status == "APPROVED", log.steps[-8:]
    return root, ctx.character_dir(cid), cid


def test_hil_report_rebuilds_every_gate_round(tmp_path: Path) -> None:
    root, char_dir, cid = run_to_export(tmp_path)
    report = build_hil_report(char_dir)

    assert report.schemaVersion == "hil-report-v1"
    assert report.subjectId == cid
    assert [gate.gate for gate in report.gates] == GATES
    assert len(report.gates) == 12
    for gate in report.gates:
        assert gate.rounds, gate.gate
        for round_ in gate.rounds:
            assert round_.openedAt, (gate.gate, round_.rev)
            assert round_.decidedAt, (gate.gate, round_.rev)
            assert round_.waitMinutes is not None and round_.waitMinutes >= 0
            assert round_.decision in {"APPROVE", "SELECT", "REJECT", "REQUEST_CHANGES"}
    assert report.totals.gatesDecided == 12
    assert report.totals.reviewMinutes > 0
    assert report.totals.requestChanges == 0  # 이 흐름은 수정 요청 없이 승인만 한다

    # G7a·G8은 사람 판정 자체가 관문의 내용이라 추천 일치 여부를 늘 비운다.
    for gate in report.gates:
        if gate.gate in {"G7a", "G8"}:
            assert [r.followedReview for r in gate.rounds] == [None] * len(gate.rounds)
    # C 갈래(수정 요청 재작업)의 브리프가 아직 없으므로 반복 상한은 거짓이다.
    assert not any(gate.reworkCapReached for gate in report.gates)

    g1 = next(gate for gate in report.gates if gate.gate == "G1")
    record = json.loads(
        (char_dir / "gates" / f"G1-{g1.rounds[0].rev}.json").read_text(encoding="utf-8")
    )
    assert g1.rounds[0].reviewMinutes == record["minutes"] == 1.5
    events = [
        json.loads(line)
        for line in (char_dir / "ledger" / "gate-events.jsonl").read_text("utf-8").splitlines()
        if line.strip()
    ]
    opened = next(e["at"] for e in events if e["gate"] == "G1" and e["event"] == "opened")
    decided = next(e["at"] for e in events if e["gate"] == "G1" and e["event"] == "decided")
    assert g1.rounds[0].openedAt == opened
    assert g1.rounds[0].decidedAt == decided


def test_cli_report_hil_writes_a_timestamped_file(tmp_path: Path) -> None:
    root, char_dir, cid = run_to_export(tmp_path)
    assert main(["--root", str(root), "report", "hil", cid]) == 0
    files = sorted((char_dir / "reports").glob("hil-*.json"))
    assert len(files) == 1, files
    assert files[0].name.startswith("hil-") and files[0].suffix == ".json"
    written = json.loads(files[0].read_text(encoding="utf-8"))
    assert written["schemaVersion"] == "hil-report-v1"
    assert written["subjectId"] == cid
    assert [gate["gate"] for gate in written["gates"]] == GATES
    assert written["totals"]["gatesDecided"] == 12
