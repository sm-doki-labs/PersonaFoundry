"""cfp 명령 (LLD §4). 기본은 dry run이다."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import character_factory_poc.contracts  # noqa: F401  계약 등록
from character_factory_poc.common.budget import format_plan
from character_factory_poc.common.errors import FactoryError
from character_factory_poc.common.store import verify_manifest
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.gates import parse_answer
from character_factory_poc.pipeline.graph import GATES, STAGES


def _root(args) -> Path:
    return Path(args.root).resolve()


def cmd_status(args) -> int:
    ctx = Context.load(_root(args), execute=False)
    st = ctx.state(args.character_id)
    print(f"{st.state.subjectId}")
    print(f"{'단계':<5}{'이름':<12}{'상태':<16}{'rev':<8}{'시도':<4}{'구현'}")
    for sid, s in STAGES.items():
        x = st.stage(sid)
        impl = "O" if s.implemented else "-"
        print(f"{sid:<5}{s.name:<12}{x.status:<16}{x.currentRev or '-':<8}{x.attempts:<4}{impl}")
    print()
    shown = [g for g in GATES if st.gate(g).status != "PENDING"]
    # G2는 결번이다(D-0042). 옛 state.json의 G2 칸은 읽기만 하고 결번으로 표시한다.
    legacy = [
        g for g in sorted(st.state.gates) if g not in GATES and st.gate(g).status != "PENDING"
    ]
    for g in shown + legacy:
        x = st.gate(g)
        suffix = "" if g in GATES else " (결번·옛 기록)"
        print(f"{g}: {x.status} rev={x.rev} record={x.recordRef}{suffix}")
    return 0


def cmd_plan_import(args) -> int:
    from character_factory_poc.stages.s3_plan.importer import import_plan

    ctx = Context.load(_root(args), execute=True)
    plan = import_plan(ctx, args.slug, Path(args.source), args.brief)
    print(f"기획서 고정: {plan.characterId} {plan.planRev} (G3 승인 기록: manual-plan)")
    return 0


def cmd_persona_traits(args) -> int:
    from character_factory_poc.stages.s7_traits import sheet as s7

    ctx = Context.load(_root(args), execute=args.execute, max_calls=args.max_calls)
    retries = int(ctx.config.stage("s7").get("max_check_retries", 3))
    refs = json.loads(Path(args.references).read_text("utf-8")) if args.references else None
    docs = {}
    for p in args.reference_doc or []:
        path = Path(p)
        raw = path.read_text("utf-8")
        docs[path.stem] = json.loads(raw) if path.suffix == ".json" else raw
    if not args.execute:
        print(format_plan(s7.plan_calls(retries)))
        return 0
    out = s7.run_s7(ctx, args.character_id, refs, docs or None)
    print(f"특질 시트: {out}")
    return 0


def _read_lines(path: str | None) -> list[str]:
    if not path:
        return []
    return [ln.strip() for ln in Path(path).read_text("utf-8").splitlines() if ln.strip()]


def cmd_persona_prompts(args) -> int:
    from character_factory_poc.stages.s8_prompts import build as s8

    ctx = Context.load(_root(args), execute=args.execute, max_calls=args.max_calls)
    retries = int(ctx.config.stage("s8").get("max_check_retries", 3))
    probes = _read_lines(args.probes)
    if not args.execute:
        print(format_plan(s8.plan_calls(retries, len(probes))))
        return 0
    out = s8.run_s8(ctx, args.character_id, probes, args.allow_same_family)
    print(f"프롬프트 쌍: {out}\n검토 페이지: {out / 'gate-G6.html'}")
    return 0


def cmd_persona_probe(args) -> int:
    from character_factory_poc.stages.s8_prompts import build as s8

    ctx = Context.load(_root(args), execute=args.execute, max_calls=args.max_calls)
    probes = _read_lines(args.probes)
    if not args.execute:
        print(format_plan([s8.plan_calls(0, len(probes))[1]]))
        return 0
    out = s8.rerun_probes(ctx, args.character_id, probes, args.allow_same_family)
    print(f"표본 재실행: {out}\n검토 페이지: {out / 'gate-G6.html'}")
    return 0


def cmd_gate_import(args) -> int:
    ctx = Context.load(_root(args), execute=True)
    answer = parse_answer(Path(args.answer))
    from character_factory_poc.pipeline.approve import approve_gate

    out = approve_gate(ctx, args.character_id, args.gate, answer)
    print(f"{args.gate} {answer['decision']} 기록: {out}")
    return 0


def cmd_ref_run(args) -> int:
    from character_factory_poc.stages.s1_reference import run as s1
    from character_factory_poc.stages.s3_plan.draft import new_character

    ctx = Context.load(_root(args), execute=args.execute, max_calls=args.max_calls)
    ranking = json.loads(Path(args.ranking).read_text("utf-8"))
    if not args.execute:
        print(s1.describe_ranking(ranking))
        image_adapter = ctx.config.provider("image").adapter
        print(format_plan(s1.plan_calls(s1.s1_config(ctx), image_adapter)))
        return 0
    cid = args.character_id
    if args.new_slug:
        cid = new_character(ctx, args.new_slug)
        print(f"새 캐릭터: {cid}")
    out = s1.run_s1(ctx, cid, ranking)
    print(f"S1 보고서: {out / 'report.json'}\n검토 페이지: {out / 'gate-G1.html'} (G1 대기)")
    return 0


def cmd_check(args) -> int:
    from character_factory_poc.checks.cli import main as check_main

    return check_main([args.stage, args.workspace])


def cmd_hero_run(args) -> int:
    from character_factory_poc.stages.s2_hero import run as s2

    ctx = Context.load(_root(args), execute=args.execute, max_calls=args.max_calls)
    cfg = s2.s2_config(ctx)
    if not args.execute:
        print(format_plan(s2.plan_calls(cfg)))
        return 0
    out = s2.run_s2(ctx, args.character_id)
    print(f"S2 외모 명세: {out / 'appearance-spec.json'} (자동 APPROVED, 관문 없음)")
    return 0


def cmd_ref_faces(args) -> int:
    """G1 REQUEST_CHANGES의 메모로 얼굴 미리보기만 다시 만든다(D-0043)."""
    from character_factory_poc.stages.s1_reference import faces as s1f

    ctx = Context.load(_root(args), execute=args.execute, max_calls=args.max_calls)
    if not args.execute:
        try:
            print(format_plan(s1f.plan_calls(ctx, args.character_id)))
        except FactoryError as e:
            print(f"아직 실행할 수 없다: {e}")
        return 0
    out = s1f.run_faces(ctx, args.character_id)
    print(f"얼굴 미리보기: {out / 'previews.json'}\n검토 페이지: {out / 'gate-G1.html'} (G1 대기)")
    return 0


def cmd_ref_collect(args) -> int:
    """S1 순위 수집(B 갈래). 결과는 cfp ref run --ranking에 그대로 넘긴다."""
    from character_factory_poc.collectors import (
        DEFAULT_CATEGORIES,
        CollectRequest,
        RankifySource,
        collect_ranking,
        now_utc,
        plan_collection,
    )
    from character_factory_poc.collectors.http import FetchSettings
    from character_factory_poc.common.config import load_config
    from character_factory_poc.common.store import write_once_json
    from character_factory_poc.contracts.reference import RankingScope

    root = _root(args)
    collect_cfg = dict(load_config(root).stage("s1").get("collect", {}))
    scope = RankingScope(
        characterGender=args.character_gender,
        ageRange=args.age_range,
        artStyle=args.art_style,
        appearanceOrigin=args.origin,
    )
    if args.categories:
        categories = tuple(c.strip() for c in args.categories.split(",") if c.strip())
    else:
        categories = tuple(collect_cfg.pop("categories", None) or DEFAULT_CATEGORIES)
    collect_cfg.pop("categories", None)
    request = CollectRequest(scope=scope, categories=categories)
    settings = FetchSettings.from_mapping(collect_cfg)
    source = RankifySource()
    if not args.execute:
        print(plan_collection(source, request, settings=settings))
        return 0
    result, record = collect_ranking(source, request, settings=settings)
    stamp = now_utc().replace(":", "").replace("-", "")
    out_dir = (
        Path(args.out) if args.out else root / "runs" / "rankings" / f"{stamp}-{source.source_id}"
    )
    write_once_json(out_dir / "ranking.json", result.document())
    write_once_json(out_dir / "collection-record.json", record)
    print(f"순위 목록: {out_dir / 'ranking.json'}\n수집 기록: {out_dir / 'collection-record.json'}")
    return 0


def _run_stage(args, stage: str, module, fn_name: str, done: str) -> int:
    """단계 하나를 dry run(호출 계획) 또는 --execute로 돌린다(D-0033 흐름 공통)."""
    ctx = Context.load(_root(args), execute=args.execute, max_calls=args.max_calls)
    if not args.execute:
        try:
            ctx.state(args.character_id).require_deps(stage)
        except FactoryError as e:
            print(f"아직 실행할 수 없다: {e}")
        print(format_plan(module.plan_calls(ctx)))
        return 0
    out = getattr(module, fn_name)(ctx, args.character_id)
    if out is None:
        print(f"{stage}: 건너뜀({ctx.state(args.character_id).stage(stage).status})")
    else:
        print(f"{done}: {out}")
    return 0


def cmd_frames_run(args) -> int:
    from character_factory_poc.stages.s4_frames import run as s4

    return _run_stage(args, "s4", s4, "run_s4", "챕터 완성 이미지(G4 대기, gate-G4.html)")


def cmd_plan_seed(args) -> int:
    from character_factory_poc.stages.s3_plan.seed import write_seed

    ctx = Context.load(_root(args), execute=True)
    fields: dict = json.loads(Path(args.file).read_text("utf-8")) if args.file else {}
    for k in ("personality", "job", "age", "gender", "background", "notes"):
        v = getattr(args, k, None)
        if v not in (None, ""):
            fields[k] = v
    seed = write_seed(ctx, args.character_id, fields)
    print(f"기획 씨앗 고정: {seed.seedRev} (다음: cfp plan variants {args.character_id})")
    return 0


def cmd_plan_variants(args) -> int:
    from character_factory_poc.stages.s3_plan import variants as s3v

    return _run_stage(args, "s3", s3v, "run_s3_variants", "기획 변형(G3 대기, gate-G3.html)")


def cmd_plan_own(args) -> int:
    from character_factory_poc.stages.s3_plan import own as s3o

    ctx = Context.load(_root(args), execute=args.execute, max_calls=args.max_calls)
    if not args.execute:
        print(format_plan(s3o.plan_calls(ctx)))
        return 0
    text = Path(args.file).read_text("utf-8")
    out = s3o.run_s3_own(ctx, args.character_id, text)
    print(f"직접 쓴 안 정리(u1, G3 대기, gate-G3.html): {out}")
    return 0


def cmd_refs_index(args) -> int:
    from character_factory_poc.providers.embed import make_embedder
    from character_factory_poc.stages.s3r_refs.index import build_index, write_index

    catalog = json.loads(Path(args.stanford).read_text("utf-8")) if args.stanford else None
    jsonl = []
    for spec in args.jsonl or []:
        path, _, source = spec.partition(":")
        jsonl.append((Path(path), source or "OTHER"))
    index = build_index(
        args.index_id,
        stanford_catalog=catalog,
        personas_dir=Path(args.personas) if args.personas else None,
        jsonl=jsonl or None,
        embedder=make_embedder(args.embedder),
    )
    write_index(Path(args.out), index)
    print(f"색인 {index.indexId}: 항목 {len(index.items)}개 → {args.out} (Git 밖에 둔다)")
    return 0


def cmd_refs_select(args) -> int:
    from character_factory_poc.stages.s3r_refs import select as s3r

    return _run_stage(args, "s3r", s3r, "run_s3r", "참고 자료 선별")


def cmd_scene_backgrounds(args) -> int:
    from character_factory_poc.stages.s4a_backgrounds import run as s4a

    return _run_stage(args, "s4a", s4a, "run_s4a", "배경 후보(G4a 대기, gate-G4a.html)")


def cmd_scene_poses(args) -> int:
    from character_factory_poc.stages.s4b_poses import run as s4b

    return _run_stage(args, "s4b", s4b, "run_s4b", "장면 사실·자세 후보(G4b 대기, gate-G4b.html)")


def cmd_video_intro(args) -> int:
    from character_factory_poc.stages.s5_intro import run as s5

    ctx = Context.load(_root(args), execute=args.execute, max_calls=args.max_calls)
    if not args.execute:
        try:
            ctx.state(args.character_id).require_deps("s5")
        except FactoryError as e:
            print(f"아직 실행할 수 없다: {e}")
        print(format_plan(s5.plan_calls(ctx, s5.s5_config(ctx))))
        return 0
    out = s5.run_s5(ctx, args.character_id)
    print(f"소개 영상 후보: {out / 'videos.json'}\n검토 페이지: {out / 'gate-G5.html'} (G5 대기)")
    return 0


def cmd_video_web_setup(args) -> int:
    from character_factory_poc.providers.grok_web import DEFAULT_PROFILE, GrokWebVideoModel

    print("grok_web 어댑터 준비(D-0029, 기본 꺼짐):")
    print("1) 전용 프로필로 Chrome을 원격 디버깅 모드로 띄운다:")
    print("   " + GrokWebVideoModel.chrome_command(args.port, args.profile or DEFAULT_PROFILE))
    print("2) 그 창에서 grok.com에 한 번 로그인한다(프로필에 세션이 남는다).")
    print("3) factory.toml에 다음을 넣는다. xAI 이용 정책상 계정 정지 위험을 감수한다는 뜻이다:")
    print('   [providers.video]\n   adapter = "grok_web"\n   accept_terms_risk = true')
    print(f'   cdp_url = "http://127.0.0.1:{args.port}"')
    print("4) playwright를 설치한다: uv sync --extra web (브라우저 다운로드는 필요 없다)")
    return 0


def cmd_video_actions(args) -> int:
    from character_factory_poc.stages.s6_actions import run as s6

    ctx = Context.load(_root(args), execute=args.execute, max_calls=args.max_calls)
    if not args.execute:
        try:
            ctx.state(args.character_id).require_deps("s6")
        except FactoryError as e:
            print(f"아직 실행할 수 없다: {e}")
        print(format_plan(s6.plan_calls(ctx, s6.s6_config(ctx), args.character_id)))
        return 0
    out = s6.run_s6(ctx, args.character_id)
    print(f"동작 영상 후보: {out / 'clips.json'}\n검토 페이지: {out / 'gate-G5b.html'} (G5b 대기)")
    return 0


def cmd_plan_draft(args) -> int:
    from character_factory_poc.stages.s3_plan import draft as s3

    ctx = Context.load(_root(args), execute=args.execute, max_calls=args.max_calls)
    retries = int(ctx.config.stage("s3").get("max_check_retries", 3))
    if not args.execute:
        print(format_plan(s3.plan_calls(retries)))
        return 0
    cid = s3.new_character(ctx, args.slug)
    brief = Path(args.brief).read_text("utf-8")
    out = s3.run_s3_draft(ctx, cid, brief)
    print(f"기획서 초안: {out} (G3 대기)")
    return 0


def cmd_run(args) -> int:
    from character_factory_poc.pipeline.orchestrator import (
        RunOptions,
        run_until,
        validate_auto_approve,
        validate_until,
    )
    from character_factory_poc.stages.s3_plan.draft import new_character

    ctx = Context.load(_root(args), execute=args.execute, max_calls=args.max_calls)
    opt = RunOptions(
        until=args.until,
        auto_approve=set(args.auto_approve or []),
        brief_text=Path(args.brief).read_text("utf-8") if args.brief else None,
        voice_probes=_read_lines(args.probes),
        allow_same_family=args.allow_same_family,
        ranking=json.loads(Path(args.ranking).read_text("utf-8")) if args.ranking else None,
        seed=json.loads(Path(args.seed).read_text("utf-8")) if args.seed else None,
        training_providers=(
            [x.strip() for x in args.training_providers.split(",")]
            if args.training_providers
            else None
        ),
        verify_export=args.verify_export,
        submit_training=args.submit_training,
        max_parallel=(
            args.parallel
            if args.parallel is not None
            else int(ctx.config.orchestrator.get("max_parallel", 1))
        ),
    )
    validate_until(opt.until)
    validate_auto_approve(opt.auto_approve)
    if not args.execute:
        print("dry run: --execute가 있어야 단계를 실행한다. 계획:")
        auto = sorted(opt.auto_approve) or "없음"
        print(f"  대상 {args.character_id} → {args.until}까지, 자동 승인 {auto}")
        print(
            "  단계별 호출 계획은 cfp plan draft / persona traits / persona prompts 의 dry run 참조"
        )
        if opt.ranking is not None:
            print("  s1 순위 목록: --ranking 지정됨. 호출 계획은 cfp ref run의 dry run 참조")
        return 0
    cid = args.character_id
    if args.new_slug:
        cid = new_character(ctx, args.new_slug)
        print(f"새 캐릭터: {cid}")
    log = run_until(ctx, cid, opt)
    print(f"멈춘 곳: {log.stopped_at}")
    return 0


def cmd_ledger_report(args) -> int:
    ctx = Context.load(_root(args), execute=False)
    print(json.dumps(ctx.ledger(args.character_id).report(), ensure_ascii=False, indent=2))
    return 0


def _short_time(value: str | None) -> str:
    if not isinstance(value, str) or not value:
        return "-"
    return value[:16].replace("T", " ")


def cmd_report_hil(args) -> int:
    """사람 관문 보고서(hil-report-v1)를 표로 내고 reports/에 쓴다(LLD §5.21·§6.10)."""
    from character_factory_poc.pipeline.hil_report import write_hil_report

    ctx = Context.load(_root(args), execute=False)
    report, path = write_hil_report(ctx.character_dir(args.character_id))
    print(f"{report.subjectId} 사람 관문 보고서 (hil-report-v1) · {report.createdAt}")
    print(f"{'관문':<5}{'rev':<6}{'열림':<18}{'결정':<18}{'대기(분)':>9}{'검토(분)':>9}  결정")
    for gate in report.gates:
        if not gate.rounds:
            continue
        for round_ in gate.rounds:
            extra = " · 반복 상한" if gate.reworkCapReached else ""
            if gate.requestChangesCount:
                extra += f" · 수정 요청 {gate.requestChangesCount}회"
            wait = "-" if round_.waitMinutes is None else f"{round_.waitMinutes}"
            print(
                f"{gate.gate:<5}{round_.rev:<6}"
                f"{_short_time(round_.openedAt):<18}{_short_time(round_.decidedAt):<18}"
                f"{wait:>9}{round_.reviewMinutes:>9}  {round_.decision or '대기'}{extra}"
            )
    totals = report.totals
    rate = "-" if totals.followedReviewRate is None else f"{totals.followedReviewRate:.3f}"
    print(
        f"합계: 결정한 관문 {totals.gatesDecided} · 대기 {totals.waitMinutes}분 · "
        f"검토 {totals.reviewMinutes}분 · 수정 요청 {totals.requestChanges}회 · "
        f"추천 일치율 {rate}"
    )
    print(f"보고서: {path}")
    return 0


def cmd_verify(args) -> int:
    ctx = Context.load(_root(args), execute=False)
    base = ctx.character_dir(args.character_id)
    problems = []
    for m in sorted(base.rglob("manifest.sha256")):
        problems += [f"{m.parent.relative_to(base)}: {p}" for p in verify_manifest(m.parent)]
    if problems:
        print("\n".join(problems))
        return 1
    print("모든 manifest가 일치한다")
    return 0


# ---------------------------------------------------------------- S9~S11·내보내기 (LLD §4, D-0044)


def _ctx(args) -> Context:
    return Context.load(
        _root(args),
        execute=getattr(args, "execute", False),
        max_calls=getattr(args, "max_calls", None),
    )


def cmd_data(args) -> int:
    """S9: plan(계획 고정) · samples(인계안·샘플 → G7a) · build(대량·검사·분할 → G7)."""
    from character_factory_poc.stages import s9_data
    from character_factory_poc.stages.s9_data import build, plan, samples

    ctx = _ctx(args)
    cid = args.character_id
    stage = {"plan": "plan", "samples": "s9s", "build": "s9"}[args.sub]
    if args.sub == "plan":
        out = plan.run_plan(ctx, cid)
        print(f"데이터 계획: {out}")
        return 0
    if not args.execute:
        print(format_plan(s9_data.plan_calls(ctx, cid, stage)))
        return 0
    if args.sub == "samples":
        out = samples.run_samples(ctx, cid)
        print(f"샘플·인계안: {out} (G7a 대기, gate-G7a.html)")
    else:
        out = build.run_build(ctx, cid)
        print(f"데이터셋: {out} (G7 대기, gate-G7.html)")
    return 0


def cmd_train(args) -> int:
    """S10 학습: plan은 비용 추정만(dry run), submit·collect는 --execute가 있어야 부른다."""
    from character_factory_poc.stages.s10_train.collect import collect_s10t
    from character_factory_poc.stages.s10_train.plan import plan_s10t
    from character_factory_poc.stages.s10_train.submit import submit_s10t

    ctx = _ctx(args)
    providers = [p.strip() for p in args.providers.split(",")] if args.providers else None
    fn = {"plan": plan_s10t, "submit": submit_s10t, "collect": collect_s10t}[args.sub]
    if args.sub != "plan" and not args.execute:
        print(
            f"dry run: train {args.sub}는 유료 학습을 부른다. --execute와 사용자 지시가 있어야 한다"
        )
        return 0
    out = fn(ctx, args.character_id, providers)
    print(f"학습 {args.sub}: {out}")
    return 0


def cmd_eval(args) -> int:
    """S10 평가: prereg → run → judge → report(G8 대기)."""
    from character_factory_poc.stages.s10_eval import judge, prereg, report
    from character_factory_poc.stages.s10_eval import run as eval_run

    ctx = _ctx(args)
    cid = args.character_id
    if args.sub == "prereg":
        built = prereg.build_prereg(ctx, cid)
        print(f"사전 등록: {built.rev_dir} (sha256 {built.sha256[:12]}…)")
        return 0
    if not args.execute:
        pre, _, rev_dir = prereg.load_prereg(ctx, cid)
        if args.sub == "run":
            print(format_plan(eval_run.plan_calls(pre, ctx.character_dir(cid))))
        else:
            print(f"dry run: eval {args.sub}는 판정 모델을 부른다. --execute가 있어야 한다")
        return 0
    if args.sub == "run":
        out = eval_run.run_eval(ctx, cid)
    elif args.sub == "judge":
        out = judge.run_judge(ctx, cid)
    else:
        out = report.judge_and_report(ctx, cid)
    print(f"평가 {args.sub}: {out}")
    return 0


def cmd_release_build(args) -> int:
    from character_factory_poc.stages.s11_release.package import build_package

    out = build_package(_ctx(args), args.character_id)
    print(f"릴리즈 패키지: {out} (G9 대기, gate-G9.html)")
    return 0


def cmd_export_doki_app(args) -> int:
    from character_factory_poc.stages.export.export import export_doki_app

    result, rev_dir = export_doki_app(_ctx(args), args.character_id, verify=args.verify)
    print(f"내보내기: {rev_dir} · 적재 확인 {result.verification.status}")
    for step in result.verification.steps:
        print(f"  {'ok ' if step.ok else 'NG '} {step.name} {step.detail}")
    return 0 if result.verification.status != "FAILED" else 1


def cmd_web(args) -> int:
    from character_factory_poc.web.__main__ import main as web_main

    argv = ["--root", str(_root(args))]
    if args.port:
        argv += ["--port", str(args.port)]
    return web_main(argv)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cfp", description="character factory poc")
    p.add_argument("--root", default=".", help="프로젝트 루트(factory.toml, runs/)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status")
    s.add_argument("character_id")
    s.set_defaults(fn=cmd_status)

    plan = sub.add_parser("plan").add_subparsers(dest="sub", required=True)
    s = plan.add_parser("import", help="사용자가 쓴 기획서를 고정하고 G3 승인으로 기록한다(D-0013)")
    s.add_argument("slug")
    s.add_argument("--from", dest="source", required=True)
    s.add_argument("--brief", default=None)
    s.set_defaults(fn=cmd_plan_import)

    persona = sub.add_parser("persona").add_subparsers(dest="sub", required=True)
    s = persona.add_parser("traits", help="S7 상세 특질 시트")
    s.add_argument("character_id")
    s.add_argument("--execute", action="store_true")
    s.add_argument("--max-calls", type=int, default=None)
    s.add_argument("--references", default=None, help="참조 유형·프리셋 JSON [{kind,id,version}]")
    s.add_argument(
        "--reference-doc", action="append", default=None, help="참조 카드 본문 파일(반복 가능)"
    )
    s.set_defaults(fn=cmd_persona_traits)
    s = persona.add_parser("prompts", help="S8 긴·짧은 프롬프트와 말투 확인 표본, G6 페이지")
    s.add_argument("character_id")
    s.add_argument("--execute", action="store_true")
    s.add_argument("--max-calls", type=int, default=None)
    s.add_argument("--probes", default=None, help="말투 확인 문장 파일(한 줄에 하나)")
    s.add_argument("--allow-same-family", action="store_true")
    s.set_defaults(fn=cmd_persona_prompts)
    s = persona.add_parser("probe", help="고정된 프롬프트 쌍으로 말투 확인 표본만 다시 돌린다")
    s.add_argument("character_id")
    s.add_argument("--execute", action="store_true")
    s.add_argument("--max-calls", type=int, default=None)
    s.add_argument("--probes", required=True)
    s.add_argument("--allow-same-family", action="store_true")
    s.set_defaults(fn=cmd_persona_probe)

    gate = sub.add_parser("gate").add_subparsers(dest="sub", required=True)
    s = gate.add_parser("import")
    s.add_argument("character_id")
    s.add_argument("gate")
    s.add_argument("--answer", required=True)
    s.set_defaults(fn=cmd_gate_import)

    s = sub.add_parser("check", help="작업 공간의 output.json을 단계 검사로 확인한다(에이전트용)")
    s.add_argument("stage")
    s.add_argument("workspace")
    s.set_defaults(fn=cmd_check)

    ref = sub.add_parser("ref").add_subparsers(dest="sub", required=True)
    s = ref.add_parser(
        "run", help="S1: 화제성 순위 → 외모 특징 → 외모군·미리보기 → G1 대기(D-0017)"
    )
    s.add_argument("character_id", help="기존 character_id, 또는 --new-slug와 함께 임의 값")
    s.add_argument("--ranking", required=True, help="popularity-ranking-v2 JSON")
    s.add_argument("--new-slug", default=None, help="새 캐릭터를 만들어 시작한다")
    s.add_argument("--execute", action="store_true")
    s.add_argument("--max-calls", type=int, default=None)
    s.set_defaults(fn=cmd_ref_run)
    s = ref.add_parser(
        "faces",
        help="G1 REQUEST_CHANGES 메모로 얼굴 미리보기만 새 rf로 다시 만든다(D-0043)",
    )
    s.add_argument("character_id")
    s.add_argument("--execute", action="store_true")
    s.add_argument("--max-calls", type=int, default=None)
    s.set_defaults(fn=cmd_ref_faces)
    s = ref.add_parser(
        "collect",
        help="S1 화제성 순위 자동 수집(D-0044 (4)). 기본은 호출 계획만, --execute로 수집",
    )
    s.add_argument("--character-gender", required=True, choices=["female", "male", "any"])
    s.add_argument("--age-range", default="20s")
    s.add_argument("--art-style", default="photoreal")
    s.add_argument("--origin", default="korean", choices=["korean", "east-asian", "unspecified"])
    s.add_argument("--categories", default=None, help="쉼표 목록. 없으면 설정·기본값")
    s.add_argument("--out", default=None, help="기본 runs/rankings/<시각>-<출처>/")
    s.add_argument("--execute", action="store_true")
    s.set_defaults(fn=cmd_ref_collect)

    hero = sub.add_parser("hero").add_subparsers(dest="sub", required=True)
    s = hero.add_parser(
        "run",
        help=(
            "S2: G1에서 고른 얼굴 → 기준 이미지·외모 명세 자동 고정"
            '(관문 없음, D-0042. [stages.s2] base_photo = "picked")'
        ),
    )
    s.add_argument("character_id")
    s.add_argument("--execute", action="store_true")
    s.add_argument("--max-calls", type=int, default=None)
    s.set_defaults(fn=cmd_hero_run)

    frames = sub.add_parser("frames").add_subparsers(dest="sub", required=True)
    s = frames.add_parser(
        "run", help="S4: 기준 얼굴 + 배경 사진 + 자세 → 챕터 완성 이미지 → G4 대기(D-0033)"
    )
    s.add_argument("character_id")
    s.add_argument("--execute", action="store_true")
    s.add_argument("--max-calls", type=int, default=None)
    s.set_defaults(fn=cmd_frames_run)

    video = sub.add_parser("video").add_subparsers(dest="sub", required=True)
    s = video.add_parser(
        "intro", help="S5: S2 기준 이미지 → 소개 영상 후보 → G5 사람 선택(D-0028, D-0042)"
    )
    s.add_argument("character_id")
    s.add_argument("--execute", action="store_true")
    s.add_argument("--max-calls", type=int, default=None)
    s.set_defaults(fn=cmd_video_intro)
    s = video.add_parser(
        "actions", help="S6: G4 승인 이미지 → 챕터별 동작 영상 후보 → G5b 사람 선택(D-0038)"
    )
    s.add_argument("character_id")
    s.add_argument("--execute", action="store_true")
    s.add_argument("--max-calls", type=int, default=None)
    s.set_defaults(fn=cmd_video_actions)
    s = video.add_parser("web-setup", help="grok_web 어댑터용 전용 Chrome 프로필 안내(D-0029)")
    s.add_argument("--port", type=int, default=9222)
    s.add_argument("--profile", default=None)
    s.set_defaults(fn=cmd_video_web_setup)

    s = plan.add_parser("seed", help="S2 뒤 기획 씨앗을 고정한다(D-0033, D-0042)")
    s.add_argument("character_id")
    s.add_argument(
        "--file", default=None, help="씨앗 JSON(personality, job, age, gender, background)"
    )
    s.add_argument("--personality", default=None, help="대표 성격(필수, 파일에 없으면)")
    s.add_argument("--job", default=None)
    s.add_argument("--age", type=int, default=None)
    s.add_argument("--gender", default=None, choices=["female", "male", "other"])
    s.add_argument("--background", default=None)
    s.add_argument("--notes", default=None)
    s.set_defaults(fn=cmd_plan_seed)
    s = plan.add_parser("variants", help="S3: 씨앗 → 상세 변형 3안 → G3 대기(D-0033)")
    s.add_argument("character_id")
    s.add_argument("--execute", action="store_true")
    s.add_argument("--max-calls", type=int, default=None)
    s.set_defaults(fn=cmd_plan_variants)
    s = plan.add_parser("own", help="직접 쓴 상세안을 기획서 형식(u1)으로 정리 → G3 대기")
    s.add_argument("character_id")
    s.add_argument("--file", required=True)
    s.add_argument("--execute", action="store_true")
    s.add_argument("--max-calls", type=int, default=None)
    s.set_defaults(fn=cmd_plan_own)

    refs = sub.add_parser("refs").add_subparsers(dest="sub", required=True)
    s = refs.add_parser("index", help="참고 자료 색인을 만든다(D-0035, Git 밖에 둔다)")
    s.add_argument("--out", required=True)
    s.add_argument("--index-id", default="refs-v1")
    s.add_argument("--embedder", default="hash-v1")
    s.add_argument("--stanford", default=None, help="Stanford 프리셋 카탈로그 JSON")
    s.add_argument("--personas", default=None, help="chat-svc 페르소나 v6 JSON 폴더")
    s.add_argument("--jsonl", action="append", default=None, help="경로:출처(SNS14|NIKL|OTHER)")
    s.set_defaults(fn=cmd_refs_index)
    s = refs.add_parser("select", help="S3r: 기획서로 참고 자료를 고른다(관문 없음)")
    s.add_argument("character_id")
    s.add_argument("--execute", action="store_true")
    s.add_argument("--max-calls", type=int, default=None)
    s.set_defaults(fn=cmd_refs_select)

    scene = sub.add_parser("scene").add_subparsers(dest="sub", required=True)
    s = scene.add_parser("backgrounds", help="S4a: 챕터별 배경 후보·배경 사진 → G4a 대기")
    s.add_argument("character_id")
    s.add_argument("--execute", action="store_true")
    s.add_argument("--max-calls", type=int, default=None)
    s.set_defaults(fn=cmd_scene_backgrounds)
    s = scene.add_parser("poses", help="S4b: 챕터 사실 작성과 자세 후보 → G4b 대기")
    s.add_argument("character_id")
    s.add_argument("--execute", action="store_true")
    s.add_argument("--max-calls", type=int, default=None)
    s.set_defaults(fn=cmd_scene_poses)

    s = plan.add_parser("draft", help="Planner가 브리프와 프리셋 카탈로그로 기획서를 쓴다(G3 대기)")
    s.add_argument("slug")
    s.add_argument("--brief", required=True)
    s.add_argument("--execute", action="store_true")
    s.add_argument("--max-calls", type=int, default=None)
    s.set_defaults(fn=cmd_plan_draft)

    s = sub.add_parser("run", help="그래프를 따라 관문까지 자동 진행한다")
    s.add_argument("character_id", help="기존 character_id, 또는 --new-slug와 함께 임의 값")
    s.add_argument("--new-slug", default=None, help="새 캐릭터를 만들어 시작한다")
    s.add_argument("--until", default="G6")
    s.add_argument(
        "--auto-approve",
        action="append",
        default=None,
        help="실험용. 지정한 관문을 자동 승인한다(기록에 reviewer=auto로 남는다)",
    )
    s.add_argument("--brief", default=None)
    s.add_argument("--probes", default=None)
    s.add_argument("--ranking", default=None, help="popularity-ranking-v2 JSON. 있으면 s1부터 돈다")
    s.add_argument(
        "--seed", default=None, help="기획 씨앗 JSON(D-0033). 저장된 씨앗이 없을 때만 쓴다"
    )
    s.add_argument("--allow-same-family", action="store_true")
    s.add_argument("--training-providers", default=None, help="s10t 학습 공급자 쉼표 목록")
    s.add_argument(
        "--parallel",
        type=int,
        default=None,
        help="동시에 돌릴 단계 수(D-0049). 기본은 [orchestrator] max_parallel, 없으면 1",
    )
    s.add_argument(
        "--submit-training",
        action="store_true",
        help="s10t에서 학습을 제출·회수한다(유료). 없으면 학습 계획(dry run)만 쓴다",
    )
    s.add_argument(
        "--verify-export", action="store_true", help="sx에서 일회용 DB 적재 확인까지 한다"
    )
    s.add_argument("--execute", action="store_true")
    s.add_argument("--max-calls", type=int, default=None)
    s.set_defaults(fn=cmd_run)

    data = sub.add_parser("data", help="S9 학습 데이터셋(D-0044)").add_subparsers(
        dest="sub", required=True
    )
    for name, help_text in (
        ("plan", "G6 승인 프롬프트로 data-plan-v1을 고정한다"),
        ("samples", "클러스터별 인계안·샘플 → G7a 대기(--execute)"),
        ("build", "G7a 승인 뒤 대량 작성·검사·분할 → G7 대기(--execute)"),
    ):
        s = data.add_parser(name, help=help_text)
        s.add_argument("character_id")
        s.add_argument("--execute", action="store_true")
        s.add_argument("--max-calls", type=int, default=None)
        s.set_defaults(fn=cmd_data)

    train = sub.add_parser("train", help="S10 학습(Gemma QLoRA·Vertex Gemini)").add_subparsers(
        dest="sub", required=True
    )
    for name, help_text in (
        ("plan", "학습 계획과 비용 추정(dry run, 호출 없음)"),
        ("submit", "학습 제출(--execute, 유료)"),
        ("collect", "학습 결과 회수(--execute)"),
    ):
        s = train.add_parser(name, help=help_text)
        s.add_argument("character_id")
        s.add_argument("--providers", default=None, help="쉼표 목록. 없으면 [stages.s10t]")
        s.add_argument("--execute", action="store_true")
        s.set_defaults(fn=cmd_train)

    ev = sub.add_parser("eval", help="S10 평가와 G8").add_subparsers(dest="sub", required=True)
    for name, help_text in (
        ("prereg", "평가 세트·조건·기준을 고정한다(학습 결과가 있어야 한다)"),
        ("run", "조건별 응답 수집(--execute)"),
        ("judge", "정순·역순 짝 판정(--execute)"),
        ("report", "지표·보고서 → G8 대기(--execute)"),
    ):
        s = ev.add_parser(name, help=help_text)
        s.add_argument("character_id")
        s.add_argument("--execute", action="store_true")
        s.add_argument("--max-calls", type=int, default=None)
        s.set_defaults(fn=cmd_eval)

    release = sub.add_parser("release").add_subparsers(dest="sub", required=True)
    s = release.add_parser("build", help="S11 릴리즈 패키지 → G9 대기")
    s.add_argument("character_id")
    s.set_defaults(fn=cmd_release_build)

    export = sub.add_parser("export").add_subparsers(dest="sub", required=True)
    s = export.add_parser("doki-app", help="G9 승인 패키지 → api-svc 시드·chat-svc 트리")
    s.add_argument("character_id")
    s.add_argument(
        "--verify",
        action="store_true",
        help="일회용 PostgreSQL에 실제 적재해 확인(CFP_PG_ADMIN_URL)",
    )
    s.set_defaults(fn=cmd_export_doki_app)

    s = sub.add_parser("web", help="워크숍 웹앱(LLD §6.5)")
    s.add_argument("--port", type=int, default=None)
    s.set_defaults(fn=cmd_web)

    ledger = sub.add_parser("ledger").add_subparsers(dest="sub", required=True)
    s = ledger.add_parser("report")
    s.add_argument("character_id")
    s.set_defaults(fn=cmd_ledger_report)

    report = sub.add_parser("report", help="사람 시간 보고서").add_subparsers(
        dest="sub", required=True
    )
    s = report.add_parser("hil", help="사람 관문 보고서 hil-report-v1을 쓰고 표로 낸다")
    s.add_argument("character_id")
    s.set_defaults(fn=cmd_report_hil)

    s = sub.add_parser("verify")
    s.add_argument("character_id")
    s.set_defaults(fn=cmd_verify)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except FactoryError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1
