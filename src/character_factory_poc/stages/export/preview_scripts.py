"""미리보기 발행이 chat-svc 저장소 가상환경 안에서 돌리는 컴파일 조각.

공장은 chat-svc 코드를 import 하지 않는다(pg_admin 과 같은 원칙). 아래 문자열을 dev 배포 판 chat-svc
체크아웃의 python 으로 실행한다. 요청은 표준입력 JSON, 결과는 표준출력 JSON 한 줄이다. DB 에는 붙지 않는다.

저장소 data/ 위에 공장 조각을 얹은 트리를 chat-svc 컴파일러(content_cli.publish._compile)로 컴파일하고,
이 캐릭터의 버전·소속만 넣기 API(backoffice factory-import) 모양으로 돌려준다.
"""

from __future__ import annotations

CHAT_COMPILE_SCRIPT = r"""
import json, sys
from pathlib import Path
from relationship_quest_chat.content_cli import publish as publisher
from relationship_quest_chat.domain.content.aggregates import (
    CompiledReleaseChapter,
    CompiledReleaseCharacter,
    GenerationModelConfigSelection,
)

req = json.loads(sys.stdin.read())
uid = req["characterUid"]
compiled = publisher._compile(Path(req["dataDir"]), GenerationModelConfigSelection.application_policy())
problems = []
for check in ("_reject_incomplete_locales", "_reject_shared_default_locale_content", "_reject_structural_mismatches"):
    fn = getattr(publisher, check, None)
    if fn is None:
        continue
    try:
        fn(compiled)
    except Exception as exc:
        problems.append(f"{check}: {str(exc)[:300]}")

chars = [m for m in compiled.memberships if isinstance(m, CompiledReleaseCharacter) and str(m.character_uid) == uid]
chaps = [m for m in compiled.memberships if isinstance(m, CompiledReleaseChapter) and str(m.character_uid) == uid]
char_revs = {m.character_revision for m in chars}
chap_keys = {(str(m.chapter_uid), m.chapter_revision) for m in chaps}
gen_revs = {m.generation_profile_revision for m in chaps}
out = {
    "characterVersions": [
        {
            "characterUid": str(c.character_uid), "revision": c.revision, "slug": c.character_slug,
            "name": c.name, "tagline": c.tagline, "displayOrder": c.display_order,
            "persona": c.persona, "payloadHash": c.payload_hash,
        }
        for c in compiled.characters if str(c.character_uid) == uid and c.revision in char_revs
    ],
    "chapterVersions": [
        {
            "chapterUid": str(c.chapter_uid), "revision": c.revision,
            "sourceChapterRevision": c.source_chapter_revision, "slug": c.chapter_slug,
            "number": c.number, "title": c.title, "goal": c.goal, "turnLimit": c.turn_limit,
            "entryStage": c.entry_stage, "kernelReady": c.kernel_ready,
            "payload": c.payload, "payloadHash": c.payload_hash,
        }
        for c in compiled.chapters if (str(c.chapter_uid), c.revision) in chap_keys
    ],
    "generationProfiles": [
        {"revision": g.revision, "payload": g.payload, "payloadHash": g.payload_hash}
        for g in compiled.generation_profiles if g.revision in gen_revs
    ],
    "releaseCharacters": [
        {"characterUid": str(m.character_uid), "locale": m.locale,
         "characterRevision": m.character_revision, "displayOrder": m.display_order}
        for m in chars
    ],
    "releaseChapters": [
        {"characterUid": str(m.character_uid), "chapterUid": str(m.chapter_uid), "locale": m.locale,
         "chapterRevision": m.chapter_revision, "generationProfileRevision": m.generation_profile_revision,
         "number": m.number}
        for m in chaps
    ],
}
sys.stdout.write(json.dumps({"content": out, "problems": problems}, ensure_ascii=False, default=str))
"""

__all__ = ["CHAT_COMPILE_SCRIPT"]
