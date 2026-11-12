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
  assert.deepEqual(laneIds(TRAIN), ['source', 'appearance', 'plan', 'scene', 'video', 'persona', 'data', 'training', 'voice', 'release']);
  assert.deepEqual(laneIds(PROMPT), ['source', 'appearance', 'plan', 'scene', 'video', 'persona', 'training', 'voice', 'release']);
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

test('chat link opens only when the character can chat: the server chatReady wins, else prompt (s8) and opening scene (s8c) both exist', () => {
  const rows = (s8, s8c) => [{ id: 's8', status: s8 }].concat(s8c ? [{ id: 's8c', status: s8c }] : []);
  const base = { id: 'cf-son', origin: 'SOURCE' };
  assert.equal(Flow.chatHref(Object.assign({}, base, { stages: rows('AWAITING_HUMAN', 'APPROVED') })), '', 'waiting for approval is not ready to chat');
  assert.equal(Flow.chatHref(Object.assign({}, base, { stages: rows('APPROVED', 'APPROVED') })), 'chat.html#c/cf-son');
  // QA C1: 프롬프트만 있고 첫 장면이 없으면 대화 화면이 막히므로 버튼을 보이지 않는다.
  assert.equal(Flow.chatHref(Object.assign({}, base, { stages: rows('APPROVED') })), '', 'no opening scene yet');
  assert.equal(Flow.chatHref(Object.assign({}, base, { stages: rows('APPROVED', 'PENDING') })), '');
  assert.equal(Flow.chatHref(Object.assign({}, base, { stages: rows('RUNNING', 'APPROVED') })), '');
  assert.equal(Flow.chatHref(Object.assign({}, base, { stages: [] })), '');
  assert.equal(Flow.chatHref({ id: 'cf-orig', origin: 'CREATED', stages: rows('APPROVED', 'APPROVED') }), '', 'original characters have no chat test yet');
  assert.equal(Flow.chatHref({ id: 'a b', origin: 'SOURCE', stages: rows('APPROVED', 'APPROVED') }), 'chat.html#c/a%20b');
  // 서버가 대화 화면과 같은 함수로 계산한 값이 있으면 단계 기록보다 먼저다.
  assert.equal(Flow.chatHref(Object.assign({}, base, { chatReady: false, stages: rows('APPROVED', 'APPROVED') })), '');
  assert.equal(Flow.chatHref(Object.assign({}, base, { chatReady: true, stages: [] })), 'chat.html#c/cf-son');
});

test('the S8c step is named after the opening scene, and mode names match the upload page', () => {
  assert.equal(Flow.s8cName('SOURCE', ''), '첫 통화 장면', 'without a template the name fits family calls too (QA v5 F20)');
  assert.equal(Flow.s8cName('SOURCE', 'FAN_CALL'), '팬 통화 장면');
  assert.equal(Flow.s8cName('SOURCE', 'FRIEND_CHAT'), '친구 대화 장면');
  assert.equal(Flow.s8cName('SOURCE', 'INTERVIEW'), '인터뷰 장면');
  assert.equal(Flow.s8cName('SOURCE', 'FAMILY_CALL'), '통화 장면');
  assert.equal(Flow.s8cName('CREATED', ''), '통화 장면');
  const S = require('../shared/sources.js');
  ['PROMPT_ONLY', 'BIND_EXISTING'].forEach((m) => assert.equal(S.MODES.find((x) => x[0] === m)[1], Flow.MODE_LABEL[m], m));
  const src = require('node:fs').readFileSync(require('node:path').join(__dirname, '..', 'shared', 'flow.js'), 'utf8');
  assert.ok(src.includes("c.origin === 'SOURCE' ? '<span class=\"fd-org\""), 'the sidebar marks motif characters');
});


// ---- 3차 사용성 QA(K 묶음): 상태 하나, 목표 진행, 목표 밖 단계 접기, 이름 구분 ----
const DONE5 = { s0: 'APPROVED', s3: 'APPROVED', s7: 'APPROVED', s8: 'APPROVED', s8c: 'APPROVED' };

