'use strict';
// 모티브 갈래 진행 화면 검사. 그래프는 서버 _graph 출력(fixtures, tests/test_web_twin_lanes.py가 같은지 확인)을 쓴다.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Runtime = require('../shared/runtime.js');
const Flow = require('../shared/flow.js');

const load = (mode) => JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'twin-graph-' + mode + '.json'), 'utf8'));
const TRAIN = load('TRAIN');
const PROMPT = load('PROMPT_ONLY');
const BIND = load('BIND_EXISTING');
const NOW = Date.parse('2026-11-08T05:00:00Z');
const laneIds = (raw) => raw.lanes.map((l) => l.id);
const edges = (raw) => Flow.crossLaneEdges(Runtime.buildGraph(raw)).map((e) => e.join('>')).sort();
function detailFor(raw, map, gates) {
  return {
    id: 'tw', origin: raw.origin, modelMode: raw.modelMode,
    stages: raw.stages.map((s) => ({ id: s.id, status: map[s.id] || 'PENDING', attempts: map[s.id] ? 1 : 0 })),
    gates, pendingGates: gates.filter((g) => g.status === 'AWAITING_HUMAN'), history: {}, held: [], jobs: [{}]
  };
}

test('the graph request names the character; without one it is the original default', () => {
  assert.equal(Runtime.graphPath(), '/api/runtime/graph');
  assert.equal(Runtime.graphPath('cf-20261108-a b'), '/api/runtime/graph?character_id=cf-20261108-a%20b');
});

test('twin teams: source team first, no s1, s9h sits with evaluation, and no-training modes drop the data team', () => {
  for (const raw of [TRAIN, PROMPT, BIND]) {
    assert.equal(raw.lanes[0].id, 'source');
    assert.deepEqual(raw.lanes[0].stages, ['s0']);
    assert.deepEqual(raw.lanes.find((l) => l.id === 'appearance').stages, ['s2']);
    assert.ok(raw.lanes.find((l) => l.id === 'training').stages.includes('s9h'));
    assert.ok(!raw.stages.some((s) => s.id === 's1'));
  }
  assert.deepEqual(laneIds(TRAIN), ['source', 'appearance', 'plan', 'scene', 'video', 'persona', 'data', 'training', 'release']);
  assert.deepEqual(laneIds(PROMPT), ['source', 'appearance', 'plan', 'scene', 'video', 'persona', 'training', 'release']);
  assert.equal(PROMPT.lanes.find((l) => l.id === 'training').label, '평가');
  for (const id of ['s9s', 's9', 's10t']) assert.ok(!PROMPT.stages.some((s) => s.id === id), id + ' is removed, not greyed');
});

test('twin links follow the real order: G0 opens appearance, plan and the comparison set; no-training evaluation waits for G6', () => {
  const train = edges(TRAIN);
  for (const e of ['s0>s2', 's0>s3', 's0>s9h', 's8>s9s', 's9>s10t']) assert.ok(train.includes(e), e);
  const prompt = edges(PROMPT);
  for (const e of ['s0>s2', 's0>s3', 's0>s9h', 's8>s10']) assert.ok(prompt.includes(e), e);
  assert.ok(!prompt.some((e) => /s9s|s9>|s10t/.test(e)));
  assert.deepEqual(edges(PROMPT), edges(BIND));
});

