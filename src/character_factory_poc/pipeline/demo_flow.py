"""시연 모드 실행이 끝난 뒤: 테스터 미리보기 발행과 디스코드 알림.

공장 실행(run_until)이 끝날 때마다 부른다. 패키지 승인(G9)까지 왔으면 발행하고, 아니면 어디서
왜 멈췄는지 알린다. 알림 실패는 공장 작업을 멈추지 않는다.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from character_factory_poc.common.notify import notify
from character_factory_poc.pipeline.demo import DemoMode, spent_since

STATUS_FILE = "demo-status.json"


def _name(ctx, cid: str) -> str:
    folder = ctx.character_dir(cid)
    for path, keys in (
        (folder / "source-pack.json", ("subject", "displayName")),
        (folder / "intake-draft.json", ("displayName",)),
    ):
        try:
            value = json.loads(path.read_text("utf-8"))
            for key in keys:
                value = value[key]
            if isinstance(value, str) and value.strip():
                return value.strip()
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return cid


def _write_status(ctx, cid: str, phase: str, detail: str, **extra) -> None:
    payload = {
        "phase": phase,
        "detail": detail,
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        **extra,
    }
    path = Path(ctx.character_dir(cid)) / STATUS_FILE
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _already_published(ctx, cid: str) -> dict | None:
    # 지운 뒤(REMOVED)에는 다시 발행할 수 있어야 한다 — 가장 최근 기록 하나만 본다.
    from character_factory_poc.stages.export.preview import latest_published

    return latest_published(ctx, cid)


def after_demo_run(ctx, cid: str, demo: DemoMode, log, *, error: str | None = None) -> str:
    """발행하거나 멈춘 이유를 알린다. 돌려주는 값은 상태 이름이다."""
    name = _name(ctx, cid)
    spent = spent_since(ctx, cid, demo.enabledAt)
    cost = f"시연 시작 뒤 추정 비용 ${spent:.2f} / 상한 ${demo.budgetUsd:.2f}"
    state = ctx.state(cid)
    if error:
        _write_status(ctx, cid, "failed", error[:300])
        notify("failed", name, [f"공장 실행 중 오류: {error[:300]}", cost], character_id=cid)
        return "failed"
    if state.gate("G9").status == "APPROVED":
        if not demo.publish:
            _write_status(ctx, cid, "packaged", "패키지 승인까지 끝났어요(발행 꺼짐)")
            notify(
                "waiting",
                name,
                ["패키지 승인까지 끝났어요. 발행은 꺼져 있어요.", cost],
                character_id=cid,
            )
            return "packaged"
        # D-0212: 발행은 테스터 발행 노드(px)가 하고 알림도 보낸다. 여기서는 상태만 남긴다.
        if state.stage("px").status == "APPROVED":
            done = _already_published(ctx, cid) or {}
            log.add(f"발행: 테스터 전용 발행 완료(앱 캐릭터 {done.get('apiCharacterId')})")
            _write_status(
                ctx,
                cid,
                "published",
                "테스터 계정에서 볼 수 있어요",
                apiCharacterId=done.get("apiCharacterId"),
                target=done.get("target"),
            )
            return "published"
        px = state.stage("px")
        reason = px.lastError or "테스터 발행 노드가 끝나지 않았어요"
        _write_status(ctx, cid, "publish_failed", reason[:300])
        if px.status != "CHECK_FAILED":  # 실패했으면 노드가 이미 알렸다
            notify("failed", name, [f"발행에서 멈췄어요: {reason[:400]}", cost], character_id=cid)
        return "publish_failed"
    budget_stop = next((s for s in log.steps if "시연 예산 상한" in s), None)
    if budget_stop:
        _write_status(ctx, cid, "budget", budget_stop)
        notify(
            "budget",
            name,
            [budget_stop, "예산을 올리거나 시연 모드를 끈 뒤 다시 실행해 주세요."],
            character_id=cid,
        )
        return "budget"
    stuck = (log.waiting or log.blocked or log.held or [log.stopped_at or "?"])[0]
    reason = next((s for s in reversed(log.steps) if s.startswith(stuck)), f"{stuck}에서 멈췄어요")
    _write_status(ctx, cid, "stopped", reason[:300], at_step=stuck)
    notify("failed", name, [reason[:400], cost], character_id=cid)
    return "stopped"


__all__ = ["STATUS_FILE", "after_demo_run"]
