'use strict';
// 영상 통화 화면(4차 묶음 P)의 검사. 약속 6(GET chat/clips, POST chat/clip)을 흉내 내는 가짜 서버와 가짜 <video>를 쓴다.
// 네트워크·유료 모델 호출 없음. 순서(답 → 고르기 → 반응 → 대기), 대체 반응, 준비 안 됨, 상황 재생 기다림을 본다.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const C = require('../shared/chat.js');

const CID = 'cf-son';
const V = (k) => '/files/' + k + '.mp4';
const CLIPS = {
  ready: true, chapter: 'ch1',
  idle: { good: { clipKey: 'idle_good', url: V('idle_good') }, bad: { clipKey: 'idle_bad', url: V('idle_bad') } },
  emotion: [
    { clipKey: 'glad_good', url: V('glad_good'), mood: 'good', title: '반가움' },
    { clipKey: 'amused_good', url: V('amused_good'), mood: 'good', title: '재미있음' },
    { clipKey: 'pouty_good', url: V('pouty_good'), mood: 'good', title: '삐죽' },
    { clipKey: 'sad_bad', url: V('sad_bad'), mood: 'bad', title: '슬픔' },
    { clipKey: 'curious_bad', url: V('curious_bad'), mood: 'bad', title: '궁금함' }
  ],
  special: []
};
const META = { characterId: CID, name: '손흥민', origin: 'SOURCE', ready: true, reason: '', scenarios: [{ id: 'greet', title: '첫인사', turns: ['안녕하세요!', '오늘 뭐 했어요?'] }], samples: [] };

