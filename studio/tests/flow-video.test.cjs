'use strict';
// 진행 화면의 영상 표시와 영상 만들기(계획 4차 약속 5). 표·카드는 원문 화면과 같고, 화면에는 개수를 쓰지 않는다.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Flow = require('../shared/flow.js');

const src = fs.readFileSync(path.join(__dirname, '..', 'shared', 'flow.js'), 'utf8');
const css = fs.readFileSync(path.join(__dirname, '..', 'shared', 'flow.css'), 'utf8');
// 대화 가능한 모티브(서버가 chatReady를 준다).
const chatReady = (extra) => Object.assign({ id: 'cf-son', origin: 'SOURCE', chatReady: true, stages: [] }, extra);

test('header and list show one plain line from the tier and status; nothing for characters without video', () => {
  assert.equal(Flow.videoText({ videoTier: 'light', videoStatus: 'making' }), '영상 만드는 중 · 라이트');
  assert.equal(Flow.videoText({ videoTier: 'max', videoStatus: 'ready' }), '영상 있음 · 맥스');
  assert.equal(Flow.videoText({ videoTier: 'pro', videoStatus: 'failed' }), '영상을 만들지 못했어요');
  assert.equal(Flow.videoText({ videoTier: 'none', videoStatus: 'none', videoLabel: '아직 영상이 없어요' }), '', 'nothing is added for characters without video, even when the server labels it');
  assert.equal(Flow.videoText({ videoLabel: '영상을 만들고 있어요', videoTier: 'light', videoStatus: 'making' }), '영상 만드는 중 · 라이트', 'a known status reads the same on every screen and names the tier');
  assert.equal(Flow.videoText({ videoLabel: '영상 확인 중', videoTier: 'light', videoStatus: 'checking' }), '영상 확인 중', 'an unknown status falls back to the server label');
  assert.deepEqual(['making', 'ready', 'failed', 'none'].map((s) => Flow.videoTone({ videoStatus: s })), ['run', 'ok', 'fail', '']);
  assert.ok(/trackHTML\(d\) \+ videoChipHTML\(d\)/.test(src), 'the header shows it next to the track badge');
  assert.ok(/videoText\(c\)\]\.filter\(Boolean\)/.test(src), 'the list row adds it to the small line');
  assert.ok(css.includes('.fd-vid{'));
});

test('영상 만들기 is offered only on chat-ready characters without video (or after a failed try) and nothing running', () => {
  assert.equal(Flow.canMakeVideo(chatReady({ videoTier: 'none', videoStatus: 'none' })), true);
  assert.equal(Flow.canMakeVideo(chatReady({ videoTier: 'light', videoStatus: 'failed' })), true);
  assert.equal(Flow.canMakeVideo(chatReady({ videoTier: 'light', videoStatus: 'making' })), false);
  assert.equal(Flow.canMakeVideo(chatReady({ videoTier: 'light', videoStatus: 'ready' })), false);
  assert.equal(Flow.canMakeVideo(chatReady({ videoStatus: 'none', job: { id: 'j' } })), false, 'not while a job runs');
  assert.equal(Flow.canMakeVideo(chatReady({ chatReady: false, videoStatus: 'none' })), false);
  assert.equal(Flow.canMakeVideo(chatReady({})), false, 'a server without video fields is not offered the action');
});

test('the chooser uses the same tier cards without "영상 없이", posts the tier, and sends people without photos to the source page', () => {
  const html = Flow.tierCardsHTML('videoTierPick', 'light', { paidOnly: true });
  assert.deepEqual(Array.from(html.matchAll(/value="([a-z]+)"/g)).map((m) => m[1]), ['light', 'standard', 'pro', 'max']);
  assert.match(html, /value="light" checked/);
  assert.ok(!/\d/.test(html.replace(/<[^>]+>/g, ' ')), 'no counts on the cards');
  assert.ok(src.includes("request('POST', '/api/characters/' + encodeURIComponent(d.id) + '/videos', { videoTier: tier, signaturePose })"));
  assert.ok(src.includes('data-sig="title"') && src.includes('data-sig="motion"') && src.includes('data-sig="useWhen"'), 'the chooser asks for the signature pose (D-0165)');
  assert.ok(src.includes('시그니처 포즈의 이름과 어떤 동작인지 적어 주세요.'), 'name and motion are required before the paid start');
  assert.ok(src.includes("'sources.html#c/' + encodeURIComponent(d.id)"), 'the no-photo note links to the source page of that character');
  assert.ok(src.includes('만들 때 사진을 올리지 않아서 영상을 만들 수 없어요'), 'a character without photos is sent to make a new one with photos');
  assert.ok(src.includes('영상 단계는 비용이 들어요'));
  assert.ok(src.includes("data-act=\"video-open\"") && src.includes("act === 'video-go'"));
});

test('ready photos are counted from the source draft by file type, or by extension on an older server', () => {
  const draft = { files: [
    { fileId: 'a', filename: 'interview.txt', fileType: 'text', status: 'ready' },
    { fileId: 'b', filename: 'face.jpg', fileType: 'photo', status: 'ready' },
    { fileId: 'c', filename: 'side.png', fileType: 'photo', status: 'pending' },
    { fileId: 'd', filename: 'old.webp', status: 'ready' }
  ] };
  assert.equal(Flow.readyPhotos(draft), 2);
  assert.equal(Flow.readyPhotos({ files: [{ filename: 'a.txt', status: 'ready' }] }), 0);
  assert.equal(Flow.readyPhotos(null), 0);
});

