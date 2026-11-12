'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const Ref = require('../shared/reference.js');
const Sources = require('../shared/sources.js');
const json = (body, status = 200) => ({ ok: status < 400, status, json: async () => structuredClone(body) });
const preview = (extra = {}) => ({ enabled: true, status: 'awaiting_confirmation', revision: 'r1', sha256: 'hash1', imageUrl: '/synthetic/r1.png', wardrobe: '', background: '', activeJobId: null, error: null, videoStatus: 'none', ...extra });
const loaded = (c) => { const r = c.state.reference; c.imageLoaded([r.revision, r.sha256, r.imageUrl].join('|'), true); };
function server(initial) {
  const db = { reference: preview(initial), calls: [], conflict: false };
  db.fetch = async (url, init) => {
    const body = init.body ? JSON.parse(init.body) : undefined;
    db.calls.push({ url, method: init.method, body });
    if (init.method === 'GET') return json(db.reference);
    if (db.conflict) { db.reference = preview({ revision: 'r2', sha256: 'hash2', imageUrl: '/synthetic/r2.png' }); return json({ detail: 'changed' }, 409); }
    if (url.endsWith('/confirm')) { db.reference.status = 'approved'; return json({ jobId: null, queued: true }); }
    db.reference = preview({ status: 'generating', revision: 'r2', imageUrl: null, wardrobe: body.wardrobe, background: body.background, activeJobId: 'reference-job' });
    return json({ jobId: 'reference-job' });
  };
  return db;
}

test('Lite draft sends reference config, signature and chapter, never enables demo; other tiers keep their contract', async () => {
  for (const videoTier of ['light', 'none', 'standard']) {
    let draft, sent;
    const fetch = async (url, init) => {
      if (url === '/api/sources/drafts') {
        sent = JSON.parse(init.body);
        draft = { ...sent, subject: { displayName: sent.displayName, kind: sent.subjectKind }, files: [], canFinalize: false };
        return json({ characterId: 'synthetic' });
      }
      if (url === '/api/sources/synthetic') return json(draft);
      return json({});
    };
    const intake = Sources.createIntake({ fetch, XHR: null });
    const input = { displayName: '합성 인물', subjectKind: 'PRIVATE_PERSON', age: '30', gender: '여성', job: '작가', background: '인물 배경', videoTier, chapterTemplate: 'INTERVIEW', sigTitle: '인사', sigMotion: '손을 들어요', referenceWardrobe: ' 흰 셔츠 ', referenceBackground: ' ', demoMode: true };
    assert.ok((await intake.createDraft(input)).characterId);
    assert.equal(sent.chapterTemplate, 'INTERVIEW');
    assert.equal(sent.knownFacts.background, '인물 배경', 'person facts never become visual background');
    if (videoTier === 'light') {
      assert.deepEqual(sent.referenceImage, { wardrobe: '흰 셔츠', background: '' });
      assert.equal(sent.demoMode, undefined);
      assert.equal(sent.signaturePose.title, '인사');
      const reopened = Sources.createIntake({ fetch, XHR: null });
      await reopened.load('synthetic');
      assert.deepEqual(reopened.settings().referenceImage, sent.referenceImage);
      assert.deepEqual(intake.validateDraft({ ...input, sigMotion: '' }), { sigMotion: '어떤 동작인지 적어 주세요.' });
    } else {
      assert.equal(sent.referenceImage, undefined);
      assert.equal(sent.demoMode, true, 'legacy mode stays intact');
    }
  }
});

