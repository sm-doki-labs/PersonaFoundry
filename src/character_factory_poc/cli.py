"""cfp 명령 (LLD §4). 기본은 dry run이다."""

from __future__ import annotations

import argparse
import json
import os
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


def cmd_models(args) -> int:
    from character_factory_poc.common.text_deck import deck, select

    try:
        ctx = Context.load(_root(args), execute=False)
        if args.models_action == "select":
            if args.profile is None and args.route is None:
                raise ValueError("--profile 또는 --route가 필요하다")
            select(ctx.config, profile=args.profile, route=args.route)
            ctx = Context.load(_root(args), execute=False)
        if not ctx.text_deck_enabled:
            print("텍스트 모델 덱 꺼짐: 기존 providers.text/judge를 사용한다.")
            return 0
        print(
            json.dumps(
                {
                    "enabled": True,
                    "bindings": [ctx.config.text_binding(s["id"]) for s in deck()["stages"]],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except (ValueError, OSError) as exc:
        raise FactoryError(str(exc)) from exc


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
    from character_factory_poc.common.errors import NeedsInputError
    from character_factory_poc.stages.s3_plan.importer import import_plan, plan_version
    from character_factory_poc.stages.s3_plan.own import plan_calls as own_calls

    ctx = Context.load(_root(args), execute=args.execute, max_calls=args.max_calls)
    try:
        out = import_plan(ctx, args.slug, Path(args.source), args.brief)
    except NeedsInputError as e:
        raw = json.loads(Path(args.source).read_text("utf-8"))
        if plan_version(raw) == "character-plan-v1":
            print(f"{e}\n{format_plan(own_calls(ctx))}")
            return 0
        raise
    if out["mode"] == "approved":
        print(f"기획서 고정: {out['characterId']} {out['planRev']} (G3 승인 기록: manual-plan)")
    else:
        print(
            f"구형 기획서를 신형 후보로 올렸다: {out['characterId']} {out['planRev']} "
            f"(G3 대기, {out['path'] / 'gate-G3.html'})"
        )
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
        if ctx.config.stage("s7").get("formation_profile"):
            from character_factory_poc.stages.s7_traits.formation import (
                format_retries,
                plan_calls,
            )

            if ctx.config.stage("s7").get("formation_profile") == "ko-text-choice-voice-long-v2":
                from character_factory_poc.common.budget import CallPlan

                print(
                    format_plan(
                        [
                            CallPlan(
                                "s7-choice-voice", "설계·뼈대·말투·보존 검토(형식 재시도 포함)", 12
                            )
                        ]
                    )
                )
            else:
                print(format_plan(plan_calls(format_retries(ctx))))
        else:
            print(format_plan(s7.plan_calls(retries, deck_enabled=ctx.text_deck_enabled)))
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
        from character_factory_poc.pipeline.origin import is_twin

        if is_twin(ctx.character_dir(args.character_id)):
            from character_factory_poc.stages.s8_prompts.evidence_pipeline import (
                configured_compiler,
            )

            compiler, _ = configured_compiler(ctx, args.character_id)
            if compiler in {
                "evidence-v2",
                "evidence-v3",
                "evidence-v4",
                "evidence-v5",
                "evidence-v6",
                "evidence-v7",
                "evidence-v8",
                "evidence-v9",
                "evidence-v10",
            }:
                from character_factory_poc.stages.s8_prompts.evidence_pipeline import full_plan

                print(format_plan(full_plan(ctx, args.character_id, len(probes))))
                return 0
            print(
                format_plan(
                    s8.motif_plan_calls(
                        len(probes),
                        ctx.config.stage("s8").get("scene_traits", False),
                        ctx.config.stage("s8").get("trait_method", "focus"),
                        compiler,
                    )
                )
            )
        elif ctx.text_deck_enabled or ctx.config.stage("s7").get("formation_profile"):
            print("고정 컴파일: 모델 호출0회. 품질 검증은 persona qualify에서 별도로 실행한다.")
        else:
            print(format_plan(s8.plan_calls(retries, len(probes))))
        return 0
    out = s8.run_s8(ctx, args.character_id, probes, args.allow_same_family)
    print(f"프롬프트 쌍: {out}\n검토 페이지: {out / 'gate-G6.html'}")
    return 0


def cmd_persona_traitcheck(args) -> int:
    from character_factory_poc.stages.s8_prompts import trait_check as tc

    ctx = Context.load(_root(args), execute=args.execute, max_calls=args.max_calls)
    if not args.execute:
        print(format_plan(tc.plan_calls(samples=args.samples)))
        return 0
    out = tc.run_trait_check(
        ctx,
        args.character_id,
        prompt_path=args.prompt,
        ledger_path=args.ledger,
        items_path=args.items,
        out_dir=args.out,
        samples=args.samples,
        rejudge=args.rejudge,
    )
    m = json.loads(Path(out).read_text("utf-8"))["metrics"]
    print(f"특질 시험: {out}")
    print(json.dumps({k: v for k, v in m.items() if k != "traits"}, ensure_ascii=False))
    return 0


def cmd_persona_chapters(args) -> int:
    from character_factory_poc.stages.s8_prompts import chapter_start as s8c

    ctx = Context.load(_root(args), execute=args.execute, max_calls=args.max_calls)
    if not args.execute:
        print(format_plan(s8c.plan_calls()))
        return 0
    out = s8c.run_chapter_start(ctx, args.character_id)
    print(f"챕터 시작 설정: {out}")
    return 0


def cmd_persona_qualify(args) -> int:
    from character_factory_poc.stages.persona_quality.protocol import load_cohort
    from character_factory_poc.stages.persona_quality.report import report_qualification
    from character_factory_poc.stages.persona_quality.run import (
        plan_qualification,
        run_qualification,
    )

    if args.quality_action == "report":
        result = report_qualification(
            Path(args.run), Path(args.human_reviews) if args.human_reviews else None
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    cohort = load_cohort(Path(args.cohort))
    plan = plan_qualification(cohort)
    if args.quality_action == "plan" or not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    from character_factory_poc.providers.factory import make_text_model
    from character_factory_poc.stages.persona_quality.tokenizer import RemoteTokenCounter

    ctx = Context.load(_root(args), execute=True, max_calls=args.max_calls)
    cfg = ctx.config.providers.get("dialogue")
    if cfg is None:
        raise FactoryError("providers.dialogue must bind the frozen service model")
    model = make_text_model(cfg)
    if hasattr(model, "max_retries"):
        model.max_retries = 0
    if not args.tokenizer_url:
        raise FactoryError("--tokenizer-url must identify an exact tokenizer for the bound model")
    counter = RemoteTokenCounter(args.tokenizer_url, cfg.model)
    folder = Path(args.output) if args.output else ctx.config.runs_dir / "quality" / cohort.id
    print(json.dumps(plan, ensure_ascii=False))
    out = run_qualification(ctx, cohort, folder, dialogue_model=model, token_counter=counter)
    print(f"품질 원문: {out}")
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


def cmd_review(args) -> int:
    from character_factory_poc.pipeline.review import plan_review_calls, review_gate

    ctx = Context.load(_root(args), execute=args.execute)
    if not args.execute:
        print(format_plan(plan_review_calls(ctx, args.character_id, args.gate)))
        return 0
    out = review_gate(ctx, args.character_id, args.gate)
    if out is None:
        print(f"{args.gate} 검토 기록 없음")
        return 0
    print(f"{args.gate} 사전 검토: {out}")
    return 0


def cmd_ref_run(args) -> int:
    from character_factory_poc.stages.s1_reference import run as s1
    from character_factory_poc.stages.s3_plan.common import new_character

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
    options = {"trait_ids": args.trait}
    if getattr(args, "expected_seed_rev", None) is not None:
        options["expected_seed_rev"] = args.expected_seed_rev
    seed = write_seed(ctx, args.character_id, fields, **options)
    print(f"기획 씨앗 고정: {seed.seedRev} (다음: cfp plan variants {args.character_id})")
    return 0


def cmd_plan_suggest(args) -> int:
    from character_factory_poc.stages.s3_plan.trait_recommendations import recommend_traits

    result = recommend_traits(args.personality, selected_ids=args.trait, search=args.search)
    print(json.dumps(result, ensure_ascii=False, indent=2))
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
    """D-0080: 브리프를 씨앗으로 옮겨 변형 3안을 만든다(구형 Planner 초안을 대체)."""
    from character_factory_poc.stages.s3_plan.common import new_character
    from character_factory_poc.stages.s3_plan.variants import plan_calls, run_s3_from_brief

    ctx = Context.load(_root(args), execute=args.execute, max_calls=args.max_calls)
    if not args.execute:
        print(format_plan(plan_calls(ctx)))
        return 0
    cid = new_character(ctx, args.slug)
    brief = Path(args.brief).read_text("utf-8")
    out = run_s3_from_brief(ctx, cid, brief)
    print(f"기획 변형: {out} (G3 대기, {out / 'gate-G3.html'})")
    return 0


def cmd_batch_run(args) -> int:
    from character_factory_poc.pipeline.batch import run_batch

    ctx = Context.load(_root(args), execute=args.execute)
    try:
        report = run_batch(ctx, Path(args.spec))
    except (ValueError, OSError) as exc:
        print(f"배치 입력 오류: {exc}", file=sys.stderr)
        return 1
    if report.batchId is None:
        print("dry run: --execute가 있어야 실행한다")
    print(report.table())
    if report.batchId:
        print(ctx.config.runs_dir / "batches" / report.batchId / "batch-report.json")
    return int(any(row.status == "failed" for row in report.characters))


def cmd_run(args) -> int:
    from character_factory_poc.pipeline.orchestrator import (
        RunOptions,
        run_until,
        validate_auto_approve,
        validate_until,
    )
    from character_factory_poc.stages.s3_plan.common import new_character

    root = _root(args)
    if os.getenv("CFP_SERVER_MODE") == "1":
        if getattr(args, "source_pack", None):
            raise SystemExit("서버에서는 --source-pack 대신 출처 화면을 사용한다")
        server_root = Path(os.getenv("CFP_ROOT") or root).resolve()
        if args.root == ".":
            root = server_root
        paths = [root, root / "runs" / "characters" / args.character_id]
        paths.extend(Path(v) for v in (args.brief, args.probes, args.ranking, args.seed) if v)
        if any(not path.resolve().is_relative_to(server_root) for path in paths):
            raise SystemExit("서버에서는 공장 루트 밖 경로를 사용할 수 없다")
    ctx = Context.load(root, execute=args.execute, max_calls=args.max_calls)
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
        source_pack=Path(args.source_pack) if getattr(args, "source_pack", None) else None,
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
    from character_factory_poc.pipeline.origin import (
        CLI_NAMES,
        origin_label,
        read_origin,
        write_origin,
    )

    origin_arg = getattr(args, "origin", None)
    if args.new_slug:
        cid = new_character(ctx, args.new_slug)
        origin = CLI_NAMES[origin_arg or "original"]
        write_origin(ctx.character_dir(cid), origin)
        print(f"새 캐릭터: {cid} ({origin_label(origin)})")
        mode_arg = getattr(args, "model_mode", None)
        if mode_arg:
            from character_factory_poc.pipeline.origin import MODE_CLI_NAMES, write_model_mode

            write_model_mode(ctx.character_dir(cid), MODE_CLI_NAMES[mode_arg], reason="cfp run")
            print(f"모델 준비 방식: {MODE_CLI_NAMES[mode_arg]}")
    elif origin_arg and read_origin(ctx.character_dir(cid)) != CLI_NAMES[origin_arg]:
        raise SystemExit("출신은 새 캐릭터를 만들 때만 정한다(--new-slug와 함께)")
    log = run_until(ctx, cid, opt)
    print(f"멈춘 곳: {log.stopped_at}")
    return 0


def cmd_model(args) -> int:
    """모델 준비 방식(D-0118). mode: 방식 정하기, bind: 이미 학습된 모델 연결 기록 들여오기."""
    from character_factory_poc.pipeline.origin import (
        MODE_CLI_NAMES,
        read_model_mode,
        write_model_mode,
    )

    ctx = Context.load(_root(args), execute=getattr(args, "execute", False))
    char_dir = ctx.character_dir(args.character_id)
    if not char_dir.exists():
        raise SystemExit(f"캐릭터가 없다: {args.character_id}")
    if args.model_action == "mode":
        if args.mode is None:
            print(read_model_mode(char_dir))
            return 0
        if ctx.state(args.character_id).stage("s10").status == "APPROVED":
            raise SystemExit("평가(G8)가 이미 승인돼 방식을 바꿀 수 없다. 새 판으로 다시 돈다")
        write_model_mode(char_dir, MODE_CLI_NAMES[args.mode], reason=args.reason or "")
        print(f"{args.character_id}: {read_model_mode(char_dir)}")
        return 0
    from character_factory_poc.stages.model_prep.bind import import_binding

    out = import_binding(ctx, args.character_id, Path(args.binding))
    print(f"모델 연결 기록: {out}")
    return 0


def cmd_ledger_report(args) -> int:
    from character_factory_poc.common import cost_report

    ctx = Context.load(_root(args), execute=False)
    ledger = ctx.ledger(args.character_id)
    out = ledger.report()
    out["cost"] = cost_report.build(ledger.calls())
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_ledger_cost(args) -> int:
    """원장으로 cost-report-v1을 만든다(FR-69). 재계산도 원래 원장을 고치지 않는다."""
    from character_factory_poc.common import cost_report

    ctx = Context.load(_root(args), execute=False)
    source = Path(args.target)
    if source.suffix == ".jsonl" or source.is_file():
        if not source.is_file():
            print(f"오류: 원장 파일이 없다: {source}", file=sys.stderr)
            return 1
        ledger_dir = source.resolve().parent
        rows = [json.loads(ln) for ln in source.read_text("utf-8").splitlines() if ln.strip()]
    else:
        ledger = ctx.ledger(args.target)
        if not ledger.calls_path.exists():
            print(f"오류: 원장이 없다: {ledger.calls_path}", file=sys.stderr)
            return 1
        ledger_dir = ledger.folder.resolve()
        rows = ledger.calls()
    report = cost_report.build(
        rows, recompute=args.recompute, overrides=ctx.price_overrides() if args.recompute else None
    )
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        out = Path(args.out)
        if not out.is_absolute():
            out = _root(args) / out
        if out.resolve().is_relative_to(ledger_dir):
            print("오류: 보고서는 원장 폴더 밖(runs/·work/ 아래)에 쓴다", file=sys.stderr)
            return 1
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
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
    from character_factory_poc.stages.s10_train.drive import cleanup_s10t, drive_s10t
    from character_factory_poc.stages.s10_train.plan import plan_s10t
    from character_factory_poc.stages.s10_train.submit import submit_s10t

    ctx = _ctx(args)
    providers = [p.strip() for p in args.providers.split(",")] if args.providers else None
    fn = {
        "plan": plan_s10t,
        "submit": submit_s10t,
        "collect": collect_s10t,
        "drive": drive_s10t,
    }.get(args.sub)
    if args.sub != "plan" and not args.execute:
        print(
            f"dry run: train {args.sub}는 유료 학습을 부른다. --execute와 사용자 지시가 있어야 한다"
        )
        return 0
    if args.sub == "cleanup":
        removed = cleanup_s10t(ctx, args.character_id, providers)
        print("임대 GPU 삭제: " + (", ".join(removed) if removed else "남은 GPU 없음"))
        return 0
    if args.sub == "guard":
        from character_factory_poc.stages.s10_train.guard import run_guard

        if not args.plan_dir:
            print("오류: train guard는 --plan-dir(학습 공급자 폴더)이 있어야 한다", file=sys.stderr)
            return 1
        adapter = providers[0] if providers else "gemma_qlora"
        result = run_guard(_root(args), args.character_id, adapter, Path(args.plan_dir))
        print(f"guard 종료: {result}")
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
    if args.sub == "import-blind":
        # 순서 8: 가족이 블라인드 화면에서 저장한 답 파일을 열린 모티브 G8에 들여온다(호출 없음).
        from character_factory_poc.stages.s10_eval.blind import import_blind_answers

        out = import_blind_answers(ctx, cid, Path(args.answers))
        print(f"가족 판정 들여옴: {out}")
        return 0
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


def _grok_login(args):
    from character_factory_poc.providers.xai_login import XaiLogin

    extra = _ctx(args).config.provider("video").extra
    return XaiLogin(
        store=extra.get("login_file") or None, client_id=str(extra.get("oauth_client_id") or "")
    )


def cmd_grok(args) -> int:
    """공장 소유 Grok 로그인(D-0184). 영상 1순위 경로의 토큰을 받고 보관·갱신한다."""
    from character_factory_poc.common.errors import VideoGenerationError

    login = _grok_login(args)
    try:
        if args.sub == "login":
            if args.device:
                cred = login.login_device(
                    on_prompt=lambda url, code: print(
                        f"다른 기기 브라우저에서 {url} 을 열고 코드 {code} 를 입력하세요."
                    )
                )
            else:
                cred = login.login_browser(
                    open_browser=not args.no_browser,
                    on_url=lambda url: print(
                        "브라우저에서 xAI 로그인을 마쳐 주세요. 창이 안 열리면 이 주소를 여세요:\n"
                        + url
                    ),
                )
            print(f"로그인됐어요: {cred.email or '이메일 없음'} · {login.store}")
        elif args.sub == "status":
            st = login.status()
            if not st["loggedIn"]:
                print(f"로그인 안 됨 · {st['store']} · cfp grok login")
                return 1
            who = st["email"] or "이메일 없음"
            print(f"로그인됨: {who} · 토큰 {st['expiresInMin']}분 남음(쓸 때 자동 갱신)")
            print(f"  저장 위치: {st['store']}")
            if args.refresh:
                login.access_token(min_valid_s=10**9)
                print(f"갱신했어요: 토큰 {login.status()['expiresInMin']}분 남음")
        elif args.sub == "logout":
            print("로그아웃했어요." if login.logout() else "로그인 기록이 없어요.")
    except VideoGenerationError as exc:
        print(f"실패: {exc}")
        return 1
    return 0


def cmd_preview_publish(args) -> int:
    """G9 승인 패키지를 테스터 전용으로 앱에 올린다([publish.preview] 설정)."""
    from character_factory_poc.common.notify import notify
    from character_factory_poc.stages.export.preview import publish_preview

    result = publish_preview(_ctx(args), args.character_id)
    for step in result.steps:
        print(f"  {'ok ' if step.ok else 'NG '} {step.name} {step.detail}")
    for warning in result.warnings:
        print(f"  참고: {warning}")
    if args.notify:
        if result.status == "PUBLISHED":
            lines = [
                "테스터 계정의 앱 목록에서 볼 수 있어요. 일반 사용자에게는 보이지 않아요.",
                f"앱 캐릭터 번호 {result.apiCharacterId} · 대상 {result.target}",
            ]
            notify(
                "published", result.name or args.character_id, lines, character_id=args.character_id
            )
        else:
            notify(
                "failed",
                result.name or args.character_id,
                [f"발행에서 멈췄어요: {result.failure[:400]}"],
                character_id=args.character_id,
            )
    print(
        f"테스터 전용 발행: {result.status}"
        + (f" · 앱 캐릭터 {result.apiCharacterId}" if result.apiCharacterId else "")
    )
    return 0 if result.status == "PUBLISHED" else 1


def cmd_preview_remove(args) -> int:
    """마지막으로 발행한 테스터 전용 캐릭터를 dev 에서 지운다(넣기 서비스 DELETE)."""
    from character_factory_poc.stages.export.preview import remove_preview

    result = remove_preview(_ctx(args), args.character_id)
    for step in result.steps:
        print(f"  {'ok ' if step.ok else 'NG '} {step.name} {step.detail}")
    for warning in result.warnings:
        print(f"  참고: {warning}")
    print(f"테스터 전용 지우기: {result.status}")
    return 0 if result.status == "REMOVED" else 1


def cmd_demo_mode(args) -> int:
    from character_factory_poc.pipeline.demo import write_demo_mode

    folder = _ctx(args).character_dir(args.character_id)
    if not folder.is_dir():
        print(f"캐릭터가 없다: {args.character_id}")
        return 1
    mode = write_demo_mode(folder, enabled=args.state == "on", budget_usd=args.budget)
    print(
        f"시연 모드: {'켬' if mode.enabled else '끔'}"
        + (f" · 예산 상한 ${mode.budgetUsd:.2f}" if mode.enabled else "")
    )
    return 0


def cmd_web(args) -> int:
    from character_factory_poc.web.__main__ import main as web_main

    argv = ["--root", str(_root(args))]
    if args.port:
        argv += ["--port", str(args.port)]
    return web_main(argv)


def build_parser() -> argparse.ArgumentParser:
    return _build_parser()


def cmd_testpath_seeds(args) -> int:
    """시험 경로 2번. --execute 없이는 무엇을 부를지만 출력한다."""
    from character_factory_poc.common.api_routes import FAMILY_DEFAULTS
    from character_factory_poc.common.config import load_env_file
    from character_factory_poc.providers.openai_compat import OpenAICompatTextModel
    from character_factory_poc.testpath import seeds as sd
    from character_factory_poc.testpath.image_api import OpenAIImagesClient

    root = _root(args)
    load_env_file(root / ".env")
    run_dir = Path(args.run)
    if not run_dir.is_absolute():
        run_dir = root / run_dir
    cfg = sd.SeedRunConfig(
        run_dir=run_dir,
        total=args.total,
        image_quality=args.quality,
        look=args.look,
        signatures=not args.no_signatures,
    )
    if args.gemini_route == "relay":
        cfg.tag_models["gemini"] = ("relay", "google-antigravity/gemini-4-argon")
    order = sd.STEPS[: sd.STEPS.index(args.until) + 1]
    if not args.execute:
        print("dry run. 실행할 단계:", ", ".join(order))
        print("태깅 모델:", ", ".join(f"{k}={m}" for k, (_, m) in cfg.tag_models.items()))
        print(f"이미지: gpt-image-2.6-sunburst {cfg.image_size} {cfg.image_quality} × {cfg.total}")
        return 0
    routes = {**FAMILY_DEFAULTS, "relay": sd.RELAY}
    models = {
        key: OpenAICompatTextModel(
            base_url=routes[family]["base_url"],
            model=model,
            api_key_env=routes[family]["api_key_env"],
            timeout=600,
            max_retries=2,
            stream=family != "relay",
        )
        for key, (family, model) in cfg.tag_models.items()
    }
    if "people" in order:
        sd.step_people(cfg)
    if "tags" in order:
        sd.step_tags(cfg, models)
    if "clusters" in order:
        sd.step_clusters(cfg)
    if "prompts" in order:
        sd.step_prompts(cfg)
    if "images" in order:
        sd.step_images(cfg, OpenAIImagesClient())
        sd.contact_sheet(cfg)
    print(json.dumps(sd.summary(cfg), ensure_ascii=False, indent=2))
    return 0


def _testpath_run(args) -> Path:
    from character_factory_poc.common.config import load_env_file

    root = _root(args)
    load_env_file(root / ".env")
    run_dir = Path(args.run)
    return run_dir if run_dir.is_absolute() else root / run_dir


def _seed_entry(run_dir: Path, seed: str) -> dict:
    plan = json.loads((run_dir / "seeds" / "plan.json").read_text("utf-8"))
    return next(s for s in plan["seeds"] if s["seedId"] == seed)


def _signature_en(tags: dict) -> str | None:
    from character_factory_poc.testpath.vocab2 import load_vocab2

    values = load_vocab2().get("signatureFeatures", {}).get("values", [])
    return next((v["en"] for v in values if v["key"] == tags.get("signature")), None)


def cmd_testpath_bundles(args) -> int:
    """3번: 고른 시드 얼굴을 보고 배경·의상 묶음을 추천받는다."""
    from character_factory_poc.common.api_routes import FAMILY_DEFAULTS
    from character_factory_poc.providers.openai_compat import OpenAICompatVisionModel
    from character_factory_poc.testpath import scenes

    run_dir = _testpath_run(args)
    seed = _seed_entry(run_dir, args.seed)
    image = run_dir / "seeds" / "images" / f"{args.seed}.png"
    out = run_dir / "bundles" / args.seed / "bundles.json"
    if not args.execute:
        print(f"dry run: {args.model}에 {image.name}와 묶음 {args.count}개 요청")
        return 0
    fam = FAMILY_DEFAULTS["openai"]
    model = OpenAICompatVisionModel(
        fam["base_url"], args.model, fam["api_key_env"], timeout=600, max_retries=2
    )
    res = model.judge(scenes.bundle_request(seed["tags"], image, args.count))
    bundles = scenes.parse_bundles(res.text, args.count)
    scenes._write(
        out, {"seedId": args.seed, "model": res.model, "usage": res.usage, "bundles": bundles}
    )
    for b in bundles:
        print(f"{b['id']} [{b['chapter']}/{b['contextKind']}/{b['timeOfDay']}] {b['title']}")
        print(f"    배경: {b['background']['ko']}")
        print(f"    의상: {b['outfit']['ko']}")
    return 0


def cmd_testpath_scenes(args) -> int:
    """4번: 고른 묶음으로 같은 얼굴의 영상용 시드 이미지(9:16)를 만든다."""
    from character_factory_poc.testpath import scenes
    from character_factory_poc.testpath.image_api import OpenAIImagesClient

    run_dir = _testpath_run(args)
    seed = _seed_entry(run_dir, args.seed)
    data = json.loads((run_dir / "bundles" / args.seed / "bundles.json").read_text("utf-8"))
    picks = [p.strip() for p in args.pick.split(",") if p.strip()]
    chosen = [b for b in data["bundles"] if b["id"] in picks]
    out_dir = run_dir / "scenes" / args.seed
    scenes._write(
        out_dir / "selection.json", {"seedId": args.seed, "picks": picks, "reason": args.reason}
    )
    if not args.execute:
        print("dry run:", ", ".join(b["id"] for b in chosen))
        return 0
    results = scenes.render_scenes(
        out_dir,
        run_dir / "seeds" / "images" / f"{args.seed}.png",
        chosen,
        _signature_en(seed["tags"]),
        OpenAIImagesClient(),
        quality=args.quality,
    )
    for r in results:
        print(r["id"], "ok" if r.get("ok") else f"실패: {r.get('error')}")
    return 0


def cmd_testpath_videos(args) -> int:
    """5·6번: 영상용 시드 한 장으로 idle과 반응(애교) 영상을 시작·끝 프레임 고정으로 만든다."""
    from character_factory_poc.stages.s6_actions.catalog import build_prompt
    from character_factory_poc.testpath.videos import VideoApiError, XaiFramesClient

    run_dir = _testpath_run(args)
    scene = run_dir / "scenes" / args.seed / f"{args.scene}.png"
    out_dir = run_dir / "videos" / f"{args.seed}-{args.scene}"
    out_dir.mkdir(parents=True, exist_ok=True)
    client = XaiFramesClient()
    for kind, key in (("idle", "idle_good"), ("reaction", args.action)):
        mp4 = out_dir / f"{kind}-{key}.mp4"
        if mp4.exists():
            print(kind, "있음:", mp4.name)
            continue
        prompt = build_prompt(key, args.chapter)
        if not args.execute:
            print(f"dry run: {kind} {key} {args.resolution} {args.duration}s")
            continue
        meta = None
        for res in dict.fromkeys([args.resolution, "720p"]):
            try:
                data, meta = client.generate(
                    prompt, scene, scene, duration=args.duration, resolution=res
                )
                break
            except VideoApiError as e:
                print(f"{kind} {res} 실패: {e}")
        if meta is None:
            return 1
        mp4.write_bytes(data)
        record = {**meta, "clipKey": key, "chapter": args.chapter, "prompt": prompt}
        (out_dir / f"{kind}-{key}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2), "utf-8"
        )
        print(kind, key, json.dumps(meta, ensure_ascii=False))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cfp", description="character factory poc")
    p.add_argument("--root", default=".", help="프로젝트 루트(factory.toml, runs/)")
    sub = p.add_subparsers(dest="cmd", required=True)

    batch = sub.add_parser("batch").add_subparsers(dest="sub", required=True)
    s = batch.add_parser("run", help="캐릭터별 병렬 실행")
    s.add_argument("--spec", required=True)
    s.add_argument("--execute", action="store_true")
    s.set_defaults(fn=cmd_batch_run)

    s = sub.add_parser("status")
    s.add_argument("character_id")
    s.set_defaults(fn=cmd_status)

    plan = sub.add_parser("plan").add_subparsers(dest="sub", required=True)
    s = plan.add_parser(
        "import",
        help="v2 기획서는 고정하고 G3 승인으로 기록한다. 구형 v1은 신형 후보로 올린다(D-0080)",
    )
    s.add_argument("slug")
    s.add_argument("--from", dest="source", required=True)
    s.add_argument("--brief", default=None)
    s.add_argument("--execute", action="store_true", help="구형 v1을 올릴 때 모델을 부른다")
    s.add_argument("--max-calls", type=int, default=None)
    s.set_defaults(fn=cmd_plan_import)

    persona = sub.add_parser("persona").add_subparsers(dest="sub", required=True)
    quality = persona.add_parser("qualify", help="기본 품질 규약과 첫 응답 검증").add_subparsers(
        dest="quality_action", required=True
    )
    for action in ("plan", "run"):
        q = quality.add_parser(action)
        q.add_argument("cohort")
        q.add_argument("--execute", action="store_true")
        q.add_argument("--output")
        q.add_argument("--tokenizer-url")
        q.add_argument("--max-calls", type=int)
        q.set_defaults(fn=cmd_persona_qualify)
    q = quality.add_parser("report")
    q.add_argument("run")
    q.add_argument("--human-reviews")
    q.set_defaults(fn=cmd_persona_qualify)
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
    s = persona.add_parser("chapters", help="S8c 챕터 시작 설정(장면 사실·경계·관계 설정, D-0089)")
    s.add_argument("character_id")
    s.add_argument("--execute", action="store_true")
    s.add_argument("--max-calls", type=int, default=None)
    s.set_defaults(fn=cmd_persona_chapters)
    s = persona.add_parser("traitcheck", help="특질 장부 기반 자동 특질 시험(D-0091)")
    s.add_argument("character_id")
    s.add_argument("--execute", action="store_true")
    s.add_argument("--max-calls", type=int, default=None)
    s.add_argument("--prompt", default=None, help="시험할 대화 프롬프트(기본: 현재 S8 long.md)")
    s.add_argument(
        "--ledger", default=None, help="특질 장부(기본: 현재 S7 rev의 trait-ledger.json)"
    )
    s.add_argument("--items", default=None, help="이미 만든 문항 파일(같은 문항으로 비교할 때)")
    s.add_argument("--out", default=None)
    s.add_argument("--samples", type=int, default=1)
    s.add_argument("--rejudge", default=None, help="이전 report.json의 응답을 판정만 다시 한다")
    s.set_defaults(fn=cmd_persona_traitcheck)
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

    s = sub.add_parser("review", help="열린 관문의 사전 검토(LLD §6.8). 기본은 호출 계획만 낸다")
    s.add_argument("character_id")
    s.add_argument("gate")
    s.add_argument("--execute", action="store_true")
    s.set_defaults(fn=cmd_review)

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
    s.add_argument(
        "--trait", action="append", default=None, help="추가 특질 ID(반복 가능, 선택 사항)"
    )
    s.add_argument("--expected-seed-rev", default=None, help="저장 기준 씨앗 버전(예: sd1)")
    s.set_defaults(fn=cmd_plan_seed)
    s = plan.add_parser("suggest", help="기본 성격에서 추가 행동 특질을 추천한다(모델 호출 없음)")
    s.add_argument("--personality", required=True)
    s.add_argument("--trait", action="append", default=[], help="이미 선택한 특질 ID")
    s.add_argument("--search", default="", help="행동 표현 직접 검색")
    s.set_defaults(fn=cmd_plan_suggest)
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

    s = plan.add_parser(
        "draft", help="브리프를 씨앗으로 옮겨 기획 변형 3안을 만든다(G3 대기, D-0080)"
    )
    s.add_argument("slug")
    s.add_argument("--brief", required=True)
    s.add_argument("--execute", action="store_true")
    s.add_argument("--max-calls", type=int, default=None)
    s.set_defaults(fn=cmd_plan_draft)

    s = sub.add_parser("run", help="그래프를 따라 관문까지 자동 진행한다")
    s.add_argument("character_id", help="기존 character_id, 또는 --new-slug와 함께 임의 값")
    s.add_argument("--new-slug", default=None, help="새 캐릭터를 만들어 시작한다")
    s.add_argument(
        "--origin",
        choices=("original", "motif", "twin"),
        default=None,
        help=(
            "갈래(D-0144). original=오리지널(창작), motif=모티브(실존 인물 모티브). "
            "twin은 예전 이름으로 motif와 같다. 새 캐릭터를 만들 때만 정한다"
        ),
    )
    s.add_argument(
        "--source-pack",
        default=None,
        help="모티브 출처 묶음 source-pack-v1 JSON(D-0120). 원문 경로는 이 파일 기준 상대 경로다",
    )
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
    s.add_argument(
        "--model-mode",
        choices=("train", "bind", "prompt"),
        default=None,
        help="모티브 모델 준비 방식(D-0118). train=학습, bind=학습된 모델 연결, prompt=학습 없음",
    )

    model = sub.add_parser("model", help="모델 준비 방식·학습된 모델 연결(D-0118)").add_subparsers(
        dest="model_action", required=True
    )
    s = model.add_parser("mode", help="방식을 보거나 정한다(train·bind·prompt)")
    s.add_argument("character_id")
    s.add_argument("mode", nargs="?", choices=("train", "bind", "prompt"), default=None)
    s.add_argument("--reason", default=None)
    s.set_defaults(fn=cmd_model)
    s = model.add_parser(
        "bind", help="이미 학습된 모델 연결 기록(model-binding-import-v1)을 들여온다"
    )
    s.add_argument("character_id")
    s.add_argument("--binding", required=True)
    s.add_argument("--execute", action="store_true")
    s.set_defaults(fn=cmd_model)

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
        ("drive", "제출부터 완료 대기·회수·체크포인트 선택·GPU 반납까지(--execute, 유료)"),
        ("cleanup", "남은 임대 GPU를 찾아 지운다(--execute)"),
    ):
        s = train.add_parser(name, help=help_text)
        s.add_argument("character_id")
        s.add_argument("--providers", default=None, help="쉼표 목록. 없으면 [stages.s10t]")
        s.add_argument("--execute", action="store_true")
        s.set_defaults(fn=cmd_train)
    # 숨은 진입점: drive가 띄우는 분리 감시(guard)를 손으로 다시 띄울 때 쓴다.
    s = train.add_parser("guard")
    s.add_argument("character_id")
    s.add_argument("--providers", default=None)
    s.add_argument("--plan-dir", default=None)
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
    s = ev.add_parser("import-blind", help="모티브 G8: 가족 블라인드 답 파일 들여오기")
    s.add_argument("character_id")
    s.add_argument("answers", help="블라인드 화면에서 저장한 답 파일 경로")
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

    grok = sub.add_parser("grok", help="공장 Grok 로그인(영상 1순위 경로)").add_subparsers(
        dest="sub", required=True
    )
    s = grok.add_parser("login", help="xAI 공식 로그인 화면에서 로그인한다")
    s.add_argument("--device", action="store_true", help="화면 없는 서버: 기기 코드로 로그인")
    s.add_argument("--no-browser", action="store_true", help="브라우저를 열지 않고 주소만 보인다")
    s.set_defaults(fn=cmd_grok)
    s = grok.add_parser("status", help="로그인 상태(토큰 값은 보이지 않는다)")
    s.add_argument("--refresh", action="store_true", help="지금 토큰을 갱신해 본다")
    s.set_defaults(fn=cmd_grok)
    s = grok.add_parser("logout", help="공장의 Grok 로그인을 지운다")
    s.set_defaults(fn=cmd_grok)

    preview = sub.add_parser("preview", help="테스터 전용 미리보기 발행").add_subparsers(
        dest="sub", required=True
    )
    s = preview.add_parser("publish", help="G9 승인 패키지를 테스터에게만 보이게 앱에 올린다")
    s.add_argument("character_id")
    s.add_argument("--notify", action="store_true", help="결과를 디스코드로 알린다")
    s.set_defaults(fn=cmd_preview_publish)
    s = preview.add_parser("remove", help="마지막으로 발행한 테스터 전용 캐릭터를 dev 에서 지운다")
    s.add_argument("character_id")
    s.set_defaults(fn=cmd_preview_remove)

    s = sub.add_parser("demo", help="시연 모드: 모든 관문 자동 승인 → 테스터 발행 → 알림")
    s.add_argument("character_id")
    s.add_argument("state", choices=["on", "off"])
    s.add_argument("--budget", type=float, default=30.0, help="시연 예산 상한(달러)")
    s.set_defaults(fn=cmd_demo_mode)

    s = sub.add_parser("web", help="워크숍 웹앱(LLD §6.5)")
    s.add_argument("--port", type=int, default=None)
    s.set_defaults(fn=cmd_web)

    models = sub.add_parser("models", help="텍스트 모델 덱·호출 경로 설정").add_subparsers(
        dest="models_action", required=True
    )
    testpath = sub.add_parser("testpath", help="시험 경로(2026-11-07)").add_subparsers(
        dest="sub", required=True
    )
    s = testpath.add_parser("seeds", help="2번: 교차 태깅·외모군·베이스 시드 후보")
    s.add_argument(
        "--run", required=True, help="runs/testpath/<run> 폴더(ranking/ranking.json 필요)"
    )
    s.add_argument(
        "--until", choices=["people", "tags", "clusters", "prompts", "images"], default="images"
    )
    s.add_argument("--total", type=int, default=10)
    s.add_argument("--quality", default="high")
    s.add_argument("--look", choices=["candid", "beauty"], default="beauty")
    s.add_argument("--no-signatures", action="store_true", help="후보별 구별 특징을 넣지 않는다")
    s.add_argument(
        "--gemini-route",
        choices=["api", "relay"],
        default="api",
        help="relay = opencodex 중계(google-antigravity/gemini-4-argon)",
    )
    s.add_argument("--execute", action="store_true")
    s.set_defaults(fn=cmd_testpath_seeds)
    s = testpath.add_parser("bundles", help="3번: 시드 얼굴로 배경·의상 묶음 추천")
    s.add_argument("--run", required=True)
    s.add_argument("--seed", required=True)
    s.add_argument("--count", type=int, default=6)
    s.add_argument("--model", default="gpt-6.1-sol")
    s.add_argument("--execute", action="store_true")
    s.set_defaults(fn=cmd_testpath_bundles)
    s = testpath.add_parser("scenes", help="4번: 고른 묶음으로 영상용 시드 이미지")
    s.add_argument("--run", required=True)
    s.add_argument("--seed", required=True)
    s.add_argument("--pick", required=True, help="쉼표 목록, 예: b1,b3,b5")
    s.add_argument("--reason", default="")
    s.add_argument("--quality", default="high")
    s.add_argument("--execute", action="store_true")
    s.set_defaults(fn=cmd_testpath_scenes)
    s = testpath.add_parser("videos", help="5·6번: idle과 애교(반응) 영상")
    s.add_argument("--run", required=True)
    s.add_argument("--seed", required=True)
    s.add_argument("--scene", required=True)
    s.add_argument("--chapter", default="ch2")
    s.add_argument("--action", default="pouty_good")
    s.add_argument("--duration", type=int, default=6)
    s.add_argument("--resolution", default="720p")
    s.add_argument("--execute", action="store_true")
    s.set_defaults(fn=cmd_testpath_videos)
    s = models.add_parser("show", help="유효 모델·프로필·호출 경로를 확인한다(호출 없음)")
    s.set_defaults(fn=cmd_models)
    s = models.add_parser("select", help="프로필/경로 선택을 work에 저장한다(호출 없음)")
    s.add_argument("--profile", choices=["basic_test", "demo", "pre_demo_completion_check"])
    s.add_argument("--route", choices=["opencodex", "test", "api"])
    s.set_defaults(fn=cmd_models)

    ledger = sub.add_parser("ledger").add_subparsers(dest="sub", required=True)
    s = ledger.add_parser("report")
    s.add_argument("character_id")
    s.set_defaults(fn=cmd_ledger_report)
    s = ledger.add_parser("cost", help="비용 보고서 cost-report-v1(원장은 고치지 않는다)")
    s.add_argument("target", help="캐릭터 ID 또는 calls.jsonl 경로")
    s.add_argument("--recompute", action="store_true", help="현재 단가표로 다시 환산한다")
    s.add_argument("--out", default=None, help="보고서 JSON을 쓸 경로(runs/나 work/ 아래 권장)")
    s.set_defaults(fn=cmd_ledger_cost)

    report = sub.add_parser("report", help="사람 시간 보고서").add_subparsers(
        dest="sub", required=True
    )
    s = report.add_parser("hil", help="사람 관문 보고서 hil-report-v1을 쓰고 표로 낸다")
    s.add_argument("character_id")
    s.set_defaults(fn=cmd_report_hil)

    s = sub.add_parser("verify")
    s.add_argument("character_id")
    s.set_defaults(fn=cmd_verify)

    # D-0144: 모티브 갈래 명령. 예전 이름 twin도 같은 명령으로 받는다.
    motif = sub.add_parser("motif", aliases=["twin"], help="모티브 갈래 도구").add_subparsers(
        dest="sub", required=True
    )
    s = motif.add_parser("precheck", help="기준 사진으로 이미지·영상 한 건씩 확인해요")
    s.add_argument("--photo", type=Path, required=True, help="기준 사진 경로를 넣어 주세요")
    kinds = s.add_mutually_exclusive_group()
    kinds.add_argument("--image-only", action="store_true", help="이미지만 확인해요")
    kinds.add_argument("--video-only", action="store_true", help="기준 사진에서 영상만 만들어요")
    s.add_argument("--execute", action="store_true", help="승인한 계획을 실행해요")
    s.set_defaults(fn=cmd_twin_precheck)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except FactoryError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1


def cmd_twin_precheck(args) -> int:
    from character_factory_poc.stages.s0_source.precheck import run_precheck

    return run_precheck(
        _ctx(args), args.photo, image=not args.video_only, video=not args.image_only
    )
