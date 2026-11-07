'use strict';

// 오프라인 검사: DOM 의존성(jsdom)이 없으므로 내보낸 순수 함수와 방어적 mount 계약을 검사한다.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
function loadModule() {
  const file = path.join(__dirname, '..', 'shared', 'text-pipeline.js');
  const source = fs.readFileSync(file, 'utf8');
  // 브라우저 전역(window/document)만 주입하고, 검사 결과는 같은 realm의 객체로 받는다.
  const browserWindow = {};
  const run = new Function('window', source);
  run(browserWindow);
  return browserWindow.FactoryTextPipeline;
}

const api = loadModule();
const I = api.internals;

test('disabled configuration keeps the contract shape without selections or roles', () => {
  const config = I.normalizeConfig({
    enabled: false,
    profile: 'demo',
    route: 'test',
    completionCheck: 'NOT_RUN',
    profiles: [{ id: 'demo', label: '시연' }],
    routes: [{ id: 'test', label: '별도 테스트 서버', available: false, reason: '주소·인증 설정이 필요합니다' }],
    tasks: [{ id: 'brief', label: '기본 설정 정리', model: 'gpt-6.1-sol', reasoningEffort: 'high' }],
    activeJobs: 0,
  });

  assert.equal(config.enabled, false);
  assert.equal(config.profile, null);
  assert.equal(config.route, null);
  assert.deepEqual(config.tasks, []);
  assert.equal(config.profiles[0].label, '시연');
  assert.equal(config.routes[0].available, false);
  assert.equal(config.routes[0].reason, '주소·인증 설정이 필요합니다');
});

test('a malformed configuration response is rejected instead of guessed at', () => {
  assert.throws(() => I.normalizeConfig(null), TypeError);
  assert.throws(() => I.normalizeConfig('{}'), TypeError);
  assert.throws(() => I.normalizeConfig([]), TypeError);
});

test('roles keep server deck order, fill only the id fallback, and are never padded to nine', () => {
  const ids = ['brief', 'research', 'voice', 'persona', 'dialogue', 'dataset', 'qa', 'packaging', 'release'];
  const config = I.normalizeConfig({
    enabled: true,
    profile: 'basic_test',
    route: 'opencodex',
    tasks: ids.map((id) => ({ id, label: `역할 ${id}`, model: 'gpt-6.1-sol', reasoningEffort: 'high' })),
  });
  assert.deepEqual(config.tasks.map((task) => task.id), ids);
  assert.equal(config.tasks.length, 9);

  const partial = I.normalizeConfig({
    enabled: true,
    tasks: [{ id: 'brief', model: '' }, { label: 'id 없음' }, { id: 'voice', model: 'm' }],
  });
  assert.equal(partial.tasks.length, 2, 'id가 없는 항목만 버린다');
  assert.equal(partial.tasks[0].label, 'brief', 'label이 없으면 id를 쓴다');
  assert.equal(partial.tasks[0].model, null, '없는 모델을 지어내지 않는다');
  assert.equal(partial.tasks[0].reasoningEffort, null);
  assert.equal(partial.activeJobs, 0);
});

test('characters are deduplicated by id and missing names fall back to the id', () => {
  const characters = I.normalizeCharacters({
    characters: [
      { id: 'cf-1' },
      { name: 'id 없음' },
      { id: 'cf-2', name: '서하' },
      { id: 'cf-1', name: '중복' },
      null,
    ],
  });
  assert.deepEqual(characters, [
    { id: 'cf-1', name: 'cf-1' },
    { id: 'cf-2', name: '서하' },
  ]);
  assert.deepEqual(I.normalizeCharacters(null), []);
  assert.deepEqual(I.normalizeCharacters({ characters: 'nope' }), []);
});

