(function (global) {
  'use strict';

  // 캐릭터 공장 진행 화면(D-0101). 서버 기록만 읽는다. 가짜 진행·가짜 시간·자동 승인은 만들지 않는다.
  const R = (typeof module !== 'undefined' && module.exports) ? require('./runtime.js') : global.FactoryRuntime;
  const E = R.escapeHTML;
  const Ref = (typeof module !== 'undefined' && module.exports) ? require('./reference.js') : global.ReferencePreview;

  // 팀 줄(서버 LANES id) → 그래프 칸. 위 줄은 외모 → 장면 → 영상, 아래 줄은 기획 → 페르소나 → 데이터 → 학습, 패키지는 오른쪽.
  // 모티브는 맨 앞 열에 출처 팀(so)이 생긴다.
  const AREA = { source: 'so', appearance: 'ap', plan: 'pl', scene: 'sc', video: 'vd', persona: 'ps', data: 'dt', training: 'tr', release: 'pk' };
  const CELL = { ap: [0, 0], sc: [0, 1], vd: [0, 2], pl: [1, 0], ps: [1, 1], dt: [1, 2], tr: [1, 3], pk: [0.5, 4] };
  // 그래프 칸 배치. 오리지널은 CELL 그대로다. 모티브는 출처 팀이 맨 앞 열(두 줄 가운데)에 서고 나머지는 한 열씩 밀린다.
  // 학습하지 않는 방식이면 데이터 팀이 그래프에서 빠지고 그 열도 없어져 학습(평가) 팀이 당겨진다.
  function layoutOf(graph) {
    const has = (id) => (graph && graph.lanes || []).some((l) => l.id === id && (l.stages || []).length);
    if (!has('source')) return { cls: '', cell: CELL };
    const noData = !has('data');
    const cell = { so: [0.5, 0] };
    Object.keys(CELL).forEach((a) => {
      if (noData && a === 'dt') return;
      const c = CELL[a];
      cell[a] = [c[0], c[1] + 1 - (noData && c[1] >= 3 ? 1 : 0)];
    });
    return { cls: noData ? 'tw nt' : 'tw', cell };
  }
  // 갈래·모델 준비 방식 표시(D-0128, D-0118). 코드 값은 화면에 보이지 않는다.
  const MODE_LABEL = { TRAIN: '학습', BIND_EXISTING: '학습된 모델 연결', PROMPT_ONLY: '프롬프트만' };
  function trackLabel(c) {
    const x = c || {};
    if (x.origin !== 'SOURCE') return '오리지널';
    return (x.originLabel || '모티브') + ' · ' + (MODE_LABEL[x.modelMode] || MODE_LABEL.TRAIN);
  }
  // 모티브 단계 줄에 붙이는 쉬운 설명. 단계 이름은 서버 그래프를 그대로 쓴다.
  const TWIN_HINT = { s2: '받은 사진에서 기준 사진 고르기', s8c: '선택한 장면을 정하고 장면마다 대화 표본을 만들어요' };
  // S8c(챕터 시작 설정)는 사람 검토 없이 도는 단계다. 화면 이름은 시작 장면을 따른다(계획 2차 약속 2).
  function s8cName(origin, template) {
    if (template === 'FRIEND_CHAT') return '친구 대화 장면';
    if (template === 'INTERVIEW') return '인터뷰 장면';
    if (template) return template === 'FAN_CALL' ? '팬 통화 장면' : '통화 장면';
    return origin === 'SOURCE' ? '첫 통화 장면' : '통화 장면';
  }
  // 대화할 수 있는지(3차 약속 3). 서버가 대화 화면과 같은 함수로 계산한 chatReady를 그대로 따른다.
  // 서버가 아직 싣지 않으면 대화 화면의 준비 조건(프롬프트 S8과 첫 장면 S8c가 모두 있음)을 단계 기록으로 본다.
  function isChatReady(detail) {
    const d = detail || {};
    if (typeof d.chatReady === 'boolean') return d.chatReady;
    if (d.origin !== 'SOURCE' || !d.id) return false;
    const rows = rowsById(d);
    const made = (id) => upper((rows.get(id) || {}).status) === 'APPROVED';
    return made('s8') && made('s8c');
  }
  // 대화해 보기 주소. 대화할 수 있을 때만 연다(대화 화면에서 막히는 버튼을 보이지 않는다).
  function chatHref(detail) {
    const d = detail || {};
    return d.id && isChatReady(d) ? 'chat.html#c/' + encodeURIComponent(d.id) : '';
  }
  // 영상 등급(계획 4차 약속 5). 원문 화면(sources.js)과 같은 표·같은 카드다(시험이 같은지 본다). 화면에는 개수를 쓰지 않는다.
  const VIDEO_TIERS = [
    ['none', '영상 없이', '대화만 만들어요. 영상 비용이 들지 않아요.', 0],
    ['light', '라이트', '대기·말하기·파이팅·웃음·인사와 시그니처를 만들어요.', 1],
    ['standard', '스탠다드', '대화에서 자주 쓰는 감정까지 만들어요.', 2],
    ['pro', '프로', '더 섬세한 감정까지 만들어요.', 3],
    ['max', '맥스', '앱에서 쓰는 반응 전부예요. 가장 오래 걸리고 비용도 가장 커요.', 4]
  ];
  const COST_WORD = ['없음', '적음', '보통', '많음', '가장 많음'];
  function tierOf(value) { return VIDEO_TIERS.some((t) => t[0] === value) ? value : 'none'; }
  function tierName(value) { return VIDEO_TIERS.find((t) => t[0] === tierOf(value))[1]; }
  function tierCardsHTML(name, value, opts) {
    const o = opts || {};
    const cur = tierOf(value);
    return VIDEO_TIERS.filter((t) => !(o.paidOnly && t[0] === 'none')).map((t) => {
      // 시간·비용 네 칸. '영상 없이'는 설명이 비용 없음을 말하므로 칸을 두지 않는다.
      const meter = t[3] ? '<span class="vt-cost" role="img" aria-label="시간·비용 ' + COST_WORD[t[3]] + '">' + [1, 2, 3, 4].map((n) => '<i' + (n <= t[3] ? ' class="on"' : '') + '></i>').join('') + '</span>' : '';
      return '<label class="vt-opt"><input type="radio" name="' + E(name) + '" value="' + t[0] + '"' + (t[0] === cur ? ' checked' : '') + (o.disabled ? ' disabled' : '') + '><span class="vt-tx"><span class="vt-top"><b>' + t[1] + '</b>' + meter + '</span><small>' + t[2] + '</small></span></label>';
    }).join('');
  }
  // 영상 상태 한 줄(원문 화면과 같은 규칙). 상태를 알면 등급 이름을 붙여 쓰고, 영상이 없으면 빈칸이다(머리·목록에 아무것도 붙이지 않는다).
  // 모르는 상태일 때만 서버 videoLabel을 쓴다.
  function videoText(c) {
    const x = c || {};
    const tier = tierOf(x.videoTier);
    const st = text(x.videoStatus);
    if (st === 'failed') return '영상을 만들지 못했어요';
    if (st === 'making') return '영상 만드는 중 · ' + tierName(tier);
    if (st === 'ready') return '영상 있음 · ' + tierName(tier);
    if (st === 'none' || !text(x.videoLabel).trim()) return tier === 'none' ? '' : '영상 기다리는 중 · ' + tierName(tier);
    return text(x.videoLabel).trim();
  }
  // 작업 오류를 사람 말로: 앞의 예외 이름을 떼고, 이름뿐인 오류는 그렇다고 적는다.
  function plainError(raw) {
    const s = text(raw).replace(/^[A-Za-z_]*(Error|Exception|Iteration): ?/, '').trim();
    // 'StopIteration'처럼 예외 이름만 있으면 사람에게 뜻이 없다.
    return (!s || /^[A-Za-z_]+$/.test(s) ? '알 수 없는 오류가 났어요.' : s).slice(0, 200);
  }
  function videoTone(c) { return { making: 'run', ready: 'ok', failed: 'fail' }[text(c && c.videoStatus)] || ''; }
  // 영상 만들기를 건넬 캐릭터: 대화 가능하고, 영상이 아직 없거나 실패했고, 도는 작업이 없을 때. 영상 상태를 주지 않는 서버면 건네지 않는다.
  function canMakeVideo(detail) {
    const d = detail || {};
    // 영상이 있어도 등급·시그니처를 바꿀 수 있다. 같은 몸짓은 옮겨 오고 새 영상만 만든다(D-0166).
    return isChatReady(d) && !d.job && ['none', 'failed', 'ready'].includes(d.videoStatus);
  }
  // 원문 초안(GET /api/sources/{id})에서 준비된 사진 수. 사진 기록은 fileType "photo"(없는 서버면 확장자)로 알아본다.
  function readyPhotos(draft) {
    return ((draft && draft.files) || []).filter((f) => {
      const t = text(f && f.fileType);
      const photo = t ? t === 'photo' : /\.(jpe?g|png|webp)$/i.test(text(f && f.filename));
      return photo && f.status === 'ready';
    }).length;
  }
  // 캐릭터 상태는 모든 화면이 같은 낱말을 쓴다(3차 약속 3). 서버 status·statusLabel이 먼저이고,
  // 없을 때만 이 화면이 가진 기록으로 같은 규칙을 따라 정한다. done은 끝까지 마친 오리지널 캐릭터에만 쓴다.
  const STATUS_LABEL = { draft: '시작 전', running: '만드는 중', needs_review: '확인 필요', chat_ready: '대화 가능', failed: '실패', stopped: '멈춤', done: '완료' };
  const STATUS_TONE = { draft: 'muted', running: 'run', needs_review: 'wait', chat_ready: 'ok', failed: 'fail', stopped: 'muted', done: 'ok' };
  const STATUS_RANK = { needs_review: 0, failed: 1, running: 2, chat_ready: 3, draft: 4, stopped: 5, done: 6 };
  // 시연 모드(모든 검토 자동 승인 → 테스터 전용 발행)는 상태 낱말 뒤에 붙인다. 품질 검토가 아니다.
  const DEMO_LABEL = { ready: '시연 모드', publishing: '시연 · 테스터 발행 중', published: '시연 · 테스터 발행됨', publish_failed: '시연 · 발행 실패', budget: '시연 · 예산 상한', stopped: '시연 · 멈춤', failed: '시연 · 멈춤', packaged: '시연 · 패키지 완료' };
  function statusOf(c, sum) {
    const x = c || {};
    const s = sum || {};
    let st = STATUS_LABEL[x.status] ? x.status : '';
    if (!st) st = s.running ? 'running' : s.fail ? 'failed' : (s.review || s.paid) ? 'needs_review' : isChatReady(x) ? 'chat_ready' : s.complete ? 'done' : s.fresh ? 'draft' : 'stopped';
    const demo = x.demo && x.demo.enabled ? (DEMO_LABEL[x.demo.phase] || DEMO_LABEL.ready) : '';
    const label = (text(x.statusLabel).trim() || STATUS_LABEL[st]) + (demo ? ' · ' + demo : '');
    return { status: st, label, tone: STATUS_TONE[st] || 'muted', rank: STATUS_RANK[st] == null ? 9 : STATUS_RANK[st] };
  }
  // 목표 경로: 모티브는 대화 가능까지 필요한 단계만(첫 장면 S8c, 없으면 프롬프트 S8의 앞 단계들). 학습 방식이면 학습 단계까지 더한다.
  // 오리지널은 목표 경로를 따로 두지 않는다(null).
  function goalStages(graph, detail) {
    const d = detail || {};
    if (!graph || (d.origin || graph.origin) !== 'SOURCE') return null;
    const end = graph.byStage.has('s8c') ? 's8c' : graph.byStage.has('s8') ? 's8' : '';
    if (!end) return null;
    const set = ancestors(graph, end);
    if ((d.modelMode || graph.modelMode) === 'TRAIN' && graph.byStage.has('s10t')) ancestors(graph, 's10t').forEach((id) => set.add(id));
    return set;
  }
  // 진행 숫자. 서버 goal {label, done, total}이 있으면 그대로, 없으면 목표 경로(오리지널은 전체 단계)로 센다.
  function goalOf(graph, detail, views) {
    const ids = goalStages(graph, detail);
    const g = detail && detail.goal;
    if (g && Number(g.total) > 0) return { label: text(g.label).trim() || (ids ? '대화 제작 단계' : '전체'), done: Number(g.done) || 0, total: Number(g.total), ids };
    const list = ids ? Array.from(ids) : (graph ? graph.stages.map((s) => s.id) : []);
    const done = list.filter((id) => ['done', 'skip'].includes(((views || {})[id] || {}).kind)).length;
    return { label: ids ? '대화 제작 단계' : '전체', done, total: list.length, ids };
  }
  // 모티브 그래프 접기: 목표 경로 단계와 지금 일이 걸린(실행·대기·실패·비용 확인) 단계만 남기고 나머지는 숨긴다.
  // keep이 null이면 전부 보인다(오리지널이거나 사람이 펼쳤을 때). hidden은 접었을 때 숨는 단계 수다.
  const ACTIVE_KINDS = ['run', 'retry', 'wait', 'confirm', 'fail'];
  function goalView(graph, detail, views, showOff) {
    const ids = goalStages(graph, detail);
    if (!ids) return { ids: null, keep: null, hidden: 0 };
    const keep = new Set();
    graph.stages.forEach((s) => { if (ids.has(s.id) || ACTIVE_KINDS.includes(((views || {})[s.id] || {}).kind)) keep.add(s.id); });
    const hidden = graph.stages.length - keep.size;
    return { ids, keep: showOff ? null : keep, hidden };
  }
  // 이름이 같은 캐릭터는 만든 날짜·시간으로 구분한다. 시간이 없거나 그래도 같으면 짧은 이름을 덧붙인다.
  function pad2(n) { return String(n).padStart(2, '0'); }
  // 만든 시각: 서버 createdAt → 첫 실행 시각 → ID의 날짜(시각 없음) 순.
  function createdOf(c) {
    const x = c || {};
    const t = parseTime(x.createdAt);
    if (t != null) return { t, time: true };
    const starts = (x.stages || []).map((s) => parseTime(s.startedAt)).filter((v) => v != null);
    if (starts.length) return { t: Math.min.apply(null, starts), time: true };
    const m = /^cf-(\d{4})(\d{2})(\d{2})-/.exec(text(x.id));
    return m ? { t: new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])).getTime(), time: false } : { t: 0, time: false };
  }
  function createdLabel(c) {
    const w = createdOf(c);
    if (!w.t) return '';
    const d = new Date(w.t);
    return (d.getMonth() + 1) + '/' + d.getDate() + (w.time ? ' ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes()) : '');
  }
  function labelOf(c) {
    const x = c || {};
    return displayName(x.displayName || (x.persona && x.persona.name) || x.name, x.id);
  }
  function nameLabels(list) {
    const groups = new Map();
    (list || []).forEach((c) => { const n = labelOf(c); if (!groups.has(n)) groups.set(n, []); groups.get(n).push(c); });
    const out = new Map();
    groups.forEach((cs, n) => {
      const whens = cs.map(createdLabel);
      cs.forEach((c, i) => {
        let note = '';
        if (cs.length > 1) {
          note = whens[i] ? whens[i] + ' 만듦' : '';
          if (!whens[i] || whens.filter((w) => w === whens[i]).length > 1) note = (note ? note + ' · ' : '') + text(c.id).replace(/^cf-\d{8}-/, '');
        }
        out.set(c.id, { name: n, note });
      });
    });
    return out;
  }
  // 새로 지어내는 캐릭터의 짧은 이름은 자동으로 만든다(브리프 속 영문 낱말 + 시각). 직접 정하는 칸은 고급 설정으로 접는다.
  function autoSlug(brief, now) {
    const words = (text(brief).toLowerCase().match(/[a-z0-9]+/g) || []).slice(0, 2).join('-').slice(0, 24);
    return (words ? words : 'char') + '-' + Math.floor(Number(now || Date.now())).toString(36).slice(-5);
  }
  // 회차 기록: 마지막에 성공한 단계라면 그 전에 실패한 시도는 따로 접어 둔다.
  function splitAttempts(hist, succeeded) {
    const all = Array.isArray(hist) ? hist : [];
    if (!succeeded) return { shown: all, earlier: [] };
    const lastOk = all.map((a) => Boolean(a.result) && a.result !== 'CHECK_FAILED' && a.result !== 'RESTARTED').lastIndexOf(true);
    if (lastOk < 0) return { shown: all, earlier: [] };
    const earlier = all.filter((a, i) => i < lastOk && (a.result === 'CHECK_FAILED' || a.result === 'RESTARTED'));
    return { shown: all.filter((a) => earlier.indexOf(a) < 0), earlier };
  }
  // 단계 이름 뒤 표시(사람 검토·유료 아이콘)는 마지막 낱말에 붙인다. 칸이 좁아도 아이콘만 다음 줄로 떨어지지 않는다.
  function stageNameHTML(name, marks) {
    const s = String(name == null ? '' : name);
    if (!marks) return E(s);
    const i = s.lastIndexOf(' ');
    return E(s.slice(0, i + 1)) + '<span class="nb">' + E(s.slice(i + 1)) + marks + '</span>';
  }
  const DEMO_NOTE = 'AI 생성 · 본인과 무관한 기술 시연';
  const KIND_LABEL = { done: '완료', run: '진행 중', retry: '다시 시도 중', wait: '검토 대기', confirm: '실행 확인 대기', fail: '멈춤', todo: '예정', out: '이번 실행 범위 밖', skip: '건너뜀' };
  const ICON = {
    check: '<polyline points="20 6 9 17 4 12"/>',
    x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    coins: '<circle cx="12" cy="12" r="8"/><path d="M12 8v8M9.5 10h4a1.5 1.5 0 0 1 0 3h-3a1.5 1.5 0 0 0 0 3h4"/>',
    retry: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><polyline points="3 3 3 8 8 8"/>',
    down: '<polyline points="6 9 12 15 18 9"/>',
    up: '<polyline points="18 15 12 9 6 15"/>',
    spark: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>',
    ok: '<circle cx="12" cy="12" r="9"/><polyline points="8 12 11 15 16 9"/>',
    factory: '<path d="M3 21V9l6 4V9l6 4V5h6v16z"/>',
    minus: '<line x1="6" y1="12" x2="18" y2="12"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    monitor: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5h13L22 12v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-6z"/>',
    plus: '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    close: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    expand: '<polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/>',
    shrink: '<polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="14" y1="10" x2="21" y2="3"/><line x1="3" y1="21" x2="10" y2="14"/>',
    grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
    chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
    gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    more: '<circle cx="5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="19" cy="12" r="1.2"/>',
    archive: '<rect x="3" y="4" width="18" height="4" rx="1"/><path d="M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8"/><line x1="10" y1="12" x2="14" y2="12"/>',
    video: '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3z"/>'
  };
  // 브랜드 마크: 보라 둥근 사각형 안의 F와 불꽃 점(D-0102).
  const MARK = '<svg class="fd-mark" viewBox="0 0 24 24" aria-hidden="true"><rect width="24" height="24" rx="6" fill="var(--fd-accent)"/><path d="M8.5 17V7h7.5M8.5 12h5" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="16.4" cy="16.4" r="1.7" fill="#fff"/></svg>';
  function icon(name, label) {
    return '<svg class="i" viewBox="0 0 24 24"' + (label ? ' role="img" aria-label="' + E(label) + '"' : ' aria-hidden="true"') + '>' + ICON[name] + '</svg>';
  }

  function text(value) { return value == null ? '' : String(value); }

  // 실패 이유: 서버 원문(개발자용)을 한 줄 요약으로 바꾸고 원문은 기술 정보로 남긴다.
  function failReason(raw) {
    const s = text(raw).trim();
    if (!s) return { summary: '실패 이유가 기록되지 않았어요. 실행 기록을 확인하세요.', detail: '' };
    const fmt = s.match(/형식 실패\s*(\d+)회/);
    if (fmt) return { summary: '모델 답이 정해진 형식과 맞지 않았어요. 마지막 실행 안에서 모델에 ' + fmt[1] + '번 다시 물었지만 맞지 않았어요.', detail: s };
    if (/검사 실패|check failed/i.test(s)) {
      const first = s.split(/\n-\s*|;\s*/).map((x) => x.trim()).filter((x) => x && !/검사 실패|check failed/i.test(x))[0] || '';
      const plain = first.replace(/^[A-Za-z0-9_.[\]]+:\s*/, '');
      return { summary: '자동 검사를 통과하지 못했어요' + (plain ? ': ' + plain.slice(0, 90) : '.'), detail: s };
    }
    if (/timeout|timed out|시간 초과/i.test(s)) return { summary: '응답이 제한 시간 안에 오지 않았어요.', detail: s };
    if (/connect|connection|network|연결/i.test(s)) return { summary: '공급자에 연결하지 못했어요.', detail: s };
    if (/budget|예산/i.test(s)) return { summary: '정해 둔 호출 예산을 넘어 멈췄어요.', detail: s };
    if (/TaintedOutputError|작업 공간 밖/.test(s)) return { summary: '작업 공간 밖의 파일을 건드리려 해서 멈췄어요.', detail: s };
    // 'SomethingError: …' 같은 개발자용 오류 이름은 그대로 보이지 않는다. 원문은 기술 정보에 남는다.
    if (/^[A-Za-z_.]*(Error|Exception)\b/.test(s)) return { summary: '실행 중에 오류가 나서 멈췄어요. 자세한 내용은 기술 정보에 있어요.', detail: s };
    const line = s.split('\n')[0];
    return { summary: line.length > 120 ? line.slice(0, 117) + '…' : line, detail: line === s && line.length <= 120 ? '' : s };
  }
  function upper(value) { return text(value).trim().toUpperCase(); }

  // ---- 시간 ----
  function parseTime(value) {
    const t = Date.parse(text(value));
    return Number.isFinite(t) ? t : null;
  }
  function span(ms) {
    const minutes = Math.max(0, Math.floor(ms / 60000));
    if (minutes < 1) return '1분 미만';
    if (minutes < 60) return minutes + '분';
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return h + '시간' + (m ? ' ' + m + '분' : '');
  }
  function since(value, now) {
    const t = parseTime(value);
    if (t == null) return '';
    const ms = now - t;
    return ms < 60000 ? '방금' : span(ms) + '째';
  }
  function clock(value) {
    const t = parseTime(value);
    if (t == null) return '';
    const d = new Date(t);
    return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
  }

  // ---- 그래프 ----
  function predecessors(graph) {
    const preds = new Map(graph.stages.map((s) => [s.id, new Set()]));
    graph.stages.forEach((s) => {
      s.deps.forEach((g) => { const owner = graph.byGate.get(g); if (owner && owner.stage && owner.stage !== s.id) preds.get(s.id).add(owner.stage); });
      s.needs.concat(s.after).forEach((a) => { if (preds.has(a) && a !== s.id) preds.get(s.id).add(a); });
    });
    return preds;
  }
  function successors(graph) {
    const succ = new Map(graph.stages.map((s) => [s.id, new Set()]));
    predecessors(graph).forEach((set, b) => set.forEach((a) => succ.get(a).add(b)));
    return succ;
  }
  function reach(map, start) {
    const seen = new Set();
    const queue = [start];
    while (queue.length) {
      const id = queue.shift();
      (map.get(id) || new Set()).forEach((n) => { if (!seen.has(n)) { seen.add(n); queue.push(n); } });
    }
    return seen;
  }
  function descendants(graph, id) { return reach(successors(graph), id); }
  function ancestors(graph, target) {
    const owner = graph.byGate.get(target);
    const stage = owner && owner.stage ? owner.stage : target;
    if (!graph.byStage.has(stage)) return new Set();
    const set = reach(predecessors(graph), stage);
    set.add(stage);
    return set;
  }
  // 바로 이어지는 선만 남긴다. 다른 길로도 닿는 선(a→c, a→b→c)은 지운다.
  function reducedEdges(graph) {
    const succ = successors(graph);
    const out = [];
    succ.forEach((targets, a) => {
      targets.forEach((b) => {
        let indirect = false;
        targets.forEach((m) => { if (!indirect && m !== b && reach(succ, m).has(b)) indirect = true; });
        if (!indirect) out.push([a, b]);
      });
    });
    return out;
  }
  function laneMap(graph) {
    const out = new Map();
    graph.lanes.forEach((lane) => (lane.stages || []).forEach((s) => out.set(typeof s === 'string' ? s : s.id, lane.id)));
    return out;
  }
  function crossLaneEdges(graph) {
    const lanes = laneMap(graph);
    return reducedEdges(graph).filter(([a, b]) => lanes.get(a) && lanes.get(b) && lanes.get(a) !== lanes.get(b));
  }

  // ---- 상태 해석 ----
  function rowsById(detail) {
    const map = new Map();
    (detail && Array.isArray(detail.stages) ? detail.stages : []).forEach((row) => map.set(row.id, row));
    return map;
  }
  function gatesById(detail) {
    const map = new Map();
    (detail && Array.isArray(detail.gates) ? detail.gates : []).forEach((row) => map.set(row.id, row));
    return map;
  }
  function stageView(def, row, ctx) {
    if (ctx.scope && !ctx.scope.has(def.id)) return { kind: 'out', sub: '' };
    const status = upper(row && row.status) || 'PENDING';
    const attempts = Number(row && row.attempts) || 0;
    const hist = (ctx.history && ctx.history[def.id]) || [];
    const gate = def.gate ? ctx.gates.get(def.gate) : null;
    const tv = trainingStageView(ctx.training, def.id, status);
    if (tv) return tv;
    if (status === 'APPROVED') return { kind: 'done', sub: '' };
    if (status === 'SKIPPED') return { kind: 'skip', sub: '건너뜀' };
    if (status === 'RUNNING') {
      const t = row && row.startedAt ? since(row.startedAt, ctx.now) : '';
      const prev = hist.length > 1 ? hist[hist.length - 2] : null;
      if (prev && prev.decision === 'REJECTED') return { kind: 'run', sub: '새 버전 만드는 중' };
      if (attempts > 1) return { kind: 'retry', sub: attempts + '회차 진행 중' + (t ? ' · ' + t : ''), retry: true };
      return { kind: 'run', sub: '실행 중' + (t ? ' · ' + t : '') };
    }
    if (status === 'AWAITING_HUMAN') {
      if (gate && upper(gate.status) === 'AWAITING_HUMAN') {
        const t = gate.openedAt ? since(gate.openedAt, ctx.now) + ' ' : '';
        return { kind: 'wait', sub: t + '검토 대기' };
      }
      return { kind: 'done', sub: '' };
    }
    if (status === 'CHECK_FAILED') return { kind: 'fail', sub: (attempts > 1 ? '실행 ' + attempts + '번 실패' : '실패') + ' · 멈춤' };
    if (status === 'REJECTED') return { kind: 'todo', sub: '다시 만들 차례' };
    if (ctx.held && ctx.held.has(def.id)) return { kind: 'confirm', sub: '실행 확인 대기' };
    return { kind: 'todo', sub: '' };
  }
  function viewsFor(graph, detail, options) {
    const opts = options || {};
    const ctx = {
      now: opts.now || Date.now(),
      gates: gatesById(detail),
      history: (detail && detail.history) || {},
      held: new Set(R.extractHeld(detail || {}).map((h) => h.stage)),
      training: trainingOf(detail),
      scope: opts.scope || null
    };
    const rows = rowsById(detail);
    const out = {};
    graph.stages.forEach((def) => { out[def.id] = stageView(def, rows.get(def.id), ctx); });
    return out;
  }
  function laneKind(ids, views) {
    const kinds = ids.map((id) => (views[id] || {}).kind);
    if (!kinds.length) return 'todo';
    if (kinds.every((k) => k === 'skip')) return 'skip';
    if (kinds.every((k) => k === 'out' || k === 'skip')) return 'out';
    if (kinds.some((k) => k === 'wait' || k === 'confirm')) return 'wait';
    if (kinds.some((k) => k === 'fail')) return 'fail';
    if (kinds.some((k) => k === 'run' || k === 'retry')) return 'run';
    if (kinds.every((k) => k === 'done' || k === 'skip')) return 'done';
    return 'todo';
  }
  function edgeClass(graph, views, a, b) {
    const ka = (views[a] || {}).kind;
    const kb = (views[b] || {}).kind;
    if ([ka, kb].some((k) => k === 'out' || k === 'skip')) return 'out';
    if (kb === 'run' || kb === 'retry') return 'flow';
    if (kb === 'todo' || kb === 'confirm') {
      const stops = Object.keys(views).filter((id) => ['wait', 'fail', 'confirm'].includes(views[id].kind));
      for (const s of stops) {
        if (s === b) continue;
        const down = descendants(graph, s);
        if (down.has(b) && (a === s || down.has(a))) return views[s].kind === 'fail' ? 'stop' : 'block';
      }
      if (kb === 'confirm' && ka === 'done') return 'block';
      return 'todo';
    }
    return 'done';
  }

  // ---- 지금 할 일 ----
  function recommendation(view) {
    const review = view && view.review;
    if (!review) return '';
    const picks = (review.items || []).filter((item) => item.verdict === 'RECOMMEND').map((item) => item.candidateId).filter(Boolean);
    if (!picks.length) return '검토 모델 의견이 있어요';
    return '검토 모델 추천: ' + picks.slice(0, 3).join(', ') + (picks.length > 3 ? ' 외 ' + (picks.length - 3) + '개' : '');
  }
  function reworkLine(view) {
    const rw = view && view.rework;
    if (!rw || !rw.maxRounds) return '';
    if (rw.capReached) return '수정 요청 ' + rw.round + '번을 모두 썼어요. 더 고치려면 다시 만들기를 허락해야 해요.';
    if (rw.round > 0) return '수정 ' + rw.round + '번을 반영한 버전이에요. 수정은 ' + rw.maxRounds + '번까지 요청할 수 있어요.';
    return '';
  }
  function remaining(graph, views, id) {
    let n = 0;
    descendants(graph, id).forEach((d) => { const k = (views[d] || {}).kind; if (k && !['done', 'skip', 'out'].includes(k)) n += 1; });
    return n;
  }
  // 이름이 아직 없으면 'cf-20261107-slug' 대신 '이름 미정 · slug (11/07)'로 보인다(D-0129).
  function displayName(name, id) {
    const n = text(name).trim();
    if (n && n !== text(id)) return n;
    const m = /^cf-(\d{4})(\d{2})(\d{2})-(.+)$/.exec(text(id));
    return m ? '이름 미정 · ' + m[4] + ' (' + Number(m[2]) + '/' + Number(m[3]) + ')' : text(id);
  }
  // 판(revision) 코드를 '버전 N'으로(D-0129).
  function revLabel(rev) {
    const m = /^[a-z]+(\d+)$/i.exec(text(rev));
    return m ? '버전 ' + m[1] : text(rev);
  }

  // ---- 모델 만들기(D-0130) ----
  // 학습 상태는 state.json의 s10t가 아니라 학습 기록(modelPath.training)에서 읽는다. 계획만 세운 학습을
  // '완료'로 그리지 않고 '비용 확인 대기'로 보인다.
  const MODEL_STAGES = new Set(['s9s', 's9', 's10t', 's10']);
  function trainingOf(detail) { return (detail && detail.modelPath && detail.modelPath.training) || null; }
  function usd(v) { return v == null || isNaN(Number(v)) ? '—' : '$' + Number(v).toFixed(2); }
  function hoursText(h) {
    if (h == null || isNaN(Number(h))) return '';
    const m = Math.max(1, Math.round(Number(h) * 60));
    return m < 60 ? m + '분' : Math.floor(m / 60) + '시간' + (m % 60 ? ' ' + (m % 60) + '분' : '');
  }
  function trainPhase(tr, key) { return ((tr && tr.phases) || []).find((p) => p.key === key) || null; }
  function gpuAlive(tr) { return ((tr && tr.providers) || []).some((p) => p.gpuAlive); }
  function trainingStageView(tr, id, status) {
    if (!tr) return null;
    if (id === 's10t') {
      const ph = trainPhase(tr, 'train');
      if (tr.state === 'plan') return { kind: 'confirm', sub: '학습 비용 확인 대기' };
      if (tr.state === 'run') return { kind: 'run', sub: tr.stopRequested ? '중단하는 중' : '학습 중' + (ph && ph.status === 'run' && ph.meter != null ? ' · ' + ph.detail : '') };
      if (tr.state === 'hold') return { kind: 'fail', sub: gpuAlive(tr) ? '결과 받기 실패 · GPU 남음' : '결과 받기 실패' };
      if (tr.state === 'stopped') return { kind: 'confirm', sub: '중단함 · 다시 시작 대기' };
      if (tr.state === 'fail') return { kind: 'fail', sub: '학습 실패 · 멈춤' };
      if (tr.state === 'skip') return { kind: 'skip', sub: '학습 없이 진행' };
      return null;
    }
    if (id === 's10' && ['plan', 'stopped', 'fail', 'run', 'hold'].includes(tr.state) && ['PENDING', 'REJECTED'].includes(status)) {
      return { kind: 'todo', sub: tr.state === 'run' ? '학습이 끝나면 열려요' : '학습을 고르면 열려요' };
    }
    return null;
  }
  function trainingTasks(tr, busy, blocked) {
    if (!tr) return [];
    const why = busy ? '지금 작업이 끝나면 할 수 있어요.' : '';
    const dl = ((tr.providers || []).map((p) => p.deadlineAt).filter(Boolean))[0];
    if (tr.state === 'hold') {
      const gpu = gpuAlive(tr);
      return [{
        kind: 'fail', stage: 's10t', order: -1,
        title: gpu ? 'GPU가 남아 있어요' : '학습 결과를 받지 못했어요', age: '학습',
        body: (gpu ? '결과를 받아 오지 못해 GPU를 남겨 뒀어요. 비용이 계속 나가요' + (dl ? ' · ' + clock(dl) + '에 자동 반납' : '') + '.' : '학습은 끝났지만 결과를 받아 오지 못했어요.') + ' 다시 받아 오거나 결과를 버려요.',
        blocked,
        actions: [{ act: 'train-retry', label: '다시 받아 오기', disabled: busy, why }, { act: 'open-model', step: 'train', label: '학습 화면 열기' }]
      }];
    }
    if (['plan', 'stopped', 'fail'].includes(tr.state)) {
      const title = tr.state === 'plan' ? '학습 비용 확인' : tr.state === 'stopped' ? '학습을 중단했어요' : '학습이 실패했어요';
      const est = tr.estimateUsd != null ? '예상 ' + usd(tr.estimateUsd) + (tr.gpuHours ? ' · 약 ' + hoursText(tr.gpuHours) : '') + '. ' : '';
      return [{
        kind: 'confirm', stage: 's10t', order: 2, title, age: '유료 단계',
        body: est + '학습을 시작하거나, 학습 없이 긴 프롬프트로 진행할지 골라요.',
        blocked,
        actions: [{ act: 'mconfirm', v: 'start', step: 'train', label: tr.state === 'plan' ? '학습 시작' : '다시 학습', disabled: busy, why }, { act: 'mconfirm', v: 'skip', step: 'train', label: '학습 없이 진행', disabled: busy }]
      }];
    }
    return [];
  }
  // ---- 모델 준비 갈래의 다음 일(QA v5 B-F06·B-F07) ----
  // 프롬프트를 승인한 뒤의 모델 단계(데이터 샘플·학습 데이터·학습 계획·평가)는 대화 준비 목표 밖이라 저절로 돌지 않는다.
  // 지금 할 일·노드 칸·모델 만들기 탭이 같은 버튼을 건넨다. 버튼은 그 단계의 검토(없으면 단계 자신)까지만 돌린다.
  // 유료 학습은 이 버튼으로 시작하지 않는다(학습 계획까지만). 유료 공급자 단계는 서버가 비용 확인으로 멈춘다.
  const MODEL_RUN_UNTIL = { s9s: 'G7a', s9: 'G7', s10t: 's10t', s10: 'G8' };
  function modelPathOf(detail) { return (detail && detail.modelPath) || {}; }
  function modelModeOf(detail) { return text((detail && detail.modelMode) || modelPathOf(detail).mode) || 'TRAIN'; }
  function modelNext(graph, detail) {
    const d = detail || {};
    if (d.origin !== 'SOURCE' || !graph || modelModeOf(d) === 'PROMPT_ONLY') return null;
    const gates = gatesById(d);
    const gs = (id) => upper((gates.get(id) || {}).status);
    if (gs('G6') !== 'APPROVED' || ['AWAITING_HUMAN', 'APPROVED'].includes(gs('G8'))) return null;
    const rows = rowsById(d);
    const held = new Set(R.extractHeld(d).map((h) => h.stage));
    const ready = (id) => graph.byStage.has(id) && !held.has(id) && ['PENDING', 'REJECTED'].includes(upper((rows.get(id) || {}).status) || 'PENDING');
    const m = modelPathOf(d);
    if (modelModeOf(d) === 'BIND_EXISTING') {
      if (!m.binding) return { stage: 's10', step: 'bind', input: true, title: '연결할 모델을 골라 주세요', body: '학습된 모델을 연결하는 방식이에요. 평가하려면 먼저 이미 학습한 모델의 연결 파일을 올려 주세요.', label: '모델 연결하기' };
      return ready('s10') ? { stage: 's10', step: 'eval', title: '평가를 시작할 수 있어요', body: '긴 프롬프트와 연결한 모델의 답을 원문에서 떼어 둔 장면으로 비교해요.', label: '평가 시작' } : null;
    }
    const tr = m.training || {};
    if (ready('s9s')) return { stage: 's9s', step: 'src', title: '데이터 샘플을 만들 차례예요', body: '프롬프트를 승인했어요. 학습에 쓸 대화 샘플을 만들고, 클러스터마다 샘플을 검토해요.', label: '데이터 샘플 만들기' };
    if (gs('G7a') === 'APPROVED' && ready('s9')) return { stage: 's9', step: 'data', title: '학습 데이터를 만들 차례예요', body: '샘플 검토를 마쳤어요. 같은 기준으로 나머지 학습 데이터를 만들어요.', label: '학습 데이터 만들기' };
    if (gs('G7') === 'APPROVED' && tr.state === 'pending' && graph.byStage.has('s10t')) return { stage: 's10t', step: 'train', title: '학습 계획을 세울 차례예요', body: '계획은 비용이 들지 않아요. 예상 비용·시간을 본 뒤 학습을 시작할지 골라요.', label: '학습 계획 세우기' };
    if (['done', 'skip'].includes(tr.state) && ready('s10')) return { stage: 's10', step: 'eval', title: '평가를 시작할 수 있어요', body: '긴 프롬프트와 학습 모델에 같은 질문을 하고 답을 비교해요.', label: '평가 시작' };
    return null;
  }
  function modelTasks(graph, detail, views, busy) {
    const n = modelNext(graph, detail);
    if (!n) return [];
    const why = busy ? '지금 작업이 끝나면 할 수 있어요.' : '';
    return [{
      kind: 'ready', stage: n.stage, order: 3, title: n.title, age: '모델 만들기', body: n.body,
      blocked: remaining(graph, views, n.stage),
      actions: [n.input ? { act: 'open-model', step: n.step, label: n.label } : { act: 'model-run', stage: n.stage, label: n.label, disabled: busy, why }]
    }];
  }
  // 모델 만들기 탭의 지금 단계와 단계 줄. 연결 방식은 '모델 연결 → 평가' 두 단계만 있다(재료·데이터셋·학습이 없다).
  function modelActive(detail) {
    const m = modelPathOf(detail);
    if (modelModeOf(detail) === 'BIND_EXISTING') return m.binding ? 'eval' : 'bind';
    const t = m.training || {};
    if (['done', 'skip'].includes(t.state)) return 'eval';
    if (['plan', 'run', 'hold', 'stopped', 'fail', 'pending'].includes(t.state)) return 'train';
    return m.dataset ? 'data' : 'src';
  }
  function modelSteps(detail, views) {
    const det = detail || {};
    const m = modelPathOf(det);
    const v = views || {};
    const gates = gatesById(det);
    const gs = (id) => upper((gates.get(id) || {}).status);
    const kind = (id) => (v[id] || {}).kind;
    const bind = modelModeOf(det) === 'BIND_EXISTING';
    const steps = [];
    let open;
    if (bind) {
      const b = m.binding;
      const due = gs('G6') === 'APPROVED';
      steps.push({ id: 'bind', n: 1, ko: '모델 연결', k: b ? 'ok' : due ? 'wait' : 'todo', s: b ? b.kindLabel + ' · ' + text(b.ref) : due ? '연결할 모델을 골라 주세요' : '아직 연결하지 않았어요', done: Boolean(b) && ['AWAITING_HUMAN', 'APPROVED'].includes(gs('G8')) });
      open = Boolean(b);
    } else {
      const mat = m.material;
      let sk = 'todo';
      let ss = '프롬프트를 승인하면 정해요';
      if (mat) { sk = 'ok'; ss = mat.used.map((u) => u.label).join(' + ') || mat.planned.map((p) => p.label).join(' + ') || '정함'; }
      else if (['run', 'retry'].includes(kind('s9s'))) { sk = 'run'; ss = '데이터 샘플 만드는 중'; }
      else if (kind('s9s') === 'fail') { sk = 'fail'; ss = '멈춤'; }
      else if (kind('s9s') === 'confirm') { sk = 'wait'; ss = '실행 확인 대기'; }
      else if (gs('G6') === 'APPROVED') ss = '데이터 샘플을 만들 차례예요';
      steps.push({ id: 'src', n: 1, ko: '재료', k: sk, s: ss, done: Boolean(mat) });
      const d = m.dataset;
      let dk = 'todo';
      let ds = '학습 데이터를 만들기 전이에요';
      if (d) {
        // 숫자는 데이터셋 승인(G7) 요약과 같은 전체 대화 수다(QA v5 C-08). 학습·검증·평가 나눔은 아래 칸에 있다.
        if (upper(d.status) === 'APPROVED') { dk = 'ok'; ds = '대화 ' + d.counts.total + '개 · 승인됨'; }
        else if (upper(d.gates.G7.status) === 'AWAITING_HUMAN') { dk = 'wait'; ds = '데이터셋 승인 대기'; }
        else if (upper(d.gates.G7a.status) === 'AWAITING_HUMAN') { dk = 'wait'; ds = '샘플 검토 대기'; }
        else if (['run', 'retry'].includes(kind('s9'))) { dk = 'run'; ds = '만드는 중'; }
        else if (['run', 'retry'].includes(kind('s9s'))) { dk = 'run'; ds = '샘플 만드는 중'; }
        else if (kind('s9') === 'fail') { dk = 'fail'; ds = '멈춤'; }
        else if (kind('s9') === 'confirm') { dk = 'wait'; ds = '실행 확인 대기'; }
        else ds = gs('G7a') === 'APPROVED' ? '학습 데이터를 만들 차례예요' : '샘플을 다시 만들 차례예요';
      }
      steps.push({ id: 'data', n: 2, ko: '데이터셋', k: dk, s: ds, done: dk === 'ok' });
      const t = m.training || {};
      const tv = v.s10t || {};
      const tk = { confirm: 'wait', run: 'run', fail: 'fail', skip: 'ok', done: 'ok', todo: 'todo', wait: 'wait', retry: 'run', out: 'todo' }[tv.kind] || 'todo';
      // '골랐어요'는 학습 안의 체크포인트 고르기다. 평가(G8)의 채택과 섞이지 않게 쓴다(QA v5 C-08).
      const tsub = t.state === 'done' ? (t.adopted ? '끝남 · 체크포인트 고름' : '끝남 · 쓸 체크포인트 없음') : t.state === 'locked' ? '데이터셋을 승인하면 열려요' : t.state === 'pending' ? '학습 계획을 세울 차례예요' : tv.sub || KIND_LABEL[tv.kind] || '';
      steps.push({ id: 'train', n: 3, ko: '학습', k: tk, s: tsub, done: ['done', 'skip'].includes(t.state) });
      open = ['done', 'skip'].includes(t.state);
    }
    const e = m.eval || {};
    const ev = v.s10 || {};
    let ek = 'todo';
    let es = bind ? '모델을 연결하면 열려요' : '학습이 끝나면 열려요';
    if (open) {
      const g8 = upper(e.gate && e.gate.status);
      if (g8 === 'AWAITING_HUMAN') { ek = 'wait'; es = e.promptOnly ? (bind ? '연결한 모델 채택 검토' : '긴 프롬프트 채택 검토') : '블라인드 20쌍 검토'; }
      else if (g8 === 'APPROVED') { ek = 'ok'; es = e.adopted ? e.adopted.label + '로 채택함' : '채택 결정함'; }
      else if (ev.kind === 'confirm') { ek = 'wait'; es = '평가 비용 확인 대기'; }
      else if (['run', 'retry'].includes(ev.kind)) { ek = 'run'; es = '답 모으는 중'; }
      else if (ev.kind === 'fail') { ek = 'fail'; es = '멈춤'; }
      else es = '평가를 시작할 차례예요';
    }
    steps.push({ id: 'eval', n: steps.length + 1, ko: '평가', k: ek, s: es, done: ek === 'ok' });
    return steps;
  }
  // 'video: xai_video/grok-video' 같은 공급자 표기를 쉬운 말로(D-0129).
  const KIND_KO = { video: '영상', image: '이미지', text: '글', judge: '검토' };
  const ADAPTER_KO = { xai_video: 'xAI 그록 영상', grok: '그록(계정 연결 우선)', grok_oauth: '그록(계정 연결)', grok_web: '그록 웹', fake_video: '시험용 가짜 영상', fake: '시험용 가짜 모델', fake_image: '시험용 가짜 이미지', codex_image: 'Codex 이미지', openai: 'OpenAI', gemini: 'Gemini', vertex_gemini: 'Vertex Gemini' };
  function providerKo(p) {
    const m = /^(?:(\w+):\s*)?([\w-]+)(?:\/(.+))?$/.exec(text(p).trim());
    if (!m) return text(p);
    const name = ADAPTER_KO[m[2]] || m[2];
    return (m[1] && KIND_KO[m[1]] ? KIND_KO[m[1]] + ' · ' : '') + name + (m[3] ? ' (' + m[3] + ')' : '');
  }

  function buildTasks(graph, detail, views, options) {
    const opts = options || {};
    const now = opts.now || Date.now();
    const gateViews = opts.gateViews || new Map();
    const busy = Boolean(opts.jobActive);
    const rows = rowsById(detail);
    const items = [];
    const tr = trainingOf(detail);
    graph.stages.forEach((def) => {
      if ((views[def.id] || {}).kind !== 'fail') return;
      if (def.id === 's10t' && tr && ['hold', 'fail'].includes(tr.state)) return; // 학습 항목이 따로 알린다
      const row = rows.get(def.id) || {};
      items.push({
        kind: 'fail', stage: def.id, order: 0,
        title: def.name + ' 단계가 멈췄어요',
        age: '실행 ' + (Number(row.attempts) || 1) + '번 실패',
        body: failReason(row.lastError).summary + ((Number(row.attempts) || 1) >= 2
          ? ' 같은 실패가 반복되고 있어요. 다시 실행하기 전에 오류 내용을 복사해 운영 담당에게 보내 주세요.'
          : ' 다시 실행하면 이 단계부터 목표까지 이어서 진행해요.'),
        blocked: remaining(graph, views, def.id),
        actions: ((Number(row.attempts) || 1) >= 2 ? [{ act: 'copy-error', stage: def.id, label: '오류 내용 복사' }, { act: 'help', anchor: 'stuck', label: '막혔을 때 안내' }] : [])
          .concat([{ act: 'retry', stage: def.id, label: '다시 실행', disabled: busy, why: busy ? '지금 작업이 끝나면 다시 실행할 수 있어요.' : '' }])
      });
    });
    if (upper((rows.get('s8') || {}).status) === 'REJECTED') {
      items.push({ kind: 'ready', stage: 's8', order: 1, blocked: 0,
        title: '말투와 성격을 다시 만들 차례예요', body: '고칠 점을 반영한 뒤 새 버전을 승인하면 대화할 수 있어요.',
        actions: [{ act: 'run-stage', stage: 's8', label: '프롬프트 다시 만들기', disabled: busy }] });
    }
    R.pendingGatesFor(detail || {}, graph).forEach((pending) => {
      const gateRow = gatesById(detail).get(pending.id) || {};
      const stage = pending.stage;
      const def = graph.byStage.get(stage);
      const view = gateViews.get(pending.id + '|' + text(gateRow.rev));
      const lines = [(def ? def.name : stage) + ' 결과를 보고 고르거나 승인하세요.'];
      const rw = reworkLine(view);
      if (rw) lines.push(rw);
      items.push({
        kind: 'wait', stage, gate: pending.id, order: 1, openedAt: gateRow.openedAt || null,
        title: pending.title || pending.id,
        age: gateRow.openedAt ? since(gateRow.openedAt, now) + ' 대기' : '',
        body: lines.join(' '),
        rec: recommendation(view),
        blocked: stage ? remaining(graph, views, stage) : 0,
        actions: [{ act: 'review', gate: pending.id, stage, label: '검토하기' }]
      });
    });
    trainingTasks(tr, busy, graph.byStage.has('s10t') ? remaining(graph, views, 's10t') : 0).forEach((item) => items.push(item));
    const modelItems = modelTasks(graph, detail, views, busy);
    modelItems.forEach((item) => items.push(item));
    const covered = new Set(modelItems.map((item) => item.stage));
    R.extractHeld(detail || {}).forEach((held) => {
      const def = graph.byStage.get(held.stage);
      items.push({
        kind: 'confirm', stage: held.stage, order: 2,
        title: (def ? def.name : held.stage) + ' 실행 확인',
        age: '유료 단계',
        body: '쓰는 곳: ' + (held.providers.length ? held.providers.map(providerKo).join(', ') : '유료 공급자') + '. 예상 비용을 확인한 뒤 실행해요. 실행하면 이 단계만 돌아요.',
        blocked: remaining(graph, views, held.stage),
        actions: [{ act: 'confirm', stage: held.stage, label: '비용 확인', disabled: busy, why: busy ? '지금 작업이 끝나면 확인할 수 있어요.' : '' }]
      });
    });
    // 마지막 작업이 단계 밖에서 실패하면 노드는 그대로라 이유가 안 보인다(QA v5 C-01·F05). 이유를 한 줄로 알린다.
    const failedJob = (detail && detail.lastJob) || {};
    if (!busy && failedJob.status === 'failed' && failedJob.error && !graph.stages.some((def) => (views[def.id] || {}).kind === 'fail')) {
      items.push({
        kind: 'fail', order: 0,
        title: '마지막 작업이 멈췄어요',
        body: plainError(failedJob.error) + ' 원인을 고친 뒤 이어서 실행해 주세요.',
        blocked: 0,
        actions: [{ act: 'resume', label: '이어서 실행' }]
      });
    }
    // 앞 단계가 모두 끝났는데 도는 작업이 없으면 공정이 조용히 멈춘다. 이어서 실행할 수 있다고 알린다.
    if (!busy && opts.goal) {
      const preds = predecessors(graph);
      const scope = ancestors(graph, opts.goal);
      // 서버가 마지막 작업에서 시작할 수 없다고 남긴 단계(그래프 밖 규칙: 외모 축은 s2 승인 뒤 기획 등)는 빼서 거짓 안내를 막는다.
      const lastJob = (detail && detail.lastJob) || {};
      const blockedByServer = new Set(Array.isArray(lastJob.blocked) ? lastJob.blocked : []);
      const ready = graph.stages.filter((def) => {
        if ((views[def.id] || {}).kind !== 'todo' || !scope.has(def.id) || blockedByServer.has(def.id) || covered.has(def.id)) return false;
        return Array.from(preds.get(def.id) || []).every((p) => ['done', 'skip'].includes((views[p] || {}).kind));
      });
      if (ready.length) {
        items.push({
          kind: 'ready', order: 3,
          title: '이어서 실행할 수 있어요',
          body: ready.map((def) => def.name).join(', ') + ' 단계는 앞 단계가 끝났지만 지금 도는 작업이 없어요. 이어서 실행하면 목표까지 진행해요.',
          blocked: 0,
          actions: [{ act: 'resume', label: '이어서 실행' }]
        });
      }
    }
    items.sort((x, y) => x.order - y.order || y.blocked - x.blocked || (parseTime(x.openedAt) || 0) - (parseTime(y.openedAt) || 0));
    items.forEach((item, i) => item.actions.forEach((a, j) => { a.pri = i === 0 && j === 0; }));
    return items;
  }

  // ---- 바뀐 점 알림 ----
  function diffNotes(graph, prev, next, now) {
    if (!prev || !next || prev.id !== next.id) return [];
    const notes = [];
    const pg = gatesById(prev);
    const ng = gatesById(next);
    ng.forEach((g, id) => {
      const before = upper((pg.get(id) || {}).status);
      const after = upper(g.status);
      const title = (graph.byGate.get(id) || {}).title || id;
      if (before === 'AWAITING_HUMAN' && after === 'APPROVED') notes.push({ t: title + ': 결정을 기록했어요.', s: '' });
      if (before === 'AWAITING_HUMAN' && after === 'REJECTED') notes.push({ t: title + ': 다시 만들도록 보냈어요.', s: '요청을 반영해 새 버전을 만들어요. 끝나면 다시 검토할 수 있어요.' });
    });
    const pr = rowsById(prev);
    const started = [];
    const failed = [];
    rowsById(next).forEach((row, id) => {
      const before = upper((pr.get(id) || {}).status);
      const after = upper(row.status);
      const name = (graph.byStage.get(id) || {}).name || id;
      if (after === 'RUNNING' && (before !== 'RUNNING' || (pr.get(id) || {}).attempts !== row.attempts)) started.push(name);
      if (after === 'CHECK_FAILED' && before !== 'CHECK_FAILED') failed.push(name);
      if (before === 'CHECK_FAILED' && ['AWAITING_HUMAN', 'APPROVED'].includes(after)) notes.push({ t: name + ' 단계를 다시 실행해 통과했어요.', s: '' });
      if (id === 'sx' && after === 'APPROVED' && before !== 'APPROVED') notes.push({ t: '모든 단계를 마쳤어요.', s: '출시 묶음을 우리 앱으로 내보냈어요.' });
    });
    if (started.length) {
      const s = started.join(', ') + ' 단계를 시작했어요.';
      if (notes.length && !notes[notes.length - 1].s) notes[notes.length - 1].s = s;
      else notes.push({ t: s, s: '' });
    }
    failed.forEach((name) => notes.push({ t: name + ' 단계가 멈췄어요.', s: '지금 할 일에서 실패 이유를 확인하세요.', tone: 'bad' }));
    return notes.map((n) => Object.assign(n, { at: now }));
  }

  function unfinishedGoal(graph, detail, target) {
    const gate = graph.byGate.get(target);
    const row = gate ? gatesById(detail).get(target) : rowsById(detail).get(target);
    return (gate || graph.byStage.has(target)) && !['APPROVED', 'SKIPPED'].includes(upper((row || {}).status));
  }
  function runGoal(graph, detail, fallback, retryStage) {
    const d = detail || {};
    const goals = [d.job, ...(d.jobs || []), d.lastJob]
      .filter((j) => j && (!j.action || j.action === 'run') && !(j.confirm || []).length && !['videos', 'videos-with-chat'].includes(j.trigger))
      .map((j) => j.until);
    goals.push(fallback);
    const goal = goals.find((g) => unfinishedGoal(graph, d, g) && (!retryStage || ancestors(graph, g).has(retryStage)));
    return goal || retryStage || (d.origin === 'SOURCE' && unfinishedGoal(graph, d, 's8c') ? 's8c' : 'sx');
  }
  function chatStatusText(reviewCount) {
    return '대화할 수 있어요' + (reviewCount ? ' · 검토 ' + reviewCount + '건이 남았어요' : '');
  }
  function runFeedback(job, graph, detail) {
    if (!job || job.status !== 'succeeded' || !Array.isArray(job.ranStages)) return '';
    if ((job.held || []).length) return '비용 확인을 기다리고 있어요. 예상 비용을 보고 실행할지 골라 주세요.';
    if ((job.waiting || []).length) return '검토를 기다리고 있어요. 결과를 확인하면 이어서 만들 수 있어요.';
    if ((job.blocked || []).length) return '아직 시작할 수 없는 단계가 있어요. 앞 단계의 결과와 필요한 입력을 확인해 주세요.';
    if (job.ranStages.length) return '이번 실행을 마쳤어요.';
    return unfinishedGoal(graph, detail, job.until) ? '이 목표로 시작할 수 있는 단계가 없어요. 필요한 입력과 앞 단계를 확인해 주세요.' : '목표까지 이미 마쳐서 새로 실행할 단계가 없어요.';
  }

  function targetLabel(graph, until) {
    const id = text(until).trim();
    if (!id) return '';
    const gate = graph.byGate.get(id);
    if (gate) return gate.title + '까지';
    if (id === 'sx') return '끝까지';
    const stage = graph.byStage.get(id);
    return (stage ? stage.name : id) + '까지';
  }

  // ======================================================================
  function mount(options) {
    const doc = options.root || document;
    const apiBase = text(options.apiBase);
    const $ = (sel) => doc.querySelector(sel);
    const region = {
      side: $('[data-side]'), top: $('[data-top]'), banner: $('[data-banner]'), head: $('[data-head]'),
      graph: $('[data-graph]'), grid: $('[data-grid]'), legend: $('[data-legend]'), svg: $('[data-graph] svg.w'),
      view: $('[data-view]'), zoombar: $('[data-zoombar]'), shell: $('.fd-shell'), body: $('.fd-body'),
      panel: $('[data-panel]'), sheet: $('[data-sheet]'), scrim: $('[data-scrim]'), offgoal: $('[data-offgoal]')
    };
    let referenceState = null;
    const reference = Ref && Ref.mount({ host: $('[data-reference]'), apiBase, onChange(s) {
      const next = s.reference;
      const changed = !!(next && next.enabled) !== !!(referenceState && referenceState.enabled);
      referenceState = next;
      if (changed) { state.video = null; render(); }
    } });
    const store = (() => { try { return global.localStorage; } catch (error) { return null; } })();
    const state = {
      graph: null, rawGraph: null, health: null, projects: null, characterId: null, detail: null,
      gateViews: new Map(), sel: null, review: null, open: new Set(), notes: [], feedback: null, decided: {},
      conn: 'connecting', lastSync: null, busy: false, form: { open: false, slug: '', brief: '', error: '' },
      target: null, sheetKey: '', opener: null, openerGate: '', destroyed: false,
      overview: false, ov: { q: '', gate: '' }, batch: null, pendingReview: null, confirming: null, plans: {}, nextTarget: null, focus: false,
      // 사이드바 검색어, 보관함 보기, 목표 밖 단계 펼치기(3차 QA)
      sq: '', showArchived: false, showOff: false,
      // 갈래·모델 준비 방식마다 그래프가 다르다. 'CREATED|TRAIN' 같은 열쇠로 받아 둔 그래프(개요·받은 일이 캐릭터마다 자기 그래프로 센다).
      graphs: new Map(), graphSeq: 0, graphAsk: new Set(),
      theme: (store && ['light', 'dark'].includes(store.getItem('fd-theme'))) ? store.getItem('fd-theme') : 'system'
    };
    let refreshTimer = null;
    let listTimer = null;
    let trainTimer = null;
    let source = null;
    const media = global.matchMedia ? global.matchMedia('(prefers-color-scheme: dark)') : null;

    // ---- 테마 ----
    function resolvedTheme() {
      if (state.theme !== 'system') return state.theme;
      return media && media.matches ? 'dark' : 'light';
    }
    function applyTheme() {
      const html = doc.documentElement;
      if (state.theme === 'system') html.removeAttribute('data-fd-theme');
      else html.setAttribute('data-fd-theme', state.theme);
      const frame = region.sheet && region.sheet.querySelector('iframe.fl-frame');
      try { if (frame && frame.contentDocument) frame.contentDocument.documentElement.setAttribute('data-fd-theme', resolvedTheme()); } catch (error) { /* 다른 출처면 다음 열기 때 반영 */ }
    }

    async function request(method, path, body) {
      let response;
      try {
        response = await fetch(R.apiPath(apiBase, path), {
          method, headers: body ? { 'Content-Type': 'application/json' } : undefined,
          body: body ? JSON.stringify(body) : undefined, cache: 'no-store'
        });
      } catch (error) {
        const e = new Error('서버에 연결하지 못했어요. 연결이 돌아오면 자동으로 다시 읽어요.');
        e.network = true;
        throw e;
      }
      let data = null;
      try { data = await response.json(); } catch (error) { data = null; }
      if (!response.ok) {
        const detail = data && data.detail;
        const e = new Error(response.status === 409 ? '이미 바뀐 내용이 있어요. 최신 상태를 다시 읽었어요. ' + text(typeof detail === 'string' ? detail : '') : text(typeof detail === 'string' ? detail : '요청이 실패했어요 (' + response.status + ').'));
        e.status = response.status;
        throw e;
      }
      return data;
    }

    function routeId() {
      const m = /^#c\/([^/]+)(?:\/model)?$/.exec(text(global.location && global.location.hash));
      return m ? decodeURIComponent(m[1]) : null;
    }
    function route() {
      const hash = text(global.location && global.location.hash);
      // 처음 열면(주소에 캐릭터가 없으면) 전체 캐릭터 목록부터 보인다. 오래 멈춘 남의 캐릭터를 먼저 열지 않는다.
      if (!hash || hash === '#') return { overview: true, filter: 'all' };
      const m = /^#all(?:\/(\w+))?/.exec(hash);
      const f = m && m[1] === 'done' ? 'chat' : m && m[1];
      return m ? { overview: true, filter: ['mine', 'run', 'fail', 'chat'].includes(f) ? f : 'all' } : { overview: false, filter: '' };
    }
    function characters() { return (state.projects && state.projects.characters) || []; }
    // 보관한 캐릭터는 기본 목록에서 숨긴다(지우지 않는다). 지금 화면에 연 캐릭터는 보관했어도 보인다.
    function visibleChars() {
      const open = route().overview || state.form.open ? null : state.characterId;
      return characters().filter((c) => state.showArchived ? c.archived : (!c.archived || c.id === open));
    }
    function archivedCount() { return characters().filter((c) => c.archived).length; }
    function createdTime(c) { return createdOf(c).t; }
    function graphKey(x) { return text((x && x.origin) || 'CREATED') + '|' + text((x && x.modelMode) || 'TRAIN'); }
    // 그 캐릭터의 그래프. 지금 연 캐릭터는 그 캐릭터로 받은 그래프, 나머지는 같은 갈래·방식으로 받아 둔 그래프다.
    function graphOf(c) {
      if (c && c.id === state.characterId && state.graph) return state.graph;
      return state.graphs.get(graphKey(c)) || state.graphs.get('CREATED|TRAIN') || state.graph;
    }
    function gateTitle(id) {
      const own = state.graph && state.graph.byGate.get(id);
      if (own) return own.title;
      for (const g of state.graphs.values()) { const x = g.byGate.get(id); if (x) return x.title; }
      return id;
    }
    function trackHTML(c) {
      const tw = c && c.origin === 'SOURCE';
      return '<span class="fd-track' + (tw ? ' tw' : '') + '"><span class="d" aria-hidden="true"></span>' + E(trackLabel(c)) + '</span>';
    }
    function videoChipHTML(c) {
      const t = videoText(c);
      return t ? '<span class="fd-vid ' + videoTone(c) + '"><span class="d" aria-hidden="true"></span>' + E(t) + '</span>' : '';
    }

    // ---- 캐릭터 요약(개요·사이드바·받은 일이 같은 기준으로 센다) ----
    function summaryOf(c) {
      const det = c.id === state.characterId && state.detail ? state.detail : c;
      const now = Date.now();
      const graph = graphOf(c);
      const v = viewsFor(graph, det, { now });
      const tasks = buildTasks(graph, det, v, { now });
      const n = (k) => tasks.filter((x) => x.kind === k).length;
      const kinds = Object.keys(v).map((id) => v[id].kind);
      const done = kinds.filter((k) => k === 'done' || k === 'skip').length;
      const isComplete = upper((rowsById(det).get('sx') || {}).status) === 'APPROVED';
      const fresh = !det.job && !det.lastJob && (det.stages || []).every((s) => upper(s.status) === 'PENDING');
      const running = Boolean(det.job) || kinds.some((k) => k === 'run' || k === 'retry');
      const waits = tasks.map((x) => parseTime(x.openedAt)).filter((x) => x != null);
      const lanes = graph.lanes.map((lane) => {
        const ids = (lane.stages || []).map((s) => (typeof s === 'string' ? s : s.id)).filter((id) => graph.byStage.has(id));
        return { id: lane.id, label: lane.label, kind: laneKind(ids, v), done: ids.filter((id) => ['done', 'skip'].includes(v[id].kind)).length, total: ids.length };
      });
      const fail = n('fail');
      const review = n('wait');
      const paid = n('confirm');
      const status = statusOf(det, { fail, review, paid, running, complete: isComplete, fresh });
      const goal = goalOf(graph, det, v);
      return { c, tasks, fail, review, paid, todo: fail + review + paid, done, total: graph.stages.length, complete: isComplete, fresh, running, oldest: waits.length ? Math.min.apply(null, waits) : null, lanes, rank: status.rank, status, goal, chat: chatHref(det), created: createdTime(c), top: tasks[0] || null, updated: parseTime(det.updatedAt || c.updatedAt) };
    }
    function statusDot(s) { const t = s.status.tone; return t === 'muted' ? '' : t; }
    function nextInBatch() {
      if (!state.batch || !state.graph) return null;
      const list = characters().filter((c) => c.id !== state.characterId).map(summaryOf)
        .filter((s) => s.tasks.some((x) => x.kind === 'wait' && x.gate === state.batch));
      list.sort((a, b) => (a.oldest || Infinity) - (b.oldest || Infinity));
      return list.length ? { next: list[0], left: list.length } : null;
    }
    function adoptGraph(raw) {
      const g = R.buildGraph(raw);
      g.paid = new Map((raw.stages || []).map((s) => [s.id, s.paid || []]));
      // 갈래에 없는 단계만 있던 팀은 그리지 않는다(그래프는 실제 순서를 뜻한다).
      g.lanes = g.lanes.filter((l) => (l.stages || []).some((s) => g.byStage.has(typeof s === 'string' ? s : s.id)));
      g.key = graphKey(raw);
      g.layout = layoutOf(g);
      g.origin = raw.origin || 'CREATED';
      g.modelMode = raw.modelMode || 'TRAIN';
      const s8c = g.byStage.get('s8c');
      if (s8c) s8c.name = s8cName(g.origin, '');
      state.graphs.set(g.key, g);
      return g;
    }
    // 인자 없는 그래프는 오리지널 기본이다. 캐릭터가 아직 없거나 개요만 볼 때 쓴다.
    async function loadGraph() {
      const [raw, health] = await Promise.all([request('GET', R.graphPath()), request('GET', '/api/health').catch(() => null)]);
      const g = adoptGraph(raw);
      if (!state.graph || !state.characterId) { state.graph = g; state.rawGraph = raw; }
      state.health = health;
    }
    // 연 캐릭터의 그래프. 캐릭터를 바꾸는 사이 이전 요청이 늦게 오면 받아 두기만 하고 화면 그래프로 쓰지 않는다.
    async function loadCharacterGraph(id) {
      const seq = ++state.graphSeq;
      const raw = await request('GET', R.graphPath(id));
      const g = adoptGraph(raw);
      if (seq !== state.graphSeq || state.characterId !== id) return false;
      state.graph = g;
      state.rawGraph = raw;
      return true;
    }
    // 개요·받은 일은 캐릭터마다 자기 그래프로 센다. 아직 없는 갈래·방식의 그래프는 그 캐릭터 하나로 받아 둔다.
    function ensureGraphs() {
      characters().forEach((c) => {
        const key = graphKey(c);
        if (state.graphs.has(key) || state.graphAsk.has(key)) return;
        state.graphAsk.add(key);
        request('GET', R.graphPath(c.id)).then((raw) => { adoptGraph(raw); render(); })
          .catch(() => {})
          .then(() => state.graphAsk.delete(key));
      });
    }
    // 보관한 캐릭터도 받아 와야 보관함 수와 보관 풀기가 보인다(QA v5 D-02). 목록에서는 archived로 거른다.
    async function loadProjects() { state.projects = await request('GET', '/api/projects?includeArchived=true'); }
    async function loadDetail() {
      if (!state.characterId) { state.detail = null; return; }
      const id = state.characterId;
      const prev = state.detail;
      const next = await request('GET', '/api/characters/' + encodeURIComponent(id));
      // 그사이 다른 캐릭터로 바꿨으면 늦게 온 결과로 덮어쓰지 않는다.
      if (state.characterId !== id) return;
      // 시트에서 막 알린 결정은 상태 비교 알림과 겹치지 않게 뺀다.
      const recent = Object.keys(state.decided).filter((g) => Date.now() - state.decided[g] < 60000).map((g) => ((state.graph.byGate.get(g) || {}).title || g) + ':');
      const fresh = diffNotes(state.graph, prev, next, Date.now()).filter((n) => !recent.some((prefix) => n.t.indexOf(prefix) === 0));
      if (fresh.length) state.notes = fresh.concat(state.notes).slice(0, 3);
      const tracked = (next.jobs || []).find((j) => j.jobId === state.runJobId);
      const result = runFeedback(tracked, state.graph, next);
      if (result || (tracked && tracked.status === 'failed')) state.runJobId = null;
      if (result) state.feedback = { tone: 'ok', text: result };
      else if (tracked && tracked.status === 'failed') state.feedback = { tone: 'bad', text: '작업이 멈췄어요. 지금 할 일에서 이유를 확인해 주세요.' };
      state.detail = next;
      if (state.review && !state.review.readonly) {
        const g = gatesById(next).get(state.review.gate);
        if (!g || upper(g.status) !== 'AWAITING_HUMAN') { state.sel = state.review.stage || state.sel; closeSheet(false); }
      }
      loadGateViews();
    }
    function loadGateViews() {
      const detail = state.detail;
      if (!detail) return;
      const wanted = R.pendingGatesFor(detail, state.graph).map((g) => g.id);
      const selDef = state.sel && state.graph.byStage.get(state.sel);
      if (selDef && selDef.gate) wanted.push(selDef.gate);
      const gates = gatesById(detail);
      wanted.forEach((gate) => {
        const rev = text((gates.get(gate) || {}).rev);
        const key = gate + '|' + rev;
        if (!rev || state.gateViews.has(key)) return;
        state.gateViews.set(key, null);
        request('GET', '/api/characters/' + encodeURIComponent(detail.id) + '/gates/' + encodeURIComponent(gate))
          .then((view) => { state.gateViews.set(key, view); render(); })
          .catch(() => { state.gateViews.delete(key); });
      });
    }

    async function refresh(full) {
      try {
        if (!state.graph || full) await loadGraph();
        await loadProjects();
        ensureGraphs();
        // 주소에 캐릭터가 없으면 아무 캐릭터도 고르지 않는다(첫 화면은 전체 캐릭터 목록).
        const wanted = routeId() || state.characterId || null;
        const changed = wanted !== state.characterId;
        if (changed) {
          state.characterId = wanted; state.detail = null; state.sel = null; closeSheet(false); state.notes = []; state.open = new Set(); state.target = null; state.mstep = null; state.mconfirm = null;
          state.showOff = false; state.menuOpen = false; state.moreOpen = false;
          state.video = null;
          // 새 그래프가 오기 전에는 받아 둔 같은 갈래 그래프로 그린다(이전 캐릭터의 그래프를 남기지 않는다).
          const entry = characters().find((c) => c.id === wanted);
          state.graph = state.graphs.get(graphKey(entry)) || state.graphs.get('CREATED|TRAIN') || state.graph;
        }
        const listed = characters().find((c) => c.id === wanted);
        // 캐릭터를 열거나 바꿀 때, 모델 준비 방식이 바뀌었을 때 그 캐릭터의 그래프를 다시 받는다.
        if (wanted && (changed || full || (listed && graphKey(listed) !== state.graph.key))) {
          if (!(await loadCharacterGraph(wanted))) return;
        }
        await loadDetail();
        // 학습이 도는 동안은 진행(스텝·쓴 돈)을 3초마다 다시 읽는다(D-0130). 상태 사건이 없어도 바뀐다.
        clearTimeout(trainTimer);
        const tr = trainingOf(state.detail);
        if ((tr && tr.state === 'run') || (state.detail && state.detail.job && state.detail.job.action === 'train')) trainTimer = setTimeout(() => refresh(false), 3000);
        if (state.reselect) { state.reselect = false; state.sel = null; }
        const pr = state.pendingReview;
        if (pr && state.detail && state.detail.id === pr.id) {
          state.pendingReview = null;
          const g = gatesById(state.detail).get(pr.gate);
          if (g && upper(g.status) === 'AWAITING_HUMAN') {
            state.review = { gate: pr.gate, stage: pr.stage || (state.graph.byGate.get(pr.gate) || {}).stage, readonly: false };
            state.openerGate = pr.gate;
            state.sel = state.review.stage;
          }
        }
        state.lastSync = Date.now();
        if (state.conn === 'offline') state.conn = 'live';
      } catch (error) {
        if (error.network) state.conn = 'offline';
        else state.feedback = { tone: 'bad', text: error.message };
      }
      render();
    }
    function soon(fn, ms, which) {
      if (which === 'list') { clearTimeout(listTimer); listTimer = setTimeout(fn, ms); }
      else { clearTimeout(refreshTimer); refreshTimer = setTimeout(fn, ms); }
    }
    function startEvents() {
      if (typeof EventSource === 'undefined') return;
      source = new EventSource(R.eventsUrl(apiBase));
      source.onopen = () => { state.conn = 'live'; render(); };
      source.onerror = () => { state.conn = 'reconnecting'; render(); };
      ['state', 'job', 'gate', 'hello'].forEach((name) => source.addEventListener(name, (event) => {
        let data = {};
        try { data = JSON.parse(event.data); } catch (error) { data = {}; }
        if (name === 'hello' || !data.characterId || data.characterId === state.characterId) soon(() => refresh(false), 300);
        else soon(() => loadProjects().then(render).catch(() => {}), 1500, 'list');
      }));
    }

    // ---- 계산 ----
    function views(scope) { return viewsFor(state.graph, state.detail, { now: Date.now(), scope }); }
    function notStarted() {
      const d = state.detail;
      if (!d) return false;
      const jobs = Array.isArray(d.jobs) ? d.jobs : [];
      return !jobs.length && !d.job && (d.stages || []).every((s) => upper(s.status) === 'PENDING');
    }
    function complete() { return upper((rowsById(state.detail).get('sx') || {}).status) === 'APPROVED'; }
    function defaultTarget() { return text(state.health && state.health.config && state.health.config.defaultUntil) || 'G6'; }
    function orchestrator() { return (state.rawGraph && state.rawGraph.orchestrator) || {}; }
    function setupScope() { return notStarted() ? ancestors(state.graph, state.target || defaultTarget()) : null; }
    function currentUntil() {
      return runGoal(state.graph, state.detail, orchestrator().resumeUntil);
    }
    // 마지막 작업 시각과 걸린 시간(첫 시작 → 마지막 끝). 아무것도 돌지 않을 때 시간이 저절로 늘어나지 않는다.
    function activity() {
      const d = state.detail || {};
      const hist = d.history || {};
      let first = null;
      let last = null;
      Object.keys(hist).forEach((id) => (hist[id] || []).forEach((a) => {
        const s = parseTime(a.startedAt);
        const e = parseTime(a.endedAt);
        if (s != null && (first == null || s < first)) first = s;
        const end = e != null ? e : s;
        if (end != null && (last == null || end > last)) last = end;
      }));
      (d.gates || []).forEach((g) => { const t = parseTime(g.decidedAt); if (t != null && (last == null || t > last)) last = t; });
      if (last == null) last = parseTime(d.updatedAt);
      return { last, took: first != null && last != null && last - first >= 60000 ? span(last - first) : '' };
    }
    function whenText(t) {
      if (t == null) return '';
      const d = new Date(t);
      const now = new Date();
      const hm = pad2(d.getHours()) + ':' + pad2(d.getMinutes());
      return d.toDateString() === now.toDateString() ? hm : (d.getMonth() + 1) + '/' + d.getDate() + ' ' + hm;
    }
    function nameOf(d) { return labelOf({ id: d && d.id, displayName: d && d.displayName, persona: d && d.persona, name: d && (d.name || (d.summary && d.summary.name)) }); }
    function isMotif(d) { return Boolean(d) && (d.origin || (state.graph && state.graph.origin)) === 'SOURCE'; }
    // 프롬프트만 쓰는 모티브는 학습을 하지 않으므로 모델 만들기 탭이 없다.
    function promptOnly(d) { return isMotif(d) && (d.modelMode || (state.graph && state.graph.modelMode)) === 'PROMPT_ONLY'; }
    function currentSummary() {
      if (!state.detail) return null;
      return allSums().get(state.detail.id) || summaryOf(Object.assign({}, characters().find((c) => c.id === state.detail.id) || {}, { id: state.detail.id }));
    }
    function counts(v) {
      const c = { run: 0, fail: 0, wait: 0, done: 0 };
      Object.keys(v).forEach((id) => { const k = v[id].kind; if (k === 'run' || k === 'retry') c.run++; if (k === 'fail') c.fail++; if (k === 'wait' || k === 'confirm') c.wait++; if (k === 'done' || k === 'skip') c.done++; });
      return c;
    }
    // 한 번 그릴 때 캐릭터마다 요약을 한 번만 만든다(사이드바·머리줄·개요가 같은 값을 쓴다).
    let sumMemo = null;
    function allSums() {
      if (!sumMemo) sumMemo = new Map(state.graph ? characters().map((c) => [c.id, summaryOf(c)]) : []);
      return sumMemo;
    }
    function visibleSums() { const m = allSums(); return visibleChars().map((c) => m.get(c.id)).filter(Boolean); }
    function inboxCount() { let n = 0; allSums().forEach((s) => { if (!s.c.archived) n += s.todo; }); return n; }
    // 사이드바는 최근에 만든 캐릭터가 위에 온다(상태가 바뀌어도 자리가 흔들리지 않는다). 상태는 줄마다 글자로 보인다.
    function byNewest(a, b) { return b.created - a.created || (b.updated || 0) - (a.updated || 0) || text(b.c.id).localeCompare(text(a.c.id)); }

    // ---- 사이드바 ----
    function renderSide() {
      if (!region.side) return;
      const rt = route();
      const labels = nameLabels(characters());
      const q = state.sq.trim().toLowerCase();
      const rows = visibleSums().sort(byNewest).filter((s) => {
        if (!q) return true;
        const l = labels.get(s.c.id) || {};
        return (text(l.name) + ' ' + text(l.note) + ' ' + text(s.c.persona && s.c.persona.job)).toLowerCase().indexOf(q) >= 0;
      });
      const items = rows.map((s) => {
        const c = s.c;
        const l = labels.get(c.id) || { name: labelOf(c), note: '' };
        const sub = [s.status.label, l.note].filter(Boolean).join(' · ');
        return '<button type="button" class="fd-nav two" data-act="pick" data-id="' + E(c.id) + '"' + (!rt.overview && c.id === state.characterId ? ' aria-current="page"' : '') + ' title="' + E(l.name + ' · ' + sub) + '">' +
          '<span class="fd-av" aria-hidden="true">' + E(Array.from(l.name)[0] || '?') + '<span class="st ' + statusDot(s) + '"></span></span>' +
          '<span class="lbl"><span class="nm"><span class="tx">' + E(l.name) + '</span>' + (c.origin === 'SOURCE' ? '<span class="fd-org" title="' + E(trackLabel(c)) + '">' + E(c.originLabel || '모티브') + '</span>' : '') + '</span><small>' + E(sub) + '</small></span>' +
          (s.todo ? '<span class="num attn"><span class="sr">할 일 </span>' + s.todo + '<span class="u">건</span></span>' : '') + '</button>';
      }).join('');
      const inbox = inboxCount();
      const arch = archivedCount();
      const empty = q ? '찾는 캐릭터가 없어요' : state.showArchived ? '보관한 캐릭터가 없어요' : '아직 없어요';
      const theme = [['system', 'monitor', '시스템 설정 따르기'], ['light', 'sun', '밝은 화면'], ['dark', 'moon', '어두운 화면']]
        .map((t) => '<button type="button" data-act="theme" data-theme="' + t[0] + '" aria-pressed="' + (state.theme === t[0]) + '" aria-label="' + t[2] + '" title="' + t[2] + '">' + icon(t[1]) + '</button>').join('');
      region.side.innerHTML = '<div class="fd-brand">' + MARK + '<div class="fd-word"><b>Foundry</b><small>캐릭터 공장</small></div></div>' +
        '<div class="fd-side-actions"><a class="btn block" href="sources.html" title="실존 인물을 원문으로 만들어요" style="text-decoration:none">' + icon('user') + '<span class="lbl">실존 인물 · 원문으로</span></a>' +
        '<button type="button" class="btn block" data-act="new" title="지어낸 캐릭터를 브리프로 만들어요" style="margin-top:6px">' + icon('plus') + '<span class="lbl">새로 지어내기</span></button></div>' +
        '<nav aria-label="캐릭터 탐색"><button type="button" class="fd-nav" data-act="overview" title="전체 캐릭터"' + (rt.overview && rt.filter !== 'mine' ? ' aria-current="page"' : '') + '>' + icon('grid') + '<span class="lbl">전체 캐릭터</span><span class="num">' + characters().filter((c) => !c.archived).length + '명</span></button>' +
        '<button type="button" class="fd-nav" data-act="inbox" title="받은 일"' + (rt.overview && rt.filter === 'mine' ? ' aria-current="page"' : '') + '>' + icon('inbox') + '<span class="lbl">받은 일</span>' + (inbox ? '<span class="num attn"><span class="sr">할 일 </span>' + inbox + '<span class="u">건</span></span>' : '<span class="num">0건</span>') + '</button>' +
        '<h2>' + (state.showArchived ? '보관함' : '캐릭터') + '</h2>' +
        '<div class="fd-side-q"><label class="sr" for="fd-side-q">캐릭터 이름으로 찾기</label><input id="fd-side-q" data-side-q type="search" placeholder="이름으로 찾기" value="' + E(state.sq) + '" autocomplete="off"></div>' +
        (items || '<p class="hint fd-side-empty">' + empty + '</p>') +
        (arch || state.showArchived ? '<button type="button" class="fd-nav fd-arch" data-act="archived" aria-pressed="' + state.showArchived + '" title="' + (state.showArchived ? '보관함 닫기' : '보관한 캐릭터 보기') + '">' + icon('archive') + '<span class="lbl">' + (state.showArchived ? '보관함 닫기' : '보관함') + '</span><span class="num">' + arch + '명</span></button>' : '') + '</nav>' +
        '<div class="fd-side-foot"><a class="fd-help" href="help.html" target="_blank" rel="noopener" title="사용 안내" aria-label="사용 안내">?</a><div class="fd-theme" role="group" aria-label="화면 테마">' + theme + '</div>' +
        '<div class="fd-foot-links"><a href="help.html" target="_blank" rel="noopener">사용 안내</a><a class="fd-ops" href="settings.html" title="설정" aria-label="설정">' + icon('gear') + '</a></div></div>';
    }

    // ---- 머리줄 ----
    // 좁은 화면에서는 사이드바(테마 버튼 포함)가 숨으므로 머리줄에 한 번 누르면 다음 테마로 넘어가는 버튼을 둔다(K-0088).
    function headThemeHTML() {
      const order = [['system', 'monitor', '시스템 설정 따르기'], ['light', 'sun', '밝은 화면'], ['dark', 'moon', '어두운 화면']];
      const i = Math.max(0, order.findIndex((t) => t[0] === state.theme));
      const cur = order[i];
      const next = order[(i + 1) % order.length];
      return '<button type="button" class="fd-head-theme" data-act="theme" data-theme="' + next[0] + '" aria-label="화면 테마: 지금 ' + cur[2] + '. 누르면 ' + next[2] + '" title="화면 테마: ' + cur[2] + '">' + icon(cur[1]) + '</button>';
    }
    // 연결 상태는 끊겼을 때만 보인다.
    function connHTML() {
      if (state.conn === 'offline') return '<span class="fd-conn off" role="status"><span class="d"></span>연결 끊김 · 다시 연결하는 중</span>';
      if (state.conn === 'reconnecting') return '<span class="fd-conn wait" role="status"><span class="d"></span>다시 연결하는 중</span>';
      return '';
    }
    function statusPill(st) { return '<span class="fl-pill ' + st.tone + '"><span class="d"></span>' + E(st.label) + '</span>'; }
    function renderTop(v) {
      const d = state.detail;
      const sums = visibleSums().sort(byNewest);
      const labels = nameLabels(characters());
      const optName = (s) => { const l = labels.get(s.c.id) || { name: labelOf(s.c), note: '' }; return l.name + (l.note ? ' (' + l.note + ')' : '') + ' · ' + s.status.label; };
      const picker = characters().length ? '<label class="sr" for="fl-pick">캐릭터</label><select id="fl-pick" class="fd-pick" data-pick><option value="__all"' + (state.overview ? ' selected' : '') + '>전체 캐릭터</option>' + sums.map((s) => '<option value="' + E(s.c.id) + '"' + (!state.overview && !state.form.open && s.c.id === state.characterId ? ' selected' : '') + '>' + E(optName(s)) + '</option>').join('') + '<option value="__src">+ 실존 인물 · 원문으로</option><option value="__new"' + (state.form.open ? ' selected' : '') + '>+ 새로 지어내기</option></select>' : '';
      if (state.form.open) {
        region.top.innerHTML = '<nav class="fd-crumb" aria-label="위치"><a class="up" href="#all">전체 캐릭터</a><span class="sep">/</span><b>새로 지어내기</b></nav>' + picker + '<div class="fd-metrics">' + connHTML() + '</div>' + headThemeHTML();
        if (doc.title !== undefined) doc.title = '새로 지어내기 · Foundry';
        return;
      }
      if (state.overview) {
        const n = (st) => sums.filter((s) => s.status.status === st).length;
        const pillsO = [['failed', '실패'], ['needs_review', '확인 필요'], ['running', '만드는 중']].map((x) => n(x[0]) ? statusPill({ tone: STATUS_TONE[x[0]], label: x[1] + ' ' + n(x[0]) + '명' }) : '').join('');
        region.top.innerHTML = '<nav class="fd-crumb" aria-label="위치">' + (route().filter === 'mine' ? '<a class="up" href="#all">전체 캐릭터</a><span class="sep">/</span><b>받은 일</b>' : '<b>전체 캐릭터</b>') + '</nav>' + picker + pillsO + '<div class="fd-metrics"><span>캐릭터 <b>' + sums.length + '</b>명</span>' + connHTML() + '</div>' + headThemeHTML();
        const todo = inboxCount();
        if (doc.title !== undefined) doc.title = (todo ? '(' + todo + ') ' : '') + '전체 캐릭터 · Foundry';
        return;
      }
      const s = d ? currentSummary() : null;
      const meta = [];
      if (d && !notStarted()) {
        const a = activity();
        if (a.last != null) meta.push('<span>마지막 작업 <b>' + E(whenText(a.last)) + '</b></span>');
        if (a.took && s && s.status.status !== 'running') meta.push('<span>걸린 시간 ' + E(a.took) + '</span>');
        if (d.cost && d.cost.estUsd != null) meta.push('<span title="지금까지 이 캐릭터에 쓴 추정 비용">비용 <b>$' + Number(d.cost.estUsd).toFixed(2) + '</b></span>');
      }
      const conn = connHTML();
      if (conn) meta.push(conn);
      const crumb = d ? '<a class="up" href="#all">전체 캐릭터</a><span class="sep">/</span><b>' + E(nameOf(d)) + '</b>' : '<b>캐릭터</b>';
      region.top.innerHTML = '<nav class="fd-crumb" aria-label="위치">' + crumb + '</nav>' + picker + (s ? statusPill(s.status) : '') + '<div class="fd-metrics">' + meta.join('') + '</div>' + headThemeHTML();
      const waiting = d ? Object.keys(v).filter((id) => ['wait', 'confirm', 'fail'].includes(v[id].kind)).length : 0;
      if (doc.title !== undefined) doc.title = (waiting ? '(' + waiting + ') ' : '') + (d ? nameOf(d) + ' · ' : '') + 'Foundry';
    }

    function renderBanner() {
      const f = state.feedback;
      if (f && f.tone === 'ok' && !f.at) f.at = Date.now();
      if (f && f.tone === 'ok' && Date.now() - f.at > 8000) state.feedback = null;
      if (f && f.tone === 'ok' && state.feedback) setTimeout(() => { if (state.feedback === f) { state.feedback = null; renderBanner(); } }, 8200 - (Date.now() - f.at));
      const g = state.feedback;
      region.banner.innerHTML = g ? '<div class="fl-banner ' + E(g.tone) + '" role="' + (g.tone === 'bad' ? 'alert' : 'status') + '">' + E(g.text) + '</div>' : '';
    }

    // ---- 캔버스 머리 ----
    function titleHTML() {
      const d = state.detail;
      const s = currentSummary();
      const motif = isMotif(d);
      const until = currentUntil();
      const sub = motif ? '' : notStarted() ? '아직 실행하지 않았어요' : (until ? '목표 ' + targetLabel(state.graph, until) : '');
      let prog = '';
      if (!notStarted() && s) {
        const g = s.goal;
        if (motif) {
          // 모티브는 대화 가능까지 필요한 단계만 센다(16단계 막대를 쓰지 않는다).
          prog = '<span class="fd-prog-wrap fd-goal">' + E(g.label) + ' <b>' + g.done + '/' + g.total + '</b>단계</span>';
        } else {
          const pct = g.total ? Math.round(g.done / g.total * 100) : 0;
          prog = '<span class="fd-prog-wrap"><span class="fd-prog" role="img" aria-label="' + E('전체 ' + g.total + '단계 중 ' + g.done + '단계 완료, ' + pct + '%') + '">' + s.lanes.map((l) => '<span class="seg ' + l.kind + '" title="' + E(l.label + ' ' + l.done + '/' + l.total) + '"></span>').join('') + '</span>' + g.done + '/' + g.total + '단계 · ' + pct + '%</span>';
        }
      }
      const demo = motif ? '<span class="fd-demo">' + E(DEMO_NOTE) + '</span>' : '';
      // 공정 보기에서는 '대화해 보기'가 지금 할 일 카드의 주 버튼이다. 머리에는 다른 보기(모델 만들기)에서만 둔다.
      const href = chatHref(d);
      const chat = href && modelMode() ? '<a class="btn fd-chat" href="' + E(href) + '">' + icon('chat') + '대화해 보기</a>' : '';
      return '<div class="fd-title"><h1 tabindex="-1">' + E(nameOf(d)) + '</h1>' + trackHTML(d) + videoChipHTML(d) + (sub ? '<p>' + E(sub) + '</p>' : '') + prog + demo + chat + moreHTML(d) + '</div>';
    }
    // 캐릭터 메뉴: 기술 정보(ID)와 보관하기. 다시 그려도 열린 상태를 유지한다.
    function archivedNow(d) { const c = characters().find((x) => x.id === d.id); return Boolean((c && c.archived) || d.archived); }
    function moreHTML(d) {
      const arch = archivedNow(d);
      return '<div class="fd-more' + (state.menuOpen ? ' open' : '') + '"><button type="button" class="btn ghost fd-more-btn" data-act="menu" aria-expanded="' + Boolean(state.menuOpen) + '" aria-label="캐릭터 메뉴" title="캐릭터 메뉴">' + icon('more') + '</button>' +
        (state.menuOpen ? '<div class="fd-menu" role="group" aria-label="캐릭터 메뉴"><button type="button" class="btn block" data-act="archive" data-v="' + (arch ? '0' : '1') + '">' + icon('archive') + (arch ? '보관 풀기' : '보관하기') + '</button><p class="hint">' + (arch ? '다시 목록에 보여요.' : '지우지 않고 목록에서만 숨겨요. 보관함에서 다시 찾을 수 있어요.') + '</p>' +
          '<div class="fd-menu-tech"><span>캐릭터 ID</span><code>' + E(d.id) + '</code></div></div>' : '') + '</div>';
    }
    function formHTML() {
      const f = state.form;
      return '<form class="fl-form" data-form><h2>새로 지어내기</h2><p class="hint">지어낸 캐릭터를 브리프로 만들어요. 실존 인물이라면 <a href="sources.html">원문으로 만들기</a>를 써 주세요. 등록만 하고 바로 실행하지 않아요.</p>' +
        '<label for="fl-brief">어떤 캐릭터인가요</label><textarea id="fl-brief" data-brief placeholder="타깃, 분위기, 성격, 챕터 배경 등을 적어 주세요.">' + E(f.brief) + '</textarea>' +
        '<label for="fl-voice">Fish Audio 음성 ID (선택)</label><input id="fl-voice" data-voice autocomplete="off" spellcheck="false" maxlength="40" value="' + E(f.voice || '') + '" placeholder="비워 두면 음성 없이 만들어요"><p class="hint">적은 ID를 그대로 캐릭터 패키지에 담아요.</p>' +
        '<details class="fl-adv"' + (f.slug ? ' open' : '') + '><summary>짧은 이름 직접 정하기 (선택)</summary><label for="fl-slug">짧은 이름 (영문 소문자·숫자·하이픈)</label><input id="fl-slug" data-slug autocomplete="off" value="' + E(f.slug) + '" placeholder="비워 두면 자동으로 정해요"></details>' +
        (f.error ? '<p class="err" role="alert">' + E(f.error) + '</p>' : '') +
        '<div class="acts"><button type="submit" class="btn pri"' + (state.busy ? ' disabled' : '') + '>등록하기</button>' + (characters().length ? '<button type="button" class="btn ghost" data-act="cancel-form">취소</button>' : '') + '</div></form>';
    }
    function overviewHTML(filter) {
      if (!characters().length) return emptyHTML();
      const all = visibleSums();
      const labels = nameLabels(characters());
      const gates = new Map();
      all.forEach((s) => s.tasks.filter((x) => x.kind === 'wait').forEach((x) => gates.set(x.gate, (gates.get(x.gate) || 0) + 1)));
      if (state.ov.gate && !gates.has(state.ov.gate)) state.ov.gate = '';
      const is = (s, st) => s.status.status === st;
      const match = { all: () => true, mine: (s) => s.todo > 0, run: (s) => is(s, 'running'), chat: (s) => isChatReady(s.c), fail: (s) => is(s, 'failed') };
      const counts = {};
      Object.keys(match).forEach((k) => { counts[k] = all.filter(match[k]).length; });
      const q = state.ov.q.trim().toLowerCase();
      let rows = all.filter(match[filter] || match.all);
      if (state.ov.gate) rows = rows.filter((s) => s.tasks.some((x) => x.kind === 'wait' && x.gate === state.ov.gate));
      if (q) rows = rows.filter((s) => { const l = labels.get(s.c.id) || {}; return (text(l.name) + ' ' + text(l.note) + ' ' + text(s.c.persona && s.c.persona.job)).toLowerCase().indexOf(q) >= 0; });
      rows.sort((a, b) => a.rank - b.rank || (a.oldest || Infinity) - (b.oldest || Infinity) || b.created - a.created);
      const tabs = [['all', '전체'], ['mine', '할 일 있음'], ['run', '만드는 중'], ['chat', '대화 가능'], ['fail', '실패']]
        .map((x) => '<a class="ov-tab" href="#all' + (x[0] === 'all' ? '' : '/' + x[0]) + '"' + (x[0] === filter ? ' aria-current="page"' : '') + '>' + x[1] + '<span class="n">' + counts[x[0]] + '명</span></a>').join('');
      const gateSel = gates.size ? '<label class="sr" for="ov-gate">검토 종류</label><select id="ov-gate" data-ov-gate><option value="">검토 종류 전체</option>' + Array.from(gates).map((x) => '<option value="' + E(x[0]) + '"' + (state.ov.gate === x[0] ? ' selected' : '') + '>' + E(gateTitle(x[0])) + ' · ' + x[1] + '건</option>').join('') + '</select>' : '';
      const search = '<label class="sr" for="ov-q">이름으로 찾기</label><input id="ov-q" data-ov-q type="search" placeholder="이름으로 찾기" value="' + E(state.ov.q) + '" autocomplete="off">';
      const arch = archivedCount();
      const archBtn = arch || state.showArchived ? '<button type="button" class="btn ghost" data-act="archived" aria-pressed="' + state.showArchived + '">' + icon('archive') + (state.showArchived ? '보관함 닫기' : '보관함 ' + arch + '명') + '</button>' : '';
      const title = state.showArchived ? '보관함' : filter === 'mine' ? '받은 일' : '전체 캐릭터';
      const lead = state.showArchived ? '보관한 캐릭터예요. 열어서 캐릭터 메뉴에서 보관을 풀 수 있어요.' : filter === 'mine' ? '사람이 확인할 일(검토 · 실패 · 비용 확인)이 있는 캐릭터예요. 검토 종류로 거르면 같은 검토를 이어서 할 수 있어요.' : '캐릭터마다 지금 상태와 할 일을 봐요. 확인이 필요한 캐릭터가 위에 와요.';
      const head = '<div class="fd-title"><h1 tabindex="-1">' + title + '</h1><p>' + lead + '</p></div>';
      const bar = '<div class="ov-bar"><nav class="ov-tabs" aria-label="상태로 거르기">' + tabs + '</nav><div class="ov-tools">' + gateSel + search + archBtn + '</div></div>';
      if (!rows.length) return head + bar + '<div class="fl-empty sm"><h2>' + (filter === 'mine' && !q && !state.ov.gate ? '지금 사람이 할 일이 없어요' : '조건에 맞는 캐릭터가 없어요') + '</h2>' + (q || state.ov.gate || filter !== 'all' ? '<div class="acts"><button type="button" class="btn" data-act="ov-clear">거르기 지우기</button></div>' : '') + '</div>';
      return head + bar + '<div class="ov-wrap"><table class="ov-table"><caption class="sr">캐릭터별 상태</caption><thead><tr><th scope="col">캐릭터</th><th scope="col">상태 · 지금 할 일</th><th scope="col">진행</th><th scope="col">마지막 변화</th><th scope="col"><span class="sr">동작</span></th></tr></thead><tbody>' + rows.map((s, i) => rowHTML(s, i, labels)).join('') + '</tbody></table></div>';
    }
    function nowText(s) {
      const st = s.status.status;
      if (st === 'chat_ready') return chatStatusText(s.review) + ' · 제작 진행은 별도예요';
      if (st === 'running') return '만드는 중이에요';
      if (st === 'draft') return s.c.origin === 'SOURCE' ? '원문을 올리는 중이에요' : '아직 실행하지 않았어요';
      if (st === 'done') return '모든 단계를 마쳤어요';
      if (s.top) return s.top.title;
      return '멈춰 있어요';
    }
    function rowHTML(s, i, labels) {
      const c = s.c;
      const l = (labels && labels.get(c.id)) || { name: labelOf(c), note: '' };
      const p = c.persona || {};
      const st = statusDot(s);
      const gateTask = state.ov.gate ? s.tasks.find((x) => x.kind === 'wait' && x.gate === state.ov.gate) : null;
      const top = gateTask || (s.todo ? s.top : null);
      const more = s.todo > 1 ? ' 외 ' + (s.todo - 1) + '건' : '';
      const now = top ? E(top.title) + (top.age ? '<span class="age"> · ' + E(top.age) + '</span>' : '') + E(more) : E(nowText(s));
      const g = s.goal;
      const pct = g.total ? Math.round(g.done / g.total * 100) : 0;
      const segs = g.ids ? '' : '<span class="segs" role="img" aria-label="' + E('전체 ' + g.total + '단계 중 ' + g.done + '단계 완료, ' + pct + '%') + '">' + s.lanes.map((x) => '<span class="seg ' + x.kind + '" title="' + E(x.label + ' ' + x.done + '/' + x.total) + '"></span>').join('') + '</span>';
      const href = '#c/' + encodeURIComponent(c.id);
      let act = '<a class="btn" href="' + E(href) + '">열기</a>';
      if (top && top.kind === 'wait') act = '<button type="button" class="btn' + (i === 0 && s.rank <= 1 ? ' pri' : '') + '" data-act="ov-review" data-id="' + E(c.id) + '" data-gate="' + E(top.gate) + '" data-stage="' + E(top.stage || '') + '">검토하기</button>';
      else if (s.chat) act = '<a class="btn" href="' + E(s.chat) + '">' + icon('chat') + '대화해 보기</a>';
      else if (s.status.status === 'draft' && c.origin === 'SOURCE') act = '<a class="btn" href="sources.html#c/' + E(encodeURIComponent(c.id)) + '">이어 하기</a>';
      const sub = [[l.note, [p.job, p.age ? p.age + '세' : ''].filter(Boolean).join(' · ')].filter(Boolean).join(' · ') || (c.origin === 'SOURCE' ? '' : '아직 기획 전이에요'), videoText(c)].filter(Boolean).join(' · ');
      return '<tr class="' + st + '"><th scope="row"><a class="ov-name" href="' + E(href) + '"><span class="fd-av" aria-hidden="true">' + E(Array.from(l.name)[0] || '?') + '<span class="st ' + st + '"></span></span><span><b>' + E(l.name) + trackHTML(c) + '</b>' + (sub ? '<small>' + E(sub) + '</small>' : '') + '</span></a></th>' +
        '<td class="ov-now">' + statusPill(s.status) + '<span class="ov-now-t">' + now + '</span></td>' +
        '<td><div class="ov-prog">' + segs + '<span class="n">' + (g.ids ? E(g.label) + ' ' : '') + g.done + '/' + g.total + '단계</span></div></td>' +
        '<td class="ov-upd">' + (s.updated ? E(whenText(s.updated)) : '—') + '</td><td class="ov-act">' + act + '</td></tr>';
    }
    function emptyHTML() {
      return '<div class="fl-empty"><span class="ic">' + MARK + '</span><h2>아직 만든 캐릭터가 없어요</h2><p>실존 인물은 인터뷰·대화 원문을 올리면 대화할 수 있는 캐릭터로 만들어요. 지어낸 캐릭터는 브리프로 만들어요.</p>' +
        '<div class="acts"><a class="btn pri" href="sources.html">실존 인물 · 원문으로</a><button type="button" class="btn" data-act="new">새로 지어내기</button></div></div>';
    }
    // 시작하지 않은 모티브 초안: 실행 범위를 고르지 않고 원문 화면으로 보낸다(시작은 원문 화면 한 곳에서만 한다).
    function draftHTML() {
      const d = state.detail;
      return '<section class="fl-tasks" aria-label="지금 할 일"><h2>지금 할 일</h2><div class="fl-item"><span class="mk"></span><div class="tx"><div class="t1">원문을 올리는 중인 초안이에요</div><div class="t2">원문 화면에서 올린 파일을 확인하고 만들기를 시작해요. 시작하면 여기에서 진행을 볼 수 있어요.</div></div>' +
        '<div class="acts"><a class="btn pri" href="sources.html#c/' + E(encodeURIComponent(d.id)) + '">원문 화면에서 이어 하기</a></div></div></section>';
    }
    function setupHTML() {
      const g = state.graph;
      const target = state.target || defaultTarget();
      const opts = g.gates.map((gate) => [gate.id, gate.title + '까지']).concat([['sx', '끝까지 · 우리 앱 내보내기']]);
      const scope = ancestors(g, target);
      let gates = 0;
      let paid = 0;
      scope.forEach((id) => { const s = g.byStage.get(id); if (s && s.gate) gates++; if ((g.paid.get(id) || []).length) paid++; });
      const orch = orchestrator();
      const after = orch.autoResume ? '목표에 닿으면 멈춰요. 그 뒤 검토를 결정하면 ' + E(targetLabel(g, orch.resumeUntil || 'sx')) + ' 자동으로 이어서 진행해요.' : '목표에 닿으면 멈춰요. 이어서 돌릴지는 그때 정해요.';
      return '<section class="fl-setup" aria-label="실행 설정"><div class="fld"><label for="fl-target">어디까지 실행할까요</label><select id="fl-target" data-target>' +
        opts.map((o) => '<option value="' + E(o[0]) + '"' + (o[0] === target ? ' selected' : '') + '>' + E(o[1]) + '</option>').join('') + '</select></div>' +
        (target !== 'G1' && g.byGate.has('G1') ? '<p class="hint fl-first">처음이라면 <button type="button" class="link" data-act="target-first">얼굴 고르기까지</button>만 실행해 보세요. 비용이 드는 영상 단계 전에 멈추고, 첫 결과로 얼굴 후보 10장을 고르게 돼요.</p>' : '') +
        (target !== 'G0' && g.byGate.has('G0') ? '<p class="hint fl-first">처음이라면 <button type="button" class="link" data-act="target-first" data-gate="G0">' + E(g.byGate.get('G0').title) + '까지</button>만 실행해 보세요. 받은 자료를 정리한 출처 묶음을 먼저 확인하게 돼요.</p>' : '') +
        '<div class="sum">전체 ' + g.stages.length + '단계 중 이번 실행 <b>' + scope.size + '단계</b> · 사람 검토 <b>' + gates + '번</b>' + (paid ? ' · 유료 실행 확인 <b>' + paid + '번</b>' : '') + '<br>' + after + '</div>' +
        '<div class="acts"><button type="button" class="btn pri" data-act="start"' + (state.busy ? ' disabled' : '') + '>실행 시작</button></div></section>';
    }
    // 유료 단계는 버튼 한 번에 돈이 나가지 않게, 이번 실행 예상 비용과 지금까지 쓴 비용을 나눠 보이고 한 번 더 확인한다(D-0129).
    function spentText() {
      return state.detail && state.detail.cost && state.detail.cost.estUsd != null ? '$' + Number(state.detail.cost.estUsd).toFixed(2) : '—';
    }
    function planText(stage) {
      const plan = state.plans[stage];
      if (!plan) return { est: null, html: '<p class="est">예상 비용을 계산하는 중이에요…</p>' };
      if (plan.error) return { est: null, html: '<p class="est">예상 비용을 불러오지 못했어요. ' + E(plan.error) + '</p>' };
      // 단가는 모델 → 해상도 → 초당 가격으로 온다. 해상도별 초당 가격만 보인다.
      const unit = Object.keys(plan.unitPrices || {}).map((k) => {
        const v = plan.unitPrices[k];
        return v && typeof v === 'object' ? Object.keys(v).map((r) => r + ' 초당 $' + v[r]).join(', ') : k + ' 초당 $' + v;
      }).join(', ');
      const rows = (plan.plans || []).map((p) => '<li>' + E(p.description) + ' · ' + E(p.calls) + '번 호출' + (p.estUsd != null ? ' · $' + Number(p.estUsd).toFixed(2) : '') + '</li>').join('');
      const est = plan.estUsd != null ? Number(plan.estUsd) : null;
      const head = est != null
        ? '이번 실행 예상 비용 <b>$' + est.toFixed(2) + '</b>' + (unit ? ' · 단가 ' + E(unit) + '(공장 설정 기준)' : '') + (est === 0 ? ' · 시험용 공급자라 비용이 들지 않아요.' : '')
        : '이번 실행 예상 비용을 계산하지 못했어요. ' + E(plan.reason || '단가가 설정되지 않았어요.') + ' 단가를 확인한 뒤 실행해 주세요.';
      return { est, html: '<p class="est">' + head + '</p>' + (rows ? '<ul class="plan-rows">' + rows + '</ul>' : '') };
    }
    async function loadPlan(stage) {
      if (!state.detail || state.plans[stage]) return;
      const id = state.detail.id;
      state.plans[stage] = null;
      try {
        state.plans[stage] = await request('GET', '/api/characters/' + encodeURIComponent(id) + '/stages/' + encodeURIComponent(stage) + '/plan');
      } catch (error) {
        state.plans[stage] = { error: error.message };
      }
      if (state.confirming) render();
    }
    function confirmHTML(stage) {
      const def = state.graph.byStage.get(stage) || { name: stage };
      const held = R.extractHeld(state.detail || {}).find((h) => h.stage === stage) || { providers: [] };
      const providers = ((held.providers || []).length ? held.providers : (state.graph.paid.get(stage) || [])).map(providerKo).join(', ') || '유료 공급자';
      const others = R.extractHeld(state.detail || {}).filter((h) => h.stage !== stage);
      const busy = state.busy || (state.detail && state.detail.job);
      return '<div class="fl-confirm" role="group" aria-label="' + E(def.name + ' 유료 실행 확인') + '"><p><b>' + E(def.name) + '</b> 단계를 <b>' + E(providers) + '</b>로 실행해요.</p>' + planText(stage).html +
        '<p class="spent">지금까지 이 캐릭터에 쓴 추정 비용: ' + E(spentText()) + ' · <a href="help.html#cost" target="_blank" rel="noopener">비용 안내</a></p>' +
        '<div class="acts"><button type="button" class="btn danger" data-act="confirm-go" data-stage="' + E(stage) + '"' + (busy ? ' disabled' : '') + '>' + E(def.name) + ' 유료로 실행</button>' +
        (others.length ? '<button type="button" class="btn" data-act="confirm-all">유료 단계 ' + (others.length + 1) + '개 함께 보기</button>' : '') +
        '<button type="button" class="btn ghost" data-act="confirm-cancel">취소</button></div></div>';
    }
    // 기다리는 유료 단계가 여럿이면 합계를 보고 한 번에 실행할 수 있다(D-0129).
    function confirmAllHTML() {
      const held = R.extractHeld(state.detail || {});
      let total = 0;
      let known = true;
      const parts = held.map((h) => {
        const def = state.graph.byStage.get(h.stage) || { name: h.stage };
        const t = planText(h.stage);
        if (t.est == null) known = false; else total += t.est;
        return '<div class="all-row"><b>' + E(def.name) + '</b>' + t.html + '</div>';
      }).join('');
      const busy = state.busy || (state.detail && state.detail.job);
      return '<div class="fl-confirm" role="group" aria-label="유료 단계 함께 실행 확인"><p>유료 단계 <b>' + held.length + '개</b>를 함께 실행해요.</p>' + parts +
        '<p class="est">' + (known ? '합계 예상 비용 <b>$' + total.toFixed(2) + '</b>' : '일부 단계의 비용을 계산하지 못했어요. 단가를 확인한 뒤 실행해 주세요.') + '</p>' +
        '<p class="spent">지금까지 이 캐릭터에 쓴 추정 비용: ' + E(spentText()) + '</p>' +
        '<div class="acts"><button type="button" class="btn danger" data-act="confirm-all-go"' + (busy ? ' disabled' : '') + '>' + held.length + '개 모두 유료로 실행</button><button type="button" class="btn ghost" data-act="confirm-cancel">취소</button></div></div>';
    }
    function tasksHTML(v) {
      const d = state.detail;
      const now = Date.now();
      const goal = currentUntil();
      // 대화가 준비된 뒤 남은 선택 작업은 직접 시작했을 때만 지금 할 일에 넣는다.
      const optional = isChatReady(d) && goal === 'sx' && (d.lastJob || {}).until !== goal;
      const tasks = buildTasks(state.graph, d, v, { now, gateViews: state.gateViews, jobActive: Boolean(d.job) || state.busy, goal: notStarted() || optional ? '' : goal });
      state.notes = state.notes.filter((n) => now - n.at < 15 * 60000);
      const sum = currentSummary();
      const st = sum ? sum.status.status : '';
      const chat = chatHref(d);
      // 모티브인데 아직 대화할 수 없고 아무것도 돌지 않으면, 대화까지 남은 단계와 이어서 만들 버튼을 먼저 보인다(QA C1).
      let goalLeft = null;
      if (!chat && isMotif(d) && !d.job && !tasks.some((t) => t.kind === 'ready')) {
        const gs = ancestors(state.graph, state.graph.byStage.has('s8c') ? 's8c' : 's8');
        const preds = predecessors(state.graph);
        const left = gs ? state.graph.stages.filter((s) => gs.has(s.id) && (v[s.id] || {}).kind === 'todo') : [];
        // 서버가 마지막 작업에서 시작할 수 없다고 남긴 단계는 권하지 않는다(buildTasks의 '이어서 실행'과 같은 규칙).
        const blocked = new Set(Array.isArray((d.lastJob || {}).blocked) ? d.lastJob.blocked : []);
        const canRun = left.some((s) => !blocked.has(s.id) && Array.from(preds.get(s.id) || []).every((p) => ['done', 'skip'].includes((v[p] || {}).kind)));
        const end = state.graph.byStage.has('s8c') ? 's8c' : 's8';
        if (canRun) goalLeft = { names: left.map((s) => s.name), end };
      }
      // 대화할 수 있으면 '대화해 보기'가 이 화면의 주 버튼이다. 다른 할 일은 그 아래에 보조 버튼으로 남는다.
      if (chat || goalLeft) tasks.forEach((t) => t.actions.forEach((a) => { a.pri = false; }));
      let html = '<section class="fl-tasks" aria-label="지금 할 일" aria-live="polite"><h2>' + (complete() ? '결과' : '지금 할 일') + (tasks.length ? '<span class="num">' + tasks.length + '</span>' : '') + '</h2>';
      if (goalLeft) {
        html += '<div class="fl-item ready"><span class="mk"></span><div class="tx"><div class="t1">대화까지 남은 단계가 있어요</div><div class="t2">' + E(goalLeft.names.join(', ')) + ' 단계가 끝나야 대화해 볼 수 있어요. 이어서 만들면 그 단계까지만 진행해요.</div></div>' +
          '<div class="acts"><button type="button" class="btn pri" data-act="run-stage" data-stage="' + E(goalLeft.end) + '"' + (state.busy ? ' disabled' : '') + '>대화 준비 이어서 하기</button></div></div>';
      }
      if (chat) {
        const t1 = chatStatusText(tasks.filter((t) => t.kind === 'wait').length);
        let t2 = st === 'chat_ready' ? '대화할 수 있어요. 전체 제작 완료 여부는 단계별 진행을 확인해 주세요.' : st === 'running' ? '그동안 다른 단계를 더 만들고 있어요.' : '아래 할 일을 마치지 않아도 대화해 볼 수 있어요.';
        // 영상(약속 5): 만드는 중이면 그렇다고 적고, 영상이 없거나 실패했으면 보조 버튼으로 영상 만들기를 건넨다.
        if (d.videoStatus === 'making') t2 += ' 영상은 만드는 중이에요. 다 되면 대화할 때 영상이 나와요.';
        else if (d.videoStatus === 'ready') t2 = st === 'chat_ready' ? '영상도 준비됐어요. 대화해 보기에서 영상과 함께 대화해요. 남은 제작 단계는 진행 화면에서 확인해 주세요.' : t2;
        else if (d.videoStatus === 'failed') t2 += ' 영상은 만들지 못했어요' + (d.videoError ? ': ' + plainError(d.videoError) : '.');
        const vOpen = Boolean(state.video && state.video.open);
        const vBtn = canMakeVideo(d) && !(referenceState && referenceState.enabled) ? '<button type="button" class="btn" data-act="video-open" aria-expanded="' + vOpen + '">' + icon('video') + (d.videoStatus === 'failed' ? '영상 다시 만들기' : d.videoStatus === 'ready' ? '영상 바꾸기' : '영상 만들기') + '</button>' : '';
        html += '<div class="fl-item ok"><span class="mk"></span><div class="tx"><div class="t1">' + E(t1) + '</div><div class="t2">' + E(t2) + '</div></div><div class="acts"><a class="btn pri" href="' + E(chat) + '">' + icon('chat') + (d.videoStatus === 'ready' ? '영상과 함께 대화해 보기' : '대화해 보기') + '</a>' + vBtn + '</div>' +
          (vBtn && vOpen ? videoHTML(d) : '') +
          (st === 'chat_ready' && !tasks.length && !d.job && !vOpen ? moreBuildHTML() : '') + '</div>';
      }
      // '다음 검토'는 그릴 때마다 새 상태로 다시 고른다(결정 직후 새 검토가 생길 수 있다).
      state.notes.forEach((n) => { if (n.act === 'next-review') { const nr = nextReviewAfter(n.gate); n.label = nr ? nr.label : ''; } });
      const notesHTML = state.notes.map((n) => '<div class="fl-note' + (n.tone === 'bad' ? ' bad' : '') + '">' + icon(n.tone === 'bad' ? 'x' : 'ok') + '<div>' + E(n.t) + (n.s ? ' <span>' + E(n.s) + '</span>' : '') + '</div>' + (n.act && n.label ? '<button type="button" class="btn" data-act="' + E(n.act) + '"' + (n.gate ? ' data-gate="' + E(n.gate) + '"' : '') + '>' + E(n.label) + '</button>' : '') + '<time>' + E(now - n.at < 60000 ? '방금' : clock(new Date(n.at).toISOString())) + '</time></div>').join('');
      if (complete()) {
        html += '<div class="fl-item ok"><span class="mk"></span><div class="tx"><div class="t1">출시 묶음이 준비됐어요</div><div class="t2">모든 단계를 마쳤어요. 릴리즈 패키지에서 묶음 구성과 사람 검토 기록을 볼 수 있어요.</div></div><div class="acts"><button type="button" class="btn pri" data-act="select" data-stage="s11">결과 보기</button></div></div>';
      }
      tasks.forEach((t) => {
        const confirmingAll = t.kind === 'confirm' && state.confirming === '__all' && t === tasks.find((x) => x.kind === 'confirm');
        const confirming = t.kind === 'confirm' && (state.confirming === t.stage || confirmingAll);
        html += '<div class="fl-item ' + t.kind + '"><span class="mk"></span><div class="tx"><div class="t1">' + E(t.title) + (t.age ? '<span class="age">' + E(t.age) + '</span>' : '') + '</div><div class="t2">' + E(t.body) + (t.blocked ? ' 뒤의 ' + t.blocked + '단계가 이 일을 기다리고 있어요.' : '') + '</div>' + (t.rec ? '<div class="rec">' + icon('spark') + E(t.rec) + '</div>' : '') + '</div>' +
          (confirming ? (confirmingAll ? confirmAllHTML() : confirmHTML(t.stage)) : '<div class="acts">' +
          t.actions.map((a) => '<button type="button" class="btn' + (a.pri ? ' pri' : '') + '" data-act="' + a.act + '"' + (a.gate ? ' data-gate="' + E(a.gate) + '"' : '') + (a.stage ? ' data-stage="' + E(a.stage) + '"' : '') + (a.anchor ? ' data-anchor="' + E(a.anchor) + '"' : '') + (a.step ? ' data-step="' + E(a.step) + '"' : '') + (a.v ? ' data-v="' + E(a.v) + '"' : '') + (a.disabled ? ' disabled' : '') + '>' + E(a.label) + '</button>' + (a.why ? '<span class="hint">' + E(a.why) + '</span>' : '')).join('') + '</div>') + '</div>';
      });
      if (notesHTML) html += '<div class="fl-recent"><h3>방금 한 일</h3>' + notesHTML + '</div>';
      if (!tasks.length && !complete()) {
        if (d.job) html += '<div class="fl-note">' + icon('ok') + '<div>지금은 기다리면 돼요. <span>사람이 할 일이 생기면 여기에 나타나요.</span></div></div>';
        else if (!chat && !goalLeft) {
          const goal = currentUntil() || orchestrator().resumeUntil || 'sx';
          html += '<div class="fl-item"><span class="mk"></span><div class="tx"><div class="t1">진행 중인 작업이 없어요</div><div class="t2">이어서 실행하면 멈춘 지점부터 ' + E(targetLabel(state.graph, goal)) + ' 진행해요.</div></div><div class="acts"><button type="button" class="btn pri" data-act="resume"' + (state.busy ? ' disabled' : '') + '>이어서 실행</button></div></div>';
        }
      }
      return html + '</section>';
    }
    // 영상 만들기 고르기(약속 5). 사진이 없으면 원문 화면으로 보내고, 있으면 등급 카드와 시작 버튼을 보인다.
    function videoHTML(d) {
      const v = state.video || {};
      const src = 'sources.html#c/' + encodeURIComponent(d.id);
      const photoLink = '<a class="btn" href="' + E(src) + '">원문 화면에서 사진 올리기</a>';
      const close = '<button type="button" class="btn ghost" data-act="video-cancel">닫기</button>';
      if (v.photos == null) return '<div class="fl-vid" role="group" aria-label="영상 만들기"><p>올린 사진을 확인하는 중이에요…</p></div>';
      // 사진은 원문과 함께 처음 만들 때 올린다. 이미 만든 캐릭터에는 사진을 덧붙일 수 없어서 새로 만드는 길을 안내한다.
      if (v.photos === 0) return '<div class="fl-vid" role="group" aria-label="영상 만들기"><p>이 캐릭터는 만들 때 사진을 올리지 않아서 영상을 만들 수 없어요. 원문 화면에서 사진과 원문을 함께 올려 새로 만들어 주세요.</p><div class="acts"><a class="btn" href="sources.html">원문 화면에서 새로 만들기</a>' + close + '</div></div>';
      const busy = Boolean(v.busy || state.busy);
      const sig = v.sig || {};
      // 시그니처 포즈(D-0165): 모든 등급에 한 편씩. 이미 정했으면 채워 두고 고칠 수 있게 한다.
      const sigHTML = '<div class="fl-sig" role="group" aria-labelledby="fl-sig-h"><p id="fl-sig-h"><b>시그니처 포즈</b> 모든 등급에 한 편씩 들어가요.</p>' +
        '<label for="fl-sig-title">이름</label><input id="fl-sig-title" data-sig="title" maxlength="30" autocomplete="off" placeholder="예: 찰칵 세리머니" value="' + E(sig.title || '') + '"' + (busy ? ' disabled' : '') + '>' +
        '<label for="fl-sig-motion">어떤 동작인가요</label><textarea id="fl-sig-motion" data-sig="motion" rows="2" maxlength="400" placeholder="예: 두 손으로 카메라 모양을 만들어 눈앞에 대고 찰칵 누르는 시늉을 해요."' + (busy ? ' disabled' : '') + '>' + E(sig.motion || '') + '</textarea>' +
        '<label for="fl-sig-when">언제 나오면 좋을까요 <span class="opt">선택</span></label><input id="fl-sig-when" data-sig="useWhen" maxlength="200" autocomplete="off" placeholder="예: 골이나 축하 얘기를 할 때" value="' + E(sig.useWhen || '') + '"' + (busy ? ' disabled' : '') + '></div>';
      return '<div class="fl-vid" role="group" aria-label="영상 만들기"><div class="vt-grid" role="radiogroup" aria-label="영상 등급">' + tierCardsHTML('videoTierPick', v.tier, { paidOnly: true, disabled: busy }) + '</div>' + sigHTML +
        '<p>영상 단계는 비용이 들어요. 시작하면 배경 하나·같은 옷으로 고른 등급의 몸짓 영상을 만들고, 다 되면 대화할 때 영상이 나와요.' + (d.videoStatus === 'ready' ? ' 이미 만든 몸짓은 그대로 두고 새로 생기거나 바뀐 영상만 만들어요.' : '') + ' 후보는 첫 번째로 자동으로 골라요.</p>' +
        (v.error ? '<p class="err" role="alert">' + E(v.error) + '</p>' : '') +
        '<div class="acts"><button type="button" class="btn" data-act="video-go"' + (busy ? ' disabled' : '') + '>' + (v.busy ? '시작하는 중…' : E(tierName(v.tier)) + ' 영상 만들기 시작') + '</button>' + (v.noPhoto ? photoLink : '') + '<button type="button" class="btn ghost" data-act="video-cancel">취소</button></div></div>';
    }
    async function openVideo() {
      if (referenceState && referenceState.enabled) return;
      const d = state.detail;
      if (!d) return;
      const id = d.id;
      const t = tierOf(d.videoTier);
      const s = d.signaturePose || {};
      state.video = { open: true, tier: t === 'none' ? 'light' : t, photos: null, busy: false, error: '', sig: { title: text(s.title), motion: text(s.motion), useWhen: text(s.useWhen) } };
      render();
      let n = -1; // 원문 초안을 읽지 못하면 모른다(-1). 그때는 고르게 두고 서버가 막으면 그 문장을 보인다.
      try { n = readyPhotos(await request('GET', '/api/sources/' + encodeURIComponent(id))); } catch (error) { n = -1; }
      if (state.video && state.detail && state.detail.id === id) { state.video.photos = n; render(); }
    }
    async function startVideo() {
      if (referenceState && referenceState.enabled) return;
      const d = state.detail;
      const v = state.video;
      if (!d || !v || v.busy) return;
      const tier = tierOf(v.tier) === 'none' ? 'light' : v.tier;
      const sig = v.sig || {};
      const signaturePose = { title: text(sig.title).trim(), motion: text(sig.motion).trim(), useWhen: text(sig.useWhen).trim() };
      if (!signaturePose.title || !signaturePose.motion) {
        v.error = '시그니처 포즈의 이름과 어떤 동작인지 적어 주세요.';
        render();
        const el = doc.querySelector(signaturePose.title ? '#fl-sig-motion' : '#fl-sig-title');
        if (el) el.focus();
        return;
      }
      v.busy = true;
      v.error = '';
      render();
      try {
        await request('POST', '/api/characters/' + encodeURIComponent(d.id) + '/videos', { videoTier: tier, signaturePose });
        state.video = null;
        state.feedback = { tone: 'ok', text: tierName(tier) + ' 영상을 만들기 시작했어요. 다 되면 대화할 때 영상이 나와요.' };
      } catch (error) {
        v.busy = false;
        v.error = error.status === 404 || error.status === 405 ? '이 서버에서는 아직 영상을 만들 수 없어요.' : error.message;
        v.noPhoto = /사진/.test(v.error);
        if (error.network) state.conn = 'offline';
      }
      await refresh(false);
    }
    function moreBuildHTML() {
      const next = 'sx';
      const v = views(null);
      const left = Array.from(ancestors(state.graph, next)).filter((id) => !['done', 'skip'].includes((v[id] || {}).kind));
      if (!left.length) return '';
      const names = state.graph.lanes.filter((lane) => laneIds(lane).some((id) => left.indexOf(id) >= 0)).map((lane) => lane.label);
      const label = targetLabel(state.graph, next);
      const open = Boolean(state.moreOpen);
      return '<div class="fl-more"><button type="button" class="link fl-more-btn" data-act="more" aria-expanded="' + open + '">' + icon(open ? 'up' : 'down') + '더 만들기 (선택)</button>' +
        (open ? '<div class="fl-more-body"><p>' + E(label) + ' 이어서 만들어요' + (left.length ? ' · 남은 단계 ' + left.length + '개' + (names.length ? '(' + names.join(', ') + ')' : '') : '') + '. 모델을 더 부르기 때문에 비용이 들 수 있어요. 이미지·영상·학습처럼 비용이 큰 단계는 시작하기 전에 한 번 더 물어봐요.</p>' +
          '<button type="button" class="btn" data-act="resume-more" data-until="' + E(next) + '"' + (state.busy ? ' disabled' : '') + '>' + E(label) + ' 이어서 실행</button></div>' : '') + '</div>';
    }

    // ---- 그래프 ----
    function laneIds(lane) { return (lane.stages || []).map((s) => (typeof s === 'string' ? s : s.id)).filter((id) => state.graph.byStage.has(id)); }
    function cardHTML(lane, v, laneKinds, gv) {
      const area = AREA[lane.id] || lane.id;
      const ids = laneIds(lane).filter((id) => !gv.keep || gv.keep.has(id));
      if (!ids.length) return '';
      const lk = laneKinds[lane.id];
      const done = ids.filter((id) => v[id].kind === 'done' || v[id].kind === 'skip').length;
      const collapsed = lk === 'done' && !state.open.has(lane.id);
      const outish = lk === 'out' || lk === 'skip';
      const tag = lk === 'skip' ? '<span class="fl-tag">건너뜀</span>' : lk === 'out' ? '<span class="fl-tag">' + (gv.ids ? '목표 밖' : '범위 밖') + '</span>' : '';
      let html = '<div class="fl-card' + (collapsed ? ' col' : '') + (outish ? ' out' : '') + '" data-lane="' + E(lane.id) + '" style="grid-area:' + E(area) + '">' +
        '<button type="button" class="fl-ch" data-act="toggle" data-lane="' + E(lane.id) + '" aria-expanded="' + (!collapsed) + '"' + (lk === 'done' ? '' : ' aria-disabled="true"') + '><span class="ld ' + (outish ? 'todo' : lk) + '"></span><span class="ln">' + E(lane.label) + '</span>' + tag +
        '<span class="cnt">' + (outish ? '' : (lk === 'done' ? icon('check') : '') + done + '/' + ids.length + (lk === 'done' ? icon(collapsed ? 'down' : 'up') : '')) + '</span></button>';
      if (!collapsed) {
        ids.forEach((id) => {
          const def = state.graph.byStage.get(id);
          // 펼쳐 본 모티브의 목표 밖 단계는 흐리게, 상태 글 없이 보인다.
          const x = gv.ids && !gv.ids.has(id) && v[id].kind === 'todo' ? { kind: 'out', sub: '' } : v[id];
          const paid = (state.graph.paid.get(id) || []).length;
          const marks = (def.gate ? icon('user', '사람 검토 있음') : '') + (paid && (x.kind === 'todo' || x.kind === 'confirm') ? icon('coins', '유료 단계') : '');
          const sub = x.sub ? '<span class="sb" title="' + E(x.sub) + '">' + (x.retry ? icon('retry') + ' ' : '') + E(x.sub) + '</span>' : '';
          const glyph = x.kind === 'done' ? icon('check') : x.kind === 'fail' ? icon('x') : x.kind === 'confirm' ? icon('coins') : x.kind === 'skip' ? icon('minus') : '';
          html += '<button type="button" class="fl-row ' + x.kind + '" data-act="select" data-stage="' + E(id) + '" aria-pressed="' + (state.sel === id) + '" aria-label="' + E(def.name + ', ' + (x.kind === 'out' && gv.ids ? '목표 밖' : KIND_LABEL[x.kind]) + (x.sub ? ', ' + x.sub : '') + (def.gate ? ', 사람 검토 있음' : '') + (paid ? ', 유료 단계' : '')) + '">' +
            '<span class="si ' + x.kind + '">' + glyph + '</span><span class="nw"><span class="nm">' + stageNameHTML(def.name, marks) + '</span>' + sub + gateSub(def) + '</span></button>';
        });
      }
      return html + '</div>';
    }
    // 할 일 목록은 관문 이름(예: 얼굴 고르기)을 쓰고 그래프는 단계 이름(레퍼런스 선별)을 쓴다. 둘을 잇는다(D-0129).
    function stageHint(def) {
      const hint = state.graph.origin === 'SOURCE' ? TWIN_HINT[def.id] : '';
      if (hint) return hint;
      if (!def.gate) return '';
      const g = state.graph.byGate.get(def.gate);
      // 검토 이름의 첫 낱말이 단계 이름에 이미 있으면(소개 영상 ↔ 소개 영상 고르기) 덧붙이지 않는다.
      const head = g && g.title ? text(g.title).split(/[\s·]/)[0] : '';
      return head && text(def.name).indexOf(head) < 0 ? '검토: ' + g.title : '';
    }
    // 모티브 그래프는 칸이 좁아 이 설명을 한 줄로 줄인다. 전체 글은 title과 인스펙터 '하는 일'에 있다.
    function gateSub(def) {
      const h = stageHint(def);
      return h ? '<span class="gt" title="' + E(h) + '">' + E(h) + '</span>' : '';
    }
    function renderGraph(v, scope) {
      if (!state.detail) { region.graph.hidden = true; return; }
      region.graph.hidden = false;
      const gv = goalView(state.graph, state.detail, v, state.showOff);
      let cls = (state.graph.layout || layoutOf(state.graph)).cls;
      state.goalCell = null;
      ['--goal-cols', '--goal-areas', '--goal-stack'].forEach((k) => region.grid.style.removeProperty(k));
      if (gv.keep) {
        // 접은 그래프는 남은 팀만 한 줄로 순서대로 선다. 휴대폰 폭에서는 한 열로 쌓는다.
        const areas = state.graph.lanes.filter((lane) => laneIds(lane).some((id) => gv.keep.has(id))).map((lane) => AREA[lane.id] || lane.id);
        cls += ' goal';
        region.grid.style.setProperty('--goal-cols', String(Math.max(1, areas.length)));
        region.grid.style.setProperty('--goal-areas', '"' + areas.join(' ') + '"');
        region.grid.style.setProperty('--goal-stack', areas.map((a) => '"' + a + '"').join(' '));
        state.goalCell = {};
        areas.forEach((a, i) => { state.goalCell[a] = [0, i]; });
      }
      region.grid.className = 'fl-grid' + (cls ? ' ' + cls : '');
      const laneKinds = {};
      state.graph.lanes.forEach((lane) => { laneKinds[lane.id] = laneKind(laneIds(lane).filter((id) => !gv.keep || gv.keep.has(id)), v); });
      region.grid.innerHTML = state.graph.lanes.map((lane) => cardHTML(lane, v, laneKinds, gv)).join('');
      if (region.offgoal) {
        const offLanes = gv.ids ? state.graph.lanes.filter((lane) => laneIds(lane).every((id) => !gv.ids.has(id))).map((lane) => lane.label) : [];
        region.offgoal.innerHTML = gv.ids && gv.hidden ? '<button type="button" class="link" data-act="show-off" aria-expanded="' + Boolean(state.showOff) + '">' + icon(state.showOff ? 'up' : 'down') + (state.showOff ? '목표 밖 단계 접기' : '목표 밖 단계 ' + gv.hidden + '개 보기') + '</button>' + (state.showOff || !offLanes.length ? '' : '<span class="hint">' + E(offLanes.join('·')) + '처럼 대화에 꼭 필요하지 않은 단계예요.</span>') : '';
        region.offgoal.hidden = !(gv.ids && gv.hidden);
      }
      if (region.zoombar) region.zoombar.hidden = Boolean(gv.keep);
      // 접은 그래프는 팀 몇 개뿐이라 연결선 범례가 필요 없다.
      region.legend.hidden = Boolean(gv.keep);
      region.legend.innerHTML = scope
        ? '<span><i class="done"></i>이번 실행에 포함</span><span><i class="todo"></i>범위 밖</span><span>' + icon('user') + '사람 검토</span><span>' + icon('coins') + '유료 실행 확인</span>'
        : [['flow', '지금 진행 중'], ['block', '사람을 기다리며 멈춤'], ['stop', '실패로 멈춤']].map((x) => '<span><svg class="lg" viewBox="0 0 24 6" width="24" height="6" aria-hidden="true"><line class="e ' + x[0] + '" x1="1" y1="3" x2="23" y2="3"/></svg>' + x[1] + '</span>').join('') + '<span>' + icon('user') + '사람 검토</span><span>' + icon('coins') + '유료 실행 확인</span>';
      applyZoomStyle();
      renderZoombar();
      requestAnimationFrame(() => drawEdges(v));
    }
    // 화면 맞춤이 기본이다(z=1, 이동 없음). 확대했을 때만 보기 영역을 고정하고 끌거나 휠로 옮긴다.
    // 연결선은 확대하지 않는 덮개(svg)에 화면 좌표로 다시 그려 선 굵기가 그대로다.
    const zoom = { z: 1, x: 0, y: 0, h: 0 };
    const ZSTEPS = [0.75, 1, 1.25, 1.5, 2];
    function zoomed() { return zoom.z !== 1 || zoom.x !== 0 || zoom.y !== 0; }
    function stacked() { return !region.svg || !global.getComputedStyle || global.getComputedStyle(region.svg).display === 'none'; }
    function applyZoomStyle() {
      if (!region.view) return;
      const on = zoomed() && !stacked();
      if (on && !zoom.h) zoom.h = Math.max(240, region.grid.offsetHeight + 8);
      if (!on) zoom.h = 0;
      region.graph.classList.toggle('zoomed', on);
      region.view.style.height = on && !state.focus ? zoom.h + 'px' : '';
      region.grid.style.transform = on ? 'translate(' + Math.round(zoom.x) + 'px,' + Math.round(zoom.y) + 'px) scale(' + zoom.z + ')' : '';
    }
    function renderZoombar() {
      if (!region.zoombar) return;
      const pct = Math.round(zoom.z * 100);
      region.zoombar.innerHTML = '<button type="button" data-act="zoom-out" aria-label="축소" title="축소 (−)"' + (zoom.z <= ZSTEPS[0] ? ' disabled' : '') + '>' + icon('minus') + '</button>' +
        '<span class="pct" role="status" aria-label="' + pct + '% 크기">' + pct + '%</span>' +
        '<button type="button" data-act="zoom-in" aria-label="확대" title="확대 (+)"' + (zoom.z >= ZSTEPS[ZSTEPS.length - 1] ? ' disabled' : '') + '>' + icon('plus') + '</button>' +
        '<button type="button" data-act="zoom-fit" title="화면에 맞추기 (0)"' + (zoomed() ? '' : ' disabled') + '>맞춤</button><span class="sep" aria-hidden="true"></span>' +
        '<button type="button" data-act="focus" aria-pressed="' + state.focus + '" title="' + (state.focus ? '원래 보기 (Esc)' : '왼쪽 탐색과 할 일을 접고 그래프를 넓게 봐요') + '">' + icon(state.focus ? 'shrink' : 'expand') + (state.focus ? '원래 보기' : '크게 보기') + '</button>';
    }
    function clampPan() {
      const r = region.view.getBoundingClientRect();
      const gw = region.grid.offsetWidth * zoom.z;
      const gh = region.grid.offsetHeight * zoom.z;
      const vh = zoom.h || r.height;
      zoom.x = Math.min(Math.max(0, r.width - gw) + 48, Math.max(Math.min(0, r.width - gw) - 48, zoom.x));
      zoom.y = Math.min(Math.max(0, vh - gh) + 48, Math.max(Math.min(0, vh - gh) - 48, zoom.y));
    }
    function redrawZoom() { applyZoomStyle(); renderZoombar(); if (state.detail) drawEdges(views(setupScope())); }
    function zoomTo(nz, cx, cy) {
      if (stacked()) return;
      nz = Math.min(ZSTEPS[ZSTEPS.length - 1], Math.max(ZSTEPS[0], Math.round(nz * 100) / 100));
      const r = region.view.getBoundingClientRect();
      if (cx == null) { cx = r.width / 2; cy = Math.min(r.height, region.grid.offsetHeight) / 2; }
      zoom.x = cx - (cx - zoom.x) * (nz / zoom.z);
      zoom.y = cy - (cy - zoom.y) * (nz / zoom.z);
      zoom.z = nz;
      if (Math.abs(nz - 1) < 0.001 && Math.abs(zoom.x) < 2 && Math.abs(zoom.y) < 2) { zoom.x = 0; zoom.y = 0; }
      clampPan();
      redrawZoom();
    }
    function zoomStep(dir) {
      const next = dir > 0 ? ZSTEPS.find((s) => s > zoom.z + 0.001) : ZSTEPS.slice().reverse().find((s) => s < zoom.z - 0.001);
      if (next != null) zoomTo(next);
    }
    function zoomFit() { zoom.z = 1; zoom.x = 0; zoom.y = 0; redrawZoom(); }
    function toggleFocus(on) {
      state.focus = on == null ? !state.focus : on;
      if (region.shell) region.shell.classList.toggle('focus', state.focus);
      zoomFit();
      render();
    }
    let drag = null;
    let swallowClick = false;
    function onDown(event) {
      if (!zoomed() || stacked() || event.button !== 0) return;
      drag = { x: event.clientX, y: event.clientY, ox: zoom.x, oy: zoom.y, moved: false, id: event.pointerId };
    }
    function onMove(event) {
      if (!drag) return;
      const dx = event.clientX - drag.x;
      const dy = event.clientY - drag.y;
      if (!drag.moved && Math.abs(dx) + Math.abs(dy) < 5) return;
      if (!drag.moved) { drag.moved = true; region.graph.classList.add('panning'); try { region.view.setPointerCapture(drag.id); } catch (error) { /* 무시 */ } }
      zoom.x = drag.ox + dx;
      zoom.y = drag.oy + dy;
      clampPan();
      applyZoomStyle();
      if (state.detail) drawEdges(views(setupScope()));
    }
    function onUp() {
      if (drag && drag.moved) swallowClick = true;
      drag = null;
      region.graph.classList.remove('panning');
    }
    function onWheel(event) {
      if (stacked()) return;
      if (event.ctrlKey || event.metaKey) {
        event.preventDefault();
        const r = region.view.getBoundingClientRect();
        zoomTo(zoom.z * Math.exp(-event.deltaY * 0.004), event.clientX - r.left, event.clientY - r.top);
      } else if (zoomed()) {
        event.preventDefault();
        zoom.x -= event.deltaX;
        zoom.y -= event.deltaY;
        clampPan();
        applyZoomStyle();
        if (state.detail) drawEdges(views(setupScope()));
      }
    }
    function onViewKey(event) {
      if (event.target !== region.view) return;
      const k = event.key;
      if (k === '+' || k === '=') { event.preventDefault(); zoomStep(1); }
      else if (k === '-' || k === '_') { event.preventDefault(); zoomStep(-1); }
      else if (k === '0') { event.preventDefault(); zoomFit(); }
      else if (zoomed() && ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(k)) {
        event.preventDefault();
        const step = 48;
        if (k === 'ArrowLeft') zoom.x += step; if (k === 'ArrowRight') zoom.x -= step; if (k === 'ArrowUp') zoom.y += step; if (k === 'ArrowDown') zoom.y -= step;
        clampPan();
        redrawZoom();
      }
    }
    function anchor(id, side, box) {
      const lanes = laneMap(state.graph);
      const card = region.grid.querySelector('.fl-card[data-lane="' + lanes.get(id) + '"]');
      if (!card) return null;
      const cr = card.getBoundingClientRect();
      const row = card.querySelector('.fl-row[data-stage="' + id + '"]');
      const r = row ? row.getBoundingClientRect() : card.querySelector('.fl-ch').getBoundingClientRect();
      const y = row ? r.top + Math.min(r.height / 2, 17) : r.top + r.height / 2;
      return { x: (side === 'r' ? cr.right : cr.left) - box.left, y: y - box.top, lane: lanes.get(id) };
    }
    function drawEdges(v) {
      const svg = region.svg;
      if (!svg || region.graph.hidden) return;
      const box = (region.view || region.graph).getBoundingClientRect();
      if (getComputedStyle(svg).display === 'none') { svg.innerHTML = ''; return; }
      svg.setAttribute('width', box.width);
      svg.setAttribute('height', box.height);
      const colour = { flow: 'var(--fd-run-solid)', block: 'var(--fd-attention-solid)', stop: 'var(--fd-danger-solid)', done: 'var(--fd-slate-8)', todo: 'var(--fd-slate-7)', out: 'var(--fd-slate-6)' };
      const cell = state.goalCell || (state.graph.layout || layoutOf(state.graph)).cell;
      const cardTop = (lane) => { const el = region.grid.querySelector('.fl-card[data-lane="' + lane + '"]'); return el ? el.getBoundingClientRect().top - box.top : null; };
      let out = '';
      crossLaneEdges(state.graph).forEach(([a, b]) => {
        const A = anchor(a, 'r', box);
        const B = anchor(b, 'l', box);
        if (!A || !B) return;
        const cls = edgeClass(state.graph, v, a, b);
        const ca = cell[AREA[A.lane]];
        const cb = cell[AREA[B.lane]];
        let d;
        // 사이에 다른 팀이 있으면 그 팀들 위 틈으로 돌아간다. 두 줄 가운데 선 팀(출처·패키지)은 상대 팀의 줄을 따른다.
        const row = !ca || !cb ? null : ca[0] === cb[0] ? ca[0] : ca[0] === 0.5 ? cb[0] : cb[0] === 0.5 ? ca[0] : null;
        const tops = row != null && row !== 0.5 && cb[1] - ca[1] > 1
          ? state.graph.lanes.filter((lane) => { const c = cell[AREA[lane.id]]; return c && c[0] === row && c[1] > ca[1] && c[1] < cb[1]; }).map((lane) => cardTop(lane.id)).filter((t) => t != null)
          : [];
        if (tops.length) {
          const yt = Math.min.apply(null, tops) - 14;
          const g1 = A.x + 16;
          const g2 = B.x - 16;
          const r = 8;
          d = 'M' + A.x + ' ' + A.y + ' L' + (g1 - r) + ' ' + A.y + ' Q' + g1 + ' ' + A.y + ' ' + g1 + ' ' + (A.y - r) + ' L' + g1 + ' ' + (yt + r) + ' Q' + g1 + ' ' + yt + ' ' + (g1 + r) + ' ' + yt + ' L' + (g2 - r) + ' ' + yt + ' Q' + g2 + ' ' + yt + ' ' + g2 + ' ' + (yt + r) + ' L' + g2 + ' ' + (B.y - r) + ' Q' + g2 + ' ' + B.y + ' ' + (g2 + r) + ' ' + B.y + ' L' + B.x + ' ' + B.y;
        } else {
          const dx = Math.max(16, (B.x - A.x) * 0.5);
          d = 'M' + A.x + ' ' + A.y + ' C' + (A.x + dx) + ' ' + A.y + ',' + (B.x - dx) + ' ' + B.y + ',' + B.x + ' ' + B.y;
        }
        out += '<path class="e ' + cls + '" d="' + d + '"/>' + (cls === 'out' ? '' : '<circle class="pt" cx="' + A.x + '" cy="' + A.y + '" r="3" style="stroke:' + colour[cls] + '"/><circle class="pt" cx="' + B.x + '" cy="' + B.y + '" r="3" style="stroke:' + colour[cls] + '"/>');
      });
      svg.innerHTML = out;
    }

    // ---- 인스펙터 ----
    function historyHTML(id) {
      const hist = (state.detail.history && state.detail.history[id]) || [];
      if (!hist.length) return '';
      // 끝내 성공한 단계라면 그 전에 실패한 시도는 '이전 시도 N회' 아래로 접는다.
      const kind = (views(null)[id] || {}).kind;
      const parts = splitAttempts(hist, kind === 'done' || kind === 'wait');
      const item = (a) => {
        const took = parseTime(a.startedAt) != null && parseTime(a.endedAt) != null ? span(parseTime(a.endedAt) - parseTime(a.startedAt)) : '';
        const result = a.result === 'CHECK_FAILED' ? '실패' : a.result === 'AWAITING_HUMAN' ? '검토로 넘김' : a.result === 'APPROVED' ? '완료' : a.result === 'RESTARTED' ? '다시 시작됨' : a.result === 'SKIPPED' ? '건너뜀' : a.result ? a.result : '진행 중';
        const decision = a.decision === 'APPROVED' ? ' → 통과' : a.decision === 'REJECTED' ? ' → 다시 만들기' : '';
        const tone = a.result === 'CHECK_FAILED' ? 'bad' : !a.result ? 'run' : a.decision === 'APPROVED' || a.result === 'APPROVED' ? 'ok' : a.result === 'AWAITING_HUMAN' && !a.decision ? 'wait' : '';
        return '<li class="' + tone + '"><b>' + E(a.attempt || '?') + '번째 시도</b> · ' + E(result + decision) + '<br>' + E(clock(a.startedAt)) + (took ? ' · ' + E(took) : '') + (a.rev ? ' · ' + E(revLabel(a.rev)) : '') + (a.error ? '<span class="err">' + E(failReason(a.error).summary) + '</span>' : '') + '</li>';
      };
      const earlier = parts.earlier.length ? '<details class="fl-earlier"><summary>이전 시도 ' + parts.earlier.length + '회</summary><ul class="fl-hist">' + parts.earlier.slice().reverse().map(item).join('') + '</ul></details>' : '';
      return '<section class="ins-sec"><h3>실행 기록</h3><ul class="fl-hist">' + parts.shown.slice().reverse().map(item).join('') + '</ul>' + earlier + '</section>';
    }
    function panelHTML(v) {
      const d = state.detail;
      const id = state.sel;
      const def = state.graph.byStage.get(id);
      if (!def) return '<div class="ins-empty">그래프에서 단계를 누르면 자세한 내용이 여기에 나와요.</div>';
      const row = rowsById(d).get(id) || {};
      const x = v[id];
      const gate = def.gate ? gatesById(d).get(def.gate) || {} : null;
      const lane = state.graph.lanes.find((l) => (l.stages || []).some((s) => (typeof s === 'string' ? s : s.id) === id));
      const props = [];
      const prop = (k, val, cls) => { if (val) props.push('<dt>' + E(k) + '</dt><dd' + (cls ? ' class="' + cls + '"' : '') + '>' + val + '</dd>'); };
      if (state.graph.origin === 'SOURCE') prop('하는 일', E(stageHint(def)));
      prop('상태', E(x.sub || KIND_LABEL[x.kind]));
      const gs = ancestors(state.graph, state.graph.byStage.has('s8c') ? 's8c' : 's8');
      if (gs && !gs.has(id)) prop('목표', '대화하는 데 꼭 필요한 단계는 아니에요');
      prop('버전', row.rev ? E(revLabel(row.rev)) : '');
      prop('시작', row.startedAt ? E(clock(row.startedAt)) : '');
      prop('걸린 시간', row.startedAt && row.endedAt ? E(span(parseTime(row.endedAt) - parseTime(row.startedAt))) : '');
      if (gate) {
        const gs = upper(gate.status);
        prop('사람 검토', E(gs === 'AWAITING_HUMAN' ? (gate.openedAt ? clock(gate.openedAt) + '부터 대기 · ' + since(gate.openedAt, Date.now()) : '대기 중') : gs === 'APPROVED' ? '통과' + (gate.decidedAt ? ' · ' + clock(gate.decidedAt) : '') : '끝나면 검토해요'));
      }
      const paid = state.graph.paid.get(id) || [];
      if (paid.length) prop('유료 공급자', E(paid.map(providerKo).join(', ')));
      if (x.kind === 'out') prop('범위', '이번 실행 범위 밖이에요');
      if (row.lastError && x.kind === 'fail') {
        const why = failReason(row.lastError);
        prop('실패 이유', E(why.summary) + (why.detail ? '<details class="fd-tech"><summary>기술 정보</summary><pre>' + E(why.detail) + '</pre><button type="button" class="btn" data-act="copy-error" data-stage="' + E(id) + '">' + icon('copy') + '오류 내용 복사</button></details>' : ''), 'bad');
      }
      const view = gate ? state.gateViews.get(def.gate + '|' + text(gate.rev)) : null;
      const thumbs = view && Array.isArray(view.previews) ? view.previews.filter((f) => f.kind === 'image' && R.safeHref(f.url)).slice(0, 4) : [];
      const busy = Boolean(d.job) || state.busy;
      const acts = [];
      const trv = id === 's10t' ? trainingOf(d) : null;
      const managed = trv && ['plan', 'stopped', 'fail', 'hold', 'run', 'skip'].includes(trv.state);
      if (managed) {
        if (trv.state === 'hold') acts.push('<button type="button" class="btn pri block" data-act="train-retry"' + (busy ? ' disabled' : '') + '>다시 받아 오기</button>');
        if (['plan', 'stopped', 'fail'].includes(trv.state)) acts.push('<button type="button" class="btn pri block" data-act="mconfirm" data-v="start" data-step="train"' + (busy ? ' disabled' : '') + '>' + (trv.state === 'plan' ? '학습 시작' : '다시 학습') + '</button>');
      }
      if (x.kind === 'wait') acts.push('<button type="button" class="btn pri block" data-act="review" data-gate="' + E(def.gate) + '" data-stage="' + E(id) + '">검토하기</button>');
      if (x.kind === 'confirm' && !managed) acts.push('<button type="button" class="btn pri block" data-act="confirm" data-stage="' + E(id) + '"' + (busy ? ' disabled' : '') + '>비용 확인</button>');
      if (x.kind === 'fail' && !managed) acts.push('<button type="button" class="btn pri block" data-act="retry" data-stage="' + E(id) + '"' + (busy ? ' disabled' : '') + '>다시 실행</button>');
      if (gate && upper(gate.status) === 'APPROVED') acts.push('<button type="button" class="btn block" data-act="review" data-gate="' + E(def.gate) + '" data-stage="' + E(id) + '" data-readonly="1">결정 기록 보기</button>');
      const mstepOf = { s9s: 'data', s9: 'data', s10t: 'train', s10: 'eval' }[id];
      const mn = mstepOf ? modelNext(state.graph, d) : null;
      if (mn && mn.stage === id) {
        if (mn.input) prop('기다리는 이유', '연결한 모델이 없어요. 모델 만들기에서 연결 파일을 올려 주세요.');
        acts.unshift(mn.input ? '<button type="button" class="btn pri block" data-act="open-model" data-step="bind">' + E(mn.label) + '</button>' : '<button type="button" class="btn pri block" data-act="model-run" data-stage="' + E(id) + '"' + (busy ? ' disabled' : '') + '>' + E(mn.label) + '</button>');
      }
      if (mstepOf) acts.push('<button type="button" class="btn block" data-act="open-model" data-step="' + mstepOf + '">모델 만들기에서 보기</button>');
      const chat = (id === 's8' || id === 's8c') ? chatHref(d) : '';
      if (chat) acts.push('<a class="btn block" href="' + E(chat) + '">' + icon('chat') + '대화해 보기</a>');
      if (x.kind === 'todo' && def.implemented && !notStarted() && !mstepOf) acts.push('<button type="button" class="btn block" data-act="run-stage" data-stage="' + E(id) + '"' + (busy ? ' disabled' : '') + '>이 단계까지 실행</button>');
      const pill = '<span class="fl-pill ' + (x.kind === 'retry' ? 'run' : x.kind === 'done' ? 'ok' : ['todo', 'out', 'skip'].includes(x.kind) ? 'muted' : x.kind) + '"><span class="d"></span>' + E(KIND_LABEL[x.kind]) + '</span>';
      return '<div class="ins-head">' + (lane ? '<span class="ins-kicker">' + E(lane.label) + '</span>' : '') + '<div class="ins-title"><h2>' + E(def.name) + '</h2>' + pill + '</div>' + (acts.length ? '<div class="acts" style="flex-direction:column;align-items:stretch">' + acts.join('') + '</div>' : '') + '</div>' +
        '<section class="ins-sec"><h3>속성</h3><dl class="ins-props">' + props.join('') + '</dl></section>' +
        (thumbs.length ? '<section class="ins-sec"><h3>산출물 미리보기</h3><div class="fl-thumbs">' + thumbs.map((f) => '<img alt="' + E(f.name) + '" src="' + E(R.safeHref(f.url)) + '" loading="lazy">').join('') + '</div></section>' : '') +
        historyHTML(id);
    }


    // ---- 모델 만들기 보기(D-0130): 재료 → 데이터셋 → 학습 → 평가 ----
    function modelMode() { return /^#c\/[^/]+\/model$/.test(text(global.location && global.location.hash)); }
    function viewTabsHTML() {
      // 프롬프트만 쓰는 모티브는 학습하지 않는다. 모델 만들기 탭 대신 한 줄로 알린다.
      if (promptOnly(state.detail)) return '<p class="fl-mode-line">학습 없이 프롬프트로 대화해요</p>';
      const id = encodeURIComponent(state.detail.id);
      const m = modelMode();
      return '<nav class="md-tabs" aria-label="보기"><a href="#c/' + id + '"' + (m ? '' : ' aria-current="page"') + '>공정</a><a href="#c/' + id + '/model"' + (m ? ' aria-current="page"' : '') + '>모델 만들기</a></nav>';
    }
    function mp() { return (state.detail && state.detail.modelPath) || {}; }
    function mActive() { return modelActive(state.detail); }
    function mSteps() { return modelSteps(state.detail, views(null)); }
    function shortLabel(s) { return text(s).split(':')[0]; }
    // 모델 단계의 다음 일(QA v5 B-F06): 그 단계 칸에 시작 버튼을 둔다.
    function nextNoteHTML(step) {
      const n = modelNext(state.graph, state.detail);
      if (!n || n.step !== step || n.input) return '';
      const busy = Boolean(state.detail.job) || state.busy;
      return '<div class="md-note"><div><b>' + E(n.title) + '</b><p>' + E(n.body) + '</p></div><button type="button" class="btn pri" data-act="model-run" data-stage="' + E(n.stage) + '"' + (busy ? ' disabled' : '') + '>' + E(n.label) + '</button></div>';
    }
    function mTasks() {
      const d = state.detail;
      const v = views(null);
      return buildTasks(state.graph, d, v, { now: Date.now(), gateViews: state.gateViews, jobActive: Boolean(d.job) || state.busy })
        .filter((t) => MODEL_STAGES.has(t.stage));
    }
    function nowBarHTML() {
      const act = mActive();
      const t = mTasks()[0];
      const tr = mp().training || {};
      const busy = Boolean(state.detail.job) || state.busy;
      let k = 'idle';
      let t1 = '할 일 없음';
      let t2 = busy ? '작업이 도는 중이에요 · 사람이 할 일이 생기면 알려 드려요' : '사람이 할 일이 생기면 여기에 나와요';
      let acts = [];
      if (t) {
        k = t.kind === 'fail' ? 'bad' : 'wait';
        t1 = t.title;
        t2 = t.body;
        if (t.gate === 'G8' && (mp().eval || {}).promptOnly) {
          const bind = modelModeOf(state.detail) === 'BIND_EXISTING';
          t1 = bind ? '연결한 모델 채택 검토' : '긴 프롬프트 채택 검토';
          t2 = bind ? '비교 결과를 보고 연결한 모델을 쓸지 정해요.' : '학습 없이 긴 프롬프트로 패키지를 만들지 확인해요.';
        }
        acts = t.actions.filter((a) => !(a.act === 'open-model' && state.mstep === a.step));
      } else if (tr.state === 'run') {
        k = 'run';
        t2 = tr.stopRequested ? '중단을 요청했어요 · GPU를 반납하고 멈춰요' : '학습 중이에요 · 창을 닫아도 계속 돌아요. 끝나면 받은 일에 알려 드려요';
      }
      let html = acts.map((a, i) => '<button type="button" class="btn' + (i === 0 ? ' pri' : '') + '" data-act="' + E(a.act) + '"' + (a.gate ? ' data-gate="' + E(a.gate) + '"' : '') + (a.stage ? ' data-stage="' + E(a.stage) + '"' : '') + (a.step ? ' data-step="' + E(a.step) + '"' : '') + (a.v ? ' data-v="' + E(a.v) + '"' : '') + (a.disabled ? ' disabled' : '') + '>' + E(a.label) + '</button>').join('');
      if (state.mstep !== act) html += '<button type="button" class="btn ghost" data-act="mstep" data-step="' + act + '">' + E({ src: '재료', data: '데이터셋', train: '학습', eval: '평가', bind: '모델 연결' }[act]) + ' 단계 보기</button>';
      return '<div class="md-now ' + k + '" role="status" aria-live="polite"><span class="lab">지금 할 일</span><span class="ic">' + icon(k === 'bad' ? 'x' : k === 'wait' ? 'coins' : k === 'run' ? 'retry' : 'ok') + '</span><span class="t1">' + E(t1) + '</span><span class="t2">' + E(t2) + '</span>' + (html ? '<div class="acts">' + html + '</div>' : '') + '</div>';
    }
    function stepperHTML() {
      const act = mActive();
      const steps = mSteps();
      return '<div class="md-steps' + (steps.length < 4 ? ' n' + steps.length : '') + '" role="group" aria-label="모델 만들기 단계">' + steps.map((s) => {
        const tail = s.id === act ? '<em>지금</em>' : s.done ? '<span class="lk" aria-hidden="true">' + LOCK + '</span>' : '';
        return '<button type="button" class="md-st ' + s.k + '" data-act="mstep" data-step="' + s.id + '" aria-pressed="' + (state.mstep === s.id) + '" aria-label="' + E(s.n + '단계 ' + s.ko + ', ' + s.s + (s.id === act ? ', 지금 단계' : '') + (s.done && s.id !== act ? ', 읽기 전용' : '')) + '"><span class="k"><b>' + (s.k === 'ok' ? icon('check') : s.n) + '</b>' + s.n + '단계' + tail + '</span><strong>' + s.ko + '</strong><span class="s">' + E(s.s) + '</span></button>';
      }).join('') + '</div>';
    }
    const LOCK = '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M8 11V8a4 4 0 0 1 8 0v3" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>';
    function roChip() { return '<span class="md-lock">' + LOCK + '읽기 전용</span>'; }
    function pill(kind, label) { return '<span class="fl-pill ' + kind + '"><span class="d"></span>' + E(label) + '</span>'; }
    function recordBtn(gate, label) {
      const g = gatesById(state.detail).get(gate);
      if (!g || upper(g.status) !== 'APPROVED') return '';
      return '<button type="button" class="btn ghost" data-act="review" data-gate="' + gate + '" data-stage="' + E((state.graph.byGate.get(gate) || {}).stage || '') + '" data-readonly="1">' + E(label) + '</button>';
    }
    function reviewBtn(gate, label) {
      return '<button type="button" class="btn pri" data-act="review" data-gate="' + gate + '" data-stage="' + E((state.graph.byGate.get(gate) || {}).stage || '') + '">' + E(label) + '</button>';
    }
    function srcHTML() {
      const m = mp().material;
      if (!m) {
        const sv = views(null).s9s || {};
        const making = ['run', 'retry'].includes(sv.kind);
        const body = nextNoteHTML('src') || (making ? '<div class="md-note run"><div><b>데이터 샘플을 만드는 중이에요</b><p>끝나면 클러스터마다 샘플을 검토할 차례가 와요.</p></div></div>' : '<p class="lead">프롬프트를 승인하면 데이터 샘플을 만들면서 재료를 정해요.</p>');
        return '<div class="md-pane"><div class="md-h"><h3>재료</h3>' + pill(making ? 'run' : 'muted', making ? '만드는 중' : '아직 정하지 않았어요') + '</div>' + body + '</div>';
      }
      const used = m.used.map((u) => E(u.label) + ' <span class="num">' + u.conversations + '대화</span>').join('<br>');
      // 모티브는 출처 묶음에서 승인한 원문 대화만 그대로 쓴다. 대화 창고·다시 쓰기 설명은 오리지널 재료에만 붙인다.
      const srcOnly = m.planned.length > 0 && m.planned.every((p) => p.kind === 'SOURCE');
      return '<div class="md-pane"><div class="md-h"><h3>재료</h3>' + pill('ok', '정함') + roChip() + '</div>' +
        '<dl class="md-ro"><dt>가져오는 곳</dt><dd>' + E(m.planned.map((p) => p.label).join(' + ')) + '<small>' + (srcOnly ? '출처 묶음에서 승인한 원문을 그대로 써요' : '대화 데이터 창고(말뭉치·SNS 색인)는 아직 연결하지 않았어요') + '</small></dd>' +
        '<dt>쓴 재료</dt><dd>' + (used || '—') + '</dd>' + sourcesRow(m.sources) +
        (srcOnly ? '<dt>다시 쓰는 방식</dt><dd>다시 쓰지 않아요<small>원문 대화를 그대로 쓰고, 샘플 검토에서 고치거나 버릴 대화는 빼요</small></dd>' : rewriteRow(m)) +
        '<dt>합계</dt><dd class="num">' + (m.total ? m.total + '대화' : '아직 없어요<small>학습 데이터를 만들면 세요</small>') + '</dd></dl>' +
        '<div class="md-foot"><p>끝난 단계라 여기서 바꿀 수 없어요. 클러스터마다 고른 샘플은 검토 기록에서 볼 수 있어요.</p>' + recordBtn('G7a', '샘플 검토 기록') + '</div></div>';
    }
    // 다시 쓰는 방식(D-0135): 흐름 뼈대만 쓰고 양쪽을 새로 써요. 원문과 겹친 가장 긴 곳과 뼈대 예시.
    function rewriteRow(m) {
      if (m.rewrite === 'TURN_ONLY') return '<dt>다시 쓰는 방식</dt><dd>상대 말은 두고 캐릭터 말만 다시 썼어요<small>이전 방식으로 만든 데이터셋이에요</small></dd>';
      const s = m.sources || {};
      const o = s.overlap;
      const notes = ['원문 문장·사람·사실은 옮기지 않아요'];
      if (o && o.checked) notes.push('원문과 이어서 같은 곳은 가장 길어도 ' + o.max + '글자예요(' + o.limit + '글자부터 막아요) · ' + o.checked + '대화 확인');
      let ex = '';
      if (s.example && s.example.beats && s.example.beats.length) {
        const e = s.example;
        ex = '<div class="md-beats"><span class="md-beats-h">흐름 뼈대 예시 · ' + E(e.origin === 'NIKL' ? '말뭉치' : 'SNS') + ' 원문 ' + e.sourceTurns + '턴 → 새로 쓴 ' + e.messages + '턴</span><ol>' + e.beats.map((b) => '<li>' + E(b) + '</li>').join('') + '</ol></div>';
      }
      return '<dt>다시 쓰는 방식</dt><dd>흐름 뼈대만 쓰고 양쪽 대사를 새로 써요' + notes.map((n) => '<small>' + E(n) + '</small>').join('') + ex + '</dd>';
    }
    // 실제 대화 후보 → 구간 → 쓴 구간과 버린 수(D-0131), 출처별 섞기(D-0134).
    function sourcesRow(s) {
      if (!s || !s.file) return '';
      if (s.missing) return '<dt>실제 대화 후보</dt><dd class="warn">후보 파일을 찾지 못해 모두 합성으로 채웠어요<small>' + E(s.file) + '</small></dd>';
      const lost = s.dropped.filter((d) => d.reason !== 'over_limit' && d.reason !== 'over_share');
      const over = s.dropped.find((d) => d.reason === 'over_limit');
      const capped = s.dropped.find((d) => d.reason === 'over_share');
      const flow = '<span class="md-flow"><span><b>' + s.sessions + '</b>대화</span><span><b>' + s.windows + '</b>구간</span><span><b>' + (s.used == null ? s.offered : s.used) + '</b>쓴 구간</span></span>';
      const notes = [];
      if (s.split) notes.push('긴 대화 ' + s.split + '개를 ' + s.window + '턴 이하로 잘랐어요. 같은 대화의 구간은 학습·검증 한쪽에만 들어가요');
      if (lost.length) notes.push('버림 ' + lost.reduce((a, d) => a + d.count, 0) + '개: ' + lost.map((d) => d.label + ' ' + d.count).join(', '));
      if (over) notes.push('상한 ' + s.limit + '개를 넘은 구간 ' + over.count + '개는 쓰지 않았어요');
      if (capped) notes.push('말뭉치 비율을 넘은 말뭉치 구간 ' + capped.count + '개는 쓰지 않았어요');
      return '<dt>실제 대화 후보</dt><dd>' + flow + notes.map((n) => '<small>' + E(n) + '</small>').join('') + '</dd>' + mixRow(s);
    }
    // 출처별 쓴 구간: SNS는 문자 장면, 말뭉치는 통화 장면으로 써요(D-0134).
    function mixRow(s) {
      const rows = (s.bySource || []).filter((b) => b.windows);
      if (!rows.length) return '';
      const n = (b) => (b.used == null ? b.offered : b.used);
      const total = rows.reduce((a, b) => a + n(b), 0);
      const share = s.corpusShare == null ? null : Math.round(s.corpusShare * 100);
      const list = rows.map((b) => '<span>' + E(b.label) + ' <b class="num">' + n(b) + '</b>' + (total ? '<em class="num">' + Math.round(n(b) / total * 100) + '%</em>' : '') + '</span>').join('');
      const hint = rows.some((b) => b.kind === 'NIKL')
        ? '말뭉치 구간은 통화 장면으로 써요. ㅋㅋ·ㅠㅠ는 문자 장면과 똑같이 쓰고 그림 이모지는 쓰지 않아요' + (share == null ? '' : ' · 말뭉치 목표 ' + share + '%')
        : '말뭉치 후보가 없어 SNS만 썼어요';
      return '<dt>출처별</dt><dd><span class="md-src">' + list + '</span><small>' + E(hint) + '</small></dd>';
    }
    function mixHTML(c) {
      const total = Object.values(c.materials).reduce((a, b) => a + b, 0) || 1;
      const sns = (c.materials.SNS_REWRITE || 0) + (c.materials.NIKL || 0) + (c.materials.SOURCE || 0);
      const syn = c.materials.SYNTH || 0;
      return '<div class="md-mix" role="img" aria-label="' + E('실제 대화 ' + sns + ', 합성 ' + syn) + '"><i class="a" style="width:' + (sns / total * 100) + '%"></i><i class="b" style="width:' + (syn / total * 100) + '%"></i></div><div class="md-mixl"><span>실제 대화 ' + sns + '</span><span>합성 ' + syn + '</span></div>';
    }
    function dataHTML() {
      const d = mp().dataset;
      if (!d) return '<div class="md-pane"><div class="md-h"><h3>데이터셋</h3>' + pill('muted', '아직 없어요') + '</div><p class="lead">프롬프트를 승인하면 클러스터마다 샘플을 만들고, 샘플을 검토한 뒤 나머지를 만들어요.</p></div>';
      const ok = upper(d.status) === 'APPROVED';
      const g7 = upper(d.gates.G7.status);
      const g7a = upper(d.gates.G7a.status);
      const head = '<div class="md-h"><h3>데이터셋 ' + E(revLabel(d.rev)) + '</h3>' + (ok ? pill('ok', '승인됨' + (d.gates.G7.decidedAt ? ' · ' + clock(d.gates.G7.decidedAt) : '')) + roChip() : g7 === 'AWAITING_HUMAN' || g7a === 'AWAITING_HUMAN' ? pill('wait', '검토 대기') : dataPill()) + '</div>';
      const wait = g7a === 'AWAITING_HUMAN' ? '<div class="md-note wait"><div><b>클러스터별 샘플을 검토할 차례예요</b><p>샘플을 채택하거나 고칠 점을 남기면 나머지 대화를 같은 기준으로 만들어요.</p></div>' + reviewBtn('G7a', '샘플 검토하기') + '</div>'
        : g7 === 'AWAITING_HUMAN' ? '<div class="md-note wait"><div><b>데이터셋을 승인할 차례예요</b><p>검사 결과와 표본 20개를 보고 승인하면 학습 계획을 세워요.</p></div>' + reviewBtn('G7', '데이터셋 검토하기') + '</div>' : '';
      const next = nextNoteHTML('data');
      const rows = d.clusters.map((c) => {
        const s = c.sample || {};
        const adopt = s.ADOPT || 0;
        return '<tr><td><b>' + E(shortLabel(c.label)) + '</b>' + c.warnings.map((w) => '<small class="warn">' + E(w.replace(/^[^:]+:\s*/, '')) + '</small>').join('') + '</td><td class="r">' + (c.share != null ? Math.round(c.share * 100) + '%' : '—') + '</td><td class="r">' + E(c.target) + '</td><td class="mixc">' + mixHTML(c) + '</td><td class="nw">' + (s.total ? '채택 ' + adopt + '/' + s.total : '—') + '</td><td class="r">' + c.train + ' · ' + c.validation + ' · ' + c.eval + '</td></tr>';
      }).join('');
      const gates = '<div class="md-gates">' + [['G7a', '샘플 검토', d.gates.G7a], ['G7', '데이터셋 승인', d.gates.G7]].map((x) => {
        const st = upper(x[2].status);
        return '<div class="md-gate ' + (st === 'APPROVED' ? 'ok' : st === 'AWAITING_HUMAN' ? 'wait' : '') + '">' + icon(st === 'APPROVED' ? 'ok' : 'user') + '<div>' + x[1] + ' · ' + (st === 'APPROVED' ? '통과' : st === 'AWAITING_HUMAN' ? '검토 대기' : '아직') + '<small>' + (x[2].decidedAt ? E(clock(x[2].decidedAt)) : '') + '</small></div>' + recordBtn(x[0], '기록') + '</div>';
      }).join('') + '</div>';
      return '<div class="md-pane">' + head + wait + next +
        '<dl class="md-stats"><div><dt>학습</dt><dd>' + d.counts.train + '<small> 대화</small></dd></div><div><dt>검증</dt><dd>' + d.counts.validation + '<small> 대화</small></dd></div><div><dt>평가</dt><dd>' + d.counts.eval + '<small> 대화</small></dd></div><div><dt>나누는 단위</dt><dd><small>같은 장면 뼈대는 한쪽에만 넣어 섞이지 않게 해요</small></dd></div></dl>' +
        '<div class="md-h"><h4>클러스터</h4><span class="sp"></span><span class="md-legend"><span><i class="a"></i>실제 대화</span><span><i class="b"></i>합성</span></span></div>' +
        '<div class="md-scroll"><table class="md-t"><thead><tr><th>클러스터</th><th class="r">비율</th><th class="r">목표</th><th>재료</th><th>샘플 판정</th><th class="r">학습 · 검증 · 평가</th></tr></thead><tbody>' + rows + '</tbody></table></div>' +
        ((d.notes || []).length ? d.notes.map((n) => '<div class="md-note wait"><div><b>데이터셋 경고</b><p>' + E(n) + '</p></div></div>').join('') : '') +
        (d.blocking.length ? '<div class="md-note bad"><div><b>막는 문제 ' + d.blocking.length + '건</b><p>' + E(d.blocking.join(' · ')) + '</p></div></div>' : '') + gates +
        (ok ? '<div class="md-foot"><p>승인한 데이터셋은 바꿀 수 없어요. 학습은 이 버전으로 해요.</p></div>' : '') + '</div>';
    }
    function dataPill() {
      const st = mSteps().find((x) => x.id === 'data') || {};
      return pill({ run: 'run', fail: 'fail', wait: 'wait' }[st.k] || 'muted', { run: '만드는 중', fail: '멈춤' }[st.k] || (st.k === 'wait' ? st.s : '만들기 전'));
    }
    function phasesHTML(tr) {
      const list = tr.phases && tr.phases.length ? tr.phases : [];
      return '<ol class="md-ph">' + list.map((p) => {
        const mark = p.status === 'ok' ? icon('check') : p.status === 'fail' ? icon('x') : p.status === 'skip' ? icon('minus') : p.status === 'warn' ? '!' : '';
        return '<li class="' + E(p.status) + '"><span class="dot">' + mark + '</span><div><b>' + E(p.name) + '</b><small>' + E(p.detail) + '</small>' + (p.meter != null ? '<div class="md-meter" role="progressbar" aria-label="학습 스텝" aria-valuenow="' + Math.round(p.meter * 100) + '" aria-valuemin="0" aria-valuemax="100"><i style="width:' + (p.meter * 100) + '%"></i></div>' : '') + '</div></li>';
      }).join('') + '</ol>';
    }
    const MCONFIRM = {
      start: ['유료 학습을 시작할까요?', (tr) => (tr.estimateUsd ? 'GPU를 빌리는 순간부터 비용이 들어요. 예상 ' + usd(tr.estimateUsd) + ', 많아도 ' + usd(tr.budgetUsd) + '에서 멈추고 GPU를 반납해요.' : '시험용 가짜 학습이라 비용이 들지 않아요. 실제 공급자라면 GPU를 빌리는 순간부터 비용이 들어요.') + (tr.state === 'done' ? ' 지금 학습 기록은 남고 새 학습을 만들어요.' : ''), 'train-go', '학습 시작', 'pri'],
      skip: ['학습 없이 진행할까요?', () => '긴 프롬프트만으로 평가하고, 평가에서 채택을 한 번 더 확인해요. 데이터셋은 남겨 두어 나중에 학습할 수 있어요.', 'skip-go', '학습 없이 진행', 'pri'],
      stop: ['학습을 멈출까요?', (tr) => '지금까지 학습한 결과는 버리고 GPU를 반납해요.' + (tr.spentUsd ? ' 쓴 돈 약 ' + usd(tr.spentUsd) + '(추정)은 돌려받지 못해요.' : ''), 'stop-go', '멈추고 반납', 'danger'],
      release: ['결과를 버리고 GPU를 반납할까요?', () => '학습한 결과를 받지 못한 채 지워요. 다시 하려면 처음부터 학습해야 해요.', 'release-go', '버리고 반납', 'danger']
    };
    function mConfirmHTML(tr) {
      const c = MCONFIRM[state.mconfirm];
      if (!c) return '';
      const busy = state.busy || (state.detail.job && state.mconfirm !== 'stop');
      return '<div class="fl-confirm md-confirm" role="group" aria-label="' + E(c[0]) + '"><p><b>' + E(c[0]) + '</b></p><p class="est">' + E(c[1](tr)) + '</p><div class="acts"><button type="button" class="btn ' + c[4] + '" data-act="' + c[2] + '"' + (busy ? ' disabled' : '') + '>' + E(c[3]) + '</button><button type="button" class="btn ghost" data-act="mconfirm-cancel">취소</button></div></div>';
    }
    function trainHTML() {
      const tr = mp().training || {};
      const p0 = (tr.providers || [])[0] || {};
      const busy = Boolean(state.detail.job) || state.busy;
      const fake = p0.provider === 'fake';
      if (tr.state === 'locked') return '<div class="md-pane"><div class="md-h"><h3>학습</h3>' + pill('muted', '아직 열리지 않았어요') + '</div><p class="lead">데이터셋을 승인하면 학습 계획(예상 비용·시간)을 세워요.</p></div>';
      if (tr.state === 'pending') return '<div class="md-pane"><div class="md-h"><h3>학습</h3>' + pill('muted', '계획 전') + '</div><div class="md-note"><div><b>학습 계획을 세울 차례예요</b><p>계획은 비용이 들지 않아요. 계획을 세우면 예상 비용을 보고 시작할지 골라요.</p></div><button type="button" class="btn pri" data-act="model-run" data-stage="s10t"' + (busy ? ' disabled' : '') + '>학습 계획 세우기</button></div></div>';
      const confirm = mConfirmHTML(tr);
      if (tr.state === 'skip') {
        const g8 = upper(((mp().eval || {}).gate || {}).status);
        return '<div class="md-pane"><div class="md-h"><h3>학습</h3>' + pill('muted', '하지 않음') + roChip() + '</div><div class="md-note"><div><b>학습 없이 긴 프롬프트로 진행하기로 했어요</b><p>데이터셋 ' + E(revLabel(tr.datasetRev)) + '는 남아 있어요.' + (g8 === 'APPROVED' ? '' : ' 평가에서 채택을 확정하기 전이면 학습으로 바꿀 수 있어요.') + '</p></div>' + (g8 === 'APPROVED' ? '' : '<button type="button" class="btn" data-act="mconfirm" data-v="start"' + (busy ? ' disabled' : '') + '>학습으로 바꾸기</button>') + '</div>' + confirm + '</div>';
      }
      const cfg = p0.config || {};
      if (['plan', 'stopped', 'fail'].includes(tr.state)) {
        const note = tr.state === 'stopped' ? '<div class="md-note"><div><b>지난 학습을 중단했어요</b><p>GPU는 반납했어요. 다시 시작하면 새 학습을 만들어요.</p></div></div>'
          : tr.state === 'fail' ? '<div class="md-note bad"><div><b>학습이 실패했어요</b><p>' + E(p0.error || '원인을 학습 기록에서 확인해 주세요.') + '</p></div></div>' : '';
        const grid = [
          ['예상 비용', usd(tr.estimateUsd), '예산 ' + usd(tr.budgetUsd) + ' 안'],
          ['예상 시간', tr.gpuHours ? '약 ' + hoursText(tr.gpuHours) : fake ? '바로 끝나요' : '—', fake ? '시험용 가짜 학습' : '준비 시간 포함'],
          ['GPU', fake ? '빌리지 않아요' : p0.provider === 'gemma_qlora' ? '임대 GPU 한 대' : '튜닝 서비스', fake ? '시험용' : '쓰는 동안만 빌려요'],
          ['기반 모델', E(p0.baseModel || '—'), 'QLoRA 학습'],
          ['학습 횟수', cfg.epochs != null ? cfg.epochs + '회' : '—', cfg.checkpointEpochs ? '체크포인트 ' + cfg.checkpointEpochs.join(' · ') + '회차' : ''],
          ['학습 데이터', E(revLabel(tr.datasetRev)), (mp().dataset ? mp().dataset.counts.train + '대화' : '')]
        ].map((x) => '<div><dt>' + x[0] + '</dt><dd>' + x[1] + '<small>' + E(x[2]) + '</small></dd></div>').join('');
        return '<div class="md-pane"><div class="md-h"><h3>학습 계획</h3>' + pill('wait', tr.state === 'plan' ? '비용 확인 대기' : '다시 시작 대기') + '</div>' + note + '<dl class="md-grid3">' + grid + '</dl>' +
          (fake ? '' : '<div class="md-note"><div><b>GPU는 쓰는 동안만 빌려요</b><p>빌리기 전에 자동 반납 감시를 먼저 켜고, 끝나거나 멈추면 바로 반납해요. 예산이나 시간 상한에 닿으면 자동으로 반납해요.</p></div></div>') +
          (confirm || '<div class="acts"><button type="button" class="btn pri" data-act="mconfirm" data-v="start"' + (busy ? ' disabled' : '') + '>' + (tr.state === 'plan' ? '학습 시작' : '다시 학습') + ' · 예상 ' + usd(tr.estimateUsd) + '</button><button type="button" class="btn ghost" data-act="mconfirm" data-v="skip"' + (busy ? ' disabled' : '') + '>학습 없이 진행</button></div>') +
          '</div><div class="md-pane"><h4>이렇게 진행돼요</h4>' + phasesHTML(tr) + '</div>';
      }
      let head = '';
      let extra = '';
      if (tr.state === 'run') {
        const el = hoursText(p0.elapsedHours);
        head = '<div class="md-h"><h3>학습</h3>' + pill('run', '진행 중' + (el ? ' · ' + el + '째' : '')) + '<span class="sp"></span>' + (tr.stopRequested ? '<span class="hint">중단하는 중이에요</span>' : state.mconfirm === 'stop' ? '' : '<button type="button" class="btn danger" data-act="mconfirm" data-v="stop">학습 중단</button>') + '</div><p class="lead">창을 닫아도 계속 돌아요. 끝나면 받은 일에 알려 드려요.</p>' + confirm;
      } else if (tr.state === 'hold') {
        const gpu = gpuAlive(tr);
        head = '<div class="md-h"><h3>학습</h3>' + pill('fail', '결과 받기 실패') + '</div><div class="md-note bad"><div><b>' + (gpu ? '결과를 받아 오지 못해 GPU를 남겨 뒀어요' : '학습 결과를 받아 오지 못했어요') + '</b><p>' + (gpu ? '학습 결과를 잃지 않으려고 반납하지 않았어요. 비용이 계속 나가요' + (p0.deadlineAt ? ' · ' + E(clock(p0.deadlineAt)) + '에 자동 반납' : '') + '.' : '학습은 끝났어요. 다시 받아 오면 이어서 체크포인트를 골라요.') + (p0.collectError ? '<details class="fd-tech"><summary>기술 정보</summary><pre>' + E(p0.collectError) + '</pre></details>' : '') + '</p></div><div class="acts"><button type="button" class="btn pri" data-act="train-retry"' + (busy ? ' disabled' : '') + '>다시 받아 오기</button><button type="button" class="btn danger" data-act="mconfirm" data-v="release"' + (busy ? ' disabled' : '') + '>결과 버리고 반납</button></div></div>' + confirm;
      } else {
        head = '<div class="md-h"><h3>학습</h3>' + pill('ok', '완료' + (p0.completedAt ? ' · ' + clock(p0.completedAt) : '')) + roChip() + '</div><div class="md-note ok"><div><b>' + (fake ? '시험용 가짜 학습을 마쳤어요' : '학습을 마치고 GPU를 반납했어요') + '</b><p>' + [p0.elapsedHours != null ? '걸린 시간 ' + hoursText(p0.elapsedHours) : '', tr.spentUsd != null ? '쓴 돈 약 ' + usd(tr.spentUsd) + '(추정)' : ''].filter(Boolean).join(' · ') + '</p></div></div>';
        const sel = p0.selection;
        if (sel) {
          const pct = (x) => (x == null ? '—' : Math.round(x * 100) + '%');
          const rows = sel.rows.map((r) => '<tr' + (r.chosen ? ' class="pick"' : '') + '><td>' + (r.role === 'base' ? '기반 모델<small>학습 없이 같은 짧은 프롬프트</small>' : E(r.epoch != null ? r.epoch + '회차' : r.arm) + (r.chosen ? '<small>골랐어요</small>' : '')) + '</td><td class="r">' + pct(r.empty) + '</td><td class="r">' + pct(r.truncated) + '</td><td class="r">' + pct(r.loop) + '</td><td>' + (r.role === 'base' ? '비교 기준' : r.eligible === false ? '<span class="bad">' + E(r.exclusion || '제외') + '</span>' : r.eligible ? '적격' : '—') + '</td><td class="r">' + (r.wins != null ? r.wins + '승' : '—') + '</td></tr>').join('');
          extra = '<div class="md-pane"><div class="md-h"><h3>체크포인트 고르기</h3>' + pill(p0.binding ? 'ok' : 'wait', sel.decisionKo || '—') + roChip() + '</div>' +
            (sel.reasons.length ? '<p class="lead">' + E(sel.reasons[0]) + '</p>' : sel.decision ? '' : '<p class="lead">선별 답을 만들지 않는 학습이라 마지막 체크포인트를 써요.</p>') +
            '<div class="md-scroll"><table class="md-t"><thead><tr><th>후보</th><th class="r">빈 답</th><th class="r">잘림</th><th class="r">반복</th><th>적격</th><th class="r">짝 판정</th></tr></thead><tbody>' + rows + '</tbody></table></div>' +
            '<div class="md-foot"><p>다른 체크포인트를 쓰거나 다시 학습하려면 새 학습을 만들어요. 이번 기록은 그대로 남아요.</p><button type="button" class="btn" data-act="mconfirm" data-v="start"' + (busy ? ' disabled' : '') + '>새 학습 만들기</button></div>' + confirm + '</div>';
        }
      }
      return '<div class="md-pane">' + head + '<h4>진행</h4>' + phasesHTML(tr) + '</div>' + extra;
    }
    // 학습 모델 조건의 평가 system(D-0139): 학습 때와 같은 학습용 짧은 프롬프트인지 보여요.
    const REL_KO = { STRONGLY_FAVORABLE: '아주 가까운 사이', FAVORABLE: '가까운 사이', NEUTRAL: '아직 가깝지 않은 사이', UNFAVORABLE: '불편한 사이' };
    function sftPromptText(p) {
      if (!p) return '학습용 짧은 프롬프트 + 학습한 말투';
      if (p.kind === 'legacy') return '옛 짧은 프롬프트(' + p.chars.toLocaleString('ko-KR') + '자) + 학습한 말투';
      return '학습 때와 같은 짧은 프롬프트(' + p.chars.toLocaleString('ko-KR') + '자 · ' + (REL_KO[p.relationship] || p.relationship) + ' · 영상통화) + 학습한 말투';
    }
    function evalHTML() {
      const m = mp();
      const tr = m.training || {};
      const e = m.eval || {};
      const b = m.binding;
      const bind = modelModeOf(state.detail) === 'BIND_EXISTING';
      const sets = bind
        ? '<h4>평가 방법</h4><ul class="md-sets"><li><span>비교 세트</span><span>원문에서 떼어 둔 실제 대화 장면</span></li><li><span>구별 판정</span><span>실제 답과 모델 답을 판정 모델과 가족이 가려요</span></li></ul>'
        : '<h4>평가 세트</h4><ul class="md-sets"><li><span>고정 이력 질문</span><span>지난 이야기를 기억하는지</span></li><li><span>서운함</span><span>감정 표현과 회복</span></li><li><span>무례·사과 대본</span><span>사과를 받고 풀리는지</span></li><li><span>200턴 대화 · 사용자 4명</span><span>반복과 200턴째 기억</span></li></ul>';
      if (bind && !b) return '<div class="md-pane"><div class="md-h"><h3>평가</h3>' + pill('muted', '아직 열리지 않았어요') + '</div><div class="md-note wait"><div><b>연결한 모델이 없어 평가를 기다려요</b><p>평가는 긴 프롬프트와 연결한 모델의 답을 비교해요. 먼저 학습된 모델을 연결해 주세요.</p></div><button type="button" class="btn pri" data-act="mstep" data-step="bind">모델 연결하기</button></div>' + sets + '</div>';
      if (!bind && !['done', 'skip'].includes(tr.state)) return '<div class="md-pane"><div class="md-h"><h3>평가</h3>' + pill('muted', '아직 열리지 않았어요') + '</div><p class="lead">학습이 끝나거나 학습 없이 진행을 고르면 열려요. 긴 프롬프트와 학습 모델에 같은 질문을 하고, 판정 모델 비교 뒤 블라인드 20쌍을 직접 골라요.</p>' + sets + '</div>';
      const v = views(null).s10 || {};
      const gs = upper(e.gate && e.gate.status);
      const busy = Boolean(state.detail.job) || state.busy;
      // 비교 조건은 G8과 같은 수로 보인다(QA v5 C-08). 사전 등록 전이면 긴 프롬프트와 학습(연결) 모델 두 가지다.
      const LONG = { label: '긴 프롬프트', sub: '학습 없음 · 지금 서비스 방식' };
      let arms;
      if (bind) arms = [LONG, { label: '연결한 모델', sub: b.kindLabel + ' · ' + text(b.ref) }];
      else if ((e.arms || []).length) arms = e.arms.map((a) => (a.id === 'LONG_BASE' ? LONG : { label: a.label, sub: a.bound ? sftPromptText(e.sftPrompt) : '학습 결과가 없어 답을 받지 않아요' }));
      else arms = [LONG, { label: tr.state === 'skip' || !tr.adopted ? '학습 모델 없음' : '학습 모델', sub: tr.state === 'skip' ? '학습 없이 진행해 비교하지 않아요' : tr.adopted ? sftPromptText(e.sftPrompt) : '쓸 체크포인트가 없어요' }];
      const vs = '<div class="md-vs' + (arms.length > 2 ? ' n' + arms.length : '') + '">' + arms.map((a) => '<div class="md-arm"><b>' + E(a.label) + '</b><small>' + E(a.sub) + '</small></div>').join('<span class="x">대</span>') + '</div>';
      let act = '';
      if (gs === 'AWAITING_HUMAN') {
        const t = !e.promptOnly ? ['블라인드 20쌍을 고를 차례예요', '지표와 판정 모델 비교를 보고, 어느 쪽 답이 나은지 직접 골라요.', '블라인드 20쌍 고르기']
          : bind ? ['연결한 모델로 채택할지 확인해요', '비교 결과를 보고 연결한 모델을 쓸지 정해요.', '채택 검토하기']
            : ['긴 프롬프트로 채택할지 확인해요', '학습 결과 없이 긴 프롬프트로 패키지를 만들어요.', '채택 검토하기'];
        act = '<div class="md-note wait"><div><b>' + t[0] + '</b><p>' + t[1] + '</p></div>' + reviewBtn('G8', t[2]) + '</div>';
      } else if (gs === 'APPROVED') act = '<div class="md-note ok"><div><b>평가를 마쳤어요</b><p>' + (e.adopted ? E(e.adopted.label) + '로 채택했어요.' : '채택 결정을 기록했어요.') + (e.gate.decidedAt ? ' · ' + E(clock(e.gate.decidedAt)) : '') + '</p></div>' + recordBtn('G8', '결정 기록') + '</div>';
      else if (v.kind === 'confirm') act = state.confirming === 's10' ? confirmHTML('s10') : '<div class="md-note wait"><div><b>' + (bind ? '평가 비용을 확인해 주세요' : '학습 모델 답을 받으려면 GPU를 다시 빌려요') + '</b><p>예상 비용을 확인한 뒤 평가를 시작해요.</p></div><button type="button" class="btn pri" data-act="confirm" data-stage="s10"' + (busy ? ' disabled' : '') + '>비용 확인</button></div>';
      else if (['run', 'retry'].includes(v.kind)) act = '<div class="md-note run"><div><b>답을 모으는 중이에요</b><p>끝나면 채택 검토가 열려요.</p></div></div>';
      else if (v.kind === 'fail') act = '<div class="md-note bad"><div><b>평가가 멈췄어요</b><p>' + E(failReason((rowsById(state.detail).get('s10') || {}).lastError).summary) + '</p></div><button type="button" class="btn pri" data-act="retry" data-stage="s10"' + (busy ? ' disabled' : '') + '>다시 실행</button></div>';
      else act = nextNoteHTML('eval');
      return '<div class="md-pane"><div class="md-h"><h3>' + (bind || (e.arms || []).length ? '비교하는 조건 ' + arms.length + '가지' : '비교') + '</h3>' + (gs === 'APPROVED' ? roChip() : '') + '</div>' + vs + act + '</div><div class="md-pane">' + sets + '</div>';
    }
    // 학습된 모델 연결(QA v5 B-F07): 연결 파일을 고르면 서버가 확인하고 기록한다. 평가 검토가 열리기 전까지 바꿀 수 있다.
    function bindHTML() {
      const b = mp().binding;
      const busy = Boolean(state.detail.job) || state.busy;
      const locked = ['AWAITING_HUMAN', 'APPROVED'].includes(upper(((mp().eval || {}).gate || {}).status));
      const err = state.bindError ? '<div class="md-note bad" role="alert"><div><b>연결하지 못했어요</b><p>' + E(state.bindError) + '</p></div></div>' : '';
      const pick = '<button type="button" class="btn' + (b ? '' : ' pri') + '" data-act="bind-pick"' + (busy ? ' disabled' : '') + '>' + (state.binding ? '확인하는 중…' : b ? '다른 모델 연결' : '연결 파일 고르기') + '</button><input type="file" data-bind-file accept=".json,application/json" hidden aria-hidden="true" tabindex="-1">';
      const guide = '<details class="fd-tech"><summary>연결 파일에 들어가는 것</summary><p>모델 종류(Hugging Face 어댑터 · Vertex 튜닝 모델 · 서빙 주소), 모델 이름, 버전(커밋), 기반 모델과 그 버전, 서빙 경로, 학습한 사람·날, 학습 데이터 설명, 사용 근거예요. 토큰 값은 넣지 않아요.</p></details>';
      if (!b) return '<div class="md-pane"><div class="md-h"><h3>모델 연결</h3>' + pill('wait', '연결 전') + '</div><p class="lead">이미 학습한 모델을 이 캐릭터에 연결해요. 연결 파일(.json)을 고르면 서버가 확인한 뒤 기록해요. 학습이나 생성은 하지 않아서 비용이 들지 않아요.</p>' + err + '<div class="acts">' + pick + '</div>' + guide + '</div>';
      const row = (k, val, small) => (val ? '<dt>' + E(k) + '</dt><dd>' + E(val) + (small ? '<small>' + E(small) + '</small>' : '') + '</dd>' : '');
      return '<div class="md-pane"><div class="md-h"><h3>연결한 모델</h3>' + pill('ok', '연결함') + (locked ? roChip() : '') + '</div>' + err +
        '<dl class="md-ro">' + row('모델 종류', b.kindLabel) + row('모델', b.ref) + row('버전', b.revision) + row('기반 모델', b.baseModel, b.baseModelRevision ? '버전 ' + b.baseModelRevision : '') + row('서빙 경로', b.servingRoute) + row('확인', b.checkLabel) +
        row('학습', [b.trainedBy, b.trainedAt].filter(Boolean).join(' · '), b.dataNote) + row('사용 근거', b.usageBasis) + '</dl>' +
        (locked ? '<div class="md-foot"><p>평가 검토가 열려서 연결한 모델을 바꿀 수 없어요.</p></div>' : '<div class="md-foot"><p>평가 검토가 열리기 전에는 다른 모델로 바꿀 수 있어요.</p>' + pick + '</div>') + '</div>';
    }
    async function connectModel(file) {
      const id = state.detail && state.detail.id;
      if (!id || !file) return;
      state.bindError = '';
      let body;
      try {
        if (file.size > 256 * 1024) throw new Error('big');
        body = JSON.parse(await file.text());
      } catch (error) {
        state.bindError = '연결 파일을 읽지 못했어요. 모델 연결용 .json 파일이 맞는지 확인해 주세요.';
        render();
        return;
      }
      state.binding = true;
      state.busy = true;
      state.feedback = null;
      render();
      try {
        const res = await fetch(R.apiPath(apiBase, '/api/characters/' + encodeURIComponent(id) + '/model-binding'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), cache: 'no-store' });
        let data = null;
        try { data = await res.json(); } catch (error) { data = null; }
        if (!res.ok) state.bindError = text(data && typeof data.detail === 'string' ? data.detail : '연결하지 못했어요 (' + res.status + ').');
        else { state.feedback = { tone: 'ok', text: '모델을 연결했어요. 이제 평가를 시작할 수 있어요.' }; state.mstep = 'eval'; }
      } catch (error) {
        state.bindError = '서버에 연결하지 못했어요. 연결이 돌아오면 다시 골라 주세요.';
        state.conn = 'offline';
      }
      state.binding = false;
      state.busy = false;
      await refresh(false);
    }
    function modelHTML() {
      if (!state.mstep) state.mstep = mActive();
      if (!mSteps().some((x) => x.id === state.mstep)) state.mstep = mActive();
      const body = state.mstep === 'bind' ? bindHTML() : state.mstep === 'src' ? srcHTML() : state.mstep === 'data' ? dataHTML() : state.mstep === 'train' ? trainHTML() : evalHTML();
      return '<div class="md">' + nowBarHTML() + stepperHTML() + body + '</div>';
    }
    function modelPanelHTML() {
      const m = mp();
      const tr = m.training || {};
      const p0 = (tr.providers || [])[0] || {};
      const st = state.mstep || mActive();
      const props = [];
      const prop = (k, v, meter, tone) => { if (v) props.push('<dt>' + E(k) + '</dt><dd>' + v + (meter != null ? '<div class="md-meter' + (tone ? ' ' + tone : '') + '"><i style="width:' + Math.min(100, meter * 100) + '%"></i></div>' : '') + '</dd>'); };
      let title = '요약';
      if (st === 'train') {
        title = '이번 학습';
        if (['plan', 'stopped', 'fail'].includes(tr.state)) {
          prop('예상 비용', E(usd(tr.estimateUsd) + ' / 예산 ' + usd(tr.budgetUsd)), tr.budgetUsd ? (tr.estimateUsd || 0) / tr.budgetUsd : null);
          prop('예상 시간', E(tr.gpuHours ? '약 ' + hoursText(tr.gpuHours) : '—'));
        } else if (['run', 'hold', 'done'].includes(tr.state)) {
          prop(tr.state === 'done' ? '쓴 돈(추정)' : '쓴 돈(추정)', E(usd(tr.spentUsd) + ' / 예산 ' + usd(tr.budgetUsd) + (tr.state === 'hold' && gpuAlive(tr) ? ' · 늘어나는 중' : '')), tr.budgetUsd ? (tr.spentUsd || 0) / tr.budgetUsd : null, tr.state === 'hold' ? 'bad' : tr.state === 'done' ? 'ok' : '');
          prop('경과', E(hoursText(p0.elapsedHours) || '—'));
          if (p0.deadlineAt) prop('자동 반납', E(clock(p0.deadlineAt) + '까지 안 끝나면'));
          prop('GPU', E(p0.provider === 'fake' ? '빌리지 않음(시험용)' : gpuAlive(tr) ? '빌린 중' + (p0.gpu ? ' · ' + p0.gpu : '') : '반납함'));
        }
        prop('데이터셋', E(revLabel(tr.datasetRev || '') || '—'));
        prop('기반 모델', E(p0.baseModel || ''));
        if (p0.binding) prop('고른 체크포인트', E(p0.binding.checkpointId));
      } else if (st === 'src' && m.material) {
        const total = m.material.total || 0;
        const sns = m.material.used.filter((u) => u.kind !== 'SYNTH').reduce((a, u) => a + u.conversations, 0);
        const srcOnly = m.material.planned.length > 0 && m.material.planned.every((p) => p.kind === 'SOURCE');
        prop('재료', E((m.material.used.length ? m.material.used : m.material.planned).map((u) => u.label).join(' + ')));
        if (!srcOnly) {
          prop('실제 대화 비율', E(total ? Math.round(sns / total * 100) + '%' : '—'), total ? sns / total : null, 'acc');
          prop('대화 데이터 창고', '연결 전');
        }
      } else if (st === 'data' && m.dataset) {
        prop('전체', E(m.dataset.counts.total + '대화'));
        prop('목표(학습)', E((m.dataset.planned || '—') + '대화'));
        prop('경고', E(m.dataset.warnings.length + '건'));
        if (m.dataset.trainingPrompt) prop('학습용 프롬프트', E((m.dataset.trainingPrompt.longestChars || 0).toLocaleString('ko-KR') + '자 이하 · 관계 ' + m.dataset.trainingPrompt.relationships + ' · 채널 ' + m.dataset.trainingPrompt.channels));
        prop('막는 문제', E(m.dataset.blocking.length + '건'));
      } else if (st === 'bind' && m.binding) {
        title = '연결한 모델';
        prop('모델 종류', E(m.binding.kindLabel));
        prop('모델', E(m.binding.ref || ''));
        prop('확인', E(m.binding.checkLabel));
      } else if (st === 'eval') {
        const ev = m.eval || {};
        prop('평가', E((mSteps().find((x) => x.id === 'eval') || {}).s || '—'));
        if (ev.adopted) prop('채택', E(ev.adopted.label));
        if (modelModeOf(state.detail) === 'BIND_EXISTING') prop('비교 세트', '원문에서 떼어 둔 장면');
        else {
          prop('블라인드', ev.promptOnly ? '없음 · 학습 없이 진행해 비교하지 않아요' : '20쌍 · 사람이 골라요');
          prop('판정', '순서를 바꿔 두 번');
        }
      }
      return '<div class="ins-head"><span class="ins-kicker">모델 만들기</span><div class="ins-title"><h2>' + E(title) + '</h2></div></div><section class="ins-sec"><dl class="ins-props md-props">' + (props.join('') || '<dt>상태</dt><dd>아직 기록이 없어요</dd>') + '</dl></section>';
    }
    const MODEL_RUN_OK = {
      s9s: '데이터 샘플 만들기를 요청했어요. 끝나면 샘플 검토를 알려 드려요.',
      s9: '학습 데이터 만들기를 요청했어요. 끝나면 데이터셋 승인을 알려 드려요.',
      s10t: '학습 계획을 세우고 있어요. 계획에는 비용이 들지 않아요.',
      s10: '평가를 요청했어요. 비용이 드는 평가면 시작하기 전에 다시 물어봐요.'
    };
    function goModel() {
      if (modelMode()) { render(); return; }
      state.keepStep = true;
      global.location.hash = '#c/' + encodeURIComponent(state.detail.id) + '/model';
    }
    async function post(path, okText) {
      state.busy = true;
      state.feedback = null;
      render();
      try {
        await request('POST', path, {});
        state.feedback = okText ? { tone: 'ok', text: okText } : null;
      } catch (error) {
        state.feedback = { tone: 'bad', text: error.message };
        if (error.network) state.conn = 'offline';
      }
      state.busy = false;
      await refresh(false);
    }

    // ---- 검토 시트 ----
    function renderSheet() {
      if (!region.sheet) return;
      if (!state.review || !state.detail) {
        if (!region.sheet.hidden) { region.sheet.hidden = true; region.scrim.hidden = true; region.sheet.innerHTML = ''; state.sheetKey = ''; }
        if (region.shell) region.shell.inert = false;
        return;
      }
      const key = state.review.gate + (state.review.readonly ? '|ro' : '');
      if (key === state.sheetKey && !region.sheet.hidden) return;
      const g = state.graph.byGate.get(state.review.gate) || { title: state.review.gate };
      const ro = state.review.readonly;
      const src = R.gateUrl(state.detail.id, state.review.gate, apiBase) + '&embedded=1&skin=foundry&theme=' + resolvedTheme();
      const nb = !ro && state.batch === state.review.gate ? nextInBatch() : null;
      const nextBtn = nb ? '<button type="button" class="btn" data-act="next-batch" title="같은 검토를 기다리는 다음 캐릭터로 가요">다음 건 · ' + E(nb.next.c.name || nb.next.c.id) + ' (' + nb.left + '건 남음)</button>' : '';
      region.sheet.innerHTML = '<div class="fd-sheet-head"><h2 id="fd-sheet-title">' + E(nameOf(state.detail)) + ' · ' + E(g.title) + (ro ? ' · 결정 기록' : /(검토|승인)$/.test(text(g.title)) ? '' : ' 검토') + '</h2><span class="fl-pill ' + (ro ? 'muted' : 'wait') + '"><span class="d"></span>' + (ro ? '기록' : '검토 대기') + '</span>' + nextBtn + '<button type="button" class="btn ghost x" data-act="close-review" aria-label="검토 닫기">' + icon('close') + '닫기</button></div>' +
        '<p class="fd-sheet-note">' + (ro ? '이 관문에서 고른 내용과 결정 기록이에요.' : '고르기 · 승인 · 수정 요청 · 반려를 여기서 해요. 수정 요청은 고칠 부분만 새 버전으로, 반려는 처음부터 다시 만들어요. 결정하면 시트가 닫히고 다음 단계가 이어서 돌아요.') + '</p>' +
        '<iframe class="fl-frame" src="' + E(src) + '" title="' + E(g.title + ' 검토 화면') + '"></iframe>';
      region.sheet.hidden = false;
      region.scrim.hidden = false;
      if (region.shell) region.shell.inert = true;
      state.sheetKey = key;
      const close = region.sheet.querySelector('[data-act="close-review"]');
      if (close) close.focus();
    }
    function closeSheet(restore) {
      if (!state.review) return;
      const gate = state.review.gate;
      state.review = null;
      renderSheet();
      if (restore !== false) {
        // 여는 버튼은 다시 그리기로 바뀌었을 수 있다. 같은 관문 버튼 → 첫 할 일 → 제목 순서로 초점을 돌린다.
        const target = (state.opener && state.opener.isConnected && state.opener) ||
          doc.querySelector('[data-act="review"][data-gate="' + String(gate).replace(/"/g, '') + '"]') ||
          doc.querySelector('.fl-tasks .btn:not([disabled])') || doc.querySelector('.fd-title h1');
        if (target && target.focus) target.focus({ preventScroll: true });
      }
      state.opener = null;
    }

    function focusKey() {
      const a = doc.activeElement;
      if (!a || a === doc.body || !a.closest || !a.closest('.fd-shell')) return null;
      const ds = a.dataset || {};
      return { id: a.id || '', act: ds.act || '', gate: ds.gate || '', stage: ds.stage || '', cid: ds.id || '', lane: ds.lane || '', theme: ds.theme || '', caret: typeof a.selectionStart === 'number' ? a.selectionStart : null };
    }
    function restoreFocus(k) {
      if (!k || state.review) return;
      const a = doc.activeElement;
      if (a && a !== doc.body && a.isConnected) return;
      let el = k.id ? doc.getElementById(k.id) : null;
      if (!el && k.act) {
        let sel = '[data-act="' + k.act + '"]';
        [['gate', k.gate], ['stage', k.stage], ['id', k.cid], ['lane', k.lane], ['theme', k.theme]].forEach((f) => { if (f[1]) sel += '[data-' + f[0] + '="' + String(f[1]).replace(/"/g, '') + '"]'; });
        el = doc.querySelector(sel);
      }
      if (!el || !el.focus) return;
      el.focus({ preventScroll: true });
      if (k.caret != null && el.setSelectionRange) { try { el.setSelectionRange(k.caret, k.caret); } catch (error) { /* 무시 */ } }
    }
    function render() {
      const k = focusKey();
      renderNow();
      restoreFocus(k);
    }
    function renderNow() {
      if (state.destroyed || !region.top) return;
      sumMemo = null;
      const rt = route();
      if (reference) reference.setCharacter(!rt.overview && !state.form.open && state.detail && state.detail.origin === 'SOURCE' ? state.detail.id : null);
      state.overview = rt.overview && Boolean(state.graph) && !state.form.open;
      if (region.shell) region.shell.classList.toggle('is-overview', state.overview);
      renderSide();
      if (!state.graph) {
        region.top.innerHTML = '<nav class="fd-crumb"><b>캐릭터</b></nav><div class="fd-metrics"><span class="fd-conn ' + (state.conn === 'offline' ? 'off' : 'wait') + '"><span class="d"></span>' + (state.conn === 'offline' ? '서버에 연결하지 못했어요' : '불러오는 중') + '</span></div>';
        region.graph.hidden = true;
        renderBanner();
        return;
      }
      if (state.overview) {
        renderTop(null);
        renderBanner();
        region.head.innerHTML = overviewHTML(rt.filter);
        region.graph.hidden = true;
        region.panel.hidden = true;
        if (region.body) region.body.classList.add('no-panel');
        renderSheet();
        return;
      }
      // 새로 지어내기 입력은 다른 캐릭터 화면 위에 열리지 않는다. 입력만 보인다.
      if (state.form.open) {
        renderTop(null);
        renderBanner();
        region.head.innerHTML = formHTML();
        region.graph.hidden = true;
        region.panel.hidden = true;
        if (region.body) region.body.classList.add('no-panel');
        renderSheet();
        return;
      }
      const scope = setupScope();
      // 시작 장면이 알려지면 S8c 이름을 그 장면에 맞춘다(모티브 기본은 팬 통화).
      if (state.detail && state.graph.byStage.get('s8c')) state.graph.byStage.get('s8c').name = s8cName(state.detail.origin || state.graph.origin, text(state.detail.chapterTemplate));
      const v = state.detail ? views(scope) : {};
      if (state.detail && !state.sel) {
        const tasks = buildTasks(state.graph, state.detail, v, {});
        const running = Object.keys(v).find((id) => v[id].kind === 'run' || v[id].kind === 'retry');
        const goal = goalStages(state.graph, state.detail);
        // 모티브는 목표 밖 단계(예: 기준 사진의 '이 단계까지 실행')로 시작하지 않는다. 할 일이 없으면 마지막으로 끝난 단계를 보인다.
        const next = goal ? lastFinished(goal, v) : state.graph.stages.find((s) => !['done', 'skip', 'out'].includes(v[s.id].kind));
        state.sel = (tasks[0] && tasks[0].stage) || running || (next && next.id) || (goal ? null : 's11');
        if (state.sel) loadGateViews();
      }
      if (state.detail && modelMode() && !promptOnly(state.detail)) {
        if (!state.wasModel && !state.keepStep) { state.mstep = null; state.mconfirm = null; state.bindError = ''; }
        state.wasModel = true;
        state.keepStep = false;
        renderTop(v);
        renderBanner();
        region.head.innerHTML = titleHTML() + viewTabsHTML() + modelHTML();
        region.graph.hidden = true;
        region.panel.hidden = false;
        if (region.body) region.body.classList.remove('no-panel');
        region.panel.innerHTML = '<div class="fl-panel">' + modelPanelHTML() + '</div>';
        renderSheet();
        return;
      }
      state.wasModel = false;
      renderTop(v);
      renderBanner();
      const draft = state.detail && notStarted() && isMotif(state.detail);
      if (state.projects && !characters().length) region.head.innerHTML = emptyHTML();
      else if (!state.detail) region.head.innerHTML = '';
      else region.head.innerHTML = titleHTML() + (draft ? '' : viewTabsHTML()) + (draft ? draftHTML() : notStarted() ? setupHTML() : tasksHTML(v));
      // 시작하지 않은 모티브 초안은 공정 그래프와 단계 패널을 보이지 않는다(원문 화면에서 시작한다).
      if (draft) region.graph.hidden = true;
      else renderGraph(v, scope);
      const panel = Boolean(state.detail) && !draft;
      region.panel.hidden = !panel;
      if (region.body) region.body.classList.toggle('no-panel', !panel);
      if (panel) region.panel.innerHTML = '<div class="fl-panel">' + panelHTML(v) + '</div>';
      renderSheet();
    }
    // 목표 경로에서 가장 늦게 끝난 단계.
    function lastFinished(goal, v) {
      const rows = rowsById(state.detail);
      const hist = state.detail.history || {};
      let best = null;
      let bestT = -1;
      state.graph.stages.forEach((s, i) => {
        if (!goal.has(s.id) || !['done', 'skip'].includes((v[s.id] || {}).kind)) return;
        const h = hist[s.id] || [];
        const t = parseTime((rows.get(s.id) || {}).endedAt) || parseTime((h[h.length - 1] || {}).endedAt) || i;
        if (t >= bestT) { bestT = t; best = s; }
      });
      return best;
    }

    // ---- 동작 ----
    async function run(payload, okText) {
      state.busy = true;
      state.feedback = null;
      render();
      try {
        const job = await request('POST', '/api/jobs', payload);
        state.runJobId = payload.action === 'run' ? job.jobId : null;
        state.feedback = okText ? { tone: 'ok', text: okText } : null;
      } catch (error) {
        state.feedback = { tone: 'bad', text: error.message };
        if (error.network) state.conn = 'offline';
      }
      state.busy = false;
      await refresh(false);
    }
    async function create(form) {
      state.form.slug = form.querySelector('[data-slug]').value.trim();
      state.form.brief = form.querySelector('[data-brief]').value;
      const voiceInput = form.querySelector('[data-voice]');
      state.form.voice = voiceInput ? voiceInput.value : '';
      if (!state.form.brief.trim()) { state.form.error = '어떤 캐릭터인지 적어 주세요.'; render(); return; }
      if (state.form.slug && !/^[a-z0-9][a-z0-9-]{0,40}$/.test(state.form.slug)) { state.form.error = '짧은 이름은 영문 소문자나 숫자로 시작하고, 영문 소문자·숫자·하이픈만 쓸 수 있어요. 비워 두면 자동으로 정해요.'; render(); return; }
      let payload;
      try { payload = R.createCharacterRequest(state.form.slug || autoSlug(state.form.brief), state.form.brief, state.form.voice); } catch (error) { state.form.error = error.message; render(); return; }
      state.busy = true;
      state.form.error = '';
      render();
      try {
        const data = await request('POST', '/api/runtime/characters', payload);
        state.form = { open: false, slug: '', brief: '', voice: '', error: '' };
        state.feedback = { tone: 'ok', text: '캐릭터를 등록했어요. 어디까지 돌릴지 고르고 실행을 시작하세요.' };
        global.location.hash = '#c/' + encodeURIComponent(data.characterId);
      } catch (error) {
        state.form.error = error.message;
      }
      state.busy = false;
      await refresh(false);
    }
    // 보관하기·보관 풀기(3차 약속 3). 지우지 않고 목록 기본 보기에서만 숨긴다.
    async function setArchived(on) {
      const id = state.detail && state.detail.id;
      if (!id) return;
      state.menuOpen = false;
      state.busy = true;
      render();
      try {
        await request('POST', '/api/characters/' + encodeURIComponent(id) + '/archive', { archived: on });
        const c = characters().find((x) => x.id === id);
        if (c) c.archived = on;
        state.feedback = { tone: 'ok', text: on ? '보관했어요. 목록 아래 보관함에서 다시 찾을 수 있어요.' : '보관을 풀었어요. 다시 목록에 보여요.' };
        if (on) { state.showArchived = false; global.location.hash = '#all'; }
      } catch (error) {
        state.feedback = { tone: 'bad', text: error.status === 404 || error.status === 405 ? '이 서버에서는 아직 보관할 수 없어요. 서버를 새 버전으로 올린 뒤 다시 해 주세요.' : error.message };
      }
      state.busy = false;
      await refresh(false);
    }
    function copyError(stage) {
      const row = rowsById(state.detail).get(stage) || {};
      const hist = ((state.detail && state.detail.history) || {})[stage] || [];
      const lines = ['캐릭터: ' + (state.detail ? state.detail.id : ''), '단계: ' + stage + ' (' + ((state.graph.byStage.get(stage) || {}).name || '') + ')', '회차: ' + (row.attempts || '?'), '오류: ' + text(row.lastError)]
        .concat(hist.filter((h) => h.error).map((h) => h.attempt + '회차 ' + text(h.startedAt) + ': ' + h.error));
      const body = lines.join('\n');
      const done = () => { state.feedback = { tone: 'ok', text: '오류 내용을 복사했어요. 담당자에게 붙여 보내 주세요.' }; render(); };
      if (global.navigator && global.navigator.clipboard && global.navigator.clipboard.writeText) global.navigator.clipboard.writeText(body).then(done, () => { state.feedback = { tone: 'bad', text: '복사하지 못했어요. 기술 정보를 직접 골라 복사해 주세요.' }; render(); });
      else { state.feedback = { tone: 'bad', text: '이 브라우저에서는 복사할 수 없어요. 기술 정보를 직접 골라 복사해 주세요.' }; render(); }
    }
    function onClick(event) {
      if (swallowClick) { swallowClick = false; if (region.view && region.view.contains(event.target)) { event.preventDefault(); return; } }
      if (event.target === region.scrim) { closeSheet(); return; }
      if (state.menuOpen && !(event.target.closest && event.target.closest('.fd-more'))) { state.menuOpen = false; render(); }
      const el = event.target.closest('[data-act]');
      if (!el || el.disabled || (el.getAttribute('aria-disabled') === 'true' && el.dataset.act === 'toggle')) return;
      const act = el.dataset.act;
      const id = state.detail && state.detail.id;
      if (act === 'select') { state.sel = el.dataset.stage; const lane = laneMap(state.graph).get(state.sel); if (lane) state.open.add(lane); loadGateViews(); render(); }
      else if (act === 'menu') { state.menuOpen = !state.menuOpen; render(); }
      else if (act === 'archive') setArchived(el.dataset.v === '1');
      else if (act === 'archived') { state.showArchived = !state.showArchived; state.form.open = false; if (route().overview) render(); else global.location.hash = '#all'; }
      else if (act === 'show-off') { state.showOff = !state.showOff; zoomFit(); render(); }
      else if (act === 'more') { state.moreOpen = !state.moreOpen; render(); }
      else if (act === 'video-open') { if (state.video && state.video.open) { state.video = null; render(); } else openVideo(); }
      else if (act === 'video-cancel') { state.video = null; render(); const b = doc.querySelector('[data-act="video-open"]'); if (b) b.focus(); }
      else if (act === 'video-go') startVideo();
      else if (act === 'resume-more') { state.moreOpen = false; run(R.runRequest(id, el.dataset.until || 'sx', []), '이어서 실행을 요청했어요. 비용이 큰 단계는 시작하기 전에 다시 물어봐요.'); }
      else if (act === 'toggle') { const lane = el.dataset.lane; if (state.open.has(lane)) state.open.delete(lane); else state.open.add(lane); render(); }
      else if (act === 'review') { state.batch = null; state.opener = el; state.review = { gate: el.dataset.gate, stage: el.dataset.stage || (state.graph.byGate.get(el.dataset.gate) || {}).stage, readonly: el.dataset.readonly === '1' }; state.sel = state.review.stage; render(); }
      else if (act === 'close-review') closeSheet();
      else if (act === 'confirm') { state.confirming = el.dataset.stage; loadPlan(el.dataset.stage); render(); const go = doc.querySelector('[data-act="confirm-go"]'); if (go) go.focus(); }
      else if (act === 'confirm-all') { state.confirming = '__all'; R.extractHeld(state.detail || {}).forEach((h) => loadPlan(h.stage)); render(); const go = doc.querySelector('[data-act="confirm-all-go"]'); if (go) go.focus(); }
      else if (act === 'confirm-all-go') { const stages = R.extractHeld(state.detail || {}).map((h) => h.stage); state.confirming = null; run(R.runRequest(id, currentUntil() || orchestrator().resumeUntil || 'sx', stages), '유료 단계 ' + stages.length + '개 실행을 요청했어요.'); }
      else if (act === 'help') { if (global.open) global.open('help.html' + (el.dataset.anchor ? '#' + el.dataset.anchor : ''), '_blank', 'noopener'); }
      else if (act === 'target-first') { state.target = el.dataset.gate || 'G1'; render(); }
      else if (act === 'next-review') { state.nextTarget = nextReviewAfter(el.dataset.gate); openNextTarget(); }
      else if (act === 'confirm-cancel') { state.confirming = null; render(); }
      else if (act === 'confirm-go') { const held = R.extractHeld(state.detail).find((h) => h.stage === el.dataset.stage) || { stage: el.dataset.stage }; state.confirming = null; run(R.confirmHeldRequest(id, held), '유료 실행을 요청했어요. 이 단계만 시작해요.'); }
      else if (act === 'copy-error') copyError(el.dataset.stage);
      else if (act === 'mstep') { state.mstep = el.dataset.step; state.mconfirm = null; render(); }
      else if (act === 'open-model') { state.mstep = el.dataset.step || null; state.mconfirm = null; goModel(); }
      else if (act === 'mconfirm') { state.mconfirm = el.dataset.v; state.mstep = el.dataset.step || state.mstep || 'train'; goModel(); const go = doc.querySelector('.md-confirm .btn:not(.ghost)'); if (go) go.focus(); }
      else if (act === 'mconfirm-cancel') { state.mconfirm = null; render(); }
      else if (act === 'train-go' || act === 'train-retry') { state.mconfirm = null; run({ characterId: id, action: 'train', confirm: ['s10t'], until: 's10t' }, act === 'train-go' ? '학습을 시작했어요. 진행은 학습 단계에서 볼 수 있어요.' : '결과를 다시 받아 오고 있어요.'); }
      // 학습 없이 진행은 평가 검토(G8)까지만 이어 간다. 다른 목표 작업을 따라가지 않는다.
      else if (act === 'skip-go') { state.mconfirm = null; run({ characterId: id, action: 'skip-training', until: 'G8' }, '학습 없이 진행해요. 평가에서 긴 프롬프트 채택을 확인해 주세요.'); }
      else if (act === 'model-run' && MODEL_RUN_UNTIL[el.dataset.stage]) run(R.runRequest(id, MODEL_RUN_UNTIL[el.dataset.stage], []), MODEL_RUN_OK[el.dataset.stage]);
      else if (act === 'bind-pick') { const input = doc.querySelector('[data-bind-file]'); if (input) input.click(); }
      else if (act === 'stop-go') { state.mconfirm = null; post('/api/characters/' + encodeURIComponent(id) + '/training/stop', '중단을 요청했어요. GPU를 반납하고 멈춰요.'); }
      else if (act === 'release-go') { state.mconfirm = null; post('/api/characters/' + encodeURIComponent(id) + '/training/release', '결과를 버리고 GPU를 반납했어요.'); }
      else if (act === 'zoom-in') zoomStep(1);
      else if (act === 'zoom-out') zoomStep(-1);
      else if (act === 'zoom-fit') zoomFit();
      else if (act === 'focus') toggleFocus();
      else if (act === 'overview') { state.batch = null; state.form.open = false; global.location.hash = '#all'; }
      else if (act === 'ov-clear') { state.ov = { q: '', gate: '' }; if (route().filter !== 'all') global.location.hash = '#all'; else render(); }
      else if (act === 'ov-review') { state.batch = el.dataset.gate; state.pendingReview = { id: el.dataset.id, gate: el.dataset.gate, stage: el.dataset.stage }; global.location.hash = '#c/' + encodeURIComponent(el.dataset.id); }
      else if (act === 'next-batch') { const nb = nextInBatch(); if (nb) { const t = nb.next.tasks.find((x) => x.kind === 'wait' && x.gate === state.batch) || {}; state.pendingReview = { id: nb.next.c.id, gate: state.batch, stage: t.stage }; closeSheet(false); global.location.hash = '#c/' + encodeURIComponent(nb.next.c.id); } }
      else if (act === 'retry') run(R.runRequest(id, runGoal(state.graph, state.detail, orchestrator().resumeUntil, el.dataset.stage), []), '다시 실행을 요청했어요. 통과하면 목표까지 이어서 진행해요.');
      else if (act === 'run-stage') run(R.runRequest(id, el.dataset.stage, []), '이 단계까지 실행을 요청했어요.');
      else if (act === 'start') run(R.runRequest(id, state.target || defaultTarget(), []), '실행을 시작했어요. 진행 상황은 서버 기록을 따라요.');
      else if (act === 'resume') run(R.runRequest(id, el.dataset.stage || currentUntil(), []), '이어서 실행을 요청했어요.');
      else if (act === 'new') { state.form.open = true; render(); const f = doc.querySelector('[data-brief]'); if (f) f.focus(); }
      else if (act === 'cancel-form') { state.form.open = false; render(); }
      else if (act === 'pick') { state.batch = null; state.form.open = false; global.location.hash = '#c/' + encodeURIComponent(el.dataset.id); }
      else if (act === 'inbox') { state.batch = null; state.form.open = false; global.location.hash = '#all/mine'; }
      else if (act === 'theme') { state.theme = el.dataset.theme; if (store) { if (state.theme === 'system') store.removeItem('fd-theme'); else store.setItem('fd-theme', state.theme); } applyTheme(); render(); }
    }
    // 결정 뒤 이어서 볼 검토: 같은 캐릭터의 다른 검토를 먼저, 없으면 다른 캐릭터의 가장 오래된 검토(D-0129).
    function nextReviewAfter(gate) {
      if (!state.graph || !state.detail) return null;
      const mine = summaryOf({ id: state.detail.id }).tasks.filter((x) => x.kind === 'wait' && x.gate !== gate);
      if (mine.length) return { id: state.detail.id, gate: mine[0].gate, stage: mine[0].stage, label: '다음 검토 · ' + mine[0].title };
      const others = characters().filter((c) => c.id !== state.detail.id).map(summaryOf)
        .map((x) => ({ s: x, t: x.tasks.find((y) => y.kind === 'wait') })).filter((x) => x.t);
      others.sort((a, b) => (a.s.oldest || Infinity) - (b.s.oldest || Infinity));
      if (!others.length) return null;
      const o = others[0];
      return { id: o.s.c.id, gate: o.t.gate, stage: o.t.stage, label: '다음 검토 · ' + labelOf(o.s.c) + ' · ' + o.t.title };
    }
    function openNextTarget() {
      const t = state.nextTarget;
      if (!t) return;
      state.nextTarget = null;
      state.notes = state.notes.filter((n) => n.act !== 'next-review');
      if (state.detail && t.id === state.detail.id) {
        state.batch = null;
        state.review = { gate: t.gate, stage: t.stage || (state.graph.byGate.get(t.gate) || {}).stage, readonly: false };
        state.sel = state.review.stage;
        render();
      } else {
        state.pendingReview = { id: t.id, gate: t.gate, stage: t.stage };
        global.location.hash = '#c/' + encodeURIComponent(t.id);
      }
    }
    function onChange(event) {
      const el = event.target;
      if (el.matches('[data-bind-file]')) { const file = el.files && el.files[0]; connectModel(file); return; }
      if (el.matches('[data-pick]')) {
        if (el.value === '__new') { state.form.open = true; render(); return; }
        if (el.value === '__src') { global.location.href = 'sources.html'; return; }
        if (el.value === '__all') { global.location.hash = '#all'; return; }
        state.form.open = false;
        global.location.hash = '#c/' + encodeURIComponent(el.value);
      } else if (el.matches('[data-target]')) { state.target = el.value; render(); }
      else if (el.matches('[data-ov-gate]')) { state.ov.gate = el.value; render(); }
      else if (el.name === 'videoTierPick' && state.video) { state.video.tier = el.value; render(); const r0 = doc.querySelector('[name="videoTierPick"][value="' + el.value + '"]'); if (r0) r0.focus(); }
    }
    function onSubmit(event) {
      if (event.target.matches('[data-form]')) { event.preventDefault(); create(event.target); }
    }
    function onInput(event) {
      if (!event.target.matches) return;
      if (event.target.matches('[data-ov-q]')) { state.ov.q = event.target.value; render(); }
      else if (event.target.matches('[data-side-q]')) { state.sq = event.target.value; render(); }
      else if (event.target.matches('[data-sig]') && state.video) { state.video.sig = Object.assign({}, state.video.sig, { [event.target.dataset.sig]: event.target.value }); }
    }
    function onKey(event) {
      if (event.key === 'Escape' && state.menuOpen) { event.preventDefault(); state.menuOpen = false; render(); const b = doc.querySelector('[data-act="menu"]'); if (b) b.focus(); return; }
      if (event.key === 'Escape' && state.review) { event.preventDefault(); closeSheet(); return; }
      if (event.key === 'Escape' && state.confirming) { event.preventDefault(); state.confirming = null; render(); return; }
      if (event.key === 'Escape' && state.focus) { event.preventDefault(); toggleFocus(false); return; }
      onViewKey(event);
    }
    function onHash() { refresh(false); }
    function onOnline() { state.conn = 'reconnecting'; refresh(true); }
    function onOffline() { state.conn = 'offline'; render(); }
    function onScheme() { if (state.theme === 'system') applyTheme(); }
    // 시트 안 관문 화면이 결정을 알린다. 새 판이 빨리 생겨 상태 변화를 못 보더라도 시트를 닫고 알림을 남긴다.
    function onMessage(event) {
      const m = event && event.data;
      if (global.location && event.origin && event.origin !== global.location.origin) return;
      if (m && m.type === 'foundry:close' && state.review) { closeSheet(); return; }
      if (!m || m.type !== 'foundry:gate-decided' || !state.review || state.review.readonly) return;
      if (m.gate !== state.review.gate || m.characterId !== state.characterId) return;
      if (upper(m.status) === 'AWAITING_HUMAN') return; // 묶음마다 따로 보내는 관문(G7a)은 시트를 유지한다
      const title = (state.graph && state.graph.byGate.get(m.gate) || {}).title || m.gate;
      const kind = upper(m.decision);
      const note = kind === 'REJECT' ? { t: title + ': 처음부터 다시 만들도록 보냈어요.', s: '새 버전이 생기면 다시 검토할 수 있어요.' }
        : kind === 'REQUEST_CHANGES' ? { t: title + ': 고칠 점을 보냈어요.', s: '고친 버전이 생기면 다시 검토할 수 있어요.' }
          : { t: title + ': 결정을 기록했어요.', s: '' };
      note.at = Date.now();
      const nb = state.batch === m.gate ? nextInBatch() : null;
      if (nb) { note.act = 'next-batch'; note.label = '다음 건 검토 · ' + labelOf(nb.next.c) + ' (' + nb.left + '건 남음)'; }
      else { note.act = 'next-review'; note.gate = m.gate; }
      state.notes = [note].concat(state.notes).slice(0, 3);
      state.decided[m.gate] = Date.now();
      state.reselect = true; // 새 상태를 읽은 뒤 다음 할 일을 인스펙터에 보인다
      closeSheet();
      render();
    }

    doc.addEventListener('click', onClick);
    doc.addEventListener('change', onChange);
    doc.addEventListener('submit', onSubmit);
    doc.addEventListener('keydown', onKey);
    doc.addEventListener('input', onInput);
    if (region.view) {
      region.view.addEventListener('pointerdown', onDown);
      region.view.addEventListener('pointermove', onMove);
      region.view.addEventListener('pointerup', onUp);
      region.view.addEventListener('pointercancel', onUp);
      region.view.addEventListener('wheel', onWheel, { passive: false });
    }
    global.addEventListener('hashchange', onHash);
    global.addEventListener('message', onMessage);
    global.addEventListener('online', onOnline);
    global.addEventListener('offline', onOffline);
    if (media && media.addEventListener) media.addEventListener('change', onScheme);
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => { if (state.detail) drawEdges(views(setupScope())); }) : null;
    if (ro) ro.observe(region.graph);
    const tick = setInterval(() => { if (!doc.hidden) render(); }, 30000);
    const poll = setInterval(() => { if (!doc.hidden && state.conn !== 'live') refresh(false); }, 30000);
    applyTheme();
    render();
    refresh(true).then(startEvents);

    return {
      state,
      refresh,
      destroy() {
        state.destroyed = true;
        if (reference) reference.destroy();
        clearInterval(tick);
        clearInterval(poll);
        clearTimeout(refreshTimer);
        clearTimeout(trainTimer);
        clearTimeout(listTimer);
        if (source) source.close();
        if (ro) ro.disconnect();
        doc.removeEventListener('click', onClick);
        doc.removeEventListener('change', onChange);
        doc.removeEventListener('submit', onSubmit);
        doc.removeEventListener('keydown', onKey);
        doc.removeEventListener('input', onInput);
        if (region.view) {
          region.view.removeEventListener('pointerdown', onDown);
          region.view.removeEventListener('pointermove', onMove);
          region.view.removeEventListener('pointerup', onUp);
          region.view.removeEventListener('pointercancel', onUp);
          region.view.removeEventListener('wheel', onWheel);
        }
        global.removeEventListener('hashchange', onHash);
        global.removeEventListener('message', onMessage);
        global.removeEventListener('online', onOnline);
        global.removeEventListener('offline', onOffline);
        if (media && media.removeEventListener) media.removeEventListener('change', onScheme);
      }
    };
  }

  const pure = { chatStatusText, runGoal, runFeedback, plainError, since, span, clock, predecessors, descendants, ancestors, reducedEdges, crossLaneEdges, viewsFor, laneKind, edgeClass, buildTasks, diffNotes, failReason, targetLabel, recommendation, reworkLine, layoutOf, trackLabel, stageNameHTML, s8cName, chatHref, isChatReady, statusOf, STATUS_LABEL, goalStages, goalOf, goalView, nameLabels, labelOf, autoSlug, splitAttempts, MODE_LABEL, MARK, VIDEO_TIERS, tierOf, tierName, tierCardsHTML, videoText, videoTone, canMakeVideo, readyPhotos, modelNext, modelTasks, modelSteps, modelActive, MODEL_RUN_UNTIL, mount };
  if (typeof module !== 'undefined' && module.exports) module.exports = pure;
  if (global) global.FactoryFlow = pure;
})(typeof window !== 'undefined' ? window : null);
