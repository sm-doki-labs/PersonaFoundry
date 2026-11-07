// 운영 현황과 실행 목록: 관문·재시도·예산·호출 기록을 보여 주는 데모 시뮬레이션.
(function OPS(){
  if (new URLSearchParams(location.search).get('mode') !== 'demo') return;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const ICONS = {
    doc:'<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M16 13H8"/><path d="M16 17H8"/>',
    image:'<rect width="18" height="18" x="3" y="3" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>',
    film:'<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M7 3v18"/><path d="M3 12h18"/><path d="M17 3v18"/>',
    megaphone:'<path d="m3 11 18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/>',
    chat:'<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
    database:'<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5V19A9 3 0 0 0 21 19V5"/><path d="M3 12A9 3 0 0 0 21 12"/>',
    cpu:'<rect width="16" height="16" x="4" y="4" rx="2"/><rect width="6" height="6" x="9" y="9" rx="1"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/>',
    aperture:'<circle cx="12" cy="12" r="10"/><path d="m14.31 8 5.74 9.94"/><path d="M9.69 8h11.48"/><path d="m7.38 12 5.74-9.94"/><path d="M9.69 16 3.95 6.06"/><path d="M14.31 16H2.83"/><path d="m16.62 12-5.74 9.94"/>',
    check:'<path d="M20 6 9 17l-5-5"/>', plus:'<path d="M5 12h14"/><path d="M12 5v14"/>', chevron:'<path d="m9 18 6-6-6-6"/>', play:'<polygon points="6 3 20 12 6 21 6 3"/>',
    pause:'<rect x="14" y="4" width="4" height="16" rx="1"/><rect x="6" y="4" width="4" height="16" rx="1"/>',
    stop:'<rect width="14" height="14" x="5" y="5" rx="2"/>', x:'<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    bell:'<path d="M10.268 21a2 2 0 0 0 3.464 0"/><path d="M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.673C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326"/>',
    refresh:'<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    sliders:'<path d="M21 4h-7"/><path d="M10 4H3"/><path d="M21 12h-9"/><path d="M8 12H3"/><path d="M21 20h-5"/><path d="M12 20H3"/><path d="M14 2v4"/><path d="M8 10v4"/><path d="M16 18v4"/>',
    maximize:'<path d="M15 3h6v6"/><path d="M9 21H3v-6"/><path d="m21 3-7 7"/><path d="m3 21 7-7"/>',
    minimize:'<path d="m14 10 7-7"/><path d="M20 10h-6V4"/><path d="m3 21 7-7"/><path d="M4 14h6v6"/>',
    help:'<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
    sidebar:'<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M15 3v18"/>',
    skip:'<polygon points="5 4 15 12 5 20 5 4"/><path d="M19 5v14"/>', arrow:'<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>'
  };
  const ST = window.FACTORY_STATUS;
  const icon = (n, c = 'ic') => `<svg class="${c}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[n] || ''}</svg>`;
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
  const START = 14 * 60;
  const dur$ = (m) => { m = Math.max(0, Math.round(m)); if (m < 60) return `${m}분`; const h = Math.floor(m / 60), r = m % 60; return `${h}시간${r ? ` ${r}분` : ''}`; };
  const hm = (m) => { const v = Math.round(START + m); return `${String(Math.floor(v / 60) % 24).padStart(2, '0')}:${String(v % 60).padStart(2, '0')}`; };
  const usd = (v) => `$${v.toFixed(2)}`;
  const k$ = (n) => (n >= 1000 ? `${(n / 1000).toFixed(n >= 100000 ? 0 : 1)}k` : String(n));
  const A = (n) => `assets/${n}.jpg`;
  const ME = '나 (기획자)';
  const RUN_ID = 'cf-20261021-s2real';
  const STORE = 'cf-ops-v6';

  // ---------- 정의. 시간·비용·실패는 데모 각본. 단계 코드·에이전트·모델·재시도 상한은 공장 문서와 factory.toml을 따른다.
  const M_TEXT = 'anthropic/claude-opus-5-5', M_JUDGE = 'gpt-6.1-sol', M_IMAGE = 'gpt-6.1-sol', M_VIDEO = 'xAI 영상 API', M_TRAIN = 'Gemma · QLoRA';
  const PROV = { [M_TEXT]: 'codex_exec', [M_IMAGE]: 'codex_image', [M_VIDEO]: 'xai', [M_TRAIN]: 'local_gpu' };
  // 모델 배정만 기준 덱과 맞춘 시연 각본이다. 실제 호출 기록은 텍스트 공정 패널에서 읽는다.
  const TEXT_DECK = window.FACTORY_TEXT_DECK_SNAPSHOT;
  const deckModel = (...ids) => [...new Set(ids.map((id) => TEXT_DECK?.tasks[id]?.model || '설정 미연결'))].join(' · ');
  const TEAMS = [
    { id: 'plan', name: '기획', icon: 'doc' }, { id: 'visual', name: '비주얼', icon: 'image' }, { id: 'video', name: '영상', icon: 'film' },
    { id: 'marketing', name: '마케팅', icon: 'megaphone' }, { id: 'persona', name: '페르소나', icon: 'chat' },
    { id: 'data', name: '데이터셋', icon: 'database' }, { id: 'train', name: '학습', icon: 'cpu' }
  ];
  const TASKS = [
    { id: 's1', team: 'visual', stage: 'S1', agent: 'Scout', short: '외모군 · 얼굴', out: '외모군 3개 · 얼굴 3장', thumbs: ['hero-b', 'hero-a', 'cluster-c3'], sq: true, dur: 8, cost: 0.6, deps: [], model: M_IMAGE, calls: 3, inputs: ['ranking.json (화제성 순위)'], rev: 'rf1' },
    { id: 'p1', team: 'plan', stage: 'S3', agent: 'Planner', short: '브리프 해석', out: '브리프 해석', dur: 6, cost: 0.05, deps: [], model: deckModel('brief'), calls: 1, inputs: ['brief-v1'], rev: 'sd1' },
    { id: 'p2', team: 'plan', stage: 'S3', agent: 'Planner', short: '기획안 3개', out: '윤서하 · 한지우 · 서은결', dur: 12, cost: 0.18, deps: ['p1'], model: deckModel('personality', 'consistency', 'voice'), calls: 3, inputs: ['brief-v1', 'seed sd1'], rev: 'pr2' },
    { id: 'v1', team: 'visual', stage: 'S2', agent: 'Stylist', short: '기준 사진', out: '기준 사진 1장 · 동일인 판정 통과', thumbs: ['hero-b2'], sq: true, dur: 6, cost: 0.16, deps: ['G1'], model: M_IMAGE, calls: 1, fail: { at: 0.5, add: 3, mode: 'auto', check: '동일인 판정', score: '같은 얼굴 FAIL', limit: '4개 항목 모두 PASS', text: '기준 사진 동일인 판정 미달', sub: '고른 얼굴로 자동 재생성' }, inputs: ['G1에서 고른 얼굴 (rf1 · c1)'], rev: 'ar1' },
    { id: 'v2', team: 'visual', stage: 'S4a', agent: 'Location Scout', short: '배경 9장', out: '챕터별 배경 3장씩', thumbs: ['bg-ch1-b1', 'bg-ch1-b2', 'bg-ch1-b3'], dur: 14, cost: 1.08, deps: ['G3'], model: M_IMAGE, calls: 9, inputs: ['plan pr2'], rev: 'bg1' },
    { id: 'p3', team: 'plan', stage: 'S4b', agent: 'Scene Writer', short: '챕터 사실', out: '장면 사실·관계 정본', dur: 10, cost: 0.12, deps: ['G4a'], model: M_TEXT, calls: 3, inputs: ['plan pr2', '배경 선택 bg1'], rev: 'ps1' },
    { id: 'v3', team: 'visual', stage: 'S4b', agent: 'Pose Director', short: '자세·의상', out: '장면별 자세 3세트', dur: 8, cost: 0.1, deps: ['p3'], model: M_TEXT, calls: 3, inputs: ['scene-plan ps1', '배경 bg1'], rev: 'ps1' },
    { id: 'v4', team: 'visual', stage: 'S4', agent: 'Framer', short: '완성 이미지', out: '9:16 완성 이미지 3장', thumbs: ['frame-ch1', 'frame-ch2', 'frame-ch3'], dur: 12, cost: 0.72, deps: ['v3', 'v1'], model: M_IMAGE, calls: 3, inputs: ['appearance-spec ar1', '배경 bg1', 'pose-plan ps1'], rev: 'fr1',
      fail: { at: 0.45, add: 5, mode: 'auto', check: '완성 이미지 판정', score: '같은 얼굴 FAIL', limit: '6개 항목 모두 PASS', text: '2장 같은 얼굴 판정 미달', sub: '해당 장만 자동 수정' } },
    { id: 'f1', team: 'video', stage: 'S6', agent: 'Director', short: '대기 영상', out: '대기 영상 6편', thumbs: ['frame-ch1', 'frame-ch2', 'frame-ch3'], dur: 14, cost: 2.1, deps: ['G4'], model: M_VIDEO, calls: 6, inputs: ['approved-frames fr1'], rev: 'va1' },
    { id: 'f2', team: 'video', stage: 'S6', agent: 'Director', short: '행동 영상 37편', out: '행동 영상 37편', dur: 30, cost: 9.6, deps: ['G4', 'G5b'], model: M_VIDEO, calls: 37, inputs: ['approved-frames fr1', '움직임 선택'], rev: 'va1',
      fail: { at: 0.4, add: 6, mode: 'auto', check: '영상 작업 응답', score: '시간 초과', limit: '15분 안에 완료', text: '행동 영상 2편 생성 실패', sub: 'sorry_bad · hurt_bad 자동 재시도' } },
    { id: 'k1', team: 'marketing', stage: 'S5', agent: 'Director', short: '소개 영상', out: '9:16 소개 쇼츠', thumbs: ['hero-b'], sq: true, dur: 16, cost: 1.2, deps: ['v1'], model: M_VIDEO, calls: 2, inputs: ['기준 사진 ar1'], rev: 'vi1' },
    { id: 'k2', team: 'marketing', stage: 'S11', agent: 'Releaser', short: '소개 문구', out: '프로필 카드 문구', dur: 10, cost: 0.06, deps: ['G3'], model: M_TEXT, calls: 1, inputs: ['plan pr2'], rev: 'mk1' },
    { id: 'k3', team: 'marketing', stage: 'S11', agent: 'Releaser', short: '썸네일', out: '썸네일 3장', thumbs: ['frame-ch1', 'frame-ch2', 'frame-ch3'], dur: 8, cost: 0.3, deps: ['G4'], model: M_IMAGE, calls: 3, inputs: ['approved-frames fr1'], rev: 'mk1' },
    { id: 'r1', team: 'persona', stage: 'S7', agent: 'Profiler', short: '특질 시트', out: '상세 특질 시트', dur: 12, cost: 0.2, deps: ['G3'], model: deckModel('voice'), calls: 1, inputs: ['plan pr2', '기준 문서'], rev: 'tr1' },
    { id: 'r2', team: 'persona', stage: 'S8', agent: 'Prompter', short: '프롬프트', out: '정본 조립 · 무압축 본문', dur: 8, cost: 0, deps: ['r1'], model: '결정적 조립 · 모델 호출 없음', calls: 0, inputs: ['traits tr1'], rev: 'pv1' },
    { id: 'd1', team: 'data', stage: 'S9', agent: 'DataSmith', short: '대화 재작성', out: '대화 2,400개', dur: 16, cost: 1.4, deps: ['G6'], model: deckModel('scenarios', 'sft_answers'), calls: 120, inputs: ['persona pv1', 'SNS 라벨 297'], rev: 'ds1' },
    { id: 'd2', team: 'data', stage: 'S9', agent: 'DataSmith', short: '클러스터 증강', out: '14개 클러스터 3,100개', dur: 18, cost: 1.8, deps: ['d1'], model: deckModel('sft_answers', 'repair'), calls: 140, inputs: ['rewrites ds1'], rev: 'ds1',
      fail: { at: 0.55, add: 4, mode: 'human', check: '클러스터 9 중복률', score: '41%', limit: '20% 이하', text: '클러스터 9 증강 결과 중복률 41%', sub: '기준 20% · 시도 3/3 소진' } },
    { id: 'd3', team: 'data', stage: 'S9', agent: 'Judge', short: 'LLM 품질 검사', out: '설정·화자·문맥 전수 검사', dur: 20, cost: 1.1, deps: ['d2'], model: deckModel('screening', 'adjudication'), calls: 80, inputs: ['augmented ds1'], rev: 'ds1' },
    { id: 't1', team: 'train', stage: 'S10', agent: 'Trainer', short: '파인튜닝', out: '3 epoch · 최종 loss 0.68', dur: 40, cost: 4.2, deps: ['G7'], model: M_TRAIN, calls: 1, inputs: ['dataset ds1 (표본 검수 완료)'], rev: 'tn1' },
    { id: 't2', team: 'train', stage: 'S10', agent: 'Trainer', short: '비교 세트', out: '블라인드 비교 40쌍', dur: 10, cost: 0.3, deps: ['t1'], model: M_TEXT, calls: 40, inputs: ['adapter tn1'], rev: 'tn1' }
  ];
  const TEXT_ROLE_IDS = {
    p1: ['brief'], p2: ['personality', 'consistency', 'voice'], r1: ['voice'], r2: [],
    d1: ['scenarios', 'sft_answers'], d2: ['sft_answers', 'repair'], d3: ['screening', 'adjudication']
  };
  const GDEF = Object.fromEntries((window.FACTORY_GATES || []).map((g) => [g.code, g]));
  const GSIM = {
    G1: { after: ['s1'], thumbs: ['hero-b', 'hero-a', 'cluster-c3'], sq: true, rec: '1번 웨이브 미디엄' },
    G3: { after: ['p2'], rec: '윤서하 · 자기 속도가 분명한 현상소 직원' },
    G4a: { after: ['v2'], thumbs: ['bg-ch1-b1', 'bg-ch1-b2', 'bg-ch1-b3'], rec: '1장 필름 현상소 카운터' },
    G4: { after: ['v4'], thumbs: ['frame-ch1', 'frame-ch2', 'frame-ch3'], rec: '3장 모두 승인' },
    // 움직임은 승인된 완성 이미지로 고른다: v4가 끝나고 G4가 승인되어야 열린다
    G5b: { after: ['v4'], needs: ['G4'], rec: '첫 실행 6편' },
    G6: { after: ['r2'], rec: '특질 시트와 프롬프트 승인' },
    G7: { after: ['d2', 'd3'], rec: '표본 40개 검수 후 학습 시작' }
  };
  const GATES = Object.keys(GSIM).map((code) => ({ id: code, code, ...GDEF[code], ...GSIM[code] }));
  const team = (id) => TEAMS.find((x) => x.id === id);
  const task = (id) => TASKS.find((x) => x.id === id);
  const gate = (id) => GATES.find((x) => x.id === id);
  const isGate = (id) => /^G/.test(id);
  const teamTasks = (tid) => TASKS.filter((t) => t.team === tid);
  const teamStages = (tid) => [...new Set(teamTasks(tid).map((t) => t.stage))].join(' · ');

  // ---------- 캐릭터. 윤하린·윤도희는 공장 기록(state.json, 원장)의 실제 상태다.
  const SEOHA = 'seoha';
  const OTHERS = [
    { key: 'harin', id: 'cf-20261014-agentic-p29', name: '윤하린', meta: '25세 · 동네 자전거 수리점 정비사', created: '10월 14일', route: '페르소나 경로만 실행 (S3 · S7 · S8)', cost: '토큰 457k', calls: '구독 경로 · 호출 18회',
      assets: { plan: { cur: 'pr1', at: '10월 14일' }, traits: { prog: 'tr1' }, persona: { prog: 'pv1' } },
      gate: { code: 'G6', title: '페르소나 승인', since: '10월 14일', wait: '13일째', impact: '이 캐릭터의 데이터셋·학습이 이 결재를 기다려요', rec: '특질 시트 tr1 · 프롬프트 pv1' },
      job: { name: '페르소나 경로 실행', revs: 'pr1 · tr1 · pv1' } },
    { key: 'dohee', id: 'cf-20261014-dohee', name: '윤도희', meta: '25세 · 소규모 행사 기획사 운영 담당', created: '10월 14일', route: '페르소나 경로만 실행 · 비교용', cost: '토큰 153k', calls: '구독 경로 · 호출 37회 · 실패 1',
      assets: { plan: { cur: 'pr1', at: '10월 14일', note: '직접 쓴 기획서 정리' }, traits: { prog: 'tr1' }, persona: { prog: 'pv2', note: 'pv1은 결재 전에 pv2로 대체' } },
      gate: { code: 'G6', title: '페르소나 승인', since: '10월 14일', wait: '13일째', impact: '비교용 · 다른 작업을 막지 않아요', rec: '특질 시트 tr1 · 프롬프트 pv2' },
      job: { name: '페르소나 경로 실행', revs: 'pr1 · tr1 · pv1 → pv2' } }
  ];
  const other = (k) => OTHERS.find((o) => o.key === k);
  // 캐릭터 한 명의 자산 묶음. revision 이름은 공장 명세 §6을 따른다.
  const FAM = [
    { k: 'ref', label: '외모군 · 얼굴', stage: 'S1', gate: 'G1', rev: 'rf1', tasks: ['s1'], thumbs: ['hero-b'], sq: true },
    { k: 'app', label: '외모 명세 · 기준 사진', stage: 'S2', gate: '자동 검사', auto: true, rev: 'ar1', tasks: ['v1'], thumbs: ['hero-b2'], sq: true },
    { k: 'plan', label: '기획서', stage: 'S3', gate: 'G3', rev: 'pr2', tasks: ['p1', 'p2'], text: '윤서하 · 필름 현상소 직원' },
    { k: 'bg', label: '챕터 배경', stage: 'S4a', gate: 'G4a', rev: 'bg1', tasks: ['v2'], thumbs: ['bg-ch1-b1', 'bg-ch2-b1', 'bg-ch3-b1'] },
    { k: 'pose', label: '장면 정본 · 자세', stage: 'S4b', gate: 'G4b', skip: true, rev: 'ps1', tasks: ['p3', 'v3'], text: '세 챕터 장면 사실과 자세' },
    { k: 'frame', label: '완성 이미지', stage: 'S4', gate: 'G4', rev: 'fr1', tasks: ['v4'], thumbs: ['frame-ch1', 'frame-ch2', 'frame-ch3'] },
    { k: 'intro', label: '소개 영상', stage: 'S5', gate: 'G5', skip: true, rev: 'vi1', tasks: ['k1'], thumbs: ['hero-b'], sq: true },
    { k: 'action', label: '대기·동작 영상', stage: 'S6', gate: 'G5b', before: true, rev: 'va1', tasks: ['f1', 'f2'], text: '43편' },
    { k: 'traits', label: '특질 시트', stage: 'S7', gate: 'G6', rev: 'tr1', tasks: ['r1'], text: '핵심 특질 3 · 대비 특질 1' },
    { k: 'persona', label: '페르소나 프롬프트', stage: 'S8', gate: 'G6', rev: 'pv1', tasks: ['r2'], text: '긴·짧은 프롬프트' },
    { k: 'data', label: '학습 데이터', stage: 'S9', gate: 'G7', rev: 'ds1', tasks: ['d1', 'd2', 'd3'], text: '5,500개 · 클러스터 14개' },
    { k: 'model', label: '학습 모델', stage: 'S10', gate: 'G8', skip: true, rev: 'tn1', tasks: ['t1', 't2'], text: '블라인드 비교 40쌍 준비' },
    { k: 'release', label: '출시본', stage: 'S11', gate: 'G9', rev: 'rl1', tasks: [], text: 'release-manifest' }
  ];
  const JOB_KINDS = [
    { k: 'video', name: '영상 증보', desc: 'S6만 다시 · 새 동작 영상 추가', fam: { action: 'va2' }, tasks: ['f1', 'f2'] },
    { k: 'persona', name: '페르소나 개정', desc: 'S7·S8 개정 · 뒤의 데이터와 학습도 다시', fam: { traits: 'tr2', persona: 'pv2', data: 'ds2', model: 'tn2' }, tasks: ['r1', 'r2', 'd1', 'd2', 'd3', 't1', 't2'] },
    { k: 'data', name: '데이터 보강', desc: 'S9 보강 · 학습 다시', fam: { data: 'ds2', model: 'tn2' }, tasks: ['d1', 'd2', 'd3', 't1', 't2'] }
  ];
  const jobCost = (j) => j.tasks.reduce((a, id) => a + task(id).cost, 0);


  // ---------- 상태
  let S;
  const blank = () => ({
    t: 0, speed: 2, auto: false, cap: 30, running: false, paused: false, cancelled: false, finished: false, axisT: 0, open: null, sunk: 0,
    tasks: Object.fromEntries(TASKS.map((t) => [t.id, { st: 'queued', start: 0, end: 0, p: 0, extra: 0, failed: false, held: false, attempts: [], notes: [], rev: 1, partial: null }])),
    gates: Object.fromEntries(GATES.map((g) => [g.id, { st: 'idle', since: 0, at: 0, by: '' }])),
    probs: [], log: [], reviews: [], notes: [], unread: 0, otherDone: {}, logFilter: 'all', jobs: [], released: false, releasedAt: 0, charFilter: 'all', newJobOpen: false
  });
  const st = (id) => (isGate(id) ? S.gates[id].st : S.tasks[id].st);
  const dur = (id) => task(id).dur + S.tasks[id].extra;
  const xcost = (id) => task(id).cost * (S.tasks[id].extra / task(id).dur);
  const depOk = (d) => (isGate(d) ? S.gates[d].st === 'approved' : S.tasks[d].st === 'done');
  const depTime = (d) => (isGate(d) ? S.gates[d].at : S.tasks[d].end);
  const committed = () => S.sunk + TASKS.reduce((a, t) => a + (S.tasks[t.id].st === 'queued' ? 0 : t.cost + xcost(t.id)), 0);
  const spent = () => S.sunk + TASKS.reduce((a, t) => a + (t.cost + xcost(t.id)) * S.tasks[t.id].p, 0);
  // revision: 사람이 다시 실행하거나 수정을 요청하면 올라간다. 자동 재시도는 같은 revision 안의 시도다.
  const REVP = (id) => task(id).rev.replace(/\d+$/, '');
  // revision 번호 = 정의의 시작 번호(pr2면 2) + 다시 만든 횟수
  const revBase = (id) => +task(id).rev.match(/\d+$/)[0];
  const revAt = (id, r) => REVP(id) + (revBase(id) + (r || 1) - 1);
  const revOf = (id) => { const p = REVP(id); return p + Math.max(...TASKS.filter((t) => REVP(t.id) === p).map((t) => revBase(t.id) + (S.tasks[t.id].rev || 1) - 1)); };
  // 입력 표시: 정의에 적힌 revision 대신 지금 그 산출물의 revision을 쓴다
  const PREFIXES = new Set(TASKS.map((t) => REVP(t.id)));
  const liveRef = (x) => x.replace(/\b([a-z]{2})(\d+)\b/g, (m, p) => (PREFIXES.has(p) ? revOf(TASKS.find((t) => REVP(t.id) === p).id) : m));
  const needsOf = (G) => G.needs || [];
  // 수정 요청을 받으면 다시 만드는 작업. 그 밖의 관문은 마지막 선행 작업
  const SUBJ = { G6: 'r2', G7: 'd2' };
  const subj = (gid) => SUBJ[gid] || gate(gid).after[gate(gid).after.length - 1];
  // 완성 이미지: 챕터마다 마지막으로 다시 만든 revision의 그림. 시안에는 2장 수정본 그림만 있다.
  const frameRev = (c) => { let r = 1; S.reviews.forEach((v) => { if (v.gate === 'G4' && v.decision === 'REQUEST_CHANGES' && v.items.some((i) => i.ch === c && !i.ok) && S.tasks.v4.rev > v.revN) r = v.revN + 1; }); return r; };
  const frameSrc = (c, r) => (c === 2 && r >= 2 ? 'frame-ch2-r2' : `frame-ch${c}`);
  const frames = () => [1, 2, 3].map((c) => frameSrc(c, frameRev(c)));
  const thumbsOf = (T) => (T.id === 'v4' ? frames() : T.thumbs);
  const TRIG = { start: '첫 실행', auto: '자동 재시도', human: '다시 실행', settings: '설정 바꿔 다시 실행', request: '수정 요청 반영', upstream: '앞 작업이 바뀌어 다시' };
  const lastRequest = (gid) => { for (let i = S.reviews.length - 1; i >= 0; i--) { const v = S.reviews[i]; if (v.gate === gid) return v.decision === 'REQUEST_CHANGES' ? v : null; } return null; };
  const projected = () => S.sunk + TASKS.reduce((a, t) => a + t.cost + xcost(t.id), 0);

  const PLAN = (() => {
    const e = {};
    const f = (id) => { if (e[id] != null) return e[id]; if (isGate(id)) return (e[id] = Math.max(...gate(id).after.map(f), ...needsOf(gate(id)).map(f))); const T = task(id); return (e[id] = Math.max(0, ...T.deps.map(f)) + T.dur); };
    TASKS.forEach((t) => f(t.id));
    return { total: Math.max(...TASKS.map((t) => e[t.id])), end: e };
  })();
  // 같은 팀에서 동시에 도는 작업은 다른 줄에 놓는다 (계획 일정 기준, 여유 15분)
  const TRACK = {}, LANES = {};
  TEAMS.forEach((tm) => {
    const ends = [];
    teamTasks(tm.id).map((t) => ({ t, s: PLAN.end[t.id] - t.dur, e: PLAN.end[t.id] })).sort((a, b) => a.s - b.s).forEach(({ t, s, e }) => {
      let k = ends.findIndex((x) => x + 15 <= s);
      if (k < 0) { k = ends.length; ends.push(e); } else ends[k] = e;
      TRACK[t.id] = Math.min(k, 1);
    });
    LANES[tm.id] = Math.min(2, Math.max(1, ends.length));
  });
  const gTrack = (g) => { const own = g.after.find((a) => task(a).team === g.team); return own ? TRACK[own] : 0; };

  // G9 출시 결재: 모든 작업이 끝나면 사람 결재를 기다린다. 결재함·KPI·공장 현장이 같은 판정을 쓴다.
  const relPending = () => !!(S.finished && !S.released && !S.cancelled);
  // 정체(제안 기준): 결재는 30분 넘게 기다리면, 작업은 계획 시간의 1.5배를 넘게 돌면
  const STALL_GATE = 30, STALL_TASK = 1.5;
  function stall(id) {
    if (id === 'G9') return relPending() && S.t - (S.finishedAt || S.t) >= STALL_GATE;
    if (isGate(id)) { const g = S.gates[id]; return !!g && g.st === 'pending' && S.t - g.since >= STALL_GATE; }
    const s = S.tasks[id]; return !!s && s.st === 'running' && !S.paused && S.t - s.start > task(id).dur * STALL_TASK;
  }
  function log(actor, html, ref) { S.log.unshift({ t: S.t, actor, html, ref }); if (S.log.length > 120) S.log.pop(); }
  // 알림 = 사람이 다시 볼 사건 기록. 결재 요청·승인(출발한 팀), 재시도 결과, 사람 필요·다시 실행, 수정 요청, 라인 완료, 출시. 작업 시작·완료와 진행 단계는 넣지 않는다
  function notify(kind, html, ref) { S.noteSeq = (S.noteSeq || 0) + 1; S.notes.unshift({ t: S.t, kind, html, ref, seq: S.noteSeq }); if (S.notes.length > 50) S.notes.pop(); S.unread += 1; }
  // 이 결재로 지금 시작할 수 있게 된 작업과 열리는 관문(공장 현장의 승인 순간 표시도 같은 값을 쓴다)
  function unlockedBy(gid) {
    const tasks = TASKS.filter((t) => t.deps.includes(gid) && t.deps.every(depOk)).map((t) => t.id);
    const gates = GATES.filter((G) => needsOf(G).includes(gid) && needsOf(G).every((n) => S.gates[n].st === 'approved') && G.after.every((a) => S.tasks[a].st === 'done')).map((G) => G.id);
    return { tasks, gates, teams: [...new Set(tasks.map((x) => task(x).team).concat(gates.map((x) => gate(x).team)))].map((x) => team(x).name) };
  }
  const gateDone = (G) => (G.kind === 'pick' ? '확정' : /승인$/.test(G.title) ? '완료' : '승인');
  // 라인 완료: 팀의 작업이 모두 끝나고 팀 관문이 모두 승인된 순간 한 번
  function checkLines() {
    S.lineDone = S.lineDone || {};
    TEAMS.forEach((tm) => {
      const ok = teamTasks(tm.id).every((t) => S.tasks[t.id].st === 'done') && GATES.filter((g) => g.team === tm.id).every((g) => S.gates[g.id].st === 'approved');
      if (ok && !S.lineDone[tm.id]) { S.lineDone[tm.id] = true; notify('done', '<b>' + tm.name + '</b> 라인 완료'); }
      else if (!ok && S.lineDone[tm.id]) delete S.lineDone[tm.id];
    });
  }

  // ---------- 진행
  function startReady() {
    let started = true;
    while (started) {
      started = false;
      TASKS.forEach((T) => {
        const s = S.tasks[T.id];
        if (s.st !== 'queued' || !T.deps.every(depOk)) return;
        if (committed() + T.cost > S.cap + 1e-9) { if (!s.held) { s.held = true; log('system', `예산 상한 · <b>${esc(T.short)}</b> 대기`); } return; }
        s.held = false;
        s.st = 'running'; s.start = Math.max(0, ...T.deps.map(depTime), s.restartAt || 0); s.restartAt = 0;
        s.p = clamp((S.t - s.start) / dur(T.id));
        s.attempts.push({ n: s.attempts.length + 1, start: s.start, st: 'running', note: s.pendingNote || '', trigger: s.pendingTrig || (s.attempts.length ? 'human' : 'start'), memo: s.pendingMemo || '', rev: revOf(T.id) }); s.pendingNote = ''; s.pendingTrig = ''; s.pendingMemo = '';
        log('agent', `<b>${T.agent}</b> · ${esc(T.short)} 시작`, T.id); flashRow(T.team); started = true;
      });
    }
  }
  // 구성 보기가 열려 있는 동안은 시간을 멈춘다(발표자가 설명하는 동안 화면이 바뀌지 않게). 저장하지 않는 화면 상태다
  let frozen = false;
  function advance(dtReal) {
    if (frozen || !S.running || S.finished || S.cancelled) return;
    const dt = dtReal * S.speed;
    S.t += dt;
    TASKS.forEach((T) => {
      const s = S.tasks[T.id];
      if (s.st === 'blocked' || (S.paused && s.st === 'running')) { s.start += dt; return; }
      if (s.st !== 'running') return;
      s.p = clamp((S.t - s.start) / dur(T.id));
      if (T.fail && !s.failed && s.p >= T.fail.at) failTask(T);
      if (s.st === 'running' && S.t >= s.start + dur(T.id)) finishTask(T);
    });
    if (S.paused) return;
    GATES.forEach((G) => {
      const g = S.gates[G.id];
      if (g.st === 'idle' && G.after.every((a) => S.tasks[a].st === 'done') && needsOf(G).every((n) => S.gates[n].st === 'approved')) {
        g.st = 'pending'; g.since = Math.max(...G.after.map((a) => S.tasks[a].end), ...needsOf(G).map((n) => S.gates[n].at));
        log('system', `결재 요청 · <b>${G.code} ${esc(G.title)}</b> → ${ME}`, G.id); notify('gate', `<b>${esc(G.title)}</b> 결재 요청 · ${team(G.team).name}`, G.id);
        flashRow(G.team); flashKpi('gate');
      }
      if (g.st === 'pending' && S.auto && S.t - g.since > 1.6 * S.speed) approve(G.id, 'auto');
    });
    TASKS.forEach((T) => { const s = S.tasks[T.id]; if (s.st === 'blocked' && S.auto && S.t - s.blockedAt > 1.6 * S.speed) rerun(T.id, { note: '시연 자동 처리 · 다시 실행' }); });
    startReady();
    checkLines();
    if (TASKS.every((t) => S.tasks[t.id].st === 'done')) { S.finished = true; S.finishedAt = S.t; log('system', '<b>모든 작업 완료</b> · G9 출시 승인 요청', 'G9'); notify('gate', '<b>모든 작업 완료</b> · 출시 승인 결재 요청', 'G9'); }
  }
  function failTask(T) {
    const s = S.tasks[T.id], F = T.fail, a = s.attempts[s.attempts.length - 1];
    s.failed = true;
    a.st = 'fail'; a.end = S.t; a.check = `${F.check} ${F.score} · 기준 ${F.limit}`;
    if (F.mode === 'auto') {
      s.extra += F.add; s.p = clamp((S.t - s.start) / dur(T.id));
      s.attempts.push({ n: a.n + 1, start: S.t, st: 'running', note: '자동 재시도', trigger: 'auto', rev: revOf(T.id) });
      S.probs.unshift({ id: T.id, team: T.team, kind: 'auto', text: F.text, sub: F.sub, at: S.t, st: 'open' });
      log('system', `${team(T.team).name} · <b>${esc(F.text)}</b> · 자동 재시도`, T.id);
    } else {
      [2, 3].forEach((n) => s.attempts.push({ n: a.n + n - 1, start: S.t, end: S.t, st: 'fail', note: '자동 재시도', check: a.check, trigger: 'auto', rev: revOf(T.id) }));
      s.st = 'blocked'; s.blockedAt = S.t;
      S.probs.unshift({ id: T.id, team: T.team, kind: 'human', text: F.text, sub: F.sub, at: S.t, st: 'open' });
      log('system', `${team(T.team).name} · <b>${esc(F.text)}</b> · 사람 필요`, T.id);
      notify('human', `<b>${esc(T.short)}</b> 사람 필요 · ${esc(F.check)} ${esc(F.score)}`, T.id);
    }
    flashRow(T.team); flashKpi('prob');
  }
  function finishTask(T) {
    const s = S.tasks[T.id];
    s.st = 'done'; s.p = 1; s.end = s.start + dur(T.id);
    const a = s.attempts[s.attempts.length - 1]; if (a && a.st === 'running') { a.st = 'ok'; a.end = s.end; }
    S.probs.forEach((p) => { if (p.id === T.id && p.st === 'open') { p.st = 'resolved'; p.done = s.end; } });
    log('agent', `${team(T.team).name} · <b>${esc(T.short)}</b> 완료`, T.id);
    if (a && a.trigger === 'auto' && T.fail) notify('done', `<b>${esc(T.short)}</b> 자동으로 다시 만들어 통과 · ${esc(T.fail.check)}`, T.id);
    else if (a && (a.trigger === 'human' || a.trigger === 'settings')) notify('done', `<b>${esc(T.short)}</b> 다시 실행해 완료`, T.id);
    flashRow(T.team);
  }

  function approve(gid, by, choice) {
    const g = S.gates[gid];
    if (!g || g.st !== 'pending') return;
    g.st = 'approved'; g.at = S.t; g.by = by === 'auto' ? '시연 자동 결재' : ME;
    { const src = subj(gid); S.reviews.push({ gate: gid, rev: revOf(src), revN: S.tasks[src].rev, at: S.t, by: g.by, decision: 'APPROVE', items: [] }); }
    log(by === 'auto' ? 'system' : 'human', `<b>${g.by}</b> · ${gid} ${esc(gate(gid).title)} 결재${choice ? ` · ${esc(choice)}` : ''}`, gid);
    { const G = gate(gid), u = unlockedBy(gid); notify('done', `<b>${esc(G.title)}</b> ${gateDone(G)}${u.teams.length ? ` → ${u.teams.join(' · ')} 시작` : ''}`, gid); }
    if (gid === 'G3') S.name = '윤서하';
    if (gid === 'G1') S.avatar = true;
    const el = $(`.gate[data-gate="${gid}"]`);
    if (el) { el.classList.add('is-approved'); const row = el.querySelector('.gate-row'); if (row) row.outerHTML = `<div class="gate-done">${icon('check')}결재했어요 · 다음 작업을 시작해요</div>`; setTimeout(() => { el.classList.add('is-gone'); setTimeout(() => el.remove(), 300); }, 900); }
    if (S.open && S.open.gate === gid) closeDrawer();
    flashKpi('gate'); startReady(); checkLines(); save();
  }

  // 작업 다시 실행: 뒤에 이어진 작업과 결재도 함께 되돌린다
  function downstream(id) {
    const tasks = new Set(), gates = new Set();
    const visit = (x) => {
      TASKS.forEach((t) => { if (!tasks.has(t.id) && t.deps.includes(x)) { tasks.add(t.id); visit(t.id); } });
      GATES.forEach((g) => { if (!gates.has(g.id) && (g.after.includes(x) || needsOf(g).includes(x))) { gates.add(g.id); visit(g.id); } });
    };
    visit(id);
    return { tasks: [...tasks].filter((t) => S.tasks[t].st !== 'queued'), gates: [...gates].filter((g) => S.gates[g].st !== 'idle') };
  }
  function rerunImpact(id) {
    const d = downstream(id);
    const list = [id, ...d.tasks];
    return { ...d, cost: list.reduce((a, x) => a + task(x).cost, 0), minutes: Math.max(...list.map((x) => task(x).dur)), teams: [...new Set(d.tasks.map((x) => team(task(x).team).name))] };
  }
  function rerun(id, opt = {}) {
    const T = task(id), s = S.tasks[id];
    if (s.st === 'blocked') {
      const left = (1 - s.p) * T.dur;
      s.st = 'running'; s.extra += (T.fail ? T.fail.add : 0); s.start = S.t - s.p * dur(id);
      s.attempts.push({ n: s.attempts.length + 1, start: S.t, st: 'running', note: opt.note || '다시 실행', trigger: opt.trigger || 'human', memo: opt.memo || '', rev: revOf(id) });
      S.probs.forEach((p) => { if (p.id === id && p.st === 'open') { p.st = 'resolved'; p.done = S.t + left; p.how = opt.note || '다시 실행'; } });
      notify('info', `<b>${esc(T.short)}</b> 다시 실행 · 사람 확인 후`, id);
      log(opt.note && opt.note.startsWith('시연') ? 'system' : 'human', `<b>${opt.note && opt.note.startsWith('시연') ? '시연 자동 처리' : ME}</b> · ${esc(T.short)} 다시 실행${opt.settings ? ` · ${esc(opt.settings)}` : ''}`, id);
      save(); return;
    }
    const d = downstream(id);
    [id, ...d.tasks].forEach((x) => {
      const ss = S.tasks[x], TT = task(x);
      S.sunk += (TT.cost + xcost(x)) * ss.p;
      const last = ss.attempts[ss.attempts.length - 1]; if (last && last.st === 'running') { last.st = 'stopped'; last.end = S.t; }
      Object.assign(ss, { st: 'queued', p: 0, start: 0, end: 0, extra: 0, failed: x === id ? true : ss.failed, held: false, restartAt: S.t });
      ss.rev = (ss.rev || 1) + 1; ss.partial = null;
      if (x !== id) { ss.pendingTrig = 'upstream'; ss.pendingMemo = `${T.short} ${revAt(id, s.rev)}`; }
    });
    s.failed = !!T.fail && s.failed; s.pendingNote = opt.settings ? `설정 변경 · ${opt.settings}` : '다시 실행';
    s.pendingTrig = opt.trigger || (opt.settings ? 'settings' : 'human'); s.pendingMemo = opt.memo || '';
    if (opt.chapters) {
      const from = revAt(id, s.rev - 1), keep = [1, 2, 3].filter((c) => !opt.chapters.includes(c));
      s.partial = { chs: opt.chapters, keep, from, memo: opt.memo || '' };
      s.extra = -T.dur * (1 - Math.max(0.45, opt.chapters.length / 3));
      log('agent', `<b>${T.agent}</b> · ${esc(T.short)} ${revOf(id)} · ${opt.chapters.join('·')}장만 다시 만들어요${keep.length ? ` · ${keep.join('·')}장은 ${from}에서 가져옴` : ''}`, id);
    }
    d.gates.forEach((g) => { Object.assign(S.gates[g], { st: 'idle', since: 0, at: 0, by: '' }); const el = $(`.gate[data-gate="${g}"]`); if (el) el.remove(); });
    log('human', `<b>${ME}</b> · ${esc(T.short)} 다시 실행${opt.settings ? ` · ${esc(opt.settings)}` : ''}${d.tasks.length ? ` · 뒤 작업 ${d.tasks.length}개 함께` : ''}`, id);
    startReady(); save();
  }
  function skipTask(id) {
    const T = task(id), s = S.tasks[id];
    s.st = 'done'; s.end = S.t; s.p = 1;
    const a = s.attempts[s.attempts.length - 1]; if (a) a.note = (a.note ? a.note + ' · ' : '') + '건너뜀';
    S.probs.forEach((p) => { if (p.id === id && p.st === 'open') { p.st = 'resolved'; p.done = S.t; p.how = '클러스터 9를 빼고 진행'; } });
    log('human', `<b>${ME}</b> · ${esc(T.short)} 건너뛰기 · 클러스터 9 제외`);
    startReady(); save();
  }

  // ---------- 저장과 복원 (작업실에 다녀와도 이어서 보이도록)
  // picks: 결재 대기 중인 고르기 관문을 풀리는 작업이 많은 순서로 저장해 작업실 상단바도 같은 순서를 쓴다
  function save() { try { localStorage.setItem(STORE, JSON.stringify({ S: { ...S, open: null }, at: Date.now(), picks: pickList() })); } catch (e) {} }
  function restore() {
    try {
      const raw = JSON.parse(localStorage.getItem(STORE) || 'null');
      if (!raw || !raw.S || !raw.S.tasks) return false;
      S = { ...blank(), ...raw.S, open: null };
      const away = Math.min(90, (Date.now() - raw.at) / 1000);
      for (let k = 0; k < away; k += 0.1) advance(0.1);
      return true;
    } catch (e) { return false; }
  }
  // 작업실에서 결재하고 돌아온 관문: 공장 현장이 '승인 순간' 표시를 띄우도록 넘겨준다(저장하지 않는 화면 상태)
  let justApproved = [];
  function applyApprovals() {
    try {
      const list = JSON.parse(localStorage.getItem('cf-approvals') || '[]');
      if (!list.length) return;
      list.forEach((a) => {
        if (a.run && a.run !== RUN_ID) { const o = OTHERS.find((x) => x.id === a.run); if (o) S.otherDone[o.key] = true; log('human', `<b>${ME}</b> · ${esc(a.run)} ${esc(a.gate)} 결재`); return; }
        justApproved.push(a.gate);
        approve(a.gate, 'human', a.choice && a.choice.length ? `선택 ${a.choice.join(', ')}` : '');
      });
      localStorage.setItem('cf-approvals', '[]');
    } catch (e) {}
  }

  // ---------- 그리기 도우미
  function flashRow(tid) { const r = $(`.row.body[data-team="${tid}"]`); if (!r) return; r.classList.add('flash'); setTimeout(() => r.classList.remove('flash'), 60); }
  function flashKpi(k) { const r = $(`.kpi[data-kpi="${k}"]`); if (!r) return; r.classList.add('flash'); setTimeout(() => r.classList.remove('flash'), 60); }
  const set = (el, html) => { if (el && el._h !== html) { el._h = html; el.innerHTML = html; } };

  function build() {
    $('[data-grid]').innerHTML = `<div class="row head"><div class="cell">팀</div><div class="cell">상태</div><div class="cell">지금 작업</div><div class="cell">진행</div><div class="cell" style="justify-content:flex-end">남은 시간</div><div class="cell c-tl"><div class="ticks" data-ticks></div></div></div>`
      + TEAMS.map((tm) => `<div class="row body" data-team="${tm.id}">
        <div class="cell c-team" role="button" tabindex="0" aria-expanded="false">${icon(tm.icon)}<span class="team-name"><b>${tm.name}</b><small>${teamStages(tm.id)}</small></span>${icon('chevron', 'ic chev')}</div>
        <div class="cell"><span class="pill" data-pill><span class="dot"></span><span></span></span></div>
        <div class="cell c-now"><span class="now-main" data-now></span><span class="now-sub" data-sub></span></div>
        <div class="cell c-prog"><span class="bar"><i data-bar></i></span><span class="num" data-pct></span></div>
        <div class="cell c-left num" data-left></div>
        <div class="cell c-tl"><div class="lane${LANES[tm.id] > 1 ? ' two' : ''}">${teamTasks(tm.id).map((t) => `<button type="button" class="tb tb-plan" style="--k:${TRACK[t.id]}" data-plan="${t.id}" data-task="${t.id}" title="${esc(t.stage + ' ' + t.short + ' · ' + t.agent)}">${esc(t.short)}</button><button type="button" class="tb tb-act" style="--k:${TRACK[t.id]}" data-act="${t.id}" data-task="${t.id}" title="${esc(t.stage + ' ' + t.short + ' · ' + t.agent)}">${esc(t.short)}</button>${t.fail ? `<span class="tb tb-retry" style="--k:${TRACK[t.id]}" data-retry="${t.id}" title="재시도"></span>` : ''}`).join('')}${GATES.filter((g) => g.team === tm.id).map((g) => `<span class="tb tb-gate" style="--k:${gTrack(g)}" data-gw="${g.id}" title="${esc(g.code + ' ' + g.title)} 결재 대기"></span>`).join('')}<span class="now-line" data-nowline></span></div></div>
      </div><div class="detail" data-detail="${tm.id}"></div>`).join('');
  }

  function teamView(tid, fc) {
    const ts = teamTasks(tid);
    const run = ts.filter((t) => S.tasks[t.id].st === 'running');
    const pend = GATES.find((g) => g.team === tid && S.gates[g.id].st === 'pending');
    const human = ts.find((t) => S.tasks[t.id].st === 'blocked');
    const openProb = S.probs.find((p) => p.team === tid && p.st === 'open' && p.kind === 'auto');
    const held = ts.find((t) => S.tasks[t.id].held);
    const done = ts.every((t) => S.tasks[t.id].st === 'done');
    const others = (x) => { const n = run.filter((t) => t.id !== x).length; return n ? ` · 다른 작업 ${n}개 진행 중` : ''; };
    let s, label, main, sub = '', subCls = '';
    if (S.cancelled && !done) { s = 'cancelled'; main = '실행이 취소됐어요'; }
    else if (human) { s = 'human'; main = `${human.agent} · ${human.short}`; sub = task(human.id).fail.text + others(human.id); subCls = 'is-bad'; }
    else if (pend) { s = 'gate'; main = `${pend.code} ${pend.title}`; sub = `${dur$(S.t - S.gates[pend.id].since)}째 대기${run.length ? ` · 작업 ${run.length}개 진행 중` : ''}`; subCls = 'is-warn'; }
    else if (openProb) { s = 'retry'; main = `${task(openProb.id).agent} · ${task(openProb.id).short}`; sub = openProb.text + others(openProb.id); subCls = 'is-bad'; }
    else if (run.length) { s = S.paused ? 'paused' : 'working'; main = run.map((t) => t.short).join(' · '); sub = run.map((t) => `${t.stage} ${t.agent}`).join(', '); }
    else if (held) { s = 'budget'; main = `다음 · ${held.short}`; sub = `예산 상한 ${usd(S.cap)}에 닿아 멈춤`; subCls = 'is-warn'; }
    else if (done) { s = 'done'; main = ts[ts.length - 1].out; sub = `${hm(Math.max(...ts.map((t) => S.tasks[t.id].end)))} 완료`; }
    else {
      s = 'idle';
      const next = ts.find((t) => S.tasks[t.id].st === 'queued');
      main = next ? `다음 · ${next.short}` : '–';
      const dep = next && next.deps.find((d) => !depOk(d));
      if (!S.running) sub = `${hm(fc.start[next.id])} 시작 예정`;
      else if (dep) sub = isGate(dep) ? `${dep} ${gate(dep).title} 결재 뒤 시작` : `${team(task(dep).team).name} · ${task(dep).short} 뒤 시작`;
    }
    const tdur = ts.reduce((a, t) => a + dur(t.id), 0), tdone = ts.reduce((a, t) => a + dur(t.id) * S.tasks[t.id].p, 0);
    const endT = Math.max(...ts.map((t) => fc.end[t.id]));
    return { s, label, main, sub, subCls, pct: Math.round((tdone / tdur) * 100), left: done ? '–' : dur$(endT - S.t) };
  }

  function forecast() {
    const end = {}, start = {}, gend = {};
    const fin = (id) => {
      if (isGate(id)) {
        if (gend[id] != null) return gend[id];
        const g = S.gates[id];
        return (gend[id] = g.st === 'approved' ? g.at : g.st === 'pending' ? S.t : Math.max(S.t, ...gate(id).after.map(fin), ...needsOf(gate(id)).map(fin)));
      }
      if (end[id] != null) return end[id];
      const s = S.tasks[id], T = task(id);
      if (s.st === 'done') { start[id] = s.start; return (end[id] = s.end); }
      if (s.st === 'running') { start[id] = s.start; return (end[id] = Math.max(S.t, s.start + dur(id))); }
      if (s.st === 'blocked') { start[id] = s.start; return (end[id] = S.t + (1 - s.p) * T.dur + (T.fail ? T.fail.add : 0)); }
      start[id] = Math.max(S.running ? S.t : 0, 0, ...T.deps.map(fin));
      return (end[id] = start[id] + dur(id));
    };
    TASKS.forEach((t) => fin(t.id));
    const total = Math.max(...TASKS.map((t) => end[t.id]));
    const crit = new Set();
    let cur = TASKS.reduce((a, t) => (end[t.id] > end[a.id] ? t : a)).id;
    for (let guard = 0; cur && guard < 40; guard++) {
      crit.add(cur);
      let next = null;
      for (const d of task(cur).deps) { const e = isGate(d) ? gend[d] : end[d]; if (Math.abs(e - start[cur]) < 1e-6) { next = d; break; } }
      if (!next) break;
      if (isGate(next)) { crit.add(next); next = gate(next).after.reduce((a, b) => (end[b] > end[a] ? b : a)); }
      cur = next;
    }
    return { end, start, gend, total, crit };
  }

  function impact(gid) {
    const blocked = new Set();
    let grew = true;
    while (grew) {
      grew = false;
      TASKS.forEach((t) => { if (blocked.has(t.id) || S.tasks[t.id].st !== 'queued') return; if (t.deps.some((d) => d === gid || blocked.has(d) || (isGate(d) && gate(d).after.some((a) => blocked.has(a))))) { blocked.add(t.id); grew = true; } });
    }
    const list = [...blocked].map(task);
    return { teams: new Set(list.map((t) => t.team)).size, minutes: list.reduce((a, t) => a + t.dur, 0), names: [...new Set(list.map((t) => team(t.team).name))] };
  }

  // ---------- 화면
  function route() {
    const h = location.hash.replace('#', '');
    if (h === 'run' || h.startsWith('job/')) return { v: 'job', c: SEOHA, sub: h.endsWith('/floor') ? 'floor' : 'table' };
    if (h.startsWith('char/')) { const c = h.slice(5); return { v: 'char', c: c === SEOHA || other(c) ? c : SEOHA }; }
    return { v: 'chars' };
  }
  const view = () => route().v;

  function seohaLife() {
    const k = S.released ? 'released' : S.finished ? 'ready' : S.gates.G3.st === 'approved' ? 'making' : 'planning';
    return [k, ST.label('life', k)];
  }
  const avatarHTML = (c) => (c === SEOHA ? (S.avatar ? `<img src="${A('hero-b')}" alt="">` : esc((S.name || '새').slice(0, 1))) : esc(other(c).name.slice(0, 1)));
  const nameOf = (c) => (c === SEOHA ? S.name || '새 캐릭터' : other(c).name);
  const idOf = (c) => (c === SEOHA ? (S.gates.G3.st === 'approved' ? RUN_ID : '') : other(c).id);

  function famState(f) {
    const frev = f.tasks.length ? revOf(f.tasks[0]) : f.rev;
    const jobRev = S.jobs.map((j) => JOB_KINDS.find((k) => k.k === j.k).fam[f.k]).filter(Boolean)[0];
    const ts = f.tasks.map((id) => S.tasks[id]);
    let st = 'none', cur = '', curAt = '', prog = '';
    if (f.k === 'release') {
      if (S.released) { st = 'approved'; cur = frev; curAt = hm(S.releasedAt); }
      else if (S.finished) { st = 'pending'; prog = `${frev} · 출시 승인 대기`; }
      return { st, cur, curAt, prog };
    }
    const anyRun = ts.some((t) => t.st === 'running' || t.st === 'blocked');
    const allDone = ts.length > 0 && ts.every((t) => t.st === 'done');
    const g = f.gate && !f.skip && !f.auto ? S.gates[f.gate] : null;
    const pct = ts.length ? Math.round((ts.reduce((a, t) => a + t.p, 0) / ts.length) * 100) : 0;
    const lastEnd = () => hm(Math.max(...ts.map((t) => t.end)));
    if (f.before) {
      if (allDone) { st = 'approved'; cur = frev; curAt = lastEnd(); }
      else if (anyRun) { st = 'running'; prog = `${frev} · 만드는 중 ${pct}%`; }
      else if (g && g.st === 'pending') { st = 'pending'; prog = `${f.gate} 움직임 고르기 대기`; }
    } else if (g && g.st === 'approved') { st = 'approved'; cur = frev; curAt = hm(g.at); }
    else if (g && g.st === 'pending') { st = 'pending'; prog = `${frev} · ${f.gate} 결재 대기`; }
    else if (ts.some((t) => t.st === 'blocked')) { st = 'human'; prog = `${frev} · 사람 필요`; }
    else if (anyRun) { st = 'running'; prog = `${frev} · 만드는 중 ${pct}%`; }
    else if (allDone && !g) { st = 'approved'; cur = frev; curAt = lastEnd(); }
    else if (allDone) { st = 'running'; prog = `${frev} · 결재 준비 중`; }
    if (jobRev) { prog = `${jobRev} · 작업 요청 대기열`; if (st === 'none') st = 'queued'; }
    return { st, cur, curAt, prog };
  }
  function otherFam(o, f) {
    const a = o.assets[f.k];
    if (!a) return { st: 'none', cur: '', prog: '', note: '' };
    if (a.cur) return { st: 'approved', cur: a.cur, curAt: a.at, prog: '', note: a.note || '' };
    if (S.otherDone[o.key]) return { st: 'approved', cur: a.prog, curAt: '오늘', prog: '', note: a.note || '' };
    return { st: 'pending', cur: '', prog: `${a.prog} · ${o.gate.code} 결재 대기`, note: a.note || '' };
  }
  const famsOf = (c) => FAM.map((f) => ({ f, s: c === SEOHA ? famState(f) : otherFam(other(c), f) }));

  function charSummary(c) {
    if (c === SEOHA) {
      const [life, lifeLabel] = seohaLife();
      const pend = GATES.filter((g) => S.gates[g.id].st === 'pending').length + (S.finished && !S.released ? 1 : 0);
      const human = TASKS.filter((t) => S.tasks[t.id].st === 'blocked').length;
      const sm = runSummary(forecast());
      const jobs = [{ name: '신규 생성', label: sm.label, status: sm.status }, ...S.jobs.map((j) => ({ name: JOB_KINDS.find((k) => k.k === j.k).name, label: ST.label('job', 'queued'), status: 'queued' }))];
      return { life, lifeLabel, pend, human, cost: usd(spent()), last: S.running ? `오늘 ${hm(S.t)}` : '오늘', jobs };
    }
    const o = other(c), done = S.otherDone[c];
    return { life: 'making', lifeLabel: ST.label('life', 'making'), pend: done ? 0 : 1, human: 0, cost: o.cost, last: done ? '오늘' : o.created, jobs: [{ name: o.job.name, label: ST.label('job', done ? 'next' : 'gate'), status: done ? 'next' : 'gate' }] };
  }
  const CHAR_KEYS = () => [SEOHA, ...OTHERS.map((o) => o.key)];

  function render() {
    const rt = route(), v = rt.v;
    document.body.dataset.view = v;
    document.body.dataset.sub = rt.sub || '';
    $$('[data-nav]').forEach((a) => { a.classList.add('is-active'); a.setAttribute('aria-current', 'page'); });
    const fc = forecast();
    const pend = GATES.filter((g) => S.gates[g.id].st === 'pending');
    const otherPend = OTHERS.filter((o) => !S.otherDone[o.key]);
    const totalPend = pend.length + otherPend.length + (relPending() ? 1 : 0);
    document.title = `${totalPend ? `(${totalPend}) ` : ''}캐릭터 공장 · ${v === 'chars' ? '캐릭터' : nameOf(rt.c)}`;
    renderCrumbs(rt);
    const live = S.cancelled ? '<span class="dot is-bad"></span>취소됨' : S.released ? '<span class="dot is-on"></span>출시됨' : S.finished ? '<span class="dot is-warn"></span>작업 완료 · 출시 결재 대기' : S.paused ? '<span class="dot is-warn"></span>일시정지' : S.running ? `<span class="dot is-on"></span>실행 중 · ${hm(S.t)}` : '<span class="dot"></span>시작 전';
    set($('[data-live]'), live);
    const ctl = $('[data-run-ctl]');
    ctl.hidden = v !== 'job' || !S.running || S.finished || S.cancelled;
    set(ctl.querySelector('[data-pause]'), S.paused ? `${icon('play')}재개` : `${icon('pause')}일시정지`);
    if (v === 'chars') renderChars();
    else if (v === 'char') renderChar(rt.c);
    else renderRun(fc, pend);
    if (v === 'job') {
      $$('[data-sub-tab]').forEach((a) => { const on = a.dataset.subTab === rt.sub; a.classList.toggle('is-on', on); a.setAttribute('aria-current', on ? 'page' : 'false'); });
      set($('[data-job-hint]'), rt.sub === 'floor' ? '작업대를 누르면 앞뒤 작업을 따라가요 · 한 번 더 누르면 상세 · 관문 표시에서 바로 결재해요' : '팀 이름을 누르면 작업별 상세, 막대를 누르면 호출 기록이 열려요');
    }
    if (v === 'job' && rt.sub === 'floor') window.CF_FLOOR.render(); else window.CF_FLOOR.hide();
    let inbox;
    const relItem = relPending() ? [{ release: true }] : [];
    if (v === 'chars') inbox = [...relItem, ...pend, ...revisingCards(), ...otherPend.map((o) => ({ other: o }))];
    else if (v === 'char' && rt.c !== SEOHA) inbox = S.otherDone[rt.c] ? [] : [{ other: other(rt.c) }];
    else inbox = [...relItem, ...pend, ...revisingCards()];
    renderInbox(inbox, v);
    renderProbs(v === 'char' && rt.c !== SEOHA ? 'none' : v);
    renderLog();
    renderEvents();
    window.AppBar.render();
    $$('.kpi-sub, .team-name small, .now-sub, .now-main, .jobline .jn, .ch-tag').forEach((e) => { const tt = e.scrollWidth > e.clientWidth + 1 ? e.textContent : ''; if (e.title !== tt) e.title = tt; });
    if (S.open) renderDrawer(fc);
  }

  function renderCrumbs(rt) {
    const el = $('[data-crumbs]');
    if (rt.v === 'chars') { set(el, ''); el.hidden = true; return; }
    el.hidden = false;
    const c = rt.c;
    let h = `<a href="#chars">캐릭터</a>${icon('chevron', 'ic sep')}<a href="#char/${c}" class="crumb-char"><span class="crumb-av">${avatarHTML(c)}</span><b>${esc(nameOf(c))}</b></a>`;
    if (rt.v === 'job') h += `${icon('chevron', 'ic sep')}<span class="crumb-job">신규 생성<code>rf1 → tn1</code></span>`;
    set(el, h);
  }

  function runSummary(fc) {
    const doneN = TASKS.filter((t) => S.tasks[t.id].st === 'done').length;
    const pct = Math.round((TASKS.reduce((a, t) => a + dur(t.id) * S.tasks[t.id].p, 0) / TASKS.reduce((a, t) => a + dur(t.id), 0)) * 100);
    const pend = GATES.filter((g) => S.gates[g.id].st === 'pending');
    const human = TASKS.filter((t) => S.tasks[t.id].st === 'blocked').length;
    let status = 'running';
    if (S.cancelled) status = 'cancelled'; else if (S.finished) status = 'done'; else if (!S.running) status = 'notstarted'; else if (S.paused) status = 'paused'; else if (human) status = 'human'; else if (pend.length) status = 'gate';
    const label = ST.label('job', status) + (status === 'gate' ? ` ${pend.length}` : '');
    return { doneN, pct, pend, human, status, label, eta: S.finished ? `${hm(S.t)} 완료` : hm(fc.total) };
  }

  function famBar(c) {
    const fams = famsOf(c);
    const ok = fams.filter((x) => x.s.st === 'approved').length;
    return `<span class="fambar">${fams.map((x) => `<i class="f-${x.s.st}" title="${esc(x.f.label)} · ${ST.label('asset', x.s.st)}${x.s.cur ? ' ' + esc(x.s.cur) : ''}"></i>`).join('')}</span><small>승인 ${ok}/${FAM.length}</small>`;
  }

  function renderChars() {
    const sums = Object.fromEntries(CHAR_KEYS().map((c) => [c, charSummary(c)]));
    const count = (l) => Object.values(sums).filter((s) => s.life === l).length;
    const n = CHAR_KEYS().length;
    set($('[data-k="c-all-v"]'), `${n}<small>명</small>`);
    set($('[data-k="c-all-s"]'), `기획 중 ${count('planning')} · 제작 중 ${count('making')} · 출시 준비 ${count('ready')}`);
    const allPend = Object.values(sums).reduce((a, s) => a + s.pend, 0);
    set($('[data-k="c-gate-v"]'), `${allPend}<small>건</small>`);
    set($('[data-k="c-gate-s"]'), OTHERS.some((o) => !S.otherDone[o.key]) ? '가장 오래된 결재 · 윤하린 G6 13일째' : allPend ? `${esc(nameOf(SEOHA))}의 결재` : '결재할 일이 없어요');
    $('.kpi[data-kpi="c-gate"]').classList.toggle('is-alert', allPend > 0);
    const human = sums[SEOHA].human;
    set($('[data-k="c-human-v"]'), `${human}<small>건</small>`);
    set($('[data-k="c-human-s"]'), human ? '자동 재시도를 다 쓴 작업이 있어요' : '사람이 나설 실패 없음');
    $('.kpi[data-kpi="c-human"]').classList.toggle('is-bad', human > 0);
    const month = 112.4 + spent();
    set($('[data-k="c-cost-v"]'), `${usd(month)}<small>/ $300</small>`);
    set($('[data-k="c-cost-s"]'), '이번 달 · 워크스페이스 상한');
    $('[data-k="c-cost-m"]').style.setProperty('--w', `${(month / 300) * 100}%`);
    set($('[data-k="c-rel-v"]'), `${count('released')}<small>명 출시됨</small>`);
    set($('[data-k="c-rel-s"]'), count('ready') ? `출시 준비 ${count('ready')}명 · 출시 승인을 기다려요` : '출시 준비 중인 캐릭터 없음');

    const F = S.charFilter;
    const tabs = [['all', '전체', n], ['planning', '기획 중', count('planning')], ['making', '제작 중', count('making')], ['ready', '출시 준비', count('ready')], ['released', '출시됨', count('released')]];
    set($('[data-char-tabs]'), tabs.map(([k, l, c]) => `<button type="button" class="ftab${F === k ? ' is-on' : ''}" data-char-filter="${k}">${l}<span class="num">${c}</span></button>`).join(''));
    const rows = CHAR_KEYS().filter((c) => F === 'all' || sums[c].life === F);
    set($('[data-chars]'), `<div class="crow head"><span>캐릭터</span><span>단계</span><span>자산</span><span>확인할 일</span><span>작업 요청</span><span>누적 비용</span><span>마지막 활동</span></div>`
      + (rows.length ? rows.map((c) => {
        const s = sums[c];
        const id = idOf(c);
        const todo = [s.pend ? `<span class="is-warn">결재 ${s.pend}</span>` : '', s.human ? `<span class="is-bad">사람 필요 ${s.human}</span>` : ''].filter(Boolean).join(' · ') || '<span class="muted">–</span>';
        const jobs = s.jobs.map((j) => `<span class="jobline">${ST.pill('job', j.status, j.label, 'sm')}<span class="jn">${esc(j.name)}</span></span>`).join('');
        return `<a class="crow" href="#char/${c}">
          <span class="r-char"><span class="r-av">${avatarHTML(c)}</span><span><b>${esc(nameOf(c))}</b><small>${id ? esc(id) : '임시 ID · G3 승인 때 확정'}</small></span></span>
          <span>${ST.pill('life', s.life)}</span>
          <span class="c-fam">${famBar(c)}</span>
          <span class="c-todo">${todo}</span>
          <span class="c-jobs">${jobs}</span>
          <span class="muted num">${esc(s.cost)}</span>
          <span class="muted">${esc(s.last)}${icon('chevron', 'ic r-go')}</span></a>`;
      }).join('') : '<div class="crow-empty">이 단계의 캐릭터가 없어요.</div>'));
  }

  function renderChar(c) {
    const s = charSummary(c), o = c === SEOHA ? null : other(c);
    const id = idOf(c);
    const g3 = c === SEOHA && S.gates.G3.st === 'approved';
    const tagline = c === SEOHA ? (g3 ? '기다리는 시간도 한 컷으로 남기는, 자기 속도가 분명한 현상소 직원' : '기획안을 고르면 채워져요') : o.route;
    const meta = c === SEOHA ? (g3 ? '25세 · 필름 사진 현상소 직원 · ISFP' : '씨앗 · 25세 · 필름 현상소 직원') : o.meta;
    const relBtn = c === SEOHA && S.finished && !S.released ? `<button type="button" class="btn btn--primary" data-release>${icon('check')}출시 승인 · G9</button>` : '';
    set($('[data-char-head]'), `
      <span class="ch-av">${avatarHTML(c)}</span>
      <span class="ch-id"><span class="ch-name"><b>${esc(nameOf(c))}</b>${ST.pill('life', s.life)}</span>
        <code>${id ? esc(id) : '임시 ID · character_id는 G3 승인 때 발급돼요'}</code><span class="ch-meta">${esc(meta)}</span><span class="ch-tag">${esc(tagline)}</span></span>
      <span class="ch-stats"><span><small>결재 대기</small><b class="${s.pend ? 'is-warn' : ''}">${s.pend}건</b></span><span><small>사람 필요</small><b class="${s.human ? 'is-bad' : ''}">${s.human}건</b></span><span><small>누적 비용</small><b class="num">${esc(s.cost)}</b></span><span><small>출시본</small><b>${c === SEOHA && S.released ? 'rl1' : '없음'}</b></span></span>
      <span class="ch-actions">${relBtn}${c === SEOHA ? `<button type="button" class="btn${S.newJobOpen ? ' is-on' : ''}" data-newjob-toggle>${icon('plus')}작업 요청</button>` : ''}</span>`);

    const fams = famsOf(c);
    set($('[data-assets]'), `<div class="arow head"><span>자산</span><span>단계 · 관문</span><span>현재 승인본</span><span>진행 중</span><span>미리보기</span></div>` + fams.map(({ f, s: x }) => {
      let prev = '<span class="muted">–</span>';
      if (x.st === 'approved' && c === SEOHA && f.thumbs) prev = `<span class="thumbs">${(f.k === 'frame' ? frames() : f.thumbs).map((t) => `<img class="${f.sq ? 'sq' : ''}" src="${A(t)}" alt="">`).join('')}</span>`;
      else if (x.st === 'approved' && c === SEOHA && f.text) prev = `<span class="muted">${esc(f.text)}</span>`;
      else if (x.note) prev = `<span class="muted">${esc(x.note)}</span>`;
      const progCls = { pending: 'is-warn', human: 'is-bad', queued: 'muted' }[x.st] || '';
      return `<div class="arow a-${x.st}"><span class="a-name"><i class="f-${x.st}"></i>${esc(f.label)}</span>
        <span class="muted">${f.stage} · ${f.gate}${f.skip ? '<sup title="이 데모에서는 결재를 생략했어요">*</sup>' : ''}</span>
        <span>${x.cur ? `<span class="rev">${esc(x.cur)}</span><small>${esc(x.curAt || '')}</small>` : '<span class="muted">아직 없음</span>'}</span>
        <span class="${progCls}">${x.prog ? esc(x.prog) : '<span class="muted">–</span>'}</span>
        <span>${prev}</span></div>`;
    }).join('') + '<p class="assets-note">* G4b·G5·G8은 이 데모에서 결재를 생략했어요. 자산마다 revision이 따로 올라가고, 출시본(release_rev)은 그 시점의 승인본을 묶어요.</p>');

    const sm = runSummary(forecast());
    const jobs = c === SEOHA
      ? [{ live: true, name: '신규 생성', revs: 'rf1 · ar1 · pr2 · bg1 · ps1 · fr1 · vi1 · va1 · tr1 · pv1 · ds1 · tn1', label: sm.label, status: sm.status, note: S.running ? `작업 ${sm.doneN}/${TASKS.length}` : '시작 전', cost: `${usd(spent())} / ${usd(S.cap)}`, when: S.running ? `오늘 ${hm(0)} 시작` : '시작 전' },
        ...S.jobs.map((j) => { const K = JOB_KINDS.find((k) => k.k === j.k); return { name: K.name, revs: Object.values(K.fam).join(' · '), label: ST.label('job', 'queued'), status: 'queued', note: S.finished ? '시작 대기' : '신규 생성이 끝나면 시작', cost: `예상 ${usd(jobCost(K))}`, when: `${hm(j.at)} 요청` }; })]
      : [{ name: o.job.name, revs: o.job.revs, label: S.otherDone[c] ? ST.label('job', 'next') : `${ST.label('job', 'gate')} · G6`, status: S.otherDone[c] ? 'next' : 'gate', note: o.calls, cost: o.cost, when: `${o.created} 실행` }];
    set($('[data-jobs]'), jobs.map((j) => `<${j.live ? 'a href="#job/seoha-new"' : 'div'} class="jrow${j.live ? ' is-live' : ''}">
      <span class="j-name"><b>${esc(j.name)}</b><small>${esc(j.revs)}</small></span>
      <span>${ST.pill('job', j.status, j.label)}</span>
      <span class="muted">${esc(j.note || '')}</span>
      <span class="muted num">${esc(j.cost)}</span><span class="muted">${esc(j.when)}${j.live ? icon('chevron', 'ic r-go') : ''}</span></${j.live ? 'a' : 'div'}>`).join(''));
    const menu = $('[data-newjob]');
    menu.hidden = !(c === SEOHA && S.newJobOpen);
    if (!menu.hidden) set(menu, `<p>무엇을 다시 만들까요? 고른 자산만 새 revision으로 만들고, 나머지는 현재 승인본을 그대로 써요.</p><div class="nj-opts">${JOB_KINDS.map((k) => `<button type="button" class="nj" data-newjob="${k.k}"><b>${k.name}</b><span>${k.desc}</span><small>${Object.entries(k.fam).map(([fk, r]) => `${FAM.find((f) => f.k === fk).label} → ${r}`).join(' · ')} · 예상 ${usd(jobCost(k))}</small></button>`).join('')}</div>`);
  }


  function renderRun(fc, pend) {
    const openP = S.probs.filter((p) => p.st === 'open');
    const humanN = TASKS.filter((t) => S.tasks[t.id].st === 'blocked').length;
    const sp = spent(), proj = projected();
    const doneN = TASKS.filter((t) => S.tasks[t.id].st === 'done').length;
    const runN = TASKS.filter((t) => S.tasks[t.id].st === 'running').length;
    const heldN = TASKS.filter((t) => S.tasks[t.id].held && S.tasks[t.id].st === 'queued').length;
    const delay = Math.max(0, fc.total - PLAN.total);
    const longest = pend.reduce((a, g) => (!a || S.gates[g.id].since < S.gates[a.id].since ? g : a), null);
    const rel = relPending() ? 1 : 0;
    // 크게 보기에서 지표 줄을 대신하는 한 줄 요약. 같은 값을 쓴다
    const hd = (cls, dot, label, val, tail) => '<span class="hd' + (cls ? ' ' + cls : '') + '">' + (dot ? '<i class="hd-d ' + dot + '"></i>' : '') + '<span>' + label + ' <b class="num">' + val + '</b>' + (tail || '') + '</span></span>';
    set($('[data-fl-hud]'), hd('', runN ? 'is-run' : 'is-off', '작업 중 에이전트', runN) + hd(pend.length + rel ? 'is-warn' : '', pend.length + rel ? 'is-warn' : 'is-off', '결재 대기', pend.length + rel) + hd(openP.length ? 'is-bad' : '', openP.length ? 'is-bad' : 'is-off', '문제', openP.length)
      + hd('', doneN ? 'is-ok' : 'is-off', '완료', doneN, '/' + TASKS.length) + hd('', '', '비용', usd(sp), ' / ' + usd(S.cap)) + hd('', '', '완료 예상', S.finished ? hm(S.finishedAt) : S.cancelled ? '–' : hm(fc.total)));
    set($('[data-k="gate-v"]'), `${pend.length + rel}<small>건</small>`);
    set($('[data-k="gate-s"]'), longest ? `최장 ${dur$(S.t - S.gates[longest.id].since)} · ${longest.code} ${esc(longest.title)}` : rel ? `G9 출시 승인 · ${dur$(S.t - S.finishedAt)}째` : S.released ? '출시본 rl1 고정' : '결재할 일이 없어요');
    $('.kpi[data-kpi="gate"]').classList.toggle('is-alert', pend.length + rel > 0);
    set($('[data-k="eta-v"]'), S.finished ? `${hm(S.t)}<small>완료</small>` : S.cancelled ? '–' : hm(fc.total));
    const causes = [];
    GATES.forEach((g) => { const s = S.gates[g.id]; const w = s.st === 'approved' ? s.at - s.since : s.st === 'pending' ? S.t - s.since : 0; if (w >= 1 && fc.crit.has(g.id)) causes.push([w, `${g.code} 대기 ${dur$(w)}`]); });
    TASKS.forEach((t) => { if (S.tasks[t.id].extra && fc.crit.has(t.id)) causes.push([S.tasks[t.id].extra, `${t.short} 재시도 ${dur$(S.tasks[t.id].extra)}`]); });
    causes.sort((a, b) => b[0] - a[0]);
    const etaS = $('[data-k="eta-s"]');
    set(etaS, S.cancelled ? '실행 취소됨' : delay >= 1 ? `계획 ${hm(PLAN.total)} · +${dur$(delay)}${causes.length ? ' · ' + esc(causes.slice(0, 2).map((c) => c[1]).join(', ')) : ''}` : `계획 ${hm(PLAN.total)} · 일정대로`);
    etaS.classList.toggle('is-warn', delay >= 1);
    etaS.title = causes.length ? '지연 원인 · ' + causes.map((c) => c[1]).join(', ') : '';
    set($('[data-k="prob-v"]'), `${openP.length}<small>건</small>`);
    set($('[data-k="prob-s"]'), humanN ? `사람 필요 ${humanN} · 자동 재시도 ${openP.length - humanN}` : openP.length ? `자동 재시도 중 ${openP.length}` : S.probs.length ? `해결 ${S.probs.length}건 · 진행 중인 문제 없음` : '문제 없음');
    $('.kpi[data-kpi="prob"]').classList.toggle('is-bad', openP.length > 0);
    const over = proj > S.cap + 1e-9;
    set($('[data-k="cost-v"]'), `${usd(sp)}<small>/ ${usd(S.cap)}</small>`);
    const cs = $('[data-k="cost-s"]');
    set(cs, over ? `예상 ${usd(proj)} · 상한 초과` : `예상 총액 ${usd(proj)} · 상한의 ${Math.round((proj / S.cap) * 100)}%`);
    cs.classList.toggle('is-bad', over);
    $('.kpi[data-kpi="cost"]').classList.toggle('is-bad', over);
    $('[data-k="cost-m"]').style.setProperty('--w', `${Math.min(100, (sp / S.cap) * 100)}%`);
    $('[data-k="cost-proj"]').style.setProperty('--w', `${Math.min(100, (proj / S.cap) * 100)}%`);
    set($('[data-k="prog-v"]'), `${doneN}<small>/ ${TASKS.length} 작업</small>`);
    set($('[data-k="prog-s"]'), S.running ? `동시 작업 ${runN}개 · 경과 ${dur$(S.t)}` : '시작 전');

    const ban = $('[data-banner]');
    let bh = '';
    if (!S.running) bh = `<span>아직 시작 전이에요. 계획대로면 <b>${hm(PLAN.total)}</b>에 끝나고, 예상 비용은 <b>${usd(proj)}</b>예요.</span><button type="button" class="btn btn--primary" data-start>${icon('play')}기획안 주입하고 시작</button>`;
    else if (S.cancelled) bh = `<span><b>실행을 취소했어요.</b> 이미 쓴 비용 ${usd(sp)}은 원장에 남아요.</span><button type="button" class="btn" data-reset>처음부터 다시</button>`;
    else if (S.released) bh = `<span><b>출시됨</b> · 윤서하 · 출시본 rl1 · ${hm(S.releasedAt)} 승인</span><a class="btn" href="#char/seoha">캐릭터 페이지</a>`;
    else if (S.finished) bh = `<span><b>모든 작업 완료 · G9 출시 승인을 기다려요</b> · 총 ${dur$(S.t)} · ${usd(sp)}. 학습 모델은 블라인드 비교 40쌍을 확인한 뒤 승인하세요.</span><button type="button" class="btn btn--primary" data-release>${icon('check')}출시 승인 · G9</button>`;
    else if (heldN) bh = `<span class="is-bad">예산 상한 <b>${usd(S.cap)}</b>에 닿아 작업 ${heldN}개를 시작하지 않았어요. 남은 작업까지 예상 총액은 <b>${usd(proj)}</b>예요.</span><button type="button" class="btn btn--primary" data-raise>상한을 ${usd(Math.ceil((proj + 2) / 5) * 5)}로 올리기</button>`;
    else if (S.paused) bh = `<span><b>일시정지 중이에요.</b> 진행 중이던 작업이 멈췄고, 새 작업도 시작하지 않아요. 기다리는 동안 완료 예상이 뒤로 밀려요.</span><button type="button" class="btn btn--primary" data-pause>${icon('play')}재개</button>`;
    set(ban, bh); ban.hidden = !bh; ban.dataset.kind = !bh ? '' : S.paused && S.running && !S.cancelled && !S.released && !S.finished && !heldN ? 'paused' : 'other';

    TEAMS.forEach((tm) => {
      const row = $(`.row.body[data-team="${tm.id}"]`), v = teamView(tm.id, fc);
      if (row._s !== v.s) { Object.keys(ST.table.task).forEach((k) => row.classList.toggle('s-' + k, k === v.s)); row._s = v.s; }
      const pill = row.querySelector('[data-pill]'); pill.className = ST.cls('task', v.s); set(pill.lastElementChild, esc(ST.label('task', v.s)));
      set(row.querySelector('[data-now]'), esc(v.main));
      const sub = row.querySelector('[data-sub]'); set(sub, esc(v.sub)); sub.className = `now-sub ${v.subCls}`;
      row.querySelector('[data-bar]').style.setProperty('--w', `${v.pct}%`);
      set(row.querySelector('[data-pct]'), `${v.pct}%`);
      set(row.querySelector('[data-left]'), v.left);
      const det = $(`[data-detail="${tm.id}"]`);
      if (det.classList.contains('is-open')) renderDetail(tm.id, fc);
    });
    renderTimeline(fc);
  }

  function renderTimeline(fc) {
    const target = Math.max(fc.total, PLAN.total, S.t) * 1.04;
    S.axisT = S.axisT ? S.axisT + (target - S.axisT) * 0.25 : target;
    const T = S.axisT, X = (v) => `${(v / T) * 100}%`, W = (a, b) => `${(Math.max(0, b - a) / T) * 100}%`;
    TASKS.forEach((t) => {
      const s = S.tasks[t.id], pl = $(`[data-plan="${t.id}"]`), ac = $(`[data-act="${t.id}"]`), crit = fc.crit.has(t.id);
      pl.classList.toggle('is-crit', crit); ac.classList.toggle('is-crit', crit);
      ac.classList.toggle('is-blocked', s.st === 'blocked');
      if (s.st === 'done') { pl.style.display = 'none'; ac.style.display = ''; ac.style.left = X(s.start); ac.style.width = W(s.start, s.end); ac.classList.remove('is-run'); }
      else if (s.st === 'running' || s.st === 'blocked') { pl.style.display = ''; pl.style.left = X(s.start); pl.style.width = W(s.start, fc.end[t.id]); ac.style.display = ''; ac.style.left = X(s.start); ac.style.width = W(s.start, s.st === 'blocked' ? s.start + s.p * dur(t.id) : S.t); ac.classList.toggle('is-run', s.st === 'running' && !S.paused); }
      else { ac.style.display = 'none'; pl.style.display = ''; pl.style.left = X(fc.start[t.id]); pl.style.width = W(fc.start[t.id], fc.end[t.id]); }
      const rt = $(`[data-retry="${t.id}"]`);
      if (rt) { const show = s.failed && s.extra > 0 && s.st !== 'queued'; rt.style.display = show ? '' : 'none'; if (show) { const e = s.st === 'done' ? s.end : fc.end[t.id]; rt.style.left = X(e - s.extra); rt.style.width = W(e - s.extra, e); } }
    });
    GATES.forEach((g) => {
      const s = S.gates[g.id], el = $(`[data-gw="${g.id}"]`);
      const end = s.st === 'pending' ? S.t : s.st === 'approved' ? s.at : 0;
      const show = s.st !== 'idle' && end - s.since > 0.3;
      el.style.display = show ? '' : 'none';
      if (show) { el.style.left = X(s.since); el.style.width = W(s.since, end); }
    });
    const laneW = ($('.lane') || { getBoundingClientRect: () => ({ width: 300 }) }).getBoundingClientRect().width;
    TASKS.forEach((t) => [$(`[data-plan="${t.id}"]`), $(`[data-act="${t.id}"]`)].forEach((el) => { const w = (parseFloat(el.style.width) || 0) / 100 * laneW; el.classList.toggle('is-tight', w < t.short.length * 8.5 + 8); }));
    $$('[data-nowline]').forEach((l) => { l.style.display = S.running ? '' : 'none'; l.style.left = X(S.t); });
    const stepM = [15, 30, 60].find((m) => T / m <= 6) || 60;
    const tk = $('[data-ticks]');
    const gap = (46 / Math.max(200, tk.getBoundingClientRect().width)) * T;
    let h = '';
    for (let m = stepM; m < T - stepM * 0.4; m += stepM) { if (S.running && !S.finished && Math.abs(m - S.t) < gap) continue; h += `<span style="left:${(m / T) * 100}%">${hm(m)}</span>`; }
    if (S.running && !S.finished) h += `<span class="t-now" style="left:${(S.t / T) * 100}%">${hm(S.t)}</span>`;
    set(tk, h);
  }

  function renderDetail(tid, fc) {
    const rows = teamTasks(tid).map((t) => {
      const s = S.tasks[t.id];
      const state = { done: '완료', running: S.paused ? '일시정지' : `진행 ${Math.round(s.p * 100)}%`, blocked: '사람 필요', queued: s.held ? '예산 대기' : '대기' }[s.st];
      const time = s.st === 'queued' ? `${hm(fc.start[t.id])} 예정` : `${hm(s.start)} – ${s.st === 'done' ? hm(s.end) : `${hm(fc.end[t.id])} 예정`}`;
      const out = s.st === 'done' && t.thumbs ? `<span class="thumbs">${t.thumbs.map((x) => `<img class="${t.sq ? 'sq' : ''}" src="${A(x)}" alt="">`).join('')}</span>` : esc(s.st === 'done' ? t.out : '–');
      return `<tr data-task="${t.id}" tabindex="0"><td>${esc(t.short)}<small>${t.stage}</small></td><td>${esc(t.agent)}</td><td>${state}${s.attempts.length > 1 ? ` · 시도 ${s.attempts.length}` : ''}</td><td class="num">${time}</td><td class="num">${usd((t.cost + xcost(t.id)) * s.p)}</td><td>${out}</td><td class="go">${icon('chevron')}</td></tr>`;
    }).join('');
    set($(`[data-detail="${tid}"]`), `<table class="dt"><thead><tr><th>작업</th><th>담당</th><th>상태</th><th>시간</th><th>비용</th><th>결과</th><th></th></tr></thead><tbody>${rows}</tbody></table><p class="dt-hint">작업을 누르면 호출 기록과 다시 실행 메뉴가 열려요</p>`);
  }

  // 직전 G4 수정 요청 가운데 이미 반영된 것(전후 비교 대상)
  const lastDone = (gid) => { const id = subj(gid); return [...S.reviews].reverse().find((v) => v.gate === gid && v.decision === 'REQUEST_CHANGES' && v.revN < S.tasks[id].rev && S.tasks[id].st === 'done'); };
  const lastReq4 = () => lastDone('G4');
  // 수정 요청을 보낸 뒤 반영되는 동안 결재함에 남는 카드
  function revisingCards() {
    return GATES.filter((g) => S.gates[g.id].st === 'idle' && lastRequest(g.id) && S.tasks[subj(g.id)].st !== 'done').map((g) => ({ revising: g.id }));
  }
  function revisingCard(gid, v) {
    const g = gate(gid), r = lastRequest(gid), id = subj(gid), T = task(id);
    const what = r.items.length ? r.items.filter((i) => !i.ok).map((i) => `${i.ch}장 “${esc(i.note)}”`).join(' · ') : `“${esc(r.note)}”`;
    return `<div><div class="gate-card is-revising"><div class="gate-top"><span class="gt-who">${v !== 'job' ? `<span class="gt-av">${avatarHTML(SEOHA)}</span>${esc(nameOf(SEOHA))} · ` : ''}${team(g.team).name} · ${g.code}</span><span class="wait num" data-wait></span></div>
      <h3>수정 반영 중 · ${esc(g.title)}</h3><div class="gate-rec">요청 · ${what}</div>
      <div class="rv-prog"><span class="meter"><i data-rvbar></i></span><span class="num" data-rvtxt></span></div>
      <div class="gate-auth">${esc(T.short)} ${esc(revOf(id))} 다시 만드는 중 · 끝나면 다시 결재를 요청해요 · ${spotBtn(id)}</div></div></div>`;
  }
  const spotBtn = (id) => `<button type="button" class="link-btn" data-spot="${id}">${icon('aperture')}현장에서 보기</button>`;
  function gateCard(g, i, first, v) {
    if (g.release) {
      return `<div><div class="gate-card"><div class="gate-top"><span class="gt-who">${v !== 'job' ? `<span class="gt-av">${avatarHTML(SEOHA)}</span>${esc(nameOf(SEOHA))} · ` : ''}출시 · G9</span><span class="wait num" data-wait></span></div>
        <h3>출시 승인</h3><div class="gate-impact">자산 ${FAM.length - 1}종을 출시본 <b>rl1</b>로 묶어요 · 승인하면 release_rev가 고정돼요</div>
        <div class="gate-rec">확인할 것 · <b>학습 모델 블라인드 비교 40쌍</b></div><div class="gate-auth">결재 권한 · ${ME} · ${spotBtn('G9')}</div>
        <div class="gate-row"><span style="margin-right:auto"></span><a class="btn" href="#char/seoha">자산 보기</a><button type="button" class="btn btn--primary" data-release>${icon('check')}승인</button></div></div></div>`;
    }
    if (g.other) {
      const r = g.other;
      return `<div><div class="gate-card"><div class="gate-top"><span class="gt-who"><span class="gt-av">${avatarHTML(r.key)}</span>${esc(r.name)} · ${r.gate.code}</span><span class="wait">${esc(r.gate.wait)}</span></div>
        <h3>${esc(r.gate.title)}</h3><div class="gate-impact">${esc(r.gate.impact)}</div><div class="gate-rec">검토 대상 · <b>${esc(r.gate.rec)}</b></div><div class="gate-auth">결재 권한 · ${ME}</div>
        <div class="gate-row"><span style="margin-right:auto"></span><button type="button" class="btn btn--primary" data-other-review="${esc(r.key)}">검토하기</button></div></div></div>`;
    }

    const kind = g.kind === 'pick';
    const href = `c-glass.html?gate=${g.code}&run=${RUN_ID}&back=d-ops.html`;
    return `<div><div class="gate-card"><div class="gate-top"><span class="gt-who">${v !== 'job' ? `<span class="gt-av">${avatarHTML(SEOHA)}</span>${esc(nameOf(SEOHA))} · ` : ''}${team(g.team).name} · ${g.code}</span><span class="wait num" data-wait></span></div>
      <span class="gate-first" data-first></span><h3>${esc(g.title)}</h3><div class="gate-impact" data-impact></div>
      ${DOC[g.id] && lastDone(g.id) ? `<div class="gate-rec is-back">다시 올라옴 · <b>${esc(lastDone(g.id).rev)} → ${esc(revOf(subj(g.id)))}</b> · 문단 ${changed(g.id)}개 수정 반영</div>` : g.id === 'G4' && lastReq4() ? `<div class="gate-rec is-back">다시 올라옴 · <b>${esc(lastReq4().rev)} → ${esc(revOf('v4'))}</b> · ${lastReq4().items.filter((i) => !i.ok).map((i) => i.ch + '장').join('·')} 수정 반영<span class="cmp-mini">${lastReq4().items.filter((i) => !i.ok).map((i) => `<img src="${A(frameSrc(i.ch, lastReq4().revN))}" alt=""><i>${icon('arrow')}</i><img src="${A(frameSrc(i.ch, lastReq4().revN + 1))}" alt="">`).join('')}</span></div>` : `<div class="gate-rec">${kind ? '판정 모델 추천' : '추천'} · <b>${esc(g.rec)}</b></div>`}<div class="gate-auth">결재 권한 · ${ME} · ${spotBtn(g.id)}</div>
      <div class="gate-row">${g.thumbs ? `<span class="thumbs">${(g.id === 'G4' ? frames() : g.thumbs).map((t) => `<img class="${g.sq ? 'sq' : ''}" src="${A(t)}" alt="">`).join('')}</span>` : '<span style="margin-right:auto"></span>'}${kind ? `<a class="btn btn--primary" href="${href}" data-go-workroom="${g.id}">작업실에서 고르기${icon('arrow')}</a>` : `<button type="button" class="btn" data-review="${g.id}">검토</button><button type="button" class="btn btn--primary" data-approve="${g.id}">승인</button>`}</div></div></div>`;
  }

  function renderInbox(list, v) {
    const box = $('[data-gates]');
    const items = list.map((g) => (g.other ? { g, key: 'o:' + g.other.key, score: 99999 } : g.release ? { g, key: 'G9', score: -1 } : g.revising ? { g, key: 'rev:' + g.revising, score: -2 } : { g, key: g.id, im: impact(g.id), score: impact(g.id).minutes }));
    items.sort((a, b) => (a.g.other ? 1 : 0) - (b.g.other ? 1 : 0) || (b.g.release ? 1 : 0) - (a.g.release ? 1 : 0) || b.score - a.score);
    set($('[data-gate-count]'), list.length ? `${list.length}건 · ${v === 'chars' ? '모든 캐릭터' : '풀리는 작업 많은 순'}` : '');
    $('[data-gate-empty]').hidden = list.length > 0 || $$('.gate', box).length > 0;
    const keys = new Set(items.map((x) => x.key));
    $$('.gate', box).forEach((el) => { if (!keys.has(el.dataset.key) && !el.classList.contains('is-approved')) el.remove(); });
    items.forEach((it, i) => {
      let el = box.querySelector(`.gate[data-key="${CSS.escape(it.key)}"]`);
      if (!el || el.dataset.v !== v) {
        if (el) el.remove();
        el = document.createElement('div'); el.className = 'gate is-new'; el.dataset.key = it.key; el.dataset.v = v; if (!it.g.other && !it.g.revising) el.dataset.gate = it.g.release ? 'G9' : it.g.id;
        el.innerHTML = it.g.revising ? revisingCard(it.g.revising, v) : gateCard(it.g, i, false, v);
      }
      if (box.children[i] !== el) box.insertBefore(el, box.children[i] || null);
      if (it.g.revising) { const g = gate(it.g.revising), id = subj(g.id), ts = S.tasks[id], r = lastRequest(g.id); const pct = Math.round(ts.p * 100); el.querySelector('[data-rvbar]').style.setProperty('--w', pct + '%'); set(el.querySelector('[data-rvtxt]'), ts.st === 'queued' ? '대기' : pct + '%'); set(el.querySelector('[data-wait]'), `요청 ${dur$(S.t - r.at)} 전`); }
      else if (it.g.release) { const w = el.querySelector('[data-wait]'); set(w, `${stall('G9') ? '정체 · ' : ''}${dur$(S.t - S.finishedAt)}째`); w.classList.toggle('is-stall', stall('G9')); }
      else if (!it.g.other) {
        const w = el.querySelector('[data-wait]');
        set(w, `${stall(it.g.id) ? '정체 · ' : ''}${dur$(S.t - S.gates[it.g.id].since)}째`); w.classList.toggle('is-stall', stall(it.g.id));
        set(el.querySelector('[data-impact]'), it.im.minutes ? `풀리는 작업 <b>${it.im.teams}팀 · 약 ${dur$(it.im.minutes)}</b> · ${esc(it.im.names.join(', '))}` : '풀리는 작업 없음');
        set(el.querySelector('[data-first]'), i === 0 && items.filter((x) => !x.g.other).length > 1 ? '먼저 처리하면 가장 많이 풀려요' : '');
      }
    });
  }

  function renderProbs(v) {
    const ul = $('[data-probs]');
    const open = S.probs.filter((p) => p.st === 'open').length;
    set($('[data-prob-count]'), S.probs.length ? `진행 중 ${open} · 해결 ${S.probs.length - open}` : '');
    const list = v === 'none' ? [] : S.probs;
    $('[data-prob-empty]').hidden = list.length > 0;
    if (v === 'none') set($('[data-prob-count]'), '');
    set(ul, list.map((p) => {
      const human = p.kind === 'human' && p.st === 'open';
      const sub = p.st === 'open' ? p.sub : `${p.how || '자동으로 해결됨'} · ${hm(p.done)}`;
      return `<li class="prob ${p.st === 'resolved' ? 'is-resolved' : ''} ${human ? 'is-human' : ''}"><span class="dot"></span><span class="prob-text">${human ? `<span class="tag-human">${ST.label('task', 'human')}</span>` : ''}${esc(p.text)}<span class="prob-sub">${v !== 'job' ? `${esc(nameOf(SEOHA))} · ` : ''}${team(p.team).name} · ${esc(sub)}</span>${p.st === 'open' ? spotBtn(p.id) : ''}${human ? `<span class="prob-act"><button type="button" class="btn btn--primary btn--sm" data-rerun="${p.id}">${icon('refresh')}다시 실행</button><button type="button" class="btn btn--sm" data-open-task="${p.id}" data-mode="settings">${icon('sliders')}설정 바꿔서</button><button type="button" class="btn btn--sm" data-skip="${p.id}">${icon('skip')}건너뛰기</button></span>` : `<button type="button" class="prob-link" data-open-task="${p.id}">호출 기록 보기</button>`}</span><span class="prob-time num">${hm(p.at)}</span></li>`;
    }).join(''));
  }

  // 지나간 일: 알림과 같은 사건(결재·재시도·사람 필요·라인 완료…)을 시간순으로. 패널이 열려 있으면 본 것으로 친다
  function renderEvents() {
    const notes = S.notes.slice(0, 12);
    set($('[data-evs]'), notes.map((n) => `<li class="ev k-${n.kind}${n.seq > (S.evSeen || 0) ? ' is-new' : ''}"${n.ref ? ` data-spot="${n.ref}" role="button" tabindex="0" title="공장 현장에서 보기"` : ''}><span class="dot"></span><span class="ev-t">${n.html}</span><span class="num">${hm(n.t)}</span></li>`).join(''));
    $('[data-ev-empty]').hidden = notes.length > 0;
    set($('[data-ev-count]'), S.notes.length ? `${S.notes.length}건` : '');
    const open = panelOpen(), unseen = (S.noteSeq || 0) > (S.evSeen || 0);
    if (open && unseen && document.body.dataset.sub === 'floor') setTimeout(() => { S.evSeen = S.noteSeq; }, 2500);
    const pend = GATES.filter((g) => S.gates[g.id].st === 'pending').length + (relPending() ? 1 : 0), prob = S.probs.filter((p) => p.st === 'open').length;
    set($('[data-pb-n]'), (pend ? `<b class="is-warn">${pend}</b>` : '') + (prob ? `<b class="is-bad">${prob}</b>` : ''));
    const dot = $('[data-pb-dot]'); if (dot) dot.hidden = open || !unseen;
  }
  const panelOpen = () => document.body.classList.contains('is-panel');
  function setPanel(on) {
    document.body.classList.toggle('is-panel', on);
    try { localStorage.setItem('cf-floor-panel', on ? '1' : '0'); } catch (e) { /* 저장 못 해도 동작 */ }
    $$('.fl-panel-btn').forEach((b) => { b.setAttribute('aria-pressed', String(on)); b.title = (on ? '기록 닫기' : '지나간 일·결재함 열기') + ' (L)'; });
    if (on) S.evSeen = S.evSeen || 0;
    window.CF_FLOOR.resize(); render();
  }
  function renderLog() {
    const f = S.logFilter;
    $$('[data-log-filter]').forEach((b) => b.classList.toggle('is-on', b.dataset.logFilter === f));
    const list = S.log.filter((l) => f === 'all' || l.actor === f);
    set($('[data-log-count]'), `${S.log.length}건`);
    if (!$('[data-log]').open) return;
    const who = { human: '사람', agent: '에이전트', system: '시스템' };
    set($('[data-log-list]'), list.slice(0, 50).map((l) => `<li><span>${hm(l.t)}</span><span class="who who-${l.actor}">${who[l.actor]}</span><span>${l.html}</span></li>`).join('') || '<li><span></span><span></span><span>기록이 없어요</span></li>');
  }


  // ---------- 오른쪽 상세 패널
  function openDrawer(o) { S.open = o; const d = $('[data-drawer]'); d.hidden = false; $('[data-scrim]').hidden = false; requestAnimationFrame(() => { d.classList.add('is-open'); $('[data-scrim]').classList.add('is-open'); }); d._h = null; renderDrawer(forecast()); d.querySelector('[data-close]').focus({ preventScroll: true }); }
  function closeDrawer() { S.open = null; const d = $('[data-drawer]'); d.classList.remove('is-open'); $('[data-scrim]').classList.remove('is-open'); setTimeout(() => { if (!S.open) { d.hidden = true; $('[data-scrim]').hidden = true; } }, 220); }

  function renderDrawer(fc) {
    const o = S.open, d = $('[data-drawer]');
    let html = '';
    if (o.task) html = taskDrawer(o, fc);
    else if (o.gate) html = gateDrawer(o.gate);
    else if (o.other) html = otherDrawer(o.other);
    const body = d.querySelector('[data-drawer-body]');
    const keep = body.querySelector('textarea');
    const val = keep ? keep.value : null;
    const ae = document.activeElement;
    const an = ae && body.contains(ae) && ae.tagName === 'TEXTAREA' ? [...ae.attributes].map((a) => a.name).find((n) => n.startsWith('data-')) : null;
    const key = an ? an + '="' + (ae.getAttribute(an) || '') + '"' : null;
    const sel = key ? [ae.selectionStart, ae.selectionEnd] : null;
    set(body, html);
    if (key) { const n = body.querySelector('textarea[' + key + ']'); if (n && n !== ae) { n.focus(); try { n.setSelectionRange(sel[0], sel[1]); } catch (e) {} } }
    if (val != null && !key && body.querySelector('textarea[data-opt-note]') && body.querySelector('textarea[data-opt-note]').value !== val) body.querySelector('textarea[data-opt-note]').value = val;
  }

  function taskDrawer(o, fc) {
    const T = task(o.task), s = S.tasks[T.id];
    const stKey = { done: 'done', running: S.paused ? 'paused' : 'working', blocked: 'human', queued: s.held ? 'budget' : 'idle' }[s.st];
    const stText = stKey === 'working' ? `진행 ${Math.round(s.p * 100)}%` : null;
    const isDeck = Object.hasOwn(TEXT_ROLE_IDS, T.id);
    const isText = (isDeck && T.calls > 0) || T.model === M_TEXT || T.agent === 'Judge';
    const prov = isDeck ? (T.calls ? 'openai_compat · opencodex' : '결정적 조립') : T.agent === 'Judge' ? 'codex_exec' : (PROV[T.model] || 'openai_compat');
    const totalCost = (T.cost + xcost(T.id)) * s.p;
    const tokIn = isText ? Math.round(T.cost * 52000 + 18000) : 0, tokOut = tokIn ? Math.round(tokIn * 0.06) : 0;
    const attempts = s.attempts.length ? s.attempts.map((a) => `<tr><td class="num">#${a.n}</td><td>${ST.pill('attempt', a.st)}</td><td class="num">${hm(a.start)}${a.end != null ? ` – ${hm(a.end)}` : ''}</td><td>${a.rev ? `<code class="att-rev">${esc(a.rev)}</code>` : ''}<span class="att-trig">${esc(TRIG[a.trigger] || a.note || '–')}</span>${a.memo ? `<q>${esc(a.memo)}</q>` : ''}${a.check ? `<small>${esc(a.check)}</small>` : ''}</td></tr>`).join('') : '<tr><td colspan="4">아직 시작하지 않았어요</td></tr>';
    // 실패한 시도의 호출도 원장에 남는다: 실패 시도마다 마지막 호출 1건이 fail.
    const failN = s.attempts.filter((a) => a.st === 'fail').length;
    const callN = T.calls === 0 ? 0 : failN * T.calls + Math.max(1, Math.round(T.calls * (s.st === 'done' ? 1 : s.p)));
    const shown = Math.min(3, callN);
    const ids = ['96f6e1e3', 'ca26cf98', '007c7adb', '3b1f0e72', 'e81a44c0'];
    const calls = s.attempts.length ? Array.from({ length: shown }, (_, i) => {
      const k = callN - shown + i;
      const ok = !(k < failN * T.calls && (k + 1) % T.calls === 0);
      return `<li><code>${ids[(T.id.charCodeAt(1) + i) % ids.length]}</code><span>${esc(T.model)}</span><span class="num">${tokIn ? `${k$(Math.round(tokIn / Math.max(1, T.calls)))} / ${k$(Math.round(tokOut / Math.max(1, T.calls)))}` : T.model === M_VIDEO ? '영상 1편' : T.model === M_IMAGE ? '이미지 1장' : 'GPU'}</span><span class="${ok ? 'ok' : 'bad'}">${ok ? 'ok' : 'fail'}</span></li>`;
    }).join('') : '';
    const deckRows = isDeck ? TEXT_ROLE_IDS[T.id].map((id) => {
      const d = TEXT_DECK?.tasks[id];
      return `<li>${esc(d?.label || id)} · <code>${esc(d?.model || '설정 미연결')}</code> · ${esc(d?.reasoningEffort || '')}</li>`;
    }).join('') : '';
    const deckInfo = isDeck ? `<section class="dr-section"><p class="dr-note">시연 각본 · 모델 배정은 기본 테스트 기준입니다. 실제 설정·호출 출처는 상단 텍스트 공정에서 확인해요.</p>${deckRows ? `<ul>${deckRows}</ul>` : '<p>확정된 문장을 보존해 조립하며 모델을 호출하지 않아요.</p>'}</section>` : '';
    const imp = (s.st === 'done') ? rerunImpact(T.id) : null;
    const canRerun = s.st === 'done' || s.st === 'blocked';
    const actions = s.st === 'running' ? `<p class="dr-note">실행 중인 작업은 위의 <b>일시정지</b>로 멈출 수 있어요. 끝나거나 막힌 뒤에 다시 실행할 수 있어요.</p>`
      : s.st === 'queued' ? `<p class="dr-note">${s.held ? `예산 상한 때문에 시작하지 않았어요. 상한을 올리면 바로 시작해요.` : '앞 작업이나 결재가 끝나면 자동으로 시작해요.'}</p>`
      : `${imp && (imp.tasks.length || imp.gates.length) ? `<p class="dr-warn">다시 실행하면 뒤 작업 <b>${imp.tasks.length}개</b>${imp.gates.length ? `와 결재 <b>${imp.gates.length}건</b>` : ''}도 처음부터 다시 진행돼요${imp.teams.length ? ` · ${esc(imp.teams.join(', '))}` : ''}. 예상 추가 비용 <b>${usd(imp.cost)}</b> · 약 <b>${dur$(imp.minutes)}</b> 이상.</p>` : imp ? `<p class="dr-note">뒤에 이어진 작업이 아직 시작하지 않아 이 작업만 다시 돌아요 · 예상 ${usd(T.cost)}</p>` : ''}
        <div class="dr-actions"><button type="button" class="btn btn--primary" data-rerun="${T.id}">${icon('refresh')}다시 실행</button><button type="button" class="btn${o.mode === 'settings' ? ' is-on' : ''}" data-settings="${T.id}">${icon('sliders')}설정 바꿔서 다시 실행</button>${s.st === 'blocked' ? `<button type="button" class="btn" data-skip="${T.id}">${icon('skip')}건너뛰기</button>` : ''}</div>
        ${o.mode === 'settings' ? `<div class="dr-form"><div class="dr-field"><span>모델</span><div class="chips">${[T.model, T.model === M_TEXT ? M_JUDGE : M_TEXT].filter((x, i, a) => a.indexOf(x) === i).map((m, i) => `<button type="button" class="chip${(o.model || T.model) === m ? ' is-on' : ''}" data-opt-model="${esc(m)}">${esc(m)}${i === 0 ? ' · 기본' : ''}</button>`).join('')}</div></div>
          <div class="dr-field"><span>검사 기준</span><div class="chips">${['기본', '엄격하게', '느슨하게'].map((x) => `<button type="button" class="chip${(o.strict || '기본') === x ? ' is-on' : ''}" data-opt-strict="${x}">${x}</button>`).join('')}</div></div>
          <div class="dr-field"><span>메모 (선택)</span><textarea rows="2" placeholder="에이전트에게 전할 지시를 적어 주세요. 예) 같은 대화를 다른 말로 바꾸지 말고 새 상황을 만들 것" data-opt-note></textarea></div>
          <button type="button" class="btn btn--primary" data-rerun-settings="${T.id}">이 설정으로 다시 실행</button></div>` : ''}`;
    return `${deckInfo}<div class="dr-head"><span class="dr-kicker">${team(T.team).name} · ${T.stage} · ${esc(T.agent)}</span><h2>${esc(T.short)}</h2>${ST.pill('task', stKey, stText)}${view() === 'job' ? `<button type="button" class="btn btn--sm dr-follow" data-follow="${T.id}">${icon('aperture')}현장에서 따라가기</button>` : ''}</div>
      <dl class="dr-meta"><dt>모델</dt><dd>${esc(T.model)}<small>${prov}</small></dd><dt>프롬프트</dt><dd>${T.stage.toLowerCase()}-${esc(T.agent.toLowerCase().replace(/\s+/g, '-'))}@v3</dd><dt>입력</dt><dd>${T.inputs.map((x) => `<span class="ref">${esc(liveRef(x))}</span>`).join('')}</dd><dt>산출물</dt><dd><span class="ref">${esc(revOf(T.id))}</span>${s.partial ? `<small class="part">${esc(s.partial.from)}에서 ${s.partial.chs.join('·')}장만 다시${s.partial.keep.length ? ` · ${s.partial.keep.join('·')}장은 그대로 가져옴` : ''}</small>` : ''} ${s.st === 'done' && thumbsOf(T) ? `<span class="thumbs">${thumbsOf(T).map((x) => `<img class="${T.sq ? 'sq' : ''}" src="${A(x)}" alt="">`).join('')}</span>` : esc(s.st === 'done' ? T.out : '')}</dd>
      ${(() => { const fs = window.CF_FLOOR && window.CF_FLOOR.step(T.id); return fs ? `<dt>지금</dt><dd>${esc(fs.line)}${fs.tiles.length ? `<span class="thumbs is-partial">${fs.tiles.map((x, i) => `<img class="${fs.on[i] ? 'on' : ''}" src="${A(x)}" alt="">`).join('')}</span><small>결과 ${fs.n}/${fs.tiles.length}</small>` : ''}</dd>` : ''; })()}<dt>호출</dt><dd class="num">${s.attempts.length ? `${callN}회` : '–'}${tokIn && s.attempts.length ? ` · 토큰 ${k$(Math.round(tokIn * s.p))} / ${k$(Math.round(tokOut * s.p))}` : ''}</dd><dt>비용</dt><dd class="num">${usd(totalCost)}${s.extra > 0 ? ` · 재시도분 ${usd(xcost(T.id) * s.p)} 포함` : s.partial ? ` · ${s.partial.chs.length}장분만` : ''}</dd></dl>
      ${actions}
      ${GATES.filter((g) => g.after.includes(T.id)).map((g) => reviewList(g.id)).join('')}<h3>시도 기록 <small>시도 상한 3회 · 자동 재시도 2회 · 사람이 다시 실행하면 revision이 올라가요</small></h3><table class="dr-table"><tbody>${attempts}</tbody></table>
      ${calls ? `<h3>호출 기록 <small>원장 calls.jsonl · 최근 ${Math.min(3, callN)}건</small></h3><ul class="calls"><li class="calls-head"><span>callId</span><span>모델</span><span>입력 / 출력</span><span>결과</span></li>${calls}</ul>` : ''}`;
  }

  const CH = ['친해지기', '썸타기', '고백하기'];
  const DOC = {
    G6: { sec: [
      { h: '핵심 특질', items: [{ t: '기다려야 하는 시간이 생기면 불평 대신 카메라를 꺼내 그 시간을 자기 것으로 쓴다' }, { t: '좋아하는 장면 앞에서는 일행이 먼저 가도 한참 서서 셔터를 아낀다' }, { t: '마음이 정해지면 말보다 인화한 사진 한 장을 먼저 건넨다' }] },
      { h: '상황별 변화', items: [{ t: '처음 보는 사람 앞에서는 말수를 줄이고 사진 이야기로만 대화를 잇는다' }, { t: '친해지면 먼저 장소를 정하고, 늦게 온 상대를 탓하지 않는다' }, { add: '상대를 기다려야 할 때는 휴대폰 대신 카메라를 꺼내고, 기다린 시간을 사진 한 장으로 돌려준다' }] },
      { h: '말투 예시', q: true, items: [{ t: '괜찮아. 나 저 앞 골목에 있어. 빛 좋거든.' }, { t: '이거… 그날 한참 서 있었어. 그림자가 계단에 딱 걸려서.' }, { from: '대답은 할게. 조금만 더 보고.', to: '대답은 할게. 이 장면만 담고.' }, { add: '늦어도 돼. 덕분에 저 간판에 불 들어오는 거 찍었어.' }] }
    ], note: (v2) => (v2 ? '짧은 프롬프트 2,265자 · 상한 2,400자' : '짧은 프롬프트 2,180자 · 상한 2,400자'), ph: '예) 상황별 변화에 기다릴 때 장면을 하나 더 넣고, 말투 예시에도 기다리는 장면을 하나' },
    G7: { sec: [
      { h: '표본 미리보기 · 클러스터 2 일상', q: true, items: [{ t: '상대 · 오늘 진짜 정신없었어 / 서하 · 그럼 그냥 같이 걸을래? 한강 쪽으로.' }, { t: '상대 · 사진 진짜 잘 찍는다 / 서하 · 고마워. 그날 계단에 그림자가 딱 걸려서, 한참 서 있었거든.' }] },
      { h: '표본 미리보기 · 클러스터 9 약속 변경', q: true, items: [{ t: '상대 · 미안, 오늘 약속 미뤄도 될까? / 서하 · 응, 괜찮아. 다음에 더 좋은 빛 있을 때 보자.' }, { from: '상대 · 오늘 약속 좀 늦출 수 있어? / 서하 · 응, 괜찮아. 다음에 더 좋은 빛 있을 때 보자.', to: '상대 · 비 와서 오늘 못 나갈 것 같아 / 서하 · 그럼 창가 쪽 사진 하나만 보내 줘. 빗방울 맺힌 거.' }] }
    ], note: (v2) => (v2 ? '클러스터 9 유사 표본 0쌍 · 중복률 9%' : '클러스터 9 유사 표본 1쌍 · 중복률 18%'), ph: '예) 클러스터 9 표본이 같은 대답으로 끝나요. 상황 자체를 바꿔서 다시' }
  };
  const docV2 = (gid) => !!lastDone(gid) || (S.reviews.some((v) => v.gate === gid && v.decision === 'REQUEST_CHANGES') && S.tasks[subj(gid)].rev > 1 && S.tasks[subj(gid)].st === 'done');
  const changed = (gid) => DOC[gid].sec.reduce((a, x) => a + x.items.filter((i) => !i.t).length, 0);
  // 지금 판의 내용
  function docBody(gid) {
    const v2 = docV2(gid), d = DOC[gid];
    return d.sec.map((x) => {
      const items = x.items.map((i) => (i.t != null ? i.t : i.add != null ? (v2 ? i.add : null) : i.del != null ? (v2 ? null : i.del) : v2 ? i.to : i.from)).filter((t) => t != null);
      return `<h3>${esc(x.h)}</h3><ul class="${x.q ? 'dr-quotes' : 'dr-list'}">${items.map((t) => `<li>${esc(t)}</li>`).join('')}</ul>`;
    }).join('') + `<p class="dr-note">${d.note(v2)}</p>`;
  }
  // 문단 전후 비교: 바뀐 섹션만 펼치고, 그대로인 섹션은 한 줄로 접는다
  function docCmp(gid) {
    const req = lastDone(gid); if (!req) return '';
    const cur = revOf(subj(gid)), d = DOC[gid];
    const rows = d.sec.map((x) => {
      if (x.items.every((i) => i.t != null)) return `<div class="pc-same">${esc(x.h)} · 변경 없음 · ${x.items.length}문단</div>`;
      const L = x.items.map((i) => (i.t != null ? `<li>${esc(i.t)}</li>` : i.add != null ? `<li class="pc-gap"></li>` : `<li class="pc-del">${esc(i.del != null ? i.del : i.from)}</li>`)).join('');
      const R = x.items.map((i) => (i.t != null ? `<li>${esc(i.t)}</li>` : i.del != null ? `<li class="pc-gap"></li>` : `<li class="pc-add"><span class="pc-tag">${i.add != null ? '추가' : '바뀜'}</span>${esc(i.add != null ? i.add : i.to)}</li>`)).join('');
      return `<div class="pc-sec"><b>${esc(x.h)}</b><div class="pc-cols"><ol>${L}</ol><ol>${R}</ol></div></div>`;
    }).join('');
    return `<div class="cmp"><div class="cmp-head"><b>${esc(req.rev)} → ${esc(cur)}</b><span>문단 ${changed(gid)}개 바뀜 · 나머지는 그대로</span></div>
      <div class="pc-cols pc-heads"><span>${esc(req.rev)} · 전</span><span>${esc(cur)} · 후</span></div>${rows}
      <div class="cmp-note"><span class="cmp-k">요청</span><q>${esc(req.note)}</q><span class="cmp-by">${esc(req.by)} · ${hm(req.at)} 요청</span><span class="cmp-done">${icon('check')}반영해서 다시 만들었어요 · ${d.note(true)}</span></div></div>`;
  }
  // 결재·수정 요청 이력: 누가 언제 어떤 revision에 무엇을 남겼는지
  function reviewList(gid) {
    const list = S.reviews.filter((v) => v.gate === gid);
    if (!list.length) return '';
    return `<h3>결재 이력 · ${gid}</h3><ol class="rv-list">${list.slice().reverse().map((v) => `<li class="${v.decision === 'APPROVE' ? 'is-ok' : 'is-req'}"><span class="num">${hm(v.at)}</span><code>${esc(v.rev)}</code><span>${v.decision === 'APPROVE' ? '승인' : '수정 요청'} · ${esc(v.by)}${v.note ? `<q>${esc(v.note)}</q>` : ''}${v.items.filter((i) => !i.ok).map((i) => `<q>${i.ch}장 · ${esc(i.note)}</q>`).join('')}</span></li>`).join('')}</ol>`;
  }
  function g4Body(s) {
    const o = S.open; if (!o.g4) o.g4 = { c: { 1: 'ok', 2: 'ok', 3: 'ok' }, n: {} };
    const st = o.g4, req = lastReq4();
    const cur = revOf('v4'), pend = s.st === 'pending';
    let h = '';
    if (req) {
      const ch = req.items.filter((i) => !i.ok);
      h += `<div class="cmp"><div class="cmp-head"><b>${esc(req.rev)} → ${esc(cur)}</b><span>${ch.map((i) => i.ch).join('·')}장만 다시 만들었어요 · ${req.items.filter((i) => i.ok).map((i) => i.ch).join('·') || '없음'}장은 그대로</span></div>
        ${ch.map((i) => `<div class="cmp-row"><figure><img src="${A(frameSrc(i.ch, req.revN))}" alt=""><figcaption>${esc(req.rev)} · 전</figcaption></figure><span class="cmp-arrow">${icon('arrow')}</span><figure><img src="${A(frameSrc(i.ch, req.revN + 1))}" alt=""><figcaption>${esc(cur)} · 후</figcaption></figure>
          <div class="cmp-note"><span class="cmp-k">${i.ch}장 · ${CH[i.ch - 1]}</span><q>${esc(i.note)}</q><span class="cmp-by">${esc(req.by)} · ${hm(req.at)} 요청</span><span class="cmp-done">${icon('check')}반영해서 다시 만들었어요</span></div></div>`).join('')}</div>`;
    }
    h += `<div class="dr-frames g4-frames">${[1, 2, 3].map((c) => {
      const fix = st.c[c] === 'fix', changed = req && req.items.some((i) => i.ch === c && !i.ok);
      return `<figure class="${fix ? 'is-fix' : ''}"><img src="${A(frameSrc(c, frameRev(c)))}" alt=""><figcaption>${c}장 · ${CH[c - 1]} <span class="g4-rev">${changed ? `새로 ${esc(cur)}` : req ? `${esc(req.rev)} 그대로` : esc(cur)}</span></figcaption>
        ${pend ? `<div class="seg-ctl g4-seg" role="group" aria-label="${c}장 결정"><button type="button" class="${fix ? '' : 'is-on'}" data-g4="${c}:ok">승인</button><button type="button" class="${fix ? 'is-on' : ''}" data-g4="${c}:fix">수정 요청</button></div>
        ${fix ? `<textarea rows="3" data-g4-note="${c}" aria-label="${c}장 수정 메모" placeholder="예) 카메라를 눈높이로 들어 골목 끝을 찍는 순간으로">${esc(st.n[c] || '')}</textarea>` : ''}` : ''}</figure>`;
    }).join('')}</div>`;
    if (pend) {
      const k = [1, 2, 3].filter((c) => st.c[c] === 'fix').length;
      h += `${o.err ? `<p class="dr-err">${esc(o.err)}</p>` : ''}<div class="dr-actions">${k ? `<button type="button" class="btn btn--primary" data-g4-send>${icon('refresh')}수정 요청 보내기 · ${k}장</button><span class="dr-note">요청한 장만 다시 만들고 나머지는 그대로 가져가요</span>` : `<button type="button" class="btn btn--primary" data-approve="G4">${icon('check')}3장 모두 승인</button>`}</div>`;
    }
    return h;
  }
  function gateDrawer(gid) {
    const g = gate(gid), s = S.gates[gid];
    let body = '';
    if (s.st === 'idle') return `<div class="dr-head"><span class="dr-kicker">${team(g.team).name} · 관문 ${g.code} · ${g.stage}</span><h2>${esc(g.title)}</h2>${ST.pill('gate', 'idle')}</div>
      <p class="dr-note">${g.after.map((a) => esc(task(a).short)).join(' · ')} 작업이 끝나면${needsOf(g).length ? ` ${needsOf(g).map((n) => esc(`${n} ${gate(n).title}`)).join(' · ')} 승인 뒤` : ''} 결재를 요청해요. 결재하면 ${esc([...new Set(TASKS.filter((t) => t.deps.includes(gid)).map((t) => team(t.team).name))].join(', ') || '다음 단계')} 작업이 시작돼요.</p>`;
    if (gid === 'G4') body = g4Body(s);
    if (gid === 'G6') body = docCmp('G6') + docBody('G6');
    if (gid === 'G7') body = docCmp('G7') + `<dl class="dr-meta"><dt>표본</dt><dd>40개 (14개 클러스터에서 고르게)</dd><dt>자동 검사</dt><dd>통과 92% · 결함 분류용이에요</dd><dt>제외</dt><dd>${S.probs.some((p) => p.id === 'd2' && p.how && p.how.includes('빼고')) ? '클러스터 9 (건너뜀)' : '없음'}</dd></dl>` + docBody('G7');
    return `<div class="dr-head"><span class="dr-kicker">${team(g.team).name} · 관문 ${g.code} · ${g.stage}</span><h2>${esc(g.title)}</h2>${s.st === 'pending' ? ST.pill('gate', 'pending', `${dur$(S.t - s.since)}째 대기`) : ST.pill('gate', 'approved')}</div>
      ${body}<p class="gate-auth">결재 권한 · ${ME}</p>
      ${s.st === 'pending' && gid !== 'G4' ? `<div class="dr-req"><label for="req-note">수정 요청 메모 <small>요청하면 이 메모와 함께 다시 만들어요</small></label><textarea id="req-note" rows="2" data-req-note="${gid}" placeholder="${esc((DOC[gid] && DOC[gid].ph) || '무엇을 고칠지 한 줄로 적어 주세요')}">${esc((S.open && S.open.req) || '')}</textarea>${S.open && S.open.err ? `<p class="dr-err">${esc(S.open.err)}</p>` : ''}</div><div class="dr-actions"><button type="button" class="btn btn--primary" data-approve="${gid}">${icon('check')}승인</button><button type="button" class="btn" data-request="${gid}">${icon('refresh')}수정 요청</button></div>` : ''}
      ${reviewList(gid)}`;
  }

  function otherDrawer(key) {
    const r = other(key);
    return `<div class="dr-head"><span class="dr-kicker">${esc(r.name)} · 관문 ${r.gate.code} · S8</span><h2>${esc(r.gate.title)}</h2>${ST.pill('gate', 'pending', `${r.gate.since}부터 ${r.gate.wait}`)}</div>
      <dl class="dr-meta"><dt>캐릭터</dt><dd><code>${esc(r.id)}</code></dd><dt>검토 대상</dt><dd>${esc(r.gate.rec)}</dd><dt>원장</dt><dd>${esc(r.cost)} · ${esc(r.calls)}</dd></dl>
      <p class="dr-note">공장에서도 이 캐릭터는 G6 검토 페이지에서 멈춰 있어요. 데모에서 승인하면 이 화면에만 반영돼요.</p>
      ${S.otherDone[key] ? '<p class="gate-done">결재했어요</p>' : `<div class="dr-actions"><button type="button" class="btn btn--primary" data-other-approve="${esc(key)}">${icon('check')}승인</button><a class="btn" href="#char/${esc(key)}">캐릭터 보기</a></div>`}`;
  }


  function toggleRow(tid) {
    const was = $(`.row.body[data-team="${tid}"]`).classList.contains('is-open');
    $$('.row.body').forEach((r) => { r.classList.remove('is-open'); r.querySelector('.c-team').setAttribute('aria-expanded', 'false'); });
    $$('.detail').forEach((d) => d.classList.remove('is-open'));
    if (!was) { const r = $(`.row.body[data-team="${tid}"]`); r.classList.add('is-open'); r.querySelector('.c-team').setAttribute('aria-expanded', 'true'); const d = $(`[data-detail="${tid}"]`); d.classList.add('is-open'); d._h = null; renderDetail(tid, forecast()); }
  }

  const workroomHref = (g) => `c-glass.html?gate=${g.code}&run=${RUN_ID}&back=${encodeURIComponent('d-ops.html' + (location.hash || '#chars'))}`;
  const pendingPicks = () => GATES.filter((g) => S.gates[g.id].st === 'pending' && g.kind === 'pick').sort((a, b) => impact(b.id).minutes - impact(a.id).minutes);
  const pickList = () => pendingPicks().map((g) => ({ code: g.code, title: g.title, who: nameOf(SEOHA) }));

  function reset() { try { localStorage.removeItem(STORE); localStorage.setItem('cf-approvals', '[]'); } catch (e) {} const keep = { speed: S.speed, auto: S.auto, cap: S.cap, charFilter: S.charFilter }; S = { ...blank(), ...keep }; $('[data-gates]').innerHTML = ''; closeDrawer(); syncDemo(); }
  function syncDemo() { $$('[data-speed]').forEach((b) => b.classList.toggle('is-on', +b.dataset.speed === S.speed)); $('[data-auto]').setAttribute('aria-checked', String(S.auto)); $$('[data-cap]').forEach((b) => b.classList.toggle('is-on', +b.dataset.cap === S.cap)); }

  document.addEventListener('click', (e) => {
    const t = (sel) => e.target.closest(sel);
    let x;
    if ((x = t('[data-approve]'))) { approve(x.dataset.approve, 'human'); return; }
    if ((x = t('[data-review]'))) { openDrawer({ gate: x.dataset.review }); return; }
    if ((x = t('[data-request]'))) {
      const g = gate(x.dataset.request), memo = ((S.open && S.open.req) || '').trim();
      if (!memo) { S.open = { ...S.open, err: '무엇을 고칠지 한 줄 적어 주세요' }; renderDrawer(forecast()); return; }
      const id = subj(g.id);
      S.reviews.push({ gate: g.id, rev: revOf(id), revN: S.tasks[id].rev, at: S.t, by: ME, decision: 'REQUEST_CHANGES', note: memo, items: [] });
      log('human', `<b>${ME}</b> · ${g.code} 수정 요청 · “${esc(memo)}”`, g.id);
      notify('info', `<b>${esc(g.title)}</b> 수정 요청 · “${esc(memo)}”`, g.id);
      S.gates[g.id].st = 'idle'; const el = $(`.gate[data-gate="${g.id}"]`); if (el) el.remove(); closeDrawer();
      rerun(id, { trigger: 'request', memo, settings: `${g.code} 수정 요청` }); return;
    }
    if ((x = t('[data-g4]'))) { const [c, v] = x.dataset.g4.split(':'); S.open.g4.c[c] = v; S.open.err = null; renderDrawer(forecast()); if (v === 'fix') { const ta = $(`[data-g4-note="${c}"]`); if (ta) ta.focus(); } return; }
    if (t('[data-g4-send]')) {
      const st = S.open.g4, items = [1, 2, 3].map((c) => ({ ch: c, ok: st.c[c] !== 'fix', note: (st.n[c] || '').trim() }));
      const fix = items.filter((i) => !i.ok);
      if (fix.some((i) => !i.note)) { S.open.err = '수정 요청한 장에 무엇을 고칠지 적어 주세요'; renderDrawer(forecast()); return; }
      const memo = fix.map((i) => `${i.ch}장 “${i.note}”`).join(' · ');
      S.reviews.push({ gate: 'G4', rev: revOf('v4'), revN: S.tasks.v4.rev, at: S.t, by: ME, decision: 'REQUEST_CHANGES', items });
      notify('info', `<b>${esc(gate('G4').title)}</b> 수정 요청 · ${fix.map((i) => i.ch).join('·')}장만 다시`, 'G4');
      log('human', `<b>${ME}</b> · G4 수정 요청 · ${esc(memo)}${items.some((i) => i.ok) ? ` · ${items.filter((i) => i.ok).map((i) => i.ch).join('·')}장 승인` : ''}`, 'G4');
      S.gates.G4.st = 'idle'; const el = $('.gate[data-gate="G4"]'); if (el) el.remove(); closeDrawer();
      rerun('v4', { trigger: 'request', memo, chapters: fix.map((i) => i.ch), settings: `G4 수정 요청 · ${fix.map((i) => i.ch).join('·')}장` });
      return;
    }
    if ((x = t('[data-follow]'))) { const id = x.dataset.follow, tgt = '#job/seoha-new/floor'; closeDrawer(); if (location.hash !== tgt) location.hash = tgt; setTimeout(() => { render(); window.CF_FLOOR.focus(id); }, 160); return; }
    if ((x = t('.floor [data-floor-task], .floor .fl-lab[data-task], .floor .fl-gname[data-review]'))) {
      const id = x.dataset.task || x.dataset.floorTask || x.dataset.review;
      if (window.CF_FLOOR.focused() === id) openDrawer(isGate(id) ? { gate: id } : { task: id }); else window.CF_FLOOR.focus(id);
      return;
    }
    if ((x = t('[data-other-review]'))) { openDrawer({ other: x.dataset.otherReview }); return; }
    if ((x = t('[data-other-approve]'))) { const o = other(x.dataset.otherApprove); S.otherDone[o.key] = true; log('human', `<b>${ME}</b> · ${esc(o.name)} G6 승인 · ${esc(o.assets.persona.prog)}`); closeDrawer(); save(); return; }
    if ((x = t('[data-char-filter]'))) { S.charFilter = x.dataset.charFilter; return; }
    if (t('[data-newjob-toggle]')) { S.newJobOpen = !S.newJobOpen; return; }
    if ((x = t('[data-newjob]'))) { const K = JOB_KINDS.find((k) => k.k === x.dataset.newjob); S.jobs.push({ k: K.k, at: S.t }); S.newJobOpen = false; log('human', `<b>${ME}</b> · ${esc(nameOf(SEOHA))} ${K.name} 요청 · ${Object.values(K.fam).join(', ')}`); save(); return; }
    if (t('[data-release]')) { S.released = true; S.releasedAt = S.t; log('human', `<b>${ME}</b> · ${esc(nameOf(SEOHA))} 출시 승인 · G9 · release_rev rl1`, 'G9'); notify('done', `<b>${esc(nameOf(SEOHA))}</b> 출시 승인 · 캐릭터 완성`, 'G9'); save(); return; }

    if ((x = t('[data-spot]'))) { const id = x.dataset.spot, tgt = '#job/seoha-new/floor'; closeDrawer(); if (location.hash !== tgt) location.hash = tgt; setTimeout(() => { render(); window.CF_FLOOR.spot(id); }, 160); return; }
    if ((x = t('[data-floor-team]'))) { const tid = x.dataset.floorTeam; location.hash = '#job/seoha-new'; setTimeout(() => { render(); const row = $(`.row.body[data-team="${tid}"]`); if (row && !row.classList.contains('is-open')) toggleRow(tid); if (row) row.scrollIntoView({ block: 'center', behavior: 'smooth' }); }, 120); return; }
    if ((x = t('[data-go-workroom]'))) { x.href = workroomHref(gate(x.dataset.goWorkroom)); save(); return; }
    if ((x = t('[data-rerun]'))) { rerun(x.dataset.rerun); if (S.open && S.open.task) S.open.mode = null; return; }
    if ((x = t('[data-skip]'))) { skipTask(x.dataset.skip); return; }
    if ((x = t('[data-settings]'))) { S.open = { ...S.open, mode: S.open.mode === 'settings' ? null : 'settings' }; return; }
    if ((x = t('[data-opt-model]'))) { S.open = { ...S.open, model: x.dataset.optModel }; return; }
    if ((x = t('[data-opt-strict]'))) { S.open = { ...S.open, strict: x.dataset.optStrict }; return; }
    if ((x = t('[data-rerun-settings]'))) { const note = ($('[data-opt-note]') || {}).value || ''; const parts = []; const T = task(x.dataset.rerunSettings); if (S.open.model && S.open.model !== T.model) parts.push(`모델 ${S.open.model}`); if (S.open.strict && S.open.strict !== '기본') parts.push(`검사 ${S.open.strict}`); if (note.trim()) parts.push(`메모 “${note.trim().slice(0, 40)}”`); rerun(T.id, { settings: parts.join(', ') || '설정 유지' , note: '설정 바꿔 다시 실행' }); S.open = { task: T.id }; return; }
    if ((x = t('[data-open-task]'))) { openDrawer({ task: x.dataset.openTask, mode: x.dataset.mode || null }); return; }
    if ((x = t('[data-task]'))) { openDrawer({ task: x.dataset.task }); return; }
    if (t('[data-close]') || t('[data-scrim]')) { closeDrawer(); return; }
    if (t('[data-start]')) { S.running = true; log('human', `<b>${ME}</b> · 기획안 주입 · 실행 시작`); startReady(); save(); return; }
    if (t('[data-pause]')) { S.paused = !S.paused; log('human', `<b>${ME}</b> · 실행 ${S.paused ? '일시정지' : '재개'}`); if (!S.paused) startReady(); save(); return; }
    if (t('[data-cancel]')) { $('[data-confirm-cancel]').hidden = false; return; }
    if (t('[data-cancel-no]')) { $('[data-confirm-cancel]').hidden = true; return; }
    if (t('[data-cancel-yes]')) { S.cancelled = true; TASKS.forEach((T) => { const s = S.tasks[T.id]; if (s.st === 'running' || s.st === 'blocked') { const a = s.attempts[s.attempts.length - 1]; if (a) { a.st = 'stopped'; a.end = S.t; } s.st = 'queued'; S.sunk += (T.cost + xcost(T.id)) * s.p; s.p = 0; } }); log('human', `<b>${ME}</b> · 실행 취소`); $('[data-confirm-cancel]').hidden = true; save(); return; }
    if (t('[data-raise]')) { const v = Math.ceil((projected() + 2) / 5) * 5; S.cap = v; log('human', `<b>${ME}</b> · 예산 상한 ${usd(v)}로 변경`); TASKS.forEach((T) => { S.tasks[T.id].held = false; }); syncDemo(); startReady(); save(); return; }
    if ((x = t('.row.body .c-team'))) { toggleRow(x.closest('.row.body').dataset.team); return; }
    if (t('[data-fl-panel]')) { setPanel(!panelOpen()); return; }
    if (t('[data-fl-big]')) { setBig(!document.body.classList.contains('is-stagebig')); return; }
    if (t('[data-fl-guide]')) { window.CF_FLOOR.guide(true); return; }
    if ((x = t('[data-speed]'))) { S.speed = +x.dataset.speed; syncDemo(); return; }
    if ((x = t('[data-cap]'))) { S.cap = +x.dataset.cap; TASKS.forEach((T) => { S.tasks[T.id].held = false; }); syncDemo(); startReady(); return; }
    if (t('[data-auto]')) { S.auto = !S.auto; syncDemo(); return; }
    if ((x = t('[data-log-filter]'))) { S.logFilter = x.dataset.logFilter; $('[data-log-list]')._h = null; return; }
    if ((x = t('[data-demo]'))) { const d = $('[data-demo-bar]'); const o = !d.classList.contains('is-open'); d.classList.toggle('is-open', o); x.classList.toggle('is-on', o); return; }
    if (t('[data-reset]')) reset();
  });
  // 크게 보기: 지표 줄과 오른쪽 패널을 접고 공장 현장이 화면을 채운다. 시연 화면 공유용
  function setBig(on) {
    document.body.classList.toggle('is-stagebig', on);
    try { localStorage.setItem('cf-floor-big', on ? '1' : '0'); } catch (e) { /* 저장 못 해도 동작 */ }
    const b = $('[data-fl-big]'); if (b) { b.innerHTML = icon(on ? 'minimize' : 'maximize') + (on ? '기본 보기' : '크게 보기'); b.setAttribute('aria-pressed', String(on)); b.title = (on ? '기본 보기' : '크게 보기') + ' (F)'; }
    window.CF_FLOOR.resize(); render();
  }
  document.addEventListener('keydown', (e) => {
    if (e.target.closest?.('[data-text-pipeline-root]')) return;
    if (window.CF_FLOOR.guiding()) { if (e.key === 'Escape') window.CF_FLOOR.guide(false); return; }
    const typing = e.target.closest && e.target.closest('input, textarea, select, [contenteditable]');
    if (document.body.dataset.sub === 'floor' && !typing && !S.open && !e.metaKey && !e.ctrlKey && !e.altKey) {
      if ((e.key === 'l' || e.key === 'L') && document.body.classList.contains('is-stagebig')) { e.preventDefault(); setPanel(!panelOpen()); return; }
      if (e.key === 'f' || e.key === 'F') { e.preventDefault(); setBig(!document.body.classList.contains('is-stagebig')); return; }
      if (e.key === '?' || e.key === 'h' || e.key === 'H') { e.preventDefault(); window.CF_FLOOR.guide(true); return; }
    }
    if (e.key === 'Escape') { if (S.open) closeDrawer(); else if (window.CF_FLOOR.focused()) window.CF_FLOOR.focus(null); }
    const tr = e.target.closest && e.target.closest('tr[data-task], .c-team, .fl-feed li[role=button], .ev[role=button]');
    if (tr && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); tr.click(); }
  });
  document.addEventListener('input', (e) => {
    const n = e.target;
    if (n.matches && n.matches('[data-g4-note]') && S.open && S.open.g4) { S.open.g4.n[n.dataset.g4Note] = n.value; S.open.err = null; }
    else if (n.matches && n.matches('[data-req-note]') && S.open) { S.open.req = n.value; S.open.err = null; }
  });
  $('[data-log]').addEventListener('toggle', () => { $('[data-log-list]')._h = null; });
  window.addEventListener('hashchange', () => { closeDrawer(); render(); });
  window.addEventListener('storage', (e) => { if (e.key === 'cf-approvals') applyApprovals(); });
  window.addEventListener('pagehide', save);

  $$('[data-icon]').forEach((e) => { e.outerHTML = icon(e.dataset.icon, e.className || 'ic'); });
  build();
  if (!restore()) S = blank();
  applyApprovals();
  syncDemo();
  { let big = false, pan = false; try { big = localStorage.getItem('cf-floor-big') === '1'; pan = localStorage.getItem('cf-floor-panel') === '1'; } catch (e) { /* 기본값 */ } setTimeout(() => { setBig(big); setPanel(pan); }, 0); }
  window.__ops = { get state() { return S; }, approve, rerun, skipTask, TASKS, GATES };
  // 공장 현장(floor.js)은 같은 상태와 같은 동작(작업 상세, 결재, 작업실 이동)을 쓴다.
  window.CF_FLOOR.attach({
    get S() { return S; }, TASKS, TEAMS, GATES, FAM, SEOHA, ST, task, gate, team, A, icon, esc, hm, dur$,
    forecast, teamView, famState, seohaLife, nameOf, avatarHTML, workroomHref, openDrawer, relPending, stall, revOf, REVP, frames, thumbsOf, lastRequest, subj,
    freeze: (on) => { frozen = !!on; }, frozen: () => frozen, unlockedBy,
    takeApproved: () => { const l = justApproved; justApproved = []; return l; }
  }, $('[data-floor]'));

  // 진행은 매 프레임, 화면은 초당 8번만 다시 그린다
  let last = performance.now(), lastDraw = 0, lastSave = 0;
  function loop(now) {
    const dt = Math.min(0.1, (now - last) / 1000); last = now;
    advance(dt);
    if (document.body.dataset.sub === 'floor') window.CF_FLOOR.tick(dt);
    if (now - lastDraw > 120) { render(); lastDraw = now; }
    if (now - lastSave > 1000) { save(); lastSave = now; }
    requestAnimationFrame(loop);
  }
  window.AppBar.init({
    notes: () => S.notes,
    unread: () => S.unread,
    markRead: () => { S.unread = 0; save(); },
    picks: () => pickList(),
    currentGate: () => null,
    spot: (id) => { const tgt = '#job/seoha-new/floor'; if (location.hash !== tgt) location.hash = tgt; setTimeout(() => { render(); window.CF_FLOOR.spot(id); }, 160); },
    back: () => 'd-ops.html' + (location.hash || '#chars'),
    beforeLeave: () => save()
  });
  render();
  requestAnimationFrame(loop);
})();

