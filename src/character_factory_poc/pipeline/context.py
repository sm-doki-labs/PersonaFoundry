"""명령 실행 문맥: 설정, 경로, 원장, 예산, 공급자."""

from __future__ import annotations

import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

from character_factory_poc.common.budget import Budget
from character_factory_poc.common.config import FactoryConfig, load_config
from character_factory_poc.common.ledger import Ledger
from character_factory_poc.pipeline.state import StateFile
from character_factory_poc.providers.base import ImageModel, TextModel, VideoModel
from character_factory_poc.providers.factory import (
    make_image_model,
    make_text_model,
    make_video_model,
)
from character_factory_poc.providers.tracked import (
    ProviderLimits,
    TrackedImageModel,
    TrackedTextModel,
    TrackedVideoModel,
)


def _utc_now():
    """형성 예산 단가를 고르는 시각. 테스트가 시계를 고정할 때 바꾼다."""
    from datetime import UTC, datetime

    return datetime.now(UTC)


@dataclass
class Context:
    config: FactoryConfig
    execute: bool
    max_calls: int | None = None
    _text: TextModel | None = None
    _judge: TextModel | None = None
    _planner: TextModel | None = None
    _analyzer: TextModel | None = None
    _labeler: TextModel | None = None
    _labeler_effort: dict | None = None
    _signature_image: ImageModel | None = None
    _codex: object | None = None
    _image: ImageModel | None = None
    _video: VideoModel | None = None
    _vision: object | None = None
    _run_budget: object | None = None
    # D-0049(LLD §6.6): 물결 실행에서 여러 단계가 동시에 공급자를 처음 만들 수 있다.
    _lazy: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    _budget_character: str | None = None
    _injected: dict = field(default_factory=dict, repr=False, compare=False)

    def for_character(self, cid: str) -> Context:
        if self._run_budget is not None:
            raise ValueError("기존 형성 예산을 캐릭터 배치에 재사용할 수 없다")
        from copy import deepcopy

        # 주입한 가짜 공급자의 응답 큐·요청 이력은 복제하고, 일반 클라이언트는 새로 만든다.
        return Context(
            config=self.config,
            execute=self.execute,
            max_calls=self.max_calls,
            _budget_character=cid,
            **deepcopy(self._injected),
        )

    def _limited(self, tracked, kind: str):
        tracked.limits = ProviderLimits(self.config.orchestrator, kind, tracked.ledger)
        return tracked

    @classmethod
    def load(cls, root: Path, execute: bool, max_calls: int | None = None) -> Context:
        return cls(config=load_config(root), execute=execute, max_calls=max_calls)

    def character_dir(self, character_id: str) -> Path:
        return self.config.runs_dir / "characters" / character_id

    def ledger(self, character_id: str) -> Ledger:
        return Ledger(self.character_dir(character_id) / "ledger")

    def state(self, character_id: str) -> StateFile:
        return StateFile(self.character_dir(character_id) / "state.json", character_id)

    def budget(self) -> Budget:
        if self._run_budget is not None:
            return self._run_budget
        return Budget(self.config.budget, max_calls_override=self.max_calls)

    def formation_budget(self):
        """New recipe shares one persistent envelope across S3 and S7 commands."""
        if self._run_budget is not None:
            return self._run_budget
        from character_factory_poc.common.budget import RunBudget

        cfg = self.config.stage("s7")
        synthetic = not self.text_deck_enabled and all(
            self.config.provider(k).adapter == "fake" for k in ("text", "judge")
        )
        scope = str(cfg.get("budget_run_id", "choice-voice"))
        if not scope or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for c in scope
        ):
            raise ValueError("budget_run_id must contain letters, numbers, hyphens or underscores")
        folder = self.config.runs_dir / "budgets"
        if self._budget_character:
            folder = self.character_dir(self._budget_character) / "budgets"
        path = folder / f"{scope}.json"
        input_rate = cfg.get("input_rate_upper_per_million", 0 if synthetic else None)
        output_rate = cfg.get("output_rate_upper_per_million", 0 if synthetic else None)
        if not synthetic and self.text_deck_enabled and (input_rate is None or output_rate is None):
            table_in, table_out = self._deck_rate_upper(path)
            input_rate = table_in if input_rate is None else input_rate
            output_rate = table_out if output_rate is None else output_rate
        self._run_budget = RunBudget(
            path,
            max_calls=min(
                self.max_calls or self.config.budget.max_calls_per_command,
                self.config.budget.max_calls_per_command,
            ),
            max_tokens=int(cfg.get("max_run_tokens", 2_000_000)),
            max_cost_usd=self.config.budget.max_cost_usd_per_command,
            input_rate_per_million=input_rate,
            output_rate_per_million=output_rate,
            synthetic=synthetic,
        )
        return self._run_budget

    def _deck_rate_upper(self, path: Path) -> tuple[float | None, float | None]:
        """현재 덱 task 모델들의 가장 높은 입력·출력 단가(명세 §24.6).

        미확인 단가가 있으면 호출 전에 거절한다. 봉투가 이미 있으면 처음 만든 단가를 쓰되,
        지금 프로필·경로의 단가가 그보다 높으면 봉투가 상한을 지킬 수 없으므로 거절한다.
        """
        import json

        from character_factory_poc.common import pricing
        from character_factory_poc.common.text_deck import deck

        models = sorted({self.config.text_binding(s["id"])["model"] for s in deck()["stages"]})
        now = _utc_now()
        overrides = self.price_overrides()
        rates = pricing.max_rates(models, now, overrides)
        if rates is None:
            missing = pricing.missing_prices(models, now, overrides)
            raise ValueError(
                "형성 예산의 단가 상한을 정할 수 없다. 단가 미확인 모델: "
                + ", ".join(missing or models)
            )
        if not path.exists():
            return rates
        try:
            limits = json.loads(path.read_text("utf-8"))["limits"]
            envelope = (limits["inputRate"], limits["outputRate"])
        except (ValueError, KeyError, TypeError, OSError):
            return rates  # 손상된 봉투는 RunBudget이 거절한다.
        if rates[0] > envelope[0] or rates[1] > envelope[1]:
            raise ValueError(
                f"현재 덱 단가 상한(입력 {rates[0]}, 출력 {rates[1]} USD/1M)이 기존 예산 봉투"
                f"(입력 {envelope[0]}, 출력 {envelope[1]})보다 높다. "
                "[stages.s7] budget_run_id를 새로 정해 새 봉투로 실행한다"
            )
        return envelope

    def price_overrides(self) -> dict:
        return dict(getattr(self.config, "pricing", None) or {})

    def _billing(self, cfg, inner, route: str | None = None) -> dict | None:
        """공급자 설정의 과금 구분(명세 §24.2). 주입한 가짜 모델은 래퍼가 none으로 표시한다."""
        if getattr(inner, "name", "") == "fake":
            return None
        from character_factory_poc.common import api_routes

        return api_routes.billing_for(cfg, route=route)

    @property
    def text_deck_enabled(self) -> bool:
        return bool(self.config.text_pipeline.get("enabled", False))

    def task_model(self, character_id: str, budget: Budget, task: str) -> TextModel:
        from character_factory_poc.common.text_deck import JUDGE_TASKS

        if not self.text_deck_enabled:
            if task in JUDGE_TASKS:
                return self.judge_model(character_id, budget)
            return self.text_model(character_id, budget)
        if not self.execute:
            raise ValueError("텍스트 제작 모델 호출에는 --execute가 필요하다")
        cfg = self.config.task_provider(task)
        binding = self.config.text_binding(task)
        if cfg.api_key_env and not cfg.api_key():
            from character_factory_poc.common.api_routes import family_of

            # 설정 칸에 키 값을 잘못 넣었을 수 있으므로 환경변수 이름은 알리지 않는다.
            family = binding.get("family") or family_of(cfg.model) or "미상"
            raise ValueError(f"{task} task({family} 계열)의 인증 키가 설정되지 않았다")
        inner = make_text_model(cfg)
        return self._limited(
            TrackedTextModel(
                inner,
                self.ledger(character_id),
                budget,
                binding=binding,
                billing=self._billing(cfg, inner, route=binding["route"]),
                price_overrides=self.price_overrides(),
                # D-0084: 덱 경로는 어댑터 재시도를 끄므로 전송 실패만 예산 안에서 다시 보낸다.
                transport_retries=int(self.config.text_pipeline.get("transport_retries", 1)),
            ),
            "judge" if task in JUDGE_TASKS else "text",
        )

    def role_model(self, character_id: str, budget: Budget, role: str) -> TextModel:
        from character_factory_poc.common.text_deck import task_for_role

        return self.task_model(character_id, budget, task_for_role(role))

    def text_model(self, character_id: str, budget: Budget) -> TextModel:
        with self._lazy:
            if self._text is None:
                self._text = make_text_model(self.config.provider("text"))
        return self._limited(
            TrackedTextModel(
                self._text,
                self.ledger(character_id),
                budget,
                billing=self._billing(self.config.provider("text"), self._text),
                price_overrides=self.price_overrides(),
            ),
            "text",
        )

    def analyzer_model(self, character_id: str, budget: Budget) -> TextModel:
        """S3 원문 분석기 모델. [providers.analyzer]가 없으면 조립 모델(planner)을 쓴다."""
        if "analyzer" not in self.config.providers or "_text" in self._injected:
            return self.planner_model(character_id, budget)
        cfg = self.config.provider("analyzer")
        with self._lazy:
            if self._analyzer is None:
                self._analyzer = make_text_model(cfg)
        return self._limited(
            TrackedTextModel(
                self._analyzer,
                self.ledger(character_id),
                budget,
                billing=self._billing(cfg, self._analyzer),
                price_overrides=self.price_overrides(),
            ),
            "text",
        )

    def labeler_model(
        self, character_id: str, budget: Budget, reasoning: str | None = None
    ) -> TextModel:
        """S8 응답별 표시 모델(evidence-v9). [providers.labeler]가 없으면 S3 분석기 모델을 쓴다.

        reasoning을 주면 같은 공급자 설정에 추론 강도만 바꾼 모델을 쓴다(evidence-v10의
        표시·보충 단계). 분석기 모델로 대신할 때는 무시한다.
        """
        if "labeler" not in self.config.providers or "_text" in self._injected:
            return self.analyzer_model(character_id, budget)
        cfg = self.config.provider("labeler")
        if reasoning is not None:
            from dataclasses import replace

            cfg = replace(cfg, extra=dict(cfg.extra, reasoning_effort=reasoning))
        with self._lazy:
            if reasoning is not None:
                self._labeler_effort = self._labeler_effort or {}
                if reasoning not in self._labeler_effort:
                    self._labeler_effort[reasoning] = make_text_model(cfg)
                inner = self._labeler_effort[reasoning]
            elif self._labeler is None:
                self._labeler = make_text_model(cfg)
                inner = self._labeler
            else:
                inner = self._labeler
        return self._limited(
            TrackedTextModel(
                inner,
                self.ledger(character_id),
                budget,
                billing=self._billing(cfg, inner),
                price_overrides=self.price_overrides(),
            ),
            "text",
        )

    def planner_model(self, character_id: str, budget: Budget) -> TextModel:
        """S3 원문 분석·기획 조립 모델. [providers.planner]가 없으면 생성 모델을 쓴다."""
        if "planner" not in self.config.providers or "_text" in self._injected:
            return self.text_model(character_id, budget)
        cfg = self.config.provider("planner")
        with self._lazy:
            if self._planner is None:
                self._planner = make_text_model(cfg)
        return self._limited(
            TrackedTextModel(
                self._planner,
                self.ledger(character_id),
                budget,
                billing=self._billing(cfg, self._planner),
                price_overrides=self.price_overrides(),
            ),
            "text",
        )

    def judge_model(self, character_id: str, budget: Budget, allow_same_family=False) -> TextModel:
        with self._lazy:
            if self._judge is None:
                self._judge = make_text_model(self.config.provider("judge"))
        t, j = self.config.provider("text"), self.config.provider("judge")
        if t.adapter != "fake" and j.adapter != "fake" and t.family() == j.family():
            msg = f"경고: 생성({t.model})과 판정({j.model}) 모델 계열이 같다(D-0010)"
            print(msg, file=sys.stderr)
            if not allow_same_family:
                raise ValueError(msg + ". --allow-same-family로 명시해야 한다")
        return self._limited(
            TrackedTextModel(
                self._judge,
                self.ledger(character_id),
                budget,
                billing=self._billing(j, self._judge),
                price_overrides=self.price_overrides(),
            ),
            "judge",
        )

    # 테스트에서 가짜 모델을 주입할 때 쓴다.
    def use_models(self, text: TextModel, judge: TextModel | None = None) -> None:
        self._text = text
        self._judge = judge or text
        self._injected.update(_text=self._text, _judge=self._judge)

    def image_model(self, character_id: str, budget: Budget) -> TrackedImageModel:
        with self._lazy:
            if self._image is None:
                self._image = make_image_model(self.config.provider("image"))
        return self._limited(
            TrackedImageModel(self._image, self.ledger(character_id), budget), "image"
        )

    def use_image(self, image: ImageModel) -> None:
        self._image = image
        self._injected["_image"] = image

    def signature_image_model(self, character_id: str, budget: Budget) -> TrackedImageModel:
        """S4 시그니처 중간 사진 모델. [providers.signature_image]가 없으면 이미지 모델을 쓴다.

        기준 사진의 몸 폭을 바꾸지 않는 편집 모델(Grok 이미지 편집)을 따로 지정할 수 있다.
        """
        if "signature_image" not in self.config.providers or "_image" in self._injected:
            return self.image_model(character_id, budget)
        with self._lazy:
            if self._signature_image is None:
                self._signature_image = make_image_model(self.config.provider("signature_image"))
        return self._limited(
            TrackedImageModel(self._signature_image, self.ledger(character_id), budget), "image"
        )

    def video_model(self, character_id: str, budget: Budget) -> TrackedVideoModel:
        with self._lazy:
            if self._video is None:
                self._video = make_video_model(self.config.provider("video"))
        return self._limited(
            TrackedVideoModel(self._video, self.ledger(character_id), budget), "video"
        )

    def use_video(self, video: VideoModel) -> None:
        self._video = video
        self._injected["_video"] = video

    def vision_family_warning(self) -> str:
        """이미지 생성과 비전 판정 모델 계열이 같으면 경고 문장(D-0010, D-0036)."""
        i, v = self.config.provider("image"), self.config.provider("vision")
        if i.adapter == "fake" or v.adapter == "fake":
            return ""
        img_family = "gpt" if i.adapter == "codex_image" else i.family()
        if img_family == v.family():
            return f"이미지 생성({i.model})과 비전 판정({v.model}) 모델 계열이 같다(D-0010)"
        return ""

    def vision_model(self, character_id: str, budget: Budget):
        """이미지 자동 검사의 비전 판정 모델(D-0036). 원장 kind=VISION."""
        from character_factory_poc.providers.factory import make_vision_model
        from character_factory_poc.providers.tracked import TrackedVisionModel

        with self._lazy:
            if self._vision is None:
                self._vision = make_vision_model(self.config.provider("vision"))
        return self._limited(
            TrackedVisionModel(
                self._vision,
                self.ledger(character_id),
                budget,
                billing=self._billing(self.config.provider("vision"), self._vision),
                price_overrides=self.price_overrides(),
            ),
            "vision",
        )

    def use_vision(self, vision) -> None:
        self._vision = vision
        self._injected["_vision"] = vision

    def use_codex(self, backend) -> None:
        self._codex = backend
        self._injected["_codex"] = backend

    def agent_backend(self, character_id: str, budget: Budget, stage: str):
        """[agent] backend = "codex_exec"이면 추적 래퍼를 돌려주고, 아니면 None(API 백엔드)."""
        from character_factory_poc.common.text_deck import TEXT_STAGES
        from character_factory_poc.providers.tracked import TrackedCodexAgent

        if self.text_deck_enabled and stage in TEXT_STAGES:
            return None

        with self._lazy:
            if self._codex is None:
                if self.config.agent.get("backend") != "codex_exec":
                    return None
                from character_factory_poc.providers.codex_exec import CodexExecAgent

                a = self.config.agent
                self._codex = CodexExecAgent(
                    model=a.get("model") or self.config.provider("text").model,
                    reasoning_effort=a.get("reasoning_effort", "medium"),
                    sandbox=a.get("sandbox", "workspace-write"),
                    timeout_s=int(a.get("timeout_s", 1800)),
                    extra_config=list(a.get("extra_config", [])),
                )
        return self._limited(
            TrackedCodexAgent(self._codex, self.ledger(character_id), budget, stage), "text"
        )
