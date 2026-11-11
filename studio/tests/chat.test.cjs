'use strict';
// 대화 테스트 화면(chat.js)의 검사. 계획 2차 약속 1 대화 API를 흉내 내는 가짜 서버를 fetch로 넣는다. 네트워크·유료 모델 호출 없음.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const C = require('../shared/chat.js');

const CID = 'cf-son';
const SCENARIOS = [
  { id: 'greet', title: '첫인사·일상', turns: ['안녕하세요!', '오늘 뭐 했어요?', '저녁은 드셨어요?'] },
  { id: 'tease', title: '칭찬·장난', turns: ['오늘 경기 최고였어요', '근데 머리 좀 바꾸셨죠?'] }
];
const META = {
  characterId: CID, name: '손흥민', origin: 'SOURCE', ready: true, reason: '', promptRev: 'pv3', chapterRev: 'cs1',
  model: { via: 'studio', model: 'gemini-3.8-flash' }, temperature: 0.8, scenarios: SCENARIOS,
  samples: [{ scenarioId: 'greet', title: '첫인사·일상', turns: [{ user: '안녕하세요!', reply: '안녕하세요, 반가워요.' }] }]
};

// 약속 1만 따르는 메모리 서버. 부른 순서를 calls에 남긴다. hold를 켜면 답을 붙잡아 두고 release로 푼다.
function fakeServer(opts) {
  const o = Object.assign({ meta: META }, opts || {});
  const calls = [];
  const sessions = new Map();
  const fail = [];
  const held = [];
  let hold = false;
  const json = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
  async function fetch(url, init) {
    const method = (init && init.method) || 'GET';
    const body = init && typeof init.body === 'string' ? JSON.parse(init.body) : null;
    calls.push({ method, url: String(url), body, credentials: init && init.credentials });
    if (method === 'GET' && url === '/api/characters/' + CID + '/chat/meta') {
      if (o.metaFail && o.metaFail.length) { const f = o.metaFail.shift(); if (f === 'network') throw new TypeError('Failed to fetch'); return json(f, { detail: '잠깐 문제가 있었어요.' }); }
      return json(200, o.meta);
    }
    const root = '/api/characters/' + CID + '/chat/sessions';
    if (url === root) return json(200, { sessions: [...sessions.values()] });
    if (url.startsWith(root + '/')) {
      const id = url.split('/').pop(), old = sessions.get(id);
      if (method === 'GET') return old ? json(200, old) : json(404, {});
      if (old && JSON.stringify(old.messages) === JSON.stringify(body.messages)) return json(200, old);
      if ((old ? old.revision : 0) !== body.revision) return json(409, {});
      const data = { id, revision: body.revision + 1, messages: body.messages };
      sessions.set(id, data);
      return json(200, data);
    }
    if (method === 'GET') return json(404, { detail: 'Not Found' });
    if (method === 'POST' && url === '/api/characters/' + CID + '/chat') {
      if (fail.length) { const f = fail.shift(); return json(f.status, { detail: f.detail }); }
      const userText = body.messages[body.messages.length - 1].content;
      const answer = { reply: '답: ' + userText, ms: 1234, rejected: [], model: 'gemini-3.8-flash' };
      if (!hold) return json(200, answer);
      return new Promise((resolve, reject) => {
        const signal = init && init.signal;
        const item = { resolve: () => resolve(json(200, answer)) };
        held.push(item);
        if (signal) signal.addEventListener('abort', () => { const e = new Error('aborted'); e.name = 'AbortError'; reject(e); });
      });
    }
    return json(404, { detail: 'Not Found' });
  }
  return {
    fetch, calls, fail, held,
    hold(on) { hold = on; },
    release() { const h = held.shift(); if (h) h.resolve(); },
    posts() { return calls.filter((c) => c.method === 'POST'); }
  };
}
function memoryStorage() {
  const m = new Map();
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k), map: m };
}
async function settle() { for (let i = 0; i < 40; i++) await new Promise((r) => setImmediate(r)); }
async function open(server, extra) {
  const chat = C.createChat(Object.assign({ fetch: server.fetch, characterId: CID, gap: 0 }, extra || {}));
  await chat.load();
  return chat;
}
const talk = (chat) => chat.state.messages.map((m) => m.role + ':' + m.content);

