'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const Runtime = require('../shared/runtime.js');

const GRAPH = {
  mode: 'live',
  stages: [
    { id: 's1', name: '기준 얼굴', deps: ['G1'], needs: [], after: [], gate: 'G1', implemented: true },
    { id: 's3', name: '기획', deps: ['G3'], needs: ['s1'], after: [], gate: 'G3', implemented: true },
    { id: 's4b', name: '장면·자세', deps: ['G4b'], needs: [], after: ['s3'], gate: 'G4b', implemented: true },
    { id: 's9s', name: '데이터 샘플', deps: ['G7a'], needs: ['s4b'], after: [], gate: 'G7a', implemented: true },
    { id: 'sx', name: '내보내기', deps: ['G9'], needs: ['s9s'], after: [], gate: 'G9', implemented: false }
  ],
  gates: [
    { id: 'G1', title: '얼굴 고르기', stage: 's1' },
    { id: 'G3', title: '기획안 고르기', stage: 's3' },
    { id: 'G4b', title: '장면·자세 고르기', stage: 's4b' },
    { id: 'G7a', title: '데이터 샘플 검토', stage: 's9s' },
    { id: 'G9', title: '패키지 승인', stage: 'sx' }
  ]
};

test('graph keeps deps, needs and after as real edges', () => {
  const graph = Runtime.buildGraph(GRAPH);
  assert.deepEqual(graph.stages.map((s) => s.id), ['s1', 's3', 's4b', 's9s', 'sx']);
  assert.ok(graph.edges.some((e) => e.from === 'G4b' && e.to === 's4b' && e.kind === 'deps'));
  assert.ok(graph.edges.some((e) => e.from === 's1' && e.to === 's3' && e.kind === 'needs'));
  assert.ok(graph.edges.some((e) => e.from === 's3' && e.to === 's4b' && e.kind === 'after'));
  assert.ok(graph.gates.some((g) => g.id === 'G4b'));
  assert.ok(graph.gates.some((g) => g.id === 'G7a'));
  assert.equal(graph.byStage.get('s9s').gate, 'G7a');
});

test('graph accepts missing arrays and does not invent stages', () => {
  const graph = Runtime.buildGraph({ stages: [{ id: 'only', name: '하나' }], gates: [] });
  assert.equal(graph.stages.length, 1);
  assert.deepEqual(graph.stages[0].deps, []);
  assert.deepEqual(graph.stages[0].needs, []);
  assert.deepEqual(graph.stages[0].after, []);
  assert.equal(graph.edges.length, 0);
});

test('server statuses translate exactly and unknown is not progress', () => {
  const expected = {
    PENDING: 'queued',
    RUNNING: 'running',
    CHECK_FAILED: 'failed',
    REJECTED: 'failed',
    AWAITING_HUMAN: 'gate',
    APPROVED: 'done',
    SKIPPED: 'skipped'
  };
  for (const [raw, state] of Object.entries(expected)) {
    const tr = Runtime.translateStage({ status: raw }, { id: 's', name: 'S' });
    assert.equal(tr.state, state, raw);
    assert.equal(tr.raw, raw);
  }
  const missing = Runtime.translateStage(null, { id: 's', name: 'S' });
  assert.equal(missing.state, 'unknown');
  assert.equal(missing.label, '상태 없음');
  assert.equal(Runtime.translateStage({ status: 'RUNNING', progress: 99, eta: 1 }, { id: 'x' }).progress, undefined);
});

test('running never gains progress from elapsed time', () => {
  const a = Runtime.translateStage({ status: 'RUNNING', startedAt: '2020-01-01T00:00:00Z' }, { id: 's' });
  const b = Runtime.translateStage({ status: 'RUNNING', startedAt: '2026-01-01T00:00:00Z' }, { id: 's' });
  assert.equal(a.state, 'running');
  assert.equal(b.state, 'running');
  assert.equal(a.progress, b.progress);
  assert.equal(a.progress, undefined);
});

