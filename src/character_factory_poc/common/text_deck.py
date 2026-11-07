"""Resolve the pinned deck, explicit execution profile, and independent transport."""

from __future__ import annotations

import json
from dataclasses import asdict
from importlib.resources import files
from urllib.parse import urlsplit

from character_factory_poc.common.canonical import sha256_text

JUDGE_TASKS = frozenset({"consistency", "screening", "adjudication"})
API_ROUTE_KEYS = frozenset({"adapter", "families", "models", "timeout_s", "stream"})
API_FAMILY_KEYS = frozenset({"base_url", "api_key_env", "timeout_s"})
ROLE_TASKS = {
    "seed_requirements": "brief",
    "plan_variants": "personality",
    "plan_normalizer": "personality",
    "choice_variants": "personality",
    "choice_review": "consistency",
    "deck_plan_voice": "voice",
    "profiler": "voice",
    "chapter_start": "voice",
    "trait_ledger": "voice",
    "persona_formation": "voice",
    "persona_choice_formation": "voice",
    "persona_dialogues": "voice",
    "persona_beats": "scenarios",
    "persona_voice_render": "voice",
    "persona_voice_preservation": "consistency",
    "data_handoff": "scenarios",
    "data_writer": "sft_answers",
}
TEXT_STAGES = frozenset(
    {
        "s3",
        "s3-own",
        "s3-variants",
        "s7",
        "s8",
        "s8c",
        "s9s",
        "s9",
        "cv-requirements",
        "cv-choices",
        "cv-choice-review",
        "cv-design",
        "cv-beats",
        "cv-render",
        "cv-preservation",
    }
)


def deck() -> dict:
    return json.loads(
        files("character_factory_poc")
        .joinpath("resources/text-model-deck-v2.json")
        .read_text(encoding="utf-8")
    )


def task_for_role(role: str) -> str:
    try:
        return ROLE_TASKS[role]
    except KeyError:
        raise ValueError(f"텍스트 모델 덱에 없는 역할: {role}") from None


def _api_transport(route_settings, model: str) -> tuple[dict, str]:
    """api 경로는 덱 모델의 계열 기본값 위에 계열별 설정만 덮는다(명세 §24.2)."""
    from character_factory_poc.common.api_routes import FAMILY_DEFAULTS, family_of

    family = family_of(model)
    if family is None:
        raise ValueError(f"api 경로에서 모델 계열을 정할 수 없다: {model}")
    if not isinstance(route_settings, dict):
        raise ValueError("text_pipeline.routes.api는 표여야 한다")
    unknown = sorted(set(route_settings) - API_ROUTE_KEYS)
    if unknown:
        raise ValueError(
            "text_pipeline.routes.api에서 쓸 수 없는 항목이다(주소·인증은 families.<계열>에 둔다): "
            + ", ".join(unknown)
        )
    families = route_settings.get("families", {})
    if not isinstance(families, dict) or any(not isinstance(v, dict) for v in families.values()):
        raise ValueError("text_pipeline.routes.api.families는 계열별 표여야 한다")
    unknown = sorted(set(families) - set(FAMILY_DEFAULTS))
    if unknown:
        raise ValueError(f"알 수 없는 api 계열이다: {', '.join(unknown)}")
    override = families.get(family, {})
    unknown = sorted(set(override) - API_FAMILY_KEYS)
    if unknown:
        raise ValueError(
            f"text_pipeline.routes.api.families.{family}에서 쓸 수 없는 항목이다: "
            + ", ".join(unknown)
        )
    transport = (
        dict(
            adapter=route_settings.get("adapter", "openai_compat"),
            timeout_s=route_settings.get("timeout_s", 240),
        )
        | FAMILY_DEFAULTS[family]
        | override
    )
    transport["models"] = route_settings.get("models", {})
    stream = route_settings.get("stream", False)
    if not isinstance(stream, bool):
        raise ValueError("text_pipeline.routes.api.stream은 true 또는 false다")
    transport["stream"] = stream
    if not transport.get("api_key_env"):
        raise ValueError(f"api 경로의 {family} 계열에는 인증 환경변수 이름이 필요하다")
    return transport, family


