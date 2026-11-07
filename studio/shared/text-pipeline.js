(function FACTORY_TEXT_PIPELINE(window) {
  'use strict';

  // 실제 텍스트 공정 설정과 저장 기록만 읽는다. 모델 호출·작업 시작·관문 승인은 하지 않는다.
  const MAX_CALLS = 50;
  const MAX_ARTIFACT_TEXT = 12000;
  const TONES = ['ok', 'warn', 'bad', 'active', 'muted'];
  const GATE_LABELS = { G3: '기획안 고르기', G6: '페르소나 승인', G7a: '표본 검수', G7: '표본 검수' };

  const esc = (value) => String(value == null ? '' : value).replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);

  const text = (value) => {
    if (typeof value !== 'string') return null;
    const trimmed = value.trim();
    return trimmed ? trimmed : null;
  };

  const plainObject = (value) => !!value && typeof value === 'object' && !Array.isArray(value);
  const array = (value) => (Array.isArray(value) ? value : []);

  function uniqueById(items) {
    const seen = new Set();
    return items.filter((item) => {
      if (!item || seen.has(item.id)) return false;
      seen.add(item.id);
      return true;
    });
  }

  function normalizeProfiles(value) {
    return uniqueById(array(value).map((entry) => {
      if (!plainObject(entry)) return null;
      const id = text(entry.id);
      if (!id) return null;
      return { id, label: text(entry.label) || id };
    }).filter(Boolean));
  }

  function normalizeRoutes(value) {
    return uniqueById(array(value).map((entry) => {
      if (!plainObject(entry)) return null;
      const id = text(entry.id);
      if (!id) return null;
      return {
        id,
        label: text(entry.label) || id,
        available: entry.available === true,
        reason: text(entry.reason) || '',
      };
    }).filter(Boolean));
  }

  function normalizeTasks(value) {
    return uniqueById(array(value).map((entry) => {
      if (!plainObject(entry)) return null;
      const id = text(entry.id);
      if (!id) return null;
      return {
        id,
        label: text(entry.label) || id,
        model: text(entry.model),
        reasoningEffort: text(entry.reasoningEffort),
      };
    }).filter(Boolean));
  }

  function normalizeConfig(raw) {
    if (!plainObject(raw)) throw new TypeError('텍스트 공정 설정 응답이 객체가 아닙니다.');
    const enabled = raw.enabled === true;
    const activeJobs = Number.isFinite(raw.activeJobs) && raw.activeJobs > 0 ? Math.floor(raw.activeJobs) : 0;
    return {
      enabled,
      profile: enabled ? text(raw.profile) : null,
      route: enabled ? text(raw.route) : null,
      completionCheck: text(raw.completionCheck),
      profiles: normalizeProfiles(raw.profiles),
      routes: normalizeRoutes(raw.routes),
      tasks: enabled ? normalizeTasks(raw.tasks) : [],
      activeJobs,
    };
  }

  function normalizeCharacters(raw) {
    if (!plainObject(raw)) return [];
    return uniqueById(array(raw.characters).map((entry) => {
      if (!plainObject(entry)) return null;
      const id = text(entry.id);
      if (!id) return null;
      return { id, name: text(entry.name) || id };
    }).filter(Boolean));
  }

  function normalizeStages(value) {
    return array(value).map((entry) => {
      if (!plainObject(entry)) return null;
      const id = text(entry.id);
      if (!id) return null;
      return { id, label: text(entry.label) || id, status: text(entry.status), revision: text(entry.revision) };
    }).filter(Boolean);
  }

  function normalizeGates(value) {
    return array(value).map((entry) => {
      if (!plainObject(entry)) return null;
      const id = text(entry.id);
      if (!id) return null;
      return { id, status: text(entry.status), revision: text(entry.revision) };
    }).filter(Boolean);
  }

  function normalizeCalls(value) {
    return array(value).slice(0, MAX_CALLS).map((entry) => {
      if (!plainObject(entry)) return null;
      return {
        task: text(entry.task),
        stage: text(entry.stage),
        model: text(entry.model),
        profile: text(entry.profile),
        route: text(entry.route),
        ok: typeof entry.ok === 'boolean' ? entry.ok : null,
        ref: text(entry.ref),
      };
    });
  }

  function normalizeArtifacts(value) {
    return array(value).map((entry) => {
      if (!plainObject(entry)) return null;
      const fullText = text(entry.text);
      return {
        label: text(entry.label) || '산출물',
        revision: text(entry.revision),
        text: fullText ? fullText.slice(0, MAX_ARTIFACT_TEXT) : null,
        textTruncated: entry.textTruncated === true || (!!fullText && fullText.length > MAX_ARTIFACT_TEXT),
        sourceModel: text(entry.sourceModel),
        sourceProfile: text(entry.sourceProfile),
        completionCheck: text(entry.completionCheck),
      };
    }).filter(Boolean);
  }

  function normalizeDetail(raw) {
    if (!plainObject(raw)) throw new TypeError('캐릭터 기록 응답이 객체가 아닙니다.');
    const characterId = text(raw.characterId);
    return {
      characterId,
      name: text(raw.name) || characterId || '캐릭터',
      stages: normalizeStages(raw.stages),
      gates: normalizeGates(raw.gates),
      calls: normalizeCalls(raw.calls).filter(Boolean),
      artifacts: normalizeArtifacts(raw.artifacts),
      workshopUrl: safeUrl(raw.workshopUrl),
    };
  }

  function modelLabel(id) {
    const value = text(id);
    if (!value) return '지정 안 됨';
    let rest = value.replace(/^google-antigravity\//i, '');
    let prefix = '';
    if (/^gpt[-_]/i.test(rest)) {
      prefix = 'GPT ';
      rest = rest.replace(/^gpt[-_]/i, '');
    }
    const words = rest.replace(/[-_/]+/g, ' ').replace(/\s+/g, ' ').trim()
      .split(' ').filter(Boolean).map((word) => {
        if (/^gpt$/i.test(word)) return 'GPT';
        return word.charAt(0).toUpperCase() + word.slice(1);
      });
    return `${prefix}${words.join(' ')}`.trim() || value;
  }

  function reasoningLabel(value) {
    const raw = text(value);
    if (!raw) return '기록 없음';
    const key = raw.toLowerCase();
    return ({ high: '높음', medium: '보통', low: '낮음', minimal: '최소', none: '없음' })[key] || raw;
  }

  function statusInfo(scope, value) {
    const raw = text(value);
    if (!raw) return { label: '기록 없음', tone: 'muted' };
    const key = raw.toUpperCase().replace(/[\s-]+/g, '_');
    if (key === 'APPROVED') return { label: scope === 'gate' ? '결재됨' : '승인', tone: 'ok' };
    if (['DONE', 'COMPLETED', 'COMPLETE'].includes(key)) return { label: scope === 'gate' ? '결재됨' : '완료', tone: 'ok' };
    if (['PENDING', 'AWAITING', 'WAITING', 'IN_REVIEW', 'REVIEW'].includes(key)) return { label: '결재 대기', tone: 'warn' };
    if (['REVISION', 'REVISION_REQUESTED', 'CHANGES_REQUESTED'].includes(key)) return { label: '수정 요청', tone: 'warn' };
    if (['RUNNING', 'IN_PROGRESS', 'WORKING', 'ACTIVE'].includes(key)) return { label: '작업 중', tone: 'active' };
    if (['FAILED', 'ERROR', 'ERRORED'].includes(key)) return { label: '실패', tone: 'bad' };
    if (['REJECTED', 'DENIED'].includes(key)) return { label: '반려', tone: 'bad' };
    if (['NOT_STARTED', 'IDLE', 'QUEUED', 'PENDING_START'].includes(key)) return { label: '시작 전', tone: 'muted' };
    if (key === 'SKIPPED') return { label: '건너뜀', tone: 'muted' };
    return { label: raw, tone: 'muted' };
  }

  function completionInfo(value) {
    const raw = text(value);
    if (!raw) return { label: '기록 없음', tone: 'muted' };
    if (raw.toUpperCase() === 'NOT_RUN') return { label: '최종 점검 전', tone: 'muted' };
    return { label: raw, tone: 'muted' };
  }

  function selectionPayload(current, next) {
    if (!plainObject(current) || !plainObject(next)) throw new TypeError('선택 값이 객체가 아닙니다.');
    const keys = Object.keys(next).filter((key) => next[key] !== undefined);
    if (keys.some((key) => key !== 'profile' && key !== 'route')) throw new TypeError('알 수 없는 선택 항목입니다.');
    const payload = {};
    for (const key of ['profile', 'route']) {
      if (!Object.prototype.hasOwnProperty.call(next, key) || next[key] === undefined) continue;
      const value = text(next[key]);
      if (!value) throw new TypeError('선택 값이 비어 있습니다.');
      if (current[key] !== value) payload[key] = value;
    }
    return Object.keys(payload).length ? payload : null;
  }

  function selectionLockReason(config, flags) {
    const options = plainObject(flags) ? flags : {};
    if (!plainObject(config)) return '설정을 아직 읽지 못했어요.';
    if (config.enabled !== true) return '텍스트 공정이 꺼져 있어 설정을 바꿀 수 없어요.';
    if (options.offline) return '연결이 끊겨 설정을 바꿀 수 없어요.';
    if (config.activeJobs > 0) return `실행 중인 작업 ${config.activeJobs}개가 끝난 뒤 바꿀 수 있어요.`;
    if (options.saving) return '설정을 바꾸는 중이에요.';
    return '';
  }

  function routeUnavailableReason(route) {
    if (!plainObject(route)) return '이 경로를 쓸 수 없어요.';
    if (route.available === true) return '';
    return text(route.reason) || '지금은 이 경로를 쓸 수 없어요.';
  }

  function createRequestGate() {
    const sequence = Object.create(null);
    const current = Object.create(null);
    return {
      next(kind) {
        if (typeof kind !== 'string' || !kind) throw new TypeError('요청 종류가 필요합니다.');
        const previous = current[kind];
        if (previous && typeof previous.abort === 'function') previous.abort();
        sequence[kind] = (sequence[kind] || 0) + 1;
        const controller = typeof AbortController === 'function' ? new AbortController() : { signal: undefined, abort() {} };
        current[kind] = controller;
        return { kind, seq: sequence[kind], controller };
      },
      isCurrent(token) {
        return !!token && sequence[token.kind] === token.seq && current[token.kind] === token.controller;
      },
      abort(kind) {
        const controller = current[kind];
        if (controller) {
          if (typeof controller.abort === 'function') controller.abort();
          current[kind] = null;
        }
      },
      abortAll() {
        Object.keys(current).forEach((kind) => this.abort(kind));
      },
    };
  }

  function safeUrl(value) {
    const url = text(value);
    if (!url || /[\s"'<>`\\]/.test(url) || /[\u0000-\u001f\u007f]/.test(url)) return null;
    if (url.startsWith('/') && !url.startsWith('//')) return url;
    if (/^https?:\/\/[^\s]+$/i.test(url)) return url;
    return null;
  }

  function normalizeApiBase(value) {
    const base = text(value);
    if (!base || base === '/') return '';
    if (base.startsWith('/') && !base.startsWith('//')) return base.replace(/\/+$/, '');
    if (/^https?:\/\/[^\s"'<>`\\]+$/i.test(base)) return base.replace(/\/+$/, '');
    return '';
  }

  function sourceCompare(config, sourceProfile) {
    if (!text(sourceProfile)) return { key: 'unknown', label: '프로필 기록 없음' };
    if (!plainObject(config) || !text(config.profile)) return { key: 'unknown', label: '지금 프로필을 알 수 없음' };
    if (sourceProfile === config.profile) return { key: 'same', label: '지금 프로필과 같음' };
    return { key: 'different', label: '다른 프로필' };
  }

  function createNoopController() {
    return {
      open: () => false, close: () => false, toggle: () => false, refresh: () => false,
      destroy() {}, get isOpen() { return false; },
    };
  }

  function mount(options) {
    const opts = plainObject(options) ? options : {};
    const root = opts.root;
    const canUseDom = typeof document !== 'undefined' && !!document && typeof document.createElement === 'function';
    if (!canUseDom || !root || typeof root.appendChild !== 'function') return createNoopController();
    if (root.__factoryTextPipeline && typeof root.__factoryTextPipeline.destroy === 'function') return root.__factoryTextPipeline;
    try {
      const controller = createPanel(root, normalizeApiBase(opts.apiBase));
      root.__factoryTextPipeline = controller;
      return controller;
    } catch (error) {
      return createNoopController();
    }
  }

  function createPanel(root, apiBase) {
    const state = {
      open: false, destroyed: false, apiBase,
      config: null, configFetching: false, configError: null, configLoaded: false,
      characters: [], charsFetching: false, charsError: null, charsLoaded: false,
      selectedId: null, detail: null, detailFetching: false, detailError: null,
      selecting: false, alert: '', returnFocus: null,
      networkOffline: typeof navigator !== 'undefined' && !!navigator && navigator.onLine === false,
    };
    const gate = createRequestGate();
    let selectionSequence = 0;

    const layer = document.createElement('div');
    layer.className = 'ftp-layer';
    layer.hidden = true;
    layer.setAttribute('data-text-pipeline-panel', '');
    layer.innerHTML = `
      <div class="ftp-backdrop" data-ftp-backdrop aria-hidden="true"></div>
      <section class="ftp-dialog" role="dialog" aria-modal="true" aria-labelledby="ftp-title" aria-describedby="ftp-desc" tabindex="-1" data-ftp-dialog>
        <header class="ftp-head">
          <div class="ftp-heading">
            <p class="ftp-kicker">실제 서버 자료</p>
            <h2 id="ftp-title">텍스트 공정</h2>
            <p class="ftp-desc" id="ftp-desc">프로필과 호출 경로를 고르고, 저장된 캐릭터 기록의 실제 출처를 확인해요. 모델은 실행하지 않아요.</p>
          </div>
          <button type="button" class="ftp-icon-btn" data-ftp-close aria-label="텍스트 공정 닫기"><span aria-hidden="true">×</span></button>
        </header>
        <div class="ftp-scroll" data-ftp-scroll>
          <div class="ftp-live ftp-sr-only" data-ftp-live role="status" aria-live="polite"></div>
          <div class="ftp-alert" data-ftp-alert role="alert"></div>
          <div class="ftp-offline-strip" data-ftp-offline hidden><span class="ftp-scope-mark" aria-hidden="true"></span>연결이 끊겨 마지막으로 읽은 내용을 보여 줘요. 연결되면 새로 읽어요.</div>
          <div class="ftp-scope">
            <span class="ftp-scope-mark" aria-hidden="true"></span>
            <p><b>실제 기록 패널</b> · 아래 설정과 기록은 서버에서 읽은 값이에요. 시뮬레이터의 시간·비용·진행은 각본이며, 이 패널의 기록과 섞이지 않아요.</p>
          </div>
          <div data-ftp-config></div>
          <div data-ftp-records></div>
        </div>
        <footer class="ftp-foot">
          <p>설정 전환과 실제 기록 읽기만 해요. 모델 호출·작업 시작·관문 승인은 하지 않아요.</p>
          <p class="ftp-foot-key"><kbd>Esc</kbd> 닫기</p>
        </footer>
      </section>`;
    root.appendChild(layer);
    root.removeAttribute('hidden');

    const dialog = layer.querySelector('[data-ftp-dialog]');
    const scroll = layer.querySelector('[data-ftp-scroll]');
    const configEl = layer.querySelector('[data-ftp-config]');
    const recordsEl = layer.querySelector('[data-ftp-records]');
    const liveEl = layer.querySelector('[data-ftp-live]');
    const alertEl = layer.querySelector('[data-ftp-alert]');
    const offlineStrip = layer.querySelector('[data-ftp-offline]');

    const isOffline = () => state.networkOffline || (typeof navigator !== 'undefined' && !!navigator && navigator.onLine === false);
    const apiUrl = (path) => `${state.apiBase}${path}`;
    const pad = (value) => String(value).padStart(2, '0');
    const initialOf = (name) => Array.from(String(name || '?').trim())[0] || '?';

    function setLive(message) {
      if (!liveEl || state.destroyed) return;
      liveEl.textContent = String(message || '');
    }

    function setAlert(message) {
      state.alert = message ? String(message) : '';
    }

    function labelFor(list, id, fallback) {
      if (!id) return fallback || '기록 없음';
      const found = array(list).find((item) => item && item.id === id);
      return found && found.label ? found.label : (fallback || id);
    }

    function statusPill(info) {
      const tone = TONES.includes(info && info.tone) ? info.tone : 'muted';
      return `<span class="ftp-pill ftp-pill--${tone}"><span class="ftp-pill-dot" aria-hidden="true"></span>${esc(info.label)}</span>`;
    }

    function tag(label, kind) {
      return `<span class="ftp-tag${kind ? ` ftp-tag--${kind}` : ''}">${esc(label)}</span>`;
    }

    function stateCard(options) {
      const opts = options || {};
      return `<div class="ftp-state ftp-state--${esc(opts.tone || 'muted')}">
        <span class="ftp-state-dot" aria-hidden="true"></span>
        <div class="ftp-state-body">
          <p class="ftp-state-title">${esc(opts.title || '')}</p>
          <p class="ftp-state-copy">${esc(opts.body || '')}</p>
          ${opts.action ? `<div class="ftp-state-actions">${opts.action}</div>` : ''}
        </div>
      </div>`;
    }

    function retryButton(attr, label) {
      return `<button type="button" class="ftp-btn" ${attr}>${esc(label)}</button>`;
    }

    function skeleton(rows) {
      return `<div class="ftp-skeleton" aria-hidden="true">${Array.from({ length: rows || 4 }, () => '<span class="ftp-skel-row"></span>').join('')}</div>`;
    }

    function errorCard(error, retryAttr, retryLabel) {
      const kind = error && error.kind;
      if (kind === 'offline' || kind === 'network') {
        return stateCard({
          tone: 'muted',
          title: '서버에 연결하지 못했어요.',
          body: '실제 설정과 기록은 서버가 있어야 볼 수 있어요. 연결되면 다시 읽고, 기록을 지어내 채우지 않아요.',
          action: retryButton(retryAttr || 'data-ftp-retry-config', retryLabel || '다시 연결'),
        });
      }
      const status = error && error.status ? `서버 응답 ${error.status}.` : '';
      return stateCard({
        tone: 'bad',
        title: '텍스트 공정 자료를 읽지 못했어요.',
        body: `${status} ${error && error.message ? error.message : '응답 형식을 확인하지 못했어요.'}`.trim(),
        action: retryButton(retryAttr || 'data-ftp-retry-config', retryLabel || '다시 불러오기'),
      });
    }

    function render() {
      if (state.destroyed) return;
      configEl.innerHTML = renderConfig();
      recordsEl.innerHTML = renderRecords();
      alertEl.textContent = state.alert;
      alertEl.hidden = !state.alert;
      offlineStrip.hidden = !(state.networkOffline && state.config);
      configEl.setAttribute('aria-busy', String(state.configFetching));
      recordsEl.setAttribute('aria-busy', String(state.charsFetching || state.detailFetching));
      scroll.setAttribute('aria-busy', String(state.configFetching || state.charsFetching || state.detailFetching));
    }

    function renderConfig() {
      if (!state.config) {
        if (state.configError) return `<section class="ftp-section">${errorCard(state.configError)}</section>`;
        return `<section class="ftp-section">${skeleton(5)}<p class="ftp-loading-line">설정을 불러오는 중이에요.</p></section>`;
      }
      if (!state.config.enabled) {
        return `<section class="ftp-section">
          <div class="ftp-section-head"><h3>텍스트 공정</h3></div>
          ${stateCard({
            tone: 'muted',
            title: '이 서버에서 텍스트 공정이 꺼져 있어요.',
            body: '프로필·호출 경로와 실제 기록을 읽을 수 없어요. 서버의 텍스트 공정 설정을 확인한 뒤 다시 불러와 주세요.',
            action: retryButton('data-ftp-retry-config', '다시 불러오기'),
          })}
        </section>`;
      }
      return `${renderSettings()}${renderRoles()}`;
    }

    function renderSettings() {
      const config = state.config;
      const lock = selectionLockReason(config, { saving: state.selecting, offline: isOffline() });
      const disabled = !!lock;
      const profileOptions = config.profiles.map((profile) => option({
        kind: 'profile', id: profile.id, label: profile.label,
        note: profile.id === config.profile ? '지금 쓰는 중' : '고르면 새 작업부터 적용해요.',
        checked: profile.id === config.profile, disabled,
      })).join('') || '<p class="ftp-empty-line">서버가 고를 수 있는 프로필을 주지 않았어요.</p>';
      const routeOptions = config.routes.map((route) => {
        const unavailable = routeUnavailableReason(route);
        return option({
          kind: 'route', id: route.id, label: route.label,
          note: unavailable ? `사용할 수 없어요 · ${unavailable}` : (route.id === config.route ? '지금 쓰는 중' : '연결 가능'),
          checked: route.id === config.route,
          disabled: disabled || !!unavailable,
          warning: !!unavailable,
        });
      }).join('') || '<p class="ftp-empty-line">서버가 고를 수 있는 호출 경로를 주지 않았어요.</p>';
      const completion = completionInfo(config.completionCheck);
      return `<section class="ftp-section ftp-section--settings" aria-labelledby="ftp-settings-head">
        <div class="ftp-section-head">
          <h3 id="ftp-settings-head">지금 설정</h3>
          <span class="ftp-meta">${state.configFetching ? '새로 고치는 중…' : '새 작업부터 적용'}</span>
        </div>
        ${state.configError ? `<div class="ftp-inline-warn">최신 설정을 읽지 못했어요. 마지막으로 읽은 값을 보여 주고 있어요. ${retryButton('data-ftp-retry-config', '다시 시도')}</div>` : ''}
        <div class="ftp-fields">
          <fieldset class="ftp-fieldset">
            <legend>모델 프로필</legend>
            <div class="ftp-options">${profileOptions}</div>
          </fieldset>
          <fieldset class="ftp-fieldset">
            <legend>호출 경로</legend>
            <div class="ftp-options">${routeOptions}</div>
          </fieldset>
        </div>
        ${lock ? `<p class="ftp-lock"><span class="ftp-lock-dot" aria-hidden="true"></span>${esc(lock)}</p>` : ''}
        <div class="ftp-check">
          <span class="ftp-check-key">최종 점검</span>
          ${statusPill(completion)}
          <span class="ftp-check-note">프로필 선택은 검증을 대신하지 않아요. 기록에 적힌 점검 값만 보여 줘요.</span>
        </div>
        <p class="ftp-fine">설정을 바꾸면 새 작업부터 적용되고, 이미 만든 자료의 출처 기록은 바뀌지 않아요.</p>
      </section>`;
    }

    function option(item) {
      const noteId = `ftp-${item.kind}-${String(item.id).replace(/[^a-zA-Z0-9_-]/g, '-')}-note`;
      return `<label class="ftp-option${item.checked ? ' is-on' : ''}${item.disabled ? ' is-disabled' : ''}">
        <input type="radio" name="ftp-${item.kind}" value="${esc(item.id)}" data-ftp-kind="${esc(item.kind)}" ${item.checked ? 'checked' : ''} ${item.disabled ? 'disabled' : ''} aria-describedby="${esc(noteId)}">
        <span class="ftp-radio" aria-hidden="true"></span>
        <span class="ftp-option-text">
          <span class="ftp-option-label">${esc(item.label)}</span>
          <span class="ftp-option-note${item.warning ? ' is-warning' : ''}" id="${esc(noteId)}">${esc(item.note)}</span>
        </span>
      </label>`;
    }

    function renderRoles() {
      const tasks = state.config.tasks;
      const countLabel = tasks.length === 9 ? '9개 역할' : `${tasks.length}개 역할`;
      const rows = tasks.map((task, index) => `<li class="ftp-role">
        <span class="ftp-role-num" aria-hidden="true">${pad(index + 1)}</span>
        <div class="ftp-role-body">
          <div class="ftp-role-line">
            <span class="ftp-role-label">${esc(task.label)}</span>
            <span class="ftp-role-model">${esc(modelLabel(task.model))}</span>
          </div>
          <details class="ftp-disclosure">
            <summary>모델 상세</summary>
            <dl class="ftp-dl">
              <div><dt>모델 ID</dt><dd><code>${esc(task.model || '기록 없음')}</code></dd></div>
              <div><dt>추론 강도</dt><dd>${esc(reasoningLabel(task.reasoningEffort))}</dd></div>
              <div><dt>역할 ID</dt><dd><code>${esc(task.id)}</code></dd></div>
            </dl>
          </details>
        </div>
      </li>`).join('');
      return `<section class="ftp-section ftp-section--roles" aria-labelledby="ftp-roles-head">
        <div class="ftp-section-head">
          <h3 id="ftp-roles-head">역할별 모델</h3>
          <span class="ftp-meta">${esc(countLabel)}</span>
        </div>
        ${tasks.length ? `<ol class="ftp-roles">${rows}</ol>` : '<p class="ftp-empty-line">역할 목록이 비어 있어요. 서버의 모델 덱 설정을 확인해 주세요.</p>'}
        <p class="ftp-fine">모델은 역할별로 정해져 있어요. 상세 ID와 추론 강도는 각 역할의 ‘모델 상세’에서 확인해요.</p>
      </section>`;
    }

    function renderRecords() {
      if (!state.config) {
        if (state.configError) return '<section class="ftp-section"><p class="ftp-empty-line">설정을 읽은 뒤 실제 기록을 불러와요.</p></section>';
        return `<section class="ftp-section">${skeleton(3)}<p class="ftp-loading-line">설정을 읽은 뒤 실제 기록을 불러와요.</p></section>`;
      }
      if (!state.config.enabled) {
        return '<section class="ftp-section"><p class="ftp-empty-line">텍스트 공정이 꺼져 있어 실제 캐릭터 기록도 읽지 않았어요.</p></section>';
      }
      return `<section class="ftp-section ftp-section--records" aria-labelledby="ftp-records-head">
        <div class="ftp-section-head">
          <h3 id="ftp-records-head">실제 캐릭터 기록</h3>
          <span class="ftp-meta">${state.characters.length ? `${state.characters.length}명` : '저장된 기록'}</span>
        </div>
        <p class="ftp-section-note">서버에 저장된 단계·관문·호출·산출물만 보여 줘요. 자료를 만든 모델과 프로필은 지금 설정과 따로 표시해요.</p>
        ${renderCharacters()}
      </section>`;
    }

    function renderCharacters() {
      if (state.charsError && !state.characters.length) return errorCard(state.charsError, 'data-ftp-retry-chars', '기록 다시 불러오기');
      if (state.charsFetching && !state.charsLoaded) return `${skeleton(3)}<p class="ftp-loading-line">캐릭터 목록을 불러오는 중이에요.</p>`;
      if (state.charsError && state.characters.length) {
        return `<div class="ftp-inline-warn">최신 캐릭터 목록을 읽지 못했어요. 마지막으로 읽은 목록을 보여 줘요. ${retryButton('data-ftp-retry-chars', '다시 시도')}</div>${renderPicker()}`;
      }
      if (!state.characters.length) {
        return stateCard({
          tone: 'muted',
          title: '저장된 캐릭터가 아직 없어요.',
          body: '이 서버에 실제 캐릭터 기록이 생기면 여기에서 단계·관문·호출·산출물 출처를 볼 수 있어요.',
          action: retryButton('data-ftp-retry-chars', '다시 확인'),
        });
      }
      return `${renderPicker()}${renderDetail()}`;
    }

    function renderPicker() {
      const buttons = state.characters.map((character) => `<button type="button" class="ftp-char${state.selectedId === character.id ? ' is-on' : ''}" data-ftp-char="${esc(character.id)}" aria-pressed="${state.selectedId === character.id}">
        <span class="ftp-char-av" aria-hidden="true">${esc(initialOf(character.name))}</span>
        <span class="ftp-char-name">${esc(character.name)}</span>
        <code>${esc(character.id)}</code>
      </button>`).join('');
      return `<div class="ftp-picker" role="group" aria-label="캐릭터 선택">${buttons}</div>`;
    }

    function renderDetail() {
      if (!state.selectedId) {
        return '<p class="ftp-picker-hint">캐릭터를 고르면 실제 단계·관문·최근 호출과 산출물의 출처를 보여 줘요.</p>';
      }
      const character = state.characters.find((item) => item.id === state.selectedId);
      const name = character ? character.name : state.selectedId;
      if (state.detailError) {
        return `<div class="ftp-record-load"><p class="ftp-record-load-title">${esc(name)} 기록을 읽지 못했어요.</p>${errorCard(state.detailError, 'data-ftp-retry-detail', '이 캐릭터 다시 불러오기')}</div>`;
      }
      if (!state.detail) {
        return `<div class="ftp-record-load">${skeleton(4)}<p class="ftp-loading-line">${esc(name)}의 실제 기록을 불러오는 중이에요.</p></div>`;
      }
      return renderRecord(state.detail);
    }

    function renderRecord(detail) {
      const config = state.config;
      const profileNow = config.profile ? labelFor(config.profiles, config.profile) : '선택 없음';
      const routeNow = config.route ? labelFor(config.routes, config.route) : '선택 없음';
      const workshop = detail.workshopUrl
        ? `<a class="ftp-btn ftp-btn--quiet" href="${esc(detail.workshopUrl)}" target="_blank" rel="noopener noreferrer">기존 워크숍에서 열기<span aria-hidden="true"> ↗</span></a>`
        : '<span class="ftp-missing">워크숍 주소가 기록에 없어요.</span>';
      return `<article class="ftp-record" aria-labelledby="ftp-record-name">
        <header class="ftp-record-head">
          <span class="ftp-record-av" aria-hidden="true">${esc(initialOf(detail.name))}</span>
          <div class="ftp-record-id"><h4 id="ftp-record-name">${esc(detail.name)}</h4><code>${esc(detail.characterId || state.selectedId)}</code></div>
          <div class="ftp-record-action">${workshop}</div>
        </header>
        <div class="ftp-now">
          <span class="ftp-now-key">지금 설정</span>
          <span class="ftp-now-value">${esc(profileNow)} · ${esc(routeNow)}</span>
          <span class="ftp-now-note">아래 자료의 출처는 이 설정과 다를 수 있어요.</span>
        </div>
        <div class="ftp-fact-grid">
          ${renderFacts('단계', detail.stages, 'stage')}
          ${renderFacts('관문', detail.gates, 'gate')}
        </div>
        ${renderCalls(detail.calls)}
        ${renderArtifacts(detail.artifacts)}
        <p class="ftp-record-footnote">이 패널은 기록을 읽기만 해요. 작업 시작과 관문 승인은 기존 워크숍에서 해요.</p>
      </article>`;
    }

    function renderFacts(title, items, scope) {
      if (!items.length) {
        return `<section class="ftp-sub" aria-label="${esc(title)}"><div class="ftp-sub-head"><h5>${esc(title)}</h5><span class="ftp-meta">0</span></div><p class="ftp-empty-line">${esc(title)} 기록이 없어요.</p></section>`;
      }
      const rows = items.map((item) => {
        const info = statusInfo(scope, item.status);
        const name = item.label || (scope === 'gate' && GATE_LABELS[item.id]) || item.id;
        return `<li class="ftp-fact">
          <span class="ftp-fact-name">${esc(name)} <code>${esc(item.id)}</code></span>
          <span class="ftp-fact-meta">${item.revision ? `<code>${esc(item.revision)}</code>` : '<span class="ftp-missing">revision 없음</span>'}</span>
          ${statusPill(info)}
        </li>`;
      }).join('');
      return `<section class="ftp-sub" aria-label="${esc(title)}"><div class="ftp-sub-head"><h5>${esc(title)}</h5><span class="ftp-meta">${items.length}</span></div><ul class="ftp-facts">${rows}</ul></section>`;
    }

    function renderCalls(calls) {
      if (!calls.length) return '<section class="ftp-sub"><div class="ftp-sub-head"><h5>최근 호출</h5><span class="ftp-meta">0</span></div><p class="ftp-empty-line">최근 호출 기록이 없어요.</p></section>';
      const config = state.config;
      const rows = calls.map((call) => {
        const taskLabel = call.task ? labelFor(config.tasks, call.task, call.task) : '기록 없음';
        const stageLabel = call.stage ? labelFor(state.detail && state.detail.stages, call.stage, call.stage) : '기록 없음';
        const result = call.ok === true
          ? '<span class="ftp-pill ftp-pill--ok"><span class="ftp-pill-dot" aria-hidden="true"></span>성공</span>'
          : call.ok === false
            ? '<span class="ftp-pill ftp-pill--bad"><span class="ftp-pill-dot" aria-hidden="true"></span>실패</span>'
            : '<span class="ftp-missing">기록 없음</span>';
        const profileDiff = call.profile && config.profile && call.profile !== config.profile ? tag('지금과 다름') : '';
        const routeDiff = call.route && config.route && call.route !== config.route ? tag('지금과 다름') : '';
        return `<tr>
          <td>${esc(taskLabel)}</td>
          <td>${esc(stageLabel)}</td>
          <td><code>${esc(call.model || '없음')}</code></td>
          <td><code>${esc(call.profile || '없음')}</code>${profileDiff}</td>
          <td><code>${esc(call.route || '없음')}</code>${routeDiff}</td>
          <td>${result}</td>
          <td><code>${esc(call.ref || '없음')}</code></td>
        </tr>`;
      }).join('');
      return `<section class="ftp-sub">
        <div class="ftp-sub-head"><h5>최근 호출</h5><span class="ftp-meta">최근 ${calls.length}건</span></div>
        <div class="ftp-tablewrap">
          <table class="ftp-table">
            <thead><tr><th>역할</th><th>단계</th><th>모델</th><th>프로필</th><th>경로</th><th>결과</th><th>참조</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </section>`;
    }

    function renderArtifacts(artifacts) {
      if (!artifacts.length) return '<section class="ftp-sub"><div class="ftp-sub-head"><h5>산출물 출처</h5><span class="ftp-meta">0</span></div><p class="ftp-empty-line">산출물 기록이 없어요.</p></section>';
      const cards = artifacts.map((artifact) => {
        const completion = completionInfo(artifact.completionCheck);
        const compare = sourceCompare(state.config, artifact.sourceProfile);
        return `<article class="ftp-artifact">
          <div class="ftp-artifact-head">
            <div class="ftp-artifact-title"><h6>${esc(artifact.label)}</h6><code>${esc(artifact.revision || 'revision 없음')}</code></div>
            ${statusPill(completion)}
          </div>
          <dl class="ftp-source">
            <div><dt>만든 모델</dt><dd>${artifact.sourceModel ? `<code>${esc(artifact.sourceModel)}</code>` : '<span class="ftp-missing">기록 없음</span>'}</dd></div>
            <div><dt>만든 프로필</dt><dd>${artifact.sourceProfile ? `<code>${esc(artifact.sourceProfile)}</code> ${tag(compare.label, compare.key)}` : '<span class="ftp-missing">기록 없음</span>'}</dd></div>
          </dl>
          ${artifact.text
            ? `<details class="ftp-artifact-body"><summary>본문 펼치기</summary><pre>${esc(artifact.text)}</pre>${artifact.textTruncated ? '<p class="ftp-fine">본문이 길어 일부만 표시해요.</p>' : ''}</details>`
            : '<p class="ftp-empty-line">저장된 본문이 없어요.</p>'}
        </article>`;
      }).join('');
      return `<section class="ftp-sub">
        <div class="ftp-sub-head"><h5>산출물 출처</h5><span class="ftp-meta">${artifacts.length}건</span></div>
        <p class="ftp-sub-note">자료마다 기록된 모델·프로필을 그대로 보여 줘요. 지금 설정으로 출처를 채우지 않아요.</p>
        ${cards}
      </section>`;
    }

    async function fetchJSON(path, init) {
      if (typeof fetch !== 'function') {
        const error = new Error('이 브라우저에서 서버에 연결할 수 없어요.');
        error.kind = 'offline';
        throw error;
      }
      if (isOffline()) {
        const error = new Error('연결이 끊겼어요.');
        error.kind = 'offline';
        throw error;
      }
      const request = init || {};
      const headers = { Accept: 'application/json' };
      if (request.body) headers['Content-Type'] = 'application/json';
      const response = await fetch(apiUrl(path), {
        method: request.method || 'GET',
        headers,
        body: request.body,
        signal: request.signal,
        credentials: 'same-origin',
        cache: 'no-store',
      });
      if (!response.ok) {
        let detail = '';
        try {
          const body = await response.json();
          detail = text(body && (body.detail || body.message || body.error)) || '';
        } catch (ignored) { detail = ''; }
        const error = new Error(detail.slice(0, 240) || '서버가 요청을 거절했어요.');
        error.status = response.status;
        throw error;
      }
      try {
        return await response.json();
      } catch (cause) {
        const error = new Error('응답 형식을 읽지 못했어요.');
        error.kind = 'shape';
        throw error;
      }
    }

    function classifyError(error) {
      if (error && error.name === 'AbortError') return { kind: 'abort' };
      if (error && (error.kind === 'shape' || error.kind === 'offline' || error.kind === 'network')) {
        return { kind: error.kind, status: error.status || 0, message: error.message };
      }
      if (isOffline()) return { kind: 'offline', status: 0, message: '연결이 끊겼어요.' };
      return { kind: 'network', status: error && error.status ? error.status : 0, message: (error && error.message) || '서버에 연결하지 못했어요.' };
    }

    async function loadConfig() {
      if (state.destroyed || state.selecting) return;
      const token = gate.next('config');
      state.configFetching = true;
      state.configError = null;
      setAlert('');
      render();
      try {
        const raw = await fetchJSON('/api/text-pipeline', { signal: token.controller.signal });
        if (!gate.isCurrent(token) || state.destroyed) return;
        const config = normalizeConfig(raw);
        state.config = config;
        state.configLoaded = true;
        state.configFetching = false;
        state.configError = null;
        render();
        if (config.enabled) {
          loadCharacters();
        } else {
          gate.abort('characters');
          gate.abort('detail');
          state.charsFetching = false;
          state.detailFetching = false;
          state.charsError = null;
          state.detailError = null;
          state.characters = [];
          state.charsLoaded = false;
          state.selectedId = null;
          state.detail = null;
          render();
        }
      } catch (error) {
        if (!gate.isCurrent(token) || state.destroyed) return;
        const classified = classifyError(error);
        if (classified.kind === 'abort') return;
        state.configFetching = false;
        state.configError = classified;
        render();
        if (classified.kind === 'offline') setLive('서버에 연결하지 못했어요. 다시 연결해 주세요.');
        else setLive('텍스트 공정 설정을 읽지 못했어요.');
      }
    }

    async function loadCharacters() {
      if (state.destroyed) return;
      if (!state.config || !state.config.enabled) return;
      const token = gate.next('characters');
      state.charsFetching = true;
      state.charsError = null;
      render();
      try {
        const raw = await fetchJSON('/api/text-pipeline/characters', { signal: token.controller.signal });
        if (!gate.isCurrent(token) || state.destroyed) return;
        const characters = normalizeCharacters(raw);
        state.characters = characters;
        state.charsLoaded = true;
        state.charsFetching = false;
        state.charsError = null;
        if (state.selectedId && !characters.some((item) => item.id === state.selectedId)) {
          state.selectedId = null;
          state.detail = null;
          state.detailError = null;
        }
        render();
        if (state.selectedId) loadDetail(state.selectedId);
      } catch (error) {
        if (!gate.isCurrent(token) || state.destroyed) return;
        const classified = classifyError(error);
        if (classified.kind === 'abort') return;
        state.charsFetching = false;
        state.charsError = classified;
        render();
      }
    }

    async function loadDetail(characterId) {
      if (state.destroyed || !characterId) return;
      const token = gate.next('detail');
      state.detailFetching = true;
      state.detailError = null;
      state.detail = null;
      render();
      try {
        const raw = await fetchJSON(`/api/text-pipeline/characters/${encodeURIComponent(characterId)}`, { signal: token.controller.signal });
        if (!gate.isCurrent(token) || state.destroyed || state.selectedId !== characterId) return;
        const detail = normalizeDetail(raw);
        state.detail = detail;
        state.detailFetching = false;
        state.detailError = null;
        render();
        focusCharacter(characterId);
      } catch (error) {
        if (!gate.isCurrent(token) || state.destroyed || state.selectedId !== characterId) return;
        const classified = classifyError(error);
        if (classified.kind === 'abort') return;
        state.detailFetching = false;
        state.detailError = classified;
        state.detail = null;
        render();
        focusCharacter(characterId);
      }
    }

    function focusChoice(kind) {
      if (!state.open) return;
      const input = configEl.querySelector(`input[data-ftp-kind="${kind}"]:checked`);
      if (input && !input.disabled) input.focus({ preventScroll: true });
    }

    function focusCharacter(characterId) {
      if (!state.open) return;
      const active = document.activeElement;
      if (active && active !== document.body && dialog.contains(active)) return;
      const button = Array.from(recordsEl.querySelectorAll('[data-ftp-char]'))
        .find((item) => item.getAttribute('data-ftp-char') === characterId);
      if (button) button.focus({ preventScroll: true });
    }

    async function commitSelection(kind, id) {
      if (kind !== 'profile' && kind !== 'route') return;
      if (state.selecting || !state.config || !state.config.enabled) return;
      if (isOffline()) {
        setAlert('연결이 끊겨 설정을 바꾸지 않았어요. 이전 선택을 그대로 두었어요.');
        render();
        return;
      }
      const lock = selectionLockReason(state.config, { saving: false, offline: false });
      if (lock) {
        setAlert(lock);
        render();
        return;
      }
      let payload;
      try {
        payload = selectionPayload(state.config, { [kind]: id });
      } catch (error) {
        setAlert('알 수 없는 선택이에요. 이전 선택을 그대로 두었어요.');
        render();
        return;
      }
      if (!payload) return;
      const kindLabel = kind === 'profile' ? '모델 프로필' : '호출 경로';
      const oldId = state.config[kind];
      const oldLabel = labelFor(kind === 'profile' ? state.config.profiles : state.config.routes, oldId, oldId || '선택 없음');
      const newLabel = labelFor(kind === 'profile' ? state.config.profiles : state.config.routes, id, id);
      const sequence = ++selectionSequence;
      // 새 설정을 저장하는 동안 이전 설정 새로 고침이 늦게 도착해 선택을 덮지 않게 한다.
      gate.abort('config');
      state.configFetching = false;
      state.selecting = true;
      setAlert('');
      render();
      dialog.focus({ preventScroll: true });
      setLive(`${kindLabel}을 ${newLabel}(으)로 바꾸는 중이에요.`);
      try {
        const raw = await fetchJSON('/api/text-pipeline/selection', { method: 'POST', body: JSON.stringify(payload) });
        if (state.destroyed || sequence !== selectionSequence) return;
        let next;
        try {
          next = normalizeConfig(raw);
        } catch (shapeError) {
          shapeError.kind = 'shape';
          throw shapeError;
        }
        state.config = next;
        state.selecting = false;
        state.configError = null;
        if (!next.enabled) {
          gate.abort('characters');
          gate.abort('detail');
          state.charsFetching = false;
          state.detailFetching = false;
          state.charsError = null;
          state.detailError = null;
          state.characters = [];
          state.charsLoaded = false;
          state.selectedId = null;
          state.detail = null;
        }
        render();
        focusChoice(kind);
        const applied = labelFor(kind === 'profile' ? next.profiles : next.routes, next[kind], next[kind] || '선택 없음');
        setLive(`${kindLabel}이 ${applied}(으)로 바뀌었어요. 새 작업부터 적용돼요.`);
      } catch (error) {
        if (state.destroyed || sequence !== selectionSequence) return;
        state.selecting = false;
        const status = error && error.status ? ` 서버 응답 ${error.status}.` : '';
        setAlert(`${kindLabel}을 바꾸지 못했어요. 이전 선택(${oldLabel})을 그대로 두었어요.${status}`);
        render();
        focusChoice(kind);
        setLive(`${kindLabel}을 바꾸지 못해 이전 선택을 그대로 두었어요.`);
      }
    }

    function selectCharacter(id) {
      if (state.destroyed || typeof id !== 'string' || !id) return;
      if (state.selectedId === id && state.detail) return;
      state.selectedId = id;
      state.detail = null;
      state.detailError = null;
      loadDetail(id);
      focusCharacter(id);
    }

    function setBackgroundInert(on) {
      if (!document.body) return;
      if (!on) {
        document.querySelectorAll('[data-ftp-inert]').forEach((element) => {
          element.removeAttribute('inert');
          element.removeAttribute('data-ftp-inert');
        });
        return;
      }
      let node = layer;
      while (node && node.parentElement && node !== document.body) {
        const parent = node.parentElement;
        Array.from(parent.children).forEach((element) => {
          if (element === node || element.hasAttribute('inert')) return;
          element.setAttribute('inert', '');
          element.setAttribute('data-ftp-inert', '');
        });
        node = parent;
      }
    }

    function focusable() {
      const nodes = dialog.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex]:not([tabindex="-1"])');
      return Array.from(nodes).filter((element) => !element.hidden && !element.closest('[hidden]') && element.type !== 'hidden' && (element.offsetWidth || element.offsetHeight || element.getClientRects().length));
    }

    function onKeydown(event) {
      if (!state.open) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        close();
        return;
      }
      if (event.key !== 'Tab') return;
      const items = focusable();
      if (!items.length) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (event.shiftKey) {
        if (active === dialog || !dialog.contains(active) || active === first) {
          event.preventDefault();
          last.focus();
        }
      } else if (active === dialog || !dialog.contains(active) || active === last) {
        event.preventDefault();
        first.focus();
      }
    }

    function open() {
      if (state.destroyed) return false;
      if (state.open) return true;
      state.open = true;
      state.returnFocus = document.activeElement && typeof document.activeElement.focus === 'function' ? document.activeElement : null;
      state.alert = '';
      layer.hidden = false;
      if (document.body) document.body.classList.add('ftp-body-lock');
      setBackgroundInert(true);
      render();
      dialog.focus({ preventScroll: true });
      loadConfig();
      return true;
    }

    function close() {
      if (state.destroyed || !state.open) return false;
      const active = document.activeElement;
      state.open = false;
      layer.hidden = true;
      if (document.body) document.body.classList.remove('ftp-body-lock');
      setBackgroundInert(false);
      const target = state.returnFocus;
      state.returnFocus = null;
      if (target && target.isConnected && typeof target.focus === 'function' && (dialog.contains(active) || active === document.body || !active)) {
        target.focus({ preventScroll: true });
      }
      return true;
    }

    function destroy() {
      if (state.destroyed) return;
      if (state.open) close();
      state.destroyed = true;
      gate.abortAll();
      layer.removeEventListener('keydown', onKeydown);
      layer.removeEventListener('click', onClick);
      configEl.removeEventListener('change', onChange);
      recordsEl.removeEventListener('click', onRecordsClick);
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
      layer.remove();
      delete root.__factoryTextPipeline;
      if (document.body) document.body.classList.remove('ftp-body-lock');
      setBackgroundInert(false);
    }

    function onClick(event) {
      if (event.target.closest('[data-ftp-close]')) {
        close();
        return;
      }
      if (event.target.hasAttribute && event.target.hasAttribute('data-ftp-backdrop')) close();
    }

    function onChange(event) {
      const input = event.target.closest('input[data-ftp-kind]');
      if (!input) return;
      commitSelection(input.getAttribute('data-ftp-kind'), input.value);
    }

    function onRecordsClick(event) {
      const target = event.target.closest ? event.target.closest('[data-ftp-char], [data-ftp-retry-chars], [data-ftp-retry-detail]') : null;
      if (!target) return;
      if (target.hasAttribute('data-ftp-char')) {
        selectCharacter(target.getAttribute('data-ftp-char'));
        return;
      }
      if (target.hasAttribute('data-ftp-retry-chars')) {
        loadCharacters();
        return;
      }
      if (target.hasAttribute('data-ftp-retry-detail') && state.selectedId) loadDetail(state.selectedId);
    }

    function onConfigClick(event) {
      if (event.target.closest('[data-ftp-retry-config]')) loadConfig();
    }

    function onOnline() {
      state.networkOffline = false;
      if (!state.open || state.destroyed) {
        render();
        return;
      }
      if (state.selecting) return;
      setLive('다시 연결됐어요. 최신 설정과 기록을 읽어요.');
      loadConfig();
    }

    function onOffline() {
      state.networkOffline = true;
      if (state.open) {
        render();
        setLive('연결이 끊겼어요. 마지막으로 읽은 내용을 보여 줘요.');
      }
    }

    layer.addEventListener('keydown', onKeydown);
    layer.addEventListener('click', onClick);
    configEl.addEventListener('click', onConfigClick);
    configEl.addEventListener('change', onChange);
    recordsEl.addEventListener('click', onRecordsClick);
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);

    return {
      open,
      close,
      toggle() { return state.open ? close() : open(); },
      refresh() {
        if (!state.open) return false;
        loadConfig();
        return true;
      },
      destroy,
      get isOpen() { return state.open; },
      get element() { return layer; },
    };
  }

  window.FactoryTextPipeline = {
    mount,
    version: '1.0.0',
    internals: {
      normalizeConfig,
      normalizeCharacters,
      normalizeDetail,
      modelLabel,
      reasoningLabel,
      statusInfo,
      completionInfo,
      selectionPayload,
      selectionLockReason,
      routeUnavailableReason,
      createRequestGate,
      safeUrl,
      normalizeApiBase,
      sourceCompare,
    },
  };
})(typeof window !== 'undefined' ? window : globalThis);