test('helpers: seconds per reply, revision labels, route, rejected count', () => {
  assert.equal(C.seconds(1234), '1.2초');
  assert.equal(C.seconds(980), '1.0초');
  assert.equal(C.seconds(45), '0.0초');
  assert.equal(C.seconds(83000), '1분 23초');
  assert.equal(C.seconds(null), '');
  assert.equal(C.revLabel('pv3'), '3판');
  assert.equal(C.revLabel(''), '');
  assert.equal(C.routeId('#c/cf-20261110-motif-8e7b'), 'cf-20261110-motif-8e7b');
  assert.equal(C.routeId('#c/a%20b'), 'a b');
  assert.equal(C.routeId('#all'), null);
  assert.equal(C.rejectedCount([{ attempt: 1, reason: '작성 메모' }]), 1);
  assert.equal(C.rejectedCount(2), 2);
  assert.equal(C.rejectedCount(false), 0);
  assert.equal(C.viaLabel('studio'), 'AI Studio');
  assert.ok(C.isMotif('SOURCE'));
  assert.ok(!C.isMotif('CREATED'));
});

test('send: POSTs the whole conversation, keeps the reply with its time, and ignores sends while waiting', async () => {
  const server = fakeServer();
  const chat = await open(server);
  assert.equal(chat.state.phase, 'ready');
  assert.equal(await chat.send('   '), false, 'blank text is not sent');
  assert.equal(await chat.send('안녕하세요'), true);
  const first = server.posts()[0];
  assert.equal(first.url, '/api/characters/cf-son/chat');
  assert.equal(first.credentials, 'same-origin');
  assert.deepEqual(first.body, { messages: [{ role: 'user', content: '안녕하세요' }] }, 'only messages are sent; the server picks the model');
  const reply = chat.state.messages[1];
  assert.equal(reply.role, 'assistant');
  assert.equal(reply.content, '답: 안녕하세요');
  assert.equal(reply.ms, 1234);
  assert.equal(C.seconds(reply.ms), '1.2초');
  assert.equal(chat.state.announce.text, '답: 안녕하세요', 'the new reply is handed to the live region');

  server.hold(true);
  const pending = chat.send('오늘 뭐 했어요?');
  await settle();
  assert.ok(chat.state.pending, 'typing state while the reply is on its way');
  assert.equal(chat.canSend(), false);
  assert.equal(await chat.send('하나 더'), false, 'a second message is not sent while waiting');
  server.release();
  assert.equal(await pending, true);
  assert.equal(chat.state.pending, null);
  assert.deepEqual(server.posts()[1].body.messages, [
    { role: 'user', content: '안녕하세요' }, { role: 'assistant', content: '답: 안녕하세요' }, { role: 'user', content: '오늘 뭐 했어요?' }
  ]);
  assert.equal(server.posts().length, 2);
});

test('sessionStorage remembers the selected conversation and 새 대화 preserves the server history', async () => {
  const server = fakeServer();
  const storage = memoryStorage();
  const chat = await open(server, { storage });
  await chat.send('안녕하세요');
  const again = await open(server, { storage });
  assert.deepEqual(talk(again), ['user:안녕하세요', 'assistant:답: 안녕하세요']);
  const first = again.state.sessionId;
  await again.reset();
  assert.equal(again.state.messages.length, 0);
  assert.equal(storage.map.size, 1);
  assert.equal(await again.selectSession(first), true);
  assert.deepEqual(talk(again), ['user:안녕하세요', 'assistant:답: 안녕하세요']);
  assert.equal(server.posts().length, 1, 'history operations never invoke the model');
});

test('scenario autoplay sends turns one by one in order, each after the previous reply', async () => {
  const server = fakeServer();
  let pauses = 0;
  const chat = await open(server, { gap: 10, pause: async () => { pauses++; } });
  await chat.send('먼저 한 말');
  server.calls.length = 0;
  assert.equal(await chat.play('greet'), true);
  const posts = server.posts();
  assert.equal(posts.length, 3);
  assert.deepEqual(posts.map((p) => p.body.messages.length), [1, 3, 5], 'a scenario starts a fresh conversation and grows by one exchange');
  assert.deepEqual(posts.map((p) => p.body.messages[p.body.messages.length - 1].content), SCENARIOS[0].turns);
  assert.deepEqual(talk(chat), ['user:안녕하세요!', 'assistant:답: 안녕하세요!', 'user:오늘 뭐 했어요?', 'assistant:답: 오늘 뭐 했어요?', 'user:저녁은 드셨어요?', 'assistant:답: 저녁은 드셨어요?']);
  assert.equal(chat.state.play.status, 'done');
  assert.equal(chat.state.play.index, 3);
  assert.equal(pauses, 2, 'a short pause between turns, none before the first');
  assert.equal(chat.canSend(), true, 'after the scenario you can keep talking');
  await chat.send('이어서');
  assert.equal(chat.state.play, null, 'a typed message turns the scenario into a free conversation');
  assert.equal(server.posts()[3].body.messages.length, 7);
});

