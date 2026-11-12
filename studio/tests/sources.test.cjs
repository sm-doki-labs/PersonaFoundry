'use strict';
// 원문으로 새 캐릭터 화면(sources.js)의 검사. 계획 §2 출처 API를 흉내 내는 가짜 서버를 fetch로 넣는다. 네트워크·브라우저 없음.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const S = require('../shared/sources.js');

const ORIGIN = 'http://factory.test';

// 계획 §2 계약과 3차 약속 4(원문에서 찾은 화자·제안)를 따르는 메모리 서버. 부른 순서를 calls에 남긴다.
// legacy를 켜면 약속 4 이전 서버처럼 화자를 채우지 않고 제안도 주지 않는다.
function fakeServer(opts) {
  const o = Object.assign({ store: 'local', allowPathImport: false, legacy: false }, opts || {});
  const calls = [];
  const db = { draft: null, files: [], seq: 0, canFinalize: false, problems: ['원문 파일을 하나 이상 올려 주세요.'], fail: {}, speakers: [{ name: '손흥민', lines: 12 }, { name: '기자', lines: 4 }], suggest: {}, drafts: null };
  const json = (status, body) => ({ ok: status >= 200 && status < 300, status, headers: { get: () => 'application/json' }, json: async () => body });
  // 약속 4: 비운 대상 화자는 서버가 표시 이름과 맞춘 화자로 채우고, 원문에 없는 이름이면 해요체 한 문장으로 알린다.
  // 맞는 화자가 없으면(suggest.subjectSpeaker null) 비워 두고 고르라고 알린다(QA v5 A-03).
  function check(f) {
    if (!f.kind) f.kind = db.suggest.kind || S.guessKind(f.filename);
    if (!f.register) f.register = db.suggest.register || S.defaultRegister(f.kind);
    if (o.legacy) { f.status = 'ready'; f.problems = []; return; }
    const names = db.speakers.map((s) => s.name);
    const sug = Object.assign({ subjectSpeaker: names[0], userSpeaker: names[1] || null }, db.suggest);
    if (!f.subjectSpeaker) f.subjectSpeaker = sug.subjectSpeaker;
    f.detectedSpeakers = db.speakers;
    f.suggested = sug;
    const ok = names.indexOf(f.subjectSpeaker) >= 0;
    f.status = ok ? 'ready' : 'problem';
    f.problems = ok ? [] : !f.subjectSpeaker ? ['누가 이 사람인지 골라 주세요. 원문에 있는 이름: ' + names.join(', ')] : ["원문에서 '" + f.subjectSpeaker + "'이라는 화자를 찾지 못했어요. 원문에 있는 이름: " + names.join(', ')];
  }
  // 4차 약속 5: 사진은 fileType "photo"로 같은 줄에 선다. photoRule을 켜면 서버도 영상 등급이 있는데 사진이 없으면 시작을 막는다.
  const isPhoto = (name) => /\.(jpe?g|png|webp)$/i.test(name);
  function photoGate() {
    if (!o.photoRule || !db.draft) return;
    const need = db.draft.videoTier && db.draft.videoTier !== 'none' && !db.files.some((f) => f.fileType === 'photo' && f.status === 'ready');
    const msg = '영상을 만들려면 사진이 1장 이상 있어야 해요.';
    const noText = '대화나 글이 담긴 원문을 하나 이상 올려 주세요.';
    db.problems = db.problems.filter((p) => p !== msg && p !== noText && p !== '원문 파일을 하나 이상 올려 주세요.');
    if (!db.files.some((f) => f.fileType === 'text')) db.problems.push(noText);
    if (need) db.problems.push(msg);
    db.canFinalize = db.files.some((f) => f.fileType === 'text' && f.status === 'ready') && !need;
  }
  function view() {
    photoGate();
    return { characterId: 'cf-son', subject: db.draft.subject, usageBasis: db.draft.usageBasis, videoTier: db.draft.videoTier, store: o.store, allowPathImport: o.allowPathImport, files: db.files.map((f) => Object.assign({}, f)), problems: db.problems.slice(), canFinalize: db.canFinalize };
  }
  async function fetch(url, init) {
    const method = (init && init.method) || 'GET';
    const u = new URL(url, ORIGIN);
    const body = init && typeof init.body === 'string' ? JSON.parse(init.body) : init && init.body;
    calls.push({ method, url: String(url), path: u.pathname, host: u.host, body, headers: (init && init.headers) || {}, credentials: init && init.credentials });
    const key = method + ' ' + u.pathname.replace(/\/f\d+/, '/:id');
    if (db.fail[key]) { db.fail[key]--; return json(500, { detail: '잠깐 문제가 있었어요.' }); }
    let m;
    if (method === 'POST' && u.pathname === '/api/sources/drafts') {
      db.draft = { subject: { displayName: body.displayName, kind: body.subjectKind }, usageBasis: body.usageBasis, chapterTemplate: body.chapterTemplate, modelMode: body.modelMode, autoReview: body.autoReview, videoTier: body.videoTier };
      return json(200, { characterId: 'cf-son' });
    }
    if (method === 'PATCH' && u.pathname === '/api/sources/cf-son/settings') {
      if (o.noSettings) return json(404, { detail: 'Not Found' });
      db.draft.videoTier = body.videoTier;
      return json(200, { characterId: 'cf-son', videoTier: body.videoTier });
    }
    if (method === 'GET' && u.pathname === '/api/sources/cf-son') return db.draft ? json(200, view()) : json(404, { detail: 'Not Found' });
    if (method === 'GET' && u.pathname === '/api/sources/drafts') return db.drafts ? json(200, db.drafts) : json(404, { detail: 'Not Found' });
    if (method === 'GET' && /^\/api\/sources\/[^/]+$/.test(u.pathname)) return json(404, { detail: 'Not Found' });
    if (method === 'POST' && u.pathname === '/api/sources/cf-son/files') {
      const fileId = 'f' + (++db.seq);
      if (db.finalized && !isPhoto(body.filename)) return json(409, { detail: '이미 만들기를 시작했어요.' });
      db.files.push({ fileId, filename: body.filename, size: body.size, sha256: '', status: 'pending', fileType: isPhoto(body.filename) ? 'photo' : 'text', textId: null, kind: null, register: null, subjectSpeaker: null, userSpeaker: null, date: null, sourceUrl: null, problems: [] });
      const upload = o.store === 's3'
        ? { method: 'PUT', url: 'https://bucket.s3.ap-northeast-2.amazonaws.com/sources/cf-son/' + fileId + '?X-Amz-Signature=abc', headers: { 'Content-Type': body.contentType } }
        : { method: 'PUT', url: '/api/sources/cf-son/files/' + fileId + '/content', headers: { 'Content-Type': 'application/octet-stream' } };
      return json(200, { fileId, upload });
    }
    if (method === 'PUT') {
      if (db.fail.PUT) { db.fail.PUT--; return { ok: false, status: 403, json: async () => null }; }
      return { ok: true, status: 200, json: async () => null };
    }
    if ((m = /^\/api\/sources\/cf-son\/files\/(f\d+)\/complete$/.exec(u.pathname)) && method === 'POST') {
      const f = db.files.find((x) => x.fileId === m[1]);
      if (f.fileType === 'photo' && Object.keys(body || {}).length) return json(422, { detail: '사진에는 화자 정보를 넣지 않아도 돼요.' });
      Object.assign(f, body, { sha256: 'h' + m[1] });
      if (f.fileType === 'photo') { f.status = 'ready'; f.problems = []; } else check(f);
      db.canFinalize = f.status === 'ready';
      db.problems = [];
      photoGate();
      return json(200, Object.assign({}, f));
    }
    if ((m = /^\/api\/sources\/cf-son\/files\/(f\d+)$/.exec(u.pathname))) {
      const f = db.files.find((x) => x.fileId === m[1]);
      if (method === 'PATCH') { Object.assign(f, body); check(f); db.canFinalize = f.status === 'ready'; return json(200, Object.assign({}, f)); }
      if (method === 'DELETE') { db.files = db.files.filter((x) => x !== f); if (!db.files.length) { db.canFinalize = false; db.problems = ['원문 파일을 하나 이상 올려 주세요.']; } return { ok: true, status: 204, json: async () => null }; }
    }
    if (method === 'POST' && u.pathname === '/api/sources/cf-son/finalize') { db.finalized = true; return json(200, { jobId: 'job-1' }); }
    if (method === 'POST' && u.pathname === '/api/sources/cf-son/import-path') {
      const f = { fileId: 'f' + (++db.seq), filename: body.path.replace(/^.*\//, ''), size: 100, sha256: 'h', fileType: 'text', textId: 'imported', kind: 'TRANSCRIPT', register: 'CASUAL', subjectSpeaker: null, userSpeaker: null, date: null, sourceUrl: null, problems: [] };
      check(f);
      db.files.push(f);
      db.canFinalize = f.status === 'ready';
      return json(200, Object.assign({}, f));
    }
    if (method === 'GET' && u.pathname === '/api/projects') return json(200, { characters: (db.projects || []).slice() });
    if (method === 'GET' && u.pathname === '/api/characters/cf-son') return json(200, Object.assign({ id: 'cf-son', origin: 'SOURCE', modelMode: db.draft && db.draft.modelMode, autoReview: db.draft && db.draft.autoReview, progress: { done: db.done || 0, total: 12 }, pendingGates: [], stages: [], job: (db.done || 0) < 12 ? { id: 'job-1' } : null }, db.detail || {}));
    if (method === 'GET' && u.pathname === '/api/characters/cf-son/chat/meta') return db.noChat ? json(404, { detail: 'Not Found' }) : json(200, { characterId: 'cf-son', ready: !!db.chatReady, reason: db.chatReady ? '' : '프롬프트를 아직 만들고 있어요.' });
    if (method === 'DELETE' && u.pathname === '/api/sources/cf-son') { db.draft = null; db.files = []; if (db.drafts) db.drafts = db.drafts.filter((d) => d.characterId !== 'cf-son'); if (db.projects) db.projects = db.projects.filter((c) => c.id !== 'cf-son'); return { ok: true, status: 204, json: async () => null }; }
    return json(404, { detail: 'Not Found' });
  }
  return { fetch, calls, db };
}
const file = (name, size, type) => ({ name, size: size == null ? 1200 : size, type: type || 'text/plain' });
async function settle() { for (let i = 0; i < 60; i++) await new Promise((r) => setImmediate(r)); }
async function ready(server) {
  const intake = S.createIntake({ fetch: server.fetch, origin: ORIGIN, XHR: null });
  const res = await intake.createDraft({ displayName: '손흥민', subjectKind: 'PUBLIC_FIGURE', age: '34세', gender: '남성', job: '축구선수', scope: '최종 발표 시연', notes: '공개 인터뷰만' });
  assert.equal(res.characterId, 'cf-son');
  return intake;
}
const seq = (calls) => calls.map((c) => c.method + ' ' + c.path);

test('register defaults follow the kind table and only replace an untouched register', () => {
  assert.equal(S.defaultRegister('INTERVIEW'), 'FORMAL');
  assert.equal(S.defaultRegister('ARTICLE'), 'FORMAL');
  assert.equal(S.defaultRegister('KAKAO_EXPORT'), 'CASUAL');
  assert.equal(S.defaultRegister('TRANSCRIPT'), 'CASUAL');
  assert.equal(S.defaultRegister('OTHER'), null);
  assert.equal(S.nextRegister('INTERVIEW', 'KAKAO_EXPORT', 'FORMAL'), 'CASUAL', 'default follows the new kind');
  assert.equal(S.nextRegister('INTERVIEW', 'KAKAO_EXPORT', ''), 'CASUAL');
  assert.equal(S.nextRegister('TRANSCRIPT', 'ARTICLE', 'FORMAL'), 'FORMAL', 'a register the person picked stays');
  assert.equal(S.guessKind('KakaoTalk_20240101.txt'), 'KAKAO_EXPORT');
  assert.equal(S.guessKind('방송 뒷이야기.srt'), 'TRANSCRIPT');
  assert.equal(S.guessKind('경기 뒤 기사.txt'), 'ARTICLE');
  assert.equal(S.guessKind('손흥민 인터뷰.txt'), 'INTERVIEW');
  assert.equal(S.guessKind('casual_vlog.txt'), 'TRANSCRIPT', 'a vlog is not an interview');
  assert.equal(S.guessKind('interview_press.txt'), 'INTERVIEW');
  assert.equal(S.kindHint('notes.txt'), null, 'no hint in the name leaves it to the server');
  assert.equal(S.guessKind('notes.txt'), 'INTERVIEW');
});

test('text ids are suggested from the file name, fall back to kind-number, and never collide', () => {
  assert.equal(S.suggestTextId('Son_Interview_2023.txt', 'INTERVIEW', []), 'son_interview_2023');
  assert.equal(S.suggestTextId('손흥민 인터뷰.txt', 'INTERVIEW', []), 'interview-1');
  assert.equal(S.suggestTextId('손흥민 인터뷰 2.txt', 'INTERVIEW', ['interview-1']), 'interview-2');
  assert.equal(S.suggestTextId('카톡.txt', 'KAKAO_EXPORT', ['kakao-1', 'kakao-2']), 'kakao-3');
  assert.equal(S.suggestTextId('Son_Interview_2023.txt', 'INTERVIEW', ['son_interview_2023']), 'son_interview_2023-2');
  assert.match(S.suggestTextId('2024.txt', 'ARTICLE', []), /^article-2024$/);
  assert.equal(S.textIdProblem('ok_id-1'), null);
  assert.ok(S.textIdProblem('한글'));
  assert.ok(S.checkFile(file('clip.mp4')));
  assert.ok(S.checkFile(file('photo.gif')), 'only jpg, png and webp photos are taken');
  assert.equal(S.checkFile(file('face.png', 5000, 'image/png')), null, 'photos are accepted for the video step');
  assert.match(S.checkFile(file('face.jpg', S.PHOTO_MAX_BYTES + 1)), /15MB/);
  assert.ok(S.checkFile(file('big.txt', S.MAX_BYTES + 1)));
  assert.equal(S.checkFile(file('a.vtt')), null);
});

test('local store: draft, then files → PUT with cookies to our server → complete with the suggested meta', async () => {
  const server = fakeServer();
  const intake = await ready(server);
  assert.deepEqual(server.calls[0].body, { displayName: '손흥민', subjectKind: 'PUBLIC_FIGURE', usageBasis: { scope: '최종 발표 시연', notes: '공개 인터뷰만' }, knownFacts: { age: '34세', gender: '남성', job: '축구선수', background: '' }, modelMode: 'PROMPT_ONLY', autoReview: true, videoTier: 'none' });
  server.calls.length = 0;
  intake.addFiles([file('KakaoTalk_son.txt', 3000)]);
  await settle();
  assert.deepEqual(seq(server.calls).filter((s) => !s.includes('/api/characters/')), ['POST /api/sources/cf-son/files', 'PUT /api/sources/cf-son/files/f1/content', 'POST /api/sources/cf-son/files/f1/complete', 'GET /api/sources/cf-son', 'PATCH /api/sources/cf-son/files/f1', 'GET /api/sources/cf-son']);
  assert.deepEqual(server.calls[0].body, { filename: 'KakaoTalk_son.txt', size: 3000, contentType: 'text/plain' });
  const put = server.calls[1];
  assert.equal(put.url, '/api/sources/cf-son/files/f1/content');
  assert.equal(put.credentials, 'same-origin');
  assert.deepEqual(put.headers, { 'Content-Type': 'application/octet-stream' });
  assert.deepEqual(server.calls[2].body, { textId: 'kakaotalk_son', kind: null, register: null, subjectSpeaker: null, userSpeaker: null, date: null, sourceUrl: null }, 'the subject speaker is left blank so the server picks it from the source');
  assert.equal(intake.state.draft.files[0].subjectSpeaker, '손흥민');
  assert.equal(server.calls.find((c) => c.method === 'PATCH').body.userSpeaker, '기자', 'the partner the server found fills the empty partner field (A-23)');
  const items = intake.items();
  assert.equal(items.length, 1);
  assert.equal(items[0].status, '준비됐어요');
  assert.equal(items[0].key, 'u1', 'the card keeps its key after the upload becomes a server file');
  assert.equal(intake.startState().ready, true);
});

test('S3 store: PUT goes to the signed URL with exactly the returned headers and no cookies', async () => {
  const server = fakeServer({ store: 's3' });
  const intake = await ready(server);
  intake.addFiles([file('interview.vtt', 500, 'text/vtt')]);
  await settle();
  const put = server.calls.find((c) => c.method === 'PUT');
  assert.equal(put.host, 'bucket.s3.ap-northeast-2.amazonaws.com');
  assert.equal(put.credentials, 'omit');
  assert.deepEqual(put.headers, { 'Content-Type': 'text/vtt' });
  const complete = server.calls.find((c) => c.path.endsWith('/complete'));
  assert.equal(complete.body.kind, null);
  assert.equal(complete.body.register, null);
  assert.equal(intake.items()[0].meta.kind, 'TRANSCRIPT');
  assert.equal(intake.items()[0].meta.register, 'CASUAL');
});

test('a failed send restarts with a fresh slot; a failed check retries only the check', async () => {
  const server = fakeServer();
  const intake = await ready(server);
  server.db.fail.PUT = 1;
  const [key] = intake.addFiles([file('a.txt')]);
  await settle();
  let item = intake.items().find((i) => i.key === key);
  assert.equal(item.status, '올리지 못했어요');
  assert.equal(item.retry, true);
  assert.equal(intake.startState().ready, false);
  assert.ok(intake.startState().reasons.some((r) => r.includes('올리지 못한 파일')));
  server.calls.length = 0;
  intake.retry(key);
  await settle();
  assert.deepEqual(seq(server.calls).slice(0, 4), ['DELETE /api/sources/cf-son/files/f1', 'POST /api/sources/cf-son/files', 'PUT /api/sources/cf-son/files/f2/content', 'POST /api/sources/cf-son/files/f2/complete']);
  assert.equal(intake.items().find((i) => i.key === key).status, '준비됐어요');

  server.db.fail['POST /api/sources/cf-son/files/:id/complete'] = 1;
  const [k2] = intake.addFiles([file('b.txt')]);
  await settle();
  item = intake.items().find((i) => i.key === k2);
  assert.equal(item.status, '올리지 못했어요');
  assert.deepEqual(item.problems, ['잠깐 문제가 있었어요.']);
  server.calls.length = 0;
  intake.retry(k2);
  await settle();
  assert.deepEqual(seq(server.calls).slice(0, 1), ['POST /api/sources/cf-son/files/f3/complete']);
  assert.ok(!server.calls.some((c) => c.method === 'PUT'), 'the file is not sent twice');
});

test('rejected files never reach the server and do not block the start', async () => {
  const server = fakeServer();
  const intake = await ready(server);
  server.calls.length = 0;
  intake.addFiles([file('clip.mp4'), file('ok.txt')]);
  await settle();
  assert.ok(!server.calls.some((c) => c.body && c.body.filename === 'clip.mp4'));
  const bad = intake.items().find((i) => i.filename === 'clip.mp4');
  assert.equal(bad.status, '받을 수 없는 파일');
  assert.equal(intake.startState().ready, true);
});

test('editing kind PATCHes the full meta with the new default register; a picked register stays', async () => {
  const server = fakeServer();
  const intake = await ready(server);
  const [key] = intake.addFiles([file('interview.txt')]);
  await settle();
  server.calls.length = 0;
  await intake.editFile(key, 'kind', 'KAKAO_EXPORT');
  await settle();
  const patch = server.calls.find((c) => c.method === 'PATCH');
  assert.equal(patch.path, '/api/sources/cf-son/files/f1');
  assert.equal(patch.body.kind, 'KAKAO_EXPORT');
  assert.equal(patch.body.register, 'CASUAL');
  assert.equal(patch.body.textId, 'interview');
  await intake.editFile(key, 'register', 'FORMAL');
  await intake.editFile(key, 'kind', 'TRANSCRIPT');
  await settle();
  const last = server.calls.filter((c) => c.method === 'PATCH').pop();
  assert.equal(last.body.register, 'FORMAL');
  assert.equal(intake.items()[0].saving, 'saved');
});

test('an invalid or duplicate text id is shown but never sent, and blocks the start until fixed', async () => {
  const server = fakeServer();
  const intake = await ready(server);
  const [a, b] = intake.addFiles([file('one.txt'), file('two.txt')]);
  await settle();
  server.calls.length = 0;
  assert.equal(intake.editFile(b, 'textId', '한글 이름'), null);
  assert.equal(intake.editFile(b, 'textId', 'one'), null);
  const item = intake.items().find((i) => i.key === b);
  assert.match(item.fieldErrors.textId, /같아요/);
  assert.equal(item.display.textId, 'one');
  assert.equal(item.meta.textId, 'two');
  assert.ok(!server.calls.some((c) => c.method === 'PATCH'));
  assert.equal(intake.startState().ready, false);
  assert.ok(intake.startState().reasons.includes('파일 정보에 고칠 곳이 있어요.'));
  await intake.editFile(b, 'textId', 'two-b');
  await settle();
  assert.equal(server.calls.filter((c) => c.method === 'PATCH').length, 1);
  assert.equal(intake.startState().ready, true);
  assert.ok(a);
});

test('finalize is gated by the server canFinalize and by local work, then starts the job once', async () => {
  const server = fakeServer();
  const intake = await ready(server);
  let st = intake.startState();
  assert.equal(st.ready, false);
  assert.ok(st.reasons.includes('원문 파일을 하나 이상 올려 주세요.'));
  assert.equal(await intake.finalize(), null);
  assert.ok(!server.calls.some((c) => c.path.endsWith('/finalize')));

  intake.addFiles([file('a.txt')]);
  st = intake.startState();
  assert.equal(st.ready, false, 'an upload in progress blocks the start');
  assert.ok(st.reasons.some((r) => r.includes('올리는 중')));
  await settle();

  server.db.canFinalize = false;
  server.db.problems = ['사용 범위를 적어 주세요.'];
  await intake.refresh();
  st = intake.startState();
  assert.equal(st.ready, false);
  assert.deepEqual(st.reasons, ['사용 범위를 적어 주세요.'], 'server problems are shown as they are');

  server.db.canFinalize = true;
  server.db.problems = [];
  await intake.refresh();
  assert.equal(intake.startState().ready, true);
  const done = await intake.finalize();
  assert.deepEqual(done, { jobId: 'job-1' });
  assert.equal(server.calls.filter((c) => c.path === '/api/sources/cf-son/finalize').length, 1);
  assert.equal(intake.startState().ready, false, 'no second start');
  assert.equal(intake.items()[0].editable, false, 'files are locked after the start');
});

test('path import is only offered when the server allows it; missing drafts say so plainly', async () => {
  const off = fakeServer();
  const a = await ready(off);
  off.calls.length = 0;
  await a.importPath('/tmp/son');
  assert.equal(off.calls.length, 0);

  const on = fakeServer({ allowPathImport: true });
  const b = await ready(on);
  on.calls.length = 0;
  await b.importPath('  /tmp/son  ');
  assert.deepEqual(on.calls[0].body, { path: '/tmp/son' });
  assert.equal(on.calls[0].path, '/api/sources/cf-son/import-path');

  const c = S.createIntake({ fetch: fakeServer().fetch, origin: ORIGIN, XHR: null });
  await c.load('cf-none');
  assert.equal(c.state.loadError.missing, true);
  assert.match(c.state.loadError.text, /찾을 수 없어요/);
});

test('draft form checks name, kind and basic facts before calling the server; usage scope is optional', async () => {
  const server = fakeServer();
  const intake = S.createIntake({ fetch: server.fetch, origin: ORIGIN, XHR: null });
  const res = await intake.createDraft({ displayName: ' ', subjectKind: '', scope: '' });
  assert.deepEqual(Object.keys(res.errors).sort(), ['age', 'displayName', 'gender', 'job', 'subjectKind']);
  assert.equal(server.calls.length, 0);
});

test('a draft with only a memo sends the team-internal scope, and carries the model mode and auto-run choice', async () => {
  const server = fakeServer();
  const intake = S.createIntake({ fetch: server.fetch, origin: ORIGIN, XHR: null });
  await intake.createDraft({ displayName: '손흥민', subjectKind: 'PUBLIC_FIGURE', age: '34세', gender: '남성', job: '축구선수', notes: ' 발표용 ', modelMode: 'TRAIN', autoReview: false });
  const body = server.calls[0].body;
  assert.deepEqual(body.usageBasis, { scope: S.DEFAULT_SCOPE, notes: '발표용' });
  assert.equal(body.modelMode, 'TRAIN');
  assert.equal(body.autoReview, false);
  assert.deepEqual(intake.settings(), { modelMode: 'TRAIN', autoReview: false, videoTier: 'none', signaturePose: null }, 'the summary shows what the server holds');

  const other = fakeServer();
  const b = S.createIntake({ fetch: other.fetch, origin: ORIGIN, XHR: null });
  await b.createDraft({ displayName: '엄마', subjectKind: 'PRIVATE_PERSON', age: '58세', gender: '여성', job: '교사', modelMode: 'SOMETHING' });
  assert.equal(other.calls[0].body.modelMode, 'PROMPT_ONLY', 'unknown modes fall back to the default');
  assert.equal(other.calls[0].body.autoReview, true, 'auto-run is on unless switched off');
  assert.equal(other.calls[0].body.usageBasis.scope, '팀 내부 사용');
});

test('after the start, progress and chat readiness are read; the chat link appears only when the server says ready', async () => {
  const server = fakeServer();
  const intake = await ready(server);
  intake.addFiles([file('a.txt')]);
  await settle();
  assert.equal(intake.state.chat, null, 'nothing is asked about chat before the start');
  server.db.done = 3;
  await intake.finalize();
  assert.deepEqual(intake.state.character.progress, { done: 3, total: 12 });
  assert.equal(intake.state.character.running, true);
  assert.deepEqual(intake.state.chat, { ready: false, reason: '프롬프트를 아직 만들고 있어요.' });
  server.db.done = 12;
  server.db.chatReady = true;
  await intake.progress();
  assert.equal(intake.state.chat.ready, true);
  assert.equal(intake.state.character.running, false);

  const old = fakeServer();
  const b = await ready(old);
  b.addFiles([file('a.txt')]);
  await settle();
  old.db.noChat = true;
  await b.finalize();
  assert.deepEqual(b.state.chat, { ready: false, unavailable: true, reason: '' }, 'a server without the chat API stops the polling quietly');
  old.db.detail = { pendingGates: ['G0'] };
  await b.progress();
  assert.equal(b.state.character.awaiting, true);
});

test('long file lists are summarised by kind and register, counting files that still need a look', () => {
  const it = (kind, register, tone, phase) => ({ meta: { kind, register }, tone, phase });
  const sum = S.fileSummary([it('INTERVIEW', 'FORMAL', 'ok'), it('INTERVIEW', 'FORMAL', 'ok'), it('TRANSCRIPT', 'CASUAL', 'wait'), it('KAKAO_EXPORT', 'CASUAL', 'fail', 'rejected')]);
  assert.equal(sum.total, 3, 'files the page refused are not counted');
  assert.equal(sum.ready, 2);
  assert.equal(sum.attention, 1);
  assert.deepEqual(sum.kinds, [['인터뷰', 2], ['받아쓰기', 1]]);
  assert.deepEqual(sum.registers, [['공식 자리', 2], ['캐주얼 자리', 1]]);
});

test('the sidebar lists characters with a motif marker and links into the factory screen', () => {
  const html = S.sideHTML([{ id: 'cf-son', name: '손흥민', origin: 'SOURCE', progress: { done: 4, total: 18 }, awaitingHuman: true }, { id: 'cf-a', name: '하진우', origin: 'CREATED', progress: { done: 18, total: 18 } }], 'dark');
  assert.ok(html.includes('href="factory.html#c/cf-son"'));
  assert.equal((html.match(/class="fd-org"/g) || []).length, 1, 'only the motif character is marked');
  assert.ok(html.includes('<span class="st wait">') && html.includes('<span class="st ok">'));
  assert.ok(html.includes('data-theme="dark" aria-pressed="true"'));
  assert.ok(html.includes('href="sources.html" aria-current="page"'));
  assert.ok(S.sideHTML([{ id: 'cf-20261109-son-motif', name: '' }], 'system').includes('이름 미정 · son-motif (11/9)'), 'unnamed characters read like the factory sidebar');
});

test('the page sits in the factory shell, offers the model mode and auto-run switch, and keeps the memo optional', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'sources.html'), 'utf8');
  assert.ok(html.includes('class="fd-shell"') && html.includes('data-side'));
  assert.ok(!/name="scope"/.test(html), 'no required usage scope field');
  assert.ok(/<details class="src-memo">[\s\S]*name="notes"/.test(html), 'the memo is folded and optional');
  assert.ok(!/동의/.test(html), 'no consent fields');
  const modes = Array.from(html.matchAll(/name="modelMode" value="([A-Z_]+)"( checked)?/g)).map((m) => m[1] + (m[2] ? '*' : ''));
  assert.deepEqual(modes, ['PROMPT_ONLY*', 'BIND_EXISTING', 'TRAIN']);
  assert.ok(/role="switch" checked/.test(html), 'auto-run is on by default');
  assert.ok(html.includes('data-chat-link'));
});