const base = (u) => String(u).replace(/^.*\//, '').replace(/\.mp4$/, '');
const tick = async (n) => { for (let i = 0; i < (n || 30); i++) await new Promise((r) => setImmediate(r)); };
// 시험이 끝날 때 남은 영상 무대를 닫아 기다리던 타이머를 푼다.
const opened = [];
test.after(() => opened.forEach((c) => c && c.destroy()));

// 가짜 <video>. load하면 다음 틱에 첫 프레임 준비(loadeddata)를 알린다(auto=false면 시험이 직접 fire한다).
function fakeVideo(name, log, auto) {
  const handlers = new Map();
  const v = {
    name, src: '', readyState: 0, paused: true, muted: false, loop: false, currentTime: 0, duration: 6, ended: false, loads: 0, plays: 0,
    load() { v.loads++; v.readyState = 0; v.ended = false; log.push(name + ' load ' + base(v.src)); if (auto !== false) setImmediate(() => v.fire('loadeddata')); },
    play() { v.paused = false; v.ended = false; v.plays++; log.push(name + ' play ' + base(v.src)); return Promise.resolve(); },
    pause() { v.paused = true; },
    addEventListener(t, f) { if (!handlers.has(t)) handlers.set(t, new Set()); handlers.get(t).add(f); },
    removeEventListener(t, f) { if (handlers.has(t)) handlers.get(t).delete(f); },
    fire(t) {
      if (t === 'loadeddata') v.readyState = 4;
      if (t === 'ended') { v.ended = true; v.paused = true; }
      Array.from(handlers.get(t) || []).forEach((f) => f({ type: t }));
    }
  };
  return v;
}

// 영상 무대 하나. picks에 넣은 응답을 차례로 돌려주고, 비면 none을 준다.
function stage(extra) {
  const log = [];
  const o = Object.assign({ auto: true, picks: [] }, extra || {});
  const players = [fakeVideo('A', log, o.auto), fakeVideo('B', log, o.auto)];
  const bodies = [];
  const shots = [];
  let front = -1;
  const call = C.createVideoCall(Object.assign({
    clips: o.clips || CLIPS, players, fadeMs: 0, random: () => 0,
    pick: async (body) => {
      bodies.push(body);
      log.push('pick');
      const next = o.picks.shift();
      if (typeof next === 'function') return next();
      return next || { clip: null, kind: 'none', mood: 'good' };
    },
    onChange: (s) => { shots.push(s); if (s.front !== front) { front = s.front; log.push('show ' + (front === 0 ? 'A' : 'B')); } }
  }, o.call || {}));
  opened.push(call);
  const shown = () => (front < 0 ? null : players[front]);
  return { call, players, log, bodies, shots, shown, endShown: () => shown().fire('ended') };
}

test('fallback: gentle first, then calm, same mood first, avoids the last key, skips idle and speaking clips', () => {
  const list = [
    { clipKey: 'idle_good', url: 'i', mood: 'good' },
    { clipKey: 'speak_good', url: 's', mood: 'good' },
    { clipKey: 'displeased_good', url: 'd', mood: 'good' },
    { clipKey: 'playful_good', url: 'p', mood: 'good' },
    { clipKey: 'glad_good', url: 'g', mood: 'good' },
    { clipKey: 's2__amused_good_strong', url: 'a', mood: 'good' },
    { clipKey: 'sorry_bad', url: 'sb', mood: 'bad' },
    { clipKey: 'curious_bad', url: 'cb', mood: 'bad' }
  ];
  const first = () => 0;
  assert.equal(C.pickFallbackClip(list, { mood: 'good', random: first }).clipKey, 'glad_good');
  assert.equal(C.pickFallbackClip(list, { mood: 'good', avoidKey: 'glad_good', random: first }).clipKey, 's2__amused_good_strong');
  // 무드가 bad면 옅은 반응 가운데 bad를 먼저 고른다.
  assert.equal(C.pickFallbackClip(list, { mood: 'bad', random: first }).clipKey, 'curious_bad');
  // 옅은 반응이 없으면 센 감정이 아닌 것을, 센 감정만 있으면 그것이라도 고른다.
  const noGentle = list.filter((c) => !/glad|amused|curious/.test(c.clipKey));
  assert.equal(C.pickFallbackClip(noGentle, { mood: 'good', random: first }).clipKey, 'playful_good');
  assert.equal(C.pickFallbackClip([{ clipKey: 'displeased_good', url: 'd' }], { avoidKey: 'displeased_good' }).clipKey, 'displeased_good');
  // 대기·말하기 영상만 있거나 목록이 비면 대신 틀 것이 없다.
  assert.equal(C.pickFallbackClip(list.slice(0, 2), {}), null);
  assert.equal(C.pickFallbackClip([], {}), null);
  assert.equal(C.clipBaseKey('reaction-pouty_good'), 'pouty');
  assert.equal(C.clipBaseKey('s3__surprised_good_strong'), 'surprised');
});

test('clips are usable only when ready with an idle video', () => {
  assert.equal(C.videoClips(null), null);
  assert.equal(C.videoClips({ ready: false }), null);
  assert.equal(C.videoClips({ ready: true, idle: {}, emotion: [] }), null);
  const v = C.videoClips(CLIPS);
  assert.equal(v.chapter, 'ch1');
  assert.equal(v.emotion.length, 5);
  assert.equal(C.createVideoCall({ clips: { ready: false }, players: [{}, {}] }), null);
});

test('sequence: idle loop first, then reply → pick → reaction once → back to idle, and the promise waits for idle', async () => {
  const s = stage({ picks: [{ clip: { clipKey: 'pouty_good', url: V('pouty_good'), mood: 'good', title: '삐죽' }, kind: 'emotion', mood: 'good' }] });
  await s.call.start();
  assert.deepEqual(s.log, ['A load idle_good', 'A play idle_good', 'show A']);
  assert.equal(s.players[0].loop, true);
  assert.equal(s.players[0].muted, true, 'autoplay starts muted');

  let done = false;
  const p = s.call.react({ userMessage: '보고 싶었어요', replyText: '나도요, 진짜로.' }).then(() => { done = true; });
  await tick();
  assert.deepEqual(s.bodies, [{ userMessage: '보고 싶었어요', replyText: '나도요, 진짜로.', recent: [], chapter: 'ch1' }]);
  assert.deepEqual(s.log.slice(3), ['pick', 'B load pouty_good', 'B play pouty_good', 'show B']);
  assert.equal(s.players[1].loop, false, 'a reaction plays once');
  assert.equal(s.call.state.mode, 'reaction');
  assert.equal(done, false, 'still playing the reaction');

  s.endShown();
  await p;
  // 대기 영상은 이미 물려 있던 A를 처음으로 되감아 다시 튼다(새로 받지 않아 검은 틈이 없다).
  assert.deepEqual(s.log.slice(7), ['A play idle_good', 'show A']);
  assert.equal(s.players[0].loads, 1);
  assert.equal(s.call.state.mode, 'idle');
  assert.equal(done, true);

  // 다음 고르기에는 방금 쓴 영상이 최근 목록으로 간다.
  s.call.react({ userMessage: '또 봐요', replyText: '네, 또 봐요.' });
  await tick();
  assert.deepEqual(s.bodies[1].recent, ['pouty_good']);
});

test('no black flash: the next video stays behind until its first frame is ready', async () => {
  const s = stage({ auto: false, picks: [{ clip: { clipKey: 'glad_good', url: V('glad_good'), mood: 'good' }, kind: 'emotion', mood: 'good' }] });
  const started = s.call.start();
  await tick();
  assert.equal(s.shown(), null, 'nothing shows before the idle video has a frame');
  s.players[0].fire('loadeddata');
  await started;
  assert.equal(s.shown(), s.players[0]);

  s.call.react({ userMessage: '안녕', replyText: '안녕하세요!' });
  await tick();
  assert.ok(s.log.includes('B load glad_good'));
  assert.equal(s.shown(), s.players[0], 'idle stays in front while the reaction loads');
  s.players[1].fire('loadeddata');
  await tick();
  assert.equal(s.shown(), s.players[1]);
});

test('mood continuity: idle follows the mood of the reaction that just played, and the fallback prefers it', async () => {
  const s = stage({ picks: [{ clip: { clipKey: 'sad_bad', url: V('sad_bad'), mood: 'bad' }, kind: 'emotion', mood: 'bad' }] });
  await s.call.start();
  const p = s.call.react({ userMessage: '오늘 졌어요', replyText: '아… 속상하네요.' });
  await tick();
  s.endShown();
  await p;
  assert.equal(s.call.state.mood, 'bad');
  assert.equal(base(s.shown().src), 'idle_bad');
  // 다음 답에 서버가 none이면 옅은 반응 가운데 무드가 같은 것을 먼저 고른다(여기서는 bad 무드의 curious_bad).
  s.call.react({ userMessage: '괜찮아요', replyText: '고마워요.' });
  await tick();
  assert.equal(s.call.state.clip.clipKey, 'curious_bad');
  assert.equal(s.call.state.clip.kind, 'fallback');
  // 새 대화는 무드를 good으로 되돌린다.
  await s.call.reset();
  assert.equal(s.call.state.mood, 'good');
  assert.equal(base(s.shown().src), 'idle_good');
  assert.equal(s.call.state.mode, 'idle');
});

test('none, a failed pick and a slow pick all play a gentle fallback, never the same one twice in a row', async () => {
  const s = stage({ picks: [null, () => { throw new Error('서버 오류'); }, () => new Promise(() => {})], call: { pickMs: 30 } });
  await s.call.start();
  const keys = [];
  for (let i = 0; i < 3; i++) {
    const p = s.call.react({ userMessage: '말 ' + i, replyText: '답 ' + i });
    await new Promise((r) => setTimeout(r, 50));
    keys.push(s.call.state.clip && s.call.state.clip.clipKey);
    assert.equal(s.call.state.clip.kind, 'fallback');
    s.endShown();
    await p;
  }
  assert.deepEqual(keys, ['glad_good', 'amused_good', 'glad_good']);
});

test('stays idle when there is nothing to play, and an empty reply does not pick at all', async () => {
  const s = stage({ clips: Object.assign({}, CLIPS, { emotion: [] }) });
  await s.call.start();
  await s.call.react({ userMessage: '안녕', replyText: '안녕하세요' });
  assert.equal(s.bodies.length, 1);
  assert.equal(s.call.state.mode, 'idle');
  assert.equal(s.players[1].loads, 0, 'the back player is never loaded');
  await s.call.react({ userMessage: '안녕', replyText: '   ' });
  assert.equal(s.bodies.length, 1);
});

test('a newer reply replaces the reaction that is still playing and the older wait ends', async () => {
  const s = stage({ picks: [
    { clip: { clipKey: 'glad_good', url: V('glad_good'), mood: 'good' }, kind: 'emotion', mood: 'good' },
    { clip: { clipKey: 'pouty_good', url: V('pouty_good'), mood: 'good' }, kind: 'emotion', mood: 'good' }
  ] });
  await s.call.start();
  let firstDone = false;
  s.call.react({ userMessage: '1', replyText: '하나' }).then(() => { firstDone = true; });
  await tick();
  assert.equal(base(s.shown().src), 'glad_good');
  const second = s.call.react({ userMessage: '2', replyText: '둘' });
  await tick();
  assert.equal(base(s.shown().src), 'pouty_good');
  assert.equal(firstDone, true);
  s.endShown();
  await second;
  assert.equal(base(s.shown().src), 'idle_good');
});

test('reduced motion: idle holds its first frame while reactions still play once', async () => {
  const s = stage({ call: { reducedMotion: true }, picks: [{ clip: { clipKey: 'glad_good', url: V('glad_good'), mood: 'good' }, kind: 'emotion', mood: 'good' }] });
  await s.call.start();
  assert.equal(s.shown(), s.players[0]);
  assert.equal(s.players[0].plays, 0);
  const p = s.call.react({ userMessage: '안녕', replyText: '안녕하세요' });
  await tick();
  assert.equal(s.players[1].plays, 1);
  s.endShown();
  await p;
  assert.equal(s.players[0].plays, 0);
});

test('sound: starts muted, the toggle shows when clips have audio and switches both players', async () => {
  const quiet = stage({ clips: Object.assign({}, CLIPS, { hasAudio: false }) });
  await quiet.call.start();
  assert.equal(quiet.call.state.hasAudio, false);
  const loud = stage({ clips: Object.assign({}, CLIPS, { hasAudio: true }) });
  await loud.call.start();
  assert.equal(loud.call.state.hasAudio, true);
  loud.call.setMuted(false);
  assert.deepEqual(loud.players.map((v) => v.muted), [false, false]);
  // 서버가 알려 주지 않으면 브라우저가 소리 트랙을 찾았을 때 보인다.
  const found = stage();
  found.players.forEach((v) => { v.audioTracks = { length: 1 }; });
  await found.call.start();
  assert.equal(found.call.state.hasAudio, true);
});

// 약속 1·6 가짜 서버. 대화 답과 영상 목록·고르기를 준다.
function fakeServer(clips, picks) {
  const calls = [];
  const json = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
  async function fetch(url, init) {
    const method = (init && init.method) || 'GET';
    const body = init && typeof init.body === 'string' ? JSON.parse(init.body) : null;
    calls.push({ method, url: String(url), body });
    const root = '/api/characters/' + CID + '/chat';
    if (method === 'GET' && url === root + '/meta') return json(200, META);
    if (method === 'GET' && url === root + '/clips?chapter=ch1') return clips ? json(200, clips) : json(404, { detail: 'Not Found' });
    if (method === 'POST' && url === root) return json(200, { reply: '답: ' + body.messages[body.messages.length - 1].content, ms: 10, rejected: [] });
    if (method === 'POST' && url === root + '/clip') return json(200, (picks && picks.shift()) || { clip: null, kind: 'none', mood: 'good' });
    return json(404, { detail: 'Not Found' });
  }
  return { fetch, calls, chats: () => calls.filter((c) => c.method === 'POST' && c.url.endsWith('/chat')), clipPosts: () => calls.filter((c) => c.url.endsWith('/clip')) };
}

test('chat + video: scenario autoplay waits for each reaction to finish before sending the next line', async () => {
  const server = fakeServer(CLIPS);
  const log = [];
  const players = [fakeVideo('A', log), fakeVideo('B', log)];
  let call = null;
  const chat = C.createChat({ fetch: server.fetch, characterId: CID, gap: 0, react: (t) => (call ? call.react(t) : null) });
  await chat.load();
  assert.equal(chat.state.clips.ready, true);
  call = C.createVideoCall({ clips: chat.state.clips, players, pick: (b) => chat.pickClip(b), fadeMs: 0, random: () => 0 });
  opened.push(call);
  await call.start();

  const playing = chat.play('greet');
  await tick();
  assert.equal(server.chats().length, 1);
  assert.equal(server.clipPosts().length, 1);
  assert.deepEqual(server.clipPosts()[0].body, { userMessage: '안녕하세요!', replyText: '답: 안녕하세요!', recent: [], chapter: 'ch1' });
  assert.equal(call.state.mode, 'reaction');
  await tick();
  assert.equal(server.chats().length, 1, 'the next line waits while the reaction plays');

  players[call.state.front].fire('ended');
  await tick();
  assert.equal(server.chats().length, 2);
  assert.equal(server.clipPosts()[1].body.userMessage, '오늘 뭐 했어요?');
  players[call.state.front].fire('ended');
  assert.equal(await playing, true);
  assert.equal(chat.state.play.status, 'done');
  await tick();
  assert.equal(call.state.mode, 'idle');
});

test('not ready: without clips the chat stays text only, never picks, and autoplay does not wait', async () => {
  for (const clips of [null, { ready: false }]) {
    const server = fakeServer(clips);
    const chat = C.createChat({ fetch: server.fetch, characterId: CID, gap: 0, react: () => null });
    await chat.load();
    assert.equal(chat.state.phase, 'ready');
    assert.equal(chat.state.clips.ready, false);
    assert.equal(C.videoClips(chat.state.clips), null);
    assert.equal(await chat.play('greet'), true);
    assert.equal(server.chats().length, 2);
    assert.equal(server.clipPosts().length, 0);
  }
});

test('page wiring: two muted inline players, a hidden sound toggle, screen reader caption, quiet note with a link', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'chat.html'), 'utf8');
  const players = html.match(/<video data-player[^>]*>/g) || [];
  assert.equal(players.length, 2);
  players.forEach((tag) => { assert.match(tag, /\bmuted\b/); assert.match(tag, /\bplaysinline\b/); assert.match(tag, /preload="auto"/); });
  assert.match(html, /data-sound[^>]*hidden/);
  assert.match(html, /<figcaption class="sr" data-vcap>/);
  const js = fs.readFileSync(path.join(__dirname, '..', 'shared', 'chat.js'), 'utf8');
  assert.ok(js.includes('영상이 아직 없어요 · <a href="'));
  assert.ok(js.includes('">영상 만들기</a>'));
  const css = fs.readFileSync(path.join(__dirname, '..', 'shared', 'chat.css'), 'utf8');
  assert.match(css, /aspect-ratio:9\/16/);
  assert.match(css, /prefers-reduced-motion:reduce\)\{\s*\.ch-screen video/);
});


test('no video: a character made without photos gets a plain note instead of a dead-end 영상 만들기 link (QA v5 D-04)', () => {
  const none = { ready: false };
  const href = 'factory.html#c/cf-son';
  const linked = C.videoNote({ canMakeVideo: true }, none, href);
  assert.match(linked, /영상 만들기<\/a>/);
  assert.ok(linked.includes('href="' + href + '"'));
  const noPhoto = C.videoNote({ canMakeVideo: false }, none, href);
  assert.ok(noPhoto.includes('영상은 만들 때 사진을 올린 캐릭터만 만들 수 있어요'));
  assert.ok(!noPhoto.includes('<a '), 'no link to a screen that cannot make it');
  // 예전 서버처럼 값이 없으면 지금처럼 링크를 둔다. 영상이 있으면 안내가 없다.
  assert.match(C.videoNote({}, none, href), /영상 만들기<\/a>/);
  const clips = { ready: true, idle: { good: { clipKey: 'idle_good', url: '/v.mp4' } } };
  assert.equal(C.videoNote({ canMakeVideo: false }, clips, href), '');
});