test('character detail caps calls at 50 and preserves unknown sources as null', () => {
  const calls = Array.from({ length: 60 }, (_, index) => ({
    task: 'voice', stage: 's7', model: `actual-${index}`, profile: 'demo', route: 'opencodex', ok: index % 2 === 0, ref: `ref-${index}`,
  }));
  const detail = I.normalizeDetail({
    characterId: 'cf-1',
    calls,
    artifacts: [
      { label: '페르소나 프롬프트', revision: 'pv1', text: '본문', completionCheck: 'NOT_RUN' },
      { label: '대화 묶음', sourceModel: 'actual-model', sourceProfile: 'demo' },
    ],
    workshopUrl: '/?character=cf-1',
  });

  assert.equal(detail.characterId, 'cf-1');
  assert.equal(detail.name, 'cf-1');
  assert.equal(detail.calls.length, 50);
  assert.equal(detail.calls[0].ref, 'ref-0');
  assert.deepEqual(detail.stages, []);
  assert.deepEqual(detail.gates, []);
  assert.equal(detail.artifacts[0].sourceModel, null, '현재 설정으로 출처를 채우지 않는다');
  assert.equal(detail.artifacts[0].sourceProfile, null);
  assert.equal(detail.artifacts[1].sourceModel, 'actual-model');
  assert.equal(detail.workshopUrl, '/?character=cf-1');

  assert.throws(() => I.normalizeDetail(null), TypeError);
  assert.equal(I.normalizeDetail({ characterId: 'cf-2', workshopUrl: 'javascript:alert(1)' }).workshopUrl, null);
});

test('model and reasoning labels stay readable while raw detail is available separately', () => {
  assert.equal(I.modelLabel('gpt-6.1-sol'), 'GPT 6.1 Sol');
  assert.equal(I.modelLabel('google-antigravity/gemini-3.8-flash'), 'Gemini 3.8 Flash');
  assert.equal(I.modelLabel('deepseek-v4.1-flash'), 'Deepseek V4.1 Flash');
  assert.equal(I.modelLabel(null), '지정 안 됨');
  assert.equal(I.modelLabel('   '), '지정 안 됨');
  assert.equal(I.reasoningLabel('high'), '높음');
  assert.equal(I.reasoningLabel('medium'), '보통');
  assert.equal(I.reasoningLabel('low'), '낮음');
  assert.equal(I.reasoningLabel(null), '기록 없음');
  assert.equal(I.reasoningLabel('ultra'), 'ultra', '모르는 강도는 원문을 그대로 보여 준다');
});

test('stage and gate statuses map truthfully and unknown codes are not renamed', () => {
  assert.deepEqual(I.statusInfo('stage', 'APPROVED'), { label: '승인', tone: 'ok' });
  assert.deepEqual(I.statusInfo('gate', 'approved'), { label: '결재됨', tone: 'ok' });
  assert.deepEqual(I.statusInfo('gate', 'PENDING'), { label: '결재 대기', tone: 'warn' });
  assert.deepEqual(I.statusInfo('stage', 'RUNNING'), { label: '작업 중', tone: 'active' });
  assert.deepEqual(I.statusInfo('stage', 'FAILED'), { label: '실패', tone: 'bad' });
  assert.deepEqual(I.statusInfo('gate', 'G7_BLOCKED'), { label: 'G7_BLOCKED', tone: 'muted' });
  assert.deepEqual(I.statusInfo('stage', null), { label: '기록 없음', tone: 'muted' });
});

test('completion check is shown as recorded and NOT_RUN is never upgraded', () => {
  assert.deepEqual(I.completionInfo('NOT_RUN'), { label: '최종 점검 전', tone: 'muted' });
  assert.deepEqual(I.completionInfo(null), { label: '기록 없음', tone: 'muted' });
  assert.deepEqual(I.completionInfo('PASSED'), { label: 'PASSED', tone: 'muted' });
});

test('selection payload contains only changed known fields', () => {
  const current = { profile: 'basic_test', route: 'opencodex' };
  assert.deepEqual(I.selectionPayload(current, { profile: 'demo' }), { profile: 'demo' });
  assert.deepEqual(I.selectionPayload(current, { route: 'test' }), { route: 'test' });
  assert.equal(I.selectionPayload(current, { profile: 'basic_test' }), null);
  assert.equal(I.selectionPayload(current, {}), null);
  assert.throws(() => I.selectionPayload(current, { profile: 'demo', activeJobs: 0 }), TypeError);
  assert.throws(() => I.selectionPayload(current, { profile: '' }), TypeError);
  assert.throws(() => I.selectionPayload(null, { profile: 'demo' }), TypeError);
});

