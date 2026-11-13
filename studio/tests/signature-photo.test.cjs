'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const S = require('../shared/sources.js');

const signature = { photoRole: 'signature' };
const photo = (name = 'pose.png') => ({ name, size: 123, type: 'image/png' });
const textRecord = { fileId: 'text', filename: 'interview.txt', fileType: 'text', status: 'ready', problems: [] };
const identityRecord = { fileId: 'identity', filename: 'face.png', fileType: 'photo', status: 'ready', previewUrl: '/preview/identity', problems: [] };
async function settle() { for (let i = 0; i < 30; i++) await new Promise(setImmediate); }

// Only the file/settings contract is simulated; no provider or live server calls.
function server(overrides = {}) {
  const db = { draft: { characterId: 'synthetic', videoTier: 'light', referenceImage: { enabled: true }, signaturePose: { title: '인사', motion: '손을 흔들어요', useWhen: '' }, files: [textRecord], problems: [], canFinalize: true, ...overrides }, seq: 0, failPut: false, failComplete: false, previews: true };
  const calls = [];
  const reply = (status, value) => ({ ok: status < 400, status, json: async () => structuredClone(value) });
  async function fetch(url, init = {}) {
    const method = init.method || 'GET';
    const pathname = new URL(url, 'http://factory.test').pathname;
    const body = typeof init.body === 'string' ? JSON.parse(init.body) : init.body;
    calls.push({ method, path: pathname, body });
    if (method === 'GET' && pathname === '/api/sources/synthetic') return reply(200, db.draft);
    if (method === 'PATCH' && pathname.endsWith('/settings')) { Object.assign(db.draft, body); return reply(200, body); }
    if (method === 'POST' && pathname.endsWith('/files')) {
      const fileId = 'p' + ++db.seq;
      db.draft.files.push({ fileId, filename: body.filename, size: body.size, fileType: 'photo', photoRole: body.photoRole || 'identity', status: 'pending', problems: [] });
      return reply(200, { fileId, upload: { method: 'PUT', url: '/api/sources/synthetic/files/' + fileId + '/content', headers: {} } });
    }
    if (method === 'PUT') { if (db.failPut) { db.failPut = false; return reply(500, {}); } return reply(200, {}); }
    if (method === 'POST' && pathname.endsWith('/complete')) {
      if (db.failComplete) { db.failComplete = false; return reply(500, { detail: '확인 요청을 다시 시도해 주세요.' }); }
      const f = db.draft.files.find((f) => pathname.includes('/' + f.fileId + '/'));
      f.status = 'ready';
      if (db.previews) f.previewUrl = '/preview/' + f.fileId;
      return reply(200, f);
    }
    if (method === 'DELETE') { db.draft.files = db.draft.files.filter((f) => !pathname.endsWith('/' + f.fileId)); return reply(204, null); }
    return reply(404, { detail: 'Not Found' });
  }
  return { db, calls, fetch };
}
async function loaded(s) {
  const intake = S.createIntake({ fetch: s.fetch, XHR: null });
  await intake.load('synthetic');
  s.calls.length = 0;
  return intake;
}

test('signature upload sends its role only at allocation and cannot satisfy the identity requirement', async () => {
  const s = server();
  const intake = await loaded(s);
  intake.addFiles([photo()], signature);
  assert.equal(intake.signaturePhotoItems().length, 1, 'queued signature stays in its own list');
  assert.equal(intake.photoItems().length, 0);
  await settle();
  const allocation = s.calls.find((c) => c.path.endsWith('/files'));
  assert.deepEqual(allocation.body, { filename: 'pose.png', size: 123, contentType: 'image/png', photoRole: 'signature' });
  assert.deepEqual(s.calls.find((c) => c.path.endsWith('/complete')).body, {});
  assert.equal(intake.signaturePhotoItems()[0].tone, 'ok');
  assert.equal(intake.photoItems().length, 0);
  assert.deepEqual(intake.items().map((i) => i.filename), ['interview.txt']);
  assert.equal(intake.startState().needPhoto, true);
  assert.equal(intake.startState().ready, false, 'even canFinalize=true cannot bypass the identity check');
  intake.addFiles([photo('identity.png')], { photoOnly: true });
  await settle();
  assert.equal(s.calls.filter((c) => c.path.endsWith('/files'))[1].body.photoRole, undefined, 'legacy identity allocation keeps its default');
  assert.equal(intake.startState().ready, true, 'one identity plus one signature does not exceed the one-portrait limit');
});