test('progress is only the server number or the unknown label', () => {
  assert.equal(Runtime.progressText(undefined), '미집계');
  assert.equal(Runtime.progressText(null), '미집계');
  assert.equal(Runtime.progressText({ percent: 42 }), '42%');
  assert.equal(Runtime.progressText({ done: 3, total: 8 }), '3/8 단계');
  assert.equal(Runtime.progressText(57), '57%');
  assert.equal(Runtime.progressText({ percent: 130 }), '100%');
});

test('header counts come from records and unknown metrics stay unknown', () => {
  const detail = {
    stages: { s1: { status: 'APPROVED', rev: 'r1' }, s3: { status: 'AWAITING_HUMAN' }, s4b: { status: 'CHECK_FAILED', error: 'boom' }, s9s: { status: 'RUNNING' } },
    pendingGates: [{ gate: 'G4b', stage: 's4b' }]
  };
  const counts = Runtime.countsFor(detail, Runtime.buildGraph(GRAPH));
  assert.equal(counts.total, 5);
  assert.equal(counts.done, 1);
  assert.equal(counts.pending, 2);
  assert.equal(counts.errors, 1);
  assert.equal(counts.unknown, 1);
  assert.equal(Runtime.metricText(undefined), '미집계');
  assert.equal(Runtime.metricText(12), '12');
});

test('job succeeded is a single job, not pipeline completion', () => {
  const j = Runtime.jobStatus('succeeded');
  assert.equal(j.tone, 'ok');
  assert.equal(j.complete, false);
  assert.match(j.label, /성공/);
  assert.equal(Runtime.jobStatus('queued').state, 'queued');
  assert.equal(Runtime.jobStatus('failed').state, 'failed');
  assert.equal(Runtime.jobStatus('bogus').state, 'unknown');
});

test('request builders keep explicit confirm list and encode identity', () => {
  assert.deepEqual(Runtime.runRequest('char/1', 'G6', []), {
    characterId: 'char/1', action: 'run', until: 'G6', confirm: []
  });
  assert.deepEqual(Runtime.runRequest('c', 's5', ['s5']), {
    characterId: 'c', action: 'run', until: 's5', confirm: ['s5']
  });
  assert.throws(() => Runtime.runRequest('', 'G6'), /캐릭터/);
  assert.throws(() => Runtime.runRequest('c', ''), /단계/);
  assert.deepEqual(Runtime.createCharacterRequest('hana-1', '브리프'), { slug: 'hana-1', brief: '브리프' });
  assert.throws(() => Runtime.createCharacterRequest('', '브리프'), /slug/);
  assert.throws(() => Runtime.createCharacterRequest('bad slug', '브리프'), /slug/);
  assert.throws(() => Runtime.createCharacterRequest('ok', ''), /브리프/);
  assert.throws(() => Runtime.createCharacterRequest('ok', 'x'.repeat(20001)), /브리프/);
});

test('URLs encode ids and gates for API and the gate iframe', () => {
  assert.equal(Runtime.apiPath('', '/api/characters/a b'), '/api/characters/a b');
  assert.equal(Runtime.apiPath('/base/', '/api/projects'), '/base/api/projects');
  assert.equal(Runtime.characterPath('a/b?c', ''), '/api/characters/a%2Fb%3Fc');
  assert.equal(Runtime.gateUrl('a b', 'G4b', ''), '/gate.html?character=a%20b&gate=G4b');
  assert.equal(Runtime.gateUrl('a&b', 'G7a', '/base/'), '/base/gate.html?character=a%26b&gate=G7a');
  assert.equal(Runtime.eventsUrl('http://127.0.0.1:8776/'), 'http://127.0.0.1:8776/api/events');
});

test('until options come only from graph stages and gates', () => {
  const options = Runtime.untilOptions(Runtime.buildGraph(GRAPH));
  assert.deepEqual(options, ['G1', 'G3', 'G4b', 'G7a', 'G9', 's1', 's3', 's4b', 's9s', 'sx']);
  assert.ok(options.includes('G7a'));
  assert.ok(options.includes('G4b'));
});