test('autoplay shows each reply as it arrives, stop aborts the open request, and resume picks up the same turn', async () => {
  const server = fakeServer();
  const chat = await open(server);
  const seen = [];
  chat.subscribe((s) => { const m = s.messages[s.messages.length - 1]; if (m && m.role === 'assistant' && seen[seen.length - 1] !== m.content) seen.push(m.content); });
  server.hold(true);
  const run = chat.play('greet');
  await settle();
  assert.equal(chat.state.play.status, 'running');
  assert.equal(chat.canSend(), false, 'typing is locked while a scenario plays');
  server.release();
  await settle();
  assert.deepEqual(seen, ['답: 안녕하세요!'], 'the first reply is shown before the second turn is answered');
  assert.equal(server.posts().length, 2);
  assert.equal(chat.stop(), true);
  assert.equal(await run, false);
  assert.equal(chat.state.play.status, 'stopped');
  const tail = chat.state.messages[chat.state.messages.length - 1];
  assert.equal(tail.content, '오늘 뭐 했어요?');
  assert.ok(tail.stopped && tail.error, 'the unanswered turn is marked so it can be fetched again');
  assert.equal(chat.state.pending, null);

  server.hold(false);
  assert.equal(await chat.resume(), true);
  assert.equal(chat.state.play.status, 'done');
  assert.deepEqual(talk(chat).filter((x) => x.startsWith('user:')), ['user:안녕하세요!', 'user:오늘 뭐 했어요?', 'user:저녁은 드셨어요?'], 'the stopped turn is not sent twice in the conversation');
  assert.deepEqual(seen, ['답: 안녕하세요!', '답: 오늘 뭐 했어요?', '답: 저녁은 드셨어요?']);
});

test('not ready: meta reason is shown, nothing is sent, and a 409 on send switches to the same state', async () => {
  const server = fakeServer({ meta: Object.assign({}, META, { ready: false, reason: '프롬프트가 아직 없어요. 진행 화면에서 페르소나 승인까지 마쳐 주세요.', scenarios: [], samples: [] }) });
  const chat = await open(server);
  assert.equal(chat.state.phase, 'not-ready');
  assert.match(chat.state.reason, /프롬프트가 아직 없어요/);
  assert.equal(await chat.send('안녕하세요'), false);
  assert.equal(await chat.play('greet'), false);
  assert.equal(server.posts().length, 0);

  const blank = await open(fakeServer({ meta: Object.assign({}, META, { ready: false, reason: '' }) }));
  assert.equal(blank.state.reason, '아직 대화할 준비가 되지 않았어요.', 'a plain Korean reason even when the server gives none');

  const s2 = fakeServer();
  const live = await open(s2);
  s2.fail.push({ status: 409, detail: '대화할 프롬프트가 없어요.' });
  assert.equal(await live.send('안녕하세요'), false);
  assert.equal(live.state.phase, 'not-ready');
  assert.equal(live.state.reason, '대화할 프롬프트가 없어요.');

  const missing = await open(fakeServer({ metaFail: [404] }));
  assert.equal(missing.state.phase, 'missing');
});

test('error and retry: a failed reply keeps the message, retry resends it once, and a new message replaces it', async () => {
  const server = fakeServer();
  const chat = await open(server);
  server.fail.push({ status: 502, detail: '대화 모델이 잠깐 답하지 않았어요.' });
  assert.equal(await chat.send('안녕하세요'), false);
  const failed = chat.state.messages[0];
  assert.equal(failed.error, '대화 모델이 잠깐 답하지 않았어요.');
  assert.equal(failed.stopped, false);
  assert.equal(chat.state.pending, null);
  assert.equal(await chat.retry(), true);
  assert.deepEqual(server.posts()[1].body.messages, [{ role: 'user', content: '안녕하세요' }], 'retry sends the same history, not a duplicate turn');
  assert.deepEqual(talk(chat), ['user:안녕하세요', 'assistant:답: 안녕하세요']);
  assert.equal(chat.state.messages[0].error, '');

  server.fail.push({ status: 500, detail: '' });
  await chat.send('잘 지냈어요?');
  assert.equal(chat.state.messages[2].error, '답을 받지 못했어요. 잠시 뒤 다시 시도해 주세요.', 'a plain message when the server gives no reason');
  await chat.send('다른 말로 할게요');
  assert.deepEqual(talk(chat), ['user:안녕하세요', 'assistant:답: 안녕하세요', 'user:다른 말로 할게요', 'assistant:답: 다른 말로 할게요']);
  assert.deepEqual(server.posts()[3].body.messages.map((m) => m.role), ['user', 'assistant', 'user'], 'two user turns never go in a row');
});