test('role-separated lists and preview URLs survive a fresh intake load, including legacy identity records', async () => {
  const s = server({ files: [textRecord, identityRecord] });
  const intake = await loaded(s);
  intake.addFiles([photo()], signature);
  await settle();
  const fresh = await loaded(s);
  assert.deepEqual(fresh.photoItems().map((i) => i.thumb), ['/preview/identity']);
  assert.deepEqual(fresh.signaturePhotoItems().map((i) => i.thumb), ['/preview/p1']);
  assert.equal(fresh.items().length, 1);
  assert.equal(fresh.startState().ready, true);
});

test('local object URL survives upload completion without a URL and yields to a later server preview', async () => {
  const s = server(); s.db.previews = false;
  const intake = await loaded(s);
  const file = new Blob(['synthetic image bytes'], { type: 'image/png' }); file.name = 'pose.png';
  const [key] = intake.addFiles([file], signature);
  const local = intake.signaturePhotoItems()[0].thumb;
  assert.match(local, /^blob:/);
  await settle();
  assert.equal(intake.signaturePhotoItems()[0].thumb, local);
  s.db.draft.files.find((f) => f.fileId === 'p1').previewUrl = '/preview/p1';
  await intake.refresh();
  assert.equal(intake.signaturePhotoItems()[0].thumb, '/preview/p1');
  await intake.removeFile(key);
  assert.equal(intake.state.thumbs[key], undefined);
});

test('multiple selection is rejected atomically and a queued or saved signature blocks a second photo', async () => {
  const s = server(); const intake = await loaded(s);
  assert.deepEqual(intake.addFiles([photo(), photo('other.png')], signature), []);
  assert.match(intake.state.signaturePhotoError, /한 장만/);
  assert.equal(s.calls.length, 0);
  const [key] = intake.addFiles([photo()], signature);
  assert.equal(intake.state.signaturePhotoError, null);
  assert.deepEqual(intake.addFiles([photo('other.png')], signature), []);
  await settle();
  assert.deepEqual(intake.addFiles([photo('other.png')], signature), []);
  assert.equal(s.calls.filter((c) => c.path.endsWith('/files')).length, 1);
  assert.equal(intake.signaturePhotoItems().length, 1);
  await intake.removeFile(key);
  assert.equal(intake.state.signaturePhotoError, null);
  assert.equal(intake.signaturePhotoItems().length, 0);
  assert.equal(intake.addFiles([photo('replacement.png')], signature).length, 1);
  await settle();
});

test('signature photo rejects unsupported tiers, nonphotos and oversize files before allocation', async () => {
  for (const tier of ['none', 'standard', 'pro', 'max']) {
    const s = server({ videoTier: tier }); const intake = await loaded(s);
    assert.deepEqual(intake.addFiles([photo()], signature), []);
    assert.match(intake.state.signaturePhotoError, /라이트/);
    assert.equal(s.calls.length, 0);
  }
  const s = server(); const intake = await loaded(s);
  assert.deepEqual(intake.addFiles([photo('notes.txt')], signature), []);
  assert.match(intake.state.signaturePhotoError, /jpg, png, webp/);
  assert.deepEqual(intake.addFiles([{ ...photo(), size: S.PHOTO_MAX_BYTES + 1 }], signature), []);
  assert.match(intake.state.signaturePhotoError, /15MB/);
  assert.equal(s.calls.length, 0);
  assert.equal(intake.items().length, 1, 'rejected signature input does not become source text');
});