test('Lite blank fields preserve the photo and finalize still requires both data and a ready photo', async () => {
  let sent;
  const intake = Sources.createIntake({ XHR: null, fetch: async (url, init) => {
    if (init.method === 'POST') { sent = JSON.parse(init.body); return json({ characterId: 'synthetic' }); }
    if (url.startsWith('/api/sources/')) return json({ videoTier: 'light', referenceImage: sent.referenceImage, files: [], canFinalize: true });
    return json({});
  } });
  await intake.createDraft({ displayName: '합성', subjectKind: 'PRIVATE_PERSON', age: '30', gender: '여성', job: '작가', videoTier: 'light', sigTitle: '인사', sigMotion: '손 흔들기' });
  assert.deepEqual(sent.referenceImage, { wardrobe: '', background: '' });
  assert.equal(intake.startState().ready, false);
  intake.state.draft.files.push({ fileId: 't', filename: 'synthetic.txt', status: 'ready' });
  assert.equal(intake.startState().needPhoto, true);
  intake.state.draft.files.push({ fileId: 'p', filename: 'synthetic.png', fileType: 'photo', status: 'ready' });
  assert.equal(intake.startState().ready, true);
  intake.state.draft.files.push({ fileId: 'p2', filename: 'second.png', fileType: 'photo', status: 'ready' });
  assert.equal(intake.startState().ready, false);
  assert.match(intake.startState().reasons.join(' '), /한 장만/);
});

test('GET never approves; explicit confirmation uses the viewed revision/hash even while persona work is active', async () => {
  const db = server({ activeJobId: 'persona-job' });
  const c = Ref.createController({ fetch: db.fetch });
  await c.setCharacter('person / 1');
  await c.refresh();
  assert.ok(db.calls.every((x) => x.method === 'GET'));
  assert.equal(await c.act('confirm'), false, 'unloaded image cannot be confirmed');
  loaded(c);
  assert.equal(await c.act('confirm'), true);
  const post = db.calls.find((x) => x.method === 'POST');
  assert.equal(post.url, '/api/sources/person%20%2F%201/reference/confirm');
  assert.deepEqual(post.body, { revision: 'r1', sha256: 'hash1' });
  assert.match(c.state.notice, /끝나면.*이어/);
  assert.equal(await c.act('confirm'), false, 'approved image cannot be submitted twice');
});

test('retry sends latest revision and edits, preserves typing through polling, and is blocked after approval or during a job', async () => {
  const db = server(); const c = Ref.createController({ fetch: db.fetch });
  await c.setCharacter('synthetic');
  c.edit('wardrobe', ' 새 옷 '); c.edit('background', '');
  await c.refresh();
  assert.equal(c.state.edits.wardrobe, ' 새 옷 ');
  assert.equal(await c.act('retry'), true);
  assert.deepEqual(db.calls.find((x) => x.method === 'POST').body, { revision: 'r1', wardrobe: '새 옷', background: '' });
  assert.equal(await c.act('confirm'), false);
  for (const extra of [{ status: 'approved' }, { activeJobId: 'persona' }, { status: 'generating' }]) assert.equal(Ref.canRetry(preview(extra)), false);
});

test('a stale approval receives 409, refreshes, and requires viewing the new image before any further confirmation', async () => {
  const db = server(); db.conflict = true;
  const c = Ref.createController({ fetch: db.fetch }); await c.setCharacter('synthetic'); loaded(c);
  assert.equal(await c.act('confirm'), false);
  assert.equal(c.state.reference.revision, 'r2');
  assert.match(c.state.error, /최신 상태/);
  assert.equal(await c.act('confirm'), false);
  assert.equal(db.calls.filter((x) => x.method === 'POST').length, 1);
});

test('duplicate clicks and navigation cannot apply a late mutation to another character', async () => {
  const db = server(); let release;
  const fetch = async (url, init) => {
    if (init.method === 'POST') await new Promise((resolve) => { release = resolve; });
    return db.fetch(url, init);
  };
  const c = Ref.createController({ fetch }); await c.setCharacter('a'); loaded(c);
  const pending = c.act('confirm');
  assert.equal(await c.act('confirm'), false);
  await c.setCharacter('b'); release(); await pending;
  assert.equal(c.state.cid, 'b'); assert.equal(c.state.reference.status, 'awaiting_confirmation');
  assert.equal(c.state.notice, '');
});

