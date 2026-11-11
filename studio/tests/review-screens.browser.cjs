'use strict';
// 검토·생성 화면(2차 I 묶음) 브라우저 확인. 실제 공장 루트를 읽기만 하는 서버에 붙어 G0·G6·원문 화면·캐릭터 화면을 열고,
// 이 캐릭터에 없는 상태(열린 G0, 대화 표본이 있는 G6, 시작한 원문 초안)는 계약 모양의 응답을 가로채 넣는다. 결정·작업은 보내지 않는다.
// 실행: STUDIO_URL=http://127.0.0.1:8871 CID=<모티브 캐릭터> SHOT_DIR=/tmp node studio/tests/review-screens.browser.cjs
const assert = require('node:assert/strict');
const path = require('node:path');
const puppeteer = require('/tmp/cfshot/node_modules/puppeteer-core');
const base = process.env.STUDIO_URL || 'http://127.0.0.1:8871';
const cid = process.env.CID || 'cf-20261110-motif-8e7b7ce7fb474b70';
const dir = process.env.SHOT_DIR || '/tmp';
const shot = (name) => path.join(dir, 'review-' + name + '.png');

async function getJSON(p) { const r = await fetch(base + p); assert.ok(r.ok, p + ' ' + r.status); return r.json(); }
// 지정한 경로만 바꿔 주고 나머지는 그대로 보낸다. 쓰기 요청(POST·PUT·PATCH·DELETE)은 막는다.
async function page(browser, width, routes) {
  const p = await browser.newPage();
  await p.setViewport({ width, height: 1000 });
  const errors = [];
  p.on('pageerror', (e) => errors.push(e.message));
  await p.setRequestInterception(true);
  p.on('request', (req) => {
    const u = new URL(req.url());
    const hit = (routes || []).find((r) => r.method === req.method() && r.match(u.pathname + u.hash));
    if (hit) return req.respond({ status: hit.status || 200, contentType: 'application/json', body: JSON.stringify(typeof hit.body === 'function' ? hit.body() : hit.body) });
    if (req.method() !== 'GET' && u.host === new URL(base).host) return req.respond({ status: 403, contentType: 'application/json', body: '{"detail":"읽기 전용 확인"}' });
    return req.continue();
  });
  return { p, errors };
}
const visible = (p, sel) => p.$$eval(sel, (els) => els.filter((e) => e.offsetParent !== null).length);
const bodyText = (p) => p.evaluate(() => document.body.innerText);

