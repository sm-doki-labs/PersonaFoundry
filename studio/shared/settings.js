/* 설정 화면(D-0211): Grok 계정 연결과 텍스트 모델 설정. 앱 틀은 원문 화면(sources.js)의 사이드바를 쓴다. */
(function () {
  'use strict';
  const $ = (s) => document.querySelector(s);
  const E = (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const intake = window.SourceIntake;
  const store = (() => { try { return window.localStorage; } catch (e) { return null; } })();
  let theme = (store && ['light', 'dark'].indexOf(store.getItem('fd-theme')) >= 0) ? store.getItem('fd-theme') : 'system';
  let projects = null;
  let data = null;
  let busy = false;
  let error = '';
  let poll = null;
  let tick = null;

  async function api(method, path) {
    const res = await fetch(path, { method, cache: 'no-store', headers: { Accept: 'application/json' } });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const d = body && body.detail;
      throw new Error((d && (d.message || d)) || '요청을 처리하지 못했어요 (' + res.status + ')');
    }
    return body;
  }

  function setTheme(t) {
    theme = t;
    try { if (t === 'system') store.removeItem('fd-theme'); else store.setItem('fd-theme', t); } catch (e) { /* 이번 화면에만 적용 */ }
    if (t === 'system') document.documentElement.removeAttribute('data-fd-theme');
    else document.documentElement.setAttribute('data-fd-theme', t);
    renderSide();
  }

  function renderSide() {
    const side = $('[data-side]');
    if (side && intake) side.innerHTML = intake.sideHTML(projects, theme, { current: 'settings' });
  }

  function left(expiresAt) {
    const ms = Date.parse(expiresAt || '') - Date.now();
    if (!(ms > 0)) return '0:00';
    const s = Math.floor(ms / 1000);
    return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
  }

  function routeText(video) {
    const order = (video && video.order) || [];
    if (order[0] === 'grok_oauth') return '영상은 이 계정의 Grok 구독으로 먼저 만들고, 연결이 안 되거나 막히면 xAI API 키로 만들어요(API 키는 비용이 들어요).';
    return '지금 서버 설정은 영상을 xAI API 키로만 만들어요. 계정을 연결해도 서버 설정을 바꾸기 전에는 쓰지 않아요.';
  }

  function grokHTML() {
    if (!data) return '<p class="hint">' + (error ? E(error) : '불러오는 중이에요') + '</p>';
    const g = data.grok || {};
    const f = data.flow;
    const pending = f && f.status === 'pending';
    const pill = g.connected
      ? '<span class="set-pill ok"><span class="dot" aria-hidden="true"></span>연결됨</span>'
      : pending ? '<span class="set-pill wait"><span class="dot" aria-hidden="true"></span>승인 기다리는 중</span>'
        : '<span class="set-pill"><span class="dot" aria-hidden="true"></span>연결 안 됨</span>';
    let body = '';
    if (pending) {
      body = '<div class="set-code" role="group" aria-label="승인 코드">' +
        '<div><span class="lbl">승인 코드</span><b class="code" data-code>' + E(f.code) + '</b></div>' +
        '<a class="btn pri" href="' + E(f.url) + '" target="_blank" rel="noopener">xAI에서 승인하기<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 17 17 7M9 7h8v8"/></svg></a></div>' +
        '<p class="set-note">xAI 화면에 같은 코드가 보이는지 확인하고 승인하세요. 승인하면 이 화면이 저절로 바뀌어요. <span class="left">남은 시간 <b data-left>' + left(f.expiresAt) + '</b></span></p>';
    } else if (g.connected) {
      body = '<dl class="set-facts"><div><dt>계정</dt><dd>' + E(g.email || '이메일을 받지 못했어요') + '</dd></div>' +
        '<div><dt>로그인 유지</dt><dd>쓸 때마다 자동으로 갱신해요</dd></div></dl>';
    }
    if (f && (f.status === 'failed' || f.status === 'expired') && !g.connected) {
      body += '<p class="set-err" role="alert">' + (f.status === 'expired' ? '승인 코드가 만료됐어요. 다시 연결해 주세요.' : E(f.error || '연결하지 못했어요.')) + '</p>';
    }
    if (error) body += '<p class="set-err" role="alert">' + E(error) + '</p>';
    let acts = '';
    if (g.connected) acts = '<button type="button" class="btn ghost" data-act="grok-logout"' + (busy ? ' disabled' : '') + '>연결 끊기</button>';
    else if (!pending) acts = '<button type="button" class="btn pri" data-act="grok-connect"' + (busy ? ' disabled' : '') + '>' + (busy ? '코드 받는 중…' : (f ? '다시 연결하기' : '계정 연결하기')) + '</button>';
    return '<div class="set-row"><h2 id="set-grok-h">Grok 계정 연결</h2>' + pill + '</div>' +
      '<p class="set-lead">' + routeText(data.video) + '</p>' + body +
      (acts ? '<div class="set-acts">' + acts + '</div>' : '');
  }

  function render() {
    const box = $('[data-grok]');
    if (box) box.innerHTML = grokHTML();
    schedule();
  }

  function schedule() {
    const pending = data && data.flow && data.flow.status === 'pending' && !(data.grok || {}).connected;
    if (pending && !poll) poll = setInterval(refresh, 3000);
    if (!pending && poll) { clearInterval(poll); poll = null; }
    if (pending && !tick) tick = setInterval(() => { const el = $('[data-left]'); if (el) el.textContent = left(data.flow.expiresAt); }, 1000);
    if (!pending && tick) { clearInterval(tick); tick = null; }
  }

  async function refresh() {
    try {
      const was = data && data.grok && data.grok.connected;
      data = await api('GET', '/api/settings/grok');
      error = '';
      if (!was && data.grok && data.grok.connected) say('Grok 계정이 연결됐어요.');
    } catch (e) { error = e.message; }
    render();
  }

  function say(msg) { const live = $('[data-live]'); if (live) live.textContent = msg; }

  async function act(name) {
    if (busy) return;
    if (name === 'grok-logout' && !window.confirm('Grok 계정 연결을 끊을까요? 끊으면 영상은 xAI API 키로 만들어져 비용이 들어요.')) return;
    busy = true; error = ''; render();
    try {
      data = await api(name === 'grok-connect' ? 'POST' : 'DELETE', name === 'grok-connect' ? '/api/settings/grok/device' : '/api/settings/grok');
      if (name === 'grok-connect') { say('승인 코드를 받았어요.'); const code = $('[data-code]'); if (code) code.focus && code.focus(); }
      else say('연결을 끊었어요.');
    } catch (e) { error = e.message; }
    busy = false; render();
  }

  document.addEventListener('click', (event) => {
    const el = event.target.closest('[data-act]');
    if (!el) return;
    const a = el.dataset.act;
    if (a === 'theme') setTheme(el.dataset.theme || 'system');
    else if (a === 'theme-next') setTheme(theme === 'system' ? 'light' : theme === 'light' ? 'dark' : 'system');
    else if (a === 'grok-connect' || a === 'grok-logout') act(a);
  });

  if (window.FactoryTextPipeline) {
    const panel = window.FactoryTextPipeline.mount({ root: $('[data-text-pipeline-root]'), apiBase: '' });
    $('[data-text-open]').addEventListener('click', () => panel.open());
    if (new URLSearchParams(location.search).get('panel') === 'text') panel.open();
  }
  renderSide();
  api('GET', '/api/projects').then((list) => { projects = Array.isArray(list) ? list : (list && list.projects) || []; renderSide(); }).catch(() => { projects = []; renderSide(); });
  refresh();
})();