test('failed signature uploads reserve their slot and retry with the same role; complete retries do not reupload', async () => {
  const s = server(); const intake = await loaded(s); s.db.failPut = true;
  const [key] = intake.addFiles([photo()], signature); await settle();
  assert.equal(intake.signaturePhotoItems()[0].retry, true);
  assert.deepEqual(intake.addFiles([photo('other.png')], signature), []);
  s.calls.length = 0;
  intake.retry(key); await settle();
  assert.deepEqual(s.calls.slice(0, 4).map((c) => c.method), ['DELETE', 'POST', 'PUT', 'POST']);
  assert.equal(s.calls[1].body.photoRole, 'signature');
  assert.equal(intake.signaturePhotoItems().length, 1);
  await intake.removeFile(key);
  s.db.failComplete = true;
  const [next] = intake.addFiles([photo()], signature); await settle();
  s.calls.length = 0;
  intake.retry(next); await settle();
  assert.equal(s.calls[0].path.endsWith('/complete'), true);
  assert.equal(s.calls.some((c) => c.method === 'PUT'), false);
  assert.equal(intake.signaturePhotoItems()[0].tone, 'ok');
});

test('finalized signature photos remain visible but add, delete and retry cannot mutate them', async () => {
  const s = server(); const intake = await loaded(s);
  const [key] = intake.addFiles([photo()], signature); await settle();
  s.db.draft.jobId = 'job-synthetic';
  const fresh = await loaded(s);
  const item = fresh.signaturePhotoItems()[0];
  assert.equal(item.removable, false);
  assert.equal(item.retry, false);
  assert.equal(item.thumb, '/preview/p1');
  assert.deepEqual(fresh.addFiles([photo()], signature), []);
  await fresh.removeFile(item.key);
  assert.equal(s.calls.length, 0);
  // A stale in-memory failed tile must be read-only too.
  fresh.state.uploads.push({ key, fileType: 'photo', photoRole: 'signature', phase: 'failed', filename: 'pose.png', error: 'failed' });
  fresh.retry(key); await fresh.removeFile(key);
  assert.equal(fresh.signaturePhotoItems().find((i) => i.key === key).removable, false);
  assert.equal(fresh.signaturePhotoItems().find((i) => i.key === key).retry, false);
  assert.equal(s.calls.length, 0);
});

test('signature text edits retain template, middle frame path and time', async () => {
  const pose = { title: ' 포즈 ', motion: ' 손을 흔들어요 ', useWhen: '', template: 'custom', middleFramePath: 'sources/pose.png', middleFrameAtS: 2.25 };
  assert.deepEqual(S.sigOf(pose), { ...pose, title: '포즈', motion: '손을 흔들어요' });
  const s = server({ signaturePose: pose }); const intake = await loaded(s);
  assert.equal(await intake.setSignature({ title: '새 이름', motion: '두 손을 흔들어요', useWhen: '인사할 때' }), true);
  const sent = s.calls.find((c) => c.method === 'PATCH').body.signaturePose;
  assert.equal(sent.template, pose.template);
  assert.equal(sent.middleFramePath, pose.middleFramePath);
  assert.equal(sent.middleFrameAtS, 2.25);
  assert.equal(intake.settings().signaturePose.title, '새 이름');
});

test('the separate optional section has one-file input, linked inline errors and middle-pose guidance', () => {
  const html = fs.readFileSync(path.join(__dirname, '../sources.html'), 'utf8');
  const section = html.match(/<section[^>]*data-signature-photos[\s\S]*?<\/section>/)[0];
  assert.match(section, /시그니처 포즈 참고 사진/);
  assert.match(section, /선택/);
  assert.match(section, /자세를 그대로 따라/);
  assert.match(section, /배경과 구도는 기준 사진 그대로/);
  assert.match(section, /시작과 끝은 승인한 기준 사진/);
  assert.match(section, /손 모양과 자세만 참고/);
  assert.match(section, /같은 인물·복장·배경에 이 동작만 입힌 중간 프레임/);
  assert.match(section, /사진이 없으면 적어 둔 동작 설명만/);
  assert.doesNotMatch(section.match(/<input[^>]*data-signature-photo-picker[^>]*>/)[0], /\bmultiple\b/);
  assert.match(section, /aria-describedby="[^"]*src-signature-photo-e/);
  assert.match(section, /data-signature-photo-error aria-live="polite"/);
});