(async () => {
  const browser = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  const out = { checks: [] };
  const ok = (name) => out.checks.push(name);
  try {
    // ---- G0: 실제 자료. 이미 결정한 관문이라 빼기 토글은 잠겨 있다.
    const g0 = await getJSON('/api/characters/' + cid + '/gates/G0');
    const items = g0.items;
    const pf = items.publicFacts || { items: [], deflections: [] };
    let { p, errors } = await page(browser, 1440);
    await p.goto(base + '/gate.html?character=' + cid + '&gate=G0&skin=foundry&theme=light', { waitUntil: 'networkidle2' });
    await p.waitForSelector('.fact-card');
    assert.equal(await p.$$eval('.fact-card', (x) => x.length), pf.items.length);
    const cardText = await p.$$eval('.fact-card', (x) => x.map((e) => e.innerText).join('\n'));
    assert.ok(!/https?:\/\//.test(cardText), 'no raw URLs on fact cards');
    assert.ok(!/yt-[A-Za-z0-9_-]{6,}-\d{5}/.test(cardText), 'no message ids on fact cards');
    const chips = await p.$$eval('.fact-card a.fact-chip', (x) => x.map((a) => [a.textContent, a.target, a.rel]));
    assert.ok(chips.length && chips.every((c) => !/[/%?]/.test(c[0].replace('↗', '').replace(' (새 탭)', '')) && c[1] === '_blank' && /noopener/.test(c[2])));
    if (pf.items.some((f) => f.selfView && f.selfView.quote)) assert.ok(await p.$('.fact-self blockquote[title^="원문 위치"]'));
    assert.equal(await p.$$eval('.fact-deflect li', (x) => x.length), (pf.deflections || []).filter((d) => d.quote).length);
    assert.ok(await p.$$eval('[data-exclude-fact]', (x) => x.every((e) => e.disabled)), 'decided gate locks the toggles');
    const g0text = await bodyText(p);
    ['동의한 사람', '동의 날짜', '동의 기록', '제외 ·'].forEach((w) => assert.ok(!g0text.includes(w), w));
    assert.ok(g0text.includes('말한 자리') && g0text.includes('공식 자리') && g0text.includes('캐주얼 자리'));
    assert.ok((await p.$$eval('.gate-section > .twin-scroll > .src-table tbody tr', (x) => x.length)) <= 10);
    if (items.texts.length > 10) assert.ok(await p.$('details.src-more'));
    assert.deepEqual(errors, []);
    await p.screenshot({ path: shot('g0-facts') });
    await p.evaluate(() => document.querySelector('.src-mix').scrollIntoView({ block: 'start' }));
    await p.screenshot({ path: shot('g0-sources') });
    await p.close();
    ok('G0 fact cards, sources summary and register column on real data');

    // ---- G0 열린 상태(가로챔): 사실 하나를 빼면 보낼 답에 excludedFactIds로 실린다.
    const open = Object.assign({}, g0, { status: 'AWAITING_HUMAN', record: null, records: [] });
    ({ p, errors } = await page(browser, 1280, [{ method: 'GET', match: (s) => s === '/api/characters/' + cid + '/gates/G0', body: open }]));
    await p.goto(base + '/gate.html?character=' + cid + '&gate=G0&skin=foundry&theme=dark', { waitUntil: 'networkidle2' });
    await p.waitForSelector('[data-exclude-fact]');
    const first = await p.$eval('[data-exclude-fact]', (e) => e.value);
    await p.click('.fact-toggle');
    await p.evaluate(() => { document.querySelectorAll('details.side-tech').forEach((d) => { d.open = true; }); document.querySelector('[data-preview]').click(); });
    const answer = JSON.parse(await p.$eval('[data-answer-json]', (e) => e.textContent));
    assert.deepEqual(answer.excludedFactIds, [first]);
    assert.ok((await p.$eval('[data-side-extra]', (e) => e.innerText)).includes('뺄 사실 1개'));
    assert.ok(await p.$eval('.fact-card', (e) => getComputedStyle(e.querySelector('.fact-out-badge')).display !== 'none'));
    assert.deepEqual(errors, []);
    await p.evaluate(() => document.querySelector('.fact-cards').scrollIntoView({ block: 'center' }));
    await p.screenshot({ path: shot('g0-exclude-dark') });
    await p.close();
    ok('G0 toggle sends excludedFactIds');

    // ---- G6: 실제 자료(표본 없음)에서도 날 키가 보이지 않는다.
    ({ p, errors } = await page(browser, 1440));
    await p.goto(base + '/gate.html?character=' + cid + '&gate=G6&skin=foundry&theme=light', { waitUntil: 'networkidle2' });
    await p.waitForSelector('.gate-section');
    let g6text = await bodyText(p);
    ['card.bigFiveNotes', 'INFERRED', 'WORRY', 'UNKNOWN', 'PRIVATE', '미정:'].forEach((w) => assert.ok(!g6text.includes(w), w));
    await p.close();

    // ---- G6 대화 표본·추론 특질(약속 1 모양을 가로채 넣는다).
    const g6 = await getJSON('/api/characters/' + cid + '/gates/G6');
    const withSamples = JSON.parse(JSON.stringify(g6));
    withSamples.items.samples = [
      { scenarioId: 'greet', title: '첫인사·일상', turns: [{ user: '안녕하세요! 오늘 경기 봤어요', reply: '아 진짜요? 와 감사해요. 오늘 좀 힘들었는데 그래도 이겨서 다행이에요.' }, { user: '컨디션은 괜찮아요?', reply: '네 괜찮아요. 내일 회복 훈련하고 푹 쉬려고요.' }] },
      { scenarioId: 'private', title: '사생활 질문', turns: [{ user: '여자친구 있어요?', reply: '아 그거는 제가 말씀드리기가 좀 그래요. 저는 지금 축구 생각밖에 없어요.' }] }
    ];
    withSamples.items.inferredTraits = [{ situation: 'WORRY', situationKo: '고민 털어놓기', behavior: '상대가 애쓰는 대목을 먼저 짚고 격려한 뒤 자기 경험을 덧붙여요.', refs: [{ msgId: 'yt-V3VwKGoW168-00274', quote: '저도 힘들 때가 많았는데 그냥 버텼던 것 같아요' }] }];
    ({ p, errors } = await page(browser, 1440, [{ method: 'GET', match: (s) => s === '/api/characters/' + cid + '/gates/G6', body: withSamples }]));
    await p.goto(base + '/gate.html?character=' + cid + '&gate=G6&skin=foundry&theme=light', { waitUntil: 'networkidle2' });
    await p.waitForSelector('.chat-sample');
    assert.equal(await p.$$eval('.chat-sample', (x) => x.length), 2);
    assert.equal(await p.$$eval('.chat-sample .bubble.is-user', (x) => x.length), 3);
    assert.equal(await p.$eval('.gate-body > .gate-section', (e) => e.querySelector('.chat-samples') !== null), true, 'samples come first');
    g6text = await bodyText(p);
    assert.ok(!g6text.includes('표본 응답이 아직 없어요'));
    assert.equal(await p.$$eval('.trait-card', (x) => x.length), 1);
    assert.ok(await p.$('.trait-refs blockquote[title="원문 위치 yt-V3VwKGoW168-00274"]'));
    ['card.bigFiveNotes', 'INFERRED', 'WORRY', 'yt-V3VwKGoW168'].forEach((w) => assert.ok(!g6text.includes(w), w));
    assert.ok((await p.$eval('.chat-samples-head a', (a) => a.getAttribute('href'))).endsWith('/studio/chat.html#c/' + cid));
    assert.deepEqual(errors, []);
    await p.screenshot({ path: shot('g6-samples') });
    await p.close();
    ok('G6 transcripts and inferred trait cards');

    // ---- 원문 화면: 빈 양식
    ({ p, errors } = await page(browser, 1512));
    await p.goto(base + '/studio/sources.html', { waitUntil: 'networkidle2' });
    await p.waitForSelector('.fd-side .fd-nav');
    assert.ok(await p.$eval('[name="modelMode"][value="PROMPT_ONLY"]', (e) => e.checked));
    assert.ok(await p.$eval('[name="autoReview"]', (e) => e.checked));
    assert.equal(await p.$('[name="scope"]'), null);
    assert.ok(await p.$$eval('.fd-side .fd-org', (x) => x.length) >= 1, 'motif marker in the sidebar');
    assert.deepEqual(errors, []);
    await p.screenshot({ path: shot('sources-form'), fullPage: true });
    await p.close();
    ok('sources form in the shell');

    // ---- 원문 화면: 시작한 초안(파일 30개, 대화 준비 끝)
    const files = Array.from({ length: 30 }, (_, i) => ({ fileId: 'f' + i, filename: (i % 2 ? 'yt-clip-' : 'interview-') + i + (i % 2 ? '.srt' : '.txt'), size: 4000 + i, sha256: 'h', status: 'ready', textId: (i % 2 ? 'clip-' : 'interview-') + i, kind: i % 2 ? 'TRANSCRIPT' : 'INTERVIEW', register: i % 2 ? 'CASUAL' : 'FORMAL', subjectSpeaker: '손흥민', userSpeaker: '질문자', date: '2025-08-02', sourceUrl: 'https://v.daum.net/v/2025', problems: [] }));
    files[3].status = 'problem'; files[3].problems = ['날짜가 비어 있어요.'];
    const draft = { characterId: 'cf-demo', subject: { displayName: '손흥민', kind: 'PUBLIC_FIGURE' }, usageBasis: { scope: '팀 내부 사용', notes: '' }, knownFacts: { age: '34세', gender: '남성', job: '축구선수' }, store: 'local', allowPathImport: false, files, problems: [], canFinalize: false, jobId: 'job-1', modelMode: 'PROMPT_ONLY', autoReview: true };
    ({ p, errors } = await page(browser, 1512, [
      { method: 'GET', match: (s) => s === '/api/sources/cf-demo', body: draft },
      { method: 'GET', match: (s) => s === '/api/characters/cf-demo', body: { id: 'cf-demo', origin: 'SOURCE', modelMode: 'PROMPT_ONLY', autoReview: true, progress: { done: 11, total: 11 }, pendingGates: [], stages: [], job: null } },
      { method: 'GET', match: (s) => s === '/api/characters/cf-demo/chat/meta', body: { characterId: 'cf-demo', ready: true, reason: '' } }
    ]));
    await p.goto(base + '/studio/sources.html#c/cf-demo', { waitUntil: 'networkidle2' });
    await p.waitForSelector('[data-chat-link]:not([hidden])');
    assert.equal(await p.$eval('[data-chat-link]', (a) => a.getAttribute('href')), 'chat.html#c/cf-demo');
    assert.equal(await visible(p, '.src-x'), 0, 'delete buttons are hidden after the start');
    assert.ok(await visible(p, '.src-file') <= 2, 'the long list is folded to the files that need a look');
    assert.ok((await p.$eval('[data-file-sum]', (e) => e.innerText)).includes('원문 30개'));
    assert.ok((await p.$eval('[data-info-summary]', (e) => e.innerText)).includes('프롬프트만'));
    assert.deepEqual(errors, []);
    await p.evaluate(() => document.querySelector('[data-step="files"]').scrollIntoView({ block: 'start' }));
    await p.screenshot({ path: shot('sources-started') });
    await p.close();
    ok('started draft: folded list, hidden deletes, chat link');

    // ---- 캐릭터 화면: 대화해 보기와 사이드바 모티브 표시
    ({ p, errors } = await page(browser, 1512));
    await p.goto(base + '/studio/factory.html#c/' + cid, { waitUntil: 'networkidle2' });
    await p.waitForSelector('.fd-title .fd-chat');
    assert.equal(await p.$eval('.fd-title .fd-chat', (a) => a.getAttribute('href')), 'chat.html#c/' + cid);
    await p.click('[data-act="select"][data-stage="s8"]');
    await p.waitForSelector('.fl-panel a[href="chat.html#c/' + cid + '"]');
    assert.ok(await p.$$eval('.fd-side .fd-org', (x) => x.length) >= 1);
    assert.deepEqual(errors, []);
    await p.screenshot({ path: shot('character') });
    await p.close();
    ok('character page chat button, inspector link and sidebar marker');
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
