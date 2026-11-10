'use strict';
// 영상 등급·사진(4차 Q 묶음) 브라우저 확인. 공장 루트 사본을 읽는 서버에 붙어 원문 화면과 진행 화면을 열고,
// 아직 서버에 없는 상태(영상 등급이 있는 초안, 사진 올리기, 영상 만드는 중·다 됨, 영상 만들기)는 약속 5 모양의 응답을 가로채 넣는다.
// 그 밖의 쓰기 요청은 막는다(유료 작업을 걸지 않는다).
// 실행: STUDIO_URL=http://127.0.0.1:8898 CID=<대화 가능한 모티브> PHOTO=/tmp/face.jpg SHOT_DIR=/tmp node studio/tests/sources-video.browser.cjs
const assert = require('node:assert/strict');
const path = require('node:path');
const puppeteer = require('/tmp/cfshot/node_modules/puppeteer-core');
const base = process.env.STUDIO_URL || 'http://127.0.0.1:8898';
const cid = process.env.CID || 'cf-20261110-motif-cd9b4de9137f424c';
const photoFile = process.env.PHOTO || '/tmp/foundry-q/face.jpg';
const dir = process.env.SHOT_DIR || '/tmp';
const shot = (name) => path.join(dir, 'video-' + name + '.png');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function open(browser, width, routes) {
  const p = await browser.newPage();
  await p.setViewport({ width, height: 1000 });
  const errors = [];
  const writes = [];
  p.on('pageerror', (e) => errors.push(e.message));
  await p.setRequestInterception(true);
  p.on('request', (req) => {
    const u = new URL(req.url());
    const hit = routes.find((r) => r.method === req.method() && r.match(u.pathname));
    if (hit) {
      if (req.method() !== 'GET') writes.push(req.method() + ' ' + u.pathname + ' ' + (req.postData() || '').slice(0, 80));
      const body = typeof hit.body === 'function' ? hit.body(req) : hit.body;
      return req.respond({ status: hit.status || 200, contentType: 'application/json', body: JSON.stringify(body) });
    }
    if (req.method() !== 'GET' && u.host === new URL(base).host) return req.respond({ status: 403, contentType: 'application/json', body: '{"detail":"읽기 전용 확인"}' });
    return req.continue();
  });
  return { p, errors, writes };
}
const text = (p, sel) => p.$eval(sel, (el) => el.innerText).catch(() => '');
const shown = (p, sel) => p.$eval(sel, (el) => !el.hidden && el.offsetParent !== null).catch(() => false);
// 다시 그린 뒤에도 지금 있는 요소를 누른다.
const tap = (p, sel) => p.$eval(sel, (el) => el.click());
// 진행 화면은 자주 다시 그려서 요소 손잡이가 떨어진다. 그 순간의 자리로 화면을 잘라 찍는다.
// has를 주면 그 글이 들어간 요소를 고른다(다시 그려도 같은 요소를 찾는다).
async function snap(p, sel, name, has) {
  const find = (els, h) => els.find((e) => e.offsetParent !== null && e.getBoundingClientRect().height > 4 && (!h || e.innerText.includes(h)));
  await p.$$eval(sel, (els, h, f) => { const el = new Function('return ' + f)()(els, h); el.scrollIntoView({ block: 'center', behavior: 'instant' }); }, has || '', find.toString());
  await sleep(300);
  // 자르는 자리는 문서 기준이라 창이 내려간 만큼 더한다.
  const box = await p.$$eval(sel, (els, h, f) => { const el = new Function('return ' + f)()(els, h); const r = el.getBoundingClientRect(); return { x: r.x + window.scrollX, y: r.y + window.scrollY, width: r.width, height: r.height }; }, has || '', find.toString());
  await p.screenshot({ path: shot(name), captureBeyondViewport: false, clip: { x: Math.max(0, box.x - 8), y: Math.max(0, box.y - 8), width: box.width + 16, height: box.height + 16 } });
}

