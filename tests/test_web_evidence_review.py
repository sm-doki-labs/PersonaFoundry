"""G6 evidence sidecar: synthetic data only, no providers or network."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from character_factory_poc.web.gate_items import prompts


def test_evidence_review_uses_displayed_revision(tmp_path):
    for rev in ("pv1", "pv2"):
        folder = tmp_path / "s8-prompts" / rev
        folder.mkdir(parents=True)
        (folder / "prompt-pair.json").write_text(json.dumps({"personaVersion": rev}))
        (folder / "prompt-probe.json").write_text('{"probes": []}')
        review = {"schemaVersion": "evidence-review-v1", "records": [{"id": rev}]}
        (folder / "evidence-review.json").write_text(json.dumps(review))
    items = prompts(tmp_path, "synthetic", "s8-prompts", "pv1")
    assert items["evidenceReview"]["records"] == [{"id": "pv1"}]
    assert "구조 검사" in items["helper"]
    assert "의미" in items["helper"]
    assert "url" not in items["evidenceReview"]


def test_legacy_prompts_have_no_evidence_review(tmp_path):
    folder = tmp_path / "s8-prompts" / "pv1"
    folder.mkdir(parents=True)
    (folder / "prompt-pair.json").write_text("{}")
    items = prompts(tmp_path, "synthetic", "s8-prompts", "pv1")
    assert items.get("evidenceReview") is None


def test_evidence_ui_render_and_decisions():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for the gate UI behavior test")
    script = (
        Path(__file__).resolve().parents[1] / "src/character_factory_poc/web/static/shared/gate.js"
    )
    result = subprocess.run(
        [node, "-e", NODE_TEST, str(script)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


NODE_TEST = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let focused = false;
const ack = {checked: false, focus() { focused = true; }, scrollIntoView() {}};
const nodes = {
  '[data-evidence-reviewed]': ack,
  '[data-prompt-note]': {value: '적용 조건을 좁혀 주세요'},
  '[data-minutes]': {value: '2'}, '[data-reviewer]': {value: 'synthetic'},
  '[data-reasons]': {value: ''}
};
const context = {
  window: {CF_API: {}, addEventListener() {}, localStorage: {setItem() {}}},
  document: {addEventListener() {}, querySelector(s) {return nodes[s] || null;}},
  location: {search: ''}, URLSearchParams
};
let source = fs.readFileSync(process.argv[1], 'utf8');
assert.ok(source.includes('load().then(watch);'));
source = source.replace('load().then(watch);',
  'window.testGate = {state: state, render: renderPrompts, ' +
  'build: buildPrompts, hint: KINDS.prompts.hintFor};');
vm.runInNewContext(source, context);
const gate = context.window.testGate;
const review = {
  schemaVersion: 'evidence-review-v1', status: 'AWAITING_HUMAN',
  records: [{id: 'r1', unit: ['synthetic'], context: '앞선 <맥락>', target: '본인 & 반응',
    next: '상대 다음 반응', followup: '본인 후속 반응', history: '더 이전 대화'}],
  cards: [{section: 'VOICE', trigger: '조건 <img src=x onerror=bad()>', first: '첫 반응',
    shift: '전환', stop: '중단', limit: '한계', evidence: ['r1'],
    rule: '규칙 <script>bad()</script>'}],
  held: [{index: 1, reason: '근거 <부족>'}], stats: {}, packetSha256: 'synthetic', binding: {}
};
const items = {evidenceReview: review, long: {text: 'prompt'}, short: {}, probes: []};
gate.state.items = items;
gate.state.view = {status: 'AWAITING_HUMAN'};
let html = gate.render(items);
assert.equal((html.match(/data-evidence-reviewed/g) || []).length, 1);
assert.ok(html.includes('원문 근거와 적용 조건을 읽고 확인했어요'));
assert.ok(html.includes('<details class="gate-more">'));
for (const text of ['앞선 &lt;맥락&gt;', '본인 &amp; 반응', '상대 다음 반응',
  '본인 후속 반응', '더 이전 대화', '근거 &lt;부족&gt;', '말투', '구조 검사', '의미']) {
  assert.ok(html.includes(text), text);
}
assert.ok(!html.includes('<script>bad()'));
assert.ok(!html.includes('<img src=x'));
assert.ok(html.indexOf('규칙 &lt;script&gt;') < html.indexOf('조건 &lt;img'));
assert.ok(html.indexOf('규칙 &lt;script&gt;') < html.indexOf('대화 표본'));
assert.ok(!html.includes('href="') && !html.includes('download'));
assert.ok(gate.hint({...items, samples: [{turns: [{}]}]}).includes('원문 근거'));
assert.throws(() => gate.build('APPROVE'), /원문 근거/);
assert.equal(focused, true);
for (const decision of ['REQUEST_CHANGES', 'REJECT']) {
  const answer = gate.build(decision);
  assert.equal(answer.decision, decision);
  assert.ok(!('evidenceReviewed' in answer));
  assert.ok(!JSON.stringify(answer).includes('앞선'));
}
ack.checked = true;
assert.equal(gate.build('APPROVE').evidenceReviewed, true);
assert.ok(!('evidenceReviewed' in gate.build('REQUEST_CHANGES')));
assert.ok(!('evidenceReviewed' in gate.build('REJECT')));
ack.checked = 'true';
assert.throws(() => gate.build('APPROVE'), /원문 근거/);
ack.checked = true;
delete nodes['[data-evidence-reviewed]'];
assert.throws(() => gate.build('APPROVE'), /원문 근거/);
nodes['[data-evidence-reviewed]'] = ack;
review.records[0].history = review.records[0].context;
html = gate.render(items);
assert.equal((html.match(/앞선 &lt;맥락&gt;/g) || []).length, 1);
const structuredHistory = [
  {speaker: 'USER', text: '이전 <질문>'},
  {speaker: 'SUBJECT', text: '이전 & 답변'},
  {speaker: 'USER', text: review.records[0].context}
];
review.records[0].history = structuredHistory;
html = gate.render(items);
assert.ok(html.includes('상대: 이전 &lt;질문&gt;'));
assert.ok(html.includes('본인: 이전 &amp; 답변'));
assert.equal((html.match(/앞선 &lt;맥락&gt;/g) || []).length, 1);
assert.ok(!html.includes('[object Object]'));
assert.ok(!html.includes('&quot;speaker&quot;'));
assert.equal(structuredHistory.length, 3, 'render must not mutate source history');
review.records[0].history = [{speaker: 'USER', text: review.records[0].context}];
assert.ok(!gate.render(items).includes('이전 대화'));
review.records[0].history = [{speaker: 'SUBJECT', text: review.records[0].context}];
assert.ok(gate.render(items).includes('본인: 앞선 &lt;맥락&gt;'));
review.records[0].history = [{speaker: 'USER', text: '별개의 맥락'}];
assert.ok(gate.render(items).includes('상대: 별개의 맥락'));
review.records[0].history = '이전 문자열 대화';
assert.ok(gate.render(items).includes('이전 문자열 대화'));
const legacyTraits = [{situation: 'WORRY', behavior: 'S7 추론 표식', refs: []}];
items.inferredTraits = legacyTraits;
assert.ok(!gate.render(items).includes('S7 추론 표식'));
assert.ok(gate.render({inferredTraits: legacyTraits}).includes('S7 추론 표식'));
gate.state.view = {status: 'APPROVED', record: {decision: 'APPROVE'}};
assert.ok(!gate.render(items).includes('data-evidence-reviewed'));
gate.state.view = {status: 'AWAITING_HUMAN'};
gate.state.items = {};
assert.ok(!('evidenceReviewed' in gate.build('APPROVE')));
assert.ok(!gate.render({}).includes('data-evidence-reviewed'));
"""
