"""시험 경로 2번: 순위 → 두 모델 교차 태깅 → 외모군 → 베이스 시드 후보(GPT Image 2.6).

단계마다 결과 파일을 남기고, 이미 있는 파일은 다시 만들지 않는다(중간에 멈춰도 이어서 돈다).
"""

from __future__ import annotations

import html
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from character_factory_poc.common import pricing
from character_factory_poc.common.names import find_name_leaks
from character_factory_poc.providers.base import TextModel
from character_factory_poc.stages.s1_reference.ranking import all_names, build_people, load_ranking
from character_factory_poc.testpath import clusters as cl
from character_factory_poc.testpath import tagging
from character_factory_poc.testpath.image_api import ImageApiError, OpenAIImagesClient
from character_factory_poc.testpath.seed_prompts import build_seed_prompt
from character_factory_poc.testpath.vocab2 import load_vocab2, phrase

STEPS = ("people", "tags", "clusters", "prompts", "images")
# 계열: openai·gemini는 공식 API, relay는 opencodex 중계(공장 기본 경로).
TAG_MODELS = {"gpt": ("openai", "gpt-6.1-sol"), "gemini": ("gemini", "gemini-4-argon")}
RELAY = {"base_url": "http://127.0.0.1:10100/v1", "api_key_env": ""}


@dataclass
class SeedRunConfig:
    run_dir: Path
    total: int = 10
    max_clusters: int = 5
    min_members: int = 3
    gender: str = "female"
    origin: str = "Korean"
    batch_size: int = 8
    image_size: str = "1024x1536"
    image_quality: str = "high"
    image_workers: int = 5
    look: str = "candid"
    signatures: bool = False
    tag_models: dict[str, tuple[str, str]] = field(default_factory=lambda: dict(TAG_MODELS))


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _names(cfg: SeedRunConfig) -> list[str]:
    return all_names(load_ranking(_read(cfg.run_dir / "ranking" / "ranking.json")))


# 1. 인물 묶기 ------------------------------------------------------------------------------
def step_people(cfg: SeedRunConfig) -> Path:
    out = cfg.run_dir / "people.json"
    if out.exists():
        return out
    ranking = load_ranking(_read(cfg.run_dir / "ranking" / "ranking.json"))
    people = build_people(ranking, min_list_size=5)
    rows = []
    for p in people.people:
        pcts = [a.percentile for a in p.appearances if a.percentile is not None]
        rows.append(
            {
                "personId": p.personId,
                "name": p.name,
                "lists": [a.listId for a in p.appearances],
                "popularity": max(pcts) if pcts else None,
            }
        )
    _write(out, {"rankingSha256": people.rankingSha256, "people": rows, "createdAt": _now()})
    return out


# 2. 교차 태깅 ------------------------------------------------------------------------------
def _cost(model: str, usage: dict | None) -> float | None:
    entry = pricing.lookup(model, datetime.now(UTC))
    return pricing.estimate(usage, entry)["usd"]


def _tag_batch(
    model_key: str, model: TextModel, batch_no: int, people: list[dict], vocab, out_dir: Path
) -> dict:
    path = out_dir / model_key / f"batch-{batch_no:02d}.json"
    if path.exists():
        return _read(path)
    roster = [{"personId": p["personId"], "name": p["name"]} for p in people]
    attempts = []
    parsed: dict | None = None
    problems: list[str] = []
    for attempt in range(2):
        req = tagging.build_request(roster, vocab, ref=f"{model_key}-b{batch_no}-a{attempt}")
        resp = model.complete(req)
        attempts.append(
            {
                "model": resp.model,
                "usage": resp.usage,
                "elapsedMs": resp.elapsed_ms,
                "finish": resp.finish_reason,
                "usd": _cost(getattr(model, "model", resp.model), resp.usage),
            }
        )
        try:
            parsed, problems = tagging.parse_tags(resp.text, roster, vocab)
            raw = resp.text
            break
        except (ValueError, json.JSONDecodeError) as e:
            problems = [f"형식 오류: {e}"]
            raw = resp.text
    record = {
        "model": model_key,
        "batch": batch_no,
        "personIds": [p["personId"] for p in people],
        "attempts": attempts,
        "parsed": parsed or {},
        "problems": problems,
        "raw": raw,
    }
    # 원문은 이름 없이 personId로만 답하라고 했지만 혹시 섞이면 기록에서 지운다.
    leaks = find_name_leaks(raw, [p["name"] for p in people])
    if leaks:
        record["raw"] = "(이름이 섞여 원문을 저장하지 않았다)"
        record["problems"].append(f"원문에 이름 {len(leaks)}개가 섞였다")
    _write(path, record)
    return record