test('a failed turn pauses autoplay and retry continues from that turn to the end', async () => {
  const server = fakeServer();
  let n = 0;
  // 두 번째 말에서만 한 번 실패하는 서버.
  const chat2 = C.createChat({ characterId: CID, gap: 0, fetch: async (url, init) => { if (init && init.method === 'POST' && ++n === 2) return { ok: false, status: 503, json: async () => ({ detail: '잠시 뒤 다시 시도해 주세요.' }) }; return server.fetch(url, init); } });
  await chat2.load();
  assert.equal(await chat2.play('greet'), false);
  assert.equal(chat2.state.play.status, 'error');
  assert.equal(chat2.state.play.index, 1);
  assert.equal(chat2.state.messages[2].error, '잠시 뒤 다시 시도해 주세요.');
  assert.equal(chat2.canSend(), true, 'after a failure the person can also type instead');
  assert.equal(await chat2.retry(), true);
  assert.equal(chat2.state.play.status, 'done');
  assert.deepEqual(talk(chat2).filter((x) => x.startsWith('user:')).map((x) => x.slice(5)), SCENARIOS[0].turns);
});

test('loading the meta can fail and be retried', async () => {
  const server = fakeServer({ metaFail: ['network'] });
  const chat = C.createChat({ fetch: server.fetch, characterId: CID });
  const phases = [];
  // 영상 목록을 받으면 같은 단계로 한 번 더 알린다. 단계가 바뀐 순서만 본다.
  chat.subscribe((s) => { if (phases[phases.length - 1] !== s.phase) phases.push(s.phase); });
  await chat.load();
  assert.equal(chat.state.phase, 'error');
  assert.match(chat.state.error, /서버에 연결하지 못했어요/);
  await chat.load();
  assert.equal(chat.state.phase, 'ready');
  assert.deepEqual(phases, ['loading', 'error', 'loading', 'ready']);
  assert.equal(chat.state.meta.name, '손흥민');
});

test('page wiring: chat.html loads the shared shell, labels the input, has a live region, and the studio serves it', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'chat.html'), 'utf8');
  for (const f of ['shared/foundry-tokens.css', 'shared/flow.css', 'shared/chat.css', 'shared/chat.js']) assert.ok(html.includes(f), f);
  assert.ok(!html.includes('shared/flow.js'), 'the chat page does not run the factory screen');
  assert.ok(html.includes('CharacterChat.mount'));
  assert.match(html, /<label class="sr" for="ch-input">/);
  assert.match(html, /aria-live="polite"/);
  const app = fs.readFileSync(path.join(__dirname, '..', '..', 'src', 'character_factory_poc', 'web', 'app.py'), 'utf8');
  assert.match(app, /"chat\.html",/);
  const js = fs.readFileSync(path.join(__dirname, '..', 'shared', 'chat.js'), 'utf8');
  assert.ok(js.includes(C.MOTIF_NOTE));
  assert.ok(/isComposing/.test(js), 'Enter while composing Hangul does not send');
});


test('names follow the shared rule; the server placeholder and raw ids never show as a name', () => {
  assert.equal(C.displayName('손흥민', 'cf-20261110-motif-cd9b'), '손흥민');
  assert.equal(C.displayName('캐릭터', 'cf-20261109-son'), '이름 미정 · son (11/9)');
  assert.equal(C.displayName('', 'cf-20261105-api-cost-argon'), '이름 미정 · api-cost-argon (11/5)');
  assert.equal(C.createdLabel('', 'cf-20261110-motif-cd9b'), '11/10', 'the date falls back to the id');
  assert.equal(C.createdLabel('not a date', 'x'), '');
});

