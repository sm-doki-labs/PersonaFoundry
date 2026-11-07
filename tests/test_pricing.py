"""단가표 price-table-v1 조회·비용 계산·설정 덮어쓰기 (명세 §24.4, LLD §22.2 C)."""

import copy
import json
from datetime import UTC, date, datetime, timedelta, timezone
from importlib.resources import files

import pytest

from character_factory_poc.common import pricing
from character_factory_poc.common.config import load_config
from character_factory_poc.common.pricing import (
    TABLE_VERSION,
    PriceEntry,
    canonical_model,
    estimate,
    load_table,
    lookup,
    max_rates,
    missing_prices,
    price_ref,
)


def at(day: str, hour: int = 12) -> datetime:
    return datetime.fromisoformat(day).replace(hour=hour, tzinfo=UTC)


def raw_table() -> dict:
    text = files("character_factory_poc.resources").joinpath("price-table-v1.json").read_text()
    return json.loads(text)


def write_table(tmp_path, data) -> object:
    path = tmp_path / "table.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def entry(**changes) -> PriceEntry:
    base = dict(
        model="m",
        family="openai",
        effective_from=date(2026, 11, 4),
        effective_to=None,
        input_per_million=2.0,
        cached_input_per_million=0.1,
        cache_write_per_million=2.5,
        output_per_million=10.0,
        source="https://example.invalid/pricing",
        checked_at="2026-11-04",
    )
    base.update(changes)
    return PriceEntry(**base)


def test_shipped_table_matches_spec_values():
    table = load_table()
    rows = {
        (e.model, e.effective_from.isoformat(), e.effective_to and e.effective_to.isoformat()): (
            e.input_per_million,
            e.cached_input_per_million,
            e.cache_write_per_million,
            e.output_per_million,
        )
        for e in table
    }
    assert rows == {
        ("gpt-6.1-sol", "2026-11-04", None): (2, 0.10, 2.50, 10),
        ("gpt-6.1-terra", "2026-11-04", None): (1, 0.05, 1.25, 5),
        ("gemini-3.8-flash", "2026-11-04", "2026-12-31"): (0.75, 0.075, None, 3.75),
        ("gemini-3.8-flash", "2027-01-01", None): (1.50, 0.15, None, 7.50),
        ("gemini-4-argon", "2026-11-04", "2026-11-30"): (2, None, None, 10),
        ("gemini-4-argon", "2026-12-01", None): (4, None, None, 20),
    }
    # OpenAI 캐시 쓰기는 입력 단가의 1.25배다.
    for e in table:
        if e.family == "openai":
            assert e.cache_write_per_million == pytest.approx(e.input_per_million * 1.25)
    assert {e.checked_at for e in table} == {"2026-11-04"}
    assert {e.basis for e in table} == {"table"}
    assert raw_table()["version"] == TABLE_VERSION


def test_canonical_model_strips_relay_prefixes():
    assert canonical_model("google-antigravity/gemini-3.8-flash") == "gemini-3.8-flash"
    assert canonical_model("openai/gpt-6.1-sol") == "gpt-6.1-sol"
    assert canonical_model("gpt-6.1-sol") == "gpt-6.1-sol"


def test_lookup_uses_utc_day_at_promo_boundaries():
    assert lookup("gemini-4-argon", at("2026-11-30")).input_per_million == 2
    assert lookup("gemini-4-argon", at("2026-12-01")).input_per_million == 4
    flash_end = lookup("google-antigravity/gemini-3.8-flash", at("2026-12-31"))
    assert (flash_end.input_per_million, flash_end.output_per_million) == (0.75, 3.75)
    flash_next = lookup("google-antigravity/gemini-3.8-flash", at("2027-01-01"))
    assert (flash_next.input_per_million, flash_next.output_per_million) == (1.50, 7.50)
    assert flash_next.source == "https://ai.google.dev/gemini-api/docs/latest-model"
    # 한국 시각 12월 1일 오전 8시는 UTC로 11월 30일이다.
    kst = timezone(timedelta(hours=9))
    assert lookup("gemini-4-argon", datetime(2026, 12, 1, 8, tzinfo=kst)).input_per_million == 2


