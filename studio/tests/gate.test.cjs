'use strict';
// 관문 화면(gate.js)의 화면 없는 판단 검사: 이름, 다시 만든 버전의 지난 요청, 출시 전 점검 관문, 반려 안내. 네트워크·브라우저 없음.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const G = require(path.join(__dirname, '..', '..', 'src', 'character_factory_poc', 'web', 'static', 'shared', 'gate.js'));

test('before planning, a motif sheet shows the name chosen on the source screen, never the internal id (QA v5 A-08, B-F15)', () => {
  const id = 'cf-20261110-motif-bc7289876e874813';
  assert.equal(G.characterName({ name: id, displayName: '엄마A-프롬프트', persona: null }, id), '엄마A-프롬프트');
  // 기획에서 이름을 정하면 그 이름을 쓴다.
  assert.equal(G.characterName({ name: '윤하린', displayName: '윤하린', persona: { name: '윤하린' } }, id), '윤하린');
  // 아무 이름도 없으면 날짜와 짧은 이름표만 보인다(서버의 '이름 미정' 자리표시는 이름으로 쓰지 않는다).
  const none = G.characterName({ name: id, displayName: '이름 미정' }, id);
  assert.equal(none, '이름 미정 · motif-bc7289876e874813 (11/10)');
});

test('a remade version shows what the last version was asked to change (QA v5 B-F18)', () => {
  const rec = (rev, decision, extra) => ({ record: Object.assign({ rev, decision, decidedAt: '2026-11-10T0' + rev.slice(-1) + ':00:00Z' }, extra) });
  // G6처럼 requestedChanges에 담긴 요청
  assert.equal(G.previousAsk({ rev: 'pv2', records: [rec('pv1', 'REQUEST_CHANGES', { requestedChanges: [{ field: 'long', note: '첫 인사를 짧게' }] })] }), '첫 인사를 짧게');
  // 메모 칸(reasons)에만 남긴 요청, 챕터별 요청
  assert.equal(G.previousAsk({ rev: 'sp2', records: [rec('sp1', 'REQUEST_CHANGES', { reasons: '정면 사진이 없어요' })] }), '정면 사진이 없어요');
  assert.equal(G.previousAsk({ rev: 'bg2', records: [rec('bg1', 'REQUEST_CHANGES', { requestedChanges: [{ field: 'ch2', note: '비 오는 골목' }] })] }), '2장: 비 오는 골목');
  // 첫 버전, 같은 버전의 기록, 바로 앞 결정이 반려면 보이지 않는다.
  assert.equal(G.previousAsk({ rev: 'pv1', records: [] }), null);
  assert.equal(G.previousAsk({ rev: 'pv1', records: [rec('pv1', 'REQUEST_CHANGES', { reasons: 'x' })] }), null);
  assert.equal(G.previousAsk({ rev: 'pv3', records: [rec('pv1', 'REQUEST_CHANGES', { reasons: '옛 요청' }), rec('pv2', 'REJECT', { reasons: '반려' })] }), null);
});

test('the package check expects every gate of this character, including G7a, and skips G9 and skipped gates (QA v5 C-15)', () => {
  const original = ['G1', 'G3', 'G4a', 'G4b', 'G4', 'G5', 'G5b', 'G6', 'G7a', 'G7', 'G8', 'G9'].map((id) => ({ id, status: 'APPROVED' }));
  assert.ok(G.packageGates(original).includes('G7a'));
  assert.equal(G.packageGates(original).length, 11);
  const motif = [{ id: 'G0', status: 'APPROVED' }, { id: 'G1s', status: 'APPROVED' }, { id: 'G3', status: 'APPROVED' }, { id: 'G5', status: 'SKIPPED' }, { id: 'G9', status: 'AWAITING_HUMAN' }];
  assert.deepEqual(G.packageGates(motif), ['G0', 'G1s', 'G3']);
  assert.ok(G.packageGates(null).includes('G7a'), 'without the character list it still checks G7a');
});

test('reject confirm only promises to keep gates that are already approved (QA v5 B-F23)', () => {
  const gates = [{ id: 'G0', title: '출처 묶음 승인', status: 'AWAITING_HUMAN' }, { id: 'G1s', title: '기준 사진 선택', status: 'PENDING' }];
  assert.deepEqual(G.keptOnReject(gates, 'G0'), [], 'G0 has nothing before it');
  const later = [{ id: 'G0', title: '출처 묶음 승인', status: 'APPROVED' }, { id: 'G1s', title: '기준 사진 선택', status: 'APPROVED' }, { id: 'G3', title: '기획안 고르기', status: 'AWAITING_HUMAN' }];
  assert.deepEqual(G.keptOnReject(later, 'G3'), ['출처 묶음 승인', '기준 사진 선택']);
});

test('gate script wiring: G3 asks for a note before a change request, gender is picked in Korean, the shared send delay is one value', () => {
  const fs = require('node:fs');
  const js = fs.readFileSync(path.join(__dirname, '..', '..', 'src', 'character_factory_poc', 'web', 'static', 'shared', 'gate.js'), 'utf8');
  const plans = js.slice(js.indexOf('function buildPlans('), js.indexOf('// ---------------------------------------------------------------- G4a'));
  assert.match(plans, /REQUEST_CHANGES[\s\S]*data-plan-note[\s\S]*throw Error/, 'an empty G3 change request is stopped');
  assert.ok(js.includes('<textarea data-plan-note'), 'G3 has a place to write what to change');
  assert.ok(!js.includes('작업실에서 직접 쓴 안을 등록'), 'no pointer to a screen that does not exist');
  assert.match(js, /field === 'gender'[\s\S]{0,400}GENDER_KO/, 'gender is shown as 여성·남성');
  // 수정 요청·반려 대기 시간은 한 값을 모든 관문이 함께 쓴다(QA v5 C-17).
  assert.equal((js.match(/delayedSend\(/g) || []).length, 2, 'one definition and one caller');
  assert.equal((js.match(/초 뒤에 보내요/g) || []).length, 1);
});