test('held entries are surfaced with providers and only one explicit confirm target', () => {
  const held = Runtime.extractHeld({ held: [{ stage: 's5', providers: ['paid-video'] }, 's10t'] });
  assert.deepEqual(held, [
    { stage: 's5', providers: ['paid-video'] },
    { stage: 's10t', providers: [] }
  ]);
  assert.deepEqual(Runtime.confirmHeldRequest('c', held[0]), {
    characterId: 'c', action: 'run', until: 's5', confirm: ['s5']
  });
  assert.throws(() => Runtime.confirmHeldRequest('c', { stage: '', providers: [] }), /단계/);
});

test('route parser handles chars, character, job table and floor with query character', () => {
  assert.deepEqual(Runtime.parseRoute('#chars'), { view: 'chars', characterId: null, jobId: null, sub: '' });
  assert.deepEqual(Runtime.parseRoute('#char/a%20b'), { view: 'char', characterId: 'a b', jobId: null, sub: '' });
  assert.deepEqual(Runtime.parseRoute('#job/j1/floor?character=a%20b'), {
    view: 'job', characterId: 'a b', jobId: 'j1', sub: 'floor'
  });
  assert.deepEqual(Runtime.parseRoute('#job/j1', '?character=c1'), {
    view: 'job', characterId: 'c1', jobId: 'j1', sub: 'table'
  });
  assert.equal(Runtime.parseRoute('').view, 'chars');
});

test('factory layout uses actual nodes and real edges only', () => {
  const scene = Runtime.sceneLayout(Runtime.buildGraph(GRAPH));
  assert.deepEqual(scene.nodes.filter((n) => n.kind === 'stage').map((n) => n.id), ['s1', 's3', 's4b', 's9s', 'sx']);
  assert.equal(scene.edges.length, 9);
  assert.ok(scene.nodes.some((n) => n.kind === 'gate' && n.id === 'G7a'));
  assert.ok(scene.width > 0 && scene.height > 0);
});

test('pending gates accept detail and project shapes and never default approve', () => {
  const graph = Runtime.buildGraph(GRAPH);
  const pending = Runtime.pendingGatesFor({
    gates: { G1: { status: 'AWAITING_HUMAN' }, G3: { status: 'APPROVED' } },
    pendingGates: ['G4b']
  }, graph);
  assert.deepEqual(pending.map((g) => g.id).sort(), ['G1', 'G4b']);
  assert.ok(pending.every((g) => !('decision' in g)));
  assert.equal(Runtime.gateState('AWAITING_HUMAN'), 'pending');
  assert.equal(Runtime.gateState('PENDING'), 'waiting');
  assert.equal(Runtime.gateState('APPROVED'), 'approved');
});

test('text pipeline records expose source provenance separately and escape markup', () => {
  const parsed = Runtime.parseTextPipeline({
    artifacts: [{ label: '<b>x</b>', text: '<script>bad()</script>', sourceModel: 'm1', sourceProfile: 'p1' }],
    calls: [{ task: 'plan', stage: 's3', model: 'm1', profile: 'p1', ok: true }]
  });
  assert.equal(parsed.artifacts.length, 1);
  assert.equal(parsed.artifacts[0].sourceModel, 'm1');
  assert.equal(Runtime.escapeHTML(parsed.artifacts[0].label), '&lt;b&gt;x&lt;/b&gt;');
  assert.equal(Runtime.escapeHTML(parsed.artifacts[0].text), '&lt;script&gt;bad()&lt;/script&gt;');
  assert.equal(Runtime.escapeHTML(`"'&<>`), '&quot;&#39;&amp;&lt;&gt;');
  assert.equal(Runtime.safeHref('javascript:alert(1)'), '');
  assert.equal(Runtime.safeHref('//evil.example/x'), '');
  assert.equal(Runtime.safeHref('/files/x'), '/files/x');
  assert.equal(Runtime.safeHref('https://example.test/x'), 'https://example.test/x');
});

test('mount is exposed as a browser-safe function', () => {
  assert.equal(typeof Runtime.mount, 'function');
});