test('the page has every region the script reads, keeps copy free of code names, and the factory links to it', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'sources.html'), 'utf8');
  const js = fs.readFileSync(path.join(__dirname, '..', 'shared', 'sources.js'), 'utf8');
  const mountSrc = js.slice(js.indexOf('function mount('));
  const wanted = new Set(Array.from(mountSrc.matchAll(/\$\('\[(data-[a-z-]+)(?:="([a-z]+)")?\]'\)/g)).map((m) => m[2] ? m[1] + '="' + m[2] + '"' : m[1]));
  assert.ok(wanted.size >= 15);
  wanted.forEach((attr) => assert.ok(html.includes(attr), attr));
  const visible = html.replace(/<script[\s\S]*?<\/script>/g, '').replace(/<[^>]+>/g, ' ');
  ['PUBLIC_FIGURE', 'KAKAO_EXPORT', 'textId', 'canFinalize', 'API', 'S3'].forEach((w) => assert.ok(!visible.includes(w), w));
  assert.ok(html.indexOf('foundry-tokens.css') < html.indexOf('sources.css'));
  const flow = fs.readFileSync(path.join(__dirname, '..', 'shared', 'flow.js'), 'utf8');
  assert.ok(flow.includes('href="sources.html"'));
  assert.equal(typeof S.mount({ root: {} }).destroy, 'function');
});

