(function (global) {
  'use strict';

  // 캐릭터 공장 진행 화면(D-0101). 서버 기록만 읽는다. 가짜 진행·가짜 시간·자동 승인은 만들지 않는다.
  const R = (typeof module !== 'undefined' && module.exports) ? require('./runtime.js') : global.FactoryRuntime;
  const E = R.escapeHTML;

  // 팀 줄(서버 LANES id) → 그래프 칸. 위 줄은 외모 → 장면 → 영상, 아래 줄은 기획 → 페르소나 → 데이터 → 학습, 패키지는 오른쪽.
  // 트윈은 맨 앞 열에 출처 팀(so)이 생긴다.
  const AREA = { source: 'so', appearance: 'ap', plan: 'pl', scene: 'sc', video: 'vd', persona: 'ps', data: 'dt', training: 'tr', release: 'pk' };
  const CELL = { ap: [0, 0], sc: [0, 1], vd: [0, 2], pl: [1, 0], ps: [1, 1], dt: [1, 2], tr: [1, 3], pk: [0.5, 4] };
  // 그래프 칸 배치. 오리지널은 CELL 그대로다. 트윈은 출처 팀이 맨 앞 열(두 줄 가운데)에 서고 나머지는 한 열씩 밀린다.
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
  const MODE_LABEL = { TRAIN: '학습', BIND_EXISTING: '학습된 모델 연결', PROMPT_ONLY: '긴 프롬프트' };
  function trackLabel(c) {
    const x = c || {};
    if (x.origin !== 'SOURCE') return '오리지널';
    return (x.originLabel || '트윈') + ' · ' + (MODE_LABEL[x.modelMode] || MODE_LABEL.TRAIN);
  }
  // 트윈 단계 줄에 붙이는 쉬운 설명. 단계 이름은 서버 그래프를 그대로 쓴다.
  const TWIN_HINT = { s2: '받은 사진에서 기준 사진 고르기' };
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
    copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>'
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
  // 'video: xai_video/grok-video' 같은 공급자 표기를 쉬운 말로(D-0129).
  const KIND_KO = { video: '영상', image: '이미지', text: '글', judge: '검토' };
  const ADAPTER_KO = { xai_video: 'xAI 그록 영상', grok_oauth: '그록(계정 연결)', grok_web: '그록 웹', fake_video: '시험용 가짜 영상', fake: '시험용 가짜 모델', fake_image: '시험용 가짜 이미지', codex_image: 'Codex 이미지', openai: 'OpenAI', gemini: 'Gemini', vertex_gemini: 'Vertex Gemini' };
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
    graph.stages.forEach((def) => {
      if ((views[def.id] || {}).kind !== 'fail') return;
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
    // 앞 단계가 모두 끝났는데 도는 작업이 없으면 공정이 조용히 멈춘다. 이어서 실행할 수 있다고 알린다.
    if (!busy && opts.goal) {
      const preds = predecessors(graph);
      const scope = ancestors(graph, opts.goal);
      // 서버가 마지막 작업에서 시작할 수 없다고 남긴 단계(그래프 밖 규칙: 외모 축은 s2 승인 뒤 기획 등)는 빼서 거짓 안내를 막는다.
      const lastJob = (detail && detail.lastJob) || {};
      const blockedByServer = new Set(Array.isArray(lastJob.blocked) ? lastJob.blocked : []);
      const ready = graph.stages.filter((def) => {
        if ((views[def.id] || {}).kind !== 'todo' || !scope.has(def.id) || blockedByServer.has(def.id)) return false;
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
      panel: $('[data-panel]'), sheet: $('[data-sheet]'), scrim: $('[data-scrim]')
    };
    const store = (() => { try { return global.localStorage; } catch (error) { return null; } })();
    const state = {
      graph: null, rawGraph: null, health: null, projects: null, characterId: null, detail: null,
      gateViews: new Map(), sel: null, review: null, open: new Set(), notes: [], feedback: null, decided: {},
      conn: 'connecting', lastSync: null, busy: false, form: { open: false, slug: '', brief: '', error: '' },
      target: null, sheetKey: '', opener: null, openerGate: '', destroyed: false,
      overview: false, ov: { q: '', gate: '' }, batch: null, pendingReview: null, confirming: null, plans: {}, nextTarget: null, focus: false,
      // 갈래·모델 준비 방식마다 그래프가 다르다. 'CREATED|TRAIN' 같은 열쇠로 받아 둔 그래프(개요·받은 일이 캐릭터마다 자기 그래프로 센다).
      graphs: new Map(), graphSeq: 0, graphAsk: new Set(),
      theme: (store && ['light', 'dark'].includes(store.getItem('fd-theme'))) ? store.getItem('fd-theme') : 'system'
    };
    let refreshTimer = null;
    let listTimer = null;
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
      const m = /^#c\/(.+)$/.exec(text(global.location && global.location.hash));
      return m ? decodeURIComponent(m[1]) : null;
    }
    function route() {
      const m = /^#all(?:\/(\w+))?/.exec(text(global.location && global.location.hash));
      return m ? { overview: true, filter: ['mine', 'run', 'fail', 'done'].includes(m[1]) ? m[1] : 'all' } : { overview: false, filter: '' };
    }
    function characters() { return (state.projects && state.projects.characters) || []; }
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
      const rank = fail ? 0 : review ? 1 : paid ? 2 : running ? 3 : isComplete ? 6 : fresh ? 5 : 4;
      return { c, tasks, fail, review, paid, todo: fail + review + paid, done, total: graph.stages.length, complete: isComplete, fresh, running, oldest: waits.length ? Math.min.apply(null, waits) : null, lanes, rank, top: tasks[0] || null, updated: parseTime(det.updatedAt || c.updatedAt) };
    }
    function statusDot(s) { return s.fail ? 'fail' : s.todo ? 'wait' : s.running ? 'run' : s.complete ? 'ok' : ''; }
    function nextInBatch() {
      if (!state.batch || !state.graph) return null;
      const list = characters().filter((c) => c.id !== state.characterId).map(summaryOf)
        .filter((s) => s.tasks.some((x) => x.kind === 'wait' && x.gate === state.batch));
      list.sort((a, b) => (a.oldest || Infinity) - (b.oldest || Infinity));
      return list.length ? { next: list[0], left: list.length } : null;
    }
    function pickDefault() {
      const list = characters();
      if (!list.length) return null;
      const waiting = list.find((c) => c.awaitingHuman);
      const running = list.find((c) => c.job);
      return (waiting || running || list.slice().sort((a, b) => text(b.updatedAt).localeCompare(text(a.updatedAt)))[0]).id;
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
    async function loadProjects() { state.projects = await request('GET', '/api/projects'); }
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
        const wanted = routeId() || state.characterId || pickDefault();
        const changed = wanted !== state.characterId;
        if (changed) {
          state.characterId = wanted; state.detail = null; state.sel = null; closeSheet(false); state.notes = []; state.open = new Set(); state.target = null;
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
      const d = state.detail || {};
      // 실행 확인·다시 실행 작업은 그 단계까지만 돈다. 전체 목표는 그런 작업이 아닌 가장 최근 작업에서 읽는다.
      const jobs = [d.job].concat(Array.isArray(d.jobs) ? d.jobs : []).filter(Boolean);
      const single = (j) => (Array.isArray(j.confirm) && j.confirm.length) || (j.until && j.until !== 'sx' && state.graph && state.graph.byStage && state.graph.byStage.has(j.until));
      const job = jobs.find((j) => !single(j)) || d.lastJob;
      return job ? job.until : '';
    }
    function elapsed(now) {
      const hist = (state.detail && state.detail.history) || {};
      let first = null;
      let last = null;
      Object.keys(hist).forEach((id) => (hist[id] || []).forEach((a) => {
        const s = parseTime(a.startedAt);
        const e = parseTime(a.endedAt);
        if (s != null && (first == null || s < first)) first = s;
        if (e != null && (last == null || e > last)) last = e;
      }));
      if (first == null) return '';
      return span((complete() && last ? last : now) - first) + (complete() ? ' 걸림' : ' 경과');
    }
    function nameOf(d) { return displayName(d && ((d.persona && d.persona.name) || (d.summary && d.summary.name) || d.name), d && d.id); }
    function charStatus(c) {
      if (c.awaitingHuman) return 'wait';
      if ((c.stages || []).some((s) => upper(s.status) === 'CHECK_FAILED')) return 'fail';
      if (c.job) return 'run';
      const p = c.progress || {};
      if (p.total && p.done >= p.total) return 'ok';
      return '';
    }
    function counts(v) {
      const c = { run: 0, fail: 0, wait: 0, done: 0 };
      Object.keys(v).forEach((id) => { const k = v[id].kind; if (k === 'run' || k === 'retry') c.run++; if (k === 'fail') c.fail++; if (k === 'wait' || k === 'confirm') c.wait++; if (k === 'done' || k === 'skip') c.done++; });
      return c;
    }

    // ---- 사이드바 ----
    function renderSide() {
      if (!region.side) return;
      const list = characters();
      // 실패·검토·유료 확인을 모든 캐릭터에서 같은 기준으로 센다(받은 일 = 머리줄 = 개요).
      const sums = state.graph ? list.map(summaryOf) : [];
      const byId = new Map(sums.map((s) => [s.c.id, s]));
      const inbox = sums.reduce((n, s) => n + s.todo, 0);
      const rt = route();
      const items = list.map((c) => {
        const s = byId.get(c.id);
        const name = displayName(c.name, c.id);
        const waiting = s ? s.todo : 0;
        return '<button type="button" class="fd-nav" data-act="pick" data-id="' + E(c.id) + '"' + (!rt.overview && c.id === state.characterId ? ' aria-current="page"' : '') + ' title="' + E(name) + '">' +
          '<span class="fd-av" aria-hidden="true">' + E(Array.from(name)[0] || '?') + '<span class="st ' + (s ? statusDot(s) : '') + '"></span></span>' +
          '<span class="lbl">' + E(name) + '</span>' +
          (waiting ? '<span class="num attn"><span class="sr">할 일 </span>' + waiting + '<span class="u">건</span></span>' : '<span class="num" title="' + (s ? E(s.done + '/' + s.total + '단계 완료') : '') + '">' + (s ? s.done + '/' + s.total : '') + '</span>') + '</button>';
      }).join('');
      const theme = [['system', 'monitor', '시스템 설정 따르기'], ['light', 'sun', '밝은 화면'], ['dark', 'moon', '어두운 화면']]
        .map((t) => '<button type="button" data-act="theme" data-theme="' + t[0] + '" aria-pressed="' + (state.theme === t[0]) + '" aria-label="' + t[2] + '" title="' + t[2] + '">' + icon(t[1]) + '</button>').join('');
      region.side.innerHTML = '<div class="fd-brand">' + MARK + '<div class="fd-word"><b>Foundry</b><small>캐릭터 공장</small></div></div>' +
        '<div class="fd-side-actions"><button type="button" class="btn block" data-act="new" title="새 캐릭터">' + icon('plus') + '<span class="lbl">새 캐릭터</span></button></div>' +
        '<nav aria-label="캐릭터 탐색"><button type="button" class="fd-nav" data-act="overview" title="전체 캐릭터"' + (rt.overview && rt.filter !== 'mine' ? ' aria-current="page"' : '') + '>' + icon('grid') + '<span class="lbl">전체 캐릭터</span><span class="num">' + list.length + '명</span></button>' +
        '<button type="button" class="fd-nav" data-act="inbox" title="받은 일"' + (rt.overview && rt.filter === 'mine' ? ' aria-current="page"' : '') + '>' + icon('inbox') + '<span class="lbl">받은 일</span>' + (inbox ? '<span class="num attn"><span class="sr">할 일 </span>' + inbox + '<span class="u">건</span></span>' : '<span class="num">0건</span>') + '</button>' +
        '<h2>캐릭터</h2>' + (items || '<p class="hint" style="padding:0 8px">아직 없어요</p>') + '</nav>' +
        '<div class="fd-side-foot"><a class="fd-help" href="help.html" target="_blank" rel="noopener" title="사용 안내" aria-label="사용 안내">?</a><div class="fd-theme" role="group" aria-label="화면 테마">' + theme + '</div><div class="fd-foot-links"><a href="help.html" target="_blank" rel="noopener">사용 안내</a><a href="d-ops.html">이전 화면</a><a href="d-ops.html?panel=text">모델 설정</a></div></div>';
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
    function connHTML() {
      const conn = state.conn === 'offline' ? ['off', '연결 끊김 · 다시 연결하는 중'] : state.conn === 'reconnecting' ? ['wait', '다시 연결하는 중'] : state.conn === 'connecting' ? ['wait', '연결하는 중'] : ['', '연결됨' + (state.lastSync ? ' · 갱신 ' + clock(new Date(state.lastSync).toISOString()) : '')];
      return '<span class="fd-conn ' + conn[0] + '" role="status"><span class="d"></span>' + conn[1] + '</span>';
    }
    function renderTop(v) {
      const d = state.detail;
      const list = characters();
      const sums = state.graph ? list.map(summaryOf) : [];
      const label = (s) => s.fail ? ' · 멈춤' : s.review ? ' · 검토 대기' : s.paid ? ' · 유료 확인' : '';
      const picker = list.length ? '<label class="sr" for="fl-pick">캐릭터</label><select id="fl-pick" class="fd-pick" data-pick><option value="__all"' + (state.overview ? ' selected' : '') + '>전체 캐릭터</option>' + sums.map((s) => '<option value="' + E(s.c.id) + '"' + (!state.overview && s.c.id === state.characterId ? ' selected' : '') + '>' + E(displayName(s.c.name, s.c.id)) + label(s) + '</option>').join('') + '<option value="__new">+ 새 캐릭터</option></select>' : '';
      if (state.overview) {
        const fail = sums.filter((s) => s.fail).length;
        const mine = sums.filter((s) => s.todo).length;
        const run = sums.filter((s) => s.running).length;
        const pillsO = (fail ? '<span class="fl-pill fail"><span class="d"></span>멈춘 캐릭터 ' + fail + '명</span>' : '') + (mine ? '<span class="fl-pill wait"><span class="d"></span>내 차례 ' + mine + '명</span>' : '') + (run ? '<span class="fl-pill run"><span class="d"></span>진행 중 ' + run + '명</span>' : '');
        region.top.innerHTML = '<nav class="fd-crumb" aria-label="위치">' + (route().filter === 'mine' ? '<a class="up" href="#all">전체 캐릭터</a><span class="sep">/</span><b>받은 일</b>' : '<b>전체 캐릭터</b>') + '</nav>' + picker + pillsO + '<div class="fd-metrics"><span>캐릭터 <b>' + list.length + '</b>명</span>' + connHTML() + '</div>' + headThemeHTML();
        const todo = sums.reduce((n, s) => n + s.todo, 0);
        if (doc.title !== undefined) doc.title = (todo ? '(' + todo + ') ' : '') + '전체 캐릭터 · Foundry';
        return;
      }
      let pills = '';
      if (d) {
        if (complete()) pills += '<span class="fl-pill ok"><span class="d"></span>완료</span>';
        else if (notStarted()) pills += '<span class="fl-pill muted"><span class="d"></span>시작 전</span>';
        else {
          const c = counts(v);
          if (c.run) pills += '<span class="fl-pill run"><span class="d"></span>진행 중 ' + c.run + '단계</span>';
          else if (d.job) pills += '<span class="fl-pill run"><span class="d"></span>작업 준비 중</span>';
          else if (!c.fail && !c.wait) pills += '<span class="fl-pill muted"><span class="d"></span>멈춰 있음</span>';
          if (c.fail) pills += '<span class="fl-pill fail"><span class="d"></span>멈춘 단계 ' + c.fail + '</span>';
          if (c.wait) pills += '<span class="fl-pill wait"><span class="d"></span>사람 할 일 ' + c.wait + '건</span>';
        }
      }
      const meta = [];
      if (d && !notStarted()) {
        meta.push('<span>완료 <b>' + counts(v).done + '</b>/' + state.graph.stages.length + '단계</span>');
        const el = elapsed(Date.now());
        if (el) meta.push('<span>' + E(el) + '</span>');
        if (d.cost) meta.push('<span>추정 비용 <b>' + (d.cost.estUsd == null ? '—' : '$' + Number(d.cost.estUsd).toFixed(2)) + '</b>' + (d.cost.unpricedCalls ? ' · 단가 미확인 ' + d.cost.unpricedCalls + '건 제외' : '') + '</span>');
      }
      meta.push(connHTML());
      const crumb = d ? '<a class="up" href="#all">전체 캐릭터</a><span class="sep">/</span><b>' + E(nameOf(d)) + '</b>' : '<b>캐릭터</b>';
      region.top.innerHTML = '<nav class="fd-crumb" aria-label="위치">' + crumb + '</nav>' + picker + pills + '<div class="fd-metrics">' + meta.join('') + '</div>' + headThemeHTML();
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
      const until = currentUntil();
      const sub = notStarted() ? '아직 실행하지 않았어요' : (until ? '목표 ' + targetLabel(state.graph, until) : '');
      let prog = '';
      if (!notStarted()) {
        const s = summaryOf({ id: d.id });
        const pct = Math.round(s.done / s.total * 100);
        prog = '<span class="fd-prog-wrap"><span class="fd-prog" role="img" aria-label="' + E('전체 ' + s.total + '단계 중 ' + s.done + '단계 완료, ' + pct + '%') + '">' + s.lanes.map((l) => '<span class="seg ' + l.kind + '" title="' + E(l.label + ' ' + l.done + '/' + l.total) + '"></span>').join('') + '</span>' + s.done + '/' + s.total + '단계 · ' + pct + '%</span>';
      }
      const demo = d.origin === 'SOURCE' ? '<span class="fd-demo">' + E(DEMO_NOTE) + '</span>' : '';
      return '<div class="fd-title"><h1 tabindex="-1">' + E(nameOf(d)) + '</h1>' + trackHTML(d) + (sub ? '<p>' + E(sub) + '</p>' : '') + prog + (nameOf(d) !== d.id ? '<code>' + E(d.id) + '</code>' : '') + demo + '</div>';
    }
    function formHTML() {
      const f = state.form;
      return '<form class="fl-form" data-form><h2>새 캐릭터</h2><p class="hint">등록만 하고 바로 실행하지 않아요. 등록한 뒤 어디까지 돌릴지 고르고 시작해요.</p>' +
        '<label for="fl-slug">짧은 이름 (영문 소문자·숫자·하이픈)</label><input id="fl-slug" data-slug autocomplete="off" value="' + E(f.slug) + '" placeholder="예: cafe-owner">' +
        '<label for="fl-brief">브리프</label><textarea id="fl-brief" data-brief placeholder="타깃, 분위기, 성격, 챕터 배경 등을 적어 주세요.">' + E(f.brief) + '</textarea>' +
        (f.error ? '<p class="err" role="alert">' + E(f.error) + '</p>' : '') +
        '<div class="acts"><button type="submit" class="btn pri"' + (state.busy ? ' disabled' : '') + '>등록하기</button>' + (characters().length ? '<button type="button" class="btn ghost" data-act="cancel-form">취소</button>' : '') + '</div></form>';
    }
    function overviewHTML(filter) {
      const list = characters();
      if (!list.length) return emptyHTML();
      const all = list.map(summaryOf);
      const gates = new Map();
      all.forEach((s) => s.tasks.filter((x) => x.kind === 'wait').forEach((x) => gates.set(x.gate, (gates.get(x.gate) || 0) + 1)));
      if (state.ov.gate && !gates.has(state.ov.gate)) state.ov.gate = '';
      const counts = { all: all.length, mine: all.filter((s) => s.todo).length, run: all.filter((s) => s.running && !s.todo).length, fail: all.filter((s) => s.fail).length, done: all.filter((s) => s.complete).length };
      const q = state.ov.q.trim().toLowerCase();
      let rows = all.filter((s) => (filter === 'mine' ? s.todo > 0 : filter === 'run' ? s.running && !s.todo : filter === 'fail' ? s.fail > 0 : filter === 'done' ? s.complete : true));
      if (state.ov.gate) rows = rows.filter((s) => s.tasks.some((x) => x.kind === 'wait' && x.gate === state.ov.gate));
      if (q) rows = rows.filter((s) => (text(s.c.name) + ' ' + s.c.id + ' ' + text(s.c.persona && s.c.persona.job)).toLowerCase().indexOf(q) >= 0);
      rows.sort((a, b) => a.rank - b.rank || (a.oldest || Infinity) - (b.oldest || Infinity) || (b.updated || 0) - (a.updated || 0));
      const tabs = [['all', '전체'], ['mine', '내 차례'], ['run', '진행 중'], ['fail', '멈춤'], ['done', '완료']]
        .map((x) => '<a class="ov-tab" href="#all' + (x[0] === 'all' ? '' : '/' + x[0]) + '"' + (x[0] === filter ? ' aria-current="page"' : '') + '>' + x[1] + '<span class="n">' + counts[x[0]] + '명</span></a>').join('');
      const gateSel = gates.size ? '<label class="sr" for="ov-gate">검토 종류</label><select id="ov-gate" data-ov-gate><option value="">검토 종류 전체</option>' + Array.from(gates).map((x) => '<option value="' + E(x[0]) + '"' + (state.ov.gate === x[0] ? ' selected' : '') + '>' + E(gateTitle(x[0])) + ' · ' + x[1] + '건</option>').join('') + '</select>' : '';
      const search = '<label class="sr" for="ov-q">이름으로 찾기</label><input id="ov-q" data-ov-q type="search" placeholder="이름으로 찾기" value="' + E(state.ov.q) + '" autocomplete="off">';
      const head = '<div class="fd-title"><h1 tabindex="-1">' + (filter === 'mine' ? '받은 일' : '전체 캐릭터') + '</h1><p>' + (filter === 'mine' ? '모든 캐릭터에서 사람이 할 일(멈춤 · 검토 · 유료 확인)이 있는 캐릭터예요. 검토 종류로 거르면 같은 검토를 이어서 할 수 있어요.' : '캐릭터마다 어디까지 왔고 무엇을 기다리는지 봐요. 내 차례인 캐릭터가 위에 와요.') + '</p></div>';
      const bar = '<div class="ov-bar"><nav class="ov-tabs" aria-label="상태로 거르기">' + tabs + '</nav><div class="ov-tools">' + gateSel + search + '</div></div>';
      if (!rows.length) return head + bar + '<div class="fl-empty sm"><h2>' + (filter === 'mine' && !q && !state.ov.gate ? '지금 사람이 할 일이 없어요' : '조건에 맞는 캐릭터가 없어요') + '</h2>' + (q || state.ov.gate || filter !== 'all' ? '<div class="acts"><button type="button" class="btn" data-act="ov-clear">거르기 지우기</button></div>' : '') + '</div>';
      return head + bar + '<div class="ov-wrap"><table class="ov-table"><caption class="sr">캐릭터별 진행</caption><thead><tr><th scope="col">캐릭터</th><th scope="col">사람 할 일</th><th scope="col">지금</th><th scope="col">진행</th><th scope="col">마지막 변화</th><th scope="col"><span class="sr">동작</span></th></tr></thead><tbody>' + rows.map(rowHTML).join('') + '</tbody></table></div>';
    }
    function rowHTML(s, i) {
      const c = s.c;
      const name = displayName(c.name, c.id);
      const p = c.persona || {};
      const st = statusDot(s);
      const badges = (s.fail ? '<span class="fl-pill fail"><span class="d"></span>멈춘 단계 ' + s.fail + '</span>' : '') + (s.review ? '<span class="fl-pill wait"><span class="d"></span>검토 ' + s.review + '건</span>' : '') + (s.paid ? '<span class="fl-pill wait"><span class="d"></span>유료 확인 ' + s.paid + '건</span>' : '') || '<span class="muted">없음</span>';
      const gateTask = state.ov.gate ? s.tasks.find((x) => x.kind === 'wait' && x.gate === state.ov.gate) : null;
      const top = gateTask || s.top;
      const now = top ? E(top.title) + (top.age ? '<span class="age"> · ' + E(top.age) + '</span>' : '') : s.complete ? '모든 단계를 마쳤어요' : s.running ? '진행 중이에요' : s.fresh ? '아직 실행하지 않았어요' : '멈춰 있어요 · 이어서 실행할 수 있어요';
      const pct = Math.round(s.done / s.total * 100);
      const segs = s.lanes.map((l) => '<span class="seg ' + l.kind + '" title="' + E(l.label + ' ' + l.done + '/' + l.total) + '"></span>').join('');
      const href = '#c/' + encodeURIComponent(c.id);
      const act = top && top.kind === 'wait'
        ? '<button type="button" class="btn' + (i === 0 && s.rank <= 1 ? ' pri' : '') + '" data-act="ov-review" data-id="' + E(c.id) + '" data-gate="' + E(top.gate) + '" data-stage="' + E(top.stage || '') + '">검토하기</button>'
        : '<a class="btn" href="' + E(href) + '">열기</a>';
      return '<tr class="' + st + '"><th scope="row"><a class="ov-name" href="' + E(href) + '"><span class="fd-av" aria-hidden="true">' + E(Array.from(name)[0] || '?') + '<span class="st ' + st + '"></span></span><span><b>' + E(name) + trackHTML(c) + '</b><small>' + E([p.job, p.age ? p.age + '세' : ''].filter(Boolean).join(' · ') || '아직 기획 전이에요') + '</small></span></a></th>' +
        '<td><div class="ov-badges">' + badges + '</div></td><td class="ov-now">' + now + '</td>' +
        '<td><div class="ov-prog"><span class="segs" role="img" aria-label="' + E('전체 ' + s.total + '단계 중 ' + s.done + '단계 완료, ' + pct + '%') + '">' + segs + '</span><span class="n">' + s.done + '/' + s.total + '단계</span></div></td>' +
        '<td class="ov-upd">' + (s.updated ? E(clock(new Date(s.updated).toISOString())) : '—') + '</td><td class="ov-act">' + act + '</td></tr>';
    }
    function emptyHTML() {
      return '<div class="fl-empty"><span class="ic">' + MARK + '</span><h2>아직 만든 캐릭터가 없어요</h2><p>브리프를 넣으면 기획부터 이미지, 영상, 학습 데이터까지 단계별로 만들어요. 중간중간 사람이 고르는 지점이 있어요.</p>' +
        '<div class="acts"><button type="button" class="btn pri" data-act="new">새 캐릭터 만들기</button><a href="d-ops.html?mode=demo#job/seoha-new/floor">시연 화면으로 둘러보기</a></div></div>';
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
      const tasks = buildTasks(state.graph, d, v, { now, gateViews: state.gateViews, jobActive: Boolean(d.job) || state.busy, goal: notStarted() ? '' : currentUntil() });
      state.notes = state.notes.filter((n) => now - n.at < 15 * 60000);
      let html = '<section class="fl-tasks" aria-label="지금 할 일" aria-live="polite"><h2>' + (complete() ? '결과' : '지금 할 일') + (tasks.length ? '<span class="num">' + tasks.length + '</span>' : '') + '</h2>';
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
          t.actions.map((a) => '<button type="button" class="btn' + (a.pri ? ' pri' : '') + '" data-act="' + a.act + '"' + (a.gate ? ' data-gate="' + E(a.gate) + '"' : '') + (a.stage ? ' data-stage="' + E(a.stage) + '"' : '') + (a.anchor ? ' data-anchor="' + E(a.anchor) + '"' : '') + (a.disabled ? ' disabled' : '') + '>' + E(a.label) + '</button>' + (a.why ? '<span class="hint">' + E(a.why) + '</span>' : '')).join('') + '</div>') + '</div>';
      });
      if (notesHTML) html += '<div class="fl-recent"><h3>방금 한 일</h3>' + notesHTML + '</div>';
      if (!tasks.length && !complete()) {
        html += d.job ? '<div class="fl-note">' + icon('ok') + '<div>지금은 기다리면 돼요. <span>사람이 할 일이 생기면 여기에 나타나요.</span></div></div>'
          : '<div class="fl-item"><span class="mk"></span><div class="tx"><div class="t1">진행 중인 작업이 없어요</div><div class="t2">멈춘 지점부터 이어서 돌릴 수 있어요.</div></div><div class="acts"><button type="button" class="btn pri" data-act="resume"' + (state.busy ? ' disabled' : '') + '>이어서 실행</button></div></div>';
      }
      return html + '</section>';
    }

    // ---- 그래프 ----
    function cardHTML(lane, v, laneKinds) {
      const area = AREA[lane.id] || lane.id;
      const ids = (lane.stages || []).map((s) => (typeof s === 'string' ? s : s.id)).filter((id) => state.graph.byStage.has(id));
      const lk = laneKinds[lane.id];
      const done = ids.filter((id) => v[id].kind === 'done' || v[id].kind === 'skip').length;
      const collapsed = lk === 'done' && !state.open.has(lane.id);
      const outish = lk === 'out' || lk === 'skip';
      const tag = lk === 'skip' ? '<span class="fl-tag">건너뜀</span>' : lk === 'out' ? '<span class="fl-tag">범위 밖</span>' : '';
      let html = '<div class="fl-card' + (collapsed ? ' col' : '') + (outish ? ' out' : '') + '" data-lane="' + E(lane.id) + '" style="grid-area:' + E(area) + '">' +
        '<button type="button" class="fl-ch" data-act="toggle" data-lane="' + E(lane.id) + '" aria-expanded="' + (!collapsed) + '"' + (lk === 'done' ? '' : ' aria-disabled="true"') + '><span class="ld ' + (outish ? 'todo' : lk) + '"></span><span class="ln">' + E(lane.label) + '</span>' + tag +
        '<span class="cnt">' + (outish ? '' : (lk === 'done' ? icon('check') : '') + done + '/' + ids.length + (lk === 'done' ? icon(collapsed ? 'down' : 'up') : '')) + '</span></button>';
      if (!collapsed) {
        ids.forEach((id) => {
          const def = state.graph.byStage.get(id);
          const x = v[id];
          const paid = (state.graph.paid.get(id) || []).length;
          const marks = (def.gate ? icon('user', '사람 검토 있음') : '') + (paid && (x.kind === 'todo' || x.kind === 'confirm') ? icon('coins', '유료 단계') : '');
          const sub = x.sub ? '<span class="sb">' + (x.retry ? icon('retry') + ' ' : '') + E(x.sub) + '</span>' : '';
          const glyph = x.kind === 'done' ? icon('check') : x.kind === 'fail' ? icon('x') : x.kind === 'confirm' ? icon('coins') : x.kind === 'skip' ? icon('minus') : '';
          html += '<button type="button" class="fl-row ' + x.kind + '" data-act="select" data-stage="' + E(id) + '" aria-pressed="' + (state.sel === id) + '" aria-label="' + E(def.name + ', ' + KIND_LABEL[x.kind] + (x.sub ? ', ' + x.sub : '') + (def.gate ? ', 사람 검토 있음' : '') + (paid ? ', 유료 단계' : '')) + '">' +
            '<span class="si ' + x.kind + '">' + glyph + '</span><span class="nw"><span class="nm">' + E(def.name) + marks + '</span>' + sub + gateSub(def) + '</span></button>';
        });
      }
      return html + '</div>';
    }
    // 할 일 목록은 관문 이름(예: 얼굴 고르기)을 쓰고 그래프는 단계 이름(레퍼런스 선별)을 쓴다. 둘을 잇는다(D-0129).
    function gateSub(def) {
      const hint = state.graph.origin === 'SOURCE' ? TWIN_HINT[def.id] : '';
      if (hint) return '<span class="gt">' + E(hint) + '</span>';
      if (!def.gate) return '';
      const g = state.graph.byGate.get(def.gate);
      // 검토 이름의 첫 낱말이 단계 이름에 이미 있으면(소개 영상 ↔ 소개 영상 고르기) 덧붙이지 않는다.
      const head = g && g.title ? text(g.title).split(/[\s·]/)[0] : '';
      return head && text(def.name).indexOf(head) < 0 ? '<span class="gt">검토: ' + E(g.title) + '</span>' : '';
    }
    function renderGraph(v, scope) {
      if (!state.detail) { region.graph.hidden = true; return; }
      region.graph.hidden = false;
      const cls = (state.graph.layout || layoutOf(state.graph)).cls;
      region.grid.className = 'fl-grid' + (cls ? ' ' + cls : '');
      const laneKinds = {};
      state.graph.lanes.forEach((lane) => { laneKinds[lane.id] = laneKind((lane.stages || []).map((s) => (typeof s === 'string' ? s : s.id)), v); });
      region.grid.innerHTML = state.graph.lanes.map((lane) => cardHTML(lane, v, laneKinds)).join('');
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
        '<span class="pct" role="status">' + (zoomed() ? pct + '%' : '맞춤') + '</span>' +
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
      const cell = (state.graph.layout || layoutOf(state.graph)).cell;
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
      const items = hist.slice().reverse().map((a) => {
        const took = parseTime(a.startedAt) != null && parseTime(a.endedAt) != null ? span(parseTime(a.endedAt) - parseTime(a.startedAt)) : '';
        const result = a.result === 'CHECK_FAILED' ? '실패' : a.result === 'AWAITING_HUMAN' ? '검토로 넘김' : a.result === 'APPROVED' ? '완료' : a.result === 'RESTARTED' ? '다시 시작됨' : a.result === 'SKIPPED' ? '건너뜀' : a.result ? a.result : '진행 중';
        const decision = a.decision === 'APPROVED' ? ' → 통과' : a.decision === 'REJECTED' ? ' → 다시 만들기' : '';
        const tone = a.result === 'CHECK_FAILED' ? 'bad' : !a.result ? 'run' : a.decision === 'APPROVED' || a.result === 'APPROVED' ? 'ok' : a.result === 'AWAITING_HUMAN' && !a.decision ? 'wait' : '';
        return '<li class="' + tone + '"><b>' + E(a.attempt || '?') + '회차</b> · ' + E(result + decision) + '<br>' + E(clock(a.startedAt)) + (took ? ' · ' + E(took) : '') + (a.rev ? ' · ' + E(revLabel(a.rev)) : '') + (a.error ? '<span class="err">' + E(failReason(a.error).summary) + '</span>' : '') + '</li>';
      });
      return '<section class="ins-sec"><h3>회차 이력</h3><ul class="fl-hist">' + items.join('') + '</ul></section>';
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
      prop('상태', E(x.sub || KIND_LABEL[x.kind]));
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
      if (x.kind === 'wait') acts.push('<button type="button" class="btn pri block" data-act="review" data-gate="' + E(def.gate) + '" data-stage="' + E(id) + '">검토하기</button>');
      if (x.kind === 'confirm') acts.push('<button type="button" class="btn pri block" data-act="confirm" data-stage="' + E(id) + '"' + (busy ? ' disabled' : '') + '>비용 확인</button>');
      if (x.kind === 'fail') acts.push('<button type="button" class="btn pri block" data-act="retry" data-stage="' + E(id) + '"' + (busy ? ' disabled' : '') + '>다시 실행</button>');
      if (gate && upper(gate.status) === 'APPROVED') acts.push('<button type="button" class="btn block" data-act="review" data-gate="' + E(def.gate) + '" data-stage="' + E(id) + '" data-readonly="1">결정 기록 보기</button>');
      if (x.kind === 'todo' && def.implemented && !notStarted()) acts.push('<button type="button" class="btn block" data-act="run-stage" data-stage="' + E(id) + '"' + (busy ? ' disabled' : '') + '>이 단계까지 실행</button>');
      const pill = '<span class="fl-pill ' + (x.kind === 'retry' ? 'run' : x.kind === 'done' ? 'ok' : ['todo', 'out', 'skip'].includes(x.kind) ? 'muted' : x.kind) + '"><span class="d"></span>' + E(KIND_LABEL[x.kind]) + '</span>';
      return '<div class="ins-head"><span class="ins-kicker">' + E((lane ? lane.label + ' 팀 · ' : '') + def.id) + '</span><div class="ins-title"><h2>' + E(def.name) + '</h2>' + pill + '</div>' + (acts.length ? '<div class="acts" style="flex-direction:column;align-items:stretch">' + acts.join('') + '</div>' : '') + '</div>' +
        '<section class="ins-sec"><h3>속성</h3><dl class="ins-props">' + props.join('') + '</dl></section>' +
        (thumbs.length ? '<section class="ins-sec"><h3>산출물 미리보기</h3><div class="fl-thumbs">' + thumbs.map((f) => '<img alt="' + E(f.name) + '" src="' + E(R.safeHref(f.url)) + '" loading="lazy">').join('') + '</div></section>' : '') +
        historyHTML(id);
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
      const rt = route();
      state.overview = rt.overview && Boolean(state.graph);
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
        region.head.innerHTML = state.form.open ? formHTML() : overviewHTML(rt.filter);
        region.graph.hidden = true;
        region.panel.hidden = true;
        if (region.body) region.body.classList.add('no-panel');
        renderSheet();
        return;
      }
      const scope = setupScope();
      const v = state.detail ? views(scope) : {};
      if (state.detail && !state.sel) {
        const tasks = buildTasks(state.graph, state.detail, v, {});
        const running = Object.keys(v).find((id) => v[id].kind === 'run' || v[id].kind === 'retry');
        const next = state.graph.stages.find((s) => !['done', 'skip', 'out'].includes(v[s.id].kind));
        state.sel = (tasks[0] && tasks[0].stage) || running || (next && next.id) || 's11';
        loadGateViews();
      }
      renderTop(v);
      renderBanner();
      if (state.form.open) region.head.innerHTML = formHTML();
      else if (state.projects && !characters().length) region.head.innerHTML = emptyHTML();
      else if (!state.detail) region.head.innerHTML = '';
      else region.head.innerHTML = titleHTML() + (notStarted() ? setupHTML() : tasksHTML(v));
      renderGraph(v, scope);
      region.panel.hidden = !state.detail;
      if (region.body) region.body.classList.toggle('no-panel', !state.detail);
      if (state.detail) region.panel.innerHTML = '<div class="fl-panel">' + panelHTML(v) + '</div>';
      renderSheet();
    }

    // ---- 동작 ----
    async function run(payload, okText) {
      state.busy = true;
      state.feedback = null;
      render();
      try {
        await request('POST', '/api/jobs', payload);
        state.feedback = okText ? { tone: 'ok', text: okText } : null;
      } catch (error) {
        state.feedback = { tone: 'bad', text: error.message };
        if (error.network) state.conn = 'offline';
      }
      state.busy = false;
      await refresh(false);
    }
    async function create(form) {
      state.form.slug = form.querySelector('[data-slug]').value;
      state.form.brief = form.querySelector('[data-brief]').value;
      let payload;
      try { payload = R.createCharacterRequest(state.form.slug, state.form.brief); } catch (error) { state.form.error = error.message; render(); return; }
      state.busy = true;
      state.form.error = '';
      render();
      try {
        const data = await request('POST', '/api/runtime/characters', payload);
        state.form = { open: false, slug: '', brief: '', error: '' };
        state.feedback = { tone: 'ok', text: '캐릭터를 등록했어요. 어디까지 돌릴지 고르고 실행을 시작하세요.' };
        global.location.hash = '#c/' + encodeURIComponent(data.characterId);
      } catch (error) {
        state.form.error = error.message;
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
      const el = event.target.closest('[data-act]');
      if (!el || el.disabled || (el.getAttribute('aria-disabled') === 'true' && el.dataset.act === 'toggle')) return;
      const act = el.dataset.act;
      const id = state.detail && state.detail.id;
      if (act === 'select') { state.sel = el.dataset.stage; const lane = laneMap(state.graph).get(state.sel); if (lane) state.open.add(lane); loadGateViews(); render(); }
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
      else if (act === 'zoom-in') zoomStep(1);
      else if (act === 'zoom-out') zoomStep(-1);
      else if (act === 'zoom-fit') zoomFit();
      else if (act === 'focus') toggleFocus();
      else if (act === 'overview') { state.batch = null; state.form.open = false; global.location.hash = '#all'; }
      else if (act === 'ov-clear') { state.ov = { q: '', gate: '' }; if (route().filter !== 'all') global.location.hash = '#all'; else render(); }
      else if (act === 'ov-review') { state.batch = el.dataset.gate; state.pendingReview = { id: el.dataset.id, gate: el.dataset.gate, stage: el.dataset.stage }; global.location.hash = '#c/' + encodeURIComponent(el.dataset.id); }
      else if (act === 'next-batch') { const nb = nextInBatch(); if (nb) { const t = nb.next.tasks.find((x) => x.kind === 'wait' && x.gate === state.batch) || {}; state.pendingReview = { id: nb.next.c.id, gate: state.batch, stage: t.stage }; closeSheet(false); global.location.hash = '#c/' + encodeURIComponent(nb.next.c.id); } }
      else if (act === 'retry') run(R.runRequest(id, currentUntil() || orchestrator().resumeUntil || el.dataset.stage, []), '다시 실행을 요청했어요. 통과하면 목표까지 이어서 진행해요.');
      else if (act === 'run-stage') run(R.runRequest(id, el.dataset.stage, []), '이 단계까지 실행을 요청했어요.');
      else if (act === 'start') run(R.runRequest(id, state.target || defaultTarget(), []), '실행을 시작했어요. 진행 상황은 서버 기록을 따라요.');
      else if (act === 'resume') run(R.runRequest(id, currentUntil() || orchestrator().resumeUntil || 'sx', []), '이어서 실행을 요청했어요.');
      else if (act === 'new') { state.form.open = true; render(); const f = doc.querySelector('[data-slug]'); if (f) f.focus(); }
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
      return { id: o.s.c.id, gate: o.t.gate, stage: o.t.stage, label: '다음 검토 · ' + displayName(o.s.c.name, o.s.c.id) + ' · ' + o.t.title };
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
      if (el.matches('[data-pick]')) {
        if (el.value === '__new') { state.form.open = true; render(); return; }
        if (el.value === '__all') { global.location.hash = '#all'; return; }
        state.form.open = false;
        global.location.hash = '#c/' + encodeURIComponent(el.value);
      } else if (el.matches('[data-target]')) { state.target = el.value; render(); }
      else if (el.matches('[data-ov-gate]')) { state.ov.gate = el.value; render(); }
    }
    function onSubmit(event) {
      if (event.target.matches('[data-form]')) { event.preventDefault(); create(event.target); }
    }
    function onInput(event) { if (event.target.matches && event.target.matches('[data-ov-q]')) { state.ov.q = event.target.value; render(); } }
    function onKey(event) {
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
      if (nb) { note.act = 'next-batch'; note.label = '다음 건 검토 · ' + displayName(nb.next.c.name, nb.next.c.id) + ' (' + nb.left + '건 남음)'; }
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
        clearInterval(tick);
        clearInterval(poll);
        clearTimeout(refreshTimer);
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

  const pure = { since, span, clock, predecessors, descendants, ancestors, reducedEdges, crossLaneEdges, viewsFor, laneKind, edgeClass, buildTasks, diffNotes, failReason, targetLabel, recommendation, reworkLine, layoutOf, trackLabel, MARK, mount };
  if (typeof module !== 'undefined' && module.exports) module.exports = pure;
  if (global) global.FactoryFlow = pure;
})(typeof window !== 'undefined' ? window : null);