// 영상 등급을 고른 초안(약속 5). 원문 하나는 준비됐고 사진은 아직 없다.
function draftServer() {
  const textFile = { fileId: 't1', filename: 'son-interview-2025.txt', size: 18234, status: 'ready', fileType: 'text', textId: 'son-interview-2025', kind: 'INTERVIEW', register: 'FORMAL', subjectSpeaker: '손흥민', userSpeaker: '기자', date: '2025-08-07', sourceUrl: 'https://example.com/interview', problems: [], detectedSpeakers: [{ name: '손흥민', lines: 41 }, { name: '기자', lines: 12 }], suggested: { subjectSpeaker: '손흥민' } };
  const db = { files: [textFile], started: false, video: 'making' };
  const need = () => !db.files.some((f) => f.fileType === 'photo' && f.status === 'ready');
  const view = () => ({ characterId: 'cf-shot', subject: { displayName: '손흥민', kind: 'PUBLIC_FIGURE' }, usageBasis: { scope: '팀 내부 사용', notes: '' }, knownFacts: { age: '33세', gender: '남성', job: '축구선수' }, modelMode: 'PROMPT_ONLY', autoReview: true, videoTier: 'light', store: 'local', allowPathImport: false, files: db.files, problems: need() ? ['영상을 만들려면 인물 사진을 한 장 이상 올려 주세요.'] : [], canFinalize: !need(), jobId: db.started ? 'job-shot' : undefined });
  const detail = () => ({ id: 'cf-shot', origin: 'SOURCE', displayName: '손흥민', modelMode: 'PROMPT_ONLY', autoReview: true, status: 'chat_ready', statusLabel: '대화 가능', chatReady: true, goal: { label: '대화 가능까지', done: 5, total: 5 }, stages: [], pendingGates: [], videoTier: 'light', videoStatus: db.video, videoLabel: db.video === 'ready' ? '영상을 볼 수 있어요' : '영상을 만들고 있어요' });
  const routes = [
    { method: 'GET', match: (p) => p === '/api/sources/cf-shot', body: () => view() },
    { method: 'POST', match: (p) => p === '/api/sources/cf-shot/files', body: (req) => { const b = JSON.parse(req.postData()); const id = 'p' + db.files.length; db.files.push({ fileId: id, filename: b.filename, size: b.size, status: 'pending', fileType: 'photo', problems: [] }); return { fileId: id, upload: { method: 'PUT', url: '/api/sources/cf-shot/files/' + id + '/content', headers: { 'Content-Type': 'application/octet-stream' } } }; } },
    { method: 'PUT', match: (p) => /^\/api\/sources\/cf-shot\/files\/p\d+\/content$/.test(p), body: {} },
    { method: 'POST', match: (p) => /^\/api\/sources\/cf-shot\/files\/p\d+\/complete$/.test(p), body: (req) => { assert.equal(req.postData(), '{}', 'photos are checked with an empty body'); const f = db.files[db.files.length - 1]; f.status = 'ready'; return f; } },
    { method: 'POST', match: (p) => p === '/api/sources/cf-shot/finalize', body: () => { db.started = true; return { jobId: 'job-shot' }; } },
    { method: 'GET', match: (p) => p === '/api/characters/cf-shot', status: 200, body: () => (db.started ? detail() : { id: 'cf-shot', origin: 'SOURCE', status: 'draft', statusLabel: '시작 전', stages: [] }) },
    { method: 'GET', match: (p) => p === '/api/characters/cf-shot/chat/meta', body: () => ({ characterId: 'cf-shot', ready: db.started, reason: '' }) }
  ];
  return { db, routes };
}