test('a name that is not in the source gets the server problem as is and a one-tap chip with the found speaker', async () => {
  const server = fakeServer();
  const intake = await ready(server);
  const [key] = intake.addFiles([file('casual_vlog.txt')]);
  await settle();
  assert.equal(intake.items()[0].speaker, '', 'no chip while the speaker matches the source');
  await intake.editFile(key, 'subjectSpeaker', 'QA테스트 손흥민');
  await settle();
  let item = intake.items()[0];
  assert.equal(item.status, '확인이 필요해요');
  assert.deepEqual(item.problems, ["원문에서 'QA테스트 손흥민'이라는 화자를 찾지 못했어요. 원문에 있는 이름: 손흥민, 기자"], 'server problems are shown word for word');
  assert.equal(item.speaker, '손흥민');
  await intake.editFile(key, 'subjectSpeaker', item.speaker);
  await settle();
  item = intake.items()[0];
  assert.equal(item.status, '준비됐어요');
  assert.equal(item.speaker, '');
  assert.equal(S.ro('손흥민'), '으로');
  assert.equal(S.ro('하나'), '로');
  assert.equal(S.ro('지민일'), '로', 'ㄹ 받침 takes 로');
});

test('server content inference wins over automatic filename hints', async () => {
  const server = fakeServer();
  server.db.suggest = { kind: 'TRANSCRIPT', register: 'CASUAL' };
  const intake = await ready(server);
  server.calls.length = 0;
  intake.addFiles([file('notes.txt')]);
  await settle();
  const complete = server.calls.find((c) => c.path.endsWith('/complete'));
  assert.equal(complete.body.kind, null, 'with no hint in the name the server reads the content first');
  assert.equal(complete.body.register, null);
  const patch = server.calls.find((c) => c.method === 'PATCH');
  assert.ok(patch, 'the content guess is saved');
  assert.equal(patch.body.kind, 'TRANSCRIPT');
  assert.equal(patch.body.register, 'CASUAL');
  assert.equal(patch.body.subjectSpeaker, '손흥민', 'the speaker the server filled is kept');

  const named = fakeServer();
  named.db.suggest = { kind: 'TRANSCRIPT', register: 'CASUAL' };
  const b = await ready(named);
  named.calls.length = 0;
  b.addFiles([file('interview_press.txt')]);
  await settle();
  assert.ok(!named.calls.some((c) => c.method === 'PATCH' && c.body.kind !== 'INTERVIEW'), 'a hint in the file name wins');
  assert.equal(b.items()[0].meta.kind, 'INTERVIEW');
});