def test_lookup_misses_unknown_model_and_days_before_checked_date():
    assert lookup("claude-unknown", at("2026-11-04")) is None
    assert lookup("gpt-6.1-sol", at("2026-11-03", hour=23)) is None
    assert lookup("gpt-6.1-sol", at("2030-01-01")).input_per_million == 2


def test_overrides_win_regardless_of_period_and_prefix():
    overrides = {
        "google-antigravity/gemini-4-argon": {"input_per_million": 3, "output_per_million": 9}
    }
    found = lookup("gemini-4-argon", at("2025-01-01"), overrides)
    assert found.basis == "config_override"
    assert found.source == "factory.toml"
    assert found.family == "gemini"
    rates = (
        found.input_per_million,
        found.cached_input_per_million,
        found.cache_write_per_million,
        found.output_per_million,
    )
    assert rates == (3, None, None, 9)
    assert lookup("google-antigravity/gemini-4-argon", at("2026-12-05"), overrides) == found
    unlisted = lookup(
        "brand-new-model", at("2026-11-04"), {"brand-new-model": {"input_per_million": 1}}
    )
    assert unlisted.basis == "config_override"
    assert lookup("gpt-6.1-sol", at("2026-11-04"), overrides).basis == "table"
    ref = price_ref(found)
    assert ref == {
        "table": None,
        "model": "gemini-4-argon",
        "effectiveFrom": None,
        "effectiveTo": None,
        "source": "factory.toml",
        "basis": "config_override",
    }


def test_overrides_reject_bad_values():
    with pytest.raises(ValueError):
        lookup("gpt-6.1-sol", at("2026-11-04"), {"gpt-6.1-sol": {"input_per_million": -1}})
    with pytest.raises(ValueError):
        lookup("gpt-6.1-sol", at("2026-11-04"), {"gpt-6.1-sol": {"input": 1}})
    with pytest.raises(ValueError):
        lookup(
            "gpt-6.1-sol",
            at("2026-11-04"),
            {
                "openai/gpt-6.1-sol": {"input_per_million": 1},
                "gpt-6.1-sol": {"input_per_million": 2},
            },
        )


def test_price_ref_for_table_entry():
    ref = price_ref(lookup("gemini-4-argon", at("2026-11-10")))
    assert ref == {
        "table": "price-table-v1",
        "model": "gemini-4-argon",
        "effectiveFrom": "2026-11-04",
        "effectiveTo": "2026-11-30",
        "source": "https://ai.google.dev/gemini-api/docs/pricing",
        "basis": "table",
    }
    assert price_ref(None) is None


def test_estimate_applies_cached_rate():
    usage = {"inputTokens": 1_000_000, "cachedInputTokens": 400_000, "outputTokens": 200_000}
    result = estimate(usage, lookup("gpt-6.1-sol", at("2026-11-04")))
    # 600k × 2 + 400k × 0.10 + 200k × 10 = 1.2 + 0.04 + 2.0
    assert result["usd"] == pytest.approx(3.24)
    assert result["upperBound"] is False
    assert result["reason"] is None


def test_estimate_charges_cache_writes_at_write_rate():
    sol = lookup("gpt-6.1-sol", at("2026-11-04"))
    usage = {
        "inputTokens": 1_000_000,
        "cachedInputTokens": 400_000,
        "cacheWriteTokens": 100_000,
        "outputTokens": 200_000,
    }
    # 500k × 2 + 400k × 0.10 + 100k × 2.50 + 200k × 10 = 1.0 + 0.04 + 0.25 + 2.0
    assert estimate(usage, sol) == {"usd": pytest.approx(3.29), "upperBound": False, "reason": None}
    unknown_write = {**usage, "cacheWriteTokens": None}
    assert estimate(unknown_write, sol)["usd"] == pytest.approx(3.24)


