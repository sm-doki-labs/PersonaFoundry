'use strict';
// 원문으로 새 캐릭터 화면(sources.js)의 검사. 계획 §2 출처 API를 흉내 내는 가짜 서버를 fetch로 넣는다. 네트워크·브라우저 없음.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const S = require('../shared/sources.js');

const ORIGIN = 'http://factory.test';

// 계획 §2 계약만 따르는 메모리 서버. 부른 순서를 calls에 남긴다.
function fakeServer(opts) {
  const o = Object.assign({ store: 'local', allowPathImport: false }, opts || {});
  const calls = [];
  const db = { draft: null, files: [], seq: 0, canFinalize: false, problems: ['원문 파일을 하나 이상 올려 주세요.'], fail: {} };
  const json = (status, body) => ({ ok: status >= 200 && status < 300, status, headers: { get: () => 'application/json' }, json: async () => body });
  function view() {
    return { characterId: 'cf-son', subject: db.draft.subject, usageBasis: db.draft.usageBasis, store: o.store, allowPathImport: o.allowPathImport, files: db.files.map((f) => Object.assign({}, f)), problems: db.problems.slice(), canFinalize: db.canFinalize };
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
      db.draft = { subject: { displayName: body.displayName, kind: body.subjectKind }, usageBasis: body.usageBasis, chapterTemplate: body.chapterTemplate };
      return json(200, { characterId: 'cf-son' });
    }
    if (method === 'GET' && u.pathname === '/api/sources/cf-son') return db.draft ? json(200, view()) : json(404, { detail: 'Not Found' });
    if (method === 'GET' && /^\/api\/sources\/[^/]+$/.test(u.pathname)) return json(404, { detail: 'Not Found' });
    if (method === 'POST' && u.pathname === '/api/sources/cf-son/files') {
      const fileId = 'f' + (++db.seq);
      db.files.push({ fileId, filename: body.filename, size: body.size, sha256: '', status: 'pending', textId: null, kind: null, register: null, subjectSpeaker: null, userSpeaker: null, date: null, sourceUrl: null, problems: [] });
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
      Object.assign(f, body, { status: 'ready', sha256: 'h' + m[1] });
      db.canFinalize = true;
      db.problems = [];
      return json(200, Object.assign({}, f));
    }
    if ((m = /^\/api\/sources\/cf-son\/files\/(f\d+)$/.exec(u.pathname))) {
      const f = db.files.find((x) => x.fileId === m[1]);
      if (method === 'PATCH') { Object.assign(f, body); return json(200, Object.assign({}, f)); }
      if (method === 'DELETE') { db.files = db.files.filter((x) => x !== f); if (!db.files.length) { db.canFinalize = false; db.problems = ['원문 파일을 하나 이상 올려 주세요.']; } return { ok: true, status: 204, json: async () => null }; }
    }
    if (method === 'POST' && u.pathname === '/api/sources/cf-son/finalize') return json(200, { jobId: 'job-1' });
    if (method === 'DELETE' && u.pathname === '/api/sources/cf-son') { db.draft = null; db.files = []; return { ok: true, status: 204, json: async () => null }; }
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
  assert.ok(S.checkFile(file('photo.png')));
  assert.ok(S.checkFile(file('big.txt', S.MAX_BYTES + 1)));
  assert.equal(S.checkFile(file('a.vtt')), null);
});

test('local store: draft, then files → PUT with cookies to our server → complete with the suggested meta', async () => {
  const server = fakeServer();
  const intake = await ready(server);
  assert.deepEqual(server.calls[0].body, { displayName: '손흥민', subjectKind: 'PUBLIC_FIGURE', usageBasis: { scope: '최종 발표 시연', notes: '공개 인터뷰만' }, knownFacts: { age: '34세', gender: '남성', job: '축구선수', background: '' } });
  server.calls.length = 0;
  intake.addFiles([file('KakaoTalk_son.txt', 3000)]);
  await settle();
  assert.deepEqual(seq(server.calls), ['POST /api/sources/cf-son/files', 'PUT /api/sources/cf-son/files/f1/content', 'POST /api/sources/cf-son/files/f1/complete', 'GET /api/sources/cf-son']);
  assert.deepEqual(server.calls[0].body, { filename: 'KakaoTalk_son.txt', size: 3000, contentType: 'text/plain' });
  const put = server.calls[1];
  assert.equal(put.url, '/api/sources/cf-son/files/f1/content');
  assert.equal(put.credentials, 'same-origin');
  assert.deepEqual(put.headers, { 'Content-Type': 'application/octet-stream' });
  assert.deepEqual(server.calls[2].body, { textId: 'kakaotalk_son', kind: 'KAKAO_EXPORT', register: 'CASUAL', subjectSpeaker: '손흥민', userSpeaker: null, date: null, sourceUrl: null });
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
  assert.equal(complete.body.kind, 'TRANSCRIPT');
  assert.equal(complete.body.register, 'CASUAL');
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
  intake.addFiles([file('photo.png'), file('ok.txt')]);
  await settle();
  assert.ok(!server.calls.some((c) => c.body && c.body.filename === 'photo.png'));
  const bad = intake.items().find((i) => i.filename === 'photo.png');
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

test('draft form checks name, kind and scope before calling the server', async () => {
  const server = fakeServer();
  const intake = S.createIntake({ fetch: server.fetch, origin: ORIGIN, XHR: null });
  const res = await intake.createDraft({ displayName: ' ', subjectKind: '', scope: '' });
  assert.deepEqual(Object.keys(res.errors).sort(), ['age', 'displayName', 'gender', 'job', 'scope', 'subjectKind']);
  assert.equal(server.calls.length, 0);
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