def step_tags(cfg: SeedRunConfig, models: dict[str, TextModel]) -> Path:
    out = cfg.run_dir / "tags-merged.json"
    if out.exists():
        return out
    vocab = load_vocab2()
    people = _read(cfg.run_dir / "people.json")["people"]
    batches = [people[i : i + cfg.batch_size] for i in range(0, len(people), cfg.batch_size)]
    jobs = [(mk, m, bi, b) for mk, m in models.items() for bi, b in enumerate(batches, 1)]
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        records = list(
            pool.map(
                lambda j: _tag_batch(j[0], j[1], j[2], j[3], vocab, cfg.run_dir / "tagging"), jobs
            )
        )
    by_model: dict[str, dict] = {k: {} for k in models}
    usd = 0.0
    for r in records:
        by_model[r["model"]].update(r["parsed"])
        usd += sum(a["usd"] or 0 for a in r["attempts"])
    keys = list(models)
    merged, stats = tagging.cross_check(
        by_model[keys[0]], by_model[keys[1]], vocab, gender=cfg.gender
    )
    stats["models"] = {k: cfg.tag_models[k][1] for k in keys}
    stats["textUsd"] = round(usd, 4)
    stats["problems"] = [p for r in records for p in r["problems"]]
    _write(out, {"merged": merged, "stats": stats, "createdAt": _now()})
    return out


# 3. 외모군 --------------------------------------------------------------------------------
def step_clusters(cfg: SeedRunConfig) -> Path:
    out = cfg.run_dir / "clusters.json"
    if out.exists():
        return out
    vocab = load_vocab2()
    tagged = _read(cfg.run_dir / "tags-merged.json")
    merged = tagged["merged"]
    fields = cl.basis_fields(vocab, tagged["stats"]["agreement"])
    pop = {p["personId"]: p["popularity"] for p in _read(cfg.run_dir / "people.json")["people"]}
    usable = {pid: e for pid, e in merged.items() if cl.usable(e, fields)}
    vectors = {pid: cl.vectorize(e, vocab, fields) for pid, e in usable.items()}
    k, groups = cl.best_partition(vectors, min_members=cfg.min_members)
    profiles, small = [], []
    for g in sorted(groups, key=lambda g: (-len(g), g)):
        if len(g) >= cfg.min_members:
            profiles.append(cl.profile(f"c{len(profiles) + 1}", g, usable, pop, vocab))
        else:
            small.append(g)
    alloc = cl.allocate(cfg.total, profiles, cfg.max_clusters)
    _write(
        out,
        {
            "k": k,
            "basisFields": fields,
            "usablePeople": len(usable),
            "excludedPeople": sorted(set(merged) - set(usable)),
            "smallGroups": small,
            "clusters": profiles,
            "allocation": [{"clusterId": c["clusterId"], "count": n} for c, n in alloc],
            "createdAt": _now(),
        },
    )
    return out


# 4. 프롬프트 ------------------------------------------------------------------------------
def step_prompts(cfg: SeedRunConfig) -> Path:
    out = cfg.run_dir / "seeds" / "plan.json"
    if out.exists():
        return out
    vocab = load_vocab2()
    data = _read(cfg.run_dir / "clusters.json")
    by_id = {c["clusterId"]: c for c in data["clusters"]}
    seeds = []
    for a in data["allocation"]:
        c = by_id[a["clusterId"]]
        for v in range(a["count"]):
            sig = None
            if cfg.signatures:
                pool = vocab["signatureFeatures"]["values"]
                sig = pool[len(seeds) % len(pool)]
            prompt, tags = build_seed_prompt(
                c, v, vocab, origin=cfg.origin, look=cfg.look, signature=sig
            )
            seeds.append(
                {
                    "seedId": f"s{len(seeds) + 1:02d}",
                    "clusterId": c["clusterId"],
                    "variant": v,
                    "tags": tags,
                    "prompt": prompt,
                }
            )
    names = _names(cfg)
    leaks = sorted({n for s in seeds for n in find_name_leaks(s["prompt"], names)})
    leaks += sorted({n for c in data["clusters"] for n in find_name_leaks(c["label"], names)})
    if leaks:
        raise RuntimeError(f"프롬프트·외모군 이름에 순위 인물 이름 {len(leaks)}개가 섞였다. 멈춘다")
    _write(
        out,
        {
            "model": "gpt-image-2.6-sunburst",
            "size": cfg.image_size,
            "quality": cfg.image_quality,
            "look": cfg.look,
            "signatures": cfg.signatures,
            "seeds": seeds,
            "createdAt": _now(),
        },
    )
    return out


# 5. 이미지 --------------------------------------------------------------------------------
def step_images(cfg: SeedRunConfig, client: OpenAIImagesClient) -> Path:
    plan = _read(cfg.run_dir / "seeds" / "plan.json")
    img_dir = cfg.run_dir / "seeds" / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    def one(seed: dict) -> dict:
        png = img_dir / f"{seed['seedId']}.png"
        meta = img_dir / f"{seed['seedId']}.json"
        if png.exists() and meta.exists():
            return _read(meta)
        try:
            res = client.generate(seed["prompt"], size=plan["size"], quality=plan["quality"])
        except ImageApiError as e:
            rec = {"seedId": seed["seedId"], "ok": False, "error": str(e)[:600], "at": _now()}
            _write(meta.with_suffix(".error.json"), rec)
            return rec
        png.write_bytes(res.data)
        rec = {
            "seedId": seed["seedId"],
            "ok": True,
            "file": png.name,
            "bytes": len(res.data),
            "elapsedMs": res.elapsed_ms,
            "usage": res.usage,
            "model": client.model,
            "at": _now(),
        }
        _write(meta, rec)
        return rec

    with ThreadPoolExecutor(max_workers=cfg.image_workers) as pool:
        results = list(pool.map(one, plan["seeds"]))
    out = cfg.run_dir / "seeds" / "manifest.json"
    _write(out, {"results": results, "createdAt": _now()})
    write_gallery(cfg)
    return out