(async () => {
  const browser = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  const report = [];
  try {
    // 1. 새 캐릭터 양식: 영상 다섯 갈래, 라이트를 고르면 사진 안내가 뜬다.
    {
      const { p, errors } = await open(browser, 1280, []);
      await p.goto(base + '/studio/sources.html', { waitUntil: 'networkidle0' });
      const cards = await p.$$eval('[data-tier-cards] .vt-opt b', (els) => els.map((e) => e.textContent));
      assert.deepEqual(cards, ['영상 없이', '라이트', '스탠다드', '프로', '맥스']);
      assert.ok(!/\d/.test(await text(p, '[data-tier-cards]')), 'no numbers on the cards');
      await p.click('[data-tier-cards] input[value="light"]');
      assert.ok(await shown(p, '[data-tier-hint]'));
      assert.ok(await shown(p, '[data-sig]'), 'picking a tier opens the signature pose fields (D-0165)');
      await p.type('[name="sigTitle"]', '찰칵 세리머니');
      await p.type('[name="sigMotion"]', '두 손으로 카메라 모양을 만들어 눈앞에 대고 찰칵 누르는 시늉을 해요.');
      const fs = await p.$('[data-tier-choice]');
      await fs.screenshot({ path: shot('1-form-tiers') });
      await p.setViewport({ width: 390, height: 900 });
      await sleep(150);
      await fs.screenshot({ path: shot('1b-form-tiers-phone') });
      assert.deepEqual(errors, []);
      report.push('form: five tiers, hint after picking 라이트');
      await p.close();
    }
    // 2. 영상 등급이 있는 초안: 사진 칸과 막힌 시작 → 사진 올리기 → 시작 → 영상 만드는 중 → 다 됨.
    {
      const srv = draftServer();
      const { p, errors, writes } = await open(browser, 1280, srv.routes);
      await p.goto(base + '/studio/sources.html#c/cf-shot', { waitUntil: 'networkidle0' });
      assert.ok(await shown(p, '[data-photos]'), 'photo area is shown for a tier');
      assert.equal(await p.$eval('[data-start]', (b) => b.disabled), true, 'start waits for a photo');
      const reasons = await text(p, '[data-reasons]');
      assert.match(reasons, /사진/);
      assert.equal((reasons.match(/사진/g) || []).length, 1, 'the photo reason is said once');
      assert.match(await text(p, '[data-sum-video]'), /라이트/);
      await p.screenshot({ path: shot('2-draft-needs-photo'), fullPage: true });
      await snap(p, '[data-step="start"]', '2b-start-waits-for-photo');
      await tap(p, '[data-act="tier-edit"]');
      await p.waitForSelector('[data-tier-edit] [name="videoTierEdit"]', { timeout: 3000 });
      assert.equal(await p.$eval('[data-tier-edit] [name="videoTierEdit"]:checked', (e) => e.value), 'light');
      await snap(p, '[data-step="info"] section', '2c-tier-change');
      await tap(p, '[data-act="tier-edit"]');
      const input = await p.$('[data-photo-picker]');
      await input.uploadFile(photoFile);
      await p.waitForFunction(() => !document.querySelector('[data-start]').disabled, { timeout: 5000 });
      assert.equal(await p.$$eval('.src-photo img', (els) => els.length), 1, 'the photo shows as a thumbnail');
      assert.match(await text(p, '[data-photo-count]'), /1장 준비/);
      assert.match(await text(p, '[data-start-note]'), /영상은 대화가 된 뒤에 만들고 비용이 들어요/);
      await p.screenshot({ path: shot('3-draft-photo-ready'), fullPage: true });
      await snap(p, '[data-step="start"]', '3b-start-ready');
      await p.click('[data-start]');
      await p.waitForFunction(() => !document.querySelector('[data-video-line]').hidden, { timeout: 5000 });
      assert.equal(await text(p, '[data-video-text]'), '영상 만드는 중 · 라이트');
      assert.equal(await text(p, '[data-chat-link]'), '대화해 보기');
      const done = await p.$('[data-step="start"]');
      await done.screenshot({ path: shot('4-started-video-making') });
      srv.db.video = 'ready';
      await p.evaluate(() => window.sourceIntake.intake.progress());
      await sleep(200);
      assert.equal(await text(p, '[data-chat-link]'), '영상과 함께 대화해 보기');
      assert.match(await text(p, '[data-done-text]'), /영상까지 다 만들었어요/);
      await done.screenshot({ path: shot('5-started-video-ready') });
      assert.deepEqual(errors, []);
      assert.ok(writes.every((w) => !/videos|jobs/.test(w)), 'no video job is posted from this page');
      report.push('draft: photo upload, start gate, chat first then video. writes=' + writes.length);
      await p.close();
    }
    // 3. 진행 화면: 대화 가능한 실제 캐릭터에 영상 상태(약속 5)를 더해서 연다.
    {
      const real = await (await fetch(base + '/api/characters/' + cid)).json();
      const projects = await (await fetch(base + '/api/projects')).json();
      const state = { video: 'none', tier: 'none', photos: false, posted: null };
      const withVideo = (c) => Object.assign({}, c, { videoTier: state.tier, videoStatus: state.video, videoLabel: state.video === 'none' ? '아직 영상이 없어요' : '영상을 만들고 있어요' });
      const routes = [
        { method: 'GET', match: (p) => p === '/api/characters/' + cid, body: () => withVideo(real) },
        { method: 'GET', match: (p) => p === '/api/projects', body: () => Object.assign({}, projects, { characters: projects.characters.map((c) => (c.id === cid ? withVideo(c) : Object.assign({}, c, { videoTier: 'none', videoStatus: 'none', videoLabel: '아직 영상이 없어요' }))) }) },
        { method: 'GET', match: (p) => p === '/api/sources/' + cid, body: () => ({ characterId: cid, files: [{ fileId: 't', filename: 'a.txt', fileType: 'text', status: 'ready' }].concat(state.photos ? [{ fileId: 'p', filename: 'face.jpg', fileType: 'photo', status: 'ready' }] : []) }) },
        { method: 'POST', match: (p) => p === '/api/characters/' + cid + '/videos', body: (req) => { state.posted = JSON.parse(req.postData()); state.tier = state.posted.videoTier; state.video = 'making'; return { jobId: 'job-v' }; } }
      ];
      const { p, errors, writes } = await open(browser, 1440, routes);
      // 진행 화면은 상태 사건 연결을 열어 두어 네트워크가 쉬지 않는다. 화면 요소를 기다린다.
      await p.goto(base + '/studio/factory.html#c/' + encodeURIComponent(cid), { waitUntil: 'domcontentloaded' });
      await p.waitForSelector('[data-act="video-open"]', { timeout: 8000 });
      await tap(p, '[data-act="video-open"]');
      // 사진은 처음 만들 때만 올린다(D-0160). 사진 없이 만든 캐릭터는 원문 화면에서 새로 만들게 안내한다.
      await p.waitForFunction(() => /만들 때 사진을 올리지 않아서/.test(document.body.innerText), { timeout: 5000 });
      const href = await p.$eval('.fl-vid a.btn', (a) => a.getAttribute('href'));
      assert.equal(href, 'sources.html');
      await snap(p, '.fl-tasks', '6-factory-no-photo');
      state.photos = true;
      await tap(p, '[data-act="video-cancel"]');
      await tap(p, '[data-act="video-open"]');
      await p.waitForSelector('[name="videoTierPick"]', { timeout: 5000 });
      assert.deepEqual(await p.$$eval('[name="videoTierPick"]', (els) => els.map((e) => e.value)), ['light', 'standard', 'pro', 'max']);
      await tap(p, '[name="videoTierPick"][value="pro"]');
      await sleep(100);
      await tap(p, '[data-act="video-go"]');
      await p.waitForFunction(() => /시그니처 포즈의 이름과 어떤 동작인지/.test(document.body.innerText), { timeout: 3000 });
      await p.type('#fl-sig-title', '찰칵 세리머니');
      await p.type('#fl-sig-motion', '두 손으로 카메라 모양을 만든다.');
      assert.match(await text(p, '[data-act="video-go"]'), /프로 영상 만들기 시작/);
      await snap(p, '.fl-tasks', '7-factory-chooser');
      await tap(p, '[data-act="video-go"]');
      await p.waitForFunction(() => /영상 만드는 중 · 프로/.test(document.querySelector('.fd-title').innerText), { timeout: 5000 });
      assert.deepEqual(state.posted, { videoTier: 'pro', signaturePose: { title: '찰칵 세리머니', motion: '두 손으로 카메라 모양을 만든다.', useWhen: '' } });
      await snap(p, '.fd-title', '8-factory-header-making');
      await snap(p, '.fl-tasks', '8b-factory-tasks-making');
      await p.goto(base + '/studio/factory.html#all', { waitUntil: 'domcontentloaded' });
      await p.waitForSelector('.ov-table', { timeout: 8000 });
      const rowText = await p.$$eval('.ov-table tbody tr', (rows) => rows.map((r) => r.innerText));
      assert.ok(rowText.some((t) => /영상 만드는 중 · 프로/.test(t)), 'the list shows the line');
      assert.ok(!rowText.some((t) => /아직 영상이 없어요/.test(t)), 'characters without video get no extra words');
      // 목록은 첫 읽기 뒤에 한 번 더 그려진다. 다 그린 뒤 그 줄을 찍고, 찍은 줄이 맞는지 다시 본다.
      await sleep(1500);
      await snap(p, '.ov-table tbody tr', '9-factory-list-row', '영상 만드는 중 · 프로');
      assert.deepEqual(errors, []);
      report.push('factory: no-photo link, chooser posts {videoTier:pro}, header and list line. writes=' + writes.join(' | '));
      await p.close();
    }
  } finally {
    await browser.close();
  }
  console.log(report.join('\n'));
})().catch((e) => { console.error(e); process.exit(1); });

