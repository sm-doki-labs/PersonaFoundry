(function (global) {
  'use strict';

  // 대화해 보기 화면(계획 2차 묶음 H, 3차 묶음 M). 완성된 캐릭터와 팀이 직접 말을 주고받는다.
  // 서버는 약속 1 대화 API만 쓴다: GET /api/characters/{cid}/chat/meta, POST /api/characters/{cid}/chat.
  // 대화 기록은 서버에 남기지 않고 이 탭의 메모리(sessionStorage)에만 둔다.
  // createChat은 DOM 없이 돌아서 시험이 가짜 fetch로 보내기·재생 순서·준비 안 됨·다시 시도를 확인한다. mount는 그 위에 화면을 그린다.

  const MOTIF_NOTE = 'AI 생성 · 본인과 무관한 기술 시연';
  const STORE_PREFIX = 'cf-chat:';
  const SLOW_MS = 8000;
  const VIA_LABEL = { studio: 'AI Studio', vertex: 'Vertex AI' };

  function text(value) { return value == null ? '' : String(value); }
  function escapeHTML(value) {
    return text(value).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  const E = escapeHTML;

  function apiPath(apiBase, path) {
    const base = text(apiBase).trim().replace(/\/+$/, '');
    const suffix = '/' + text(path).trim().replace(/^\/+/, '');
    return base + suffix;
  }
  function chatPath(cid, tail) { return '/api/characters/' + encodeURIComponent(text(cid)) + '/chat' + (tail || ''); }

  // 주소 #c/<characterId>에서 캐릭터를 꺼낸다.
  function routeId(hash) {
    const m = /^#c\/([^/?#]+)/.exec(text(hash));
    if (!m) return null;
    try { return decodeURIComponent(m[1]); } catch (error) { return m[1]; }
  }
  // 걸린 시간: 1분 아래는 소수 한 자리 초, 그 위는 분·초.
  function seconds(ms) {
    const n = Number(ms);
    if (ms == null || ms === '' || !Number.isFinite(n) || n < 0) return '';
    if (n < 60000) return (Math.round(n / 100) / 10).toFixed(1) + '초';
    const s = Math.round(n / 1000);
    return Math.floor(s / 60) + '분 ' + (s % 60) + '초';
  }
  // 산출물 revision(pv3, cs1)은 화면에 "3판"으로 쓰고 원래 이름은 툴팁에 둔다.
  function revLabel(rev) {
    const m = /(\d+)$/.exec(text(rev));
    return m ? Number(m[1]) + '판' : '';
  }
  function viaLabel(via) { return VIA_LABEL[via] || text(via); }
  // 메모 걸러내기(reply_guard)가 버린 답: 서버가 목록·숫자·참거짓 어느 것으로 줘도 개수로 센다.
  function rejectedCount(value) {
    if (Array.isArray(value)) return value.length;
    if (typeof value === 'number' && Number.isFinite(value)) return Math.max(0, Math.round(value));
    return value ? 1 : 0;
  }
  function rejectedReasons(value) {
    if (!Array.isArray(value)) return [];
    return value.map((x) => text(x && typeof x === 'object' ? x.reason : x)).filter(Boolean);
  }
  function isMotif(origin) { return origin === 'SOURCE' || origin === 'MOTIF'; }

  // 이름 규칙(진행 화면·원문 화면과 같다): 서버 표시 이름 → 없으면 '이름 미정 · slug (11/9)'. 서버의 자리 채움 이름 '캐릭터'와 ID는 이름으로 쓰지 않는다.
  function displayName(name, id) {
    const n = text(name).trim();
    if (n && n !== text(id) && n !== '캐릭터') return n;
    const m = /^cf-(\d{4})(\d{2})(\d{2})-(.+)$/.exec(text(id));
    return m ? '이름 미정 · ' + m[4] + ' (' + Number(m[2]) + '/' + Number(m[3]) + ')' : text(id);
  }
  // 만든 날짜 '11/10'. 서버 값이 없으면 ID 앞의 날짜를 쓴다.
  function createdLabel(iso, id) {
    const d = iso ? new Date(iso) : null;
    if (d && !isNaN(d.getTime())) return (d.getMonth() + 1) + '/' + d.getDate();
    const m = /^cf-\d{4}(\d{2})(\d{2})-/.exec(text(id));
    return m ? Number(m[1]) + '/' + Number(m[2]) : '';
  }
  function clockLabel(iso) {
    const d = iso ? new Date(iso) : null;
    return d && !isNaN(d.getTime()) ? String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0') : '';
  }
  // 대화 화면 왼쪽 목록: GET /api/chat/characters(약속 3)를 그대로 쓴다. 그 API가 없는 서버면 /api/projects에서
  // 대화 가능(chatReady) 표시가 있는 캐릭터만, 표시가 아예 없으면 전부를 같은 모양으로 바꿔 쓴다. 보관한 캐릭터는 뺀다.
  function chatList(data, fromProjects) {
    if (!fromProjects) return (Array.isArray(data) ? data : Array.isArray(data && data.characters) ? data.characters : []).filter((c) => c && c.characterId);
    const list = (data && Array.isArray(data.characters) ? data.characters : []).filter((c) => c && c.id && !c.archived);
    const known = list.some((c) => typeof c.chatReady === 'boolean');
    return list.filter((c) => !known || c.chatReady === true).map((c) => ({ characterId: c.id, displayName: displayName(c.displayName || c.name, c.id), createdAt: c.createdAt || null, origin: c.origin || null }));
  }
  // 상황 목록 하나로 합치기: 이 캐릭터 전용 상황을 먼저 두고, 기본 상황 가운데 전용 상황과 제목이 같은 것은 뺀다.
  // 기본 상황 표시는 서버가 generic을 주면 그 값을, 없으면 기본 상황 파일의 ID로 가린다.
  const GENERIC_IDS = ['daily', 'tease', 'worry', 'unknown', 'private'];
  function isGeneric(sc) {
    if (!sc) return false;
    if (typeof sc.generic === 'boolean') return sc.generic;
    if (sc.source === 'generic' || sc.kind === 'generic') return true;
    return GENERIC_IDS.indexOf(text(sc.id)) >= 0;
  }
  function groupScenarios(list) {
    const all = Array.isArray(list) ? list.filter(Boolean) : [];
    const key = (s) => text(s && s.title).replace(/\s+/g, '');
    const mine = all.filter((s) => !isGeneric(s));
    const titles = new Set(mine.map(key));
    const generic = all.filter(isGeneric);
    return { mine, basic: generic.filter((s) => !titles.has(key(s))), dropped: generic.filter((s) => titles.has(key(s))).map((s) => text(s.id)) };
  }

  function createChat(opts) {
    const o = opts || {};
    const fetchFn = o.fetch || (global.fetch ? global.fetch.bind(global) : null);
    const apiBase = o.apiBase || '';
    const cid = text(o.characterId);
    const now = o.now || (() => Date.now());
    const gap = o.gap == null ? 500 : o.gap;
    const pause = o.pause || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
    const storage = o.storage || null;
    const AbortCtl = o.AbortController === undefined ? global.AbortController : o.AbortController;
    const listeners = new Set();
    let seq = 0;
    let playSeq = 0;
    let destroyed = false;

    // phase: loading · ready · not-ready(준비 안 됨) · missing(없는 캐릭터) · error(불러오기 실패)
    const state = { phase: 'loading', meta: null, reason: '', error: '', messages: [], pending: null, play: null, announce: null };

    function emit() { if (!destroyed) listeners.forEach((fn) => { try { fn(state); } catch (error) { /* 화면 오류가 대화를 멈추지 않게 한다 */ } }); }
    function storeKey() { return STORE_PREFIX + cid; }
    function save() {
      if (!storage) return;
      try {
        const keep = state.messages.map((m) => ({ role: m.role, content: m.content, ms: m.ms, rejected: m.rejected, reasons: m.reasons, model: m.model }));
        if (keep.length) storage.setItem(storeKey(), JSON.stringify({ v: 1, messages: keep }));
        else storage.removeItem(storeKey());
      } catch (error) { /* 저장 공간이 없어도 대화는 이어 간다 */ }
    }
    function restore() {
      if (!storage) return;
      try {
        const raw = storage.getItem(storeKey());
        const data = raw ? JSON.parse(raw) : null;
        if (!data || !Array.isArray(data.messages)) return;
        state.messages = data.messages.filter((m) => m && (m.role === 'user' || m.role === 'assistant')).map((m) => Object.assign({}, m, { id: 'm' + (++seq) }));
        // 답을 못 받은 채 끝난 마지막 말은 다시 받을 수 있게 실패로 표시한다.
        const tail = state.messages[state.messages.length - 1];
        if (tail && tail.role === 'user') { tail.error = '답을 받기 전에 화면을 닫았어요.'; tail.stopped = true; }
      } catch (error) { state.messages = []; }
    }

    async function call(method, path, body, signal) {
      if (!fetchFn) { const e = new Error('이 브라우저에서는 서버에 연결할 수 없어요.'); e.network = true; throw e; }
      let response;
      try {
        response = await fetchFn(apiPath(apiBase, path), {
          method, credentials: 'same-origin', cache: 'no-store', signal,
          headers: body ? { 'Content-Type': 'application/json' } : undefined,
          body: body ? JSON.stringify(body) : undefined
        });
      } catch (error) {
        if (error && error.name === 'AbortError') { const e = new Error('답 받기를 멈췄어요.'); e.aborted = true; throw e; }
        const e = new Error('서버에 연결하지 못했어요. 연결을 확인하고 다시 시도해 주세요.');
        e.network = true;
        throw e;
      }
      let data = null;
      try { data = await response.json(); } catch (error) { data = null; }
      if (!response.ok) {
        const detail = data && typeof data.detail === 'string' ? data.detail.trim() : '';
        const e = new Error(detail || '답을 받지 못했어요. 잠시 뒤 다시 시도해 주세요.');
        e.status = response.status;
        e.detail = detail;
        throw e;
      }
      return data || {};
    }

    async function load() {
      state.phase = 'loading'; state.error = ''; state.reason = '';
      emit();
      try {
        const meta = await call('GET', chatPath(cid, '/meta'));
        if (destroyed) return state;
        state.meta = meta;
        if (meta.ready) { state.phase = 'ready'; if (!state.messages.length) restore(); }
        else { state.phase = 'not-ready'; state.reason = text(meta.reason).trim() || '아직 대화할 준비가 되지 않았어요.'; }
      } catch (error) {
        if (error.status === 404) { state.phase = 'missing'; state.reason = '지웠거나 주소가 바뀌었을 수 있어요. 목록에서 다시 골라 주세요.'; }
        else { state.phase = 'error'; state.error = error.message; }
      }
      emit();
      return state;
    }

    function last() { return state.messages[state.messages.length - 1] || null; }
    function failedLast() { const m = last(); return m && m.role === 'user' && m.error ? m : null; }
    function history() { return state.messages.map((m) => ({ role: m.role, content: m.content })); }
    function scenarios() { return (state.meta && Array.isArray(state.meta.scenarios)) ? state.meta.scenarios : []; }
    function canSend() { return state.phase === 'ready' && !state.pending && !(state.play && state.play.status === 'running'); }

    // 마지막 사람 말에 대한 답을 한 번 받는다. 성공하면 true.
    async function reply() {
      const user = last();
      const ctl = AbortCtl ? new AbortCtl() : null;
      const startedAt = now();
      state.pending = { startedAt, abort: () => { if (ctl) ctl.abort(); } };
      emit();
      let data;
      try {
        data = await call('POST', chatPath(cid), { messages: history() }, ctl ? ctl.signal : undefined);
      } catch (error) {
        state.pending = null;
        if (destroyed) return false;
        if (error.status === 409) {
          // 약속 1: 409는 프롬프트가 없다는 뜻이다. 대화를 멈추고 준비 안 됨 화면으로 바꾼다.
          state.phase = 'not-ready';
          state.reason = error.detail || '대화할 프롬프트가 아직 없어요.';
          if (state.play) state.play.status = 'stopped';
        } else if (user) {
          user.error = error.message;
          user.stopped = !!error.aborted;
        }
        emit();
        return false;
      }
      state.pending = null;
      if (destroyed) return false;
      const ms = data.ms != null && Number.isFinite(Number(data.ms)) ? Number(data.ms) : now() - startedAt;
      const msg = { id: 'm' + (++seq), role: 'assistant', content: text(data.reply), ms, rejected: rejectedCount(data.rejected), reasons: rejectedReasons(data.rejected), model: text(data.model) };
      state.messages.push(msg);
      state.announce = { id: msg.id, text: msg.content };
      save();
      emit();
      return true;
    }

    function pushUser(content) {
      const msg = { id: 'm' + (++seq), role: 'user', content };
      state.messages.push(msg);
      return msg;
    }

    // 직접 보내기. 마지막 말이 실패해 있으면 그 말을 새 말로 바꾼다(사람 말이 두 번 연달아 가지 않게).
    async function send(raw) {
      const content = text(raw).trim();
      if (!content || !canSend()) return false;
      if (failedLast()) state.messages.pop();
      if (state.play) state.play = null; // 직접 말을 걸면 재생은 끝나고 자유 대화가 된다
      pushUser(content);
      save();
      return reply();
    }

    // 상황 재생: 대화를 새로 시작하고 준비된 말을 하나씩 보낸다. 답이 오면 다음 말을 보낸다.
    async function play(scenarioId) {
      const sc = scenarios().find((s) => s.id === scenarioId);
      const turns = sc && Array.isArray(sc.turns) ? sc.turns.map(text).filter((t) => t.trim()) : [];
      if (state.phase !== 'ready' || !turns.length || state.pending) return false;
      state.messages = [];
      state.play = { scenarioId: sc.id, title: text(sc.title) || '상황', turns, index: 0, status: 'running', token: ++playSeq };
      save();
      emit();
      return loop(state.play.token);
    }

    async function loop(token) {
      const live = () => state.play && state.play.token === token && state.play.status === 'running' && !destroyed;
      while (live() && state.play.index < state.play.turns.length) {
        if (last() && last().role === 'assistant' && gap) {
          await pause(gap);
          if (!live()) return false;
        }
        pushUser(state.play.turns[state.play.index]);
        save();
        const ok = await reply();
        if (!state.play || state.play.token !== token) return false;
        if (!ok) {
          if (state.play.status === 'running') state.play.status = failedLast() && failedLast().stopped ? 'stopped' : 'error';
          emit();
          return false;
        }
        state.play.index++;
      }
      if (live()) { state.play.status = 'done'; emit(); return true; }
      return false;
    }

    // 실패한 말을 다시 보낸다. 재생 중 실패였으면 그 말부터 재생을 이어 간다.
    async function retry() {
      const failed = failedLast();
      if (!failed || state.pending || state.phase !== 'ready') return false;
      failed.error = ''; failed.stopped = false;
      const p = state.play;
      if (p && (p.status === 'error' || p.status === 'stopped')) p.status = 'running';
      const ok = await reply();
      if (!ok) {
        if (p && state.play === p && p.status === 'running') p.status = failedLast() && failedLast().stopped ? 'stopped' : 'error';
        emit();
        return false;
      }
      if (p && state.play === p && p.status === 'running') { p.index++; return loop(p.token); }
      return true;
    }

    // 멈춘 재생을 이어 간다. 답을 받던 말이 있으면 그 말부터 다시 보낸다.
    async function resume() {
      const p = state.play;
      if (!p || p.status !== 'stopped' || state.pending || state.phase !== 'ready') return false;
      if (failedLast()) return retry();
      p.status = 'running';
      emit();
      return loop(p.token);
    }

    // 재생과 지금 받는 답을 멈춘다. 이미 받은 답은 남는다.
    function stop() {
      let changed = false;
      if (state.play && state.play.status === 'running') { state.play.status = 'stopped'; changed = true; }
      if (state.pending) { state.pending.abort(); changed = true; }
      if (changed) emit();
      return changed;
    }

    function reset() {
      if (state.pending) state.pending.abort();
      state.pending = null;
      state.play = null;
      state.messages = [];
      state.announce = null;
      save();
      emit();
    }

    function subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); }
    function destroy() { if (state.pending) state.pending.abort(); destroyed = true; listeners.clear(); }

    return { state, load, send, play, stop, resume, retry, reset, subscribe, destroy, canSend, history, scenarios, characterId: cid };
  }

  // ---------------- 화면 ----------------

  const ICON = {
    send: '<path d="M5 12h14"/><polyline points="13 6 19 12 13 18"/>',
    stop: '<rect x="7" y="7" width="10" height="10" rx="1.5"/>',
    play: '<polygon points="8 5 19 12 8 19 8 5"/>',
    refresh: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><polyline points="3 3 3 8 8 8"/>',
    back: '<polyline points="15 18 9 12 15 6"/>',
    grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    monitor: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    check: '<polyline points="20 6 9 17 4 12"/>',
    alert: '<circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="12.5"/><line x1="12" y1="16" x2="12" y2="16"/>'
  };
  const MARK = '<svg class="fd-mark" viewBox="0 0 24 24" aria-hidden="true"><rect width="24" height="24" rx="6" fill="var(--fd-accent)"/><path d="M8.5 17V7h7.5M8.5 12h5" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="16.4" cy="16.4" r="1.7" fill="#fff"/></svg>';
  const THEMES = [['system', 'monitor', '시스템 설정 따르기'], ['light', 'sun', '밝은 화면'], ['dark', 'moon', '어두운 화면']];
  function icon(name) { return '<svg class="i" viewBox="0 0 24 24" aria-hidden="true">' + ICON[name] + '</svg>'; }
  function initial(name) { return Array.from(text(name).trim())[0] || '?'; }
  function factoryHref(cid) { return cid ? 'factory.html#c/' + encodeURIComponent(cid) : 'factory.html#all'; }
  function clip(s, n) { const a = Array.from(text(s)); return a.length > n ? a.slice(0, n).join('') + '…' : a.join(''); }

  function mount(options) {
    const o = options || {};
    const doc = (o.root && o.root.nodeType === 9) ? o.root : (o.root && o.root.ownerDocument) || global.document;
    const $ = (sel) => doc.querySelector(sel);
    const R = {
      side: $('[data-side]'), head: $('[data-top]'), call: $('[data-call]'), list: $('[data-list]'), state: $('[data-state]'),
      form: $('[data-composer]'), input: $('[data-input]'), sendBtn: $('[data-send]'), hint: $('[data-composer-hint]'),
      panel: $('[data-panel]'), live: $('[data-live]'), playbar: $('[data-playbar]'), stage: $('[data-stage]')
    };
    const store = (() => { try { return global.localStorage; } catch (error) { return null; } })();
    const session = o.storage !== undefined ? o.storage : (() => { try { return global.sessionStorage; } catch (error) { return null; } })();
    const media = global.matchMedia ? global.matchMedia('(prefers-color-scheme: dark)') : null;
    const ui = { theme: (store && ['light', 'dark'].includes(store.getItem('fd-theme'))) ? store.getItem('fd-theme') : 'system', chars: null, open: new Set(), lastSeen: '', stick: true, announced: '' };
    const narrow = global.matchMedia ? global.matchMedia('(max-width: 1099px)') : null;
    let chat = null;
    let unsub = null;
    let tick = null;

    function applyTheme() {
      const html = doc.documentElement;
      if (ui.theme === 'system') html.removeAttribute('data-fd-theme');
      else html.setAttribute('data-fd-theme', ui.theme);
    }
    function setTheme(t) {
      ui.theme = t;
      if (store) { try { if (t === 'system') store.removeItem('fd-theme'); else store.setItem('fd-theme', t); } catch (error) { /* 저장 못 해도 이번 화면에는 적용한다 */ } }
      applyTheme(); renderSide(); renderHead();
    }

    async function loadCharacters() {
      const fetchFn = o.fetch || (global.fetch && global.fetch.bind(global));
      if (!fetchFn) return;
      const get = async (p) => { const res = await fetchFn(apiPath(o.apiBase, p), { credentials: 'same-origin', cache: 'no-store' }); return res.ok ? res.json() : Promise.reject(res.status); };
      try { ui.chars = chatList(await get('/api/chat/characters'), false); }
      catch (error) {
        try { ui.chars = chatList(await get('/api/projects'), true); } catch (e) { /* 목록은 보조 길잡이라 실패해도 대화는 된다 */ }
      }
      renderSide(); renderHead();
      if (chat) { renderCall(); renderList(); }
    }

    function meta() { return chat && chat.state.meta; }
    function nameOf() {
      if (!chat) return '';
      const m = meta() || {};
      const cid = chat.characterId;
      const listed = (ui.chars || []).find((c) => c.characterId === cid);
      const pick = [m.displayName, listed && listed.displayName, m.name].map((x) => text(x).trim()).find((x) => x && x !== cid && x !== '캐릭터');
      return pick || displayName('', cid);
    }

    // 왼쪽 사이드바: 진행 화면(factory.html)과 같은 모양. 대화 가능한 캐릭터만 이름과 만든 날짜로 보이고, 누르면 그 캐릭터와 대화한다.
    // 이름과 날짜가 같은 캐릭터가 둘 이상이면 시각까지 붙여 가린다. 돌아가기는 머리줄 위치 표시가 맡는다.
    function renderSide() {
      if (!R.side) return;
      const cid = chat ? chat.characterId : '';
      const list = ui.chars || [];
      const dateOf = (c) => createdLabel(c.createdAt, c.characterId);
      const twin = (c) => list.filter((x) => x.displayName === c.displayName && dateOf(x) === dateOf(c)).length > 1;
      const items = list.map((c) => {
        const name = displayName(c.displayName, c.characterId);
        const when = [dateOf(c), twin(c) ? clockLabel(c.createdAt) : ''].filter(Boolean).join(' ');
        return '<a class="fd-nav" href="chat.html#c/' + E(encodeURIComponent(c.characterId)) + '"' + (c.characterId === cid ? ' aria-current="page"' : '') + ' title="' + E(name + (when ? ' · ' + when + ' 만듦' : '')) + '">' +
          '<span class="fd-av" aria-hidden="true">' + E(initial(name)) + '</span><span class="lbl">' + E(name) + '</span>' + (when ? '<span class="num">' + E(when) + '</span>' : '') + '</a>';
      }).join('');
      const theme = THEMES.map((t) => '<button type="button" data-act="theme" data-theme="' + t[0] + '" aria-pressed="' + (ui.theme === t[0]) + '" aria-label="' + t[2] + '" title="' + t[2] + '">' + icon(t[1]) + '</button>').join('');
      R.side.innerHTML = '<div class="fd-brand">' + MARK + '<div class="fd-word"><b>Foundry</b><small>캐릭터 공장</small></div></div>' +
        '<nav aria-label="캐릭터 탐색"><a class="fd-nav" href="factory.html#all" title="전체 캐릭터">' + icon('grid') + '<span class="lbl">전체 캐릭터</span></a>' +
        '<h2>대화할 수 있는 캐릭터</h2>' + (items || '<p class="hint" style="padding:0 8px">' + (ui.chars ? '아직 없어요' : '불러오는 중이에요') + '</p>') + '</nav>' +
        '<div class="fd-side-foot"><a class="fd-help" href="help.html" target="_blank" rel="noopener" title="사용 안내" aria-label="사용 안내">?</a><div class="fd-theme" role="group" aria-label="화면 테마">' + theme + '</div><div class="fd-foot-links"><a href="help.html" target="_blank" rel="noopener">사용 안내</a></div></div>';
    }

    function renderHead() {
      if (!R.head) return;
      // 없는 캐릭터면 그 ID를 이름처럼 보이지 않는다.
      const cid = chat && chat.state.phase !== 'missing' ? chat.characterId : '';
      const i = Math.max(0, THEMES.findIndex((t) => t[0] === ui.theme));
      const cur = THEMES[i];
      const next = THEMES[(i + 1) % THEMES.length];
      const crumb = cid
        ? '<a class="up" href="factory.html#all">전체 캐릭터</a><span class="sep" aria-hidden="true">/</span><a class="up" href="' + E(factoryHref(cid)) + '">' + E(nameOf()) + '</a><span class="sep" aria-hidden="true">/</span><b aria-current="page">대화해 보기</b>'
        : '<a class="up" href="factory.html#all">전체 캐릭터</a><span class="sep" aria-hidden="true">/</span><b aria-current="page">대화해 보기</b>';
      R.head.innerHTML = '<nav class="fd-crumb" aria-label="위치">' + crumb + '</nav>' +
        '<a class="ch-head-help" href="help.html" target="_blank" rel="noopener" title="사용 안내" aria-label="사용 안내">?</a>' +
        '<button type="button" class="fd-head-theme" data-act="theme" data-theme="' + next[0] + '" aria-label="화면 테마: 지금 ' + cur[2] + '. 누르면 ' + next[2] + '" title="화면 테마: ' + cur[2] + '">' + icon(cur[1]) + '</button>';
    }

    // 통화 머리: 캐릭터 이름, 모티브 안내, 지금 상태, 새 대화·고칠 점 적기, 접힌 '설정 보기'(모델·온도·판).
    // 캐릭터를 고르지 않았거나 없는 캐릭터면 머리를 숨기고 상태 카드만 보인다.
    function renderCall() {
      if (!R.call) return;
      const s = chat ? chat.state : null;
      R.call.hidden = !s || s.phase === 'missing';
      if (R.call.hidden) { R.call.innerHTML = ''; return; }
      const m = meta() || {};
      const ready = !!(s && s.phase === 'ready');
      const speaking = !!(s && s.pending);
      let pill = '';
      if (s && s.phase === 'loading') pill = '<span class="fl-pill muted"><span class="d"></span>불러오는 중</span>';
      else if (speaking) pill = '<span class="fl-pill run"><span class="d"></span>답을 쓰는 중</span>';
      else if (ready && s.play && s.play.status === 'running') pill = '<span class="fl-pill run"><span class="d"></span>재생 중</span>';
      else if (ready) pill = '<span class="fl-pill ok"><span class="d"></span>대화 가능</span>';
      const model = m.model || {};
      const info = [];
      if (ready) {
        if (model.model) info.push('<span title="대화 모델">' + E(model.model) + (model.via ? ' · ' + E(viaLabel(model.via)) : '') + '</span>');
        if (m.temperature != null && m.temperature !== '') info.push('<span title="답의 다양성(온도)">온도 ' + E(m.temperature) + '</span>');
        if (revLabel(m.promptRev)) info.push('<span>프롬프트 ' + E(revLabel(m.promptRev)) + '</span>');
        if (revLabel(m.chapterRev)) info.push('<span>장면 ' + E(revLabel(m.chapterRev)) + '</span>');
      }
      const name = nameOf();
      const hasTalk = !!(s && (s.messages.length || s.pending || s.play));
      R.call.innerHTML = '<div class="ch-av' + (speaking ? ' is-speaking' : '') + '" aria-hidden="true">' + E(initial(name)) + '</div>' +
        '<div class="ch-who"><div class="ch-name"><h1 id="ch-title">' + E(name) + '</h1>' + pill + '</div>' +
        (isMotif(m.origin) ? '<p class="ch-note">' + E(MOTIF_NOTE) + '</p>' : '') +
        (info.length ? '<details class="ch-set" data-open-key="set"' + (ui.open.has('set') ? ' open' : '') + '><summary data-key="sum:set">설정 보기</summary><p class="ch-info" aria-label="대화 설정">' + info.join('<span class="dot" aria-hidden="true">·</span>') + '</p></details>' : '') + '</div>' +
        (ready ? '<div class="ch-acts"><a class="btn" href="' + E(factoryHref(chat.characterId)) + '" title="진행 화면에서 프롬프트에 고칠 점을 적어요">고칠 점 적기</a><button type="button" class="btn" data-act="reset" data-key="reset"' + (hasTalk ? '' : ' disabled') + '>' + icon('refresh') + '새 대화</button></div>' : '');
    }

    function playbarHTML(s) {
      const p = s.play;
      if (!p) return '';
      const n = p.turns.length;
      const done = Math.min(p.index, n);
      let line = '';
      let acts = '';
      // 재생 중 멈추기는 입력 칸과 오른쪽 패널에 있어 띠에는 두지 않는다.
      if (p.status === 'running') line = '<b>' + E(p.title) + '</b> 상황을 재생하고 있어요 · ' + Math.min(done + 1, n) + '/' + n;
      else if (p.status === 'stopped') { line = '<b>' + E(p.title) + '</b> 재생을 멈췄어요 · 말 ' + n + '개 중 ' + done + '개까지 했어요'; acts = (done < n ? '<button type="button" class="btn" data-act="resume" data-key="resume">' + icon('play') + '이어서 재생</button>' : ''); }
      else if (p.status === 'error') { line = '<b>' + E(p.title) + '</b> ' + (done + 1) + '번째 말에서 답을 받지 못해 멈췄어요'; }
      else if (p.status === 'done') { line = '<b>' + E(p.title) + '</b> 재생을 마쳤어요 · 이어서 직접 말을 걸 수 있어요'; }
      return '<div class="ch-playbar is-' + p.status + '"><span class="ch-prog" aria-hidden="true">' + p.turns.map((_, i) => '<i class="' + (i < done ? 'ok' : (i === done && p.status === 'running' ? 'now' : '')) + '"></i>').join('') + '</span><span class="tx">' + line + '</span>' + acts + '</div>';
    }

    function messageHTML(msg, s, isLast) {
      if (msg.role === 'user') {
        const failed = msg.error && isLast;
        // 멈춘 재생은 띠의 "이어서 재생"이 같은 일을 하므로 말 옆 단추는 두지 않는다.
        const inline = !(s.play && s.play.status === 'stopped');
        return '<li class="ch-msg me' + (failed ? ' is-failed' : '') + '" data-mid="' + E(msg.id) + '"><div class="col"><span class="sr">나: </span><div class="bub">' + E(msg.content) + '</div>' +
          // 직접 멈춘 말은 오류가 아니라서 회색 안내로, 실패만 빨간 경고로 보인다.
          (failed ? '<div class="ch-fail' + (msg.stopped ? ' is-stopped' : '') + '"' + (msg.stopped ? '' : ' role="alert"') + '>' + icon(msg.stopped ? 'stop' : 'alert') + '<span>' + E(msg.error) + '</span>' + (inline ? '<button type="button" class="btn" data-act="retry" data-key="retry"' + (s.pending ? ' disabled' : '') + '>' + icon('refresh') + (msg.stopped ? '답 받기' : '다시 시도') + '</button>' : '') + '</div>' : '') + '</div></li>';
      }
      const empty = !text(msg.content).trim();
      const bits = [];
      if (seconds(msg.ms)) bits.push('<span class="t" title="답이 오기까지 걸린 시간">' + E(seconds(msg.ms)) + '</span>');
      if (msg.rejected) bits.push('<span class="rj" title="' + E((msg.reasons || []).join(' / ') || '작성 메모가 섞인 답') + '">메모가 섞인 답 ' + msg.rejected + '개를 버리고 다시 받았어요</span>');
      return '<li class="ch-msg ai" data-mid="' + E(msg.id) + '"><span class="ch-av sm" aria-hidden="true">' + E(initial(nameOf())) + '</span><div class="col"><span class="sr">' + E(nameOf()) + ': </span>' +
        '<div class="bub' + (empty ? ' empty' : '') + '">' + (empty ? '빈 답이 왔어요.' : E(msg.content)) + '</div>' +
        (bits.length ? '<div class="meta">' + bits.join('<span aria-hidden="true">·</span>') + '</div>' : '') + '</div></li>';
    }

    function waitText(sec) {
      return (sec * 1000 >= SLOW_MS ? '조금 오래 걸리고 있어요' : '답을 쓰는 중이에요') + (sec >= 1 ? ' · ' + sec + '초' : '');
    }
    function elapsed(s) { return Math.max(0, Math.floor((Date.now() - s.pending.startedAt) / 1000)); }
    function typingHTML(s) {
      return '<li class="ch-msg ai is-typing"><span class="ch-av sm is-speaking" aria-hidden="true">' + E(initial(nameOf())) + '</span><div class="col"><div class="bub"><span class="ch-dots" aria-hidden="true"><i></i><i></i><i></i></span><span class="ch-wait" data-wait>' + waitText(elapsed(s)) + '</span></div></div></li>';
    }

    function nearBottom() { const l = R.list; return !l || l.scrollHeight - l.scrollTop - l.clientHeight < 80; }

    function renderList() {
      const s = chat ? chat.state : null;
      if (!R.list) return;
      const ready = !!(s && s.phase === 'ready');
      R.list.hidden = !ready;
      if (R.playbar) { R.playbar.innerHTML = ready ? playbarHTML(s) : ''; R.playbar.hidden = !(ready && s.play); }
      if (!ready) { R.list.innerHTML = ''; return; }
      const stick = ui.stick || nearBottom();
      const msgs = s.messages;
      let html = msgs.map((m, i) => messageHTML(m, s, i === msgs.length - 1)).join('');
      if (s.pending) html += typingHTML(s);
      // 좁은 화면에서는 상황 목록이 대화 아래에 있다.
      if (!html) html = '<li class="ch-empty"><p><b>' + E(nameOf()) + '</b>에게 먼저 말을 걸어 보세요.</p><p class="hint">' + (narrow && narrow.matches ? '아래' : '오른쪽') + ' 상황을 누르면 준비된 말을 하나씩 보내고 답을 받아요.</p></li>';
      R.list.innerHTML = html;
      const lastMsg = msgs[msgs.length - 1];
      const newReply = !!(lastMsg && lastMsg.role === 'assistant' && lastMsg.id !== ui.lastSeen);
      if (lastMsg) ui.lastSeen = lastMsg.id;
      if (stick) {
        // 긴 답은 첫 줄부터 읽히게 답의 머리로, 아니면 맨 아래로 내린다.
        const el = newReply ? R.list.querySelector('[data-mid="' + lastMsg.id + '"]') : null;
        if (el && el.offsetHeight > R.list.clientHeight - 48) R.list.scrollTop = Math.max(0, el.offsetTop - 12);
        else R.list.scrollTop = R.list.scrollHeight;
      }
      ui.stick = false;
    }

    function renderState() {
      if (!R.state) return;
      const s = chat ? chat.state : null;
      let html = '';
      if (!chat) {
        html = '<div class="ch-card"><h2>대화할 캐릭터를 골라 주세요</h2><p>대화 가능한 캐릭터를 고르면 여기서 바로 말을 걸 수 있어요.</p><div class="acts"><a class="btn pri" href="factory.html#all">전체 캐릭터 보기</a></div></div>';
      } else if (s.phase === 'loading') {
        html = '<div class="ch-card is-muted" aria-busy="true"><p class="row"><span class="ch-spin" aria-hidden="true"></span>대화 준비 상태를 확인하는 중이에요…</p></div>';
      } else if (s.phase === 'not-ready') {
        // 서버가 빠진 것과 할 일(reason), 갈 곳(nextHref)을 준다(약속 3). 없으면 진행 화면으로 보낸다.
        const m = meta() || {};
        const next = /^(factory|sources)\.html(#|$)/.test(text(m.nextHref)) ? text(m.nextHref) : factoryHref(chat.characterId);
        const label = next.indexOf('sources.html') === 0 ? '원문 화면 열기' : '진행 화면 열기';
        html = '<div class="ch-card is-wait" role="status"><h2>아직 대화할 수 없어요</h2><p>' + E(s.reason) + '</p><div class="acts"><a class="btn pri" href="' + E(next) + '">' + label + '</a><button type="button" class="btn" data-act="reload" data-key="reload">' + icon('refresh') + '다시 확인</button></div></div>';
      } else if (s.phase === 'missing') {
        html = '<div class="ch-card is-bad" role="alert"><h2>캐릭터를 찾지 못했어요</h2><p>' + E(s.reason) + '</p><div class="acts"><a class="btn pri" href="factory.html#all">전체 캐릭터 보기</a></div></div>';
      } else if (s.phase === 'error') {
        html = '<div class="ch-card is-bad" role="alert"><h2>대화 화면을 열지 못했어요</h2><p>' + E(s.error) + '</p><div class="acts"><button type="button" class="btn pri" data-act="reload" data-key="reload">' + icon('refresh') + '다시 불러오기</button></div></div>';
      }
      R.state.innerHTML = html;
      R.state.hidden = !html;
    }

    function renderComposer() {
      if (!R.form) return;
      const s = chat ? chat.state : null;
      const ready = !!(s && s.phase === 'ready');
      R.form.hidden = !ready;
      if (!ready) return;
      const playing = !!(s.play && s.play.status === 'running');
      const busy = !!s.pending || playing;
      R.input.disabled = playing;
      R.input.placeholder = playing ? '상황을 재생하는 중이에요. 멈추면 이어서 말할 수 있어요.' : nameOf() + '에게 말을 걸어 보세요';
      const mode = busy ? 'stop' : 'send';
      if (R.sendBtn.dataset.mode !== mode) {
        R.sendBtn.dataset.mode = mode;
        R.sendBtn.innerHTML = busy ? icon('stop') + '<span>멈추기</span>' : icon('send') + '<span>보내기</span>';
      }
      R.sendBtn.setAttribute('aria-label', busy ? (playing ? '재생 멈추기' : '답 받기 멈추기') : '보내기');
      R.sendBtn.disabled = !busy && !text(R.input.value).trim();
      if (R.hint) R.hint.textContent = busy ? 'Esc를 눌러도 멈춰요' : 'Enter로 보내고 Shift+Enter로 줄을 바꿔요';
    }

    // 오른쪽 패널: 상황 재생 목록과 만들 때 받아 둔 답.
    function samplesHTML(list, key) {
      if (!list.length) return '';
      const count = list.reduce((n, x) => n + ((x && Array.isArray(x.turns)) ? x.turns.length : 0), 0);
      const body = list.map((x) => '<div class="ch-sample">' + (list.length > 1 || key === 'rest' ? '<p class="st">' + E(text(x && x.title) || '받아 둔 답') + '</p>' : '') +
        '<ol>' + ((x && Array.isArray(x.turns)) ? x.turns : []).map((t) => '<li><p class="u"><span class="sr">나: </span>' + E(t && t.user) + '</p><p class="r"><span class="sr">' + E(nameOf()) + ': </span>' + E(t && t.reply) + '</p></li>').join('') + '</ol></div>').join('');
      return '<details class="ch-samples" data-open-key="' + E(key) + '"' + (ui.open.has(key) ? ' open' : '') + '><summary data-key="sum:' + E(key) + '">만들 때 받아 둔 답 <span class="n">' + count + '개</span></summary>' + body + '</details>';
    }
    function renderPanel() {
      if (!R.panel) return;
      const s = chat ? chat.state : null;
      const ready = !!(s && s.phase === 'ready');
      R.panel.hidden = !ready;
      if (!ready) { R.panel.innerHTML = ''; return; }
      const m = meta() || {};
      const groups = groupScenarios(m.scenarios);
      const samples = Array.isArray(m.samples) ? m.samples : [];
      const byScenario = new Map();
      samples.forEach((x) => { const k = text(x && x.scenarioId); if (!byScenario.has(k)) byScenario.set(k, []); byScenario.get(k).push(x); });
      // 뺀 기본 상황의 받아 둔 답도 함께 뺀다(같은 제목이 두 번 보이지 않게).
      groups.dropped.forEach((id) => byScenario.delete(id));
      const p = s.play;
      const locked = !!s.pending || !!(p && p.status === 'running');
      const itemHTML = (sc) => {
        const turns = Array.isArray(sc.turns) ? sc.turns : [];
        const on = !!(p && p.scenarioId === sc.id);
        const done = on ? Math.min(p.index, p.turns.length) : 0;
        const now = on && p.status === 'running';
        const turnList = on ? '<ol class="ch-turns">' + turns.map((t, i) => '<li class="' + (i < done ? 'ok' : (i === done && now ? 'now' : '')) + '"' + (i === done && now ? ' aria-current="step"' : '') + '>' + E(t) + '</li>').join('') + '</ol>' : '';
        const mine = byScenario.get(text(sc.id)) || [];
        byScenario.delete(text(sc.id));
        const title = text(sc.title) || '상황';
        // 누르면 지금 대화를 지우고 새로 시작하므로 단추에 그 사실을 적는다.
        const sub = on
          ? (now ? '재생 중 · ' + Math.min(done + 1, turns.length) + '/' + turns.length : (p.status === 'done' ? '모두 재생했어요' : '멈춤 · ' + done + '/' + turns.length))
          : '말 ' + turns.length + '개 · 새 대화로 시작해요';
        return '<li class="ch-sc' + (on ? ' is-on is-' + p.status : '') + '">' +
          '<button type="button" class="ch-sc-play" data-act="play" data-id="' + E(sc.id) + '" data-key="play:' + E(sc.id) + '"' + (locked || !turns.length ? ' disabled' : '') + ' aria-label="' + E(title) + ' 상황 재생, 새 대화로 말 ' + turns.length + '개를 보내요">' +
          '<span class="ic" aria-hidden="true">' + icon(on && p.status === 'done' ? 'check' : 'play') + '</span><span class="tx"><b>' + E(title) + '</b><small>' + sub + '</small></span></button>' +
          turnList + samplesHTML(mine, 'sc:' + text(sc.id)) + '</li>';
      };
      // 전용 상황이 있으면 먼저 펼쳐 두고 남은 기본 상황은 접는다. 전용 상황이 없으면 기본 상황을 바로 보인다.
      const mineHTML = groups.mine.map(itemHTML).join('');
      const basicHTML = groups.basic.map(itemHTML).join('');
      const playingBasic = !!(p && groups.basic.some((x) => x.id === p.scenarioId));
      let list = '';
      if (mineHTML) {
        list = '<ul class="ch-scs">' + mineHTML + '</ul>';
        if (basicHTML) list += '<details class="ch-basic" data-open-key="basic"' + (ui.open.has('basic') || playingBasic ? ' open' : '') + '><summary data-key="sum:basic">기본 상황 <span class="n">' + groups.basic.length + '개</span></summary><ul class="ch-scs">' + basicHTML + '</ul></details>';
      } else if (basicHTML) list = '<ul class="ch-scs">' + basicHTML + '</ul>';
      const rest = Array.from(byScenario.values()).reduce((a, b) => a.concat(b), []);
      R.panel.innerHTML = '<section class="ch-sec" aria-labelledby="ch-sc-h"><div class="ch-sec-h"><h2 id="ch-sc-h">상황 재생</h2>' + (p && p.status === 'running' ? '<button type="button" class="btn ghost" data-act="stop" data-key="stop">' + icon('stop') + '멈추기</button>' : '') + '</div>' +
        (list || '<p class="ch-none">준비된 상황이 없어요.</p>') + '</section>' +
        (rest.length ? '<section class="ch-sec" aria-labelledby="ch-sm-h"><div class="ch-sec-h"><h2 id="ch-sm-h">그 밖에 받아 둔 답</h2></div>' + samplesHTML(rest, 'rest') + '</section>' : '');
    }

    function announce() {
      const s = chat && chat.state;
      if (!R.live || !s || !s.announce || s.announce.id === ui.announced) return;
      ui.announced = s.announce.id;
      R.live.textContent = nameOf() + ': ' + (text(s.announce.text).trim() || '빈 답이 왔어요.');
    }

    function syncTick() {
      const s = chat && chat.state;
      if (s && s.pending && !tick) {
        tick = global.setInterval(() => {
          const el = R.list && R.list.querySelector('[data-wait]');
          const st = chat && chat.state;
          if (el && st && st.pending) el.textContent = waitText(elapsed(st));
        }, 500);
      } else if (!(s && s.pending) && tick) { global.clearInterval(tick); tick = null; }
    }

    // 다시 그려도 키보드 포커스가 같은 단추에 남게 한다. 그 단추가 사라지면 가까운 다음 단추로 옮긴다.
    const FALLBACK = { 'play:': ['stop'], stop: ['resume', 'retry', 'reset'], resume: ['stop'], retry: ['stop'] };
    function render() {
      const active = doc.activeElement;
      const key = active && active.getAttribute ? active.getAttribute('data-key') : null;
      renderCall(); renderState(); renderList(); renderComposer(); renderPanel(); announce(); syncTick();
      if (!key) return;
      const find = (k) => { const el = doc.querySelector('[data-key="' + k.replace(/"/g, '') + '"]'); return el && !el.disabled ? el : null; };
      let el = find(key);
      if (!el) {
        const alts = FALLBACK[key.startsWith('play:') ? 'play:' : key] || [];
        for (const k of alts) { el = find(k); if (el) break; }
      }
      if (!el && R.input && !R.input.disabled && !R.form.hidden) el = R.input;
      if (el && el !== doc.activeElement) el.focus({ preventScroll: true });
    }

    function open() {
      if (unsub) unsub();
      if (chat) chat.destroy();
      ui.lastSeen = ''; ui.stick = true; ui.announced = '';
      const cid = routeId(global.location && global.location.hash);
      chat = cid ? createChat({ fetch: o.fetch, apiBase: o.apiBase, characterId: cid, storage: session, gap: o.gap, pause: o.pause }) : null;
      if (chat) {
        unsub = chat.subscribe(() => {
          if (chat) doc.title = (chat.state.meta ? nameOf() + ' · ' : '') + '대화해 보기 · Foundry';
          render();
        });
      }
      renderSide(); renderHead(); render();
      if (chat) chat.load().then(() => { renderHead(); renderSide(); if (chat && chat.state.phase === 'ready' && R.input && !R.input.disabled) R.input.focus(); });
    }

    function autosize() {
      if (!R.input) return;
      R.input.style.height = 'auto';
      R.input.style.height = Math.min(R.input.scrollHeight, 168) + 'px';
    }
    function submit() {
      if (!chat || !R.input) return;
      const value = R.input.value;
      if (!text(value).trim() || !chat.canSend()) return;
      R.input.value = '';
      autosize();
      ui.stick = true;
      chat.send(value);
    }

    doc.addEventListener('click', (ev) => {
      const el = ev.target && ev.target.closest ? ev.target.closest('[data-act]') : null;
      if (!el || el.disabled) return;
      const act = el.dataset.act;
      if (act === 'theme') { setTheme(el.dataset.theme); return; }
      if (!chat) return;
      if (act === 'play') {
        ui.stick = true;
        chat.play(el.dataset.id);
        // 좁은 화면에서는 상황 목록이 대화 아래에 있으므로 재생하는 대화가 보이게 올린다.
        if (R.stage && R.stage.getBoundingClientRect().top < 0 && R.stage.scrollIntoView) R.stage.scrollIntoView({ block: 'start', behavior: 'smooth' });
      }
      else if (act === 'stop') chat.stop();
      else if (act === 'resume') { ui.stick = true; chat.resume(); }
      else if (act === 'retry') { ui.stick = true; chat.retry(); }
      else if (act === 'reload') chat.load();
      else if (act === 'reset') { chat.reset(); if (R.input) { R.input.disabled = false; R.input.focus(); } }
    });
    doc.addEventListener('toggle', (ev) => {
      const d = ev.target;
      if (!d || !d.getAttribute || !d.hasAttribute('data-open-key')) return;
      const k = d.getAttribute('data-open-key');
      if (d.open) ui.open.add(k); else ui.open.delete(k);
    }, true);
    if (R.form) {
      R.form.addEventListener('submit', (ev) => {
        ev.preventDefault();
        if (R.sendBtn && R.sendBtn.dataset.mode === 'stop') { if (chat) chat.stop(); return; }
        submit();
      });
    }
    if (R.input) {
      R.input.addEventListener('keydown', (ev) => {
        // 한글 조합 중 Enter는 글자를 확정하는 키라 보내지 않는다.
        if (ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing && ev.keyCode !== 229) { ev.preventDefault(); submit(); }
      });
      R.input.addEventListener('input', () => { autosize(); renderComposer(); });
    }
    doc.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape' && chat && (chat.state.pending || (chat.state.play && chat.state.play.status === 'running'))) { ev.preventDefault(); chat.stop(); }
    });
    if (media && media.addEventListener) media.addEventListener('change', () => { if (ui.theme === 'system') applyTheme(); });
    global.addEventListener('hashchange', open);

    applyTheme();
    open();
    loadCharacters();
    return { get chat() { return chat; }, open };
  }

  const api = { createChat, mount, routeId, seconds, revLabel, viaLabel, rejectedCount, isMotif, displayName, createdLabel, chatList, isGeneric, groupScenarios, MOTIF_NOTE };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (global) global.CharacterChat = api;
})(typeof window !== 'undefined' ? window : globalThis);
