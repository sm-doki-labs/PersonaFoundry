'use strict';
// 사용 안내(help.html)의 검사. 첫 절이 주 흐름(원문 올리기 → 기다리기 → 대화해 보기)이고, 내부 용어·잘못된 안내가 없는지 본다.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const html = fs.readFileSync(path.join(__dirname, '..', 'help.html'), 'utf8');
const visible = html.replace(/<style[\s\S]*?<\/style>/g, '').replace(/<script[\s\S]*?<\/script>/g, '').replace(/<[^>]+>/g, ' ');

test('the first section is the main flow in three steps', () => {
  const first = /<h2 id="([^"]+)">([^<]*)<\/h2>\s*<ol class="steps">([\s\S]*?)<\/ol>/.exec(html);
  assert.ok(first, 'the first heading is followed by numbered steps');
  assert.equal(first[1], 'start');
  assert.ok(html.indexOf('<h2') === html.indexOf('<h2 id="start"'), 'it is the first section');
  const steps = Array.from(first[3].matchAll(/<li><div><b>([^<]+)<\/b>/g)).map((m) => m[1]);
  assert.deepEqual(steps, ['원문 올리기', '기다리기', '대화해 보기']);
});

test('no internal codes or team jargon, and no advice to run paid steps on a finished character', () => {
  assert.ok(!/\bG\d\b/.test(visible), 'no G codes');
  assert.ok(!/관문/.test(visible));
  assert.ok(!/팀\(|\b팀\b|팀별|팀 ·/.test(visible), 'no 팀 grouping');
  assert.ok(!/이어서 실행을 누르면/.test(visible));
  assert.ok(!/대화 테스트/.test(visible));
  assert.ok(/대화 가능인데/.test(visible), 'the stuck section covers a finished character');
});

test('there is a way back to the app, anchors other screens link to still exist, and the icon is inline', () => {
  assert.match(html, /<a class="back" href="factory\.html#all">/);
  ['start', 'cost', 'stuck', 'keys'].forEach((id) => assert.ok(html.includes('id="' + id + '"'), id));
  assert.match(html, /<link rel="icon" href="data:image\/svg\+xml/, 'no /favicon.ico request that ends in 404');
});