test('an older server without suggestions still gets the display name as the speaker', async () => {
  const server = fakeServer({ legacy: true });
  const intake = await ready(server);
  server.calls.length = 0;
  intake.addFiles([file('a.txt')]);
  await settle();
  const patch = server.calls.find((c) => c.method === 'PATCH');
  assert.equal(patch.body.subjectSpeaker, '손흥민');
  assert.equal(intake.items()[0].speaker, '');
});

test('unstarted drafts are offered to resume, and a server without that list stays quiet', async () => {
  const server = fakeServer();
  const intake = S.createIntake({ fetch: server.fetch, origin: ORIGIN, XHR: null });
  assert.equal(await intake.drafts(), null);
  server.db.drafts = [{ characterId: 'cf-20261110-motif-55f4', displayName: 'QA테스트 손흥민', createdAt: '2026-11-10T05:10:00+09:00', files: 2 }, { displayName: 'no id' }];
  const list = await intake.drafts();
  assert.deepEqual(list.map((x) => x.characterId), ['cf-20261110-motif-55f4'], 'rows without an id are dropped');
  assert.match(S.shortDate('2026-11-10T05:10:00+09:00'), /^11\/(9|10)$/);
  assert.equal(S.shortDate(''), '');
});

test('progress reads the shared status, chat readiness and goal when the server sends them', async () => {
  const server = fakeServer();
  const intake = await ready(server);
  intake.addFiles([file('a.txt')]);
  await settle();
  server.db.detail = { status: 'chat_ready', statusLabel: '대화 가능', chatReady: true, goal: { label: '대화 가능까지', done: 5, total: 5 }, displayName: '손흥민' };
  await intake.finalize();
  const c = intake.state.character;
  assert.equal(c.status, 'chat_ready');
  assert.equal(c.chatReady, true);
  assert.deepEqual(c.goal, { label: '대화 가능까지', done: 5, total: 5 });
  assert.equal(c.displayName, '손흥민');
  server.db.detail = {};
  await intake.progress();
  assert.equal(intake.state.character.status, null, 'an older server leaves the old signals in charge');
  assert.equal(intake.state.character.chatReady, null);
});

