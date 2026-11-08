(function (global) {
  'use strict';

  // 이 파일은 실제 서버 기록만 읽는다. 시연 상태·가짜 진행·가짜 비용은 만들지 않는다.
  const UNKNOWN = '미집계';
  const STAGE_META = {
    queued: ['대기', 'muted'],
    running: ['실행 중', 'active'],
    done: ['승인', 'ok'],
    failed: ['실패', 'bad'],
    gate: ['사람 확인', 'warn'],
    skipped: ['건너뜀', 'muted'],
    unknown: ['상태 없음', 'muted']
  };
  const JOB_META = {
    queued: ['대기열', 'muted'],
    running: ['실행 중', 'active'],
    succeeded: ['성공 · 작업 1건', 'ok'],
    failed: ['실패', 'bad'],
    cancelled: ['취소됨', 'muted'],
    unknown: ['상태 없음', 'muted']
  };

  function text(value) {
    return value == null ? '' : String(value);
  }

  function array(value) {
    return Array.isArray(value) ? value : [];
  }

  function object(value) {
    return value && typeof value === 'object' && !Array.isArray(value) ? value : null;
  }

  function unique(values) {
    const seen = new Set();
    return values.filter((value) => {
      if (!value || seen.has(value)) return false;
      seen.add(value);
      return true;
    });
  }

  function escapeHTML(value) {
    return text(value).replace(/[&<>"']/g, (character) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[character]);
  }

  function safeHref(value) {
    const string = text(value).trim();
    if (!string) return '';
    return /^(https?:\/\/|\/(?!\/)|#|\.{0,2}\/(?!\/))/i.test(string) ? string : '';
  }

  function safeDecode(value) {
    try {
      return decodeURIComponent(value);
    } catch (error) {
      return value;
    }
  }

  function statusOf(value) {
    if (value && typeof value === 'object') {
      return text(value.status || value.state || value.State).trim();
    }
    return text(value).trim();
  }

  function stateForStatus(raw) {
    const key = text(raw).trim().toUpperCase().replace(/[\s-]+/g, '_');
    if (!key) return 'unknown';
    if (['APPROVED', 'DONE', 'SUCCEEDED', 'COMPLETED', 'COMPLETE', 'PASSED', 'FINISHED'].includes(key)) return 'done';
    if (['RUNNING', 'IN_PROGRESS', 'ACTIVE', 'WORKING', 'STARTED'].includes(key)) return 'running';
    if (['CHECK_FAILED', 'FAILED', 'ERROR', 'REJECTED', 'TIMED_OUT', 'BLOCKED'].includes(key)) return 'failed';
    if (['AWAITING_HUMAN', 'NEEDS_HUMAN', 'WAITING_HUMAN', 'HUMAN', 'GATE'].includes(key)) return 'gate';
    if (['PENDING', 'QUEUED', 'NOT_STARTED', 'READY', 'IDLE', 'WAITING'].includes(key)) return 'queued';
    if (key === 'SKIPPED') return 'skipped';
    return 'unknown';
  }

  function gateState(raw) {
    const key = text(raw).trim().toUpperCase().replace(/[\s-]+/g, '_');
    if (!key) return 'unknown';
    if (key === 'AWAITING_HUMAN' || key === 'NEEDS_HUMAN' || key === 'WAITING_HUMAN') return 'pending';
    if (key === 'PENDING' || key === 'WAITING') return 'waiting';
    if (key === 'APPROVED' || key === 'DONE') return 'approved';
    if (key === 'REJECTED' || key === 'CHECK_FAILED' || key === 'FAILED') return 'rejected';
    if (key === 'RUNNING' || key === 'IN_PROGRESS') return 'running';
    if (key === 'SKIPPED') return 'skipped';
    return 'unknown';
  }

  function stageRecord(stages, id) {
    if (Array.isArray(stages)) {
      return stages.find((entry) => entry && text(entry.id || entry.stage) === id) || null;
    }
    const map = object(stages);
    return map ? map[id] || null : null;
  }

  function translateStage(raw, definition) {
    const record = raw && typeof raw === 'object' ? raw : { status: raw };
    const definitionObject = definition && typeof definition === 'object' ? definition : {};
    const rawStatus = statusOf(record).toUpperCase();
    const state = stateForStatus(rawStatus);
    const meta = STAGE_META[state] || STAGE_META.unknown;
    const result = {
      id: text(definitionObject.id || record.id || record.stage),
      name: text(definitionObject.name || definitionObject.id || record.name || '단계'),
      state,
      status: rawStatus,
      raw: rawStatus,
      label: meta[0],
      tone: meta[1],
      progress: undefined
    };
    const rev = text(record.rev || record.revision || record.currentRev);
    const error = text(record.error || record.lastError || record.stateError);
    if (rev) result.rev = rev;
    if (error) result.error = error;
    return result;
  }

  function normalizeList(value) {
    return unique(array(value).map((entry) => text(entry).trim()).filter(Boolean));
  }

  function buildGraph(raw) {
    const source = raw && typeof raw === 'object' ? raw : {};
    const gates = [];
    const gateSeen = new Set();
    function addGate(entry) {
      const candidate = typeof entry === 'string' ? { id: entry } : object(entry);
      if (!candidate) return;
      const id = text(candidate.id || candidate.gate || candidate.code).trim();
      if (!id || gateSeen.has(id)) return;
      gateSeen.add(id);
      gates.push({
        id,
        title: text(candidate.title || candidate.name || id),
        stage: text(candidate.stage || ''),
        raw: candidate
      });
    }
    array(source.gates).forEach(addGate);
    const stages = array(source.stages).map((entry) => {
      const item = object(entry) || {};
      const id = text(item.id || item.stage).trim();
      const deps = normalizeList(item.deps);
      const needs = normalizeList(item.needs);
      const after = normalizeList(item.after);
      const gate = text(item.gate || '').trim();
      deps.forEach((gateId) => addGate(gateId));
      if (gate) addGate({ id: gate, title: gate, stage: id });
      return {
        id,
        name: text(item.name || item.label || id),
        deps,
        needs,
        after,
        gate: gate || null,
        implemented: item.implemented !== false,
        raw: item
      };
    }).filter((stage) => stage.id);
    const stageIds = new Set(stages.map((stage) => stage.id));
    const byStage = new Map(stages.map((stage) => [stage.id, stage]));
    stages.forEach((stage) => {
      if (!stage.gate) return;
      const gate = gates.find((entry) => entry.id === stage.gate);
      if (gate && !gate.stage) gate.stage = stage.id;
    });
    const byGate = new Map(gates.map((gate) => [gate.id, gate]));
    const edges = [];
    const edgeSeen = new Set();
    function addEdge(from, to, kind) {
      if (!from || !to || from === to) return;
      const key = from + '|' + to + '|' + kind;
      if (edgeSeen.has(key)) return;
      edgeSeen.add(key);
      edges.push({ from, to, kind });
    }
    stages.forEach((stage) => {
      stage.deps.forEach((gate) => addEdge(gate, stage.id, 'deps'));
      stage.needs.forEach((needed) => { if (stageIds.has(needed)) addEdge(needed, stage.id, 'needs'); });
      stage.after.forEach((before) => { if (stageIds.has(before)) addEdge(before, stage.id, 'after'); });
    });
    return {
      mode: text(source.mode || 'live'),
      lanes: array(source.lanes),
      stages,
      gates,
      edges,
      byStage,
      byGate,
      stageIds,
      raw: source
    };
  }

  function metricText(value) {
    if (value == null || value === '') return UNKNOWN;
    if (typeof value === 'number') return Number.isFinite(value) ? String(value) : UNKNOWN;
    const string = text(value).trim();
    return string || UNKNOWN;
  }

  function progressText(progress) {
    if (progress == null || progress === '') return UNKNOWN;
    if (typeof progress === 'number') {
      if (!Number.isFinite(progress)) return UNKNOWN;
      return Math.max(0, Math.min(100, Math.round(progress))) + '%';
    }
    if (typeof progress === 'string') {
      const string = progress.trim();
      if (!string) return UNKNOWN;
      const numeric = Number(string);
      return Number.isFinite(numeric) ? Math.max(0, Math.min(100, Math.round(numeric))) + '%' : string;
    }
    const item = object(progress);
    if (!item) return UNKNOWN;
    const percent = item.percent != null ? item.percent : item.pct;
    if (percent != null) {
      const numeric = Number(percent);
      if (Number.isFinite(numeric)) return Math.max(0, Math.min(100, Math.round(numeric))) + '%';
    }
    const done = Number(item.done);
    const total = Number(item.total);
    if (Number.isFinite(done) && Number.isFinite(total) && total > 0) return done + '/' + total + ' 단계';
    return UNKNOWN;
  }

  function jobStatus(value) {
    const raw = statusOf(value);
    const key = raw.toLowerCase();
    const state = JOB_META[key] ? key : 'unknown';
    const meta = JOB_META[state];
    return { state, raw, label: meta[0], tone: meta[1], complete: false };
  }

  function jobIdentity(job) { return text(job && (job.jobId || job.id)); }
  function characterLabel(detail) {
    const value = object(detail) || {};
    const summary = object(value.summary) || {};
    return text(value.name || summary.name || (value.persona && value.persona.name) || value.id || '캐릭터');
  }

  function normalizeJobs(source) {
    const entries = Array.isArray(source) ? source : array(source && (source.jobs || source.items));
    return entries.map((entry) => {
      const item = object(entry);
      if (!item) return null;
      const id = text(item.id || item.jobId);
      const status = statusOf(item.status || item.state);
      const info = jobStatus(status);
      return {
        id,
        characterId: text(item.characterId || item.character || ''),
        status,
        state: info.state,
        label: info.label,
        tone: info.tone,
        until: text(item.until || item.target || ''),
        createdAt: text(item.createdAt || item.startedAt || item.at || ''),
        finishedAt: text(item.finishedAt || item.endedAt || ''),
        raw: item
      };
    }).filter(Boolean);
  }

  function pendingFromValue(value) {
    if (value == null) return [];
    if (typeof value === 'string') return [{ id: value, status: 'AWAITING_HUMAN' }];
    if (Array.isArray(value)) return value.reduce((all, entry) => all.concat(pendingFromValue(entry)), []);
    const item = object(value);
    if (!item) return [];
    const id = text(item.gate || item.id || item.code).trim();
    if (!id) {
      return Object.keys(item).reduce((all, key) => {
        return all.concat(pendingFromValue(Object.assign({ gate: key }, object(item[key]) || {})));
      }, []);
    }
    return [{ id, status: statusOf(item) || 'AWAITING_HUMAN', stage: text(item.stage || '') }];
  }

  function pendingGatesFor(source, graph) {
    const detail = object(source) || {};
    const built = graph && graph.byGate ? graph : buildGraph(graph);
    const found = new Map();
    function add(id, status, stage) {
      const key = text(id).trim();
      if (!key) return;
      const info = pendingFromValue({ id: key, status: status || 'AWAITING_HUMAN', stage: stage || '' })[0];
      if (info) found.set(info.id, info);
    }
    pendingFromValue(detail.pendingGates).forEach((item) => add(item.id, item.status, item.stage));
    const gates = detail.gates;
    if (Array.isArray(gates)) {
      gates.forEach((entry) => {
        const item = object(entry);
        if (item && gateState(statusOf(item)) === 'pending') add(item.id || item.gate, statusOf(item), item.stage);
      });
    } else if (object(gates)) {
      Object.keys(gates).forEach((id) => {
        const item = gates[id];
        if (gateState(statusOf(item)) === 'pending') add(id, statusOf(item), item && item.stage);
      });
    }
    built.stages.forEach((stage) => {
      const record = stageRecord(detail.stages, stage.id);
      if (!record || !stage.gate) return;
      if (stateForStatus(statusOf(record)) === 'gate') add(stage.gate, statusOf(record), stage.id);
    });
    const gateOrder = new Map(built.gates.map((gate, index) => [gate.id, index]));
    return Array.from(found.values()).map((item) => {
      const definition = built.byGate.get(item.id);
      return {
        id: item.id,
        title: definition ? definition.title : item.id,
        stage: definition && definition.stage ? definition.stage : (item.stage || ''),
        status: item.status,
        raw: item
      };
    }).sort((a, b) => (gateOrder.get(a.id) == null ? 9999 : gateOrder.get(a.id)) - (gateOrder.get(b.id) == null ? 9999 : gateOrder.get(b.id)));
  }

  function countsFor(source, graph) {
    const detail = object(source) || {};
    const built = graph && graph.byStage ? graph : buildGraph(graph);
    const counts = { total: built.stages.length, done: 0, skipped: 0, pending: 0, errors: 0, unknown: 0, stages: [] };
    built.stages.forEach((definition) => {
      const row = translateStage(stageRecord(detail.stages, definition.id), definition);
      counts.stages.push(row);
      if (row.state === 'done') counts.done += 1;
      else if (row.state === 'skipped') counts.skipped += 1;
      else if (row.state === 'failed') counts.errors += 1;
      else if (row.state === 'unknown') counts.unknown += 1;
    });
    counts.pending = pendingGatesFor(detail, built).length;
    return counts;
  }

  function runRequest(characterId, until, confirm) {
    const id = text(characterId).trim();
    const target = text(until).trim();
    if (!id) throw new Error('캐릭터를 먼저 선택해 주세요.');
    if (!target) throw new Error('실행할 단계나 관문을 골라 주세요.');
    if (confirm != null && !Array.isArray(confirm)) throw new Error('확인할 단계 목록이 올바르지 않아요.');
    return {
      characterId: id,
      action: 'run',
      until: target,
      confirm: normalizeList(confirm || [])
    };
  }

  function createCharacterRequest(slug, brief) {
    const cleanSlug = text(slug).trim();
    const cleanBrief = text(brief).trim();
    if (!/^[a-z0-9][a-z0-9-]{0,40}$/.test(cleanSlug)) {
      throw new Error('slug는 소문자·숫자로 시작하는 1~41자(소문자·숫자·하이픈)여야 해요.');
    }
    if (!cleanBrief || cleanBrief.length > 20000) throw new Error('브리프는 1~20,000자로 적어 주세요.');
    return { slug: cleanSlug, brief: cleanBrief };
  }

  function extractHeld(source) {
    const raw = Array.isArray(source) ? source : array(source && source.held);
    return raw.map((entry) => {
      if (typeof entry === 'string') return { stage: entry, providers: [] };
      const item = object(entry);
      if (!item) return null;
      const stage = text(item.stage || item.id || item.code).trim();
      if (!stage) return null;
      return { stage, providers: normalizeList(item.providers) };
    }).filter(Boolean);
  }

  function confirmHeldRequest(characterId, held) {
    const stage = text(held && held.stage).trim();
    if (!stage) throw new Error('확인할 단계를 찾지 못했어요.');
    return runRequest(characterId, stage, [stage]);
  }

  function apiPath(apiBase, path) {
    const base = text(apiBase).trim();
    const suffix = text(path).trim();
    if (!base) return suffix.startsWith('/') ? suffix : '/' + suffix;
    const left = base.replace(/\/+$/, '');
    const right = suffix.replace(/^\/+/, '');
    return left + '/' + right;
  }

  function characterPath(id, apiBase) {
    return apiPath(apiBase, '/api/characters/' + encodeURIComponent(text(id)));
  }

  // 캐릭터마다 갈래(오리지널·트윈)와 모델 준비 방식이 달라 그래프도 다르다. id가 없으면 오리지널 기본 그래프다.
  function graphPath(characterId) {
    const id = text(characterId).trim();
    return '/api/runtime/graph' + (id ? '?character_id=' + encodeURIComponent(id) : '');
  }

  function gateUrl(characterId, gate, apiBase) {
    return apiPath(apiBase, '/gate.html') + '?character=' + encodeURIComponent(text(characterId)) + '&gate=' + encodeURIComponent(text(gate));
  }

  function eventsUrl(apiBase) {
    return apiPath(apiBase, '/api/events');
  }

  function untilOptions(graph) {
    const built = graph && graph.stages ? graph : buildGraph(graph);
    return unique(built.gates.map((gate) => gate.id).concat(built.stages.map((stage) => stage.id)));
  }

  function parseRoute(hash, search) {
    const rawHash = text(hash).replace(/^#/, '');
    const parts = rawHash.split('?');
    const path = parts[0] || '';
    const query = new URLSearchParams(parts.slice(1).join('?'));
    const extra = new URLSearchParams(text(search).replace(/^\?/, ''));
    const characterId = text(query.get('character') || extra.get('character') || '') || null;
    if (path === 'char' || path.startsWith('char/')) {
      const id = safeDecode(path.slice(5));
      return { view: 'char', characterId: id || null, jobId: null, sub: '' };
    }
    if (path === 'job' || path.startsWith('job/')) {
      const rest = path.slice(4).split('/').filter(Boolean);
      const jobId = rest[0] ? safeDecode(rest[0]) : null;
      const sub = rest[1] === 'floor' ? 'floor' : 'table';
      return { view: 'job', characterId, jobId, sub };
    }
    return { view: 'chars', characterId, jobId: null, sub: '' };
  }

  function sceneLayout(graph) {
    const built = graph && graph.edges ? graph : buildGraph(graph);
    const lanes = [];
    const assigned = new Set();
    array(built.lanes).forEach((lane) => {
      const ids = array(lane.stages).map((entry) => text(typeof entry === 'string' ? entry : entry.id))
        .filter((id) => built.byStage.has(id) && !assigned.has(id));
      if (!ids.length) return;
      ids.forEach((id) => assigned.add(id));
      lanes.push({id: lane.id, label: text(lane.label || lane.id), stages: ids});
    });
    const rest = built.stages.filter((stage) => !assigned.has(stage.id));
    for (let i = 0; i < rest.length; i += 4) {
      lanes.push({id: 'other-' + i, label: lanes.length ? '기타 공정' : '공정', stages: rest.slice(i, i + 4).map((stage) => stage.id)});
    }
    const nodes = [];
    lanes.forEach((lane, row) => {
      lane.y = 85 + row * 118;
      lane.stages.forEach((id, column) => {
        const stage = built.byStage.get(id);
        nodes.push({id, kind:'stage', label:stage.name, x:155 + column * 190, y:lane.y, stage, state:'unknown'});
      });
    });
    const byId = new Map(nodes.map((node) => [node.id, node]));
    built.gates.forEach((gate) => {
      let owner = byId.get(gate.stage);
      if (!owner) {
        const edge = built.edges.find((edge) => edge.from === gate.id && byId.has(edge.to));
        owner = edge && byId.get(edge.to);
      }
      const node = {id:gate.id, kind:'gate', label:gate.title, x:(owner ? owner.x : 155) + 72, y:(owner ? owner.y : 85) - 47, gate, state:'unknown'};
      nodes.push(node);byId.set(node.id,node);
    });
    const edges = built.edges.map((edge) => ({...edge, source:byId.get(edge.from), target:byId.get(edge.to)})).filter((edge) => edge.source && edge.target);
    const columns = Math.max(1,...lanes.map((lane) => lane.stages.length));
    return {nodes,edges,byId,lanes,width: Math.max(500, 200 + columns * 190),height:Math.max(250, lanes.length * 118 + 60)};
  }

  function parseTextPipeline(raw) {
    const source = object(raw) || {};
    const artifactSource = array(source.artifacts).length ? source.artifacts : (array(source.documents).length ? source.documents : array(source.docs));
    const artifacts = artifactSource.map((entry) => {
      const item = object(entry);
      if (!item) return null;
      return {
        label: text(item.label || item.title || item.path || '산출물'),
        revision: text(item.revision || item.rev || ''),
        text: text(item.text || item.content || item.body || ''),
        textTruncated: item.textTruncated === true,
        sourceModel: text(item.sourceModel || ''),
        sourceProfile: text(item.sourceProfile || ''),
        completionCheck: text(item.completionCheck || ''),
        path: text(item.path || ''),
        files: array(item.files).map((file) => {
          const info = object(file) || {};
          return { path: text(info.path || info.name || ''), url: safeHref(info.url || ''), size: text(info.size || '') };
        }).filter((file) => file.path || file.url)
      };
    }).filter(Boolean);
    const calls = array(source.calls).map((entry) => {
      const item = object(entry);
      if (!item) return null;
      return {
        task: text(item.task || item.role || ''),
        stage: text(item.stage || ''),
        model: text(item.model || ''),
        profile: text(item.profile || ''),
        route: text(item.route || ''),
        ok: typeof item.ok === 'boolean' ? item.ok : null,
        ref: text(item.ref || item.reference || '')
      };
    }).filter(Boolean);
    return {
      characterId: text(source.characterId || ''),
      name: text(source.name || ''),
      artifacts,
      calls
    };
  }

  const pure = {
    UNKNOWN,
    escapeHTML,
    safeHref,
    buildGraph,
    translateStage,
    stageRecord,
    stateForStatus,
    gateState,
    jobStatus,
    normalizeJobs,
    jobIdentity,
    characterLabel,
    pendingGatesFor,
    countsFor,
    metricText,
    progressText,
    runRequest,
    createCharacterRequest,
    extractHeld,
    confirmHeldRequest,
    apiPath,
    graphPath,
    characterPath,
    gateUrl,
    eventsUrl,
    untilOptions,
    parseRoute,
    sceneLayout,
    parseTextPipeline
  };

  function mount(options) {
    const opts = options || {};
    let root = opts.root || (typeof document !== 'undefined' ? document : null);
    if (typeof root === 'string' && typeof document !== 'undefined') root = document.querySelector(root);
    if (!root) return { refresh: function () { return Promise.resolve(); }, destroy: function () {} };
    const doc = root.nodeType === 9 ? root : root.ownerDocument;
    if (!doc) return { refresh: function () { return Promise.resolve(); }, destroy: function () {} };
    const body = doc.body;
    const apiBase = text(opts.apiBase);
    const state = {
      graph: buildGraph({}),
      graphLoaded: false,
      projects: null,
      projectsError: null,
      detail: null,
      detailId: null,
      detailLoading: false,
      detailError: null,
      text: null,
      textId: null,
      textLoading: false,
      textError: null,
      textConfig: null,
      jobDetail: null,
      jobId: null,
      jobError: null,
      offline: false,
      sseOk: false,
      stale: false,
      lastUpdated: null,
      busy: false,
      feedback: null,
      until: 'G6',
      form: { open: false, dismissed: false, slug: '', brief: '', error: null },
      route: parseRoute(typeof location !== 'undefined' ? location.hash : '', typeof location !== 'undefined' ? location.search : ''),
      detailSeq: 0,
      textSeq: 0,
      jobSeq: 0,
      refreshSeq: 0,
      refreshing: null,
      refreshQueued: false,
      refreshController: null,
      detailController: null,
      textController: null,
      jobController: null,
      eventSource: null,
      timers: new Set(),
      returnFocus: null,
      drawerOpener: null,
      destroyed: false
    };
    if (body) body.classList.add('runtime-live');

    function $(selector) {
      try { return root.querySelector(selector); } catch (error) { return null; }
    }
    function setText(element, value) {
      if (element && element.textContent !== text(value)) element.textContent = text(value);
    }
    function setHTML(element, html) {
      if (!element) return false;
      if (element.__rtHTML === html) return false;
      element.innerHTML = html;
      element.__rtHTML = html;
      return true;
    }
    function show(element, visible) {
      if (element) element.hidden = !visible;
    }
    function later(fn, ms) {
      const id = setTimeout(function () {
        state.timers.delete(id);
        if (!state.destroyed) fn();
      }, ms);
      state.timers.add(id);
      return id;
    }
    function clearTimers() {
      state.timers.forEach((id) => clearTimeout(id));
      state.timers.clear();
    }
    function nowLabel() {
      if (!state.lastUpdated) return '';
      try {
        return state.lastUpdated.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
      } catch (error) {
        return '';
      }
    }
    function dateLabel(value) {
      const string = text(value);
      if (!string) return '–';
      const date = new Date(string);
      if (Number.isNaN(date.getTime())) return string;
      try {
        return date.toLocaleString('ko-KR', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
      } catch (error) {
        return string;
      }
    }
    function canMutate() {
      return !state.offline && !state.busy && !state.destroyed && !state.detailError;
    }
    function messageFor(error) {
      if (!error) return '알 수 없는 오류가 났어요.';
      if (error.network) return '서버에 연결하지 못했어요. 연결을 확인한 뒤 다시 시도해 주세요.';
      const detail = error.detail;
      if (typeof detail === 'string' && detail.trim()) return detail;
      if (Array.isArray(detail)) {
        return detail.map((item) => text(item && (item.msg || item.message || item))).filter(Boolean).join(' ') || '요청을 처리하지 못했어요.';
      }
      return error.message || ('요청을 처리하지 못했어요.' + (error.status ? ' (' + error.status + ')' : ''));
    }
    async function request(method, path, init) {
      if (typeof fetch !== 'function') {
        const error = new Error('이 브라우저에서는 서버에 연결할 수 없어요.');
        error.network = true;
        throw error;
      }
      const config = init || {};
      const headers = { Accept: 'application/json' };
      if (config.body != null) headers['Content-Type'] = 'application/json';
      let response;
      try {
        response = await fetch(apiPath(apiBase, path), {
          method,
          headers,
          body: config.body == null ? undefined : JSON.stringify(config.body),
          signal: config.signal
        });
      } catch (error) {
        if (error && error.name === 'AbortError') throw error;
        const network = new Error(messageFor({ network: true }));
        network.network = true;
        throw network;
      }
      let data = null;
      const contentType = response.headers && response.headers.get ? response.headers.get('content-type') || '' : '';
      try {
        if (contentType.indexOf('application/json') >= 0) data = await response.json();
        else if (response.status !== 204) {
          const raw = await response.text();
          data = raw ? raw : null;
        }
      } catch (error) {
        data = null;
      }
      if (!response.ok) {
        const detail = data && typeof data === 'object' ? data.detail || data.message : data;
        const failure = new Error(typeof detail === 'string' ? detail : 'HTTP ' + response.status);
        failure.status = response.status;
        failure.detail = detail;
        throw failure;
      }
      return data;
    }

    function routeNow() {
      return parseRoute(typeof location !== 'undefined' ? location.hash : '', typeof location !== 'undefined' ? location.search : '');
    }
    function findJob(jobId) {
      const all = [].concat(
        state.projects && array(state.projects.jobs),
        state.detail && array(state.detail.jobs),
        state.detail && state.detail.lastJob ? [state.detail.lastJob] : []
      );
      return all.find((job) => job && text(job.id || job.jobId) === jobId) || null;
    }
    function characterIdForRoute(route) {
      if (route.characterId) return route.characterId;
      if (route.jobId) {
        const job = findJob(route.jobId);
        if (job) return text(job.characterId || job.character || '');
      }
      return '';
    }
    function latestJobId(detail) {
      if (!detail) return null;
      if (jobIdentity(detail.lastJob)) return jobIdentity(detail.lastJob);
      const jobs = normalizeJobs(detail.jobs);
      if (jobs.length && jobs[0].id) return jobs[0].id;
      if (jobIdentity(detail.job)) return jobIdentity(detail.job);
      return null;
    }
    function updateRoute(route) {
      const previous = state.route;
      const changed = previous.view !== route.view || previous.characterId !== route.characterId || previous.jobId !== route.jobId || previous.sub !== route.sub;
      state.route = route;
      if (body) {
        body.dataset.view = route.view;
        body.dataset.sub = route.sub || '';
      }
      if (changed && previous.view !== 'chars') closeDrawer(false);
    }

    async function loadDetail(id) {
      if (!id || state.destroyed) return;
      const sequence = ++state.detailSeq;
      if (state.detailController) state.detailController.abort();
      const controller = typeof AbortController === 'function' ? new AbortController() : null;
      state.detailController = controller;
      const differs = state.detailId !== id;
      if (differs) {
        state.detail = null;
        state.detailId = id;
        state.text = null;
        state.textId = null;
        state.textError = null;
        state.textSeq += 1;
        if (state.textController) state.textController.abort();
        state.jobDetail = null;
        state.jobId = null;
        state.jobError = null;
        state.jobSeq += 1;
        if (state.jobController) state.jobController.abort();
      }
      state.detailLoading = true;
      state.detailError = null;
      render();
      try {
        const data = await request('GET', '/api/characters/' + encodeURIComponent(id), { signal: controller ? controller.signal : undefined });
        if (state.destroyed || sequence !== state.detailSeq || state.detailId !== id) return;
        state.detail = object(data) || {};
        state.detailLoading = false;
        state.detailError = null;
        state.offline = false;
        state.stale = false;
        state.lastUpdated = new Date();
        render();
        const jobId = state.route.jobId || latestJobId(state.detail);
        state.jobId = jobId;
        loadJob(jobId);
        loadText(id);
      } catch (error) {
        if (error && error.name === 'AbortError') return;
        if (state.destroyed || sequence !== state.detailSeq) return;
        state.detailLoading = false;
        state.detailError = messageFor(error);
        if (error.network) state.offline = true;
        render();
      }
    }

    async function loadText(id) {
      if (!id || state.destroyed) return;
      const sequence = ++state.textSeq;
      if (state.textController) state.textController.abort();
      const controller = typeof AbortController === 'function' ? new AbortController() : null;
      state.textController = controller;
      state.textLoading = true;
      state.textError = null;
      if (state.textId !== id) state.text = null;
      try {
        const results = await Promise.allSettled([
          request('GET', '/api/text-pipeline/characters/' + encodeURIComponent(id), { signal: controller ? controller.signal : undefined }),
          request('GET', '/api/text-pipeline', { signal: controller ? controller.signal : undefined })
        ]);
        if (state.destroyed || sequence !== state.textSeq) return;
        const detailResult = results[0];
        const configResult = results[1];
        state.textLoading = false;
        if (detailResult.status === 'fulfilled') {
          state.text = parseTextPipeline(detailResult.value);
          state.textId = id;
          state.textError = null;
        } else if (detailResult.reason && detailResult.reason.name === 'AbortError') {
          return;
        } else {
          state.textError = messageFor(detailResult.reason);
          if (detailResult.reason && detailResult.reason.network) state.offline = true;
        }
        if (configResult.status === 'fulfilled' && object(configResult.value)) {
          state.textConfig = {
            profile: text(configResult.value.profile),
            route: text(configResult.value.route),
            enabled: configResult.value.enabled === true
          };
        }
        render();
      } catch (error) {
        if (state.destroyed || error.name === 'AbortError') return;
        state.textLoading = false;
        state.textError = messageFor(error);
        render();
      }
    }

    async function loadJob(jobId) {
      if (state.destroyed) return;
      if (!jobId) {
        state.jobDetail = null;
        state.jobId = null;
        state.jobError = null;
        render();
        return;
      }
      state.jobId = text(jobId);
      const sequence = ++state.jobSeq;
      if (state.jobController) state.jobController.abort();
      const controller = typeof AbortController === 'function' ? new AbortController() : null;
      state.jobController = controller;
      try {
        const data = await request('GET', '/api/jobs/' + encodeURIComponent(jobId), { signal: controller ? controller.signal : undefined });
        if (state.destroyed || sequence !== state.jobSeq) return;
        state.jobDetail = object(data) || {};
        state.jobError = null;
        render();
      } catch (error) {
        if (error && error.name === 'AbortError') return;
        if (state.destroyed || sequence !== state.jobSeq) return;
        state.jobError = messageFor(error);
        if (error.network) state.offline = true;
        render();
      }
    }

    async function refresh() {
      if (state.destroyed) return;
      if (state.refreshing) {
        state.refreshQueued = true;
        return state.refreshing;
      }
      const sequence = ++state.refreshSeq;
      if (state.refreshController) state.refreshController.abort();
      const controller = typeof AbortController === 'function' ? new AbortController() : null;
      state.refreshController = controller;
      const task = (async function () {
        const results = await Promise.allSettled([
          request('GET', '/api/runtime/graph', { signal: controller ? controller.signal : undefined }),
          request('GET', '/api/projects', { signal: controller ? controller.signal : undefined })
        ]);
        if (state.destroyed || sequence !== state.refreshSeq) return;
        const graphResult = results[0];
        const projectsResult = results[1];
        let successes = 0;
        let networkFailure = false;
        if (graphResult.status === 'fulfilled') {
          state.graph = buildGraph(graphResult.value);
          state.graphLoaded = true;
          successes += 1;
        } else if (graphResult.reason && graphResult.reason.network) {
          networkFailure = true;
        }
        if (projectsResult.status === 'fulfilled') {
          state.projects = object(projectsResult.value) || {};
          state.projectsError = null;
          successes += 1;
        } else {
          if (projectsResult.reason && projectsResult.reason.network) networkFailure = true;
          state.projectsError = messageFor(projectsResult.reason);
        }
        if (successes) {
          state.offline = false;
          state.stale = false;
          state.lastUpdated = new Date();
        } else if (networkFailure) {
          state.offline = true;
        }
        const route = routeNow();
        updateRoute(route);
        if (route.view === 'chars' && !route.characterId) {
          state.detail = null;
          state.detailId = null;
          state.detailLoading = false;
          state.detailError = null;
          state.text = null;
          state.textSeq += 1;
          if (state.textController) state.textController.abort();
          state.jobDetail = null;
          state.jobId = null;
          state.jobSeq += 1;
          if (state.jobController) state.jobController.abort();
          render();
        } else {
          let id = characterIdForRoute(route);
          if (!id && route.jobId) {
            try {
              const stored = await request('GET', '/api/jobs/' + encodeURIComponent(route.jobId));
              if (routeNow().jobId !== route.jobId) return;
              id = text(stored && stored.characterId);
            } catch (error) {
              state.detailError = messageFor(error);
            }
          }
          if (id) {
          await loadDetail(id);
          } else {
            state.detailLoading = false;
            state.detailError = '캐릭터를 찾지 못했어요. 주소의 캐릭터를 확인해 주세요.';
            render();
          }
        }
      })();
      state.refreshing = task;
      const finish = function () {
        if (state.refreshing === task) state.refreshing = null;
        if (state.refreshQueued) {
          state.refreshQueued = false;
          later(refresh, 80);
        }
      };
      task.then(finish, finish);
      return task;
    }

    function scheduledRefresh() {
      clearTimers();
      later(refresh, 320);
    }

    function startEvents() {
      if (state.destroyed) return;
      if (typeof EventSource !== 'function') return;
      try {
        const source = new EventSource(eventsUrl(apiBase));
        state.eventSource = source;
        source.onopen = function () {
          state.sseOk = true;
          state.stale = false;
          render();
          refresh();
        };
        source.onerror = function () {
          state.sseOk = false;
          state.stale = true;
          render();
        };
        ['state', 'job', 'gate', 'hello', 'message'].forEach((name) => {
          source.addEventListener(name, function () {
            state.stale = false;
            scheduledRefresh();
          });
        });
      } catch (error) {
        state.sseOk = false;
      }
    }

    function pill(label, tone) {
      return '<span class="rt-pill t-' + escapeHTML(tone) + '"><span class="rt-dot"></span>' + escapeHTML(label) + '</span>';
    }
    function emptyBlock(message) {
      return '<div class="crow-empty">' + escapeHTML(message) + '</div>';
    }
    function netNote() {
      const pieces = [];
      if (state.offline) {
        pieces.push('<div class="rt-net rt-net--bad" role="status"><span class="rt-dot"></span><b>서버 연결 끊김</b> 마지막 기록을 보여 주는 중이에요. 실행·생성은 다시 연결될 때까지 잠겨 있어요.</div>');
      } else if (state.stale) {
        pieces.push('<div class="rt-net" role="status"><span class="rt-dot"></span><b>실시간 재연결 중</b> 기록은 주기적으로 다시 확인해요. 마지막 갱신 ' + escapeHTML(nowLabel() || '기록 없음') + '.</div>');
      } else if (state.detailError) {
        pieces.push('<div class="rt-net rt-net--bad" role="status"><span class="rt-dot"></span><b>기록을 다시 읽지 못했어요.</b> ' + escapeHTML(state.detailError) + '</div>');
      } else if (state.projectsError) {
        pieces.push('<div class="rt-net" role="status"><span class="rt-dot"></span><b>목록을 새로 읽지 못했어요.</b> ' + escapeHTML(state.projectsError) + ' 마지막 목록을 보여 주는 중이에요.</div>');
      }
      if (pieces.length) {
        pieces.push('<div class="rt-net-actions"><button type="button" class="btn btn--sm" data-runtime-retry' + (state.busy ? ' disabled' : '') + '>지금 다시 확인</button></div>');
      }
      return pieces.join('');
    }

    function kpi(key, value, sub, bad) {
      const card = $('[data-kpi="' + key + '"]');
      if (card) {
        card.classList.toggle('is-bad', !!bad);
        card.classList.toggle('is-alert', !!bad && /대기|사람/.test(text(sub)));
      }
      setText($('[data-k="' + key + '-v"]'), value);
      setText($('[data-k="' + key + '-s"]'), sub);
      const meter = $('[data-k="' + key + '-m"]');
      if (meter) meter.style.setProperty('--w', '0%');
    }
    function projectCharacters() {
      return state.projects && Array.isArray(state.projects.characters) ? state.projects.characters : [];
    }
    function projectJobs() {
      return state.projects && Array.isArray(state.projects.jobs) ? state.projects.jobs : [];
    }
    function pendingFor(character) {
      return pendingGatesFor(character, state.graph);
    }
    function renderKpis() {
      const chars = projectCharacters();
      const allPending = chars.reduce((sum, character) => sum + pendingFor(character).length, 0);
      const errors = chars.reduce((sum, character) => {
        const counts = countsFor(character, state.graph);
        return sum + counts.errors + (text(character.stateError) ? 1 : 0);
      }, 0);
      const withPending = chars.filter((character) => pendingFor(character).length > 0).length;
      const jobs = projectJobs().map((job) => jobStatus(job.status || job.state));
      const running = jobs.filter((job) => job.state === 'running').length;
      if (state.projects) {
        kpi('c-all', metricText(chars.length), jobs.length ? '작업 기록 ' + jobs.length + '건 · 실행 중 ' + running + '건' : '작업 기록 없음', false);
        kpi('c-gate', metricText(allPending), withPending + '명에게 대기 중', allPending > 0);
        kpi('c-human', metricText(errors), errors ? '단계 실패·상태 손상' : '문제 없음', errors > 0);
        kpi('c-cost', UNKNOWN, '서버 비용 지표 없음', false);
        kpi('c-rel', UNKNOWN, '출시 상태 미제공', false);
      }
      const detail = state.detail;
      const counts = detail ? countsFor(detail, state.graph) : null;
      const stagePending = detail ? pendingGatesFor(detail, state.graph).length : 0;
      if (counts) {
        kpi('gate', metricText(stagePending), stagePending ? '서버가 사람 확인을 기다려요' : '사람 확인 대기 없음', stagePending > 0);
        kpi('eta', UNKNOWN, '서버 예상 시간 미제공', false);
        kpi('prob', metricText(counts.errors), counts.errors ? '검사 실패 단계' : (text(detail.stateError) ? '상태 파일 손상' : '실패 기록 없음'), counts.errors > 0 || !!text(detail.stateError));
        kpi('cost', UNKNOWN, '서버 비용 지표 없음', false);
        kpi('prog', progressText(detail.progress), (counts.done + counts.skipped) + '/' + counts.total + ' 단계 승인·건너뜀', false);
        const meter = $('[data-k="cost-m"]');
        if (meter) meter.style.setProperty('--w', '0%');
      } else {
        kpi('gate', detail ? UNKNOWN : '–', detail ? '관문 상태 미집계' : '캐릭터를 선택하세요', false);
        kpi('eta', UNKNOWN, '서버 예상 시간 미제공', false);
        kpi('prob', detail ? UNKNOWN : '–', '실패 기록 없음', false);
        kpi('cost', UNKNOWN, '서버 비용 지표 없음', false);
        kpi('prog', detail ? UNKNOWN : '–', '서버 진행률 미집계', false);
      }
    }

    function renderChars() {
      const host = $('[data-chars]');
      if (!host) return;
      const chars = projectCharacters();
      if (!state.projects && !state.projectsError) {
        setHTML(host, emptyBlock('서버에서 실제 캐릭터 목록을 불러오는 중이에요.') + netNote());
        return;
      }
      if (!state.projects && state.projectsError) {
        setHTML(host, emptyBlock(state.projectsError) + '<div class="rt-net-actions"><button type="button" class="btn btn--sm" data-runtime-retry>다시 확인</button></div>');
        return;
      }
      if (!chars.length && !state.form.dismissed) state.form.open = true;
      const existingForm = host.querySelector('[data-runtime-create-form]');
      const rows = chars.length ? chars.map((character) => {
        const id = text(character.id || character.characterId);
        const name = text(character.name || character.id || '캐릭터');
        const info = countsFor(character, state.graph);
        const pending = pendingFor(character).length;
        const job = character.lastJob || character.job || null;
        const jobInfo = job ? jobStatus(job.status || job.state) : null;
        const stateError = text(character.stateError);
        return '<a class="crow rt-crow" href="#char/' + encodeURIComponent(id) + '" aria-label="' + escapeHTML(name + ' 열기') + '">' +
          '<span class="r-char"><span class="r-av" aria-hidden="true">' + escapeHTML(name.slice(0, 1)) + '</span><span><b>' + escapeHTML(name) + '</b><small>' + escapeHTML(id) + '</small></span></span>' +
          '<span class="rt-cell"><b>' + info.done + '/' + info.total + '</b><small>승인 단계</small></span>' +
          '<span class="rt-cell"><b>' + pending + '</b><small>결재 대기</small></span>' +
          '<span class="rt-cell">' + (stateError ? '<b class="is-bad">상태 손상</b>' : (info.errors ? '<b class="is-bad">실패 ' + info.errors + '</b>' : '<small>확인할 문제 없음</small>')) + '</span>' +
          '<span class="rt-cell"><b>' + escapeHTML(progressText(character.progress)) + '</b><small>서버 진행</small></span>' +
          '<span class="rt-cell">' + (jobInfo ? pill(jobInfo.label, jobInfo.tone) + '<small>' + escapeHTML(jobIdentity(job)) + '</small>' : '<small>작업 기록 없음</small>') + '</span>' +
          '<span class="rt-cell"><small>' + escapeHTML(dateLabel(character.updatedAt || (job && (job.finishedAt || job.startedAt || job.createdAt)) || '')) + '</small></span>' +
          '</a>';
      }).join('') : emptyBlock('아직 실제 서버에 캐릭터가 없어요. 아래에서 브리프로 첫 캐릭터를 등록하세요.');
      const head = '<div class="crow head"><span>캐릭터</span><span>단계</span><span>관문</span><span>확인할 일</span><span>진행</span><span>작업 요청</span><span>마지막 활동</span></div>';
      if (state.form.open && existingForm) {
        setHTML(host.querySelector('[data-runtime-character-rows]'), head + rows);
        setHTML(host.querySelector('[data-runtime-list-net]'), netNote());
        syncCreateForm(existingForm);
        return;
      }
      setHTML(host, '<div data-runtime-list-net>' + netNote() + '</div><div data-runtime-character-rows>' + head + rows + '</div>' + (state.form.open ? createFormHTML() : ''));
      const form = host.querySelector('[data-runtime-create-form]');
      if (form) syncCreateForm(form);
    }

    function createFormHTML() {
      const disabled = canMutate() ? '' : ' disabled';
      return '<form class="rt-create" data-runtime-create-form novalidate>' +
        '<div class="rt-create-head"><div><h3>새 캐릭터 등록</h3><p>슬러그와 브리프를 저장해 실제 캐릭터 폴더를 만들어요. 모델 생성은 자동으로 시작하지 않아요.</p></div><button type="button" class="btn btn--sm" data-runtime-close-form>닫기</button></div>' +
        '<label class="rt-field">슬러그<input type="text" name="slug" data-runtime-slug value="' + escapeHTML(state.form.slug) + '" maxlength="41" pattern="[a-z0-9][a-z0-9-]{0,40}" placeholder="hana-01" autocomplete="off" required></label>' +
        '<label class="rt-field">브리프<textarea name="brief" data-runtime-brief rows="4" maxlength="20000" placeholder="이름, 성격, 관계, 원하는 장면을 적어 주세요." required>' + escapeHTML(state.form.brief) + '</textarea></label>' +
        '<div class="rt-form-foot"><span class="rt-form-status" data-runtime-form-status role="status"></span><button type="submit" class="btn btn--primary" data-runtime-create' + disabled + '>캐릭터 등록</button></div>' +
        '</form>';
    }
    function syncCreateForm(form) {
      if (!form) return;
      const status = form.querySelector('[data-runtime-form-status]');
      let message = '브리프 1~20,000자 · 등록만 하고 실행은 직접 시작해요.';
      let tone = '';
      if (state.form.error) { message = state.form.error; tone = 'is-bad'; }
      else if (state.busy) message = '등록 요청을 보내는 중이에요.';
      else if (state.offline) { message = '서버 연결이 끊겨 등록할 수 없어요.'; tone = 'is-bad'; }
      setText(status, message);
      if (status) status.className = 'rt-form-status ' + tone;
      const button = form.querySelector('[data-runtime-create]');
      if (button) button.disabled = !canMutate();
      const slug = form.querySelector('[data-runtime-slug]');
      const brief = form.querySelector('[data-runtime-brief]');
      if (slug && doc.activeElement !== slug && slug.value !== state.form.slug) slug.value = state.form.slug;
      if (brief && doc.activeElement !== brief && brief.value !== state.form.brief) brief.value = state.form.brief;
    }

    function renderCharHead() {
      const host = $('[data-char-head]');
      if (!host) return;
      if (!state.detail) {
        const message = state.detailLoading ? '캐릭터 기록을 불러오는 중이에요.' : (state.detailError || '캐릭터를 선택해 주세요.');
        const retry = !state.detailLoading && (state.detailError || state.offline) ? '<button type="button" class="btn btn--sm" data-runtime-retry>다시 확인</button>' : '';
        setHTML(host, '<div class="rt-char-empty">' + escapeHTML(message) + retry + '</div>');
        return;
      }
      const detail = state.detail;
      const id = text(detail.id || state.detailId);
      const name = characterLabel(detail);
      const counts = countsFor(detail, state.graph);
      const pending = pendingGatesFor(detail, state.graph).length;
      const stateError = text(detail.stateError);
      const jobId = jobIdentity(detail.lastJob || detail.job);
      const actions = [];
      if (jobId) actions.push('<button type="button" class="btn" data-runtime-open-job data-job="' + escapeHTML(jobId) + '">공장 현장</button>');
      if (state.offline) actions.push('<button type="button" class="btn" data-runtime-retry>다시 연결</button>');
      setHTML(host, '<span class="ch-av" aria-hidden="true">' + escapeHTML(name.slice(0, 1)) + '</span>' +
        '<span class="ch-id"><span class="ch-name"><b>' + escapeHTML(name) + '</b>' + pill(stateError ? '상태 손상' : '실제 기록', stateError ? 'bad' : 'ok') + '</span>' +
        '<code>' + escapeHTML(id) + '</code><span class="ch-meta">' + escapeHTML(pending ? '사람 검토 ' + pending + '건 대기' : '검토할 기록을 선택하세요') + (stateError ? ' · ' + escapeHTML(stateError) : '') + '</span>' +
        '<span class="ch-tag">' + escapeHTML(detail.brief ? text(detail.brief).slice(0, 180) : '브리프 본문은 서버 기록에 있을 때만 표시해요.') + '</span></span>' +
        '<span class="ch-stats"><span><small>진행</small><b>' + escapeHTML(progressText(detail.progress)) + '</b></span>' +
        '<span><small>승인 단계</small><b>' + counts.done + '/' + counts.total + '</b></span>' +
        '<span><small>결재 대기</small><b class="' + (pending ? 'is-warn' : '') + '">' + pending + '건</b></span>' +
        '<span><small>문제</small><b class="' + (counts.errors || stateError ? 'is-bad' : '') + '">' + escapeHTML(metricText(counts.errors)) + '</b></span></span>' +
        '<span class="ch-actions">' + actions.join('') + '</span>');
    }

    function renderControls() {
      const host = $('[data-newjob]');
      if (!host) return;
      show(host, true);
      if (!state.detail) {
        setHTML(host, state.detailLoading ? '<p class="rt-muted">캐릭터 기록을 불러오는 중이에요.</p>' : netNote());
        return;
      }
      const detail = state.detail;
      const id = text(detail.id || state.detailId);
      const options = untilOptions(state.graph);
      if (!options.includes(state.until)) state.until = options.includes('G6') ? 'G6' : (options[0] || 'G6');
      const optionHTML = options.map((option) => {
        const definition = state.graph.byStage.get(option);
        const gate = state.graph.byGate.get(option);
        const label = definition ? definition.name + ' (' + option + ')' : (gate ? gate.title + ' (' + option + ')' : option);
        const missing = definition && definition.implemented === false ? ' · 미구현' : '';
        return '<option value="' + escapeHTML(option) + '"' + (option === state.until ? ' selected' : '') + '>' + escapeHTML(label + missing) + '</option>';
      }).join('');
      const held = extractHeld(detail);
      const stateError = text(detail.stateError);
      const disabled = !canMutate() || !!stateError || !!detail.job || !options.length;
      const heldHTML = held.length ? held.map((entry) => '<li class="rt-held"><span><b>' + escapeHTML(entry.stage) + '</b><small>' + (entry.providers.length ? escapeHTML(entry.providers.join(' · ')) : '유료 공급자 기록 없음') + '</small></span><button type="button" class="btn btn--sm" data-runtime-confirm-held data-stage="' + escapeHTML(entry.stage) + '"' + (disabled ? ' disabled' : '') + '>이 단계만 실행 확인</button></li>').join('') : '<li class="rt-held rt-held--none">보류된 유료 단계가 없어요.</li>';
      const feedback = state.feedback ? '<div class="rt-feedback t-' + escapeHTML(state.feedback.tone) + '" role="status">' + escapeHTML(state.feedback.text) + '</div>' : '';
      setHTML(host, netNote() + feedback + '<div class="rt-run">' +
        '<div class="rt-run-head"><div><h3>작업 시작</h3><p>실행할 때만 서버에 요청해요. 승인은 관문 화면에서 직접 결정해요.</p></div>' +
        '<div class="rt-run-controls"><label>여기까지<select data-runtime-until' + (disabled ? ' disabled' : '') + '>' + optionHTML + '</select></label>' +
        '<button type="button" class="btn btn--primary" data-runtime-run' + (disabled ? ' disabled' : '') + '>실행</button></div></div>' +
        (stateError ? '<p class="rt-bad">상태 파일을 읽지 못해 실행할 수 없어요: ' + escapeHTML(stateError) + '</p>' : '') +
        '<div class="rt-held-wrap"><h4>유료 단계 확인 대기</h4><p>아래 단계는 자동 승인되지 않아요. 한 단계를 직접 고를 때만 그 단계가 확인 목록에 들어가요.</p><ul class="rt-held-list">' + heldHTML + '</ul></div>' +
        '</div>');
    }

    function renderAssets() {
      const host = $('[data-assets]');
      if (!host) return;
      if (!state.detail) {
        setHTML(host, emptyBlock(state.detailLoading ? '기록을 불러오는 중이에요.' : '캐릭터를 선택하면 실제 산출물 기록을 보여 줘요.'));
        return;
      }
      const detail = state.detail;
      const stages = state.graph.stages.map((definition) => translateStage(stageRecord(detail.stages, definition.id), definition));
      const stageHTML = stages.map((row) => '<div class="rt-asset-row"><span class="rt-asset-name">' + pill(row.label, row.tone) + ' <b>' + escapeHTML(row.id) + '</b><small>' + escapeHTML(row.name) + '</small></span><span class="rt-asset-meta">' + (row.rev ? '<code>' + escapeHTML(row.rev) + '</code>' : '<small>revision 없음</small>') + (row.error ? '<small class="is-bad">' + escapeHTML(row.error) + '</small>' : '') + '</span></div>').join('');
      const selection = state.textConfig ? '<p class="rt-note">지금 선택 설정 · 프로필 <code>' + escapeHTML(state.textConfig.profile || '없음') + '</code> · 경로 <code>' + escapeHTML(state.textConfig.route || '없음') + '</code></p>' : '<p class="rt-note">지금 선택 설정 · 미집계</p>';
      let textHTML = '';
      if (state.textLoading) textHTML = '<p class="rt-muted">텍스트 원장을 불러오는 중이에요.</p>';
      else if (state.textError) textHTML = '<p class="rt-bad" role="status">텍스트 기록을 불러오지 못했어요: ' + escapeHTML(state.textError) + '</p><button type="button" class="btn btn--sm" data-runtime-retry>다시 확인</button>';
      else if (!state.text) textHTML = '<p class="rt-muted">텍스트 산출물 기록이 없어요.</p>';
      else {
        const artifacts = state.text.artifacts.map((artifact) => {
          const files = artifact.files.length ? '<ul class="rt-files">' + artifact.files.map((file) => '<li>' + (file.url ? '<a href="' + escapeHTML(file.url) + '" target="_blank" rel="noopener noreferrer">' + escapeHTML(file.path || file.url) + '</a>' : '<code>' + escapeHTML(file.path) + '</code>') + (file.size ? ' <small>' + escapeHTML(file.size) + '</small>' : '') + '</li>').join('') + '</ul>' : '';
          return '<article class="rt-artifact"><div class="rt-artifact-head"><div><h4>' + escapeHTML(artifact.label) + '</h4><code>' + escapeHTML(artifact.revision || 'revision 없음') + '</code></div><span class="rt-source">출처</span></div>' +
            '<dl class="rt-source-grid"><div><dt>만든 모델</dt><dd>' + (artifact.sourceModel ? '<code>' + escapeHTML(artifact.sourceModel) + '</code>' : '<small>기록 없음</small>') + '</dd></div><div><dt>만든 프로필</dt><dd>' + (artifact.sourceProfile ? '<code>' + escapeHTML(artifact.sourceProfile) + '</code>' : '<small>기록 없음</small>') + '</dd></div></dl>' +
            files + (artifact.text ? '<details class="rt-text"><summary>본문 보기</summary><pre>' + escapeHTML(artifact.text) + '</pre>' + (artifact.textTruncated ? '<p class="rt-muted">본문이 길어 일부만 표시해요.</p>' : '') + '</details>' : '<p class="rt-muted">저장된 본문이 없어요.</p>') + '</article>';
        }).join('') || '<p class="rt-muted">텍스트 산출물 기록이 없어요.</p>';
        const calls = state.text.calls.length ? '<div class="rt-calls-wrap"><h4>최근 호출</h4><table class="rt-calls"><thead><tr><th>역할</th><th>단계</th><th>모델</th><th>프로필</th><th>결과</th><th>참조</th></tr></thead><tbody>' + state.text.calls.map((call) => '<tr><td>' + escapeHTML(call.task || '기록 없음') + '</td><td>' + escapeHTML(call.stage || '–') + '</td><td><code>' + escapeHTML(call.model || '–') + '</code></td><td><code>' + escapeHTML(call.profile || '–') + '</code></td><td>' + (call.ok === true ? '<span class="rt-ok">성공</span>' : call.ok === false ? '<span class="rt-bad">실패</span>' : '<small>기록 없음</small>') + '</td><td><code>' + escapeHTML(call.ref || '–') + '</code></td></tr>').join('') + '</tbody></table></div>' : '<p class="rt-muted">최근 호출 기록이 없어요.</p>';
        textHTML = '<div class="rt-asset-section"><div class="rt-asset-title"><h3>텍스트 기록</h3><span>' + state.text.artifacts.length + '개 산출물 · ' + state.text.calls.length + '건 호출</span></div>' + selection + '<p class="rt-note">산출물의 출처는 만든 당시 서버 기록이에요. 지금 선택 설정과 섞지 않았어요.</p>' + artifacts + calls + '</div>';
      }
      setHTML(host, '<div class="rt-asset-section"><div class="rt-asset-title"><h3>공정 단계</h3><span>' + stages.length + '단계</span></div><div class="rt-asset-list">' + stageHTML + '</div></div>' + textHTML + (state.textConfig && state.textConfig.enabled === false ? '<p class="rt-muted">텍스트 공정이 설정에서 꺼져 있어요.</p>' : ''));
    }

    function renderJobs() {
      const host = $('[data-jobs]');
      if (!host) return;
      const jobs = normalizeJobs(state.detail && state.detail.jobs);
      if (!jobs.length) {
        setHTML(host, '<div class="crow-empty">이 캐릭터의 작업 기록이 아직 없어요.</div>');
        return;
      }
      setHTML(host, '<div class="jrow head"><span>작업</span><span>상태</span><span>목표</span><span>시작</span><span>끝</span></div>' + jobs.map((job) =>
        '<div class="jrow"><span class="j-name"><b>' + escapeHTML(job.id || '작업 ID 없음') + '</b><small>' + escapeHTML(job.characterId) + '</small></span><span>' + pill(job.label, job.tone) + '</span><span class="muted">' + escapeHTML(job.until || '기록 없음') + '</span><span class="muted">' + escapeHTML(dateLabel(job.createdAt)) + '</span><span class="muted">' + escapeHTML(dateLabel(job.finishedAt)) + '</span></div>').join(''));
    }

    function renderBanner() {
      const host = $('[data-banner]');
      if (!host) return;
      let html = '';
      let tone = '';
      if (state.offline) {
        html = '<span class="rt-dot"></span><span><b>서버 연결이 끊겼어요.</b> 마지막 기록을 그대로 보여 주는 중이에요. 실행·결재·생성은 다시 연결될 때까지 잠겨 있어요.</span><button type="button" class="btn btn--sm" data-runtime-retry>다시 연결</button>';
        tone = 'rt-banner--bad';
      } else if (state.stale) {
        html = '<span class="rt-dot"></span><span><b>실시간 연결이 잠시 끊겼어요.</b> 주기적으로 서버 기록을 다시 확인해요. 마지막 갱신 ' + escapeHTML(nowLabel() || '기록 없음') + '.</span><button type="button" class="btn btn--sm" data-runtime-retry>지금 확인</button>';
        tone = 'rt-banner--warn';
      } else if (state.detail && text(state.detail.stateError)) {
        html = '<span class="rt-dot"></span><span><b>상태 파일을 읽지 못했어요.</b> ' + escapeHTML(state.detail.stateError) + ' 실행은 잠겨 있어요.</span>';
        tone = 'rt-banner--bad';
      } else if (state.detailError) {
        html = '<span class="rt-dot"></span><span><b>캐릭터 기록을 다시 읽지 못했어요.</b> ' + escapeHTML(state.detailError) + '</span><button type="button" class="btn btn--sm" data-runtime-retry>다시 확인</button>';
        tone = 'rt-banner--bad';
      } else if (state.feedback) {
        html = '<span class="rt-dot"></span><span>' + escapeHTML(state.feedback.text) + '</span>';
        tone = state.feedback.tone === 'bad' ? 'rt-banner--bad' : 'rt-banner--ok';
      } else if (state.busy) {
        html = '<span class="rt-dot"></span><span>서버 응답을 기다리는 중이에요. 중복 입력은 잠시 막아 둘게요.</span>';
        tone = 'rt-banner--warn';
      }
      show(host, !!html);
      host.className = 'banner rt-banner ' + tone;
      setHTML(host, html);
    }

    function renderGrid() {
      const host = $('[data-grid]');
      if (!host) return;
      if (!state.detail) {
        setHTML(host, emptyBlock(state.detailLoading ? '단계 기록을 불러오는 중이에요.' : (state.detailError || '캐릭터를 선택하면 단계가 표시돼요.')));
        return;
      }
      const detail = state.detail;
      const pendingIds = new Map(pendingGatesFor(detail, state.graph).map((gate) => [gate.id, gate]));
      const gateMap = gateRecords(detail);
      const header = '<div class="row head"><div class="cell">단계</div><div class="cell">상태</div><div class="cell">기록</div><div class="cell">관문</div><div class="cell">의존</div><div class="cell">동작</div></div>';
      const rows = state.graph.stages.map((definition) => {
        const row = translateStage(stageRecord(detail.stages, definition.id), definition);
        const pending = definition.gate && pendingIds.get(definition.gate);
        const dependencies = definition.deps.map((gate) => '<span class="rt-chip rt-chip--gate">' + escapeHTML(gate) + '</span>')
          .concat(definition.needs.map((stage) => '<span class="rt-chip">needs ' + escapeHTML(stage) + '</span>'))
          .concat(definition.after.map((stage) => '<span class="rt-chip">after ' + escapeHTML(stage) + '</span>')).join('');
        const actions = [];
        if (pending) actions.push('<button type="button" class="btn btn--sm" data-runtime-gate data-gate="' + escapeHTML(pending.id) + '"' + (state.offline || state.busy ? ' disabled' : '') + '>결재 열기</button>');
        if (definition.implemented) actions.push('<button type="button" class="btn btn--sm" data-runtime-run-stage data-stage="' + escapeHTML(definition.id) + '"' + (!canMutate() || text(detail.stateError) ? ' disabled' : '') + '>이 단계까지</button>');
        return '<div class="row body rt-stage-row st-' + escapeHTML(row.state) + '" data-runtime-stage-row="' + escapeHTML(definition.id) + '">' +
          '<div class="cell c-team"><span class="team-name"><b>' + escapeHTML(definition.id) + '</b><small>' + escapeHTML(definition.name) + '</small></span></div>' +
          '<div class="cell">' + pill(row.label, row.tone) + '</div>' +
          '<div class="cell c-now"><span class="now-main">' + (row.rev ? escapeHTML(row.rev) : 'revision 없음') + '</span>' + (row.error ? '<span class="now-sub is-bad">' + escapeHTML(row.error) + '</span>' : (row.raw ? '<span class="now-sub">' + escapeHTML(row.raw) + '</span>' : '')) + '</div>' +
          '<div class="cell c-now">' + (definition.gate ? '<button type="button" class="rt-gate-link" data-runtime-gate data-gate="' + escapeHTML(definition.gate) + '"' + (state.offline || state.busy ? ' disabled' : '') + '>' + escapeHTML(definition.gate) + '</button><span class="now-sub">' + escapeHTML(statusOf(gateMap.get(definition.gate)) || (pendingIds.has(definition.gate) ? 'AWAITING_HUMAN' : '상태 없음')) + '</span>' : '<span class="muted">–</span>') + '</div>' +
          '<div class="cell rt-deps">' + (dependencies || '<span class="muted">–</span>') + '</div>' +
          '<div class="cell rt-actions">' + (actions.join('') || '<span class="muted">–</span>') + '</div>' +
          '</div>';
      }).join('');
      setHTML(host, header + rows);
    }

    function gateRecords(detail) {
      const result = new Map();
      const gates = detail && detail.gates;
      if (Array.isArray(gates)) gates.forEach((entry) => { if (entry && entry.id) result.set(text(entry.id), entry); });
      else if (object(gates)) Object.keys(gates).forEach((id) => result.set(id, gates[id]));
      return result;
    }
    function edgePath(source, target) {
      if (!source || !target) return '';
      const x1 = source.x;
      const y1 = source.y;
      const x2 = target.x;
      const y2 = target.y;
      const bend = Math.max(30, Math.abs(x2 - x1) * 0.42);
      return 'M' + x1 + ' ' + y1 + ' C' + (x1 + bend) + ' ' + y1 + ' ' + (x2 - bend) + ' ' + y2 + ' ' + x2 + ' ' + y2;
    }
    function renderFloor() {
      const host = $('[data-floor]');
      if (!host) return;
      if (!state.detail) {
        setHTML(host, '<div class="rt-floor-empty">' + escapeHTML(state.detailLoading ? '공장 기록을 불러오는 중이에요.' : '캐릭터를 선택하면 실제 단계가 공장 현장에 표시돼요.') + '</div>');
        return;
      }
      if (!state.graph.stages.length) {
        setHTML(host, '<div class="rt-floor-empty">서버가 단계 그래프를 주지 않았어요.</div>');
        return;
      }
      const detail = state.detail;
      const scene = sceneLayout(state.graph);
      const pending = new Map(pendingGatesFor(detail, state.graph).map((gate) => [gate.id, gate]));
      const gates = gateRecords(detail);
      scene.nodes.forEach((node) => {
        if (node.kind === 'stage') {
          node.state = translateStage(stageRecord(detail.stages, node.id), state.graph.byStage.get(node.id)).state;
        } else {
          const record = gates.get(node.id);
          const p = pending.get(node.id);
          node.state = p ? 'pending' : (record ? gateState(statusOf(record)) : 'unknown');
        }
      });
      const laneLabels = scene.lanes.map((lane) => '<text class="rt-lane-label" x="18" y="' + lane.y + '">' + escapeHTML(lane.label) + '</text>').join('');
      const edges = scene.edges.map((edge) => '<path d="' + edgePath(edge.source, edge.target) + '" class="rt-edge rt-edge--' + escapeHTML(edge.kind) + '"><title>' + escapeHTML(edge.from + ' → ' + edge.to + ' · ' + edge.kind) + '</title></path>').join('');
      const nodes = scene.nodes.map((node) => {
        if (node.kind === 'gate') {
          const gateLabels = { pending: '사람 확인', approved: '승인', rejected: '반려', running: '실행 중', waiting: '대기', skipped: '건너뜀', unknown: '상태 없음' };
          const label = gateLabels[node.state] || '상태 없음';
          return '<g class="rt-node rt-node--gate g-' + escapeHTML(node.state) + '" data-runtime-gate-node="' + escapeHTML(node.id) + '" tabindex="0" role="button" aria-label="' + escapeHTML(node.id + ' ' + node.label + ' · ' + label + ' 결재 열기') + '" transform="translate(' + node.x + ' ' + node.y + ')"><rect x="-46" y="-15" width="92" height="30" rx="15"></rect><text class="rt-node-code" text-anchor="middle" y="-2">' + escapeHTML(node.id) + '</text><text class="rt-node-state" text-anchor="middle" y="10">' + escapeHTML(label) + '</text><title>' + escapeHTML(node.id + ' · ' + node.label + ' · ' + label) + '</title></g>';
        }
        const tr = translateStage(stageRecord(detail.stages, node.id), state.graph.byStage.get(node.id));
        const rev = tr.rev ? tr.rev : 'revision 없음';
        return '<g class="rt-node rt-node--stage st-' + escapeHTML(node.state) + '" data-runtime-stage="' + escapeHTML(node.id) + '" tabindex="0" role="button" aria-label="' + escapeHTML(node.id + ' ' + node.label + ' · ' + tr.label + ' · ' + rev) + '" transform="translate(' + node.x + ' ' + node.y + ')">' +
          '<rect x="-58" y="-36" width="116" height="72" rx="16"></rect>' +
          '<rect class="rt-node-lamp" x="-48" y="-26" width="7" height="7" rx="3.5"></rect>' +
          '<text class="rt-node-id" x="0" y="-8" text-anchor="middle">' + escapeHTML(node.id) + '</text>' +
          '<text class="rt-node-name" x="0" y="9" text-anchor="middle">' + escapeHTML(node.label.slice(0, 15)) + '</text>' +
          '<text class="rt-node-rev" x="0" y="24" text-anchor="middle">' + escapeHTML(tr.label + ' · ' + rev) + '</text>' +
          '<title>' + escapeHTML(node.id + ' · ' + node.label + ' · ' + tr.label + ' · ' + rev) + '</title></g>';
      }).join('');
      const focus = '<div class="rt-floor-head"><div><b>실제 공정 그래프</b><small>서버가 준 단계와 의존 경로만 그려요. 시계로 진행률을 만들지 않아요.</small></div><span class="rt-legend"><i class="ok"></i>승인 <i class="run"></i>실행 <i class="wait"></i>대기 <i class="human"></i>사람 <i class="bad"></i>실패</span></div>';
      setHTML(host, '<div class="rt-floor-stage">' + focus + '<svg class="rt-svg" style="min-width:' + scene.width + 'px;width:' + scene.width + 'px;height:' + scene.height + 'px" viewBox="0 0 ' + scene.width + ' ' + scene.height + '" preserveAspectRatio="xMidYMid meet" role="group" aria-label="실제 캐릭터 공정 단계와 관문">' +
        '<defs><pattern id="rt-grid" width="28" height="28" patternUnits="userSpaceOnUse"><path d="M28 0H0V28" fill="none"></path></pattern></defs>' +
        '<rect class="rt-svg-bg" x="0" y="0" width="' + scene.width + '" height="' + scene.height + '" fill="url(#rt-grid)"></rect>' +
        laneLabels + edges + nodes + '</svg></div>');
      const hud = $('[data-fl-hud]');
      if (hud) hud.innerHTML = '<span>단계 <b>' + state.graph.stages.length + '</b></span><span>관문 <b>' + state.graph.gates.length + '</b></span><span>사람 대기 <b>' + pending.size + '</b></span>';
      setText($('[data-job-hint]'), state.jobId ? '작업 ' + state.jobId + ' · ' + (state.jobDetail && state.jobDetail.status ? state.jobDetail.status : '서버 기록') : '서버 기록 기준');
      const link = state.jobId ? '#job/' + encodeURIComponent(state.jobId) + (state.detailId ? '?character=' + encodeURIComponent(state.detailId) : '') : '#chars';
      const floorLink = state.jobId ? '#job/' + encodeURIComponent(state.jobId) + '/floor' + (state.detailId ? '?character=' + encodeURIComponent(state.detailId) : '') : '#chars';
      const tableTab = $('[data-sub-tab="table"]');
      const floorTab = $('[data-sub-tab="floor"]');
      if (tableTab) tableTab.setAttribute('href', link);
      if (floorTab) floorTab.setAttribute('href', floorLink);
    }

    function renderSide() {
      const detail = state.detail;
      const pending = pendingGatesFor(detail || {}, state.graph);
      const gateHost = $('[data-gates]');
      if (gateHost) {
        setHTML(gateHost, pending.map((gate) => '<div class="gate"><div><div class="gate-card"><div class="gate-top"><span>' + escapeHTML(gate.id + (gate.stage ? ' · ' + gate.stage : '')) + '</span><span class="wait">' + escapeHTML(gate.status || 'AWAITING_HUMAN') + '</span></div><h3>' + escapeHTML(gate.title) + '</h3><p class="gate-impact">서버가 사람 확인을 기다려요. 후보·검수·결정은 실제 관문 화면에서 해요.</p><div class="gate-row"><button type="button" class="btn btn--sm btn--primary" data-runtime-gate data-gate="' + escapeHTML(gate.id) + '"' + (state.offline || state.busy ? ' disabled' : '') + '>검토·결정</button></div></div></div></div>').join(''));
      }
      show($('[data-gate-empty]'), !pending.length);
      setText($('[data-gate-count]'), pending.length ? pending.length + '건' : '0건');
      const gateEmpty = $('[data-gate-empty]');
      if (gateEmpty && !pending.length) setText(gateEmpty, detail ? '서버에 사람 확인을 기다리는 관문이 없어요.' : '캐릭터를 선택하면 실제 결재함을 보여 줘요.');

      const events = [];
      const jobs = normalizeJobs(detail && detail.jobs);
      jobs.forEach((job) => {
        const tone = job.tone === 'ok' ? 'done' : (job.tone === 'bad' ? 'human' : (job.tone === 'warn' ? 'gate' : ''));
        events.push({ kind: tone, text: '<b>작업 ' + escapeHTML(jobIdentity(job)) + '</b> · ' + escapeHTML(job.label) + (job.until ? ' · 목표 ' + escapeHTML(job.until) : ''), time: dateLabel(job.createdAt) });
      });
      const records = gateRecords(detail);
      records.forEach((record, id) => {
        const raw = statusOf(record);
        if (!raw || raw === 'PENDING') return;
        events.push({ kind: gateState(raw) === 'pending' ? 'gate' : (gateState(raw) === 'approved' ? 'done' : (gateState(raw) === 'rejected' ? 'human' : '')), text: '<b>관문 ' + escapeHTML(id) + '</b> · ' + escapeHTML(raw) + (record && record.rev ? ' · ' + escapeHTML(record.rev) : ''), time: '' });
      });
      const logs = [];
      if (state.jobError) events.push({ kind: 'human', text: '<b>작업 로그</b> · ' + escapeHTML(state.jobError), time: '' });
      if (state.jobDetail) {
        const rawLog = state.jobDetail.log || state.jobDetail.logs;
        if (Array.isArray(rawLog)) {
          rawLog.slice(-20).forEach((line) => logs.push(text(line && (line.message || line.text || line))));
        } else if (typeof rawLog === 'string') {
          rawLog.split('\n').slice(-20).forEach((line) => { if (line.trim()) logs.push(line); });
        }
      }
      logs.forEach((line) => events.push({ kind: 'log', text: escapeHTML(line), time: '' }));
      const evHost = $('[data-evs]');
      if (evHost) {
        setHTML(evHost, events.map((event) => '<li class="ev ' + (event.kind ? 'k-' + event.kind : '') + '"><span class="dot"></span><span>' + event.text + '</span><span class="num">' + escapeHTML(event.time || '') + '</span></li>').join(''));
      }
      show($('[data-ev-empty]'), !events.length);
      const evEmpty = $('[data-ev-empty]');
      if (evEmpty && !events.length) setText(evEmpty, detail ? '서버에 저장된 최근 작업·관문 기록이 없어요.' : '캐릭터를 선택하면 실제 작업·관문 기록을 보여 줘요.');
      setText($('[data-ev-count]'), events.length ? events.length + '건' : '0건');

      const problems = [];
      if (detail) {
        if (text(detail.stateError)) problems.push({ kind: 'human', text: '<b>상태 파일 손상</b><span class="prob-sub">' + escapeHTML(detail.stateError) + '</span>' });
        state.graph.stages.forEach((definition) => {
          const row = translateStage(stageRecord(detail.stages, definition.id), definition);
          if (row.state === 'failed') problems.push({ kind: 'bad', text: '<b>' + escapeHTML(row.id + ' ' + row.name) + '</b><span class="prob-sub">' + escapeHTML(row.error || row.raw || '실패 기록') + '</span>' });
        });
        jobs.forEach((job) => {
          if (job.state === 'failed') problems.push({ kind: 'bad', text: '<b>작업 ' + escapeHTML(jobIdentity(job)) + '</b><span class="prob-sub">실패 상태</span>' });
        });
      }
      const probHost = $('[data-probs]');
      if (probHost) {
        setHTML(probHost, problems.map((problem) => '<li class="prob ' + (problem.kind === 'human' ? 'is-human' : '') + '"><span class="dot"></span><span class="prob-text">' + problem.text + '</span><span></span></li>').join(''));
      }
      show($('[data-prob-empty]'), !problems.length);
      const probEmpty = $('[data-prob-empty]');
      if (probEmpty && !problems.length) setText(probEmpty, detail ? '서버 기록에 실패나 상태 손상이 없어요.' : '캐릭터를 선택하면 실제 문제 기록을 보여 줘요.');
      setText($('[data-prob-count]'), problems.length ? problems.length + '건' : '0건');
      const logCount = $('[data-log-count]');
      if (logCount) setText(logCount, logs.length ? logs.length + '줄' : '기록 없음');
      const logList = $('[data-log-list]');
      if (logList) setHTML(logList, logs.map((line) => '<li><span></span><b>작업</b><span>' + escapeHTML(line) + '</span></li>').join(''));
    }

    function renderCrumbs() {
      const host = $('[data-crumbs]');
      if (!host) return;
      if (state.route.view === 'chars') { show(host, false); return; }
      const name = state.detail ? characterLabel(state.detail) : (state.route.characterId || '캐릭터');
      let html = '<a href="#chars">캐릭터</a><span class="crumb-char"><b>' + escapeHTML(name) + '</b></span>';
      if (state.route.view === 'job' && state.jobId) html += '<span class="crumb-job"><code>' + escapeHTML(state.jobId) + '</code></span>';
      setHTML(host, html);
      show(host, true);
    }
    function renderLive() {
      const host = $('[data-live]');
      if (!host) return;
      let html = '<span class="dot"></span>기록 대기';
      if (state.offline) html = '<span class="dot is-bad"></span>서버 연결 끊김 · 마지막 기록';
      else if (state.stale) html = '<span class="dot is-warn"></span>실시간 재연결 중';
      else if (state.busy) html = '<span class="dot is-on"></span>서버 응답 대기';
      else if (state.sseOk) html = '<span class="dot is-on"></span>실시간 연결';
      else if (state.lastUpdated) html = '<span class="dot is-warn"></span>주기 확인 중';
      setHTML(host, html);
    }
    function renderNav() {
      const nav = root.querySelectorAll('[data-nav]');
      Array.prototype.forEach.call(nav, (link) => {
        const active = link.getAttribute('data-nav') === 'chars' && state.route.view === 'chars';
        link.classList.toggle('is-active', active);
        if (active) link.setAttribute('aria-current', 'page');
        else link.removeAttribute('aria-current');
      });
      const workroom = $('[data-workroom-tab]');
      if (workroom) workroom.setAttribute('href', '#chars');
      const tabs = $('[data-char-tabs]');
      if (tabs) setHTML(tabs, '<button type="button" class="ftab' + (state.form.open ? ' is-on' : '') + '" data-runtime-new>새 캐릭터</button>');
      const pending = state.detail ? pendingGatesFor(state.detail, state.graph).length : projectCharacters().reduce((sum, character) => sum + pendingFor(character).length, 0);
      setText($('[data-workroom-count]'), pending ? String(pending) : '');
      const titleName = state.detail && state.route.view !== 'chars' ? characterLabel(state.detail) : '캐릭터';
      doc.title = (pending ? '(' + pending + ') ' : '') + '캐릭터 공장 · ' + titleName;
    }
    function render() {
      if (state.destroyed) return;
      if (body) {
        body.dataset.view = state.route.view;
        if (state.route.sub) body.dataset.sub = state.route.sub;
        else delete body.dataset.sub;
      }
      renderLive();
      renderNav();
      renderCrumbs();
      renderKpis();
      renderChars();
      renderCharHead();
      renderControls();
      renderAssets();
      renderJobs();
      renderBanner();
      renderGrid();
      renderFloor();
      renderSide();
    }

    function showDrawer(content, label, opener) {
      const drawer = $('[data-drawer]');
      const scrim = $('[data-scrim]');
      const bodyHost = $('[data-drawer-body]');
      if (!drawer || !bodyHost) return;
      state.returnFocus = doc.activeElement && doc.activeElement.focus ? doc.activeElement : null;
      state.drawerOpener = opener || null;
      bodyHost.innerHTML = content;
      drawer.setAttribute('aria-label', label);
      drawer.hidden = false;
      if (scrim) scrim.hidden = false;
      drawer.classList.add('is-open');
      if (scrim) scrim.classList.add('is-open');
      if (body) body.classList.add('rt-drawer-open');
      const background = $('.wrap');
      if (background) background.inert = true;
      const close = drawer.querySelector('[data-close]');
      if (close) close.focus();
    }
    function closeDrawer(restore) {
      const drawer = $('[data-drawer]');
      const scrim = $('[data-scrim]');
      if (!drawer || drawer.hidden) return;
      drawer.classList.remove('is-open');
      if (scrim) { scrim.classList.remove('is-open'); scrim.hidden = true; }
      drawer.hidden = true;
      if (body) body.classList.remove('rt-drawer-open');
      const background = $('.wrap');
      if (background) background.inert = false;
      const bodyHost = $('[data-drawer-body]');
      if (bodyHost) bodyHost.innerHTML = '';
      if (restore !== false) {
        let target = state.returnFocus && state.returnFocus.isConnected !== false ? state.returnFocus : null;
        if (!target && state.drawerOpener) {
          const attribute = state.drawerOpener.gate ? 'data-runtime-gate' : 'data-runtime-stage';
          const value = state.drawerOpener.gate || state.drawerOpener.stage;
          const all = root.querySelectorAll('[' + attribute + ']');
          for (let index = 0; index < all.length; index += 1) {
            const candidate = all[index];
            const actual = candidate.getAttribute(attribute === 'data-runtime-gate' ? 'data-gate' : attribute);
            if (actual === value && candidate.offsetParent !== null) { target = candidate; break; }
          }
        }
        if (target && target.isConnected !== false && target.focus) target.focus();
      }
      state.returnFocus = null;
      state.drawerOpener = null;
      if (restore !== false) refresh();
    }
    function openGate(gateId) {
      const id = text(gateId).trim();
      const characterId = text(state.detail && (state.detail.id || state.detailId) || state.route.characterId);
      if (!id || !characterId) return;
      const definition = state.graph.byGate.get(id);
      const title = definition ? definition.title : id;
      const stage = definition && definition.stage ? definition.stage : '';
      const src = gateUrl(characterId, id, apiBase) + '&embedded=1';
      showDrawer('<div class="dr-head"><h2>' + escapeHTML(title) + '</h2><span class="rt-pill t-warn"><span class="rt-dot"></span>' + escapeHTML(id) + (stage ? ' · ' + escapeHTML(stage) : '') + '</span></div>' +
        '<p class="dr-note">후보 선택·검수·승인은 아래 실제 관문 화면에서 직접 결정해요. 이 화면은 기본 승인을 대신 보내지 않아요.</p>' +
        '<iframe class="rt-gate-frame" src="' + escapeHTML(src) + '" title="' + escapeHTML(title + ' 실제 관문 화면') + '"></iframe>', title + ' 결재', { gate: id });
      const frame = $('.rt-gate-frame');
      frame.addEventListener('load', function () {
        const child = frame.contentDocument;
        if (!child) return;
        child.addEventListener('keydown', function (event) {
          if (event.key === 'Escape') { event.preventDefault(); closeDrawer(); }
          if (event.key === 'Tab') {
            const choices = Array.from(child.querySelectorAll('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex="0"]')).filter((el) => el.offsetParent !== null);
            const boundary = event.shiftKey ? choices[0] : choices[choices.length - 1];
            if (child.activeElement === boundary) {
              event.preventDefault();
              const close = $('[data-drawer] [data-close]');
              if (close) close.focus();
            }
          }
        });
      }, {once:true});
    }
    function openStageDrawer(stageId) {
      const definition = state.graph.byStage.get(stageId);
      if (!definition || !state.detail) return;
      const row = translateStage(stageRecord(state.detail.stages, stageId), definition);
      const pending = definition.gate ? pendingGatesFor(state.detail, state.graph).find((gate) => gate.id === definition.gate) : null;
      const deps = definition.deps.concat(definition.needs, definition.after).map((dep) => '<span class="rt-chip">' + escapeHTML(dep) + '</span>').join('') || '<span class="muted">의존 없음</span>';
      const actions = [];
      if (pending) actions.push('<button type="button" class="btn btn--primary" data-runtime-gate data-gate="' + escapeHTML(pending.id) + '"' + (state.offline || state.busy ? ' disabled' : '') + '>결재 화면 열기</button>');
      if (definition.implemented) actions.push('<button type="button" class="btn" data-runtime-run-stage data-stage="' + escapeHTML(definition.id) + '"' + (!canMutate() || text(state.detail.stateError) ? ' disabled' : '') + '>이 단계까지 실행</button>');
      showDrawer('<div class="dr-head"><h2>' + escapeHTML(definition.name) + '</h2><span class="rt-pill t-' + escapeHTML(row.tone) + '"><span class="rt-dot"></span>' + escapeHTML(row.label) + '</span></div>' +
        '<dl class="dr-meta"><dt>단계</dt><dd><code>' + escapeHTML(definition.id) + '</code></dd><dt>서버 상태</dt><dd>' + escapeHTML(row.raw || '상태 없음') + '</dd><dt>revision</dt><dd>' + escapeHTML(row.rev || '기록 없음') + '</dd><dt>관문</dt><dd>' + escapeHTML(definition.gate || '없음') + '</dd><dt>의존</dt><dd class="rt-deps">' + deps + '</dd></dl>' +
        (row.error ? '<p class="dr-warn">' + escapeHTML(row.error) + '</p>' : '') + (actions.length ? '<div class="dr-actions">' + actions.join('') + '</div>' : ''), definition.name + ' 단계', { stage: definition.id });
    }

    async function createCharacter(form) {
      if (!canMutate()) return;
      const slug = form.querySelector('[data-runtime-slug]');
      const brief = form.querySelector('[data-runtime-brief]');
      state.form.slug = slug ? slug.value : state.form.slug;
      state.form.brief = brief ? brief.value : state.form.brief;
      let payload;
      try {
        payload = createCharacterRequest(state.form.slug, state.form.brief);
      } catch (error) {
        state.form.error = error.message;
        render();
        return;
      }
      state.form.error = null;
      state.busy = true;
      state.feedback = null;
      syncCreateForm(form);
      render();
      try {
        const data = await request('POST', '/api/runtime/characters', { body: payload });
        state.busy = false;
        state.offline = false;
        const characterId = text(data && (data.characterId || data.id));
        if (!characterId) throw new Error('서버가 캐릭터 ID를 돌려주지 않았어요.');
        state.feedback = { tone: 'ok', text: '캐릭터를 등록했어요. 실행은 원하는 단계에서 직접 시작해 주세요.' };
        state.form.open = false;
        state.form.slug = '';
        state.form.brief = '';
        if (typeof location !== 'undefined') location.hash = '#char/' + encodeURIComponent(characterId);
        await refresh();
      } catch (error) {
        state.busy = false;
        if (error.network) state.offline = true;
        state.form.error = messageFor(error);
        state.feedback = { tone: 'bad', text: messageFor(error) };
        render();
      }
    }
    async function startRun(until, confirm) {
      if (!canMutate() || !state.detail || state.detail.job || state.detail.stateError) return;
      let payload;
      try {
        payload = runRequest(state.detail.id || state.detailId, until, confirm || []);
      } catch (error) {
        state.feedback = { tone: 'bad', text: error.message };
        render();
        return;
      }
      state.busy = true;
      state.feedback = null;
      render();
      try {
        const data = await request('POST', '/api/jobs', { body: payload });
        state.busy = false;
        state.offline = false;
        const job = data && (data.job || data);
        state.feedback = { tone: 'ok', text: '실제 작업을 요청했어요' + (jobIdentity(job) ? ' · ' + jobIdentity(job) : '') + '. 진행 상황은 서버 기록을 따릅니다.' };
        await refresh();
      } catch (error) {
        state.busy = false;
        if (error.network) state.offline = true;
        state.feedback = { tone: 'bad', text: messageFor(error) };
        render();
        refresh();
      }
    }
    function retry() {
      state.feedback = null;
      refresh();
    }
    function focusables(container) {
      return Array.prototype.slice.call(container.querySelectorAll('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),iframe,[tabindex]:not([tabindex="-1"])')).filter((element) => element.offsetParent !== null || element.tagName === 'IFRAME');
    }
    function onClick(event) {
      const target = event.target;
      if (!target || !target.closest) return;
      if (target.closest('[data-text-pipeline-root], .ftp-layer')) return;
      if (target.closest('[data-workroom-tab]')) {
        event.preventDefault();
        const waiting = pendingGatesFor(state.detail || {}, state.graph);
        if (waiting.length) openGate(waiting[0].id);
        else if (typeof location !== 'undefined') location.hash = '#chars';
        return;
      }
      if (target.closest('[data-scrim]')) { closeDrawer(); return; }
      if (target.closest('[data-close]')) { closeDrawer(); return; }
      const stageNode = target.closest('[data-runtime-stage]');
      if (stageNode) { event.preventDefault(); openStageDrawer(stageNode.getAttribute('data-runtime-stage')); return; }
      const gateNode = target.closest('[data-runtime-gate-node]');
      if (gateNode) { event.preventDefault(); openGate(gateNode.getAttribute('data-runtime-gate-node')); return; }
      const gate = target.closest('[data-runtime-gate]');
      if (gate) { event.preventDefault(); openGate(gate.getAttribute('data-gate')); return; }
      const runStage = target.closest('[data-runtime-run-stage]');
      if (runStage) { event.preventDefault(); startRun(runStage.getAttribute('data-stage'), []); return; }
      const held = target.closest('[data-runtime-confirm-held]');
      if (held) {
        event.preventDefault();
        const stage = held.getAttribute('data-stage');
        if (stage) startRun(stage, [stage]);
        return;
      }
      if (target.closest('[data-runtime-run]')) {
        event.preventDefault();
        const select = $('[data-runtime-until]');
        const until = select ? select.value : state.until;
        startRun(until, []);
        return;
      }
      if (target.closest('[data-runtime-retry]')) { event.preventDefault(); retry(); return; }
      if (target.closest('[data-runtime-new]')) { event.preventDefault(); state.form.open = true; state.form.dismissed = false; state.form.error = null; render(); return; }
      if (target.closest('[data-runtime-close-form]')) { event.preventDefault(); state.form.open = false; state.form.dismissed = true; state.form.error = null; render(); return; }
      const openJob = target.closest('[data-runtime-open-job]');
      if (openJob) {
        event.preventDefault();
        const jobId = openJob.getAttribute('data-job');
        const characterId = state.detailId || state.route.characterId;
        if (jobId && characterId && typeof location !== 'undefined') {
          location.hash = '#job/' + encodeURIComponent(jobId) + '/floor?character=' + encodeURIComponent(characterId);
        }
      }
    }
    function onInput(event) {
      const target = event.target;
      if (!target || !target.matches) return;
      if (target.matches('[data-runtime-slug]')) state.form.slug = target.value;
      else if (target.matches('[data-runtime-brief]')) state.form.brief = target.value;
    }
    function onChange(event) {
      const target = event.target;
      if (target && target.matches && target.matches('[data-runtime-until]')) state.until = target.value;
    }
    function onSubmit(event) {
      const form = event.target;
      if (!form || !form.matches || !form.matches('[data-runtime-create-form]')) return;
      event.preventDefault();
      createCharacter(form);
    }
    function onKeyDown(event) {
      const target = event.target;
      if (!target || !target.closest) return;
      if (event.key === 'Escape') {
        const drawer = $('[data-drawer]');
        if (drawer && !drawer.hidden) { event.preventDefault(); closeDrawer(); }
        return;
      }
      if (event.key !== 'Tab') {
        if ((event.key === 'Enter' || event.key === ' ') && target.matches && target.matches('[data-runtime-stage],[data-runtime-gate-node]')) {
          event.preventDefault();
          target.click();
        }
        return;
      }
      const drawer = $('[data-drawer]');
      if (!drawer || drawer.hidden) return;
      const list = focusables(drawer);
      if (!list.length) return;
      const first = list[0];
      const last = list[list.length - 1];
      if (event.shiftKey && doc.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && doc.activeElement === last) { event.preventDefault(); first.focus(); }
    }
    function onHashChange() {
      const route = routeNow();
      updateRoute(route);
      if (route.view === 'chars') {
        state.detail = null;
        state.detailId = null;
        state.detailLoading = false;
        state.detailError = null;
        state.text = null;
        state.textSeq += 1;
        if (state.textController) state.textController.abort();
        state.jobDetail = null;
        state.jobId = null;
        state.jobSeq += 1;
        if (state.jobController) state.jobController.abort();
        render();
      } else {
        const id = characterIdForRoute(route);
        if (id) loadDetail(id);
        else refresh();
      }
      render();
    }
    function onOffline() {
      state.offline = true;
      render();
    }
    function onOnline() {
      refresh();
    }
    function onVisibility() {
      if (doc.visibilityState === 'visible') refresh();
    }

    doc.addEventListener('click', onClick);
    doc.addEventListener('input', onInput);
    doc.addEventListener('change', onChange);
    doc.addEventListener('submit', onSubmit);
    doc.addEventListener('keydown', onKeyDown);
    if (typeof window !== 'undefined') {
      window.addEventListener('hashchange', onHashChange);
      window.addEventListener('popstate', onHashChange);
      window.addEventListener('offline', onOffline);
      window.addEventListener('online', onOnline);
    }
    doc.addEventListener('visibilitychange', onVisibility);
    const poll = setInterval(function () { if (!state.destroyed && doc.visibilityState !== 'hidden') refresh(); }, 30000);

    updateRoute(state.route);
    render();
    refresh().finally(startEvents);

    return {
      refresh: refresh,
      destroy: function () {
        if (state.destroyed) return;
        closeDrawer(false);
        state.destroyed = true;
        clearTimers();
        clearInterval(poll);
        if (state.eventSource) state.eventSource.close();
        [state.refreshController, state.detailController, state.textController, state.jobController].forEach((controller) => {
          if (controller) controller.abort();
        });
        doc.removeEventListener('click', onClick);
        doc.removeEventListener('input', onInput);
        doc.removeEventListener('change', onChange);
        doc.removeEventListener('submit', onSubmit);
        doc.removeEventListener('keydown', onKeyDown);
        doc.removeEventListener('visibilitychange', onVisibility);
        if (typeof window !== 'undefined') {
          window.removeEventListener('hashchange', onHashChange);
          window.removeEventListener('popstate', onHashChange);
          window.removeEventListener('offline', onOffline);
          window.removeEventListener('online', onOnline);
        }
        if (body) {
          body.classList.remove('runtime-live');
          body.classList.remove('rt-drawer-open');
        }
      }
    };
  }

  pure.mount = mount;
  if (typeof module !== 'undefined' && module.exports) module.exports = pure;
  if (global) global.FactoryRuntime = pure;
})(typeof window !== 'undefined' ? window : null);
