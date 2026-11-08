"""합성 팬·가족 모티브와 오리지널의 앱 표시 문구 계약."""

import pytest

from character_factory_poc.stages.export.doki_app.api_svc import build_seed
from character_factory_poc.stages.export.settings import API_SVC_HEAD
from character_factory_poc.stages.s11_release.package import build_package, load_package
from tests.support.export_flow import full_flow
from tests.test_twin_export import _approved


@pytest.mark.parametrize(
    ("mode", "button"),
    [(None, None), ("PROMPT_ONLY", "안부 전화하기"), ("BIND_EXISTING", "통화 시작하기")],
)
def test_character_seed_labels(tmp_path, mode, button):
    if mode is None:
        ctx, cid = full_flow(tmp_path)
    else:
        ctx, cid, _, _ = _approved(tmp_path, mode)
    build_package(ctx, cid)
    package, folder = load_package(ctx, cid)
    seed = build_seed(
        package, folder, exported_at="2026-11-08T00:00:00Z", alembic_revision=API_SVC_HEAD
    )
    table = seed.bundle["tables"]["character"]
    (row,) = table["rows"]
    character = dict(zip(table["columns"], row, strict=True))
    assert character["call_start_label"] == button
    assert character["disclosure_label"] == ("AI 생성 · 본인과 무관한 기술 시연" if mode else None)
    assert not any(
        "twin.disclosure" in item or "twin.startButtonLabel" in item for item in seed.unmapped
    )
