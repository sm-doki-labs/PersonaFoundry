(function APPBAR() {
  // 공통 상단바 동작. 두 화면은 AppBar.init(provider)로 데이터만 넘기고, 알림·작업실 탭의 동작은 여기 한 곳에서 정한다.
  // provider: { notes(): [{t, kind, html}], unread(): number, markRead(), picks(): [{code, title, who}], currentGate(): code|null, back(): string, beforeLeave()? }
  const START = 14 * 60;
  const RUN = 'cf-20261021-s2real';
  const $ = (s, r = document) => r.querySelector(s);
  const hm = (m) => { const v = Math.round(START + m); return `${String(Math.floor(v / 60) % 24).padStart(2, '0')}:${String(v % 60).padStart(2, '0')}`; };
  const pickHref = (code, back) => `c-glass.html?gate=${encodeURIComponent(code)}&run=${RUN}&back=${encodeURIComponent(back)}`;
  let P = null, lastList = '';

  function openPanel() {
    const panel = $('[data-notes]'), bell = $('[data-bell]');
    panel.hidden = false;
    const r = bell.getBoundingClientRect();
    panel.style.top = `${Math.round(r.bottom + 10)}px`;
    panel.style.right = `${Math.round(window.innerWidth - r.right)}px`;
    bell.setAttribute('aria-expanded', 'true');
    P.markRead();
    lastList = '';
    render();
  }
  function closePanel(focusBell) {
    const panel = $('[data-notes]'), bell = $('[data-bell]');
    if (panel.hidden) return false;
    panel.hidden = true;
    bell.setAttribute('aria-expanded', 'false');
    if (focusBell) bell.focus();
    return true;
  }

  function render() {
    if (!P) return;
    const unread = P.unread(), bell = $('[data-bell]');
    $('[data-bell-count]').textContent = unread ? String(unread) : '';
    bell.setAttribute('aria-label', unread ? `알림 · 안 읽은 알림 ${unread}건` : '알림');
    const panel = $('[data-notes]');
    if (!panel.hidden) {
      const notes = P.notes();
      const html = notes.length
        ? notes.map((n) => `<li class="note k-${n.kind}"><span class="dot"></span><span>${n.html}</span><span class="num">${hm(n.t)}</span></li>`).join('')
        : '<li class="note is-empty"><span></span><span>새 알림이 없어요</span><span></span></li>';
      if (html !== lastList) { panel.querySelector('[data-notes-list]').innerHTML = html; lastList = html; }
    }
    const picks = P.picks(), tab = $('[data-workroom-tab]');
    $('[data-workroom-count]').textContent = picks.length ? String(picks.length) : '';
    const top = picks[0];
    tab.href = top ? pickHref(top.code, P.back()) : 'c-glass.html';
    tab.title = top ? `고를 것 ${picks.length}건 · 먼저 ${top.who} ${top.code} ${top.title}` : '고를 것이 없어요';
  }

  document.addEventListener('click', (e) => {
    if (!P) return;
    if (e.target.closest('[data-bell]')) { if (!closePanel(false)) openPanel(); return; }
    if (!e.target.closest('[data-notes]')) closePanel(false);
    const tab = e.target.closest('[data-workroom-tab]');
    if (tab) {
      render();
      const picks = P.picks(), cur = P.currentGate();
      // 지금 보고 있는 관문이 가장 먼저 처리할 관문이면 다시 불러오지 않는다
      if (tab.classList.contains('is-active') && (!picks.length || picks[0].code === cur)) { e.preventDefault(); return; }
      if (P.beforeLeave) P.beforeLeave();
    }
  }, true);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && closePanel(true)) { e.stopImmediatePropagation(); }
  }, true);
  window.addEventListener('resize', () => { if (!$('[data-notes]').hidden) openPanel(); });

  window.AppBar = { init(provider) { P = provider; render(); }, render, pickHref, hm };
})();