test('QA F01/C2: one status everywhere; the server status wins, otherwise a finished prompt-only motif reads "대화 가능"', () => {
  const p = Runtime.buildGraph(PROMPT);
  const d = detailFor(PROMPT, DONE5, [{ id: 'G0', status: 'APPROVED' }, { id: 'G3', status: 'APPROVED' }, { id: 'G6', status: 'APPROVED' }]);
  d.id = 'cf-son';
  const v = Flow.viewsFor(p, d, { now: NOW });
  assert.equal(Flow.buildTasks(p, d, v, { now: NOW }).length, 0, 'nothing for a person to do');
  const st = Flow.statusOf(d, { fail: 0, review: 0, paid: 0, running: false, complete: false, fresh: false });
  assert.deepEqual([st.status, st.label, st.tone], ['chat_ready', '대화 가능', 'ok']);
  // 서버가 정한 상태와 이름표가 있으면 그대로 쓴다.
  assert.deepEqual([Flow.statusOf({ status: 'running', statusLabel: '만드는 중' }, {}).label, Flow.statusOf({ status: 'running' }, {}).tone], ['만드는 중', 'run']);
  // 서버 값이 없을 때의 순서: 만드는 중 → 실패 → 확인 필요 → 대화 가능 → 완료 → 시작 전 → 멈춤
  const of = (s, c) => Flow.statusOf(c || {}, s).status;
  assert.equal(of({ running: true, fail: 1 }), 'running');
  assert.equal(of({ fail: 1, review: 1 }), 'failed');
  assert.equal(of({ paid: 1 }, d), 'needs_review', 'a paid confirmation is a person\'s decision');
  assert.equal(of({ fresh: true }), 'draft');
  assert.equal(of({ complete: true }), 'done');
  assert.equal(of({}), 'stopped');
  assert.deepEqual(Object.values(Flow.STATUS_LABEL).slice(0, 6), ['시작 전', '만드는 중', '확인 필요', '대화 가능', '실패', '멈춤']);
});

test('QA F02/F16: progress counts only the stages needed to chat (motif), uses the server goal when present, originals count every stage', () => {
  const p = Runtime.buildGraph(PROMPT);
  assert.deepEqual([...Flow.goalStages(p, { origin: 'SOURCE', modelMode: 'PROMPT_ONLY' })].sort(), ['s0', 's3', 's7', 's8', 's8c']);
  const d = detailFor(PROMPT, DONE5, []);
  const g = Flow.goalOf(p, d, Flow.viewsFor(p, d, { now: NOW }));
  assert.deepEqual([g.label, g.done, g.total], ['대화 제작 단계', 5, 5]);
  const half = detailFor(PROMPT, { s0: 'APPROVED', s3: 'APPROVED' }, []);
  assert.equal(Flow.goalOf(p, half, Flow.viewsFor(p, half, { now: NOW })).done, 2);
  assert.deepEqual(Flow.goalOf(p, Object.assign({}, half, { goal: { label: '대화 가능까지', done: 4, total: 5 } }), {}).done, 4, 'server goal wins');
  // 학습 방식 모티브는 학습 단계까지 센다.
  const t = Runtime.buildGraph(TRAIN);
  const tg = Flow.goalStages(t, { origin: 'SOURCE', modelMode: 'TRAIN' });
  for (const id of ['s0', 's8', 's8c', 's9s', 's9', 's10t']) assert.ok(tg.has(id), id);
  assert.ok(!tg.has('s2') && !tg.has('s11'));
  // 오리지널은 목표 경로가 없고 전체 단계를 센다.
  const o = Runtime.buildGraph(PROMPT);
  assert.equal(Flow.goalStages(o, { origin: 'CREATED' }), null);
});

test('QA F03: off-goal stages fold into one row; a stage that needs a person stays visible; unfolding shows everything', () => {
  const p = Runtime.buildGraph(PROMPT);
  const d = detailFor(PROMPT, DONE5, []);
  const gv = Flow.goalView(p, d, Flow.viewsFor(p, d, { now: NOW }), false);
  assert.equal(gv.hidden, PROMPT.stages.length - 5, '11 stages fold away');
  assert.ok(!gv.keep.has('s2') && gv.keep.has('s8c'));
  const busy = detailFor(PROMPT, Object.assign({ s2: 'AWAITING_HUMAN' }, DONE5), [{ id: 'G1s', status: 'AWAITING_HUMAN', rev: 'h1' }]);
  assert.ok(Flow.goalView(p, busy, Flow.viewsFor(p, busy, { now: NOW }), false).keep.has('s2'), 'a waiting off-goal review is not hidden');
  assert.equal(Flow.goalView(p, d, {}, true).keep, null);
  assert.equal(Flow.goalView(p, { origin: 'CREATED' }, {}, false).keep, null, 'original graphs never fold');
});

