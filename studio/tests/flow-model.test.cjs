'use strict';
// 모델 만들기 탭과 모델 단계의 다음 일(QA v5 B-F06·B-F07·C-08). 그래프는 서버 _graph 출력(fixtures)을 쓴다.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Runtime = require('../shared/runtime.js');
const Flow = require('../shared/flow.js');

const load = (mode) => JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'twin-graph-' + mode + '.json'), 'utf8'));
const TRAIN = load('TRAIN');
const BIND = load('BIND_EXISTING');
const NOW = Date.parse('2026-11-11T05:00:00Z');
const CHAT = { s0: 'APPROVED', s3: 'APPROVED', s7: 'APPROVED', s8: 'APPROVED', s8c: 'APPROVED' };
function detailFor(raw, stages, gates, modelPath, extra) {
  const g = Object.keys(gates).map((id) => ({ id, status: gates[id], rev: 'r1' }));
  return Object.assign({
    id: 'tw', origin: 'SOURCE', modelMode: raw.modelMode,
    stages: raw.stages.map((s) => ({ id: s.id, status: stages[s.id] || 'PENDING', attempts: stages[s.id] ? 1 : 0 })),
    gates: g, pendingGates: g.filter((x) => x.status === 'AWAITING_HUMAN'), history: {}, held: [], jobs: [{}],
    modelPath: Object.assign({ training: { state: 'locked' }, eval: { gate: { status: 'PENDING' } } }, modelPath || {})
  }, extra || {});
}
function look(raw, d, busy) {
  const graph = Runtime.buildGraph(raw);
  const views = Flow.viewsFor(graph, d, { now: NOW });
  return {
    tasks: Flow.buildTasks(graph, d, views, { now: NOW, jobActive: Boolean(busy), goal: 'sx' }),
    steps: Object.fromEntries(Flow.modelSteps(d, views).map((s) => [s.id, s])),
    next: Flow.modelNext(graph, d)
  };
}
const modelTask = (tasks) => tasks.find((t) => t.age === '모델 만들기');

test('B-F06: after the prompt is approved, the training motif offers to start data samples (not before)', () => {
  const before = look(TRAIN, detailFor(TRAIN, CHAT, { G6: 'AWAITING_HUMAN' }));
  assert.equal(modelTask(before.tasks), undefined);
  assert.equal(before.steps.src.s, '프롬프트를 승인하면 정해요');
  const after = look(TRAIN, detailFor(TRAIN, CHAT, { G6: 'APPROVED' }));
  const t = modelTask(after.tasks);
  assert.equal(t.title, '데이터 샘플을 만들 차례예요');
  assert.deepEqual(t.actions.map((a) => [a.act, a.stage]), [['model-run', 's9s']]);
  assert.equal(Flow.MODEL_RUN_UNTIL.s9s, 'G7a', 'the button runs only up to the sample review');
  assert.equal(after.steps.src.s, '데이터 샘플을 만들 차례예요');
  // 같은 단계를 '이어서 실행' 안내가 또 알리지 않는다.
  assert.ok(!after.tasks.some((x) => x.kind === 'ready' && x.age !== '모델 만들기' && /데이터 샘플/.test(x.body)));
  // 작업이 도는 동안은 누를 수 없고, 다른 일이 끝나면 할 수 있다고 알린다.
  const busy = modelTask(look(TRAIN, detailFor(TRAIN, CHAT, { G6: 'APPROVED' }), true).tasks).actions[0];
  assert.ok(busy.disabled && busy.why);
});

test('B-F06: after the sample review the dataset says it is waiting to be made, and only says making while it runs', () => {
  const ds = { rev: 'ds1', status: 'PENDING', counts: { train: 0, validation: 0, eval: 0, total: 0 }, gates: { G7a: { status: 'APPROVED' }, G7: { status: 'PENDING' } } };
  const st = Object.assign({}, CHAT, { s9s: 'APPROVED' });
  const idle = look(TRAIN, detailFor(TRAIN, st, { G6: 'APPROVED', G7a: 'APPROVED' }, { dataset: ds }));
  assert.deepEqual([idle.steps.data.k, idle.steps.data.s], ['todo', '학습 데이터를 만들 차례예요']);
  assert.deepEqual(modelTask(idle.tasks).actions.map((a) => [a.act, a.stage]), [['model-run', 's9']]);
  assert.equal(Flow.MODEL_RUN_UNTIL.s9, 'G7');
  const running = look(TRAIN, detailFor(TRAIN, Object.assign({}, st, { s9: 'RUNNING' }), { G6: 'APPROVED', G7a: 'APPROVED' }, { dataset: ds }));
  assert.deepEqual([running.steps.data.k, running.steps.data.s], ['run', '만드는 중']);
  assert.equal(modelTask(running.tasks), undefined);
});