test('the sidebar list comes from the chat list API, or from projects keeping only chat-ready ones', () => {
  const api = [{ characterId: 'cf-a', displayName: '손흥민', createdAt: '2026-11-10T05:00:00Z', origin: 'SOURCE' }, { displayName: 'no id' }];
  assert.deepEqual(C.chatList(api, false).map((c) => c.characterId), ['cf-a']);
  const projects = { characters: [
    { id: 'cf-20261110-a', name: '손흥민', chatReady: true },
    { id: 'cf-20261110-b', name: '손흥민', chatReady: false },
    { id: 'cf-20261105-api-cost-argon', name: '', chatReady: true, archived: true }
  ] };
  assert.deepEqual(C.chatList(projects, true).map((c) => c.characterId), ['cf-20261110-a'], 'not-ready and archived characters stay out');
  const old = { characters: [{ id: 'cf-20261105-api-cost-argon', name: '' }] };
  assert.deepEqual(C.chatList(old, true), [{ characterId: 'cf-20261105-api-cost-argon', displayName: '이름 미정 · api-cost-argon (11/5)', createdAt: null, origin: null }], 'an older server keeps every character but never shows a raw id');
});

test('one scenario list: own scenarios first, generic ones with the same title dropped, the rest kept as 기본', () => {
  const list = [
    { id: 'son-sc5-unknown', title: '모르는 것 묻기', turns: ['a'] },
    { id: 'son-sc6-private', title: '사생활 질문', turns: ['a'] },
    { id: 'daily', title: '첫인사·일상', turns: ['a'] },
    { id: 'unknown', title: '모르는 것 묻기', turns: ['a'] },
    { id: 'private', title: '사생활  질문', turns: ['a'] },
    { id: 'extra', title: '새 기본', generic: true, turns: ['a'] }
  ];
  const g = C.groupScenarios(list);
  assert.deepEqual(g.mine.map((s) => s.id), ['son-sc5-unknown', 'son-sc6-private']);
  assert.deepEqual(g.basic.map((s) => s.id), ['daily', 'extra']);
  assert.deepEqual(g.dropped, ['unknown', 'private']);
  assert.deepEqual(C.groupScenarios(SCENARIOS.map((s) => Object.assign({}, s, { generic: true }))).basic.length, 2, 'with no own scenarios the generic ones all stay');
});

test('chat page copy: one name 대화해 보기, settings folded, a fix link, help entry, no collapse-looking back button', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'chat.html'), 'utf8');
  const js = fs.readFileSync(path.join(__dirname, '..', 'shared', 'chat.js'), 'utf8');
  const css = fs.readFileSync(path.join(__dirname, '..', 'shared', 'chat.css'), 'utf8');
  assert.ok(!/대화 테스트/.test(html + js), 'no second name for the page');
  assert.ok(html.includes('<title>대화해 보기 · Foundry</title>'));
  assert.ok(js.includes('<summary data-key="sum:set">설정 보기</summary>'), 'model and temperature sit in a folded 설정 보기');
  assert.ok(!js.includes('>고칠 점 적기<') && js.includes("'factory.html#c/'"), 'no dead-end feedback link (QA v5 D-03)');
  assert.ok(js.includes('class="fd-help"') && js.includes('ch-head-help'), 'the same ? help entry as the factory');
  assert.ok(!js.includes('ch-sidebtn') && !js.includes("icon('back')"), 'the back button that looked like a sidebar toggle is gone');
  assert.ok(js.includes('새 대화로 시작해요'), 'scenario buttons say they start a new conversation');
  assert.ok(js.includes("'아래' : '오른쪽'"), 'narrow screens point down to the scenarios');
  assert.match(css, /@media \(pointer:coarse\)\{\.ch-hint\{display:none\}\}/);
  assert.match(css, /\.ch-fail\.is-stopped\{color:var\(--fd-fg-muted\)\}/, 'a stop the person chose is grey, not an error');
});

test('not ready keeps the server reason and next place; a missing id gives a plain message', async () => {
  const server = fakeServer({ meta: Object.assign({}, META, { ready: false, reason: '팬 통화 장면이 아직 없어요. 진행 화면에서 만들어 주세요.', missing: ['scene'], nextHref: 'factory.html#c/cf-son', scenarios: [], samples: [] }) });
  const chat = await open(server);
  assert.equal(chat.state.phase, 'not-ready');
  assert.equal(chat.state.reason, '팬 통화 장면이 아직 없어요. 진행 화면에서 만들어 주세요.');
  assert.equal(chat.state.meta.nextHref, 'factory.html#c/cf-son');
  const missing = await open(fakeServer({ metaFail: [404] }));
  assert.equal(missing.state.phase, 'missing');
  assert.ok(!missing.state.reason.includes(CID), 'the id is not repeated as if it were a name');
});