test('QA F09/F6: same names are told apart by when they were made; the display name comes from the server first', () => {
  const list = [
    { id: 'cf-20261110-motif-aaa', displayName: '손흥민', createdAt: '2026-11-10T04:49:00' },
    { id: 'cf-20261110-motif-bbb', name: '손흥민', createdAt: '2026-11-10T02:57:00' },
    { id: 'cf-20261109-son-v2', name: '손흥민' },
    { id: 'cf-20261109-son-v3', name: '손흥민' },
    { id: 'cf-20261109-solo', name: '정이환' },
    { id: 'cf-20261110-motif-ccc', name: 'cf-20261110-motif-ccc', displayName: 'QA테스트 손흥민' }
  ];
  const m = Flow.nameLabels(list);
  assert.deepEqual(m.get('cf-20261110-motif-aaa'), { name: '손흥민', note: '11/10 04:49 만듦' });
  assert.equal(m.get('cf-20261110-motif-bbb').note, '11/10 02:57 만듦');
  assert.equal(m.get('cf-20261109-son-v2').note, '11/9 만듦 · son-v2', 'same day without a time falls back to the short name');
  assert.equal(m.get('cf-20261109-solo').note, '', 'a unique name needs nothing extra');
  assert.equal(m.get('cf-20261110-motif-ccc').name, 'QA테스트 손흥민');
  assert.equal(Flow.labelOf({ id: 'cf-20261105-api-cost-argon', name: 'cf-20261105-api-cost-argon' }), '이름 미정 · api-cost-argon (11/5)');
  // 서버 createdAt이 없으면 첫 실행 시각으로 구분한다.
  const runs = Flow.nameLabels([{ id: 'cf-20261109-a', name: 'X', stages: [{ startedAt: '2026-11-09T01:03:00' }] }, { id: 'cf-20261109-b', name: 'X', stages: [{ startedAt: '2026-11-09T01:35:00' }] }]);
  assert.equal(runs.get('cf-20261109-a').note, '11/9 01:03 만듦');
});

test('QA F11: a made-up character gets its short id automatically and the server accepts it', () => {
  for (const brief of ['동네 빵집 제빵사, 29세', 'Cafe owner in Seoul', '']) {
    const slug = Flow.autoSlug(brief, Date.parse('2026-11-10T06:00:00Z'));
    assert.match(slug, /^[a-z0-9][a-z0-9-]{0,40}$/, slug);
    assert.doesNotThrow(() => Runtime.createCharacterRequest(slug, '브리프'));
  }
  assert.match(Flow.autoSlug('Cafe owner in Seoul', 1), /^cafe-owner-/);
});

test('QA F08: earlier failed attempts of a stage that later succeeded fold away, and developer errors read as plain Korean', () => {
  const hist = [{ attempt: 1, result: 'CHECK_FAILED', error: 'TaintedOutputError: 작업 공간 밖 경로에 접근했다: /out' }, { attempt: 2, result: 'APPROVED' }];
  const ok = Flow.splitAttempts(hist, true);
  assert.deepEqual([ok.shown.map((a) => a.attempt), ok.earlier.map((a) => a.attempt)], [[2], [1]]);
  assert.deepEqual(Flow.splitAttempts(hist, false).earlier, [], 'a stage still failing shows every attempt');
  const why = Flow.failReason(hist[0].error);
  assert.equal(why.summary, '작업 공간 밖의 파일을 건드리려 해서 멈췄어요.');
  assert.match(why.detail, /TaintedOutputError/, 'the original stays in the technical details');
  assert.doesNotMatch(Flow.failReason('KeyError: subjectSpeaker').summary, /KeyError|subjectSpeaker/);
});

test('QA F20/F09/F7: no link to the old screen, names stay visible on laptops, and a motif draft points to the source page', () => {
  const css = fs.readFileSync(path.join(__dirname, '..', 'shared', 'flow.css'), 'utf8');
  const src = fs.readFileSync(path.join(__dirname, '..', 'shared', 'flow.js'), 'utf8');
  const page = fs.readFileSync(path.join(__dirname, '..', 'factory.html'), 'utf8');
  assert.ok(!src.includes('>이전 화면<'), 'the old-screen link is gone');
  assert.ok(src.includes('모델 설정 (운영 담당용)'), 'model settings moved to a small operator link');
  // 첫 글자만 남는 레일은 900px 아래에서만 쓴다(1280px에서도 이름이 보인다).
  const rail = css.split('@media (max-width:899px){')[1] || '';
  assert.ok(rail.split('}')[0].includes('grid-template-columns:60px'), 'rail only below 900px');
  assert.ok(!/@media \(max-width:1439px\)\{[^}]*\.fd-nav \.lbl/.test(css), 'labels are not hidden at 1280px');
  assert.ok(page.includes('data-offgoal'));
  assert.ok(/원문 화면에서 이어 하기/.test(src) && /href="sources\.html#c\/'/.test(src), 'drafts continue on the source page');
});