test('layout keeps the reviewed columns: source in front, data column closes up when there is no training', () => {
  const tw = Flow.layoutOf(Runtime.buildGraph(TRAIN));
  assert.equal(tw.cls, 'tw');
  assert.deepEqual(tw.cell.so, [0.5, 0]);
  assert.deepEqual([tw.cell.ap, tw.cell.pl, tw.cell.dt, tw.cell.tr, tw.cell.pk], [[0, 1], [1, 1], [1, 3], [1, 4], [0.5, 5]]);
  const nt = Flow.layoutOf(Runtime.buildGraph(PROMPT));
  assert.equal(nt.cls, 'tw nt');
  assert.equal(nt.cell.dt, undefined);
  assert.deepEqual([nt.cell.vd, nt.cell.ps, nt.cell.tr, nt.cell.pk], [[0, 3], [1, 2], [1, 3], [0.5, 4]]);
  const css = fs.readFileSync(path.join(__dirname, '..', 'shared', 'flow.css'), 'utf8');
  const original = Flow.layoutOf({ lanes: [{ id: 'appearance', stages: ['s1', 's2'] }, { id: 'data', stages: ['s9s', 's9'] }] });
  assert.equal(original.cls, '', 'original graph keeps the plain layout');
  assert.deepEqual(original.cell.pk, [0.5, 4]);
  assert.equal(original.cell.so, undefined);
  assert.ok(css.includes('"so ap sc vd . pk" "so pl ps dt tr pk"'));
  assert.ok(css.includes('"so ap sc vd pk" "so pl ps tr pk"'));
});

