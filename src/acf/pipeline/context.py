"""명령 실행 문맥: 설정, 경로, 원장, 예산, 공급자."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from acf.common.budget import Budget
from acf.common.config import FactoryConfig, load_config
from acf.common.ledger import Ledger
from acf.pipeline.state import StateFile
from acf.providers.base import ImageModel, TextModel, VideoModel
from acf.providers.factory import make_image_model, make_text_model, make_video_model
from acf.providers.tracked import TrackedImageModel, TrackedTextModel, TrackedVideoModel


@dataclass
class Context:
    config: FactoryConfig
    execute: bool
    max_calls: int | None = None
    _text: TextModel | None = None
    _judge: TextModel | None = None
    _codex: object | None = None
    _image: ImageModel | None = None
    _video: VideoModel | None = None
    _vision: object | None = None

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
        return Budget(self.config.budget, max_calls_override=self.max_calls)

    def text_model(self, character_id: str, budget: Budget) -> TextModel:
        if self._text is None:
            self._text = make_text_model(self.config.provider("text"))
        return TrackedTextModel(self._text, self.ledger(character_id), budget)

    def judge_model(self, character_id: str, budget: Budget, allow_same_family=False) -> TextModel:
        if self._judge is None:
            self._judge = make_text_model(self.config.provider("judge"))
        t, j = self.config.provider("text"), self.config.provider("judge")
        if t.adapter != "fake" and j.adapter != "fake" and t.family() == j.family():
            msg = f"경고: 생성({t.model})과 판정({j.model}) 모델 계열이 같다(D-0010)"
            print(msg, file=sys.stderr)
            if not allow_same_family:
                raise ValueError(msg + ". --allow-same-family로 명시해야 한다")
        return TrackedTextModel(self._judge, self.ledger(character_id), budget)

    # 테스트에서 가짜 모델을 주입할 때 쓴다.
    def use_models(self, text: TextModel, judge: TextModel | None = None) -> None:
        self._text = text
        self._judge = judge or text

    def image_model(self, character_id: str, budget: Budget) -> TrackedImageModel:
        if self._image is None:
            self._image = make_image_model(self.config.provider("image"))
        return TrackedImageModel(self._image, self.ledger(character_id), budget)

    def use_image(self, image: ImageModel) -> None:
        self._image = image

    def video_model(self, character_id: str, budget: Budget) -> TrackedVideoModel:
        if self._video is None:
            self._video = make_video_model(self.config.provider("video"))
        return TrackedVideoModel(self._video, self.ledger(character_id), budget)

    def use_video(self, video: VideoModel) -> None:
        self._video = video

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
        from acf.providers.factory import make_vision_model
        from acf.providers.tracked import TrackedVisionModel

        if self._vision is None:
            self._vision = make_vision_model(self.config.provider("vision"))
        return TrackedVisionModel(self._vision, self.ledger(character_id), budget)

    def use_vision(self, vision) -> None:
        self._vision = vision

    def use_codex(self, backend) -> None:
        self._codex = backend

    def agent_backend(self, character_id: str, budget: Budget, stage: str):
        """[agent] backend = "codex_exec"이면 추적 래퍼를 돌려주고, 아니면 None(API 백엔드)."""
        from acf.providers.tracked import TrackedCodexAgent

        if self._codex is None:
            if self.config.agent.get("backend") != "codex_exec":
                return None
            from acf.providers.codex_exec import CodexExecAgent

            a = self.config.agent
            self._codex = CodexExecAgent(
                model=a.get("model") or self.config.provider("text").model,
                reasoning_effort=a.get("reasoning_effort", "medium"),
                sandbox=a.get("sandbox", "workspace-write"),
                timeout_s=int(a.get("timeout_s", 1800)),
                extra_config=list(a.get("extra_config", [])),
            )
        return TrackedCodexAgent(self._codex, self.ledger(character_id), budget, stage)