def test_estimate_refuses_cache_writes_without_write_rate():
    argon = lookup("gemini-4-argon", at("2026-12-01"))
    writes = {"inputTokens": 1000, "cacheWriteTokens": 200, "outputTokens": 100}
    assert estimate(writes, argon) == {"usd": None, "upperBound": False, "reason": "missing_rate"}
    no_writes = estimate({**writes, "cacheWriteTokens": 0}, argon)
    assert no_writes["usd"] == pytest.approx((1000 * 4 + 100 * 20) / 1e6)


def test_estimate_uses_input_rate_as_upper_bound_when_cache_rate_missing():
    argon = lookup("gemini-4-argon", at("2026-12-01"))
    cached = {"inputTokens": 1000, "cachedInputTokens": 600, "outputTokens": 100}
    result = estimate(cached, argon)
    assert result["usd"] == pytest.approx((1000 * 4 + 100 * 20) / 1e6)
    assert result["upperBound"] is True
    plain = estimate({"inputTokens": 1000, "cachedInputTokens": None, "outputTokens": 100}, argon)
    assert plain["usd"] == pytest.approx(result["usd"])
    assert plain["upperBound"] is False
    missing_key = estimate({"inputTokens": 1000, "outputTokens": 100}, argon)
    assert missing_key == plain


def test_estimate_reports_unknown_cost_reasons():
    usage = {"inputTokens": 10, "cachedInputTokens": 0, "outputTokens": 5}
    assert estimate(usage, None) == {"usd": None, "upperBound": False, "reason": "no_price"}
    assert estimate(usage, entry(output_per_million=None))["reason"] == "missing_rate"
    assert estimate(usage, entry(input_per_million=None))["reason"] == "missing_rate"
    sol = lookup("gpt-6.1-sol", at("2026-11-04"))
    assert estimate(None, sol)["reason"] == "no_usage"
    assert estimate({"inputTokens": None, "outputTokens": 5}, sol)["reason"] == "no_usage"
    assert estimate({"inputTokens": 10, "outputTokens": None}, sol)["reason"] == "no_usage"
    for bad in (
        {"inputTokens": 10, "cachedInputTokens": 11, "outputTokens": 5},
        {"inputTokens": 10, "cachedInputTokens": 6, "cacheWriteTokens": 5, "outputTokens": 5},
        {"inputTokens": 10, "cacheWriteTokens": -1, "outputTokens": 5},
        {"inputTokens": -1, "outputTokens": 5},
        {"inputTokens": "10", "outputTokens": 5},
    ):
        assert estimate(bad, sol) == {"usd": None, "upperBound": False, "reason": "invalid_usage"}
    zero = estimate({"inputTokens": 0, "outputTokens": 0}, sol)
    assert zero == {"usd": 0.0, "upperBound": False, "reason": None}