test('six-column twin graph fits laptop widths: columns follow name length, the original grid is untouched', () => {
  const css = fs.readFileSync(path.join(__dirname, '..', 'shared', 'flow.css'), 'utf8');
  const cols = (css.match(/\.fl-grid\.tw\{grid-template-columns:([^;]+);/) || [])[1] || '';
  const fr = (cols.match(/[\d.]+fr/g) || []).map(parseFloat);
  assert.equal(fr.length, 6, cols);
  const [so, , sc, , tr] = fr;
  assert.ok(sc === Math.max(...fr), 'scene has the longest step names');
  assert.ok(tr === Math.min(...fr), 'training has the shortest step names');
  assert.ok(so > 1, 'source fits its waiting status on one line');
  assert.ok(css.includes('.fl-grid{position:relative;display:grid;grid-template-columns:repeat(5,minmax(0,1fr));column-gap:32px'), 'original graph keeps equal columns');
  // 줄임 규칙은 모티브 칸에만 건다.
  assert.ok(css.includes('.fl-grid.tw .fl-row .gt{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}'));
  assert.ok(!/\.fl-grid \.fl-row \.(gt|sb)\{/.test(css));
  // 휴대폰 폭에서는 긴 프롬프트 그래프도 한 열이다(5열 상속으로 칸이 39px가 되던 문제).
  const phone = css.split('@container canvas (max-width:760px)').slice(1).join('');
  assert.ok(phone.includes('.fl-grid.tw.nt{grid-template-columns:minmax(0,1fr);'));
});

test('step marks stick to the last word so an icon never wraps alone', () => {
  const mark = '<svg class="i"></svg>';
  assert.equal(Flow.stageNameHTML('캐릭터 기획', mark), '캐릭터 <span class="nb">기획' + mark + '</span>');
  assert.equal(Flow.stageNameHTML('평가', mark), '<span class="nb">평가' + mark + '</span>');
  assert.equal(Flow.stageNameHTML('참고 자료 선별', ''), '참고 자료 선별');
  assert.equal(Flow.stageNameHTML('<b> x', mark), '&lt;b&gt; <span class="nb">x' + mark + '</span>');
});

test('G0 and G1s count as reviews with the same task function', () => {
  const g = Runtime.buildGraph(TRAIN);
  const d = detailFor(TRAIN, { s0: 'AWAITING_HUMAN' }, [{ id: 'G0', status: 'AWAITING_HUMAN', rev: 'sp1', openedAt: '2026-11-08T04:40:00Z' }]);
  const v = Flow.viewsFor(g, d, { now: NOW });
  assert.equal(v.s0.kind, 'wait');
  const [task] = Flow.buildTasks(g, d, v, { now: NOW });
  assert.deepEqual([task.kind, task.gate, task.stage, task.title], ['wait', 'G0', 's0', TRAIN.gates.find((x) => x.id === 'G0').title]);
  assert.equal(task.blocked, TRAIN.stages.length - 1, 'every later stage waits for the source bundle');

  const p = Runtime.buildGraph(PROMPT);
  const d2 = detailFor(PROMPT, { s0: 'APPROVED', s2: 'AWAITING_HUMAN', s3: 'AWAITING_HUMAN' }, [
    { id: 'G0', status: 'APPROVED' },
    { id: 'G1s', status: 'AWAITING_HUMAN', rev: 'hr1', openedAt: '2026-11-08T04:50:00Z' },
    { id: 'G3', status: 'AWAITING_HUMAN', rev: 'pl1', openedAt: '2026-11-08T04:55:00Z' }
  ]);
  const tasks = Flow.buildTasks(p, d2, Flow.viewsFor(p, d2, { now: NOW }), { now: NOW });
  assert.deepEqual(tasks.map((t) => t.gate).sort(), ['G1s', 'G3']);
  assert.equal(Flow.targetLabel(p, 'G0'), TRAIN.gates.find((x) => x.id === 'G0').title + '까지');
});

test('track badge text: original, or twin with how the model is prepared', () => {
  assert.equal(Flow.trackLabel({ origin: 'CREATED' }), '오리지널');
  assert.equal(Flow.trackLabel({}), '오리지널');
  assert.equal(Flow.trackLabel({ origin: 'SOURCE', originLabel: '모티브', modelMode: 'TRAIN' }), '모티브 · 학습');
  assert.equal(Flow.trackLabel({ origin: 'SOURCE', modelMode: 'BIND_EXISTING' }), '모티브 · 학습된 모델 연결');
  assert.equal(Flow.trackLabel({ origin: 'SOURCE', modelMode: 'PROMPT_ONLY' }), '모티브 · 프롬프트만');
});

test('chat test link opens only for motif characters whose prompt (s8) exists', () => {
  const row = (status) => ({ id: 's8', status });
  const base = { id: 'cf-son', origin: 'SOURCE' };
  assert.equal(Flow.chatHref(Object.assign({}, base, { stages: [row('AWAITING_HUMAN')] })), 'chat.html#c/cf-son', 'G6 waiting means the prompt is already written');
  assert.equal(Flow.chatHref(Object.assign({}, base, { stages: [row('APPROVED')] })), 'chat.html#c/cf-son');
  assert.equal(Flow.chatHref(Object.assign({}, base, { stages: [row('RUNNING')] })), '');
  assert.equal(Flow.chatHref(Object.assign({}, base, { stages: [] })), '');
  assert.equal(Flow.chatHref({ id: 'cf-orig', origin: 'CREATED', stages: [row('APPROVED')] }), '', 'original characters have no chat test yet');
  assert.equal(Flow.chatHref({ id: 'a b', origin: 'SOURCE', stages: [row('APPROVED')] }), 'chat.html#c/a%20b');
});

test('the S8c step is named after the opening scene, and mode names match the upload page', () => {
  assert.equal(Flow.s8cName('SOURCE', ''), '팬 통화 장면');
  assert.equal(Flow.s8cName('SOURCE', 'FAN_CALL'), '팬 통화 장면');
  assert.equal(Flow.s8cName('SOURCE', 'FAMILY_CALL'), '통화 장면');
  assert.equal(Flow.s8cName('CREATED', ''), '통화 장면');
  const S = require('../shared/sources.js');
  ['PROMPT_ONLY', 'BIND_EXISTING'].forEach((m) => assert.equal(S.MODES.find((x) => x[0] === m)[1], Flow.MODE_LABEL[m], m));
  const src = require('node:fs').readFileSync(require('node:path').join(__dirname, '..', 'shared', 'flow.js'), 'utf8');
  assert.ok(src.includes("c.origin === 'SOURCE' ? '<span class=\"fd-org\""), 'the sidebar marks motif characters');
});