test('the sidebar prefers the shared name and status like the factory list, and hides archived characters', () => {
  const html = S.sideHTML([
    { id: 'cf-20261110-motif-cd9b', name: '', displayName: '손흥민', status: 'chat_ready', statusLabel: '대화 가능', goal: { done: 5, total: 5 }, progress: { done: 5, total: 16 }, origin: 'SOURCE' },
    { id: 'cf-old', name: '테스트', archived: true }
  ], 'system');
  assert.ok(html.includes('>손흥민<'));
  assert.ok(html.includes('<span class="st ok">'));
  assert.ok(html.includes('<small>대화 가능</small>') && !html.includes('5/16'), 'shows the shared status, not a step count');
  assert.ok(!html.includes('테스트'), 'archived characters stay out of the list');
});

test('file cards hide the internal text id, the path import is folded under 고급, and the switch keeps its size', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'sources.html'), 'utf8');
  const js = fs.readFileSync(path.join(__dirname, '..', 'shared', 'sources.js'), 'utf8');
  const css = fs.readFileSync(path.join(__dirname, '..', 'shared', 'sources.css'), 'utf8');
  assert.ok(!js.includes("fld('textId'"), 'no 원문 이름 field on the card');
  assert.ok(!/영문, 숫자, -, _로 적어요/.test(js));
  assert.match(html, /<details class="src-adv" data-adv hidden>\s*<summary>고급<\/summary>\s*<form class="src-path" data-path>/);
  assert.ok(/:not\(\[type="checkbox"\]\),\.src textarea/.test(css), 'the full-width field rule skips the switch');
  const note = (html.match(/id="src-auto-h">([^<]*)</) || [])[1];
  assert.ok(note && note.length <= 40, 'the switch has a one-line note');
  assert.ok(html.includes('data-start-note'));
  assert.ok(html.includes('data-resume') && html.includes('data-title') && html.includes('data-crumb'));
  assert.ok(!/대화 테스트/.test(html + js), 'the chat page is called 대화해 보기 everywhere');
});

// ---- 4차 약속 5: 영상 등급과 사진 ----
async function tierDraft(server, videoTier) {
  const intake = S.createIntake({ fetch: server.fetch, origin: ORIGIN, XHR: null });
  const sig = videoTier === 'none' ? {} : { sigTitle: '찰칵 세리머니', sigMotion: '두 손으로 카메라 모양을 만든다.' };
  await intake.createDraft(Object.assign({ displayName: '손흥민', subjectKind: 'PUBLIC_FIGURE', age: '34세', gender: '남성', job: '축구선수', videoTier }, sig));
  return intake;
}
const photo = (name, size) => file(name || 'face.jpg', size == null ? 5000 : size, 'image/jpeg');

test('five video tiers with plain names, no clip counts, and the same cards on both screens', () => {
  assert.deepEqual(S.VIDEO_TIERS.map((t) => t[0]), ['none', 'light', 'standard', 'pro', 'max']);
  assert.deepEqual(S.VIDEO_TIERS.map((t) => t[1]), ['영상 없이', '라이트', '스탠다드', '프로', '맥스']);
  const html = S.tierCardsHTML('videoTier', 'none');
  const visible = html.replace(/<[^>]+>/g, ' ');
  assert.ok(!/\d/.test(visible), 'no numbers on the cards');
  assert.ok(!/\d+\s*개|클립/.test(html), 'no clip counts anywhere, not even in labels');
  assert.equal((html.match(/type="radio"/g) || []).length, 5);
  assert.match(html, /value="none" checked/, 'no video is the default');
  assert.match(visible, /말하기·파이팅·웃음·인사와 시그니처를 만들어요/);
  assert.match(visible, /가장 오래 걸리고 비용도 가장 커요/);
  assert.ok(!S.tierCardsHTML('x', 'light', { paidOnly: true }).includes('value="none"'));
  assert.equal(S.tierOf('ultra'), 'none');
  const Flow = require('../shared/flow.js');
  assert.deepEqual(Flow.VIDEO_TIERS, S.VIDEO_TIERS, 'the factory screen uses the same table');
  assert.equal(Flow.tierCardsHTML('videoTierPick', 'pro', { paidOnly: true }), S.tierCardsHTML('videoTierPick', 'pro', { paidOnly: true }), 'and the same card markup');
});

test('the 영상 section sits after the model mode with a cost note, and the summary can change it before the start', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'sources.html'), 'utf8');
  const mode = html.indexOf('name="modelMode" value="TRAIN"');
  const tier = html.indexOf('data-tier-cards');
  assert.ok(mode > 0 && tier > mode && tier < html.indexOf('class="src-switch"'), 'after 모델 준비 방식, before the auto-run switch');
  assert.match(html, /<legend>영상<\/legend>/);
  assert.match(html, /영상 단계는 비용이 들어요/);
  assert.ok(html.includes('data-sum-video') && html.includes('data-act="tier-edit"') && html.includes('data-tier-edit'));
  assert.match(html, /영상용 사진/);
  assert.match(html, /얼굴이 잘 보이는 사진 1장 이상/);
  assert.match(html, /data-photo-picker multiple accept="[^"]*\.webp/);
});

test('a chosen tier goes with the draft; photos use the same upload and the start waits for one ready photo', async () => {
  const server = fakeServer();
  const intake = await tierDraft(server, 'light');
  assert.equal(server.calls[0].body.videoTier, 'light');
  assert.equal(intake.settings().videoTier, 'light');
  intake.addFiles([file('interview.txt')]);
  await settle();
  let st = intake.startState();
  assert.equal(st.ready, false);
  assert.ok(st.needPhoto);
  assert.ok(st.reasons.some((x) => /얼굴이 잘 보이는 인물사진 한 장/.test(x)), st.reasons.join(' / '));
  server.calls.length = 0;
  intake.addFiles([photo('face.jpg')]);
  assert.equal(intake.photoItems()[0].tone, 'run', 'the photo is on its way');
  assert.equal(intake.startState().ready, false, 'not while the photo is still going up');
  await settle();
  assert.deepEqual(seq(server.calls).filter((s) => !s.includes('/api/characters/')), ['POST /api/sources/cf-son/files', 'PUT /api/sources/cf-son/files/f2/content', 'POST /api/sources/cf-son/files/f2/complete', 'GET /api/sources/cf-son'], 'no PATCH: photos have no fields to fix');
  assert.equal(server.calls[0].body.contentType, 'image/jpeg');
  assert.deepEqual(server.calls[2].body, {}, 'the photo check goes with an empty body');
  const photos = intake.photoItems();
  assert.equal(photos.length, 1);
  assert.equal(photos[0].status, '준비됐어요');
  assert.deepEqual(intake.items().map((i) => i.filename), ['interview.txt'], 'photos are not listed as source texts');
  st = intake.startState();
  assert.equal(st.ready, true, st.reasons.join(' / '));
  await intake.finalize();
  assert.ok(server.calls.some((c) => c.path === '/api/sources/cf-son/finalize'));
});

