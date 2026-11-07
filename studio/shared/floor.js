// 공장 현장: 진행 현황과 같은 시뮬레이션 상태를 아이소메트릭 공장 바닥으로 보여 준다.
// 팀마다 벨트 하나, 작업마다 작업대 하나, 관문마다 차단기 하나. 끝난 작업의 산출물 상자는 벨트를 타고
// 다음 공정이나 관문 앞에서 기다리고, 라인 끝에서 모아 캐릭터 포장대로 들어간다.
(function FLOOR() {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  // 비대칭 축측 투영: 벨트(X)는 화면 가로로 길게, 라인(Y)은 앞쪽 아래로 쌓인다. 넓은 화면을 채우기 위한 각도다.
  const SC = 10, EX = [1, 0.16], EY = [-0.3, 0.55], EZ = 0.85;
  const P = (X, Y, Z = 0) => [(X * EX[0] + Y * EY[0]) * SC, (X * EX[1] + Y * EY[1] - Z * EZ) * SC];
  const r1 = (n) => Math.round(n * 10) / 10;
  const GAP = 22, X0 = -6, S0 = 2, SW = 88, XC = 96, YC = 66, BW = 2.3, SLAT = 3;
  const PACK = { x0: 106, x1: 122, y0: 58, y1: 74, h: 9 };
  const XP = (PACK.x0 + PACK.x1) / 2;
  // 라인 위 순서: 작업과 관문. 같은 팀 안에서 계획 일정 순서다.
  const LINES = {
    plan: ['p1', 'p2', 'G3', 'p3'], visual: ['s1', 'G1', 'v1', 'v2', 'G4a', 'v3', 'v4', 'G4'], video: ['f1', 'G5b', 'f2'],
    marketing: ['k1', 'k2', 'k3'], persona: ['r1', 'r2', 'G6'], data: ['d1', 'd2', 'd3', 'G7'], train: ['t1', 't2']
  };
  const V = 6; // 시뮬레이션 1분 동안 벨트가 움직이는 거리
  // 작업대 위 실시간 문구. 진행률(s.p)에서 계산하므로 진행과 어긋난 움직임을 만들지 않는다. 장소·영상 이름은 데모 각본이다.
  const n$ = (v) => Math.round(v).toLocaleString('en-US');
  const BG = ['필름 현상소 카운터', '현상소 암실', '비 오는 골목', '동네 사진관 앞', '한강 산책로', '야시장 골목', '새벽 버스 정류장', '옥상 정원', '해질녘 다리'];
  const CLIP = ['glad_good', 'amused_good', 'shy_good', 'sorry_good', 'relieved_bad', 'sympathy_bad', 'sorry_bad', 'hurt_bad', 'sad_bad', 'pout_bad', 'proud_good', 'worried_bad'];
  const FR = ['frame-ch1', 'frame-ch2', 'frame-ch3'];
  const STEP = {
    p1: { list: ['브리프 문장 12개 읽는 중', '타깃·제약 정리 중', '기획 씨앗 sd1 고정 중'] },
    p2: { list: ['윤서하 안 쓰는 중', '한지우 안 쓰는 중', '서은결 안 쓰는 중', '같은 상황 첫 행동 비교 중'] },
    s1: { list: ['화제성 순위 42명 특징 태깅 중', '외모군 3개로 묶는 중', '외모군 1 얼굴 생성 중', '외모군 2 얼굴 생성 중', '외모군 3 얼굴 생성 중'], tiles: ['hero-b', 'hero-a', 'cluster-c3'] },
    v1: { list: ['G1 얼굴로 기준 사진 생성 중', '동일인 판정 중'], tiles: ['hero-b2'] },
    v2: { n: 9, f: (k) => BG[k - 1] + ' 배경 만드는 중', tiles: ['bg-ch1-b1', 'bg-ch1-b2', 'bg-ch1-b3', 'bg-ch2-b1', 'bg-ch2-b2', 'bg-ch2-b3', 'bg-ch3-b1', 'bg-ch3-b2', 'bg-ch3-b3'] },
    p3: { list: ['1장 장면 사실 쓰는 중', '2장 관계 정본 잇는 중', '3장 장면 경계 정리 중'] },
    v3: { list: ['1장 자세 후보 3개', '2장 자세 후보 3개', '3장 자세 후보 3개', '챕터별 의상 정리 중'] },
    v4: { tiles: FR, fn: (q, s) => (s && s.partial ? { idx: Math.floor(q * 3), line: s.partial.memo + ' 반영 중' } : { idx: Math.floor(q * 3), line: Math.min(3, Math.floor(q * 3) + 1) + '장 완성 이미지 합성 중' }) },
    f1: { n: 6, f: (k) => Math.ceil(k / 2) + '장 ' + (k % 2 ? '좋은 기분' : '나쁜 기분') + ' 대기 영상 렌더링', tiles: [FR[0], FR[0], FR[1], FR[1], FR[2], FR[2]] },
    f2: { n: 37, f: (k) => CLIP[k % CLIP.length] + ' 행동 영상 렌더링' },
    k1: { list: ['세로 첫 프레임 생성 중', '소개 쇼츠 1편 렌더링', '소개 쇼츠 2편 렌더링'], tiles: ['hero-b'] },
    k2: { list: ['한 줄 소개 쓰는 중', '프로필 태그 고르는 중'] },
    k3: { n: 3, f: (k) => k + '장 장면에서 썸네일 자르는 중', tiles: FR },
    r1: { list: ['주목·해석 항목 쓰는 중', '대응·강도 항목 쓰는 중', '상황별 변화 쓰는 중', '경험·말버릇 정리 중'] },
    r2: { list: ['긴 프롬프트 조립 중', '짧은 프롬프트로 압축 중', '두 프롬프트 섹션 대조 중'] },
    d1: { total: 2400, f: () => '대화를 서하 말투로 다시 쓰는 중' },
    d2: { total: 3100, f: () => '상황 묶음별로 대화를 늘리는 중' },
    d3: { total: 3100, f: () => 'LLM이 대화 품질을 검사하는 중' },
    t1: { fn: (q) => ({ idx: Math.floor(q * 6), line: '학습 ' + Math.min(3, 1 + Math.floor(q * 3)) + '바퀴째 · loss ' + (1.92 - 1.24 * Math.sqrt(q)).toFixed(2) }) },
    t2: { n: 40, f: () => '블라인드 비교 쌍 만드는 중' }
  };
  // 관문 쉬운 이름: 공장 바닥에서는 코드(G4a) 대신 이 이름을 보인다. 코드는 툴팁·상세에 남긴다
  const GSHORT = { G1: '얼굴 고르기', G3: '기획안 고르기', G4a: '배경 고르기', G4: '이미지 승인', G5b: '움직임 고르기', G6: '페르소나 승인', G7: '표본 검수' };
  const gName = (id) => GSHORT[id] || api.gate(id).title;
  // 에이전트 한국어 역할명: 실시간 목록에서 영어 이름 앞에 쓴다
  const ROLE = { Scout: '외모 탐색', Planner: '기획안 작성', Stylist: '외모 정리', 'Location Scout': '배경 탐색', 'Scene Writer': '장면 작가', 'Pose Director': '자세 연출', Framer: '이미지 합성', Director: '영상 제작', Releaser: '출시 자료', Profiler: '성격 분석', Prompter: '프롬프트 작성', DataSmith: '데이터 제작', Judge: '품질 심사', Trainer: '모델 학습' };
  const ROLE_KEYS = Object.keys(ROLE).sort((a, b) => b.length - a.length);
  const BARI = '<svg class="gn-bar" viewBox="0 0 14 12" aria-hidden="true"><path d="M2.5 11.5V1.5M11.5 11.5V1.5M1 4.5h12"/></svg>';
  // 상자 하나 = 산출물 하나(또는 묶음 하나). 단위가 6개를 넘으면 6묶음으로 나눈다
  const CHN = ['친해지기', '썸타기', '고백하기'];
  const UNITS = {
    s1: { n: 3, l: (k) => '외모군 ' + (k + 1) + ' 얼굴', th: () => ['hero-b', 'hero-a', 'cluster-c3'] },
    p1: { n: 1, l: () => '브리프 해석 · 기획 씨앗' },
    p2: { n: 3, l: (k) => '기획안 ' + (k + 1) + ' · ' + ['윤서하', '한지우', '서은결'][k] },
    v1: { n: 1, l: () => '기준 사진', th: () => ['hero-b2'] },
    v2: { n: 9, l: (k) => '배경 ' + (k + 1) + '/9 · ' + BG[k], th: () => STEP.v2.tiles },
    p3: { n: 3, l: (k) => (k + 1) + '장 장면 사실 · ' + CHN[k] },
    v3: { n: 3, l: (k) => (k + 1) + '장 자세 후보 3개' },
    v4: { n: 3, l: (k) => (k + 1) + '장 완성 이미지 · ' + CHN[k], th: () => api.frames() },
    f1: { n: 6, l: (k) => '대기 영상 ' + (k + 1) + '/6 · ch' + (1 + Math.floor(k / 2)) + ' ' + (k % 2 ? 'idle_bad' : 'idle_good'), th: () => [0, 0, 1, 1, 2, 2].map((i) => api.frames()[i]), video: '15초' },
    f2: { n: 37, unit: '행동 영상', th: () => api.frames(), video: '10초' },
    k1: { n: 2, l: (k) => '소개 쇼츠 후보 ' + (k + 1), th: () => ['hero-b'], video: '8초' },
    k2: { n: 1, l: () => '프로필 카드 문구' },
    k3: { n: 3, l: (k) => '썸네일 ' + (k + 1) + '/3', th: () => api.frames() },
    r1: { n: 1, l: () => '특질 시트' },
    r2: { n: 2, l: (k) => ['긴 프롬프트', '짧은 프롬프트'][k] },
    d1: { n: 2400, unit: '재작성 대화' }, d2: { n: 3100, unit: '증강 대화' }, d3: { n: 3100, unit: '품질 검사 결과' },
    t1: { n: 1, l: () => 'LoRA 어댑터' }, t2: { n: 40, unit: '블라인드 비교 쌍' }
  };
  // 9개까지는 하나씩, 그보다 많으면 6묶음
  const boxes = (id) => { const n = (UNITS[id] || { n: 1 }).n; return n <= 9 ? n : 6; };
  function unitOf(id, k) {
    const u = UNITS[id] || { n: 1, l: () => api.task(id).out };
    const thl = u.th ? u.th() : null;
    if (u.n <= 9) return { label: u.l(k), th: thl ? thl[k % thl.length] : null, video: u.video, count: 1 };
    const per = Math.ceil(u.n / 6), a = k * per + 1, b = Math.min(u.n, (k + 1) * per);
    return { label: u.unit + ' ' + a.toLocaleString('en-US') + '–' + b.toLocaleString('en-US') + ' / ' + u.n.toLocaleString('en-US'), th: thl ? thl[k % thl.length] : null, video: u.video, count: b - a + 1 };
  }
  // 진행 표시는 하나만: 개수가 있는 작업은 '완료 수/전체'(썸네일 수와 같다), 나머지는 %
  function stepOf(T, s) {
    const d = STEP[T.id], q = Math.max(0, Math.min(0.999, s.p)), pct = Math.round(q * 100) + '%';
    if (!d) return { idx: 0, line: '', prog: pct };
    if (d.fn) return Object.assign({ prog: pct }, d.fn(q, s));
    if (d.list) { const i = Math.min(d.list.length - 1, Math.floor(q * d.list.length)); return { idx: i, line: d.list[i], prog: pct }; }
    if (d.n) { const done = Math.floor(q * d.n), k = Math.min(d.n, done + 1); return { idx: d.n > 9 ? Math.floor(k / 6) : k, line: d.f(k), prog: done + '/' + d.n }; }
    return { idx: Math.floor(q * 5), line: d.f(q * d.total, q), prog: n$(q * d.total) + '/' + n$(d.total) };
  }
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let api, S, root, stage, cam, svg, ov, tip, built = false, visible = false, snap = true, vb, size = '';
  let pkSeq = 0, pop = null;
  const parcels = {};
  // 결재 승인 순간 풀리는 라인 표시(rels): 관문 id → { targets, until, html, g }. relPrev는 직전 관문 상태
  const rels = {}, relPrev = {}, RELMS = 2800;
  let relSeen = false, relLast = 0;
  // 승인 표시 시간은 실행 중에만 흐른다. 일시정지·구성 보기 중에는 그대로 남아 발표자가 설명할 수 있다
  function relClock(nowMs) {
    const dt = relLast ? nowMs - relLast : 0; relLast = nowMs;
    const held = !S.running || S.paused || S.cancelled || api.frozen();
    Object.keys(rels).forEach((k) => { const r = rels[k]; if (held) { r.until += dt; r.targets.forEach((x) => { if (where[x].sl.unl) where[x].sl.unl += dt; }); } else if (r.until <= nowMs) { r.g.remove(); delete rels[k]; } });
  }
  let gA = null, gIdx = -1, lowOK = false, lowPx = 20, hiPx = 30, gHiPx = 40;
  let focus = null, follow = true, camK = 1, camKey = '', chain = new Set(), arcs = [];
  const where = {};
  const lanes = [], pk = {}, prevKey = {}, cache = new WeakMap();
  const B = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
  const lyr = {};

  const el = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };
  const grow = (p) => { B.x0 = Math.min(B.x0, p[0]); B.x1 = Math.max(B.x1, p[0]); B.y0 = Math.min(B.y0, p[1]); B.y1 = Math.max(B.y1, p[1]); };
  const pts = (arr, track = true) => arr.map((a) => { const q = P(...a); if (track) grow(q); return r1(q[0]) + ',' + r1(q[1]); }).join(' ');
  const html = (n, h) => { if (cache.get(n) !== h) { n.innerHTML = h; cache.set(n, h); } };
  function box(parent, x0, x1, y0, y1, z0, z1, cls) {
    const g = el('g', { class: cls || '' }, parent);
    el('polygon', { class: 'f-l', points: pts([[x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1]]) }, g);
    el('polygon', { class: 'f-r', points: pts([[x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1]]) }, g);
    el('polygon', { class: 'f-top', points: pts([[x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]]) }, g);
    return g;
  }
  const line = (parent, a, b, cls) => { const p = P(...a), q = P(...b); grow(p); grow(q); return el('line', { x1: r1(p[0]), y1: r1(p[1]), x2: r1(q[0]), y2: r1(q[1]), class: cls }, parent); };
  const at = (X, Y, Z = 0) => { const q = P(X, Y, Z); return { left: ((q[0] - vb.x) / vb.w) * 100 + '%', top: ((q[1] - vb.y) / vb.h) * 100 + '%' }; };
  const place = (n, X, Y, Z) => { const p = at(X, Y, Z); n.style.left = p.left; n.style.top = p.top; };
  const shift = (dx, dy) => { const a = P(dx, dy), o = P(0, 0); return 'translate(' + r1(a[0] - o[0]) + ' ' + r1(a[1] - o[1]) + ')'; };
  function slats(parent, id, clipPts, along, from, to, fixed, z) {
    const cp = el('clipPath', { id }, lyr.defs); el('polygon', { points: clipPts }, cp);
    const wrap = el('g', { 'clip-path': 'url(#' + id + ')' }, parent);
    const g = el('g', { class: 'slats' }, wrap);
    for (let v = from - SLAT; v <= to + SLAT; v += SLAT) {
      if (along === 'x') line(g, [v, fixed - BW, z], [v, fixed + BW, z], 'slat');
      else line(g, [fixed - BW, v, z], [fixed + BW, v, z], 'slat');
    }
    return g;
  }

  // ---------- 상태
  function taskKey(T) {
    const s = S.tasks[T.id];
    if (s.st === 'done') return 'done';
    if (S.cancelled) return 'cancelled';
    if (s.st === 'blocked') return 'human';
    if (s.st === 'running') { if (S.paused) return 'paused'; const la = s.attempts[s.attempts.length - 1]; if (la && la.trigger === 'auto') return 'retry'; return 'working'; }
    return s.held ? 'budget' : 'idle';
  }

  // ---------- 장면 만들기
  function build() {
    root.innerHTML = '';
    stage = document.createElement('div'); stage.className = 'fl-stage'; root.appendChild(stage);
    cam = document.createElement('div'); cam.className = 'fl-cam'; stage.appendChild(cam);
    svg = el('svg', { role: 'group', 'aria-label': '공장 현장 · 팀별 라인, 작업대, 결재 차단기, 캐릭터 포장대' }, cam);
    ov = document.createElement('div'); ov.className = 'fl-ov'; cam.appendChild(ov);
    lyr.fbar = document.createElement('div'); lyr.fbar.className = 'fl-focus glass'; lyr.fbar.hidden = true; root.appendChild(lyr.fbar);
    lyr.fbar.addEventListener('click', onBar);
    lyr.pop = document.createElement('div'); lyr.pop.className = 'fl-pkpop glass'; lyr.pop.hidden = true; lyr.pop.setAttribute('role', 'dialog'); lyr.pop.setAttribute('aria-label', '산출물 상세'); root.appendChild(lyr.pop);
    lyr.pop.addEventListener('click', (e) => { if (e.target.closest('[data-pp-close]')) popClose(); });
    tip = document.createElement('div'); tip.className = 'fl-tip glass'; tip.hidden = true; root.appendChild(tip);
    lyr.feed$ = document.createElement('div'); lyr.feed$.className = 'fl-feed glass';
    lyr.feed$.innerHTML = '<h4><i></i>지금 일하는 에이전트 <b class="num" data-crew-n></b><small>누르면 상세</small></h4><ol class="fl-crew"></ol><p class="cw-empty"></p>'; root.appendChild(lyr.feed$);
    lyr.crew = lyr.feed$.querySelector('.fl-crew'); lyr.crewN = lyr.feed$.querySelector('[data-crew-n]'); lyr.crewEmpty = lyr.feed$.querySelector('.cw-empty');
    // 범례: 바닥 위 요소가 무엇인지 한 줄로 알려 준다
    lyr.legend = document.createElement('div'); lyr.legend.className = 'fl-legend'; lyr.legend.setAttribute('aria-label', '공장 현장 범례');
    lyr.legend.innerHTML = [
      ['belt', '라인', '팀 하나'], ['station', '작업대', '에이전트 작업'], ['gate', '차단기', '사람 결재'], ['pkg', '상자', '산출물'], ['pack', '포장대', '캐릭터 출시 묶음']
    ].map(([k, a, b]) => '<span class="lg-i"><i class="lg-' + k + '"></i><b>' + a + '</b>' + b + '</span>').join('');
    root.appendChild(lyr.legend);
    lyr.defs = el('defs', {}, svg);
    lyr.plate = el('g', { class: 'plate-g' }, svg);
    lyr.col = el('g', { class: 'collector' }, svg);
    lyr.lanes = el('g', {}, svg);
    lyr.colPk = el('g', { class: 'pkgs' }, svg);
    lyr.pack = el('g', { class: 'pack' }, svg);
    lyr.fx = el('g', { class: 'fx' }, svg);
    lyr.arcs = el('g', { class: 'arcs' }, svg);
    lyr.rel = el('g', { class: 'rels' }, svg);

    // 바닥판과 격자
    const yMax = (api.TEAMS.length - 1) * GAP;
    el('polygon', { class: 'plate', points: pts([[-16, -10, 0], [127, -10, 0], [127, yMax + 10, 0], [-16, yMax + 10, 0]]) }, lyr.plate);
    for (let x = -14; x <= 126; x += 10) line(lyr.plate, [x, -10, 0], [x, yMax + 10, 0], 'grid-l');
    for (let i = 0; i <= api.TEAMS.length; i++) line(lyr.plate, [-16, i * GAP - GAP / 2, 0], [127, i * GAP - GAP / 2, 0], 'grid-l');

    // 모으는 벨트: 라인 끝(X=108)에서 가운데로 모아 포장대로 보낸다
    box(lyr.col, XC - BW, XC + BW, -BW, yMax + BW, 0, 1, 'belt');
    box(lyr.col, XC + BW, PACK.x0, YC - BW, YC + BW, 0, 1, 'belt');
    lyr.colUp = slats(lyr.col, 'cl-up', pts([[XC - BW, -BW, 1], [XC + BW, -BW, 1], [XC + BW, YC, 1], [XC - BW, YC, 1]], false), 'y', -BW, YC, XC, 1);
    lyr.colDn = slats(lyr.col, 'cl-dn', pts([[XC - BW, YC, 1], [XC + BW, YC, 1], [XC + BW, yMax + BW, 1], [XC - BW, yMax + BW, 1]], false), 'y', YC, yMax + BW, XC, 1);
    lyr.feed = slats(lyr.col, 'cl-fd', pts([[XC + BW, YC - BW, 1], [PACK.x0, YC - BW, 1], [PACK.x0, YC + BW, 1], [XC + BW, YC + BW, 1]], false), 'x', XC, PACK.x0, YC, 1);

    api.TEAMS.forEach((tm, i) => {
      const Y = i * GAP;
      const g = el('g', { class: 'lane', style: '--i:' + i, 'data-li': i }, lyr.lanes);
      const L = { tm, i, Y, g, slots: [], A: XC - X0, B: Math.abs(Y - YC), total: 0, off: 0, active: false, delivered: false };
      // 라인 띠: 이 라인에 속한 작업대·관문이 한 띠 위에 놓인다
      L.band = el('polygon', { class: 'band' + (i % 2 ? ' band-alt' : ''), 'data-li': i, points: pts([[X0 - 7, Y - GAP / 2 + 0.8, 0], [XC + BW + 1.5, Y - GAP / 2 + 0.8, 0], [XC + BW + 1.5, Y + GAP / 2 - 0.8, 0], [X0 - 7, Y + GAP / 2 - 0.8, 0]]) }, lyr.plate);
      L.total = L.A + L.B + (XP - XC);
      const back = el('g', {}, g);
      box(back, X0 - 5, X0, Y - 3.2, Y + 3.2, 0, 3.4, 'dock');
      box(back, X0, XC - BW, Y - BW, Y + BW, 0, 1, 'belt');
      L.slats = slats(back, 'ln-' + i, pts([[X0, Y - BW, 1], [XC - BW, Y - BW, 1], [XC - BW, Y + BW, 1], [X0, Y + BW, 1]], false), 'x', X0, XC, Y, 1);
      L.back = el('g', {}, g); L.pk = el('g', { class: 'pkgs' }, g); L.front = el('g', {}, g);
      const line$ = LINES[tm.id] || [];
      line$.forEach((id, j) => {
        const x = S0 + (j + 0.5) * (SW / line$.length);
        const sl = { id, j, x, u: x - X0, type: /^G/.test(id) ? 'gate' : 'task' };
        if (sl.type === 'task') {
          const T = api.task(id);
          const st = el('g', { class: 'station st-idle', 'data-task': id, 'data-floor-task': id, tabindex: '0', role: 'button', 'data-li': i, 'aria-label': tm.name + ' · ' + T.short + ' 작업 상세 열기' }, L.front);
          box(st, x - 3.4, x + 3.4, Y - 3.4, Y + 3.4, 0, 5.4, 'body');
          el('polygon', { class: 'glow', points: pts([[x - 2.6, Y - 2.6, 5.4], [x + 2.6, Y - 2.6, 5.4], [x + 2.6, Y + 2.6, 5.4], [x - 2.6, Y + 2.6, 5.4]]) }, st);
          const arm = el('g', { class: 'arm' }, st);
          line(arm, [x - 2.8, Y - 2.8, 5.4], [x - 2.8, Y - 2.8, 11.5], 'arm-l');
          line(arm, [x - 2.8, Y - 2.8, 11.5], [x, Y, 11.5], 'arm-l');
          const head = el('g', { class: 'arm-head' }, arm);
          line(head, [x, Y, 11.5], [x, Y, 8.6], 'arm-l');
          box(head, x - 0.7, x + 0.7, Y - 0.7, Y + 0.7, 7.8, 8.6, 'arm-h');
          sl.st = st; sl.T = T;
          const lab = document.createElement('div'); lab.className = 'fl-lab k-idle'; lab.dataset.task = id; lab.dataset.li = i; ov.appendChild(lab); sl.lab = lab;
          lab.innerHTML = '<span class="lb-top"><i class="lb-live"></i><span class="lb-ok">' + api.icon('check') + '</span><b></b><span class="lb-tail num"></span><span class="lb-tiles"></span></span><span class="lb-step"><i></i><span class="lb-who"></span><span class="lb-txt"></span></span>';
          sl.lb = { tail: lab.querySelector('.lb-tail'), step: lab.querySelector('.lb-txt'), tiles: [] };
          lab.querySelector('b').textContent = T.short;
          // 담당 에이전트는 진행 문장의 주어로 쓴다: 'Location Scout · 배경 4/9 …'
          lab.querySelector('.lb-who').textContent = T.agent;
          const td = STEP[id] && STEP[id].tiles;
          if (td) sl.lb.tiles = td.map((src) => { const im = document.createElement('img'); im.src = api.A(src); im.alt = ''; lab.querySelector('.lb-tiles').appendChild(im); return im; });
          // 산출물 상자: 호출 수만큼(최대 6개) 진행률에 맞춰 하나씩 나온다
          pk[id] = { slot: sl, n: boxes(id), gen: -1, emitted: 0, list: [] };
        } else {
          const G = api.gate(id);
          const gb = el('g', { class: 'gate-b g-idle' }, L.back);
          box(gb, x - 0.5, x + 0.5, Y - 3.7, Y - 2.9, 0, 6.5, 'post');
          const gf = el('g', { class: 'gate-f g-idle', 'data-floor-gate': id, 'data-li': i }, L.front);
          sl.bar = el('g', { class: 'barrier' }, gf);
          line(sl.bar, [x, Y - 2.9, 2.4], [x, Y + 2.9, 2.4], 'bar-l');
          box(gf, x - 0.5, x + 0.5, Y + 2.9, Y + 3.7, 0, 6.5, 'post');
          box(gf, x - 0.5, x + 0.5, Y - 3.7, Y + 3.7, 5.9, 6.5, 'beam');
          const lp = P(x, Y, 7.3); grow(lp);
          el('circle', { class: 'lamp', cx: r1(lp[0]), cy: r1(lp[1]), r: 7 }, gf);
          sl.gb = gb; sl.gf = gf; sl.G = G;
          const chip = document.createElement('div'); chip.className = 'fl-gate'; chip.dataset.li = i; ov.appendChild(chip); sl.chip = chip;
          const nm = document.createElement('button'); nm.type = 'button'; nm.className = 'fl-gname'; nm.dataset.review = id; nm.dataset.li = i; ov.appendChild(nm); sl.nm = nm;
        }
        L.slots.push(sl); where[id] = { sl, L };
      });
      const lab = document.createElement('button'); lab.type = 'button'; lab.className = 'fl-lane'; lab.dataset.floorTeam = tm.id; lab.dataset.li = i; lab.setAttribute('aria-label', tm.name + ' 팀 작업 표 열기'); ov.appendChild(lab); L.lab = lab;
      lanes.push(L);
    });

    // 캐릭터 포장대와 입고 상자 자리
    box(lyr.pack, PACK.x0, PACK.x1, PACK.y0, PACK.y1, 0, PACK.h, 'pack-box');
    el('polygon', { class: 'pack-glow', points: pts([[PACK.x0 + 1.6, PACK.y0 + 1.6, PACK.h], [PACK.x1 - 1.6, PACK.y0 + 1.6, PACK.h], [PACK.x1 - 1.6, PACK.y1 - 1.6, PACK.h], [PACK.x0 + 1.6, PACK.y1 - 1.6, PACK.h]]) }, lyr.pack);
    lyr.crates = lanes.map((L, k) => {
      const cx = PACK.x0 + 3.2 + (k % 4) * 3.2, cy = PACK.y0 + 4.5 + Math.floor(k / 4) * 6.5;
      const c = box(lyr.pack, cx - 1.2, cx + 1.2, cy - 1.2, cy + 1.2, PACK.h, PACK.h + 2.4, 'crate pack-crate');
      c.style.display = 'none'; return c;
    });
    grow(P(XP, YC, PACK.h + 14));
    B.x0 -= 380; // 라인 이름 자리
    B.x1 = Math.max(B.x1, P(PACK.x1, YC, 0)[0] + 780); // 포장대 카드 자리
    B.y0 -= 110; // 결재 대기 표시 자리

    const pad = 24;
    vb = { x: B.x0 - pad, y: B.y0 - pad, w: B.x1 - B.x0 + pad * 2, h: B.y1 - B.y0 + pad * 2 };
    svg.setAttribute('viewBox', [vb.x, vb.y, vb.w, vb.h].map(r1).join(' '));

    lanes.forEach((L) => {
      place(L.lab, X0 - 5.6, L.Y, 1.7);
      L.slots.forEach((sl) => { sl.low = false; placeName(sl, L); if (sl.type === 'gate') place(sl.chip, sl.x, L.Y, 7.4); });
    });
    lyr.card = document.createElement('a'); lyr.card.className = 'fl-pack glass'; lyr.card.href = '#char/seoha'; ov.appendChild(lyr.card);
    place(lyr.card, PACK.x1, YC - 2, PACK.h * 0.7);
    // G9 출시 결재: 포장대 위에 둔다
    lyr.g9 = document.createElement('div'); lyr.g9.className = 'fl-gate fl-g9'; ov.appendChild(lyr.g9);
    place(lyr.g9, PACK.x1, YC - 2, PACK.h * 0.7); // 포장대 카드 바로 위

    // 라인 강조: 라인 이름에 올리면 그 라인만 남기고 흐리게, 작업대·관문에 올리면 그 라인 띠만 밝힌다
    const st$ = document.createElement('style');
    st$.textContent = lanes.map((L) => '.floor[data-hlw="' + L.i + '"] .band[data-li="' + L.i + '"]{fill:rgba(255,255,255,.075);stroke:rgba(255,255,255,.2)}'
      + '.floor[data-hl="' + L.i + '"] .fl-ov [data-li]:not([data-li="' + L.i + '"]){opacity:.22}'
      + '.floor[data-hl="' + L.i + '"] svg .station:not([data-li="' + L.i + '"]),.floor[data-hl="' + L.i + '"] svg .gate-f:not([data-li="' + L.i + '"]){opacity:.25}'
      + '.floor.is-guide[data-hl="' + L.i + '"] svg .lane:not([data-li="' + L.i + '"]){opacity:.22}'
      + '.floor.is-guide[data-hlw="' + L.i + '"] .band[data-li="' + L.i + '"]{fill:rgba(255,255,255,.11);stroke:rgba(227,229,233,.6);stroke-width:1.5}'
      + '.floor[data-hl="' + L.i + '"] .fl-lane[data-li="' + L.i + '"]{background:rgba(255,255,255,.07);border-color:rgba(227,229,233,.3)}').join('');
    root.appendChild(st$);
    root.addEventListener('mouseover', (e) => { const n = e.target.closest && e.target.closest('[data-li]'); setHL(n ? n.dataset.li : null, !!(n && n.classList.contains('fl-lane'))); const h = e.target.closest && e.target.closest('.fl-crew li[data-task], .fl-lab.k-working, .fl-lab.k-retry, .fl-lab.k-human, .station.st-working, .station.st-retry, .station.st-human'); setHot(h ? h.dataset.task : null); });
    root.addEventListener('mouseleave', () => { setHL(null); setHot(null); });
    lyr.guide = document.createElement('div'); lyr.guide.className = 'fl-guide'; lyr.guide.hidden = true; root.appendChild(lyr.guide);
    lyr.guide.innerHTML = '<div class="gd-marks">' + GUIDE.map((g, i) => '<span class="gd-mk num">' + (i + 1) + '</span>').join('') + '</div><div class="gd-panel glass" role="dialog" aria-label="공장 구성 안내"></div>';
    lyr.gdMarks = [...lyr.guide.querySelectorAll('.gd-mk')]; lyr.gdPanel = lyr.guide.querySelector('.gd-panel');
    lyr.guide.addEventListener('click', (e) => { if (e.target.closest('[data-gd-close]')) guide(false); else if (e.target.closest('[data-gd-prev]')) gStep(-1); else if (e.target.closest('[data-gd-next]') || !e.target.closest('.gd-panel')) gStep(1); });
    svg.addEventListener('click', (e) => { const g = e.target.closest('[data-parcel]'); if (g && focus) { e.stopPropagation(); popOpen(g.dataset.parcel); } });
    svg.addEventListener('focusin', onFocus); svg.addEventListener('focusout', () => { tip.hidden = true; });
    svg.addEventListener('mouseover', onOver); svg.addEventListener('mousemove', onMove); svg.addEventListener('mouseleave', () => { tip.hidden = true; });
    svg.addEventListener('keydown', (e) => { const n = e.target.closest && e.target.closest('[data-floor-task]'); if (n && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); n.dispatchEvent(new MouseEvent('click', { bubbles: true })); } });
    built = true;
  }

  // 이름표 자리: 작업대 바로 앞. 이웃 이름표와 겹치면 한 줄 아래(is-low)로 내리고 짧은 선으로 잇는다(unstack에서 정한다)
  function placeName(sl, L) {
    if (sl.type === 'task') place(sl.lab, sl.x + 1, L.Y + 3.6, 0); else place(sl.nm, sl.x, L.Y + 3.9, 0);
  }
  // ---------- 상자 이동
  // 상자는 같은 라인에서 자기를 입력으로 쓰는 다음 작업대나 관문까지만 간다. 그런 곳이 없으면 그 사이를 지나 포장대로 간다.
  const consumes = (sl, src) => (sl.type === 'task' ? sl.T.deps.includes(src) : sl.G.after.includes(src));
  function stopFor(L, j) {
    let src = L.slots[j].id;
    for (let k = j + 1; k < L.slots.length; k++) {
      const sl = L.slots[k];
      if (!consumes(sl, src)) continue;
      if (sl.type === 'task') return S.tasks[sl.id].st === 'queued' ? { u: sl.u - 4.6, to: sl.id } : { u: sl.u - 1.2, consume: true, to: sl.id };
      if (S.gates[sl.id].st !== 'approved') return { u: sl.u - 3.4, gate: true, to: sl.id };
      src = sl.id; // 승인된 관문을 지나면 그 관문을 입력으로 쓰는 다음 작업대를 찾는다
    }
    return { u: L.total, end: true, to: 'pack' };
  }
  function posAt(L, u) {
    if (u <= L.A) return [X0 + u, L.Y];
    if (u <= L.A + L.B) return [XC, L.Y + Math.sign(YC - L.Y) * (u - L.A)];
    return [XC + (u - L.A - L.B), YC];
  }
  function mkParcel(L, rec, k) {
    const g = el('g', { class: 'pkg' }, L.pk);
    box(g, -1.1, 1.1, -1.1, 1.1, 1, 3.3, 'crate');
    const T = rec.slot.T, s = S.tasks[T.id], un = unitOf(T.id, k);
    // 누르는 영역은 상자보다 넓게. 포커스 모드에서만 눌린다
    const c = P(0, 0, 2.2);
    el('circle', { class: 'pk-hit', cx: r1(c[0]), cy: r1(c[1]), r: 15 }, g);
    const pid = 'pk' + (++pkSeq); g.dataset.parcel = pid;
    let th = null;
    if (un.th) { th = document.createElement('img'); th.className = 'fl-thumb' + (T.sq ? '' : ' is-wide'); th.src = api.A(un.th); th.alt = ''; th.hidden = true; ov.appendChild(th); }
    const p = { g, th, rec, k, pid, un, born: S.t, att: s.attempts.length, rev: api.revOf(T.id), u: rec.slot.u + 3.6, inCol: false, dead: false };
    parcels[pid] = p;
    return p;
  }
  function drop(p) { if (pop && pop.p === p) popEnd(p, 'in'); p.dead = true; p.g.remove(); if (p.th) p.th.remove(); delete parcels[p.pid]; }
  // 재시도·취소로 버려지는 상자는 벨트 밖으로 튕겨 나간다
  function kick(p, L) {
    if (pop && pop.p === p) popEnd(p, 'kick');
    p.dead = true; if (p.th) p.th.remove(); delete parcels[p.pid];
    p.rec.slot.kickedAt = performance.now();
    if (reduce) { p.g.remove(); return; }
    const [X, Y] = posAt(L, p.u);
    const o = el('g', { transform: shift(X, Y) }, lyr.fx);
    o.appendChild(p.g); p.g.removeAttribute('transform'); p.g.setAttribute('class', 'pkg reject is-bad');
    requestAnimationFrame(() => requestAnimationFrame(() => { p.g.style.transform = 'translate(40px,-90px) rotate(18deg)'; p.g.style.opacity = '0'; }));
    setTimeout(() => o.remove(), 1500);
  }
  function tick(dtReal) {
    if (!built || !visible) return;
    S = api.S;
    const go = S.running && !S.paused && !S.cancelled && !api.frozen();
    const dts = go ? dtReal * S.speed : 0;
    const now = snap || reduce;
    let colActive = false;
    lanes.forEach((L) => {
      let moving = false;
      const alive = [];
      L.slots.forEach((sl) => {
        if (sl.type !== 'task') return;
        const rec = pk[sl.id], s = S.tasks[sl.id], gen = s.attempts.length;
        const kept = (p) => !!(s.partial && s.partial.keep.includes(p.k + 1));
        if (rec.gen !== gen) {
          if (rec.gen >= 0) rec.list.forEach((p) => { if (!p.dead && !kept(p)) kick(p, L); });
          rec.list = rec.gen >= 0 ? rec.list.filter((p) => !p.dead) : []; rec.emitted = 0; rec.gen = gen;
          rec.plan = s.partial ? s.partial.chs.map((c) => c - 1) : null;
        }
        const plan = rec.plan || [...Array(rec.n).keys()];
        const want = s.st === 'done' ? plan.length : s.st === 'running' || s.st === 'blocked' ? Math.min(plan.length - 1, Math.floor(s.p * plan.length)) : 0;
        if (want < rec.emitted) { rec.list.forEach((p) => { if (!p.dead && !kept(p)) kick(p, L); }); rec.list = rec.list.filter((p) => !p.dead); rec.emitted = 0; }
        while (rec.emitted < want) { rec.list.push(mkParcel(L, rec, plan[rec.emitted])); rec.emitted++; }
        const tgt = stopFor(L, sl.j);
        rec.list.forEach((p) => { if (!p.dead) { p.tgt = tgt; alive.push(p); } });
      });
      alive.sort((a, b) => b.u - a.u || a.k - b.k);
      const fronts = {}; // 같은 곳으로 가는 상자끼리만 줄을 선다. 지나가는 상자는 줄을 통과한다
      alive.forEach((p) => {
        const tgt = p.tgt, front = fronts[tgt.to];
        const lim = front ? Math.min(tgt.u, front.u - 3.6) : tgt.u;
        if (now) p.u = lim;
        else if (p.u < lim) { p.u = Math.min(lim, p.u + V * dts); if (p.u < lim - 0.01) { if (p.u > L.A) colActive = true; else moving = true; } }
        if (p.u >= tgt.u - 0.01 && (tgt.consume || tgt.end)) { if (tgt.end && !now) pulsePack(); drop(p); return; }
        const [X, Y] = posAt(L, p.u);
        const inCol = p.u > L.A - 0.5;
        if (inCol !== p.inCol) { (inCol ? lyr.colPk : L.pk).appendChild(p.g); p.inCol = inCol; }
        p.g.setAttribute('transform', shift(X, Y));
        const wait = !!tgt.gate && p.u >= lim - 0.05, inC = !focus || chain.has(p.rec.slot.id);
        if (wait !== p.wait || inC !== p.inC) { p.wait = wait; p.inC = inC; p.g.setAttribute('class', 'pkg' + (wait ? ' is-wait' : '') + (inC ? ' in-chain' : '')); if (p.th) p.th.classList.toggle('in-chain', inC); }
        if (p.th) { const show = !front || front.u - p.u > 7; if (show) place(p.th, X, Y, 6.2); p.th.hidden = !show; }
        fronts[tgt.to] = p;
      });
      L.alive = alive.some((p) => !p.dead);
      const running = go && L.slots.some((sl) => sl.type === 'task' && S.tasks[sl.id].st === 'running');
      L.active = moving || running; L.moving = moving;
      if (L.active && !reduce) { L.off = (L.off + V * dts) % SLAT; L.slats.setAttribute('transform', shift(L.off, 0)); }
    });
    if (colActive && !reduce) {
      lyr.colOff = ((lyr.colOff || 0) + V * dts) % SLAT;
      lyr.colUp.setAttribute('transform', shift(0, lyr.colOff));
      lyr.colDn.setAttribute('transform', shift(0, -lyr.colOff));
      lyr.feed.setAttribute('transform', shift(lyr.colOff, 0));
    }
    if (pop && !pop.ended) { popPlace(); const k = 'x' + Math.round(pop.p.u * 4) + (pop.p.tgt ? pop.p.tgt.to : ''); if (pop.key !== k) { pop.key = k; popRender(); } }
    snap = false;
  }
  function pulsePack() { lyr.pack.classList.remove('is-pulse'); void lyr.pack.getBoundingClientRect(); lyr.pack.classList.add('is-pulse'); }
  function reject(L, sl) {
    if (reduce || (sl.kickedAt && performance.now() - sl.kickedAt < 800)) return;
    const o = el('g', { transform: shift(sl.x + 2.2, L.Y) }, lyr.fx);
    const g = el('g', { class: 'pkg reject is-bad' }, o);
    box(g, -1.1, 1.1, -1.1, 1.1, 1, 3.3, 'crate');
    requestAnimationFrame(() => requestAnimationFrame(() => { g.style.transform = 'translate(40px,-90px) rotate(18deg)'; g.style.opacity = '0'; }));
    setTimeout(() => o.remove(), 1500);
  }

  function tileOn(T, s, n, live) {
    return [...Array(n).keys()].map((i) => {
      if (s.st === 'done') return true;
      if (s.partial) { const j = s.partial.chs.indexOf(i + 1); return j < 0 ? true : live && j < Math.floor(s.p * s.partial.chs.length); }
      return live && i < Math.floor(s.p * n);
    });
  }
  // 라인 하나가 지금 왜 이런 상태인지 한 줄로 말한다
  function laneInfo(L, fc) {
    const ts = L.slots.filter((x) => x.type === 'task').map((x) => x.T), gs = L.slots.filter((x) => x.type === 'gate').map((x) => x.G);
    const st = (id) => S.tasks[id].st, ok = (d) => (/^G/.test(d) ? S.gates[d].st === 'approved' : st(d) === 'done');
    const depName = (d) => (/^G/.test(d) ? gName(d) + ' 결재' : api.team(api.task(d).team).name + ' ' + api.task(d).short);
    if (!S.running) return { cls: 'pre', why: api.hm(Math.min(...ts.map((t) => fc.start[t.id]))) + ' 시작 예정' };
    if (S.cancelled && !ts.every((t) => st(t.id) === 'done')) return { cls: 'pre', why: '실행 취소됨' };
    const human = ts.find((t) => st(t.id) === 'blocked');
    if (human) return { cls: 'alert', why: '사람 확인 필요 · ' + human.short };
    const pend = gs.find((g) => S.gates[g.code].st === 'pending');
    if (pend) return { cls: 'wait', why: gName(pend.code) + ' 결재 대기 · ' + api.dur$(S.t - S.gates[pend.code].since) + '째' };
    const run = ts.filter((t) => st(t.id) === 'running');
    const rv = run.find((t) => { const a = S.tasks[t.id].attempts; return a.length && a[a.length - 1].trigger === 'request'; });
    if (rv) return { cls: 'run', why: rv.short + ' 수정 반영 중' + (S.tasks[rv.id].partial ? ' · ' + S.tasks[rv.id].partial.chs.join('·') + '장' : '') + ' · 남은 ' + api.teamView(L.tm.id, fc).left };
    if (run.length) return { cls: 'run', why: (run.length > 1 ? run.length + '개 작업 중' : run[0].short + ' 작업 중') + ' · 남은 ' + api.teamView(L.tm.id, fc).left };
    if (ts.every((t) => st(t.id) === 'done') && gs.every((g) => S.gates[g.code].st === 'approved')) return { cls: 'done', why: api.hm(Math.max(...ts.map((t) => S.tasks[t.id].end))) + ' 완료' };
    const next = ts.find((t) => st(t.id) === 'queued');
    if (next && S.tasks[next.id].held) return { cls: 'wait', why: '예산 상한에 막힘 · ' + next.short };
    const dep = next && next.deps.find((d) => !ok(d));
    const started = ts.some((t) => st(t.id) !== 'queued');
    // 모래색은 사람 결재를 기다릴 때만. 앞 작업을 기다리는 것은 중립색이다
    return { cls: started ? 'hold' : 'pre', why: dep ? depName(dep) + ' 기다림' : '다음 · ' + (next ? next.short : '') };
  }

  // ---------- 표시 갱신 (초당 8번)
  function render() {
    if (!api) return;
    S = api.S;
    if (!built) build();
    if (!visible) { visible = true; snap = true; root.classList.add('is-enter'); setTimeout(() => root.classList.remove('is-enter'), 1300); }
    fit();
    if (snap) tick(0);
    root.classList.toggle('is-paused', !!(S.paused || !S.running || S.cancelled || gIdx >= 0));
    const fc = api.forecast();
    const ST = api.ST, esc = api.esc, icon = api.icon;
    const first = !fed; fed = true;
    const nowMs = performance.now();
    relClock(nowMs);
    // 이름표 두 줄이 라인 사이에 들어갈 만큼 화면이 클 때만 이웃 이름표를 한 줄 내린다(이름표 높이로 계산)
    const nameH = (where.p1 && where.p1.sl.lab.classList.contains('k-working') ? 0 : where.s1.sl.lab.offsetHeight) || 17;
    lowOK = 0.55 * GAP * SC * (stage.clientWidth / vb.w) >= nameH * 2 + 6; lowPx = nameH + 3;
    // 작업대 위(뒤) 자리: 이름표 기준점에서 작업대 윗면 바로 위까지
    hiPx = Math.round((P(1, 3.6, 0)[1] - P(0, 0, 6.2)[1]) * (stage.clientWidth / vb.w)) + 3;
    if (root.style.getPropertyValue('--hi') !== hiPx + 'px') root.style.setProperty('--hi', hiPx + 'px');
    // 관문 위 자리: 이름표 기준점(차단기 앞)에서 차단기 윗면 위까지
    gHiPx = Math.round((P(0, 3.9, 0)[1] - P(0, 0, 7.6)[1]) * (stage.clientWidth / vb.w)) + 2;
    if (root.style.getPropertyValue('--ghi') !== gHiPx + 'px') root.style.setProperty('--ghi', gHiPx + 'px');
    if (root.style.getPropertyValue('--low') !== (nameH + 3) + 'px') root.style.setProperty('--low', (nameH + 3) + 'px');
    lanes.forEach((L) => {
      const tv = api.teamView(L.tm.id, fc), li = laneInfo(L, fc);
      if (L.cls !== li.cls) { ['pre', 'hold', 'wait', 'run', 'done', 'alert'].forEach((c) => { L.g.classList.toggle('ln-' + c, c === li.cls); L.lab.classList.toggle('ln-' + c, c === li.cls); }); L.cls = li.cls; }
      const run = S.running && !S.paused && L.slots.some((sl) => sl.type === 'task' && S.tasks[sl.id].st === 'running');
      if (L.run !== run) { L.run = run; L.g.classList.toggle('is-run', run); }
      L.lab.classList.toggle('is-unlocked', L.slots.some((x) => x.unl && x.unl > nowMs));
      html(L.lab, '<span class="ln-top">' + icon(L.tm.icon) + '<b>' + esc(L.tm.name) + '</b>' + ST.pill('task', tv.s, null, 'sm') + '</span><span class="ln-why">' + esc(li.why) + '</span>');
      L.slots.forEach((sl) => {
        if (sl.type === 'task') {
          const T = sl.T, s = S.tasks[T.id], k = taskKey(T);
          if (prevKey[T.id] !== k) {
            if (prevKey[T.id] === 'working' && (k === 'retry' || k === 'human')) setTimeout(() => reject(L, sl), 40);
            sl.st.setAttribute('class', 'station st-' + k);
            prevKey[T.id] = k;
          }
          const live = k === 'working' || k === 'retry' || k === 'human';
          let tail = '', line = '';
          const la = s.attempts[s.attempts.length - 1], req = k === 'working' && la && la.trigger === 'request';
          if (k === 'working') { const st = stepOf(T, s); tail = st.prog + (req ? ' · 수정 반영 중' : '') + (api.stall(T.id) ? ' · 정체' : ''); line = req && !s.partial ? '“' + la.memo + '” 반영 중' : st.line; }
          if (k === 'retry') { tail = ST.label('task', 'retry') + ' · 시도 ' + s.attempts.length; line = T.fail.check + ' ' + T.fail.score + ' · ' + T.fail.sub; }
          else if (k === 'human') { tail = ST.label('task', 'human'); line = T.fail.text; }
          else if (k === 'budget' || k === 'paused') { tail = ST.label('task', k); if (k === 'paused') line = stepOf(T, s).line; }
          if (sl.lb.tail.textContent !== tail) sl.lb.tail.textContent = tail;
          if (sl.lb.step.textContent !== line) sl.lb.step.textContent = line;
          sl.cw = { prog: tail, line };
          if (sl.lb.tiles.length) {
            if (T.id === 'v4') { const fr = api.frames(); sl.lb.tiles.forEach((im, i) => { const u = api.A(fr[i]); if (im.getAttribute('src') !== u) im.setAttribute('src', u); }); }
            const on = tileOn(T, s, sl.lb.tiles.length, live); sl.lb.tiles.forEach((im, i) => { if (im.classList.contains('on') !== on[i]) im.classList.toggle('on', on[i]); });
            // 칩에는 완료된 썸네일 가운데 최근 4개만
            const onIdx = on.map((v, i) => (v ? i : -1)).filter((i) => i >= 0), keep4 = new Set(onIdx.slice(-4)); sl.lb.tiles.forEach((im, i) => { const c = !keep4.has(i); if (im.classList.contains('cut') !== c) im.classList.toggle('cut', c); });
          }
          sl.lab.classList.toggle('is-rev', !!req);
          sl.lab.className = 'fl-lab k-' + k + (sl.low ? ' is-low' : '') + (sl.high ? ' is-high' : '') + (sl.hid ? ' is-hidden' : '') + (sl.spot ? ' is-spot' : '') + (sl.hot ? ' is-hot' : '') + (sl.unl && sl.unl > nowMs ? ' is-unlocked' : '');
          sl.st.classList.toggle('is-hot', !!sl.hot);
          sl.st.classList.toggle('is-unlocked', !!(sl.unl && sl.unl > nowMs));
          sl.st.setAttribute('aria-label', L.tm.name + ' · ' + T.short + ' · ' + ST.label('task', k) + ' · 작업 상세 열기');
        } else {
          const G = sl.G, g = S.gates[G.id];
          if (relSeen && relPrev[G.id] && relPrev[G.id] !== 'approved' && g.st === 'approved') release(G.id);
          relPrev[G.id] = g.st;
          const relOn = g.st === 'approved' && rels[G.id];
          const cls = 'g-' + g.st;
          if (sl.gf.getAttribute('class') !== 'gate-f ' + cls) { sl.gf.setAttribute('class', 'gate-f ' + cls); sl.gb.setAttribute('class', 'gate-b ' + cls); }
          let h;
          if (g.st === 'pending') {
            const act = G.kind === 'pick'
              ? '<a class="btn btn--primary btn--sm" href="' + api.workroomHref(G) + '" data-go-workroom="' + G.id + '">고르기' + icon('arrow') + '</a>'
              : '<button type="button" class="btn btn--sm" data-review="' + G.id + '">검토</button><button type="button" class="btn btn--primary btn--sm" data-approve="' + G.id + '">승인</button>';
            const stall = api.stall(G.id);
            h = '<span class="fg-lamp"></span><b>' + esc(gName(G.id)) + '</b><span class="fg-code">' + G.code + '</span><span class="fg-wait num' + (stall ? ' is-stall' : '') + '">' + (stall ? '정체 · ' : '') + api.dur$(S.t - g.since) + '째</span>' + act;
          } else h = relOn ? rels[G.id].html : '';
          html(sl.chip, h);
          sl.chip.className = 'fl-gate is-' + (relOn ? 'released' : g.st) + (sl.left ? ' is-left' : '');
          if (relOn) sl.chip.title = rels[G.id].title; else if (sl.chip.title) sl.chip.title = '';
          const unG = !!(sl.unl && sl.unl > nowMs);
          sl.gf.classList.toggle('is-unlocked', unG);
          const rq = g.st === 'idle' && api.lastRequest(G.id), rqOn = rq && S.tasks[api.subj(G.id)].st !== 'done';
          html(sl.nm, (g.st === 'approved' ? icon('check') : rqOn ? icon('refresh') : BARI) + '<span class="gn-t">' + (rqOn ? '수정 반영 중' + (rq.items.length ? ' · ' + rq.items.filter((i) => !i.ok).map((i) => i.ch).join('·') + '장' : '') : esc(gName(G.id))) + '</span>');
          if (sl.nm.title !== G.code + ' ' + G.title + ' · 사람 결재') { sl.nm.title = G.code + ' ' + G.title + ' · 사람 결재'; sl.nm.setAttribute('aria-label', G.code + ' ' + G.title + ' 결재 상세 열기'); }
          sl.nm.className = 'fl-gname is-' + (rqOn ? 'revising' : g.st) + (sl.low ? ' is-low' : '') + (sl.high ? ' is-high' : '') + (sl.mini ? ' is-mini' : '') + (sl.hid ? ' is-hidden' : '') + (sl.spot ? ' is-spot' : '') + (sl.unl && sl.unl > nowMs ? ' is-unlocked' : '');
        }
      });
    });
    renderCrew();
    updateFocus();
    unstack();
    // 포장대: 라인마다 마지막 상자가 들어오면 입고 상자가 하나씩 쌓인다
    // 라인 완료 수는 상태로 센다(결재함·KPI의 G9 판정과 같은 기준). 입고 상자는 마지막 상자가 도착하면 쌓인다
    const laneDone = (L) => L.slots.every((sl) => (sl.type === 'task' ? S.tasks[sl.id].st === 'done' : S.gates[sl.id].st === 'approved'));
    lanes.forEach((L, k) => {
      L.delivered = !L.alive && laneDone(L);
      lyr.crates[k].style.display = L.delivered ? '' : 'none';
    });
    const nIn = lanes.filter(laneDone).length;
    const ok = api.FAM.filter((f) => api.famState(f).st === 'approved').length;
    const life = api.seohaLife(), rel = api.relPending();
    lyr.pack.classList.toggle('is-gate', rel);
    lyr.pack.classList.toggle('is-ready', !!S.released);
    if (rel) {
      const stall = api.stall('G9');
      html(lyr.g9, '<span class="fg-lamp"></span><b>G9 출시 승인</b><span class="fg-wait num' + (stall ? ' is-stall' : '') + '">' + (stall ? '정체 · ' : '') + api.dur$(S.t - S.finishedAt) + '째</span><a class="btn btn--sm" href="#char/seoha">자산 보기</a><button type="button" class="btn btn--primary btn--sm" data-release>승인</button>');
    } else html(lyr.g9, S.released ? '<span class="fg-mini is-ok">' + icon('check') + 'G9 출시 승인 · rl1</span>' : '<span class="fg-mini">G9 출시 승인</span>');
    lyr.g9.className = 'fl-gate fl-g9 ' + (rel ? 'is-pending' : 'is-mini') + (lyr.g9spot ? ' is-spot' : '');
    html(lyr.card, '<span class="fp-av">' + api.avatarHTML(api.SEOHA) + '</span><span class="fp-body"><span class="fp-top"><b>' + esc(api.nameOf(api.SEOHA)) + '</b>' + ST.pill('life', life[0], null, 'sm') + '</span>'
      + '<span class="fp-meta">자산 승인 <b class="num">' + ok + '/' + api.FAM.length + '</b> · 라인 완료 <b class="num">' + nIn + '/' + lanes.length + '</b></span>'
      + '<span class="meter"><i style="--w:' + Math.round((ok / api.FAM.length) * 100) + '%"></i></span></span>');
    tick(0);
    if (gIdx >= 0) guideRender();
    relSeen = true;
    // 작업실에서 결재하고 돌아온 경우: 화면이 들어선 뒤 승인 순간 표시를 띄운다
    const back = api.takeApproved();
    if (back.length) setTimeout(() => { if (!visible) return; back.forEach((g) => { if (S.gates[g] && S.gates[g].st === 'approved') release(g); }); render(); }, 1100);
  }
  // ---------- 상자 상세: 산출물 하나의 그림·만든 시도·revision·지금 어디로 가는지
  function popOpen(pid) {
    const p = parcels[pid]; if (!p) return;
    pop = { p, ended: null }; lyr.pop.hidden = false; popRender(); popPlace();
  }
  function popClose() { pop = null; lyr.pop.hidden = true; }
  function popEnd(p, why) { if (!pop || pop.p !== p) return; pop.ended = why; popRender(); setTimeout(() => { if (pop && pop.p === p) popClose(); }, 2600); }
  function popRender() {
    const p = pop.p, T = p.rec.slot.T, esc = api.esc, a = S.tasks[T.id].attempts[p.att - 1];
    const to = p.tgt ? p.tgt.to : null;
    const toName = !to ? '' : to === 'pack' ? '캐릭터 포장대' : /^G/.test(to) ? gName(to) : api.task(to).short;
    const where = pop.ended === 'in' ? (to === 'pack' ? '포장대에 들어갔어요 · 출시 묶음에 포함' : '‘' + toName + '’ 작업의 입력으로 들어갔어요')
      : pop.ended === 'kick' ? '버려졌어요 · 다시 만들기로 새 산출물이 나와요'
      : p.tgt && p.tgt.gate && p.u >= p.tgt.u - 0.6 ? toName + ' 결재를 기다리는 중' : '‘' + toName + '’(으)로 가는 중';
    const trig = a && a.trigger ? ({ start: '첫 실행', auto: '자동 재시도', human: '다시 실행', settings: '설정 바꿔 다시 실행', request: '수정 요청 반영', upstream: '앞 작업이 바뀌어 다시' })[a.trigger] : '';
    html(lyr.pop, (p.un.th ? '<span class="pp-img' + (p.un.video ? ' is-video' : '') + '"><img src="' + api.A(p.un.th) + '" alt="">' + (p.un.video ? '<i>' + api.icon('play') + p.un.video + '</i>' : '') + '</span>' : '')
      + '<span class="pp-body"><span class="pp-k">' + esc(api.team(T.team).name) + ' · ' + esc(T.short) + '</span><b>' + esc(p.un.label) + '</b>'
      + '<span class="pp-meta"><code>' + esc(p.rev) + '</code> 시도 #' + p.att + (trig ? ' · ' + esc(trig) : '') + ' · ' + api.hm(p.born) + ' 생성' + (p.un.count > 1 ? ' · ' + p.un.count.toLocaleString('en-US') + '개 묶음' : '') + '</span>'
      + (a && a.memo && a.trigger === 'request' ? '<q>' + esc(a.memo) + '</q>' : '')
      + '<span class="pp-where' + (pop.ended ? ' is-end' : '') + '">' + esc(where) + '</span>'
      + '<span class="pp-act"><button type="button" class="btn btn--sm" data-task="' + T.id + '">작업 상세</button><button type="button" class="btn btn--sm fb-x" data-pp-close aria-label="닫기">' + api.icon('x') + '</button></span></span>');
  }
  function popPlace() {
    if (!pop || pop.ended) return;
    const r = root.getBoundingClientRect(), b = pop.p.g.getBoundingClientRect();
    if (!b.width) return;
    const w = lyr.pop.offsetWidth, h = lyr.pop.offsetHeight;
    let x = b.left - r.left + b.width / 2 - w / 2, y = b.top - r.top - h - 14;
    if (y < 8) y = b.bottom - r.top + 14;
    x = Math.max(8, Math.min(r.width - w - 8, x));
    lyr.pop.style.transform = 'translate(' + Math.round(x) + 'px,' + Math.round(y) + 'px)';
    lyr.pop.classList.toggle('is-below', y > b.top - r.top);
  }
  // ---------- 포커스(따라가기): 작업 하나와 그 앞뒤 의존만 밝히고, 지금 일이 일어나는 곳으로 카메라가 따라간다
  const isG = (x) => /^G/.test(x);
  const okN = (x) => (isG(x) ? S.gates[x].st === 'approved' : S.tasks[x].st === 'done');
  const busyN = (x) => (isG(x) ? S.gates[x].st === 'pending' : ['running', 'blocked'].includes(S.tasks[x].st));
  const nameN = (x) => (isG(x) ? x + ' ' + api.gate(x).title : api.task(x).short);
  function hood(id) {
    const nodes = new Set([id]), edges = [];
    const add = (a, b) => { nodes.add(a); nodes.add(b); edges.push([a, b]); };
    const nd = (g) => api.gate(g).needs || [];
    if (isG(id)) { api.gate(id).after.forEach((a) => add(a, id)); nd(id).forEach((n) => add(n, id)); api.TASKS.filter((t) => t.deps.includes(id)).forEach((t) => add(id, t.id)); api.GATES.filter((g) => nd(g.id).includes(id)).forEach((g) => add(id, g.id)); }
    else {
      api.task(id).deps.forEach((d) => { add(d, id); if (isG(d)) { api.gate(d).after.forEach((a) => add(a, d)); nd(d).forEach((n) => add(n, d)); } });
      api.TASKS.filter((t) => t.deps.includes(id)).forEach((t) => add(id, t.id));
      api.GATES.filter((g) => g.after.includes(id)).forEach((g) => { add(id, g.id); api.TASKS.filter((t) => t.deps.includes(g.id)).forEach((t) => add(g.id, t.id)); });
    }
    const E = edges.filter(([a, b]) => where[a] && where[b]);
    const reach = (from, dir) => { const out = new Set(), q = [from]; while (q.length) { const x = q.shift(); E.forEach((e) => { const [a, b] = dir ? e : [e[1], e[0]]; if (a === x && !out.has(b)) { out.add(b); q.push(b); } }); } return [...out]; };
    return { nodes: new Set([...nodes].filter((x) => where[x])), edges: E, ups: reach(id, false), downs: reach(id, true) };
  }
  const nodePt = (x, lift = 0) => { const w = where[x]; return P(w.sl.x, w.L.Y, (w.sl.type === 'task' ? 5.4 : 6.5) + lift); };
  const toStage = (q) => [((q[0] - vb.x) / vb.w) * stage.clientWidth, ((q[1] - vb.y) / vb.h) * stage.clientHeight];
  let H = null;
  function setFocus(id) {
    focus = id && where[id] ? id : null; follow = true;
    lyr.arcs.innerHTML = ''; arcs = [];
    lanes.forEach((L) => L.slots.forEach((sl) => [sl.st, sl.lab, sl.gf, sl.gb, sl.nm, sl.chip].forEach((n) => { if (n) n.classList.remove('in-chain', 'is-target'); })));
    lanes.forEach((L) => L.lab.classList.remove('in-chain'));
    root.classList.toggle('is-focus', !!focus);
    if (!focus) { popClose(); chain = new Set(); H = null; lyr.fbar.hidden = true; camKey = ''; applyCam(1, 0, 0); return; }
    H = hood(focus); chain = H.nodes;
    chain.forEach((x) => { const w = where[x]; [w.sl.st, w.sl.lab, w.sl.gf, w.sl.gb, w.sl.nm, w.sl.chip].forEach((n) => { if (n) n.classList.add('in-chain'); }); w.L.lab.classList.add('in-chain'); });
    const w0 = where[focus]; [w0.sl.st, w0.sl.gf].forEach((n) => { if (n) n.classList.add('is-target'); });
    H.edges.forEach(([a, b]) => {
      const p0 = nodePt(a), p1 = nodePt(b), cross = where[a].L !== where[b].L;
      const mx = (p0[0] + p1[0]) / 2, my = Math.min(p0[1], p1[1]) - (cross ? 34 + Math.abs(p1[0] - p0[0]) * 0.12 : 16);
      const path = el('path', { class: 'arc' + (cross ? ' is-cross' : ''), d: 'M' + r1(p0[0]) + ' ' + r1(p0[1]) + ' Q' + r1(mx) + ' ' + r1(my) + ' ' + r1(p1[0]) + ' ' + r1(p1[1]) }, lyr.arcs);
      const dot = el('circle', { class: 'arc-end', cx: r1(p1[0]), cy: r1(p1[1]), r: 3.5 }, lyr.arcs);
      arcs.push({ a, b, path, dot });
    });
    lyr.fbar.hidden = false;
    render();
  }
  // 지금 일이 일어나는 곳: 고른 작업이 일하면 그 작업, 기다리면 앞 작업, 끝났으면 그 결과를 쓰는 뒤 작업
  function camNode() {
    if (busyN(focus)) return { id: focus, rel: 'self' };
    const list = okN(focus) ? H.downs : H.ups;
    const b = list.find(busyN);
    return b ? { id: b, rel: okN(focus) ? 'down' : 'up' } : { id: focus, rel: 'self' };
  }
  function applyCam(k, tx, ty) {
    camK = k; const v = 'translate(' + r1(tx) + 'px,' + r1(ty) + 'px) scale(' + k.toFixed(3) + ')';
    if (cam.style.transform !== v) { cam.style.transform = v; cam.style.setProperty('--ik', (1 / k).toFixed(4)); }
  }
  // render가 매 프레임 class를 다시 쓰므로 앞뒤 작업 표시는 그 뒤에 다시 붙인다
  function applyChain() {
    chain.forEach((x) => { const w = where[x]; [w.sl.st, w.sl.lab, w.sl.gf, w.sl.gb, w.sl.nm, w.sl.chip].forEach((n) => { if (n) n.classList.add('in-chain'); }); w.L.lab.classList.add('in-chain'); });
    const w0 = where[focus]; [w0.sl.st, w0.sl.gf].forEach((n) => { if (n) n.classList.add('is-target'); });
  }
  function updateFocus() {
    if (!focus) return;
    applyChain();
    arcs.forEach((x) => { const c = 'arc' + (where[x.a].L !== where[x.b].L ? ' is-cross' : '') + (okN(x.a) && okN(x.b) ? ' is-done' : okN(x.a) ? ' is-live' : ''); if (x.path.getAttribute('class') !== c) x.path.setAttribute('class', c); });
    const cn = camNode(), W = stage.clientWidth, Hh = stage.clientHeight;
    if (follow) {
      const a = toStage(nodePt(focus)), b = toStage(nodePt(cn.id));
      const bw = Math.abs(a[0] - b[0]) + 260, bh = Math.abs(a[1] - b[1]) + 200;
      const top = lyr.fbar.offsetHeight + 20, avail = Hh - top;
      const k = Math.max(1, Math.min(1.6, (W * 0.9) / bw, (avail * 0.9) / bh));
      const cx = (a[0] + b[0]) / 2, cy = (a[1] + b[1]) / 2 + 20;
      const tx = Math.min(0, Math.max(W - W * k, W / 2 - cx * k)), ty = Math.min(top * 0.9, Math.max(Hh - Hh * k, top + avail / 2 - cy * k));
      const key = k.toFixed(2) + ':' + Math.round(tx / 4) + ':' + Math.round(ty / 4);
      if (key !== camKey) { camKey = key; applyCam(k, tx, ty); }
    } else if (camKey !== 'free') { camKey = 'free'; applyCam(1, 0, 0); }
    // 따라가기 막대
    const esc = api.esc, ST = api.ST;
    const T = isG(focus) ? null : api.task(focus), G = isG(focus) ? api.gate(focus) : null;
    const kind = T ? ST.pill('task', taskKey(T), null, 'sm') : ST.pill('gate', S.gates[focus].st, null, 'sm');
    let now;
    if (cn.rel === 'self') {
      if (T && S.tasks[focus].st === 'running') now = esc(stepOf(T, S.tasks[focus]).line);
      else if (G && S.gates[focus].st === 'pending') now = '결재를 기다려요 · ' + api.dur$(S.t - S.gates[focus].since) + '째';
      else if (T && S.tasks[focus].st === 'done') now = '끝났어요 · 결과를 쓰는 작업도 모두 끝났거나 아직 시작 전이에요';
      else now = '앞 작업이 끝나면 시작해요';
    } else now = '<span class="fb-cam">' + api.icon('aperture') + (cn.rel === 'up' ? '기다리는 앞 작업' : '결과를 쓰는 뒤 작업') + '</span><b>' + esc(nameN(cn.id)) + '</b>' + (isG(cn.id) ? ' · 결재 대기' : S.tasks[cn.id].st === 'running' ? ' · ' + esc(stepOf(api.task(cn.id), S.tasks[cn.id]).line) : '');
    const ups = H.ups.filter((x) => !isG(x) || true).map((x) => '<span class="' + (okN(x) ? 'is-ok' : busyN(x) ? 'is-busy' : '') + '">' + esc(nameN(x)) + '</span>').join('');
    const downs = H.downs.map((x) => '<span class="' + (okN(x) ? 'is-ok' : busyN(x) ? 'is-busy' : '') + '">' + esc(nameN(x)) + '</span>').join('');
    html(lyr.fbar, '<div class="fb-top"><span class="fb-k">따라가는 중</span><b>' + esc(T ? T.short : G.code + ' ' + G.title) + '</b>' + kind + '<span class="fb-sub">' + esc(T ? api.team(T.team).name + ' · ' + T.stage + ' · ' + T.agent : api.team(G.team).name + ' · 사람 결재') + '</span>'
      + '<span class="fb-act"><button type="button" class="btn btn--sm" data-fb="' + (follow ? 'look' : 'follow') + '">' + (follow ? '전체 둘러보기' : '추적 중인 작업으로') + '</button><button type="button" class="btn btn--sm" data-fb="detail">상세</button><button type="button" class="btn btn--sm fb-x" data-fb="close" aria-label="따라가기 끝내기 (Esc)">' + api.icon('x') + '</button></span></div>'
      + '<div class="fb-now">' + now + '</div>'
      + '<div class="fb-rel"><span class="fb-rk">앞</span>' + (ups || '<span>없음</span>') + '<span class="fb-rk">뒤</span>' + (downs || '<span>없음</span>') + '</div>'
      );
  }
  function onBar(e) {
    const b = e.target.closest('[data-fb]'); if (!b) return;
    const a = b.dataset.fb;
    if (a === 'look') { follow = false; updateFocus(); }
    else if (a === 'follow') { follow = true; camKey = ''; updateFocus(); }
    else if (a === 'detail') api.openDrawer(isG(focus) ? { gate: focus } : { task: focus });
    else if (a === 'close') setFocus(null);
  }
  // 겹침 정리: 라인 이름과 포장대 카드는 고정, 결재 표시는 위로, 작업대 라벨은 아래로 비켜 연결선으로 잇는다.
  // 기준 위치는 transform 영향이 없는 offset 값으로 재서 매 프레임 같은 답을 낸다.
  // 겹침 정리. 고정 요소(피드·범례·라인 이름·포장대·결재 표시) → 일하는 칩 → 관문 이름 → 작업대 이름 순으로 자리를 잡는다.
  // 일하는 칩과 관문 이름은 자기 라인 안에만 둔다. 작업대 이름만 한 줄 아래·위로 비킬 수 있다. 기준 위치는 transform과 무관한 offset 값이다
  function unstack() {
    const hit = (a, b) => a.l < b.r + 4 && a.r > b.l - 4 && a.t < b.b + 3 && a.b > b.t - 3;
    const hitN = (a, b) => a.l < b.r + 2 && a.r > b.l - 2 && a.t < b.b + 1 && a.b > b.t - 1;
    const hard = [], soft = [];
    const ovR = ov.getBoundingClientRect();
    const loc = (r) => ({ l: (r.left - ovR.left) / camK, r: (r.right - ovR.left) / camK, t: (r.top - ovR.top) / camK, b: (r.bottom - ovR.top) / camK });
    [lyr.feed$, lyr.legend].concat(lyr.fbar.hidden ? [] : [lyr.fbar]).forEach((n) => hard.push(loc(n.getBoundingClientRect())));
    hard.push(loc(lyr.g9.getBoundingClientRect()));
    lanes.forEach((L) => { const n = L.lab, w = n.offsetWidth, h = n.offsetHeight; hard.push({ l: n.offsetLeft - w, r: n.offsetLeft, t: n.offsetTop - h / 2, b: n.offsetTop + h / 2 }); });
    { const n = lyr.card, h = n.offsetHeight; hard.push({ l: n.offsetLeft + 18, r: n.offsetLeft + 18 + n.offsetWidth, t: n.offsetTop - h / 2, b: n.offsetTop + h / 2 }); }
    const chips = [], labs = [], small = [];
    lanes.forEach((L) => L.slots.forEach((sl) => {
      if (sl.type === 'gate') { const on = sl.chip.classList.contains('is-pending') || sl.chip.classList.contains('is-released'); chips.push({ sl, n: sl.chip, i: L.i, x: sl.x, on }); if (!on) small.push({ sl, n: sl.nm, i: L.i, x: sl.x, g: 1 }); }
      else if (/k-(working|retry|human|paused)/.test(sl.lab.className)) labs.push({ sl, n: sl.lab, i: L.i, x: sl.x });
      else small.push({ sl, n: sl.lab, i: L.i, x: sl.x, g: 0 });
    }));
    // 결재 표시·승인 문구: 관문 오른쪽으로 펼치고, 막히면 왼쪽으로. 화면 위쪽 밖으로는 올리지 않는다
    chips.filter((c) => c.on).sort((a, b) => b.i - a.i || a.x - b.x).forEach((c) => {
      const n = c.n, w = n.offsetWidth, h = n.offsetHeight, bt = n.offsetTop - 6, maxLift = Math.max(0, bt - h - 4);
      const fit = (l) => { let lift = 0; for (let k = 0; k < 8; k++) { const box = { l, r: l + w, t: bt - h - lift, b: bt - lift }; const o = hard.find((p) => hit(box, p)); if (!o) return { lift, ok: true }; lift = bt - o.t + 6; if (lift > maxLift) return { lift: maxLift, ok: false }; } return { lift: Math.min(lift, maxLift), ok: false }; };
      const lR = n.offsetLeft - 6, lL = n.offsetLeft + 6 - w;
      const R = fit(lR), Lf = fit(lL), right = lR + w <= ov.clientWidth - 4 && (R.ok && (!Lf.ok || R.lift <= Lf.lift + 24) || !Lf.ok && R.lift <= Lf.lift);
      const lift = right ? R.lift : Lf.lift, l = right ? lR : lL;
      hard.push({ l, r: l + w, t: bt - h - lift, b: bt - lift });
      if (c.sl.lift !== lift) { c.sl.lift = lift; n.style.setProperty('--lift', lift + 'px'); }
      if (!!c.sl.left !== !right) { c.sl.left = !right; }
      n.classList.toggle('is-left', !right);
    });
    const keep = (sl) => sl.spot || (focus && chain.has(sl.id));
    // 관문 이름표는 기호만 남은 상태에서도 전체 이름의 폭·높이로 잰다(줄어든 크기로 재면 펼침·줄임을 매 프레임 되풀이한다)
    const fullBox = (c) => { const n = c.n, key = n.innerHTML; if (c.sl.fwKey !== key) { const m = n.classList.contains('is-mini'); if (m) n.classList.remove('is-mini'); c.sl.fw = n.offsetWidth; c.sl.fh = n.offsetHeight; if (m) n.classList.add('is-mini'); c.sl.fwKey = key; } return c.sl; };
    const rect = (c, sx, row) => { const n = c.n, g = c.sl.type === 'gate' ? fullBox(c) : null, w = g ? g.fw : n.offsetWidth, h = g ? g.fh : n.offsetHeight, l0 = n.offsetLeft - w / 2, t0 = n.offsetTop + (c.sl.type === 'task' ? 5 : 4); const t = row === 1 ? t0 + lowPx : row === -1 ? n.offsetTop - (c.sl.type === 'task' ? hiPx : gHiPx) - h : t0; return { l: l0 + sx, r: l0 + sx + w, t, b: t + h }; };
    const clear = (b) => !hard.some((p) => hit(b, p)) && !soft.some((p) => hitN(b, p));
    const set = (c, p, hid) => { c.sx = p[0]; c.low = p[1] === 1; c.high = p[1] === -1; c.hid = hid; };
    // 일하는 칩: 작업대 바로 앞, 막히면 옆으로. 숨기지 않는다
    labs.sort((a, b) => a.i - b.i || a.x - b.x).forEach((c) => {
      const cands = [[0, 0], [-14, 0], [14, 0], [-28, 0], [28, 0], [-42, 0], [42, 0]];
      const p = cands.find(([sx, row]) => clear(rect(c, sx, row))) || [0, 0];
      set(c, p, false); hard.push(rect(c, p[0], p[1]));
    });
    // 이름표: 라인 안 왼쪽부터. 작업대는 옆 → 한 줄 아래 → 위, 관문은 옆 → 차단기 바로 위(표지판 자리). 관문은 다음 라인 쪽으로 내리지 않는다
    small.sort((a, b) => a.i - b.i || a.x - b.x).forEach((c) => {
      const row0 = [[0, 0], [-12, 0], [12, 0]], up = [[0, -1], [-12, -1], [12, -1]];
      const cands = c.g ? row0.concat(up) : row0.concat(lowOK ? [[0, 1], [-12, 1], [12, 1]] : [], up);
      const p = cands.find(([sx, row]) => clear(rect(c, sx, row)));
      // 관문 이름이 들어갈 자리가 없으면 차단기 기호만 남긴다(이름은 마우스를 올리면 보인다)
      let mini = false, mp = null;
      if (!p && c.g && !keep(c.sl)) { const n = c.n, l0 = n.offsetLeft, t0 = n.offsetTop + 4, h = n.offsetHeight; mp = [0, -10, 10].map((sx) => ({ l: l0 - 11 + sx, r: l0 + 11 + sx, t: t0, b: t0 + fullBox(c).fh, sx })).find((b) => clear(b)); mini = !!mp; }
      set(c, p || [mp ? mp.sx : 0, 0], !p && !mini && !keep(c.sl)); c.mini = mini;
      if (p) soft.push(rect(c, p[0], p[1])); else if (mp) soft.push(mp);
    });
    labs.concat(small).forEach((c) => {
      const n = c.n;
      if (c.sl.drop) { c.sl.drop = 0; n.style.setProperty('--drop', '0px'); n.classList.remove('is-dropped', 'is-up'); }
      if (c.sl.hid !== c.hid) { c.sl.hid = c.hid; n.classList.toggle('is-hidden', c.hid); }
      if (c.sl.low !== c.low) { c.sl.low = c.low; n.classList.toggle('is-low', c.low); }
      if (c.sl.high !== c.high) { c.sl.high = c.high; n.classList.toggle('is-high', c.high); }
      if (c.sl.sx !== c.sx) { c.sl.sx = c.sx; n.style.setProperty('--sx', c.sx + 'px'); }
      if (!!c.sl.mini !== !!c.mini) { c.sl.mini = !!c.mini; n.classList.toggle('is-mini', !!c.mini); }
    });
  }
  // ---------- 결재 승인 순간: 이 결재로 실제로 시작할 수 있게 된 작업(나머지 의존도 모두 끝난 것)과 열리는 관문만 잇는다
  function release(gid) {
    const { tasks, gates } = api.unlockedBy(gid);
    const targets = tasks.concat(gates).filter((x) => where[x]);
    if (!targets.length || !where[gid]) return;
    const esc = api.esc, until = performance.now() + RELMS;
    const teams = [...new Set(targets.map((x) => (isG(x) ? api.gate(x).team : api.task(x).team)))].map((t) => api.team(t).name);
    const names = targets.map((x) => (isG(x) ? api.team(api.gate(x).team).name + ' ' + gName(x) + ' 결재' : api.team(api.task(x).team).name + ' ' + api.task(x).short));
    if (rels[gid] && rels[gid].g) rels[gid].g.remove();
    const g = el('g', { class: 'rel' }, lyr.rel);
    targets.forEach((x, k) => {
      const p0 = nodePt(gid), p1 = nodePt(x), cross = where[gid].L !== where[x].L;
      const mx = (p0[0] + p1[0]) / 2, my = Math.min(p0[1], p1[1]) - (cross ? 30 + Math.abs(p1[0] - p0[0]) * 0.1 : 18);
      el('path', { class: 'rel-arc', pathLength: '1', style: '--d:' + k * 110 + 'ms', d: 'M' + r1(p0[0]) + ' ' + r1(p0[1]) + ' Q' + r1(mx) + ' ' + r1(my) + ' ' + r1(p1[0]) + ' ' + r1(p1[1]) }, g);
      el('circle', { class: 'rel-end', cx: r1(p1[0]), cy: r1(p1[1]), r: 9, style: '--d:' + k * 110 + 'ms' }, g);
      where[x].sl.unl = until;
    });
    rels[gid] = { gid, targets, until, g, title: gName(gid) + ' 승인으로 시작: ' + names.join(', '),
      html: '<span class="fg-ok">' + api.icon('check') + '</span><b>' + esc(gName(gid)) + '</b><span class="fg-to">→ ' + esc(teams.join(' · ')) + ' 시작</span>' };
  }
  // ---------- 지금 일하는 에이전트: 바닥은 '어디서', 이 목록은 '무엇을'. 라인 순서대로 쌓고, 줄에 올리면 작업대와 라인이 밝아진다
  const crewRows = {};
  function renderCrew() {
    const act = [], esc = api.esc;
    lanes.forEach((L) => L.slots.forEach((sl) => { if (sl.type === 'task' && /^(working|retry|human|paused)$/.test(prevKey[sl.id] || '')) act.push({ sl, L }); }));
    const nRun = act.filter((x) => prevKey[x.sl.id] !== 'human').length, nTxt = nRun ? String(nRun) : '';
    if (lyr.crewN.textContent !== nTxt) lyr.crewN.textContent = nTxt;
    const ids = new Set(act.map((x) => x.sl.id));
    Object.keys(crewRows).forEach((id) => { if (!ids.has(id)) { crewRows[id].remove(); delete crewRows[id]; } });
    act.forEach(({ sl, L }, idx) => {
      let li = crewRows[sl.id];
      if (!li) {
        li = document.createElement('li'); li.dataset.task = sl.id; li.dataset.li = L.i; li.tabIndex = 0; li.setAttribute('role', 'button');
        li.innerHTML = '<span class="cw-a">' + api.icon(L.tm.icon) + '<span class="cw-t">' + esc(L.tm.name) + '</span><b>' + esc(sl.T.short) + '</b></span><span class="cw-p num"></span><span class="cw-b"><b>' + esc(ROLE[sl.T.agent] || sl.T.agent) + '</b><small>' + esc(sl.T.agent) + '</small><span class="cw-now"></span></span>';
        crewRows[sl.id] = li;
      }
      if (lyr.crew.children[idx] !== li) lyr.crew.insertBefore(li, lyr.crew.children[idx] || null);
      const cls = 'k-' + prevKey[sl.id] + (sl.hot ? ' is-hot' : '');
      if (li.className !== cls) li.className = cls;
      const cw = sl.cw || { prog: '', line: '' }, p = li.querySelector('.cw-p'), w = li.querySelector('.cw-now');
      if (p.textContent !== cw.prog) p.textContent = cw.prog;
      if (w.textContent !== cw.line) w.textContent = cw.line;
    });
    const empty = act.length ? '' : !S.running ? '시작하면 일하는 에이전트가 여기에 나와요' : S.finished ? '모든 작업이 끝났어요' : S.paused ? '일시정지 중이에요' : '지금은 사람 결재를 기다리고 있어요';
    if (lyr.crewEmpty.textContent !== empty) lyr.crewEmpty.textContent = empty;
    lyr.crewEmpty.hidden = !empty;
  }
  function setHot(id) {
    lanes.forEach((L) => L.slots.forEach((sl) => { if (sl.type !== 'task') return; const h = sl.id === id; if (!!sl.hot !== h) { sl.hot = h; sl.lab.classList.toggle('is-hot', h); sl.st.classList.toggle('is-hot', h); if (crewRows[sl.id]) crewRows[sl.id].classList.toggle('is-hot', h); } }));
  }
  let fed = false;
  function hide() { visible = false; fed = false; relSeen = false; if (tip) tip.hidden = true; if (lyr.pop) popClose(); if (gIdx >= 0) guide(false); }
  function fit() {
    const r = root.getBoundingClientRect();
    const ratio = vb.w / vb.h;
    let w = r.width - 16, h = w / ratio;
    if (h > r.height - 12) { h = r.height - 12; w = h * ratio; }
    const k = Math.round(w) + 'x' + Math.round(h);
    if (k !== size) { size = k; stage.style.width = Math.round(w) + 'px'; stage.style.height = Math.round(h) + 'px'; }
  }

  // ---------- 라인 강조
  function setHL(i, strong) {
    if (gIdx >= 0) return;
    if (focus) i = null;
    const v = i == null ? '' : String(i), w = strong ? v : '';
    if (root.dataset.hlw !== v) root.dataset.hlw = v;
    if (root.dataset.hl !== w) root.dataset.hl = w;
  }
  // ---------- 구성 보기: 발표자가 공장 요소 다섯 가지를 실제 화면 위에서 하나씩 짚는다
  const GUIDE = [
    { k: 'lane', t: '라인 = 팀', d: '팀 하나가 라인 하나예요. 일은 왼쪽에서 오른쪽으로 흘러요. 앞 단계 결과가 준비된 라인부터 동시에 움직여요.' },
    { k: 'station', t: '작업대 = 작업 하나', d: 'AI 에이전트가 작업대에서 작업 하나씩 처리해요. 일하는 동안 이름 옆에 진행이 뜨고, 지금 하는 일은 ‘지금 일하는 에이전트’ 목록에 나와요.' },
    { k: 'gate', t: '차단기 = 사람 결재', d: '사람이 고르거나 승인해야 열려요. 결재를 기다리는 곳은 모래색으로 표시돼요.' },
    { k: 'box', t: '상자 = 산출물', d: '작업대가 만든 결과물이에요. 벨트를 타고 그 결과를 쓰는 다음 작업대나 결재로 가요.', d0: '작업대가 일을 끝내면 여기서 결과물 상자가 나와, 벨트를 타고 다음 작업대나 결재로 가요.' },
    { k: 'pack', t: '포장대 = 캐릭터', d: '모든 라인의 산출물이 여기 모여 캐릭터 한 명이 돼요. 마지막에 사람이 출시를 승인해요.' }
  ];
  function guide(on) {
    if (!built) return;
    if (on) {
      if (focus) setFocus(null);
      popClose(); tip.hidden = true; setHot(null);
      api.freeze(true);
      gIdx = 0; gA = GUIDE.map((g) => guideAnchor(g.k)); lyr.guide.hidden = false; root.classList.add('is-guide');
      lyr.gdPanel.dataset.step = ''; guideRender();
      const nx = lyr.gdPanel.querySelector('[data-gd-next]'); if (nx) nx.focus({ preventScroll: true });
    } else {
      gIdx = -1; gA = null; lyr.guide.hidden = true; root.classList.remove('is-guide'); root.dataset.hl = ''; root.dataset.hlw = '';
      api.freeze(false);
    }
  }
  function gStep(d) {
    const n = gIdx + d;
    if (n >= GUIDE.length) { guide(false); return; }
    gIdx = Math.max(0, n); guideRender();
    const nx = lyr.gdPanel.querySelector('[data-gd-next]'); if (nx) nx.focus({ preventScroll: true });
  }
  function guideAnchor(k) {
    const busy = lanes.find((L) => L.run) || lanes[1];
    const find = (ok) => { let r = null; lanes.forEach((L) => L.slots.forEach((x) => { if (!r && ok(x)) r = x; })); return r; };
    if (k === 'lane') return { n: busy.band, n2: busy.lab, li: busy.i, side: 'left', band: true };
    if (k === 'station') { const sl = find((x) => x.type === 'task' && /st-(working|retry|human)/.test(x.st.getAttribute('class'))) || where.v2.sl; return { n: sl.st, n2: sl.lab.classList.contains('is-hidden') ? null : sl.lab }; }
    if (k === 'gate') { const sl = find((x) => x.type === 'gate' && S.gates[x.id].st === 'pending') || where.G4.sl; return { n: sl.gf, n2: sl.chip.classList.contains('is-pending') ? sl.chip : sl.nm }; }
    if (k === 'box') { const p = Object.values(parcels).find((q) => !q.dead && !q.inCol); if (p) return { n: p.g }; const sl0 = busy.slots.find((x) => x.type === 'task'); return { pt: P(sl0.x + 6, busy.Y, 1), empty: true }; }
    return { n: lyr.pack, n2: lyr.card };
  }
  function guideRender() {
    if (gIdx < 0) return;
    const R = root.getBoundingClientRect();
    const box$ = (n) => { const b = n.getBoundingClientRect(); return { l: b.left - R.left, t: b.top - R.top, r: b.right - R.left, b: b.bottom - R.top }; };
    const marks = GUIDE.map((g, i) => {
      const a = gA[i];
      let b;
      if (a.n) { b = box$(a.n); if (a.n2) { const c = box$(a.n2); b = { l: Math.min(b.l, c.l), t: Math.min(b.t, c.t), r: Math.max(b.r, c.r), b: Math.max(b.b, c.b) }; } }
      else { const s = stage.getBoundingClientRect(), q = toStage(a.pt), x = s.left - R.left + q[0], y = s.top - R.top + q[1]; b = { l: x - 10, t: y - 8, r: x + 10, b: y + 8 }; }
      return { a, b, cx: (b.l + b.r) / 2, cy: (b.t + b.b) / 2 };
    });
    const cur = marks[gIdx];
    // 라인 단계는 라인 띠 전체를 타원으로, 나머지는 원으로 비춘다
    const rad = Math.min(150, Math.max(40, Math.hypot(cur.b.r - cur.b.l, cur.b.b - cur.b.t) / 2 + 14));
    const rx = cur.a.band ? (cur.b.r - cur.b.l) / 2 + 12 : rad, ry = cur.a.band ? (cur.b.b - cur.b.t) / 2 + 10 : rad;
    lyr.guide.style.setProperty('--gx', Math.round(cur.cx) + 'px');
    lyr.guide.style.setProperty('--gy', Math.round(cur.cy) + 'px');
    lyr.guide.style.setProperty('--grx', Math.round(rx) + 'px');
    lyr.guide.style.setProperty('--gry', Math.round(ry) + 'px');
    const li = GUIDE[gIdx].k === 'lane' ? String(cur.a.li) : '';
    // 라인 단계는 어둡게 덮지 않고, 그 라인 띠를 밝히고 다른 라인을 흐린다(타원은 비스듬한 띠 옆 라인까지 비췄다)
    lyr.guide.classList.toggle('is-lane', GUIDE[gIdx].k === 'lane');
    root.dataset.hl = li; root.dataset.hlw = li;
    marks.forEach((m, i) => {
      const n = lyr.gdMarks[i];
      const lb = m.a.side === 'left' && m.a.n2 ? box$(m.a.n2) : null;
      const x = lb ? lb.l - 16 : m.cx, y = lb ? (lb.t + lb.b) / 2 : m.b.t - 14;
      n.style.left = Math.round(x) + 'px'; n.style.top = Math.round(Math.max(14, y)) + 'px';
      n.className = 'gd-mk num' + (i === gIdx ? ' is-on' : i < gIdx ? ' is-seen' : '');
    });
    // 안내 창은 비추는 곳의 반대쪽 아래에 둔다
    const side = cur.cx > R.width * 0.55 ? 'left' : 'right';
    lyr.gdPanel.classList.toggle('is-left', side === 'left');
    if (lyr.gdPanel.dataset.step !== String(gIdx)) {
      lyr.gdPanel.dataset.step = String(gIdx);
      const esc = api.esc;
      lyr.gdPanel.innerHTML = '<div class="gd-head"><b>캐릭터 공장 읽는 법</b><span class="gd-n num">' + (gIdx + 1) + ' / ' + GUIDE.length + '</span><button type="button" class="btn btn--sm fb-x" data-gd-close aria-label="안내 닫기 (Esc)">' + api.icon('x') + '</button></div>'
        + '<ol class="gd-list">' + GUIDE.map((g, i) => '<li class="' + (i === gIdx ? 'is-on' : i < gIdx ? 'is-seen' : '') + '"><i class="num">' + (i + 1) + '</i><span><b>' + esc(g.t) + '</b>' + (i === gIdx ? '<small>' + esc(g.d0 && gA[i].empty ? g.d0 : g.d) + '</small>' : '') + '</span></li>').join('') + '</ol>'
        + '<div class="gd-act"><span class="gd-k">→ 다음 · ← 이전 · Esc 닫기</span><button type="button" class="btn btn--sm" data-gd-prev' + (gIdx ? '' : ' disabled') + '>이전</button><button type="button" class="btn btn--primary btn--sm" data-gd-next>' + (gIdx === GUIDE.length - 1 ? '끝내기' : '다음') + '</button></div>';
    }
  }
  document.addEventListener('keydown', (e) => {
    if (gIdx < 0) return;
    if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'Enter') { e.preventDefault(); gStep(1); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); gStep(-1); }
    else if (e.key === 'Escape') { e.preventDefault(); guide(false); }
  });

  // ---------- 작업대 툴팁
  function tipHTML(id) {
    const T = api.task(id), s = S.tasks[id], k = taskKey(T), esc = api.esc, fc = api.forecast();
    const time = s.st === 'queued' ? api.hm(fc.start[id]) + ' 시작 예정' : s.st === 'done' ? api.hm(s.start) + ' – ' + api.hm(s.end) : api.hm(s.start) + ' 시작 · ' + Math.round(s.p * 100) + '%';
    return '<span class="ft-k">' + esc(api.team(T.team).name) + ' · ' + T.stage + ' · ' + esc(T.agent) + '</span><b>' + esc(T.short) + '</b>'
      + api.ST.pill('task', k, null, 'sm') + '<span class="ft-m">' + esc(T.model) + '<br>' + time + (s.st === 'done' ? '<br>' + esc(T.out) : '') + '</span><span class="ft-h">누르면 앞뒤 작업을 따라가요 · 한 번 더 누르면 상세</span>';
  }
  function onFocus(e) {
    const n = e.target.closest && e.target.closest('[data-floor-task]'); if (!n) return;
    html(tip, tipHTML(n.dataset.floorTask)); tip.hidden = false;
    const r = root.getBoundingClientRect(), b = n.getBoundingClientRect();
    let x = b.right - r.left + 10, y = b.top - r.top;
    if (x + 230 > r.width) x = b.left - r.left - 240;
    if (y + 140 > r.height) y = r.height - 150;
    tip.style.transform = 'translate(' + x + 'px,' + y + 'px)';
  }
  // 결재함·문제 카드의 '현장에서 보기': 해당 작업대나 관문에 고리를 세 번 띄운다
  function spot(id) {
    let anchor = null, sl = null;
    lanes.forEach((L) => L.slots.forEach((x) => { if (x.id === id) sl = x; }));
    if (sl) { sl.spot = true; anchor = sl.type === 'task' ? sl.st : sl.gf; }
    else if (id === 'G9') { lyr.g9spot = true; anchor = lyr.pack; }
    if (!anchor) return;
    render();
    const r = ov.getBoundingClientRect(), b = anchor.getBoundingClientRect();
    const ring = document.createElement('span'); ring.className = 'fl-spot';
    ring.style.left = (b.left + b.width / 2 - r.left) / camK + 'px'; ring.style.top = (b.top + b.height / 2 - r.top) / camK + 'px';
    ov.appendChild(ring);
    setTimeout(() => { ring.remove(); if (sl) sl.spot = false; lyr.g9spot = false; }, 2800);
  }
  function stepInfo(id) {
    const T = api.task(id), s = api.S.tasks[id], d = STEP[id];
    if (!T || !(s.st === 'running' || s.st === 'blocked')) return null;
    const tiles = id === 'v4' ? api.frames() : (d && d.tiles) || [];
    const on = tileOn(T, s, tiles.length, true);
    return { line: stepOf(T, s).line, tiles, on, n: on.filter(Boolean).length };
  }
  // 검증용: 벨트 위 상자가 어디로 가고 있는지
  function routes() {
    const out = [];
    lanes.forEach((L) => L.slots.forEach((sl) => { if (sl.type === 'task') pk[sl.id].list.forEach((p) => { if (!p.dead && p.tgt) out.push({ src: sl.id, to: p.tgt.to }); }); }));
    return out;
  }
  function onOver(e) { const n = e.target.closest('[data-floor-task]'); if (!n) { tip.hidden = true; return; } html(tip, tipHTML(n.dataset.floorTask)); tip.hidden = false; onMove(e); }
  function onMove(e) {
    if (tip.hidden) return;
    const r = root.getBoundingClientRect();
    let x = e.clientX - r.left + 16, y = e.clientY - r.top + 14;
    if (x + 230 > r.width) x -= 250;
    if (y + 140 > r.height) y -= 150;
    tip.style.transform = 'translate(' + x + 'px,' + y + 'px)';
  }

  window.CF_FLOOR = {
    attach(a, node) { api = a; root = node; },
    render, tick, hide, spot, step: stepInfo, routes,
    focus(id) { if (!built) return; if (gIdx >= 0) guide(false); setFocus(id); }, focused: () => focus,
    guide(on) { guide(on); }, guiding: () => gIdx >= 0,
    parcels: () => Object.values(parcels).filter((p) => !p.dead).map((p) => ({ pid: p.pid, task: p.rec.slot.id, label: p.un.label, inChain: !!p.inC })), openParcel: popOpen,
    resize() { size = ''; },
    releases: () => Object.values(rels).map((r) => ({ gate: r.gid, targets: r.targets.slice(), arcs: r.g.querySelectorAll('.rel-arc').length, chip: (where[r.gid].sl.chip.textContent || '') }))
  };
  window.addEventListener('resize', () => { size = ''; });
})();