test('late GET results cannot overwrite another character, and network errors disable actions until a successful read', async () => {
  let release, fail = false;
  const c = Ref.createController({ fetch: async (url) => {
    if (url.includes('/a/')) await new Promise((resolve) => { release = resolve; });
    if (fail) throw new Error('offline');
    return json(preview({ wardrobe: url.includes('/a/') ? 'a' : 'b' }));
  } });
  const pending = c.setCharacter('a'); await c.setCharacter('b'); release(); await pending;
  assert.equal(c.state.reference.wardrobe, 'b');
  loaded(c); fail = true; await c.refresh();
  assert.equal(await c.act('confirm'), false); assert.equal(c.state.readError, true);
  fail = false; await c.refresh(); assert.equal(c.state.readError, false);
});

test('preview escapes every server field, rejects unsafe image URLs, and marks unverified images without assuming they are fake', () => {
  const attack = '\"><script>alert(1)</script><img src=x onerror=alert(2)>';
  const r = preview({ wardrobe: attack, background: '</textarea>' + attack, error: attack, validationStatus: 'unverified', revision: attack, imageUrl: '/image.png?name="quoted"' });
  const html = Ref.cardHTML({ reference: r, edits: r, error: attack, notice: attack });
  assert.ok(!html.includes('<script>')); assert.ok(!html.includes('<img src=x')); assert.ok(html.includes('&lt;/textarea&gt;'));
  assert.ok(!html.includes('시험용')); assert.match(html, /생성 완료는 품질 검증 완료를 뜻하지/);
  assert.match(html, /영상 6편/); assert.match(html, /병렬/);
  for (const url of ['javascript:alert(1)', 'data:image/svg+xml,<svg/>', '//evil.test/x', '/\\evil', 'https://u:p@example.test/x', 'java\nscript:x']) assert.equal(Ref.imageUrl(url), '');
  assert.equal(Ref.imageUrl('/safe.png'), '/safe.png');
  for (const status of ['not_started', 'generating', 'awaiting_confirmation', 'approved', 'failed']) assert.ok(Ref.statusCopy(preview({ status })));
  assert.equal(Ref.cardHTML({ reference: { enabled: false } }), '');
});


test('reference progress uses parallel copy, preserves failures and chat readiness, and separates review gates', () => {
  const options = { tier: 'light', referenceImage: { wardrobe: '', background: '' } };
  const running = Sources.doneView({ status: 'running', videoTier: 'light' }, {}, options);
  assert.equal(running.body, Ref.PARALLEL_COPY);
  assert.ok(!running.body.includes('대화가 된 뒤'));
  for (const status of ['failed', 'stopped']) {
    assert.equal(Sources.doneView({ status }, {}, options).body, Sources.doneView({ status }).body);
  }
  const review = Sources.doneView({ status: 'needs_review', chatReady: true }, {}, options);
  assert.match(review.body, /각각 확인/); assert.equal(review.ready, true);
  const ready = Sources.doneView({ status: 'chat_ready', chatReady: true, videoStatus: 'none' }, {}, options);
  assert.equal(ready.ready, true); assert.match(ready.body, /대화할 수 있어요/);
  assert.ok(!ready.body.includes('만들고 있어요')); assert.equal(ready.video.show, false);
});

test('legacy drafts still accept more than one photo', () => {
  const intake = Sources.createIntake({ fetch: async () => json({}), XHR: null });
  intake.state.draft = { videoTier: 'light', canFinalize: true, files: [
    { filename: 'synthetic.txt', status: 'ready' },
    { filename: 'a.png', fileType: 'photo', status: 'ready' },
    { filename: 'b.png', fileType: 'photo', status: 'ready' }
  ] };
  assert.equal(intake.startState().ready, true);
});

