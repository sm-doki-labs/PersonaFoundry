// 세 시안이 함께 쓰는 선택·확정·되돌리기 흐름과 효과.
(function ENGINE(){
  const D = window.FACTORY_DATA;
  const ICONS = {
    face:'<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><path d="M9 9h.01"/><path d="M15 9h.01"/>',
    doc:'<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
    image:'<rect width="18" height="18" x="3" y="3" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>',
    film:'<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M7 3v18"/><path d="M3 7.5h4"/><path d="M3 12h18"/><path d="M3 16.5h4"/><path d="M17 3v18"/><path d="M17 7.5h4"/><path d="M17 16.5h4"/>',
    chat:'<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
    package:'<path d="m7.5 4.27 9 5.15"/><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>',
    check:'<path d="M20 6 9 17l-5-5"/>',
    refresh:'<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    pencil:'<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/><path d="m15 5 4 4"/>',
    arrow:'<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    undo:'<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"/>',
    plus:'<path d="M5 12h14"/><path d="M12 5v14"/>',
    star:'<path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"/>',
    aperture:'<circle cx="12" cy="12" r="10"/><path d="m14.31 8 5.74 9.94"/><path d="M9.69 8h11.48"/><path d="m7.38 12 5.74-9.94"/><path d="M9.69 16 3.95 6.06"/><path d="M14.31 16H2.83"/><path d="m16.62 12-5.74 9.94"/>',
    send:'<path d="M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z"/><path d="m21.854 2.147-10.94 10.939"/>'
    ,bell:'<path d="M10.268 21a2 2 0 0 0 3.464 0"/><path d="M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.673C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326"/>'
    ,chevron:'<path d="m9 18 6-6-6-6"/>'
    ,activity:'<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/>'
  };
  const q = (s, r = document) => r.querySelector(s);
  const qa = (s, r = document) => [...r.querySelectorAll(s)];
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const wait = (ms) => new Promise((r) => setTimeout(r, reduce ? 0 : ms));
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  const icon = (n, cls = 'ic') => `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[n] || ''}</svg>`;
  const CIRCLE = '<svg class="cand-circle" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><path pathLength="1" d="M52 3 C 82 2, 98 22, 97 50 C 96 81, 76 98, 47 97 C 18 96, 2 77, 3 48 C 4 22, 22 5, 58 6"/></svg>';

  const fresh = () => ({ step: 0, sel: [], choices: {}, tweaks: [], customTweaks: [], extra: {}, alt: {}, history: [], busy: false });
  let state = fresh();

  const stepData = () => D.steps[state.step];
  const ST = (id) => D.steps.find((x) => x.id === id);
  const cands = (s) => [...s.candidates, ...(state.extra[s.id] || [])];
  const findCand = (s, id) => cands(s).find((c) => c.id === id);
  const imgOf = (s, c) => (state.alt[s.id] && c.alt ? c.alt : c.img);
  const titleOf = (s, c) => (state.alt[s.id] && c.altTitle ? c.altTitle : c.title);
  const descOf = (s, c) => (state.alt[s.id] && c.altDesc ? c.altDesc : c.desc);
  const emit = (name, detail) => document.dispatchEvent(new CustomEvent(name, { detail }));

  function setText(sel, t) { qa(sel).forEach((e) => { e.textContent = t || ''; }); }
  function agentHTML(t) { return `<span class="agent-dot" aria-hidden="true"></span><span class="agent-text">${esc(t)}</span>`; }

  function renderRail(justDone) {
    const cur = state.step < D.steps.length ? D.steps[state.step].stage : D.finaleStage;
    qa('[data-rail]').forEach((rail) => {
      rail.innerHTML = D.stages.map((s, i) => {
        const st = i < cur ? 'done' : i === cur ? 'current' : 'locked';
        return `<li class="rail-item is-${st}${i === justDone ? ' just-done' : ''}"${st === 'current' ? ' aria-current="step"' : ''}>`
          + `<span class="rail-icon">${icon(st === 'done' ? 'check' : s.icon)}</span>`
          + `<span class="rail-text"><span class="rail-label">${s.label}</span><span class="rail-sub">${s.sub}</span></span>`
          + `<span class="rail-num">${String(i + 1).padStart(2, '0')}</span></li>`;
      }).join('');
    });
    const pct = Math.round((cur / D.stages.length) * 100);
    qa('[data-progress-bar]').forEach((b) => b.style.setProperty('--p', pct + '%'));
    setText('[data-progress-text]', `${D.stages.length}단계 중 ${Math.min(cur + 1, D.stages.length)}단계`);
  }

  function cardHTML(s, c, i) {
    const kind = c.custom ? 'text' : s.kind;
    const attr = `type="button" class="cand cand--${kind}${c.custom ? ' is-custom' : ''}" data-id="${esc(c.id)}" aria-pressed="false" style="--i:${i}"`;
    const num = `<span class="cand-num">${i + 1}</span>`;
    const check = `<span class="cand-check">${icon('check')}</span>`;
    const tags = c.tags ? `<span class="cand-tags">${c.tags.map((t) => `<span class="tag">${esc(t)}</span>`).join('')}</span>` : '';
    const badge = c.recommended ? `<span class="cand-badge">${icon('star')}추천</span>` : '';
    if (kind === 'image') {
      return `<button ${attr}><span class="cand-media"><img src="${imgOf(s, c)}" alt="${esc(titleOf(s, c))}" draggable="false">${num}${badge}${check}${CIRCLE}<span class="cand-shine"></span></span>`
        + `<span class="cand-body"><span class="cand-title">${esc(titleOf(s, c))}</span><span class="cand-desc">${esc(descOf(s, c))}</span>${tags}</span></button>`;
    }
    if (kind === 'chip') {
      return `<button ${attr}><span class="chip-box">${icon('check')}</span><span class="chip-label">${esc(c.title)}</span></button>`;
    }
    const name = c.name || c.title || '직접 쓴 안';
    return `<button ${attr}><span class="cand-head">${num}<span class="cand-name">${esc(name)}</span>${c.mbti ? `<span class="cand-mbti">${esc(c.mbti)}</span>` : ''}${check}</span>`
      + `<span class="cand-desc">${esc(c.desc)}</span>`
      + (c.move ? `<span class="cand-move"><span class="cand-move-label">이럴 때 먼저 하는 행동</span><span class="cand-move-text">${esc(c.move)}</span></span>` : '')
      + (c.quote ? `<span class="cand-quote">${esc(c.quote)}</span>` : '')
      + tags + CIRCLE + '<span class="cand-shine"></span></button>';
  }

  function renderCands(develop) {
    const s = stepData();
    const box = q('[data-cands]');
    box.className = `cands cands--${s.kind}${s.ratio ? ' cands--' + s.ratio : ''} cands--n${cands(s).length}`;
    box.setAttribute('role', 'group');
    box.setAttribute('aria-label', s.title);
    box.innerHTML = cands(s).map((c, i) => cardHTML(s, c, i)).join('');
    applySelection();
    if (develop && !reduce) {
      qa('.cand', box).forEach((c) => c.classList.add('is-developing'));
      setTimeout(() => qa('.cand', box).forEach((c) => c.classList.remove('is-developing')), 2200);
    }
  }

  function renderTweaks(s) {
    const t = q('[data-tweaks]');
    if (!t) return;
    t.hidden = !s.tweaks;
    if (!s.tweaks) { t.innerHTML = ''; return; }
    t.innerHTML = `<span class="tweaks-label">${icon('pencil')}고칠 점</span>`
      + [...s.tweaks, ...state.customTweaks].map((x) => `<button type="button" class="chip tweak" aria-pressed="${state.tweaks.includes(x)}">${esc(x)}</button>`).join('');
  }

  function renderStep({ develop = true } = {}) {
    const s = stepData();
    state.sel = []; state.tweaks = []; state.customTweaks = [];
    const body = q('[data-stage-body]');
    if (body) body.scrollTop = 0;
    setText('[data-kicker]', s.kicker); setText('[data-title]', s.title); setText('[data-desc]', s.desc);
    const seed = q('[data-seed]');
    if (seed) { seed.hidden = !s.seed; seed.innerHTML = s.seed ? `<span class="seed-label">씨앗</span>` + s.seed.map((x) => `<span class="chip chip--static seed-chip">${esc(x)}</span>`).join('') : ''; }
    const sit = q('[data-situation]');
    if (sit) { sit.hidden = !s.situation; sit.innerHTML = s.situation ? `<span class="sit-label">같은 상황</span><span class="sit-text">${esc(s.situation)}</span>` : ''; }
    const pr = q('[data-presets]');
    if (pr) { pr.hidden = !s.presets; pr.innerHTML = s.presets ? s.presets.map((p, i) => `<button type="button" class="chip chip--md preset${i === 0 ? ' is-active' : ''}" data-preset="${i}">${esc(p.label)}</button>`).join('') : ''; }
    renderCands(develop);
    renderTweaks(s);
    const wt = q('[data-write-toggle]'), w = q('[data-write]'), wi = q('[data-write-input]');
    if (wt) { wt.hidden = !s.writePlaceholder; wt.setAttribute('aria-expanded', 'false'); wt.classList.remove('is-active'); }
    if (w) w.classList.remove('is-open');
    if (wi) { wi.value = ''; wi.placeholder = s.writePlaceholder || ''; }
    const rg = q('[data-regen]');
    if (rg) rg.hidden = !!s.noRegen;
    (s.preselect || []).forEach((id) => toggle(id, true, true));
    updateActions(true);
    const agent = q('[data-agent]'), judge = q('[data-judge]');
    const arrive = () => { if (stepData() !== s) return; agent.dataset.state = 'done'; agent.innerHTML = agentHTML(s.arrive); if (judge) { judge.textContent = s.judge || ''; judge.classList.toggle('is-on', !!s.judge); } };
    if (develop && !reduce) {
      agent.dataset.state = 'working'; agent.innerHTML = agentHTML(`${s.agent}가 ${s.working}`);
      if (judge) { judge.textContent = ''; judge.classList.remove('is-on'); }
      setTimeout(arrive, s.kind === 'chip' ? 600 : 1150);
    } else arrive();
    emit('factory:step', { step: s });
  }

  function applySelection() {
    const s = stepData();
    qa('[data-cands] .cand').forEach((c) => { const v = state.sel.includes(c.dataset.id); c.classList.toggle('is-selected', v); c.setAttribute('aria-pressed', String(v)); });
    const box = q('[data-cands]');
    box.classList.toggle('has-selection', state.sel.length > 0 && s.select === 'single');
  }

  function toggle(id, force, silent) {
    const s = stepData();
    const on = force ?? !state.sel.includes(id);
    if (s.select === 'single') state.sel = on ? [id] : [];
    else state.sel = on ? [...new Set([...state.sel, id])] : state.sel.filter((x) => x !== id);
    applySelection();
    if (!silent) updateActions();
    const c = findCand(s, id);
    if (on && c && !silent) emit('factory:select', { step: s, cand: c, img: c.img ? imgOf(s, c) : null });
  }

  function updateActions(initial) {
    const s = stepData(), n = state.sel.length, b = q('[data-confirm]');
    const wasDisabled = b.disabled;
    b.disabled = n === 0;
    b.querySelector('.btn-label').textContent = n === 0 && s.zeroLabel ? s.zeroLabel : (s.confirmLabel || '이걸로 확정').replace('{n}', n);
    if (wasDisabled && !b.disabled && !initial) { b.classList.remove('just-ready'); void b.offsetWidth; b.classList.add('just-ready'); }
    const hint = q('[data-hint]');
    if (hint) {
      let t = s.hint;
      if (n && s.select === 'single') { const c = findCand(s, state.sel[0]); t = `선택 · ${c ? (c.name || titleOf(s, c) || '직접 쓴 안') : ''}`; }
      else if (n && s.selHint) t = s.selHint.replace('{n}', n);
      hint.textContent = t;
      hint.classList.toggle('is-selected', n > 0);
    }
    const rg = q('[data-regen] .btn-label');
    if (rg) rg.textContent = state.tweaks.length ? `요청 ${state.tweaks.length}개로 다시 만들기` : '다시 만들기';
    q('[data-regen]')?.classList.toggle('has-tweaks', state.tweaks.length > 0);
  }

  function slotEl(name) {
    const all = qa(`[data-slot="${name}"]`);
    return all.find((e) => e.offsetParent !== null && e.getBoundingClientRect().width > 0) || null;
  }
  function empty(ic, label) { return `<span class="slot-empty">${icon(ic)}${label ? `<span>${esc(label)}</span>` : ''}</span>`; }
  function setSlot(name, html, filled) { qa(`[data-slot="${name}"]`).forEach((e) => { if (html !== null) e.innerHTML = html; e.classList.toggle('is-filled', !!filled); }); }

  function renderSheet(pulse = []) {
    const ch = state.choices, S = D.steps;
    const hero = ch.hero && findCand(ST('hero'), ch.hero[0]);
    const heroImg = hero && !hero.custom ? imgOf(ST('hero'), hero) : null;
    setSlot('portrait', heroImg ? `<img src="${heroImg}" alt="대표 얼굴">` : empty('face', '대표 얼굴'), !!heroImg);
    setSlot('avatar', heroImg ? `<img src="${heroImg}" alt="">` : empty('face', ''), !!heroImg);
    const plan = ch.plan && findCand(ST('plan'), ch.plan[0]);
    setSlot('profile', null, !!plan);
    setSlot('name', esc(plan ? (plan.name || '직접 쓴 안') : '새 캐릭터'), !!plan);
    setSlot('tagline', esc(plan ? plan.desc : '기획안을 고르면 채워져요'), !!plan);
    setSlot('meta', esc(plan ? [D.seedMeta, plan.mbti].filter(Boolean).join(' · ') : '나이 · 직업 · 성격 유형'), !!plan);
    setSlot('tags', plan && plan.tags ? plan.tags.map((t) => `<span class="tag">#${esc(t)}</span>`).join('') : '', !!plan);
    D.chapters.forEach((c) => {
      const fr = ch.frames && ch.frames.includes(c.id) ? findCand(ST('frames'), c.id) : null;
      const bgc = c.id === 'ch1' && ch.bg ? findCand(ST('bg'), ch.bg[0]) : null;
      const img = fr ? fr.img : bgc && !bgc.custom ? imgOf(ST('bg'), bgc) : null;
      setSlot(c.id, img ? `<img src="${img}" alt="${esc(c.label)}"><span class="slot-cap">${esc(c.label)}<em>${fr ? '승인' : '배경'}</em></span>` : empty('image', c.label), !!img);
    });
    const m = ch.motion;
    setSlot('motion', m ? `<span class="slot-motion"><strong class="slot-big">${m.length}</strong><span>편 영상 생성 대기</span></span>` : empty('film', '움직임 영상'), !!m);
    const filled = [heroImg, plan, ch.bg || ch.frames, ch.frames && ch.frames.includes('ch2'), ch.frames && ch.frames.includes('ch3'), m].filter(Boolean).length;
    setText('[data-sheet-count]', `6칸 중 ${filled}칸`);
    qa('[data-sheet-meter]').forEach((e) => e.style.setProperty('--p', Math.round((filled / 6) * 100) + '%'));
    const targets = pulse.flatMap((p) => (p === 'portrait' ? ['portrait', 'avatar'] : [p]));
    targets.forEach((p) => qa(`[data-slot="${p}"]`).forEach((e) => { e.classList.remove('slot-pop'); void e.offsetWidth; e.classList.add('slot-pop'); }));
  }

  function fly(src, target, delay = 0, label) {
    if (!src || !target || reduce) return Promise.resolve();
    const a = src.getBoundingClientRect(), b = target.getBoundingClientRect();
    if (!b.width || !a.width) return Promise.resolve();
    let g;
    if (label) { g = document.createElement('span'); g.className = 'fly-pill'; g.textContent = label; }
    else { g = src.cloneNode(true); qa('.stamp,.cand-check,.cand-num,.cand-badge,.cand-circle,.cand-shine', g).forEach((x) => x.remove()); }
    g.classList.add('fly-ghost');
    const from = label ? { left: a.left + a.width / 2 - 48, top: a.top, width: 96, height: a.height } : { left: a.left, top: a.top, width: a.width, height: a.height };
    const to = label ? { left: b.left + b.width / 2 - 48, top: b.top + b.height / 2 - a.height / 2, width: 96, height: a.height } : { left: b.left, top: b.top, width: b.width, height: b.height };
    const mid = { left: (from.left + to.left) / 2, top: Math.min(from.top, to.top) - 70, width: (from.width + to.width) / 2, height: (from.height + to.height) / 2 };
    const k = (r) => ({ left: r.left + 'px', top: r.top + 'px', width: r.width + 'px', height: r.height + 'px' });
    Object.assign(g.style, { position: 'fixed', margin: '0', zIndex: '1000', pointerEvents: 'none', ...k(from) });
    document.body.appendChild(g);
    const anim = g.animate([{ ...k(from), opacity: 1 }, { ...k(mid), opacity: 1, offset: 0.5 }, { ...k(to), opacity: 0.9 }], { duration: 780, delay, easing: 'cubic-bezier(.6,0,.25,1)', fill: 'forwards' });
    return anim.finished.then(() => g.animate([{ opacity: 0.9 }, { opacity: 0 }], { duration: 180, fill: 'forwards' }).finished).then(() => g.remove());
  }

  async function exitStage() {
    const b = q('[data-stage-body]');
    if (!b || reduce) return;
    await b.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateY(-12px)' }], { duration: 200, easing: 'ease-in', fill: 'forwards' }).finished;
  }
  function enterStage() {
    const b = q('[data-stage-body]');
    if (!b) return;
    b.getAnimations().forEach((x) => x.cancel());
    if (reduce) return;
    b.animate([{ opacity: 0, transform: 'translateY(16px)' }, { opacity: 1, transform: 'none' }], { duration: 340, easing: 'cubic-bezier(.2,.8,.2,1)' });
  }

  function toast(msg, undoable) {
    let t = q('.toast');
    if (!t) { t = document.createElement('div'); t.className = 'toast'; t.setAttribute('role', 'status'); document.body.appendChild(t); }
    t.innerHTML = `<span class="toast-ic">${icon('check')}</span><span class="toast-text">${esc(msg)}</span>` + (undoable ? `<button type="button" class="toast-undo" data-undo>${icon('undo')}되돌리기</button>` : '');
    t.classList.remove('is-on'); void t.offsetWidth; t.classList.add('is-on');
    clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('is-on'), 4200);
  }

  async function confirm() {
    const s = stepData();
    if (state.busy || !state.sel.length) return;
    state.busy = true;
    document.body.classList.add('is-busy');
    const cards = state.sel.map((id) => q(`[data-cands] .cand[data-id="${CSS.escape(id)}"]`)).filter(Boolean);
    if (s.kind !== 'chip') {
      cards.forEach((c) => { const st = document.createElement('span'); st.className = 'stamp'; st.textContent = s.stamp || '확정'; (c.querySelector('.cand-media') || c).appendChild(st); c.classList.add('is-stamped'); });
      await wait(460);
    }
    const flights = s.kind === 'chip'
      ? [fly(q('[data-confirm]'), slotEl('motion'), 0, `${state.sel.length}편`)]
      : cards.map((c, i) => { const cand = findCand(s, c.dataset.id); return fly(c.querySelector('.cand-media') || c, slotEl(s.slot || cand.chapter), i * 120); });
    await Promise.all(flights);
    state.choices[s.id] = [...state.sel];
    if (linked && s.gate === linked.gate) { finishLinked(s); return; }
    const filled = s.slot ? [s.slot] : state.sel.map((id) => findCand(s, id).chapter);
    renderSheet(filled);
    state.history.push(state.step);
    const prevStage = s.stage;
    state.step += 1;
    const nextStage = state.step < D.steps.length ? D.steps[state.step].stage : D.finaleStage;
    renderRail(nextStage !== prevStage ? prevStage : null);
    toast(s.doneText, true);
    await exitStage();
    if (state.step < D.steps.length) { renderStep(); enterStage(); }
    else finale();
    state.busy = false;
    document.body.classList.remove('is-busy');
  }

  async function regen() {
    const s = stepData();
    if (state.busy) return;
    state.busy = true;
    const n = state.tweaks.length;
    const agent = q('[data-agent]');
    agent.dataset.state = 'working';
    agent.innerHTML = agentHTML(`${s.agent}가 ${n ? `요청 ${n}개를 반영해 ` : ''}다시 만드는 중…`);
    const judge = q('[data-judge]'); if (judge) judge.classList.remove('is-on');
    state.sel = []; applySelection(); updateActions();
    const cards = qa('[data-cands] .cand');
    cards.forEach((c) => { c.classList.remove('is-developing'); c.classList.add('is-regen'); });
    await wait(300 + cards.length * 80);
    state.alt[s.id] = !state.alt[s.id];
    cards.forEach((c) => {
      const cand = findCand(s, c.dataset.id);
      if (!cand) return;
      const img = c.querySelector('img');
      if (img && cand.alt) img.src = imgOf(s, cand);
      const tt = c.querySelector('.cand-title'), dd = c.querySelector('.cand-body .cand-desc');
      if (tt) tt.textContent = titleOf(s, cand);
      if (dd) dd.textContent = descOf(s, cand);
    });
    await wait(320);
    cards.forEach((c) => { c.classList.remove('is-regen'); if (!reduce) c.classList.add('is-developing'); });
    setTimeout(() => cards.forEach((c) => c.classList.remove('is-developing')), 2000);
    await wait(700);
    agent.dataset.state = 'done';
    agent.innerHTML = agentHTML(n ? `요청 ${n}개를 반영한 새 후보가 도착했어요` : '새 후보가 도착했어요');
    state.tweaks = []; renderTweaks(s); updateActions();
    state.busy = false;
  }

  function toggleWrite(force) {
    const w = q('[data-write]'), wt = q('[data-write-toggle]');
    const open = force ?? !w.classList.contains('is-open');
    w.classList.toggle('is-open', open);
    wt.setAttribute('aria-expanded', String(open));
    wt.classList.toggle('is-active', open);
    if (open) setTimeout(() => { q('[data-write-input]').focus({ preventScroll: true }); w.scrollIntoView({ block: 'nearest', behavior: reduce ? 'auto' : 'smooth' }); }, 320);
  }

  function submitWrite() {
    const s = stepData();
    const input = q('[data-write-input]');
    const v = input.value.trim();
    if (!v) { input.focus(); return; }
    if (s.kind === 'text') {
      const id = 'custom-' + Date.now();
      (state.extra[s.id] = state.extra[s.id] || []).push({ id, custom: true, name: '직접 쓴 안', desc: v, tags: ['직접 작성'] });
      renderCands(false);
      const card = q(`[data-cands] .cand[data-id="${id}"]`);
      if (card && !reduce) card.classList.add('is-developing');
      toggle(id, true);
      toast('직접 쓴 안을 정리해 후보에 올렸어요');
    } else {
      const label = v.length > 16 ? v.slice(0, 16) + '…' : v;
      state.customTweaks.push(label); state.tweaks.push(label);
      renderTweaks(s); updateActions();
      toast('요청을 추가했어요 · 다시 만들기를 누르면 반영돼요');
    }
    input.value = '';
    toggleWrite(false);
  }

  async function undo() {
    if (state.busy || !state.history.length) return;
    const prev = state.history.pop();
    const s = D.steps[prev];
    const ids = state.choices[s.id] || [];
    D.steps.slice(prev).forEach((x) => delete state.choices[x.id]);
    closeFinale();
    state.step = prev;
    renderRail(); renderSheet();
    q('.toast')?.classList.remove('is-on');
    await exitStage();
    renderStep({ develop: false });
    state.sel = []; ids.forEach((id) => toggle(id, true, true)); updateActions();
    enterStage();
  }

  function finale() {
    const f = q('[data-finale]');
    const ch = state.choices, S = D.steps;
    const hero = ch.hero && findCand(ST('hero'), ch.hero[0]);
    const plan = ch.plan && findCand(ST('plan'), ch.plan[0]);
    const agent = q('[data-agent]');
    if (agent) { agent.dataset.state = 'working'; agent.innerHTML = agentHTML('Profiler가 상세 특질 시트를 쓰는 중…'); }
    if (!f) return;
    const img = q('[data-finale-img]', f);
    if (img) img.src = hero && !hero.custom ? imgOf(ST('hero'), hero) : (ch.frames && ch.frames.length ? findCand(ST('frames'), ch.frames[0]).img : '');
    setText('[data-finale-name]', plan ? (plan.name || '새 캐릭터') : '새 캐릭터');
    setText('[data-finale-tagline]', plan ? plan.desc : '');
    const stats = q('[data-finale-stats]', f);
    if (stats) {
      stats.innerHTML = [
        ['관문 통과', `${state.history.length}개`],
        ['완성 이미지', `${(ch.frames || []).length}장 승인`],
        ['움직임 영상', `${(ch.motion || []).length}편 대기`]
      ].map(([k, v]) => `<li><span>${k}</span><strong>${v}</strong></li>`).join('');
    }
    setText('[data-finale-next]', '다음 단계 · 페르소나. Profiler가 기획서로 상세 특질 시트를 쓰기 시작했어요.');
    const fr = q('[data-finale-frames]', f);
    if (fr) fr.innerHTML = (ch.frames || []).map((id, i) => { const c = findCand(ST('frames'), id); return `<span class="finale-frame" style="--i:${i}"><img src="${c.img}" alt="${esc(c.title)}"><em>${esc(c.title)}</em></span>`; }).join('');
    q('.toast')?.classList.remove('is-on');
    f.hidden = false;
    requestAnimationFrame(() => requestAnimationFrame(() => f.classList.add('is-open')));
    emit('factory:finale', {});
  }
  function closeFinale() { const f = q('[data-finale]'); if (f) { f.classList.remove('is-open'); f.hidden = true; } }

  function reset() {
    state = fresh();
    closeFinale();
    q('.toast')?.classList.remove('is-on');
    renderRail(); renderSheet(); renderStep(); enterStage();
    emit('factory:reset', {});
  }

  document.addEventListener('click', (e) => {
    const card = e.target.closest('[data-cands] .cand');
    if (card) { if (!state.busy) toggle(card.dataset.id); return; }
    const tw = e.target.closest('.tweak');
    if (tw) {
      const v = tw.textContent;
      state.tweaks = state.tweaks.includes(v) ? state.tweaks.filter((x) => x !== v) : [...state.tweaks, v];
      tw.setAttribute('aria-pressed', String(state.tweaks.includes(v)));
      updateActions();
      return;
    }
    const p = e.target.closest('[data-preset]');
    if (p) {
      const s = stepData(); const pr = s.presets[+p.dataset.preset];
      state.sel = [];
      (pr.all ? cands(s).map((c) => c.id) : pr.ids).forEach((id) => toggle(id, true, true));
      applySelection(); updateActions();
      qa('[data-preset]').forEach((x) => x.classList.toggle('is-active', x === p));
      return;
    }
    if (e.target.closest('[data-confirm]')) confirm();
    else if (e.target.closest('[data-regen]')) regen();
    else if (e.target.closest('[data-write-toggle]')) toggleWrite();
    else if (e.target.closest('[data-write-submit]')) submitWrite();
    else if (e.target.closest('[data-undo]')) undo();
    else if (e.target.closest('[data-reset]')) reset();
  });

  document.addEventListener('keydown', (e) => {
    if (e.target.matches('textarea, input')) {
      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); submitWrite(); }
      if (e.key === 'Escape') toggleWrite(false);
      return;
    }
    if (state.step >= D.steps.length || state.busy) return;
    const s = stepData();
    if (/^[1-9]$/.test(e.key) && s.kind !== 'chip') { const c = cands(s)[+e.key - 1]; if (c) toggle(c.id); }
    else if (e.key === 'Enter' && !e.target.closest('button')) confirm();
  });


  // 운영 현황의 결재 카드에서 ?gate=G1&run=...&back=... 로 들어온 경우
  const params = new URLSearchParams(location.search);
  const linked = params.get('gate') ? { gate: params.get('gate'), run: params.get('run') || '', back: params.get('back') || 'd-ops.html#job/seoha-new' } : null;
  function enterLinked() {
    const idx = D.steps.findIndex((x) => x.gate === linked.gate);
    if (idx < 0) return;
    state.step = idx;
    D.steps.slice(0, idx).forEach((x) => {
      state.choices[x.id] = x.select === 'single' ? [(x.candidates.find((c) => c.recommended) || x.candidates[0]).id] : (x.preselect || x.candidates.map((c) => c.id));
    });
    qa('[data-back-link]').forEach((a) => { a.href = linked.back; });
    const note = q('[data-linked-note]');
    if (note) { note.hidden = false; note.textContent = '결재 요청 · 관문 ' + linked.gate + ' · 고르면 들어온 화면으로 돌아가요'; }
  }
  function finishLinked(s) {
    renderSheet(s.slot ? [s.slot] : state.sel.map((id) => (findCand(s, id) || {}).chapter));
    try {
      const key = 'cf-approvals';
      const list = JSON.parse(localStorage.getItem(key) || '[]');
      list.push({ gate: linked.gate, run: linked.run, choice: [...state.sel], at: Date.now() });
      localStorage.setItem(key, JSON.stringify(list));
    } catch (e) { /* 저장소를 못 쓰면 돌아가기만 한다 */ }
    toast(s.doneText + ' · 운영 현황으로 돌아가요');
    setTimeout(() => { location.href = linked.back; }, reduce ? 200 : 1300);
  }

  function init() {
    qa('[data-icon]').forEach((e) => { e.outerHTML = icon(e.dataset.icon, e.className || 'ic'); });
    if (linked) enterLinked();
    renderRail(); renderSheet(); renderStep();
  }
  window.Factory = { icon, reset, state: () => state };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();