def resolve(config, task: str) -> dict:
    from character_factory_poc.common.config import _provider

    source = deck()
    tasks = {s["id"]: s for s in source["stages"]}
    if task not in tasks:
        raise ValueError(f"텍스트 모델 덱에 없는 task: {task}")
    settings = config.text_pipeline
    profile = settings.get("profile", source["default_profile"])
    route = settings.get("route", "opencodex")
    if profile not in source["profiles"]:
        raise ValueError(f"알 수 없는 text_pipeline profile: {profile}")
    routes = settings.get("routes", {})
    stage = tasks[task]
    selected_model = source["profiles"][profile]["model_overrides"].get(
        stage["model"], stage["model"]
    )
    family = None
    if route == "api":
        transport, family = _api_transport(routes.get("api", {}), selected_model)
    elif route == "opencodex":
        transport = dict(routes.get(route, {}))
        transport = (
            dict(adapter="openai_compat", base_url=source["transport"]["base_url"], api_key_env="")
            | transport
        )
    elif route != "test":
        raise ValueError(f"알 수 없는 text_pipeline route: {route}")
    else:
        transport = dict(routes.get(route, {}))
    if not transport.get("base_url"):
        raise ValueError(f"text_pipeline.routes.{route}.base_url을 먼저 설정해야 한다")
    if transport.get("adapter", "openai_compat") != "openai_compat":
        raise ValueError("텍스트 제작 경로는 openai_compat 어댑터를 사용한다")
    url = urlsplit(transport["base_url"])
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise ValueError("base_url은 인증정보·query·fragment 없는 HTTP(S) 주소여야 한다")
    env = transport.get("api_key_env", "")
    if env:
        from character_factory_poc.common.api_routes import validate_env_name

        validate_env_name(env)
    mapping = transport.get("models", {})
    if not isinstance(mapping, dict) or any(
        not isinstance(v, str) or not v.strip() for v in mapping.values()
    ):
        raise ValueError("경로의 models는 비어 있지 않은 모델 ID 매핑이어야 한다")
    if family is None:
        model = mapping.get(selected_model, selected_model)
    else:
        # api 경로는 설정 매핑(덱 ID, 다음으로 공식 ID 키)이 공식 모델 ID 규칙보다 우선한다.
        from character_factory_poc.common.api_routes import official_model_id

        official = official_model_id(selected_model)
        model = mapping.get(selected_model, mapping.get(official, official))
    provider = _provider(
        dict(
            adapter="openai_compat",
            base_url=transport["base_url"],
            api_key_env=env,
            model=model,
            reasoning_effort=stage["reasoning_effort"],
            timeout_s=float(transport.get("timeout_s", 240)),
            max_retries=0,
            # api 경로만 stream 칸을 둔다(opencodex·test 반환값은 fingerprint 때문에 그대로).
            **({"stream": transport.get("stream", False)} if route == "api" else {}),
        )
    )
    binding = dict(
        task=task,
        profile=profile,
        route=route,
        baselineModel=stage["model"],
        model=provider.model,
        reasoning_effort=stage["reasoning_effort"],
        provider=asdict(provider),
        deckSha256=sha256_text(json.dumps(source, sort_keys=True)),
    )
    if family is not None:
        # opencodex·test 반환값은 형성 fingerprint가 해시하므로 api 경로에만 계열을 더한다.
        binding["family"] = family
    return binding


def selection_path(config):
    return config.root / "work" / "text-pipeline-selection.json"


def select(config, *, profile=None, route=None) -> dict:
    """Validate the entire candidate before atomically persisting non-secret choices."""
    from dataclasses import replace

    if not config.text_pipeline.get("enabled", False):
        raise ValueError("text_pipeline.enabled가 꺼져 있다")
    candidate = dict(config.text_pipeline)
    if profile is not None:
        candidate["profile"] = profile
    if route is not None:
        candidate["route"] = route
    updated = replace(config, text_pipeline=candidate)
    bindings = [resolve(updated, s["id"]) for s in deck()["stages"]]
    chosen = dict(profile=bindings[0]["profile"], route=bindings[0]["route"])
    path = selection_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(chosen, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)
    return chosen