test('approved idle/failed videos expose explicit recovery only without an active job', () => {
  for (const videoStatus of ['none', 'failed']) {
    const reference = preview({ status: 'approved', videoStatus });
    assert.equal(Ref.canResumeVideo(reference), true);
    const html = Ref.cardHTML({ reference, edits: {} });
    assert.match(html, /data-ref-act="resume-video"/);
    assert.match(html, videoStatus === 'failed' ? /영상 6편 생성 다시 시도/ : /영상 6편 생성 이어서 하기/);
    assert.match(html, /모델 사용 비용/);
    assert.ok(!html.includes('data-ref-act="confirm"'));
    for (const extra of [{ activeJobId: 'persona' }, { activeJobId: 'video' }, { videoStatus: 'making' }, { videoStatus: 'ready' }, { status: 'awaiting_confirmation' }, { enabled: false }, { revision: null }, { sha256: null }]) {
      const r = { ...reference, ...extra };
      assert.equal(Ref.canResumeVideo(r), false);
      assert.ok(!Ref.cardHTML({ reference: r, edits: {} }).includes('data-ref-act="resume-video"'));
    }
  }
});

test('reloaded approved videos resume only by explicit action using the persisted revision/hash', async () => {
  for (const videoStatus of ['none', 'failed']) {
    const db = server({ status: 'approved', videoStatus, imageUrl: null });
    const c = Ref.createController({ fetch: db.fetch });
    await c.setCharacter('synthetic'); await c.refresh(); await c.refresh();
    assert.ok(db.calls.every((x) => x.method === 'GET'), 'polling never resumes a paid job');
    assert.equal(await c.act('resume-video'), true, 'an already approved photo does not need a new load/approval');
    assert.deepEqual(db.calls.filter((x) => x.method === 'POST'), [{ url: '/api/sources/synthetic/reference/confirm', method: 'POST', body: { revision: 'r1', sha256: 'hash1' } }]);
    await c.refresh(); await c.refresh();
    assert.equal(db.calls.filter((x) => x.method === 'POST').length, 1, 'a still-failed response never triggers an automatic retry');
  }
});

test('recovery blocks duplicate clicks while pending and respects the returned active job', async () => {
  const db = server({ status: 'approved', videoStatus: 'failed' });
  let release;
  const c = Ref.createController({ fetch: async (url, init) => {
    if (init.method === 'POST') { await new Promise((resolve) => { release = resolve; }); db.reference.activeJobId = 'video-job'; db.reference.videoStatus = 'making'; }
    return db.fetch(url, init);
  } });
  await c.setCharacter('synthetic');
  const pending = c.act('resume-video');
  assert.equal(await c.act('resume-video'), false);
  release(); assert.equal(await pending, true);
  assert.equal(await c.act('resume-video'), false);
  assert.equal(db.calls.filter((x) => x.method === 'POST').length, 1);
});

test('a generated signature seed is shown beside the master photo and approved with its own hash', async () => {
  const sig = { signatureImageUrl: '/synthetic/r1-sig.png', signatureSha256: 'sighash1' };
  const db = server(sig);
  const c = Ref.createController({ fetch: db.fetch });
  await c.setCharacter('synthetic');
  await c.refresh();
  const html = Ref.cardHTML(c.state);
  assert.match(html, /r1-sig\.png/);
  assert.match(html, /시그니처 중간 프레임/);
  assert.match(html, /두 이미지로 승인/);
  assert.equal((html.match(/data-ref-image/g) || []).length, 2);
  // The master-only key no longer counts as "loaded": both images must have decoded.
  loaded(c);
  assert.equal(await c.act('confirm'), false);
  c.imageLoaded(Ref.keyOf(c.state.reference), true);
  assert.equal(await c.act('confirm'), true);
  const post = db.calls.find((x) => x.method === 'POST');
  assert.deepEqual(post.body, { revision: 'r1', sha256: 'hash1', signatureSha256: 'sighash1' });
});

test('a seed hash without a safe image URL cannot be approved', () => {
  const r = preview({ signatureSha256: 'sighash1', signatureImageUrl: 'javascript:alert(1)' });
  assert.equal(Ref.canConfirm(r), false);
  assert.equal(Ref.canConfirm(preview()), true);
  assert.deepEqual(Ref.confirmBody(preview()), { revision: 'r1', sha256: 'hash1' });
});