test('a photo alone is not a source text, and a server photo rule is shown once in its own words', async () => {
  const server = fakeServer({ photoRule: true });
  const intake = await tierDraft(server, 'pro');
  intake.addFiles([photo('face.webp')]);
  await settle();
  assert.deepEqual(intake.startState().reasons.filter((x) => /원문/.test(x)), ['대화나 글이 담긴 원문을 하나 이상 올려 주세요.'], 'a photo alone is not a source text, said once');
  intake.removeFile(intake.photoItems()[0].key);
  await settle();
  intake.addFiles([file('interview.txt')]);
  await settle();
  const reasons = intake.startState().reasons;
  assert.deepEqual(reasons.filter((x) => /사진/.test(x)), ['영상을 만들려면 사진이 1장 이상 있어야 해요.'], 'no second sentence saying the same thing');
});

test('the photo box refuses other files, big photos stay out, and photos can still be added after the start', async () => {
  const server = fakeServer();
  const intake = await tierDraft(server, 'standard');
  intake.addFiles([file('notes.txt'), photo('huge.jpg', S.PHOTO_MAX_BYTES + 1)], { photoOnly: true });
  const refused = intake.photoItems();
  assert.deepEqual(refused.map((p) => p.status), ['받을 수 없는 사진', '받을 수 없는 사진']);
  assert.match(refused[0].problems[0], /jpg, png, webp/);
  assert.match(refused[1].problems[0], /15MB/);
  assert.equal(intake.items().length, 0, 'a text picked in the photo box does not become a source');
  refused.forEach((p) => intake.dismiss(p.key));
  intake.addFiles([file('interview.txt'), photo('face.png')]);
  await settle();
  await intake.finalize();
  server.calls.length = 0;
  intake.addFiles([file('more.txt'), photo('second.jpg')]);
  await settle();
  assert.deepEqual(server.calls.filter((c) => c.method === 'POST' && c.path.endsWith('/files')).map((c) => c.body.filename), ['second.jpg'], 'texts are locked after the start, photos are not');
  assert.equal(intake.photoItems().length, 2);
  assert.ok(intake.photoItems().every((p) => !p.removable), 'photos already in use cannot be removed after the start');
});

test('a video tier needs a signature pose: name and motion are required, the pose goes with the draft and can be saved later (D-0165)', async () => {
  const server = fakeServer();
  const intake = S.createIntake({ fetch: server.fetch, origin: ORIGIN, XHR: null });
  const base = { displayName: '손흥민', subjectKind: 'PUBLIC_FIGURE', age: '34세', gender: '남성', job: '축구선수', videoTier: 'light' };
  const missing = await intake.createDraft(base);
  assert.deepEqual(Object.keys(missing.errors).sort(), ['sigMotion', 'sigTitle']);
  assert.equal(server.calls.length, 0, 'nothing is sent without the pose');
  assert.deepEqual(intake.validateDraft(Object.assign({}, base, { videoTier: 'none' })), {}, 'no pose is asked without video');
  await intake.createDraft(Object.assign({}, base, { sigTitle: ' 찰칵 세리머니 ', sigMotion: '두 손으로 카메라 모양을 만든다.', sigWhen: '' }));
  assert.deepEqual(server.calls[0].body.signaturePose, { title: '찰칵 세리머니', motion: '두 손으로 카메라 모양을 만든다.', useWhen: '' });
  assert.equal(intake.settings().signaturePose.title, '찰칵 세리머니');
  server.calls.length = 0;
  assert.equal(await intake.setSignature({ title: '하트', motion: '손가락 하트를 내민다.', useWhen: '고마울 때' }), true);
  const call = server.calls.find((c) => c.method === 'PATCH');
  assert.deepEqual(call.body, { videoTier: 'light', signaturePose: { title: '하트', motion: '손가락 하트를 내민다.', useWhen: '고마울 때' } });
  assert.equal(await intake.setSignature({ title: '하트', motion: ' ' }), false, 'a pose without motion is not sent');
  assert.equal(S.sigOf({ title: 'a' }), null);
});

test('the tier can be changed before the start, and an older server says so plainly', async () => {
  const server = fakeServer();
  const intake = await tierDraft(server, 'none');
  assert.equal(await intake.setTier('pro'), true);
  const call = server.calls.find((c) => c.method === 'PATCH');
  assert.equal(call.path, '/api/sources/cf-son/settings');
  assert.deepEqual(call.body, { videoTier: 'pro' });
  assert.equal(intake.settings().videoTier, 'pro');
  const old = fakeServer({ noSettings: true });
  const b = await tierDraft(old, 'none');
  assert.equal(await b.setTier('light'), false);
  assert.equal(b.state.error, '이 서버에서는 아직 영상 등급을 바꿀 수 없어요.');
  assert.equal(b.settings().videoTier, 'none');
});

test('after the start the card shows chat first, then "영상 만드는 중 · 라이트", then a chat link that mentions video', async () => {
  const before = S.doneView({ status: 'running', statusLabel: '만드는 중', videoTier: 'light', videoStatus: 'none' }, { ready: false }, { auto: true, tier: 'light' });
  assert.equal(before.ready, false);
  assert.equal(before.video.show, false, 'no video line until chat works');
  assert.match(before.body, /영상은 대화가 된 뒤에 이어서 만들어요/);
  const making = S.doneView({ chatReady: true, videoTier: 'light', videoStatus: 'making' }, { ready: true }, { tier: 'light' });
  assert.equal(making.title, '대화 가능');
  assert.deepEqual(making.video, { show: true, text: '영상 만드는 중 · 라이트', tone: 'run', making: true });
  assert.equal(making.chatLabel, '대화해 보기');
  assert.match(making.body, /대화는 지금 해 볼 수 있어요/);
  const waiting = S.doneView({ chatReady: true, videoTier: 'light', videoStatus: 'none' }, null, {});
  assert.equal(waiting.video.text, '영상 만드는 중 · 라이트', 'the server has not flipped to making yet, the line already says so');
  const done = S.doneView({ chatReady: true, videoTier: 'light', videoStatus: 'ready' }, null, {});
  assert.equal(done.chatLabel, '영상과 함께 대화해 보기');
  assert.match(done.body, /영상도 준비됐어요/);
  assert.equal(done.video.tone, 'ok');
  const failed = S.doneView({ chatReady: true, videoTier: 'max', videoStatus: 'failed' }, null, {});
  assert.equal(failed.chatLabel, '대화해 보기');
  assert.match(failed.body, /영상은 만들지 못했어요/);
  const none = S.doneView({ chatReady: true, videoTier: 'none', videoStatus: 'none' }, null, {});
  assert.equal(none.video.show, false);
  assert.match(none.body, /전체 제작 진행/, 'chat availability does not claim production completion');
  [before, making, done, failed].forEach((v) => assert.ok(!/\d+\s*개/.test(v.body + v.video.text), 'no counts'));
});

test('progress keeps reading until the video is ready or failed, and stops for servers without video fields', async () => {
  const server = fakeServer();
  const intake = await tierDraft(server, 'light');
  intake.addFiles([file('interview.txt'), photo()]);
  await settle();
  server.db.detail = { status: 'chat_ready', chatReady: true, videoTier: 'light', videoStatus: 'making', videoLabel: '' };
  server.db.chatReady = true;
  await intake.finalize();
  const c = intake.state.character;
  assert.equal(c.videoTier, 'light');
  assert.equal(c.videoStatus, 'making');
  assert.equal(S.wantsPoll(intake.state), true);
  server.db.detail.videoStatus = 'ready';
  await intake.progress();
  assert.equal(S.wantsPoll(intake.state), false);
  server.db.detail = { status: 'chat_ready', chatReady: true };
  await intake.progress();
  assert.equal(intake.state.character.videoStatus, null);
  assert.equal(S.wantsPoll(intake.state), false, 'an older server without videoStatus stops once chat works');
  assert.equal(S.wantsPoll({ finalized: { jobId: 'j' }, cid: 'x', character: { chatReady: false } }), true);
});