def test_max_rates_and_missing_prices():
    deck = ["gpt-6.1-sol", "google-antigravity/gemini-4-argon", "gpt-6.1-terra"]
    # 입력 상한은 gpt-6.1-sol의 캐시 쓰기 단가 2.50이다.
    assert max_rates(deck, at("2026-11-20")) == (2.5, 10)
    assert max_rates(deck, at("2026-12-01")) == (4, 20)
    assert missing_prices(deck, at("2026-12-01")) == []
    with_flash = [*deck, "google-antigravity/gemini-3.8-flash", "mystery"]
    assert max_rates(with_flash, at("2027-01-01")) is None
    assert missing_prices([*with_flash, "mystery"], at("2027-01-01")) == ["mystery"]
    overrides = {
        "gemini-3.8-flash": {"input_per_million": 1.5, "output_per_million": 30},
        "mystery": {"input_per_million": 0.5, "output_per_million": 1},
    }
    assert missing_prices(with_flash, at("2027-01-01"), overrides) == []
    assert max_rates(with_flash, at("2027-01-01"), overrides) == (4, 30)
    write_override = {
        "gpt-6.1-sol": {
            "input_per_million": 2,
            "cache_write_per_million": 5,
            "output_per_million": 10,
        }
    }
    assert max_rates(deck, at("2026-12-01"), write_override) == (5, 20)
    assert max_rates([], at("2026-11-04")) is None


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda t: t["entries"][5].update(effectiveFrom="2026-11-30"), "겹친다"),
        (lambda t: t["entries"][2].update(effectiveTo=None), "겹친다"),
        (lambda t: t["entries"][0].update(inputPerMillion=-2), "0 이상"),
        (lambda t: t["entries"][0].update(outputPerMillion="10"), "숫자"),
        (lambda t: t["entries"][0].update(effectiveFrom="2026-02-30"), "없는 날짜"),
        (lambda t: t["entries"][0].update(effectiveFrom="20261104"), "YYYY-MM-DD"),
        (lambda t: t["entries"][4].update(effectiveTo="2026-11-01"), "앞선다"),
        (lambda t: t["entries"][0].update(checkedAt="yesterday"), "YYYY-MM-DD"),
        (lambda t: t["entries"][0].pop("source"), "필드"),
        (lambda t: t["entries"][0].pop("cacheWritePerMillion"), "필드"),
        (lambda t: t["entries"][1].update(cacheWritePerMillion=-1.25), "0 이상"),
        (lambda t: t["entries"][0].update(model="openai/gpt-6.1-sol"), "접두사"),
        (lambda t: t.update(version="price-table-v0"), "version"),
        (lambda t: t.update(currency="KRW"), "USD"),
    ],
)
def test_load_table_rejects_bad_tables(tmp_path, mutate, message):
    data = copy.deepcopy(raw_table())
    assert len(load_table(write_table(tmp_path, data))) == 6
    mutate(data)
    with pytest.raises(ValueError, match=message):
        load_table(write_table(tmp_path, data))


def test_lookup_reads_default_table_once(monkeypatch):
    calls = []
    real = pricing.parse_table
    pricing._default_table.cache_clear()
    monkeypatch.setattr(pricing, "parse_table", lambda data: calls.append(1) or real(data))
    lookup("gpt-6.1-sol", at("2026-11-04"))
    lookup("gpt-6.1-terra", at("2026-11-04"))
    assert calls == [1]
    pricing._default_table.cache_clear()


def test_config_reads_pricing_models(tmp_path):
    assert load_config(tmp_path).pricing == {}
    (tmp_path / "factory.toml").write_text(
        '[pricing.models."google-antigravity/gemini-3.8-flash"]\n'
        "input_per_million = 1.5\n"
        "output_per_million = 12\n"
        '[pricing.models."gpt-6.1-sol"]\n'
        "input_per_million = 2\n"
        "cached_input_per_million = 0\n"
        "cache_write_per_million = 2.5\n"
        "output_per_million = 10\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    assert cfg.pricing == {
        "google-antigravity/gemini-3.8-flash": {
            "input_per_million": 1.5,
            "output_per_million": 12.0,
        },
        "gpt-6.1-sol": {
            "input_per_million": 2.0,
            "cached_input_per_million": 0.0,
            "cache_write_per_million": 2.5,
            "output_per_million": 10.0,
        },
    }
    found = lookup("gemini-3.8-flash", at("2027-03-01"), cfg.pricing)
    assert (found.basis, found.output_per_million) == ("config_override", 12.0)
    sol = lookup("gpt-6.1-sol", at("2026-11-04"), cfg.pricing)
    assert (sol.basis, sol.cache_write_per_million) == ("config_override", 2.5)


@pytest.mark.parametrize(
    "body",
    [
        '[pricing.models."gpt-6.1-sol"]\ninput_per_million = -1\n',
        '[pricing.models."gpt-6.1-sol"]\ncache_write_per_million = -2.5\n',
        '[pricing.models."gpt-6.1-sol"]\ninput_per_million = "2"\n',
        '[pricing.models."gpt-6.1-sol"]\noutput_per_million = true\n',
        '[pricing.models."gpt-6.1-sol"]\ninput_per_milion = 2\n',
        '[pricing]\nmodels = "gpt-6.1-sol"\n',
        '[pricing.models]\n"gpt-6.1-sol" = 2\n',
    ],
)
def test_config_rejects_bad_pricing(tmp_path, body):
    (tmp_path / "factory.toml").write_text(body, encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(tmp_path)