test('selection is locked while jobs run, while saving, while offline, or when disabled', () => {
  assert.match(I.selectionLockReason({ enabled: true, activeJobs: 2 }), /2/);
  assert.ok(I.selectionLockReason({ enabled: false, activeJobs: 0 }));
  assert.ok(I.selectionLockReason({ enabled: true, activeJobs: 0 }, { saving: true }));
  assert.ok(I.selectionLockReason({ enabled: true, activeJobs: 0 }, { offline: true }));
  assert.equal(I.selectionLockReason({ enabled: true, activeJobs: 0 }, {}), '');

  assert.equal(I.routeUnavailableReason({ available: false, reason: '주소·인증 설정이 필요합니다' }), '주소·인증 설정이 필요합니다');
  assert.equal(I.routeUnavailableReason({ available: true }), '');
  assert.ok(I.routeUnavailableReason({ available: false }), '이유가 없어도 쓸 수 없다는 사실은 남긴다');
});

test('request gate rejects stale and aborted responses per request kind', () => {
  const gate = I.createRequestGate();
  const first = gate.next('config');
  const second = gate.next('config');
  assert.equal(gate.isCurrent(first), false);
  assert.equal(gate.isCurrent(second), true);
  assert.equal(first.controller.signal.aborted, true, '새 요청은 이전 요청을 중단한다');

  const characters = gate.next('characters');
  assert.equal(gate.isCurrent(characters), true);
  assert.equal(gate.isCurrent(second), true, '요청 종류끼리 서로를 무효화하지 않는다');
  gate.abort('characters');
  assert.equal(gate.isCurrent(characters), false);
  assert.equal(characters.controller.signal.aborted, true);
  assert.equal(gate.isCurrent({ kind: 'config', seq: 99, controller: second.controller }), false);
});

test('URLs and API bases reject executable or protocol-relative values', () => {
  assert.equal(I.safeUrl('/?character=cf-1'), '/?character=cf-1');
  assert.equal(I.safeUrl('https://example.com/workshop'), 'https://example.com/workshop');
  assert.equal(I.safeUrl('javascript:alert(1)'), null);
  assert.equal(I.safeUrl('//evil.example/path'), null);
  assert.equal(I.safeUrl(''), null);
  assert.equal(I.normalizeApiBase(''), '');
  assert.equal(I.normalizeApiBase('/api/'), '/api');
  assert.equal(I.normalizeApiBase('https://example.com/'), 'https://example.com');
  assert.equal(I.normalizeApiBase('javascript:alert(1)'), '');
  assert.equal(I.normalizeApiBase('//evil.example'), '');
});

test('artifact source comparison distinguishes current settings from recorded source', () => {
  const config = { profile: 'basic_test' };
  assert.deepEqual(I.sourceCompare(config, 'basic_test'), { key: 'same', label: '지금 프로필과 같음' });
  assert.deepEqual(I.sourceCompare(config, 'demo'), { key: 'different', label: '다른 프로필' });
  assert.deepEqual(I.sourceCompare(config, null), { key: 'unknown', label: '프로필 기록 없음' });
  assert.deepEqual(I.sourceCompare(null, 'demo'), { key: 'unknown', label: '지금 프로필을 알 수 없음' });
});

test('mount is defensive without a DOM or a usable root and returns a no-op controller', () => {
  assert.equal(typeof api.mount, 'function');
  for (const arg of [undefined, {}, { root: null }, { root: {} }]) {
    const controller = api.mount(arg);
    assert.equal(typeof controller.open, 'function');
    assert.equal(typeof controller.close, 'function');
    assert.equal(typeof controller.destroy, 'function');
    assert.equal(controller.open(), false);
    assert.equal(controller.close(), false);
    controller.destroy();
  }
});


test('a server-truncated artifact remains visibly partial after normalization', () => {
  const detail = I.normalizeDetail({characterId: 'cf-1', artifacts: [
    {label: '프롬프트', text: '서버가 제한한 본문…', textTruncated: true}
  ]});
  assert.equal(detail.artifacts[0].textTruncated, true);
});