test('video text names the tier for known states, stays empty without video, and matches the factory screen', () => {
  assert.equal(S.videoText({ videoTier: 'pro', videoStatus: 'making', videoLabel: '영상을 만들고 있어요' }), '영상 만드는 중 · 프로');
  assert.equal(S.videoText({ videoTier: 'standard', videoStatus: 'ready' }), '영상 있음 · 스탠다드');
  assert.equal(S.videoText({ videoTier: 'none', videoStatus: 'none', videoLabel: '아직 영상이 없어요' }), '');
  assert.equal(S.videoText({}), '');
  const Flow = require('../shared/flow.js');
  const cases = [{}, { videoTier: 'light', videoStatus: 'none' }, { videoTier: 'max', videoStatus: 'failed' }, { videoTier: 'pro', videoStatus: 'odd', videoLabel: '확인 중' }];
  cases.forEach((c) => assert.equal(Flow.videoText(c), S.videoText(c)));
});

test('friend messenger and interview scenes are selectable and sent unchanged to the API', async () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'sources.html'), 'utf8');
  const select = html.match(/<select id="src-chapter"[\s\S]*?<\/select>/)[0];
  for (const chapter of ['FRIEND_CHAT', 'INTERVIEW']) {
    assert.ok(select.includes('value="' + chapter + '"'), chapter + ' is selectable');
    const server = fakeServer();
    const intake = S.createIntake({ fetch: server.fetch, origin: ORIGIN, XHR: null });
    await intake.createDraft({ displayName: '합성 인물', subjectKind: 'PRIVATE_PERSON', age: '30', gender: '여성', job: '작가', chapterTemplate: chapter, autoReview: true });
    assert.equal(server.db.draft.chapterTemplate, chapter);
    assert.equal(server.db.draft.autoReview, true);
  }
});

test('chat availability preserves failure, review, running states and incomplete progress', () => {
  for (const [status, tone] of [['failed', 'fail'], ['needs_review', 'wait'], ['running', 'run']]) {
    const view = S.doneView({ status, chatReady: true, goal: { label: '제작 진행', done: 4, total: 5 } }, { ready: true });
    assert.equal(view.ready, true);
    assert.equal(view.status, status);
    assert.equal(view.tone, tone);
    assert.equal(view.progress.done, 4);
    assert.equal(view.progress.total, 5);
    assert.match(view.body, /대화/);
  }
});

test('chat availability keeps polling while production or review is pending', () => {
  for (const status of ['running', 'needs_review']) {
    assert.equal(S.wantsPoll({ finalized: true, cid: 'synthetic', chat: { ready: true }, character: { status, chatReady: true } }), true);
  }
});

test('auto upload asks the server to infer content instead of confirming filename guesses', async () => {
  const server = fakeServer();
  server.db.suggest = {kind:'KAKAO_EXPORT',register:'CASUAL'};
  const intake=await ready(server);
  intake.addFiles([file('synthetic-interview.txt')]);
  await settle();
  const complete=server.calls.find(c=>c.path.endsWith('/complete'));
  assert.equal(complete.body.kind,null);
  assert.equal(complete.body.register,null);
  assert.equal(intake.items()[0].meta.kind,'KAKAO_EXPORT');
  assert.equal(intake.items()[0].meta.subjectSpeaker,'손흥민');
});

test('typing is kept across an older PATCH response and suggestion applies without erasing other fields', async () => {
  const server=fakeServer();
  let release, hold=false;
  const fetch=async (url,init)=>{
    const response=await server.fetch(url,init);
    if(hold && init?.method==='PATCH') {hold=false; await new Promise(r=>{release=r;});}
    return response;
  };
  const intake=await ready({fetch});
  const [key]=intake.addFiles([file('interview.txt')]);
  await settle();
  hold=true;
  const saving=intake.editFile(key,'kind','KAKAO_EXPORT');
  await settle();
  assert.equal(typeof intake.stageFile,'function','input events need a local draft before blur');
  intake.stageFile(key,'subjectSpeaker','새 대상');
  intake.stageFile(key,'userSpeaker','대화 상대');
  intake.stageFile(key,'register','FORMAL');
  release(); await saving;
  assert.equal(intake.items()[0].display.subjectSpeaker,'새 대상');
  assert.equal(intake.items()[0].display.userSpeaker,'대화 상대');
  assert.equal(intake.startState().ready,false,'unsaved input must not be finalized');
  await intake.editFile(key,'subjectSpeaker','손흥민');
  await settle();
  assert.equal(server.db.files[0].subjectSpeaker,'손흥민');
  assert.equal(server.db.files[0].userSpeaker,'대화 상대');
  assert.equal(server.db.files[0].register,'FORMAL');
});

test('a GET started before a new edit cannot replace the acknowledged metadata', async () => {
  const server=fakeServer();
  let hold=false,release;
  const fetch=async (url,init)=>{
    const response=await server.fetch(url,init);
    if(hold && init?.method==='GET' && url.endsWith('/api/sources/cf-son')) {
      hold=false;
      const data=structuredClone(await response.json());
      await new Promise(r=>{release=r;});
      return {...response,json:async()=>data};
    }
    return response;
  };
  const intake=await ready({fetch});
  const [key]=intake.addFiles([file('interview.txt')]); await settle();
  hold=true;
  const reading=intake.refresh(); await settle();
  await intake.editFile(key,'userSpeaker','기자');
  release(); await reading;
  assert.equal(intake.items()[0].display.userSpeaker,'기자');
});

test('actual input/change/suggest handlers keep all fields through delayed rerender', async () => {
  const server=fakeServer();
  const listeners={}, controls={};
  let release, hold=false;
  const fetch=async (url,init)=>{
    const result=await server.fetch(url,init);
    if(hold && init?.method==='PATCH') {hold=false; await new Promise(r=>{release=r;});}
    return result;
  };
  function node() {
    const children=new Map();
    return {dataset:{},classList:{toggle(){},remove(){}},style:{},firstChild:{dataset:{},style:{},setAttribute(){}},
      setAttribute(){},removeAttribute(){},remove(){},
      querySelector(s){if(!children.has(s))children.set(s,node());return children.get(s);},
      querySelectorAll(){return [];}};
  }
  const card=node(); card.dataset.key='u1';
  for(const field of ['kind','subjectSpeaker','userSpeaker','register']) {
    controls[field]={dataset:{field},value:'',id:'input-'+field,closest:()=>card,setAttribute(){},removeAttribute(){}};
  }
  card.querySelector('[data-body]').querySelectorAll=()=>Object.values(controls);
  const doc={querySelector:()=>null,createElement:()=>({firstChild:card}),activeElement:null,
    addEventListener:(name,fn)=>{listeners[name]=fn;},removeEventListener(){}};
  const mounted=S.mount({root:doc,fetch,XHR:null});
  await mounted.intake.createDraft({displayName:'손흥민',subjectKind:'PUBLIC_FIGURE',age:'34',gender:'남성',job:'선수'});
  mounted.intake.addFiles([file('interview.txt')]); await settle();
  hold=true;
  controls.kind.value='KAKAO_EXPORT'; listeners.change({target:controls.kind}); await settle();
  for(const [field,value] of [['subjectSpeaker','입력 중'],['userSpeaker','대화 상대'],['register','FORMAL']]) {
    controls[field].value=value; listeners.input({target:controls[field]});
  }
  release(); await settle();
  assert.equal(controls.subjectSpeaker.value,'입력 중');
  assert.equal(controls.userSpeaker.value,'대화 상대');
  assert.equal(controls.register.value,'FORMAL');
  const suggestion={dataset:{act:'use-speaker',name:'손흥민'},closest:()=>card};
  listeners.click({target:{closest:()=>suggestion}}); await settle();
  assert.equal(server.db.files[0].userSpeaker,'대화 상대');
  assert.equal(server.db.files[0].register,'FORMAL');
  assert.equal(controls.subjectSpeaker.value,'손흥민');
  mounted.destroy();
});