test('B-F06: the free training plan has a button; paid training never starts from it', () => {
  const st = Object.assign({}, CHAT, { s9s: 'APPROVED', s9: 'APPROVED' });
  const r = look(TRAIN, detailFor(TRAIN, st, { G6: 'APPROVED', G7a: 'APPROVED', G7: 'APPROVED' }, { training: { state: 'pending' } }));
  assert.equal(r.next.stage, 's10t');
  assert.equal(Flow.MODEL_RUN_UNTIL.s10t, 's10t');
  assert.deepEqual(modelTask(r.tasks).actions.map((a) => a.act), ['model-run']);
  // 계획을 세운 뒤에는 비용 확인 항목이 대신 나오고, 모델 단계 버튼은 없다.
  const plan = look(TRAIN, detailFor(TRAIN, Object.assign({}, st, { s10t: 'AWAITING_HUMAN' }), { G6: 'APPROVED', G7: 'APPROVED' }, { training: { state: 'plan', estimateUsd: 0.37 } }));
  assert.equal(plan.next, null);
  assert.ok(plan.tasks.some((x) => x.kind === 'confirm' && x.stage === 's10t'));
});

test('a paid stage held for cost confirmation is left to the confirmation item', () => {
  const d = detailFor(TRAIN, CHAT, { G6: 'APPROVED' }, null, { held: [{ stage: 's9s', providers: ['text: openai/gpt'] }] });
  assert.equal(look(TRAIN, d).next, null);
});

test('B-F07: the bind mode shows only connect → evaluate, asks for a connection file, then offers evaluation', () => {
  const none = look(BIND, detailFor(BIND, CHAT, { G6: 'APPROVED' }, { mode: 'BIND_EXISTING', binding: null }));
  assert.deepEqual(Object.keys(none.steps), ['bind', 'eval']);
  assert.equal(Flow.modelActive(detailFor(BIND, CHAT, {}, { binding: null })), 'bind');
  assert.equal(none.steps.eval.s, '모델을 연결하면 열려요');
  const ask = modelTask(none.tasks);
  assert.equal(ask.title, '연결할 모델을 골라 주세요');
  assert.deepEqual(ask.actions.map((a) => [a.act, a.step]), [['open-model', 'bind']]);
  const binding = { kindLabel: '서빙 주소', ref: 'https://serving.example/m' };
  const bound = look(BIND, detailFor(BIND, CHAT, { G6: 'APPROVED' }, { binding }));
  assert.deepEqual([bound.steps.bind.k, bound.steps.bind.s], ['ok', '서빙 주소 · https://serving.example/m']);
  assert.equal(bound.steps.bind.done, false, 'can still switch models before the evaluation review');
  assert.deepEqual(modelTask(bound.tasks).actions.map((a) => [a.act, a.stage]), [['model-run', 's10']]);
  assert.equal(Flow.MODEL_RUN_UNTIL.s10, 'G8');
  const review = look(BIND, detailFor(BIND, CHAT, { G6: 'APPROVED', G8: 'AWAITING_HUMAN' }, { binding, eval: { promptOnly: true, gate: { status: 'AWAITING_HUMAN' } } }));
  assert.equal(review.next, null);
  assert.equal(review.steps.eval.s, '연결한 모델 채택 검토');
  assert.equal(review.steps.bind.done, true);
});

test('C-08: the model tab uses the same numbers and outcome as the reviews', () => {
  const st = Object.assign({}, CHAT, { s9s: 'APPROVED', s9: 'APPROVED', s10t: 'APPROVED', s10: 'APPROVED' });
  const mp = {
    dataset: { rev: 'ds1', status: 'APPROVED', counts: { train: 11, validation: 6, eval: 6, total: 23 }, gates: { G7a: { status: 'APPROVED' }, G7: { status: 'APPROVED' } } },
    training: { state: 'done', adopted: true },
    eval: { gate: { status: 'APPROVED' }, adopted: { value: 'LONG_BASE', label: '긴 프롬프트' } }
  };
  const r = look(TRAIN, detailFor(TRAIN, st, { G6: 'APPROVED', G7a: 'APPROVED', G7: 'APPROVED', G8: 'APPROVED' }, mp));
  assert.equal(r.steps.data.s, '대화 23개 · 승인됨', 'G7 summary counts every conversation');
  assert.ok(!/골랐어요/.test(r.steps.train.s), 'the checkpoint pick is not the adoption');
  assert.equal(r.steps.eval.s, '긴 프롬프트로 채택함');
});
