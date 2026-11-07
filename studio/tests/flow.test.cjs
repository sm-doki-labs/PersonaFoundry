'use strict';
// 진행 화면(flow.js)의 순수 함수 검사. 실제 서버 그래프(_graph)를 그대로 쓴다. 네트워크·브라우저 없음.
const test = require('node:test');
const assert = require('node:assert/strict');
const Runtime = require('../shared/runtime.js');
const Flow = require('../shared/flow.js');


test('Foundry tokens are the same file for the studio and the gate page, and the gate uses them only inside the review sheet', () => {
  const fs = require('node:fs');
  const path = require('node:path');
  const studio = fs.readFileSync(path.join(__dirname, '..', 'shared', 'foundry-tokens.css'), 'utf8');
  const staticDir = path.join(__dirname, '..', '..', 'src', 'character_factory_poc', 'web', 'static');
  assert.equal(fs.readFileSync(path.join(staticDir, 'shared', 'foundry-tokens.css'), 'utf8'), studio);
  for (const name of ['--fd-bg-app', '--fd-fg', '--fd-accent', '--fd-run-solid', '--fd-attention-fg', '--fd-danger-fg', '--fd-success-fg']) {
    assert.ok(studio.includes(name + ':'), name);
  }
  assert.ok(studio.includes('[data-fd-theme="dark"]'));
  const gate = fs.readFileSync(path.join(staticDir, 'gate.html'), 'utf8');
  assert.ok(gate.includes('shared/gate-foundry.css') && gate.includes("get('skin') !== 'foundry'"));
  const gateCss = fs.readFileSync(path.join(staticDir, 'shared', 'gate-foundry.css'), 'utf8');
  const rules = gateCss.replace(/\/\*[\s\S]*?\*\//g, '').split('}').map((r) => r.trim()).filter((r) => r && !r.startsWith('@media'));
  assert.ok(rules.every((r) => /^body\.fd/.test(r) || /^body\.fd/.test(r.split('{')[0].trim().replace(/^@media[^{]*\{/, '').trim())), 'every gate rule is scoped to body.fd');
  const page = fs.readFileSync(path.join(__dirname, '..', 'factory.html'), 'utf8');
  assert.ok(page.indexOf('foundry-tokens.css') < page.indexOf('flow.css'));
  assert.ok(Flow.MARK.includes('var(--fd-accent)'));
});

const RAW = {"stages": [{"id": "s1", "name": "레퍼런스 선별", "deps": [], "needs": [], "after": [], "gate": "G1", "implemented": true, "paid": []}, {"id": "s2", "name": "기준 사진", "deps": ["G1"], "needs": [], "after": [], "gate": null, "implemented": true, "paid": []}, {"id": "s3", "name": "캐릭터 기획", "deps": [], "needs": [], "after": [], "gate": "G3", "implemented": true, "paid": []}, {"id": "s5", "name": "소개 영상", "deps": [], "needs": ["s2"], "after": [], "gate": "G5", "implemented": true, "paid": ["video: xai_video/grok-video"]}, {"id": "s3r", "name": "참고 자료 선별", "deps": ["G3"], "needs": [], "after": [], "gate": null, "implemented": true, "paid": []}, {"id": "s4a", "name": "챕터 배경 후보", "deps": ["G3"], "needs": ["s2"], "after": [], "gate": "G4a", "implemented": true, "paid": []}, {"id": "s4b", "name": "장면 사실·자세 후보", "deps": ["G4a"], "needs": [], "after": [], "gate": "G4b", "implemented": true, "paid": []}, {"id": "s4", "name": "챕터 완성 이미지", "deps": ["G4b"], "needs": ["s2"], "after": [], "gate": "G4", "implemented": true, "paid": []}, {"id": "s6", "name": "동작 영상", "deps": ["G4"], "needs": [], "after": [], "gate": "G5b", "implemented": true, "paid": ["video: xai_video/grok-video"]}, {"id": "s7", "name": "상세 특질", "deps": ["G3"], "needs": [], "after": [], "gate": null, "implemented": true, "paid": []}, {"id": "s8", "name": "프롬프트", "deps": ["G3"], "needs": [], "after": ["s7"], "gate": "G6", "implemented": true, "paid": []}, {"id": "s9s", "name": "데이터 샘플", "deps": ["G6"], "needs": [], "after": [], "gate": "G7a", "implemented": true, "paid": []}, {"id": "s9", "name": "학습 데이터", "deps": ["G7a"], "needs": [], "after": [], "gate": "G7", "implemented": true, "paid": []}, {"id": "s10t", "name": "SFT 학습", "deps": ["G7"], "needs": [], "after": [], "gate": null, "implemented": true, "paid": []}, {"id": "s10", "name": "평가", "deps": ["G7"], "needs": [], "after": ["s10t"], "gate": "G8", "implemented": true, "paid": []}, {"id": "s11", "name": "릴리즈 패키지", "deps": ["G4", "G5", "G5b", "G6", "G8"], "needs": [], "after": [], "gate": "G9", "implemented": true, "paid": []}, {"id": "sx", "name": "우리 앱 내보내기", "deps": ["G9"], "needs": [], "after": [], "gate": null, "implemented": true, "paid": []}], "gates": [{"id": "G1", "title": "얼굴 고르기", "stage": "s1"}, {"id": "G3", "title": "기획안 고르기", "stage": "s3"}, {"id": "G4a", "title": "챕터 배경 고르기", "stage": "s4a"}, {"id": "G4b", "title": "장면·자세 고르기", "stage": "s4b"}, {"id": "G4", "title": "완성 이미지 승인", "stage": "s4"}, {"id": "G5", "title": "소개 영상 고르기", "stage": "s5"}, {"id": "G5b", "title": "동작 영상 고르기", "stage": "s6"}, {"id": "G6", "title": "프롬프트 승인", "stage": "s8"}, {"id": "G7a", "title": "데이터 샘플 검토", "stage": "s9s"}, {"id": "G7", "title": "데이터셋 승인", "stage": "s9"}, {"id": "G8", "title": "평가·블라인드 20쌍", "stage": "s10"}, {"id": "G9", "title": "패키지 승인", "stage": "s11"}], "mode": "live", "lanes": [{"id": "appearance", "label": "외모", "stages": ["s1", "s2"]}, {"id": "plan", "label": "기획", "stages": ["s3", "s3r"]}, {"id": "scene", "label": "장면", "stages": ["s4a", "s4b", "s4"]}, {"id": "video", "label": "영상", "stages": ["s5", "s6"]}, {"id": "persona", "label": "페르소나", "stages": ["s7", "s8"]}, {"id": "data", "label": "데이터", "stages": ["s9s", "s9"]}, {"id": "training", "label": "학습", "stages": ["s10t", "s10"]}, {"id": "release", "label": "패키지", "stages": ["s11", "sx"]}]};
const graph = Runtime.buildGraph(RAW);
const NOW = Date.parse('2026-11-07T05:42:00Z');

function stage(id, status, extra) { return Object.assign({ id, status, attempts: status === 'PENDING' ? 0 : 1 }, extra || {}); }
function detail(stages, gates, extra) {
  return Object.assign({ id: 'c1', stages, gates: gates || [], pendingGates: (gates || []).filter((g) => g.status === 'AWAITING_HUMAN'), history: {}, held: [], jobs: [{}] }, extra || {});
}
const ALL = RAW.stages.map((s) => s.id);
function rows(map) { return ALL.map((id) => stage(id, map[id] || 'PENDING', typeof map[id + ':x'] === 'object' ? map[id + ':x'] : undefined)); }

test('only direct cross-team links remain, matching the reviewed design', () => {
  const edges = Flow.crossLaneEdges(graph).map((e) => e.join('>')).sort();
  assert.deepEqual(edges, ['s10>s11', 's2>s4a', 's2>s5', 's3>s4a', 's3>s7', 's4>s6', 's5>s11', 's6>s11', 's8>s9s', 's9>s10t'].sort());
});

test('target scope follows real dependencies', () => {
  assert.deepEqual([...Flow.ancestors(graph, 'G6')].sort(), ['s3', 's7', 's8']);
  const all = Flow.ancestors(graph, 'sx');
  assert.equal(all.size, ALL.length - 1, 's3r is not needed for export');
  assert.ok(!all.has('s3r'));
});

test('stage rows read waiting time, retries, rework, failures and held paid steps', () => {
  const d = detail(rows({
    s3: 'APPROVED', s7: 'APPROVED', s8: 'AWAITING_HUMAN', s4b: 'RUNNING', s5: 'RUNNING', s4a: 'CHECK_FAILED', s3r: 'RUNNING'
  }), [{ id: 'G6', status: 'AWAITING_HUMAN', rev: 'pv1', openedAt: '2026-11-07T05:24:00Z' }], {
    held: ['s6'],
    history: { s3r: [{ decision: 'REJECTED' }, { decision: null }] }
  });
  d.stages.find((s) => s.id === 's5').attempts = 2;
  d.stages.find((s) => s.id === 's4b').startedAt = '2026-11-07T05:27:00Z';
  const v = Flow.viewsFor(graph, d, { now: NOW });
  assert.equal(v.s8.kind, 'wait');
  assert.equal(v.s8.sub, '18분째 검토 대기');
  assert.equal(v.s4b.kind, 'run');
  assert.equal(v.s4b.sub, '실행 중 · 15분째');
  assert.equal(v.s5.kind, 'retry');
  assert.equal(v.s4a.kind, 'fail');
  assert.equal(v.s6.kind, 'confirm');
  assert.equal(v.s3r.sub, '새 버전 만드는 중');
  assert.equal(Flow.laneKind(['s7', 's8'], v), 'wait');
  assert.equal(Flow.edgeClass(graph, v, 's8', 's9s'), 'block');
  assert.equal(Flow.edgeClass(graph, v, 's2', 's5'), 'flow');
});

test('tasks put failures first, then reviews by how much they block, then paid confirmations', () => {
  const d = detail(rows({ s3: 'APPROVED', s7: 'APPROVED', s8: 'AWAITING_HUMAN', s1: 'APPROVED', s2: 'APPROVED', s5: 'AWAITING_HUMAN', s3r: 'CHECK_FAILED' }), [
    { id: 'G5', status: 'AWAITING_HUMAN', rev: 'iv1', openedAt: '2026-11-07T05:40:00Z' },
    { id: 'G6', status: 'AWAITING_HUMAN', rev: 'pv1', openedAt: '2026-11-07T05:24:00Z' }
  ], { held: [{ stage: 's4a', providers: ['image: x/y'] }] });
  d.stages.find((s) => s.id === 's3r').lastError = '참고 자료 형식 오류';
  const v = Flow.viewsFor(graph, d, { now: NOW });
  const reviews = new Map([['G6|pv1', { review: { items: [{ candidateId: 'pv1-b', verdict: 'RECOMMEND' }] }, rework: { round: 3, maxRounds: 3, capReached: true } }]]);
  const tasks = Flow.buildTasks(graph, d, v, { now: NOW, gateViews: reviews, jobActive: true });
  assert.deepEqual(tasks.map((t) => t.kind + ':' + t.stage), ['fail:s3r', 'wait:s8', 'wait:s5', 'confirm:s4a']);
  assert.equal(tasks[0].body.startsWith('참고 자료 형식 오류'), true);
  assert.match(tasks[0].body, /이 단계부터 목표까지 이어서/);
  assert.equal(tasks[0].actions[0].disabled, true, 'no second job while one runs');
  assert.equal(tasks[1].rec, '검토 모델 추천: pv1-b');
  assert.match(tasks[1].body, /3번을 모두 썼어요/);
  assert.equal(tasks[1].blocked > tasks[2].blocked, true);
  assert.equal(tasks.filter((t) => t.actions.some((a) => a.pri)).length, 1, 'one primary action');
});

test('failure reasons are plain sentences, repeated failures offer a copy for the owner, and idle ready stages surface', () => {
  const fmt = Flow.failReason('profiler: 형식 실패 3회: characterId: Field required');
  assert.equal(fmt.summary, '모델 답이 정해진 형식과 맞지 않았어요. 마지막 실행 안에서 모델에 3번 다시 물었지만 맞지 않았어요.');
  assert.match(fmt.detail, /Field required/);
  const chk = Flow.failReason('S7 자동 검사 실패(3회):\n- card.expressedTraits.core: 기획서의 핵심 성격이 하나도 언급되지 않았다');
  assert.equal(chk.summary, '자동 검사를 통과하지 못했어요: 기획서의 핵심 성격이 하나도 언급되지 않았다');
  assert.equal(Flow.failReason('').detail, '');

  const twice = detail(rows({ s3r: 'CHECK_FAILED' }), []);
  const row = twice.stages.find((s) => s.id === 's3r');
  row.attempts = 2;
  row.lastError = 'x: 형식 실패 3회: y';
  const tv = Flow.viewsFor(graph, twice, { now: NOW });
  assert.equal(tv.s3r.sub, '실행 2번 실패 · 멈춤');
  const fail = Flow.buildTasks(graph, twice, tv, { now: NOW })[0];
  assert.equal(fail.age, '실행 2번 실패');
  assert.deepEqual(fail.actions.map((a) => a.act), ['copy-error', 'help', 'retry']);
  assert.match(fail.body, /운영 담당에게/);

  const idle = detail(rows({ s1: 'APPROVED', s2: 'APPROVED', s3: 'APPROVED', s3r: 'SKIPPED' }), []);
  const iv = Flow.viewsFor(graph, idle, { now: NOW });
  const ready = Flow.buildTasks(graph, idle, iv, { now: NOW, goal: 'sx' }).find((x) => x.kind === 'ready');
  assert.ok(ready, 'a stage whose predecessors are done but nothing runs is offered to continue');
  assert.match(ready.body, /상세 특질/);
  assert.equal(ready.actions[0].act, 'resume');
  assert.equal(Flow.buildTasks(graph, idle, iv, { now: NOW, goal: 'sx', jobActive: true }).some((x) => x.kind === 'ready'), false);
  idle.lastJob = { status: 'succeeded', blocked: ['s7'] };
  const blockedReady = Flow.buildTasks(graph, idle, iv, { now: NOW, goal: 'sx' }).find((x) => x.kind === 'ready');
  assert.equal(Boolean(blockedReady && /상세 특질/.test(blockedReady.body)), false, 'stages the server reported as blocked are not offered');

  const recovered = Flow.diffNotes(graph, detail(rows({ s3r: 'CHECK_FAILED' }), []), detail(rows({ s3r: 'APPROVED' }), []), NOW);
  assert.equal(recovered.some((n) => /다시 실행해 통과했어요/.test(n.t)), true);
});

test('decisions and newly started steps become one note', () => {
  const before = detail(rows({ s8: 'AWAITING_HUMAN' }), [{ id: 'G6', status: 'AWAITING_HUMAN' }]);
  const after = detail(rows({ s8: 'APPROVED', s9s: 'RUNNING' }), [{ id: 'G6', status: 'APPROVED' }]);
  const notes = Flow.diffNotes(graph, before, after, NOW);
  assert.equal(notes.length, 1);
  assert.equal(notes[0].t, '프롬프트 승인: 결정을 기록했어요.');
  assert.equal(notes[0].s, '데이터 샘플 단계를 시작했어요.');
  const reworked = Flow.diffNotes(graph, before, detail(rows({ s8: 'REJECTED' }), [{ id: 'G6', status: 'REJECTED' }]), NOW);
  assert.match(reworked[0].t, /다시 만들도록 보냈어요/);
});

test('out-of-scope stages and their links are faded before the first run', () => {
  const d = detail(rows({}), [], { jobs: [] });
  const v = Flow.viewsFor(graph, d, { now: NOW, scope: Flow.ancestors(graph, 'G6') });
  assert.equal(v.s8.kind, 'todo');
  assert.equal(v.s4a.kind, 'out');
  assert.equal(Flow.edgeClass(graph, v, 's8', 's9s'), 'out');
  assert.equal(Flow.targetLabel(graph, 'G6'), '프롬프트 승인까지');
  assert.equal(Flow.targetLabel(graph, 'sx'), '끝까지');
});