test('manual selections during upload override inference and failed metadata retries retain later edits', async () => {
  const server=fakeServer();
  server.db.suggest={kind:'TRANSCRIPT',register:'CASUAL'};
  const intake=await ready(server);
  const [key]=intake.addFiles([file('synthetic-interview.txt')]);
  intake.editFile(key,'kind','KAKAO_EXPORT');
  intake.editFile(key,'register','FORMAL');
  await settle();
  const complete=server.calls.find(c=>c.path.endsWith('/complete'));
  assert.equal(complete.body.kind,'KAKAO_EXPORT');
  assert.equal(complete.body.register,'FORMAL');
  assert.equal(intake.items()[0].meta.kind,'KAKAO_EXPORT');
  assert.equal(intake.items()[0].meta.register,'FORMAL');
  server.db.fail['PATCH /api/sources/cf-son/files/:id']=1;
  await intake.editFile(key,'userSpeaker','유지할 상대');
  assert.equal(intake.items()[0].saving,'error');
  await intake.editFile(key,'subjectSpeaker','손흥민'); await settle();
  assert.equal(server.db.files[0].userSpeaker,'유지할 상대');
  assert.equal(intake.items()[0].saving,'saved');
  assert.equal(intake.startState().ready,true);
});

test('when no speaker matches the display name, nobody is picked: the card lists names to choose and the start waits (A-03)', async () => {
  const server = fakeServer();
  server.db.speakers = [{ name: '엄마', lines: 4 }, { name: '나', lines: 4 }];
  server.db.suggest = { subjectSpeaker: null, userSpeaker: '나', subjectChoices: ['엄마'] };
  const intake = await ready(server);
  server.calls.length = 0;
  const [key] = intake.addFiles([file('kakao-mom.txt')]);
  await settle();
  const patch = server.calls.find((c) => c.method === 'PATCH');
  assert.equal(patch.body.subjectSpeaker, null, 'no speaker is chosen by line count or as the exporter');
  assert.equal(patch.body.userSpeaker, '나', 'the exporter is offered as the partner');
  let item = intake.items()[0];
  assert.equal(item.status, '확인이 필요해요');
  assert.equal(item.speaker, '', 'no one-tap chip suggests a guess');
  assert.deepEqual(item.choices, ['엄마']);
  assert.match(item.problems[0], /누가 이 사람인지 골라 주세요/);
  assert.equal(intake.startState().ready, false);
  await intake.pickSpeaker(key, '엄마');
  await settle();
  item = intake.items()[0];
  assert.equal(item.status, '준비됐어요');
  assert.deepEqual(item.choices, []);
  assert.equal(item.meta.subjectSpeaker, '엄마');
  assert.equal(item.meta.userSpeaker, '나');
  assert.equal(intake.startState().ready, true);
  assert.equal(S.suggestedSpeaker({ detectedSpeakers: [{ name: '나', lines: 9 }], suggested: { subjectSpeaker: null } }), '', 'the busiest speaker is never a fallback');
});
test('deleting a draft re-reads the resume list and the sidebar so it disappears from both (A-04)', async () => {
  const server = fakeServer();
  const intake = await ready(server);
  server.db.drafts = [{ characterId: 'cf-son', displayName: '손흥민', createdAt: '2026-11-10T05:10:00+09:00', files: 0 }];
  server.db.projects = [{ id: 'cf-son', displayName: '손흥민', status: 'draft', origin: 'SOURCE' }];
  await intake.drafts();
  await intake.projects();
  assert.equal(await intake.deleteDraft(), true);
  assert.deepEqual(intake.state.drafts, []);
  assert.deepEqual(intake.state.projects, []);
  assert.equal(intake.state.cid, null);
});

test('a path import comes back checked like an upload, and the partner speaker is filled (A-05)', async () => {
  const server = fakeServer({ allowPathImport: true });
  const intake = await ready(server);
  await intake.importPath('/tmp/qa/son-vlog.vtt');
  await settle();
  const item = intake.items()[0];
  assert.equal(item.status, '준비됐어요', 'no longer stuck on "다 올라가지 않았어요"');
  assert.equal(item.editable, true);
  assert.equal(item.meta.subjectSpeaker, '손흥민');
  assert.equal(item.meta.userSpeaker, '기자');
  assert.equal(intake.startState().ready, true);
});

test('long basic facts are caught per field, and an old server error does not linger (A-06)', async () => {
  const server = fakeServer();
  const intake = S.createIntake({ fetch: server.fetch, origin: ORIGIN, XHR: null });
  const base = { displayName: '손흥민', subjectKind: 'PUBLIC_FIGURE', age: '34세', gender: '남성', job: '축구선수' };
  intake.state.error = '입력한 내용을 확인해 주세요.';
  const res = await intake.createDraft(Object.assign({}, base, { age: '서른넷 그리고 몇 달 지났고 생일은 칠월이에요', job: '가'.repeat(61), background: '가'.repeat(401) }));
  assert.deepEqual(res.errors, { age: '나이는 20자까지 적을 수 있어요.', job: '하는 일은 60자까지 적을 수 있어요.', background: '한 줄 배경은 400자까지 적을 수 있어요.' });
  assert.equal(intake.state.error, null);
  assert.equal(server.calls.length, 0);
  const html = fs.readFileSync(path.join(__dirname, '..', 'sources.html'), 'utf8');
  assert.match(html, /name="age" maxlength="20"/);
  assert.match(html, /name="job" maxlength="60"/);
  assert.match(html, /name="background" rows="2" maxlength="400"/);
  assert.match(html, /data-err="background"/);
});

test('when progress changes state the sidebar is read again, and not on every unchanged poll (A-07)', async () => {
  const server = fakeServer();
  const intake = await ready(server);
  await intake.projects();
  server.db.detail = { status: 'running', chatReady: false };
  await intake.progress();
  const reads = () => server.calls.filter((c) => c.path === '/api/projects').length;
  const before = reads();
  await intake.progress();
  assert.equal(reads(), before, 'same state, no extra read');
  server.db.detail = { status: 'chat_ready', chatReady: true };
  await intake.progress();
  assert.equal(reads(), before + 1);
});

test('a photo the server cannot open shows an icon instead of a broken image (A-14)', async () => {
  const server = fakeServer();
  const intake = await ready(server);
  intake.state.draft.files = [{ fileId: 'p1', filename: 'broken.jpg', fileType: 'photo', status: 'problem', problems: ['열 수 없는 사진이에요. 이 사진을 지우고 다른 사진을 올려 주세요.'], url: '/x/broken.jpg' }];
  const [ph] = intake.photoItems();
  assert.equal(ph.thumb, '');
  assert.match(ph.problems[0], /지우고/);
  assert.equal(ph.removable, true);
});

test('fact sheet: one trimmed fact per line is sent only when filled, and limits match the server', async () => {
  const server = fakeServer();
  const intake = S.createIntake({ fetch: server.fetch, origin: ORIGIN, XHR: null });
  const base = { displayName: '손흥민', subjectKind: 'PUBLIC_FIGURE', age: '34세', gender: '남성', job: '축구선수' };
  await intake.createDraft(Object.assign({}, base, { factSheet: '  2025년 8월 LAFC로 이적했다.  \r\n\n  \n2024-25 시즌 7골 10도움\n' }));
  assert.deepEqual(server.calls[0].body.factSheet, ['2025년 8월 LAFC로 이적했다.', '2024-25 시즌 7골 10도움'], 'lines are kept verbatim apart from edge spaces');

  const blank = fakeServer();
  await S.createIntake({ fetch: blank.fetch, origin: ORIGIN, XHR: null }).createDraft(Object.assign({}, base, { factSheet: ' \n ' }));
  assert.equal('factSheet' in blank.calls[0].body, false, 'an empty sheet is not sent, so older servers keep accepting the draft');

  const lines = (n) => Array.from({ length: n }, (_, i) => '사실 ' + i).join('\n');
  assert.deepEqual(intake.validateDraft(Object.assign({}, base, { factSheet: lines(S.FACT_SHEET_MAX_LINES) })), {});
  assert.deepEqual(intake.validateDraft(Object.assign({}, base, { factSheet: lines(S.FACT_SHEET_MAX_LINES + 1) })), { factSheet: '사실은 40줄까지 적을 수 있어요.' });
  assert.deepEqual(intake.validateDraft(Object.assign({}, base, { factSheet: '짧은 사실\n' + '가'.repeat(301) })), { factSheet: '사실 2번째 줄은 300자까지 적을 수 있어요.' });
});