def write_gallery(cfg: SeedRunConfig) -> Path:
    vocab = load_vocab2()
    plan = _read(cfg.run_dir / "seeds" / "plan.json")
    data = _read(cfg.run_dir / "clusters.json")
    by_id = {c["clusterId"]: c for c in data["clusters"]}
    cards = []
    for s in plan["seeds"]:
        c = by_id[s["clusterId"]]
        img = cfg.run_dir / "seeds" / "images" / f"{s['seedId']}.png"
        keys = (
            "faceShape",
            "eyelid",
            "eyeTail",
            "noseBridge",
            "lipShape",
            "hairStyle",
            "bangs",
            "makeup",
        )
        tags = " · ".join(phrase(vocab, k, s["tags"][k], "ko") for k in keys if k in s["tags"])
        sig = {x["key"]: x["ko"] for x in vocab.get("signatureFeatures", {}).get("values", [])}
        if s["tags"].get("signature") in sig:
            tags = f"[{sig[s['tags']['signature']]}] " + tags
        src = f"images/{img.name}" if img.exists() else ""
        body = (
            f'<img src="{src}" alt="{s["seedId"]}">' if src else '<div class="miss">생성 실패</div>'
        )
        cards.append(
            f"<figure>{body}<figcaption><b>{s['seedId']}</b> · {html.escape(c['label'])}"
            f"<br><small>{html.escape(tags)}</small></figcaption></figure>"
        )
    page = (
        '<!doctype html><meta charset="utf-8"><title>베이스 시드 후보</title>'
        "<style>body{font-family:-apple-system,sans-serif;margin:24px;background:#f6f6f7}"
        "main{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px}"
        "figure{margin:0;background:#fff;border-radius:12px;overflow:hidden;"
        "border:1px solid #e3e3e6}"
        "img{width:100%;display:block}figcaption{padding:8px 10px;font-size:13px;line-height:1.4}"
        "small{color:#666}.miss{aspect-ratio:2/3;display:grid;place-items:center;color:#b00}</style>"
        f"<h1>베이스 시드 후보 {len(plan['seeds'])}장</h1><main>{''.join(cards)}</main>"
    )
    out = cfg.run_dir / "seeds" / "gallery.html"
    out.write_text(page, encoding="utf-8")
    return out


def contact_sheet(cfg: SeedRunConfig) -> Path | None:
    """ffmpeg로 5열 밑그림 한 장을 만든다(검토용). ffmpeg가 없으면 건너뛴다."""
    imgs = sorted((cfg.run_dir / "seeds" / "images").glob("s*.png"))
    if not imgs:
        return None
    out = cfg.run_dir / "seeds" / "contact-sheet.jpg"
    cols = 5
    rows = (len(imgs) + cols - 1) // cols
    inputs: list[str] = []
    for p in imgs:
        inputs += ["-i", str(p)]
    scaled = "".join(f"[{i}:v]scale=320:480[v{i}];" for i in range(len(imgs)))
    layout = "|".join(f"{(i % cols) * 320}_{(i // cols) * 480}" for i in range(len(imgs)))
    filt = (
        scaled
        + "".join(f"[v{i}]" for i in range(len(imgs)))
        + f"xstack=inputs={len(imgs)}:layout={layout}:fill=white"
    )
    if len(imgs) == 1:
        filt = "[0:v]scale=320:480"
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                *inputs,
                "-filter_complex",
                filt,
                "-frames:v",
                "1",
                str(out),
            ],
            check=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    _ = rows
    return out


def summary(cfg: SeedRunConfig) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if (cfg.run_dir / "tags-merged.json").exists():
        st = _read(cfg.run_dir / "tags-merged.json")["stats"]
        out["tagging"] = {
            "kept": st["kept"],
            "dropped": len(st["dropped"]),
            "textUsd": st.get("textUsd"),
        }
    if (cfg.run_dir / "clusters.json").exists():
        d = _read(cfg.run_dir / "clusters.json")
        out["clusters"] = [
            {
                "id": c["clusterId"],
                "label": c["label"],
                "n": c["memberCount"],
                "popularity": c["popularity"],
            }
            for c in d["clusters"]
        ]
        out["allocation"] = d["allocation"]
    if (cfg.run_dir / "seeds" / "manifest.json").exists():
        res = _read(cfg.run_dir / "seeds" / "manifest.json")["results"]
        out["images"] = {
            "ok": sum(1 for r in res if r.get("ok")),
            "failed": [r["seedId"] for r in res if not r.get("ok")],
        }
    return out
