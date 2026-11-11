'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const Sources = require('../shared/sources.js');

test('launch preflight failure shows its reason and keeps the uploaded draft retryable', async () => {
  const draft = {
    characterId: 'synthetic', subject: { displayName: '합성인물', kind: 'PRIVATE_PERSON' },
    autoReview: true, modelMode: 'PROMPT_ONLY', videoTier: 'none',
    files: [{ fileId: 'f1', filename: 'synthetic.txt', fileType: 'text', status: 'ready', problems: [] }],
    canFinalize: true, problems: []
  };
  let configured = false;
  const launchError = '생성 모델은 연결돼 있지만 검토 모델이 준비되지 않았어요. 운영 설정에서 검토 모델을 연결한 뒤 다시 시작해 주세요. 아직 제작을 시작하지 않았어요.';
  const launches = [];
  const json = (status, data) => ({ ok: status < 400, status, json: async () => structuredClone(data) });
  const intake = Sources.createIntake({ fetch: async (url, init = {}) => {
    const path = new URL(url, 'http://synthetic.test').pathname;
    if (path === '/api/sources/synthetic/finalize') {
      if (!configured) return json(503, { detail: launchError });
      launches.push(path);
      return json(200, { jobId: 'synthetic-job' });
    }
    if (path === '/api/sources/synthetic') return json(200, draft);
    if (path === '/api/characters/synthetic') return json(200, { stages: [], pendingGates: [] });
    if (path.endsWith('/chat/meta')) return json(200, { ready: false });
    throw Error('Unexpected request: ' + (init.method || 'GET') + ' ' + path);
  }, XHR: null });
  await intake.load('synthetic');
  assert.equal(await intake.finalize(), null);
  assert.equal(intake.state.error, '만들기를 시작하지 못했어요. ' + launchError);
  assert.equal(intake.state.busy, null);
  assert.equal(intake.startState().ready, true);
  assert.equal(intake.state.draft.files[0].fileId, 'f1');
  assert.equal(launches.length, 0);
  configured = true;
  assert.deepEqual(await intake.finalize(), { jobId: 'synthetic-job' });
  assert.equal(launches.length, 1);
});
