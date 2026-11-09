(function (global) {
  'use strict';

  // 원문으로 새 캐릭터 만들기 화면(계획 A2 "출처 받기(화면)", 출처 API는 계획 §2).
  // 초안의 파일 목록·문제·시작 가능 여부(canFinalize)는 서버 응답을 그대로 쓴다.
  // 화면이 따로 들고 있는 것은 올리는 중인 파일과 저장 중인 고침뿐이다.
  // 아래 createIntake는 DOM 없이 돌아가서 시험이 가짜 fetch로 올리기 순서를 확인한다. mount는 그 위에 화면을 그린다.

  const MAX_BYTES = 20 * 1024 * 1024;
  const EXTENSIONS = ['.txt', '.srt', '.vtt', '.csv', '.json'];
  const KINDS = [['INTERVIEW', '인터뷰'], ['ARTICLE', '기사'], ['TRANSCRIPT', '받아쓰기'], ['KAKAO_EXPORT', '카톡']];
  const REGISTERS = [['FORMAL', '공식 자리'], ['CASUAL', '캐주얼 자리']];
  const SUBJECT_KINDS = [['PUBLIC_FIGURE', '공인'], ['PRIVATE_PERSON', '개인']];
  const CHAPTERS = [['FAN_CALL', '팬과 첫 통화'], ['FAMILY_CALL', '가족과 통화']];
  const KIND_SLUG = { INTERVIEW: 'interview', ARTICLE: 'article', TRANSCRIPT: 'transcript', KAKAO_EXPORT: 'kakao' };
  const TEXT_ID = /^[A-Za-z0-9_-]+$/;
  const META_FIELDS = ['textId', 'kind', 'register', 'subjectSpeaker', 'userSpeaker', 'date', 'sourceUrl'];
  const ACTIVE = ['queued', 'starting', 'sending', 'checking'];

  function text(value) { return value == null ? '' : String(value); }
  function escapeHTML(value) {
    return text(value).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  const E = escapeHTML;
  function labelOf(pairs, id) { const p = pairs.find((x) => x[0] === id); return p ? p[1] : ''; }

  // 계획 §1 default_register와 같은 표: 인터뷰·기사는 공식 자리, 카톡·받아쓰기는 캐주얼 자리.
  function defaultRegister(kind) {
    if (kind === 'INTERVIEW' || kind === 'ARTICLE') return 'FORMAL';
    if (kind === 'KAKAO_EXPORT' || kind === 'TRANSCRIPT') return 'CASUAL';
    return null;
  }
  // 종류를 바꿀 때 말한 자리가 아직 기본값(또는 빈칸)이면 새 종류의 기본값을 따른다. 사람이 고른 값은 그대로 둔다.
  function nextRegister(prevKind, nextKind, current) {
    if (!current || current === defaultRegister(prevKind)) return defaultRegister(nextKind);
    return current;
  }
  function extOf(name) {
    const s = text(name).toLowerCase();
    const i = s.lastIndexOf('.');
    return i > 0 ? s.slice(i) : '';
  }
  function baseOf(name) {
    const s = text(name).replace(/^.*[\\/]/, '');
    const i = s.lastIndexOf('.');
    return i > 0 ? s.slice(0, i) : s;
  }
  // 파일 이름과 확장자로 종류를 짐작한다. 사람이 카드에서 고칠 수 있다.
  function guessKind(filename) {
    const ext = extOf(filename);
    const name = text(filename).toLowerCase();
    if (ext === '.srt' || ext === '.vtt') return 'TRANSCRIPT';
    if (/kakao|카톡|카카오/.test(name) || ext === '.csv') return 'KAKAO_EXPORT';
    if (/기사|뉴스|article|news/.test(name)) return 'ARTICLE';
    if (/받아쓰기|자막|transcript|subtitle/.test(name)) return 'TRANSCRIPT';
    return 'INTERVIEW';
  }
  // 원문 이름(textId) 제안: 파일 이름의 영문·숫자를 쓰고, 남는 게 없으면 종류-번호로 만든다. 이미 쓴 이름과 겹치지 않게 뒤에 번호를 붙인다.
  function suggestTextId(filename, kind, taken) {
    const used = new Set(Array.from(taken || []).map((x) => text(x).toLowerCase()));
    let slug = baseOf(filename).toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/-+/g, '-').replace(/^[-_]+|[-_]+$/g, '').slice(0, 40).replace(/[-_]+$/, '');
    const bare = !slug;
    if (!/[a-z]/.test(slug) || slug.length < 3) slug = (KIND_SLUG[kind] || 'text') + (slug ? '-' + slug : '');
    if (!bare && !used.has(slug)) return slug;
    for (let n = bare ? 1 : 2; ; n++) {
      const id = slug + '-' + n;
      if (!used.has(id)) return id;
    }
  }
  function checkFile(file) {
    const name = text(file && file.name);
    if (EXTENSIONS.indexOf(extOf(name)) < 0) return '이 형식은 받을 수 없어요. txt, srt, vtt, csv, json 파일만 올려 주세요.';
    const size = Number(file && file.size) || 0;
    if (size > MAX_BYTES) return '파일이 20MB보다 커요. 나눠서 올려 주세요.';
    if (size === 0) return '빈 파일이에요. 내용이 있는 파일을 올려 주세요.';
    return null;
  }
  function formatSize(bytes) {
    const n = Number(bytes) || 0;
    if (n < 1024) return n + 'B';
    if (n < 1024 * 1024) return Math.max(1, Math.round(n / 1024)) + 'KB';
    return (Math.round(n / 1024 / 1024 * 10) / 10) + 'MB';
  }
  function textIdProblem(value) {
    const v = text(value).trim();
    if (!v) return '원문 이름을 적어 주세요.';
    if (!TEXT_ID.test(v)) return '원문 이름은 영문, 숫자, -, _만 쓸 수 있어요.';
    return null;
  }
  // 완료·고치기 요청 본문. 빈칸은 null로 보내 지운 값도 서버에 전해진다.
  function metaBody(meta) {
    const body = {};
    META_FIELDS.forEach((f) => {
      const v = meta && meta[f];
      body[f] = v == null || text(v).trim() === '' ? null : text(v).trim();
    });
    return body;
  }
  function sameMeta(a, b) { return JSON.stringify(metaBody(a)) === JSON.stringify(metaBody(b)); }
  function apiUrl(apiBase, path) {
    const p = text(path);
    if (/^https?:\/\//i.test(p)) return p;
    return text(apiBase).replace(/\/+$/, '') + p;
  }
  function originOf(url, base) {
    try { return new URL(url, base).origin; } catch (error) { return ''; }
  }
  function errorText(error, step) {
    const e = error || {};
    if (e.network) return step === 'put' ? '파일을 보내는 중에 연결이 끊겼어요. 다시 올려 주세요.' : '서버에 연결하지 못했어요. 인터넷 연결을 확인하고 다시 해 주세요.';
    if (e.status === 413) return '파일이 너무 커요. 20MB 이하로 나눠서 올려 주세요.';
    if (e.detail) return e.detail;
    if (step === 'put') return '파일을 보내지 못했어요. 다시 올려 주세요.';
    return '요청을 처리하지 못했어요. 잠시 뒤 다시 해 주세요.';
  }

  // 받은 주소로 파일을 보낸다. 공장 서버 주소면 로그인 쿠키를 같이 보내고, 다른 곳(S3 서명 주소)에는 쿠키를 보내지 않는다.
  // 받은 headers만 그대로 붙인다(서명 주소는 머리글이 하나라도 다르면 거절한다).
  function putFile(target, body, opts) {
    const o = opts || {};
    const method = text(target && target.method) || 'PUT';
    const url = apiUrl(o.apiBase, target && target.url);
    const headers = Object.assign({}, (target && target.headers) || {});
    const local = originOf(url, o.origin) === originOf(o.origin, o.origin);
    const onProgress = o.onProgress || function () {};
    if (o.XHR) {
      return new Promise((resolve, reject) => {
        const xhr = new o.XHR();
        xhr.open(method, url);
        xhr.withCredentials = false; // 같은 출처면 쿠키가 가고, 다른 출처에는 가지 않는다.
        Object.keys(headers).forEach((k) => { try { xhr.setRequestHeader(k, headers[k]); } catch (error) { /* 브라우저가 막는 머리글은 브라우저가 붙인다 */ } });
        if (xhr.upload) xhr.upload.onprogress = (ev) => { if (ev.lengthComputable && ev.total) onProgress(ev.loaded / ev.total); };
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) { onProgress(1); resolve(); return; }
          const err = new Error('put'); err.status = xhr.status; reject(err);
        };
        xhr.onerror = () => { const err = new Error('put'); err.network = true; reject(err); };
        xhr.onabort = () => { const err = new Error('abort'); err.aborted = true; reject(err); };
        if (o.register) o.register(() => xhr.abort());
        xhr.send(body);
      });
    }
    if (typeof o.fetch !== 'function') return Promise.reject(Object.assign(new Error('put'), { network: true }));
    const ctrl = typeof AbortController === 'function' ? new AbortController() : null;
    if (o.register && ctrl) o.register(() => ctrl.abort());
    return Promise.resolve()
      .then(() => o.fetch(url, { method, headers, body, credentials: local ? 'same-origin' : 'omit', signal: ctrl ? ctrl.signal : undefined }))
      .catch((error) => { const err = new Error('put'); if (error && error.name === 'AbortError') err.aborted = true; else err.network = true; throw err; })
      .then((res) => {
        if (!res || !res.ok) { const err = new Error('put'); err.status = res ? res.status : 0; throw err; }
        onProgress(1);
      });
  }

  // ---- DOM 없는 상태 관리 ----
  function createIntake(options) {
    const o = options || {};
    const fetchImpl = o.fetch || (typeof fetch === 'function' ? fetch.bind(global || undefined) : null);
    const apiBase = text(o.apiBase);
    const origin = o.origin || (global && global.location && global.location.origin) || 'http://localhost';
    const XHR = o.XHR !== undefined ? o.XHR : ((global && global.XMLHttpRequest) || null);
    const concurrency = Math.max(1, o.concurrency || 2);
    const listeners = [];
    const state = {
      cid: null,
      loading: false,
      loadError: null, // { missing: bool, text }
      draft: null,
      uploads: [], // { key, file, filename, size, contentType, phase, progress, fileId, meta, error, step }
      overlay: {}, // fileId → 저장 중인 고친 값
      saving: {}, // key → 'saving' | 'saved' | 'error'
      saveError: {},
      fieldErrors: {}, // key → { field: 문구 }
      rawInput: {}, // key → { field: 아직 맞지 않아 보내지 않은 입력값 }. 보내는 값(meta)은 늘 검사를 통과한 값이다.
      cardKey: {}, // fileId → 올릴 때 쓴 카드 key(올린 뒤에도 같은 카드를 쓴다)
      busy: null, // 'create' | 'import' | 'finalize' | 'delete' | 'remove:<key>'
      error: null,
      notice: null,
      finalized: null,
      announce: ''
    };
    let seq = 0;
    let active = 0;
    const aborts = {};
    const chains = {};
    let pendingSaves = 0;

    function emit() { listeners.forEach((fn) => { try { fn(state); } catch (error) { /* 화면 오류가 상태를 막지 않게 */ } }); }
    function filesPath(fid) { return '/api/sources/' + encodeURIComponent(state.cid) + '/files' + (fid ? '/' + encodeURIComponent(fid) : ''); }

    async function request(method, path, body) {
      if (!fetchImpl) throw Object.assign(new Error('network'), { network: true });
      let res;
      try {
        res = await fetchImpl(apiUrl(apiBase, path), {
          method,
          headers: body === undefined ? { Accept: 'application/json' } : { Accept: 'application/json', 'Content-Type': 'application/json' },
          body: body === undefined ? undefined : JSON.stringify(body),
          credentials: 'same-origin'
        });
      } catch (error) {
        throw Object.assign(new Error('network'), { network: true });
      }
      let data = null;
      try { data = res.status === 204 ? null : await res.json(); } catch (error) { data = null; }
      if (!res.ok) {
        const err = new Error('request');
        err.status = res.status;
        const d = data && data.detail;
        err.detail = typeof d === 'string' ? d : Array.isArray(d) ? d.map((x) => text(x && (x.msg || x))).filter(Boolean).join(' ') : '';
        throw err;
      }
      return data;
    }

    function files() { return (state.draft && state.draft.files) || []; }
    function takenIds(exceptKey) {
      const ids = [];
      files().forEach((f) => { if (keyOf(f.fileId) !== exceptKey) ids.push(metaOfRecord(f).textId); });
      state.uploads.forEach((u) => { if (u.phase !== 'rejected' && u.key !== exceptKey) ids.push(u.meta.textId); });
      return ids.filter(Boolean);
    }
    function keyOf(fileId) { return state.cardKey[fileId] || 'f-' + fileId; }
    function metaOfRecord(rec) {
      const base = {};
      META_FIELDS.forEach((f) => { base[f] = rec[f] == null ? '' : rec[f]; });
      return Object.assign(base, state.overlay[rec.fileId] || {});
    }
    function upsert(rec) {
      if (!state.draft || !rec || !rec.fileId) return;
      const list = state.draft.files || (state.draft.files = []);
      const i = list.findIndex((f) => f.fileId === rec.fileId);
      if (i >= 0) list[i] = rec; else list.push(rec);
    }

    async function refresh() {
      if (!state.cid) return;
      try {
        const data = await request('GET', '/api/sources/' + encodeURIComponent(state.cid));
        state.draft = data;
      } catch (error) {
        state.notice = '최신 상태를 불러오지 못했어요. ' + errorText(error);
      }
      emit();
    }

    async function load(cid) {
      if (cid !== state.cid) Object.assign(state, { uploads: [], overlay: {}, saving: {}, saveError: {}, fieldErrors: {}, rawInput: {}, cardKey: {} });
      state.cid = cid;
      state.loading = true;
      state.loadError = null;
      state.draft = null;
      state.finalized = null;
      emit();
      try {
        state.draft = await request('GET', '/api/sources/' + encodeURIComponent(cid));
      } catch (error) {
        state.loadError = error.status === 404 ? { missing: true, text: '이 초안을 찾을 수 없어요. 이미 지웠거나 주소가 바뀌었을 수 있어요.' } : { missing: false, text: errorText(error) };
      }
      state.loading = false;
      emit();
    }

    function validateDraft(input) {
      const v = input || {};
      const errors = {};
      if (!text(v.displayName).trim()) errors.displayName = '표시 이름을 적어 주세요.';
      if (!SUBJECT_KINDS.some((k) => k[0] === v.subjectKind)) errors.subjectKind = '공인인지 개인인지 골라 주세요.';
      if (!text(v.scope).trim()) errors.scope = '어디에 쓰는지 적어 주세요.';
      return errors;
    }
    async function createDraft(input) {
      const errors = validateDraft(input);
      if (Object.keys(errors).length) return { errors };
      state.busy = 'create';
      state.error = null;
      emit();
      try {
        const body = {
          displayName: text(input.displayName).trim(),
          subjectKind: input.subjectKind,
          usageBasis: { scope: text(input.scope).trim(), notes: text(input.notes).trim() }
        };
        if (input.chapterTemplate) body.chapterTemplate = input.chapterTemplate;
        const data = await request('POST', '/api/sources/drafts', body);
        state.busy = null;
        if (o.onCid) o.onCid(data.characterId);
        await load(data.characterId);
        return { characterId: data.characterId };
      } catch (error) {
        state.busy = null;
        state.error = errorText(error);
        emit();
        return { error: state.error };
      }
    }

    function addFiles(list) {
      if (!state.draft || state.finalized) return [];
      const added = [];
      Array.from(list || []).forEach((file) => {
        const key = 'u' + (++seq);
        const problem = checkFile(file);
        const kind = guessKind(file.name);
        const subject = state.draft && state.draft.subject;
        const entry = {
          key,
          file,
          filename: text(file.name),
          size: Number(file.size) || 0,
          contentType: text(file.type) || 'application/octet-stream',
          phase: problem ? 'rejected' : 'queued',
          progress: 0,
          fileId: null,
          step: 'start',
          error: problem,
          meta: {
            textId: problem ? '' : suggestTextId(file.name, kind, takenIds()),
            kind,
            register: defaultRegister(kind),
            subjectSpeaker: text(subject && subject.displayName),
            userSpeaker: '',
            date: '',
            sourceUrl: ''
          }
        };
        state.uploads.push(entry);
        added.push(key);
      });
      emit();
      pump();
      return added;
    }
    function pump() {
      while (active < concurrency) {
        const next = state.uploads.find((u) => u.phase === 'queued');
        if (!next) break;
        run(next);
      }
    }
    // 올리기 순서: 자리 받기(POST files) → 받은 주소로 보내기(PUT) → 확인 요청(POST complete).
    // 확인에서 실패하면 다시 시도 때 확인만 다시 한다. 보내기에서 실패하면 받은 자리를 지우고 처음부터 한다(서명 주소는 15분 뒤 끝난다).
    async function run(entry) {
      active++;
      try {
        if (entry.step !== 'complete') {
          entry.phase = 'starting';
          entry.error = null;
          emit();
          if (entry.fileId) {
            const old = entry.fileId;
            entry.fileId = null;
            try { await request('DELETE', filesPath(old)); } catch (error) { /* 남은 자리는 서버 목록에서 지울 수 있다 */ }
          }
          entry.step = 'start';
          const started = await request('POST', filesPath(), { filename: entry.filename, size: entry.size, contentType: entry.contentType });
          entry.fileId = started.fileId;
          state.cardKey[started.fileId] = entry.key;
          if (entry.cancelled) throw Object.assign(new Error('abort'), { aborted: true });
          entry.step = 'put';
          entry.phase = 'sending';
          entry.progress = 0;
          emit();
          await putFile(started.upload, entry.file, {
            apiBase, origin, XHR, fetch: fetchImpl,
            register: (abort) => { aborts[entry.key] = abort; },
            onProgress: (p) => { entry.progress = Math.max(0, Math.min(1, p)); emit(); }
          });
          delete aborts[entry.key];
          entry.step = 'complete';
        }
        if (entry.cancelled) throw Object.assign(new Error('abort'), { aborted: true });
        entry.phase = 'checking';
        entry.progress = 1;
        emit();
        const sent = Object.assign({}, entry.meta);
        const rec = await request('POST', filesPath(entry.fileId) + '/complete', metaBody(sent));
        if (entry.cancelled) throw Object.assign(new Error('abort'), { aborted: true });
        state.uploads = state.uploads.filter((u) => u !== entry);
        upsert(rec);
        state.announce = entry.filename + ' 파일을 올렸어요.';
        // 확인하는 동안 사람이 고친 값이 있으면 이어서 저장한다.
        if (!sameMeta(sent, entry.meta)) queuePatch(rec.fileId, entry.meta);
      } catch (error) {
        delete aborts[entry.key];
        if (entry.cancelled || error.aborted) {
          state.uploads = state.uploads.filter((u) => u !== entry);
          if (entry.fileId) { try { await request('DELETE', filesPath(entry.fileId)); } catch (e) { /* 다음 새로고침에 남은 자리로 보인다 */ } }
        } else {
          entry.phase = 'failed';
          entry.error = errorText(error, entry.step);
          state.announce = entry.filename + ' 파일을 올리지 못했어요.';
        }
      }
      active--;
      emit();
      pump();
      if (!active && !state.uploads.some((u) => u.phase === 'queued')) await refresh();
    }
    function retry(key) {
      const entry = state.uploads.find((u) => u.key === key);
      if (!entry || entry.phase !== 'failed') return;
      entry.phase = 'queued';
      entry.error = null;
      emit();
      pump();
    }

    function queuePatch(fileId, meta) {
      const key = keyOf(fileId);
      state.overlay[fileId] = Object.assign({}, meta);
      state.saving[key] = 'saving';
      delete state.saveError[key];
      pendingSaves++;
      emit();
      const chain = (chains[fileId] || Promise.resolve()).then(async () => {
        try {
          const rec = await request('PATCH', filesPath(fileId), metaBody(meta));
          if (sameMeta(state.overlay[fileId], meta)) delete state.overlay[fileId];
          upsert(rec);
          state.saving[key] = 'saved';
        } catch (error) {
          state.saving[key] = 'error';
          state.saveError[key] = errorText(error);
        }
        pendingSaves--;
        emit();
        if (!pendingSaves) await refresh();
      });
      chains[fileId] = chain;
      return chain;
    }
    // 카드 칸 하나를 고친다. 올리는 중이면 확인 요청에 실어 보내고, 다 올린 파일이면 바로 저장(PATCH)한다.
    function editFile(key, field, value) {
      if (META_FIELDS.indexOf(field) < 0 || state.finalized) return null;
      const entry = state.uploads.find((u) => u.key === key);
      const rec = entry ? null : files().find((f) => keyOf(f.fileId) === key);
      if (!entry && !rec) return null;
      const meta = Object.assign({}, entry ? entry.meta : metaOfRecord(rec));
      const prevKind = meta.kind;
      meta[field] = text(value);
      if (field === 'kind') meta.register = nextRegister(prevKind, meta.kind, meta.register) || '';
      if (field === 'textId') meta.textId = text(value).trim();
      const errs = Object.assign({}, state.fieldErrors[key] || {});
      delete errs[field];
      if (field === 'textId') {
        const problem = textIdProblem(meta.textId) || (takenIds(key).some((x) => x.toLowerCase() === meta.textId.toLowerCase()) ? '다른 파일과 원문 이름이 같아요. 다른 이름을 적어 주세요.' : null);
        if (problem) errs.textId = problem;
      }
      if (field === 'sourceUrl' && meta.sourceUrl && !/^https?:\/\/\S+$/i.test(meta.sourceUrl.trim())) errs.sourceUrl = 'http:// 또는 https://로 시작하는 주소를 적어 주세요.';
      const raw = Object.assign({}, state.rawInput[key] || {});
      if (errs[field]) raw[field] = text(value); else delete raw[field];
      if (Object.keys(raw).length) state.rawInput[key] = raw; else delete state.rawInput[key];
      if (Object.keys(errs).length) state.fieldErrors[key] = errs; else delete state.fieldErrors[key];
      if (errs[field]) { emit(); return null; }
      if (entry) { entry.meta = meta; emit(); return Promise.resolve(); }
      return queuePatch(rec.fileId, meta);
    }

    async function removeFile(key) {
      const entry = state.uploads.find((u) => u.key === key);
      if (entry) {
        delete state.fieldErrors[key];
        delete state.rawInput[key];
        if (ACTIVE.indexOf(entry.phase) >= 0 && entry.phase !== 'queued') {
          entry.cancelled = true;
          if (aborts[key]) aborts[key]();
          emit();
          return;
        }
        state.uploads = state.uploads.filter((u) => u !== entry);
        emit();
        if (entry.fileId) { try { await request('DELETE', filesPath(entry.fileId)); } catch (error) { /* 서버 목록에 남으면 거기서 지운다 */ } await refresh(); }
        return;
      }
      const rec = files().find((f) => keyOf(f.fileId) === key);
      if (!rec) return;
      state.busy = 'remove:' + key;
      state.error = null;
      emit();
      try {
        await request('DELETE', filesPath(rec.fileId));
        state.draft.files = files().filter((f) => f !== rec);
        delete state.fieldErrors[key];
        delete state.rawInput[key];
        delete state.overlay[rec.fileId];
        state.announce = rec.filename + ' 파일을 지웠어요.';
      } catch (error) {
        state.error = rec.filename + ' 파일을 지우지 못했어요. ' + errorText(error);
      }
      state.busy = null;
      emit();
      await refresh();
    }

    async function importPath(path) {
      const p = text(path).trim();
      if (!state.draft || !state.draft.allowPathImport || !p) return;
      state.busy = 'import';
      state.error = null;
      emit();
      try {
        await request('POST', '/api/sources/' + encodeURIComponent(state.cid) + '/import-path', { path: p });
        state.announce = '경로에서 원문을 가져왔어요.';
      } catch (error) {
        state.error = '가져오지 못했어요. ' + errorText(error);
      }
      state.busy = null;
      await refresh();
    }

    // 시작 가능 조건: 서버 canFinalize가 참이고, 화면에 올리는 중·실패한 파일, 저장 중이거나 고칠 곳이 남은 칸이 없어야 한다.
    function startState() {
      const reasons = [];
      const d = state.draft;
      if (state.finalized) return { ready: false, reasons: [] };
      if (!d) return { ready: false, reasons: ['인물 정보를 먼저 저장해 주세요.'] };
      if (state.uploads.some((u) => ACTIVE.indexOf(u.phase) >= 0)) reasons.push('올리는 중인 파일이 끝나면 시작할 수 있어요.');
      if (state.uploads.some((u) => u.phase === 'failed')) reasons.push('올리지 못한 파일을 다시 올리거나 지워 주세요.');
      if (pendingSaves) reasons.push('고친 내용을 저장하고 있어요.');
      if (Object.keys(state.saveError).length) reasons.push('저장하지 못한 파일 정보가 있어요.');
      if (Object.keys(state.fieldErrors).length) reasons.push('파일 정보에 고칠 곳이 있어요.');
      if (!(d.files || []).length && !state.uploads.some((u) => u.phase !== 'rejected')) reasons.push('원문 파일을 하나 이상 올려 주세요.');
      if (d.canFinalize !== true) (d.problems || []).forEach((p) => { if (reasons.indexOf(p) < 0) reasons.push(text(p)); });
      if (d.canFinalize !== true && !reasons.length) reasons.push('아직 시작할 수 없어요. 파일마다 확인할 점을 봐 주세요.');
      return { ready: d.canFinalize === true && !reasons.length, reasons };
    }

    async function finalize() {
      if (!startState().ready || state.busy) return null;
      state.busy = 'finalize';
      state.error = null;
      emit();
      try {
        const data = await request('POST', '/api/sources/' + encodeURIComponent(state.cid) + '/finalize');
        state.finalized = { jobId: data && data.jobId };
        state.saving = {};
        state.announce = '출처 정리를 시작했어요.';
      } catch (error) {
        state.error = '출처 정리를 시작하지 못했어요. ' + errorText(error);
      }
      state.busy = null;
      emit();
      if (!state.finalized) await refresh();
      return state.finalized;
    }

    async function deleteDraft() {
      if (!state.cid) return false;
      state.busy = 'delete';
      state.error = null;
      emit();
      try {
        await request('DELETE', '/api/sources/' + encodeURIComponent(state.cid));
      } catch (error) {
        state.busy = null;
        state.error = '초안을 지우지 못했어요. ' + errorText(error);
        emit();
        return false;
      }
      Object.keys(aborts).forEach((k) => aborts[k]());
      Object.assign(state, { cid: null, draft: null, uploads: [], overlay: {}, saving: {}, saveError: {}, fieldErrors: {}, rawInput: {}, cardKey: {}, busy: null, finalized: null, loadError: null, announce: '초안과 올린 원문을 지웠어요.' });
      if (o.onCid) o.onCid(null);
      emit();
      return true;
    }
    function reset() {
      Object.assign(state, { cid: null, draft: null, uploads: [], overlay: {}, saving: {}, saveError: {}, fieldErrors: {}, rawInput: {}, cardKey: {}, busy: null, finalized: null, loadError: null, error: null, notice: null });
      emit();
    }
    function dismiss(key) {
      state.uploads = state.uploads.filter((u) => !(u.key === key && u.phase === 'rejected'));
      emit();
    }

    // 카드 목록: 서버에 있는 파일 다음에 올리는 중인 파일. 올리는 중인 파일과 같은 자리를 서버 목록이 보여 주면 한 번만 쓴다.
    function items() {
      const uploading = new Set(state.uploads.map((u) => u.fileId).filter(Boolean));
      const out = [];
      files().forEach((f) => {
        if (uploading.has(f.fileId)) return;
        const key = keyOf(f.fileId);
        const st = f.status === 'ready' ? ['ok', '준비됐어요'] : f.status === 'problem' ? ['wait', '확인이 필요해요'] : ['muted', '다 올라가지 않았어요'];
        const problems = (f.problems || []).map(text);
        if (f.status === 'pending' && !problems.length) problems.push('이 파일은 끝까지 올라가지 않았어요. 지우고 다시 올려 주세요.');
        out.push({ key, source: 'record', fileId: f.fileId, filename: text(f.filename), size: f.size, tone: st[0], status: st[1], progress: null, problems, meta: metaOfRecord(f), display: Object.assign(metaOfRecord(f), state.rawInput[key] || {}), editable: f.status !== 'pending' && !state.finalized, removable: !state.finalized && state.busy !== 'remove:' + key, retry: false, saving: state.saving[key] || '', saveError: state.saveError[key] || '', fieldErrors: state.fieldErrors[key] || {} });
      });
      state.uploads.forEach((u) => {
        const map = { queued: ['muted', '기다리는 중'], starting: ['run', '준비하는 중'], sending: ['run', '올리는 중 ' + Math.round(u.progress * 100) + '%'], checking: ['run', '확인하는 중'], failed: ['fail', '올리지 못했어요'], rejected: ['fail', '받을 수 없는 파일'] };
        const st = map[u.phase] || ['muted', ''];
        out.push({ key: u.key, source: 'upload', fileId: u.fileId, filename: u.filename, size: u.size, tone: st[0], status: st[1], phase: u.phase, progress: u.phase === 'sending' ? u.progress : null, problems: u.error ? [u.error] : [], meta: u.meta, display: Object.assign({}, u.meta, state.rawInput[u.key] || {}), editable: u.phase !== 'rejected' && !state.finalized, removable: !u.cancelled, retry: u.phase === 'failed', saving: '', saveError: '', fieldErrors: state.fieldErrors[u.key] || {} });
      });
      return out;
    }
    function uploading() { return state.uploads.some((u) => ACTIVE.indexOf(u.phase) >= 0); }

    return {
      state, load, refresh, createDraft, validateDraft, addFiles, retry, dismiss, editFile, removeFile, importPath, finalize, deleteDraft, reset, startState, items, uploading,
      subscribe(fn) { listeners.push(fn); return () => { const i = listeners.indexOf(fn); if (i >= 0) listeners.splice(i, 1); }; }
    };
  }

  // ---- 화면 ----
  const ICON = {
    file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><polyline points="14 3 14 8 19 8"/>',
    upload: '<path d="M12 16V4"/><polyline points="7 9 12 4 17 9"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
    x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    check: '<polyline points="20 6 9 17 4 12"/>',
    down: '<polyline points="6 9 12 15 18 9"/>',
    retry: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><polyline points="3 3 3 8 8 8"/>'
  };
  function icon(name) { return '<svg class="i" viewBox="0 0 24 24" aria-hidden="true">' + ICON[name] + '</svg>'; }
  function options(pairs, value) { return pairs.map((p) => '<option value="' + p[0] + '"' + (p[0] === value ? ' selected' : '') + '>' + p[1] + '</option>').join(''); }

  function cardHTML(item) {
    const k = E(item.key);
    const id = (f) => 'sf-' + k + '-' + f;
    const fld = (f, label, control, hint, wide) => '<div class="src-fld' + (wide ? ' wide' : '') + '" data-fld="' + f + '"><label for="' + id(f) + '">' + label + '</label>' + control + '<p class="src-fhint" id="' + id(f) + '-h">' + (hint || '') + '</p></div>';
    const input = (f, type, extra) => '<input id="' + id(f) + '" data-field="' + f + '" type="' + type + '" aria-describedby="' + id(f) + '-h" autocomplete="off"' + (extra || '') + '>';
    return '<article class="src-file" data-key="' + k + '" aria-labelledby="' + id('name') + '">' +
      '<div class="src-file-head">' +
        '<span class="src-file-ic" aria-hidden="true">' + icon('file') + '</span>' +
        '<div class="src-file-tx"><b class="nm" id="' + id('name') + '"></b><span class="meta" data-meta></span></div>' +
        '<span class="fl-pill" data-status><span class="d"></span><span data-status-text></span></span>' +
        '<button type="button" class="btn ghost src-tog" data-act="toggle" aria-expanded="true" aria-controls="' + id('body') + '">' + icon('down') + '<span>정보</span></button>' +
        '<button type="button" class="btn ghost src-x" data-act="remove" aria-label="">' + icon('x') + '</button>' +
      '</div>' +
      '<div class="src-bar" data-bar role="progressbar" aria-valuemin="0" aria-valuemax="100" hidden><span></span></div>' +
      '<ul class="src-problems" data-problems hidden></ul>' +
      '<div class="src-file-acts" data-retry-row hidden><button type="button" class="btn" data-act="retry">' + icon('retry') + '다시 올리기</button></div>' +
      '<div class="src-fields" id="' + id('body') + '" data-body>' +
        fld('textId', '원문 이름', input('textId', 'text', ' spellcheck="false" inputmode="latin"'), '영문, 숫자, -, _로 적어요. 파일마다 달라야 해요.') +
        fld('kind', '종류', '<select id="' + id('kind') + '" data-field="kind" aria-describedby="' + id('kind') + '-h">' + options(KINDS, item.meta.kind) + '</select>', '') +
        fld('register', '말한 자리', '<select id="' + id('register') + '" data-field="register" aria-describedby="' + id('register') + '-h">' + options(REGISTERS, item.meta.register) + '</select>', '') +
        fld('date', '날짜', input('date', 'date'), '말하거나 쓴 날이에요.') +
        fld('subjectSpeaker', '대상 화자 이름', input('subjectSpeaker', 'text'), '원문에 적힌 그 사람의 이름이에요.') +
        fld('userSpeaker', '상대 화자 이름', input('userSpeaker', 'text'), '카톡·대담에서 이야기 상대의 이름이에요. 없으면 비워 두세요.') +
        fld('sourceUrl', '출처 주소', input('sourceUrl', 'url', ' placeholder="https://" spellcheck="false"'), '', true) +
      '</div>' +
      '<p class="src-save" data-save></p>' +
    '</article>';
  }

  function mount(options) {
    const opt = options || {};
    const doc = opt.root || (global && global.document);
    if (!doc || typeof doc.querySelector !== 'function') return { destroy() {}, intake: null };
    const $ = (s) => doc.querySelector(s);
    const loc = global && global.location;
    const route = () => { const m = /^#c\/([^/]+)$/.exec(text(loc && loc.hash)); return m ? decodeURIComponent(m[1]) : null; };
    const intake = createIntake({
      fetch: opt.fetch, apiBase: opt.apiBase, XHR: opt.XHR,
      onCid(cid) { if (!loc) return; if (cid) loc.hash = '#c/' + encodeURIComponent(cid); else clearHash(); }
    });
    const S = intake.state;
    // 해시를 지울 때는 hashchange가 생기지 않게 주소만 바꾼다.
    function clearHash() { if (!loc) return; if (global.history && global.history.replaceState) global.history.replaceState(null, '', loc.pathname + loc.search); else loc.hash = ''; }
    const r = {
      banner: $('[data-banner]'), live: $('[data-live]'),
      steps: { info: $('[data-step="info"]'), files: $('[data-step="files"]'), start: $('[data-step="start"]') },
      form: $('[data-info-form]'), formErr: $('[data-info-error]'), summary: $('[data-info-summary]'), loading: $('[data-loading]'), missing: $('[data-missing]'),
      drop: $('[data-drop]'), picker: $('[data-picker]'), list: $('[data-list]'), empty: $('[data-empty]'), count: $('[data-count]'),
      pathRow: $('[data-path]'), pathInput: $('[data-path-input]'), pathBtn: $('[data-path-go]'),
      startBtn: $('[data-start]'), reasons: $('[data-reasons]'), done: $('[data-done]'), doneLink: $('[data-done-link]'),
      delRow: $('[data-del]'), delConfirm: $('[data-del-confirm]'), publicNote: $('[data-public-note]')
    };
    let chapterTouched = false;
    let confirmDelete = false;
    const open = {}; // key → 정보 칸 펼침
    const cards = new Map();

    function setStep(el, st) {
      if (!el) return;
      el.dataset.state = st;
      const sec = el.querySelector('section');
      if (sec) { if (st === 'todo') sec.setAttribute('aria-disabled', 'true'); else sec.removeAttribute('aria-disabled'); }
    }
    function fieldError(name, msg) {
      const el = r.form && r.form.querySelector('[data-err="' + name + '"]');
      if (el) { el.textContent = msg || ''; el.hidden = !msg; }
      const ctl = r.form && r.form.querySelector('[name="' + name + '"]');
      if (ctl) { if (msg) ctl.setAttribute('aria-invalid', 'true'); else ctl.removeAttribute('aria-invalid'); }
    }

    function renderInfo() {
      const d = S.draft;
      const hasDraft = !!d;
      if (r.loading) r.loading.hidden = !S.loading;
      if (r.missing) {
        r.missing.hidden = !S.loadError;
        if (S.loadError) r.missing.querySelector('[data-missing-text]').textContent = S.loadError.text;
        const again = r.missing.querySelector('[data-act="reload"]');
        if (again) again.hidden = !!(S.loadError && S.loadError.missing);
      }
      if (r.form) {
        r.form.hidden = hasDraft || S.loading || !!S.loadError;
        r.form.querySelectorAll('input,textarea,select,button').forEach((el) => { el.disabled = S.busy === 'create'; });
        const btn = r.form.querySelector('[type="submit"]');
        if (btn) btn.textContent = S.busy === 'create' ? '저장하는 중…' : '저장하고 원문 올리기';
      }
      if (r.formErr) { r.formErr.textContent = !hasDraft && S.error ? S.error : ''; r.formErr.hidden = !(!hasDraft && S.error); }
      if (r.summary) {
        r.summary.hidden = !hasDraft;
        if (hasDraft) {
          const sub = d.subject || {};
          const basis = d.usageBasis || {};
          r.summary.querySelector('[data-sum-name]').textContent = text(sub.displayName);
          r.summary.querySelector('[data-sum-kind]').textContent = labelOf(SUBJECT_KINDS, sub.kind);
          r.summary.querySelector('[data-sum-scope]').textContent = text(basis.scope) || '적지 않았어요';
          const notes = r.summary.querySelector('[data-sum-notes]');
          notes.textContent = text(basis.notes);
          notes.parentElement.hidden = !text(basis.notes);
        }
      }
      if (r.publicNote) r.publicNote.hidden = !(hasDraft && d.subject && d.subject.kind === 'PUBLIC_FIGURE');
    }

    function syncCard(el, item) {
      // 정보 칸은 사람이 볼 게 있을 때만 저절로 펼친다: 확인할 점·고칠 칸이 있거나, 공인 인터뷰·기사에 날짜나 출처 주소가 비었을 때. 그 밖은 한 줄 요약(크기·종류·자리)만 둔다.
      function needsLook(it) {
        if (it.tone === 'wait' || it.problems.length || Object.keys(it.fieldErrors).length || it.saving === 'error') return true;
        const pub = S.draft && S.draft.subject && S.draft.subject.kind === 'PUBLIC_FIGURE';
        return !!(pub && (it.meta.kind === 'INTERVIEW' || it.meta.kind === 'ARTICLE') && (!it.meta.date || !it.meta.sourceUrl));
      }
      const q = (s) => el.querySelector(s);
      q('.nm').textContent = item.filename;
      q('[data-meta]').textContent = (item.editable || item.source === 'record' ? [formatSize(item.size), labelOf(KINDS, item.meta.kind), labelOf(REGISTERS, item.meta.register)] : [formatSize(item.size)]).filter(Boolean).join(' · ');
      const pill = q('[data-status]');
      pill.className = 'fl-pill ' + item.tone;
      q('[data-status-text]').textContent = item.status;
      el.dataset.tone = item.tone;
      const bar = q('[data-bar]');
      bar.hidden = item.progress == null;
      if (item.progress != null) {
        const pct = Math.round(item.progress * 100);
        bar.firstChild.style.width = pct + '%';
        bar.setAttribute('aria-valuenow', String(pct));
        bar.setAttribute('aria-label', item.filename + ' 올리는 중');
      }
      const probs = q('[data-problems]');
      const ph = item.problems.map((p) => '<li>' + E(p) + '</li>').join('');
      if (probs.dataset.html !== ph) { probs.innerHTML = ph; probs.dataset.html = ph; }
      probs.hidden = !item.problems.length;
      probs.classList.toggle('bad', item.tone === 'fail');
      q('[data-retry-row]').hidden = !item.retry;
      const x = q('[data-act="remove"]');
      x.disabled = !item.removable;
      x.setAttribute('aria-label', (item.phase && ACTIVE.indexOf(item.phase) > 0 ? '올리기 멈추고 지우기: ' : item.source === 'upload' && item.phase === 'rejected' ? '목록에서 빼기: ' : '지우기: ') + item.filename);
      x.title = item.phase && ACTIVE.indexOf(item.phase) > 0 ? '올리기 멈추기' : '지우기';
      // 저절로 펼친 카드는 문제가 풀려도 접지 않는다(고치던 칸에서 초점을 잃지 않게).
      if (open[item.key] === undefined && item.editable && needsLook(item)) open[item.key] = true;
      const isOpen = item.editable && open[item.key] === true;
      const body = q('[data-body]');
      body.hidden = !isOpen;
      const tog = q('[data-act="toggle"]');
      tog.hidden = !item.editable;
      tog.setAttribute('aria-expanded', String(isOpen));
      tog.querySelector('span').textContent = isOpen ? '접기' : '정보 보기';
      body.querySelectorAll('[data-field]').forEach((ctl) => {
        const f = ctl.dataset.field;
        const v = text(item.display[f]);
        if (doc.activeElement !== ctl && ctl.value !== v) ctl.value = v;
        ctl.disabled = !item.editable;
        const err = item.fieldErrors[f];
        const hint = el.querySelector('#' + ctl.id + '-h');
        if (!hint.dataset.base) hint.dataset.base = hint.textContent;
        let h = err || hint.dataset.base;
        if (!err && f === 'register' && item.meta.register && item.meta.register === defaultRegister(item.meta.kind)) h = labelOf(KINDS, item.meta.kind) + ' 기본값이에요. 다르면 바꿔 주세요.';
        if (!err && f === 'sourceUrl') h = S.draft && S.draft.subject && S.draft.subject.kind === 'PUBLIC_FIGURE' && (item.meta.kind === 'INTERVIEW' || item.meta.kind === 'ARTICLE') && (!item.meta.date || !item.meta.sourceUrl) ? '공인은 날짜와 출처 주소가 있어야 이 원문에서 사실을 모아요.' : '원문을 찾을 수 있는 인터넷 주소예요.';
        hint.textContent = h;
        hint.classList.toggle('bad', !!err);
        if (err) ctl.setAttribute('aria-invalid', 'true'); else ctl.removeAttribute('aria-invalid');
      });
      const save = q('[data-save]');
      save.textContent = item.saving === 'saving' ? '저장하는 중…' : item.saving === 'saved' ? '저장했어요' : item.saving === 'error' ? '저장하지 못했어요. ' + item.saveError : '';
      save.className = 'src-save' + (item.saving === 'error' ? ' bad' : '');
    }

    function renderFiles() {
      const d = S.draft;
      setStep(r.steps.files, !d ? 'todo' : S.finalized ? 'done' : 'active');
      if (r.drop) {
        r.drop.hidden = !!S.finalized;
        r.drop.classList.toggle('is-off', !d || !!S.finalized);
        const pick = r.drop.querySelector('[data-act="pick"]');
        if (pick) pick.disabled = !d || !!S.finalized;
      }
      const items = d ? intake.items() : [];
      if (r.empty) r.empty.hidden = !d || items.length > 0;
      const counted = items.filter((i) => i.phase !== 'rejected');
      if (r.count) r.count.textContent = counted.length ? counted.filter((i) => i.tone === 'ok').length + ' / ' + counted.length + '개 준비' : '';
      const keep = new Set(items.map((i) => i.key));
      cards.forEach((el, key) => { if (!keep.has(key)) { el.remove(); cards.delete(key); } });
      items.forEach((item) => {
        let el = cards.get(item.key);
        if (!el) {
          const holder = doc.createElement('div');
          holder.innerHTML = cardHTML(item);
          el = holder.firstChild;
          cards.set(item.key, el);
        }
        syncCard(el, item);
      });
      if (r.list) {
        const want = items.map((i) => cards.get(i.key));
        const now = Array.from(r.list.children);
        if (want.length !== now.length || want.some((el, i) => el !== now[i])) want.forEach((el) => r.list.appendChild(el));
      }
      if (r.pathRow) {
        r.pathRow.hidden = !(d && d.allowPathImport && !S.finalized);
        if (r.pathBtn) { r.pathBtn.disabled = S.busy === 'import'; r.pathBtn.textContent = S.busy === 'import' ? '가져오는 중…' : '가져오기'; }
      }
    }

    function renderStart() {
      const d = S.draft;
      const st = intake.startState();
      setStep(r.steps.info, d ? 'done' : 'active');
      setStep(r.steps.start, !d ? 'todo' : S.finalized ? 'done' : st.ready ? 'active' : 'wait');
      if (r.startBtn) {
        r.startBtn.disabled = !st.ready || !!S.busy;
        r.startBtn.hidden = !!S.finalized;
        r.startBtn.textContent = S.busy === 'finalize' ? '시작하는 중…' : '출처 정리 시작';
      }
      if (r.reasons) {
        const html = d && !S.finalized && st.reasons.length ? '<p>시작하기 전에 봐 주세요</p><ul>' + st.reasons.map((x) => '<li>' + E(x) + '</li>').join('') + '</ul>' : '';
        if (r.reasons.dataset.html !== html) { r.reasons.innerHTML = html; r.reasons.dataset.html = html; }
        r.reasons.hidden = !html;
      }
      if (r.done) {
        r.done.hidden = !S.finalized;
        if (r.doneLink && S.cid) r.doneLink.href = 'factory.html#c/' + encodeURIComponent(S.cid);
      }
      if (r.delRow) {
        r.delRow.hidden = !d || !!S.finalized;
        if (r.delConfirm) r.delConfirm.hidden = !confirmDelete;
        const ask = r.delRow.querySelector('[data-act="ask-delete"]');
        if (ask) ask.hidden = confirmDelete;
        const yes = r.delRow.querySelector('[data-act="delete"]');
        if (yes) { yes.disabled = S.busy === 'delete'; yes.textContent = S.busy === 'delete' ? '지우는 중…' : '모두 지우기'; }
      }
      if (r.banner) {
        const msg = d ? S.error || S.notice : '';
        const html = msg ? '<div class="fl-banner ' + (S.error ? 'bad' : '') + '" role="alert">' + E(msg) + '</div>' : '';
        if (r.banner.dataset.html !== html) { r.banner.innerHTML = html; r.banner.dataset.html = html; }
      }
      if (r.live && S.announce) { r.live.textContent = S.announce; S.announce = ''; }
      if (doc.title !== undefined) doc.title = (d && d.subject ? text(d.subject.displayName) + ' · ' : '') + '원문으로 새 캐릭터 · Foundry';
    }
    function render() { renderInfo(); renderFiles(); renderStart(); }
    intake.subscribe(render);

    function onSubmit(e) {
      if (e.target !== r.form) {
        if (e.target === r.pathRow) { e.preventDefault(); intake.importPath(r.pathInput.value).then(() => { if (!S.error) r.pathInput.value = ''; }); }
        return;
      }
      e.preventDefault();
      const f = r.form;
      const kind = (f.querySelector('[name="subjectKind"]:checked') || {}).value;
      const input = { displayName: f.querySelector('[name="displayName"]').value, subjectKind: kind, scope: f.querySelector('[name="scope"]').value, notes: f.querySelector('[name="notes"]').value, chapterTemplate: f.querySelector('[name="chapterTemplate"]').value || undefined };
      const errors = intake.validateDraft(input);
      ['displayName', 'subjectKind', 'scope'].forEach((n) => fieldError(n, errors[n]));
      const first = Object.keys(errors)[0];
      if (first) { const ctl = f.querySelector('[name="' + first + '"]'); if (ctl) ctl.focus(); return; }
      intake.createDraft(input).then((res) => {
        if (res && res.characterId) {
          const h = r.steps.files && r.steps.files.querySelector('h2');
          if (h) h.focus();
        }
      });
    }
    function onClick(e) {
      const el = e.target.closest && e.target.closest('[data-act]');
      if (!el || el.disabled) return;
      const act = el.dataset.act;
      const card = el.closest('[data-key]');
      const key = card && card.dataset.key;
      if (act === 'pick' && r.picker) r.picker.click();
      else if (act === 'toggle' && key) { open[key] = el.getAttribute('aria-expanded') !== 'true'; render(); }
      else if (act === 'remove' && key) {
        const item = intake.items().find((i) => i.key === key);
        if (item && item.source === 'upload' && item.phase === 'rejected') intake.dismiss(key); else intake.removeFile(key);
        const next = card.nextElementSibling || card.previousElementSibling;
        setTimeout(() => { const t = next && next.querySelector('[data-act="remove"]'); if (t && doc.contains(t)) t.focus(); else if (r.drop) { const p = r.drop.querySelector('[data-act="pick"]'); if (p) p.focus(); } }, 0);
      }
      else if (act === 'retry' && key) intake.retry(key);
      else if (act === 'start') intake.finalize().then((done) => { if (done && r.done) { const h = r.done.querySelector('h3'); if (h) h.focus(); } });
      else if (act === 'ask-delete') { confirmDelete = true; render(); const no = r.delRow.querySelector('[data-act="cancel-delete"]'); if (no) no.focus(); }
      else if (act === 'cancel-delete') { confirmDelete = false; render(); const ask = r.delRow.querySelector('[data-act="ask-delete"]'); if (ask) ask.focus(); }
      else if (act === 'delete') intake.deleteDraft().then((ok) => { if (ok) { confirmDelete = false; chapterTemplateReset(); render(); const n = r.form && r.form.querySelector('[name="displayName"]'); if (n) n.focus(); } });
      else if (act === 'reload') { const cid = route(); if (cid) intake.load(cid); }
      else if (act === 'restart') { intake.reset(); clearHash(); render(); }
    }
    function chapterTemplateReset() {
      chapterTouched = false;
      if (r.form) r.form.reset();
    }
    function onChange(e) {
      const t = e.target;
      if (t === r.picker) { intake.addFiles(t.files); t.value = ''; return; }
      if (r.form && r.form.contains(t)) {
        if (t.name === 'chapterTemplate') chapterTouched = true;
        if (t.name === 'subjectKind') {
          fieldError('subjectKind', '');
          const ch = r.form.querySelector('[name="chapterTemplate"]');
          if (ch && !chapterTouched) ch.value = t.value === 'PRIVATE_PERSON' ? 'FAMILY_CALL' : 'FAN_CALL';
        }
        return;
      }
      const card = t.closest && t.closest('[data-key]');
      if (card && t.dataset.field) intake.editFile(card.dataset.key, t.dataset.field, t.value);
    }
    function onInput(e) {
      const t = e.target;
      if (r.form && r.form.contains(t) && t.name && t.getAttribute('aria-invalid')) fieldError(t.name, '');
    }
    function hasFiles(e) { const dt = e.dataTransfer; return !!(dt && Array.from(dt.types || []).indexOf('Files') >= 0); }
    function onDragOver(e) {
      if (!hasFiles(e)) return;
      e.preventDefault();
      const inside = r.drop && r.drop.contains(e.target) && S.draft && !S.finalized;
      if (e.dataTransfer) e.dataTransfer.dropEffect = inside ? 'copy' : 'none';
      if (r.drop) r.drop.classList.toggle('is-over', !!inside);
    }
    function onDragLeave(e) { if (r.drop && (!e.relatedTarget || !r.drop.contains(e.relatedTarget))) r.drop.classList.remove('is-over'); }
    function onDrop(e) {
      if (!hasFiles(e)) return;
      e.preventDefault(); // 화면 밖에 떨어뜨려도 브라우저가 파일을 열며 화면을 떠나지 않게 한다.
      if (r.drop) r.drop.classList.remove('is-over');
      if (r.drop && r.drop.contains(e.target)) intake.addFiles(e.dataTransfer.files);
    }
    function onHash() { const cid = route(); if (cid && cid !== S.cid) intake.load(cid); else if (!cid && S.cid) intake.reset(); }
    function onLeave(e) { if (intake.uploading()) { e.preventDefault(); e.returnValue = ''; } }

    doc.addEventListener('submit', onSubmit);
    doc.addEventListener('click', onClick);
    doc.addEventListener('change', onChange);
    doc.addEventListener('input', onInput);
    doc.addEventListener('dragover', onDragOver);
    doc.addEventListener('dragleave', onDragLeave);
    doc.addEventListener('drop', onDrop);
    if (global && global.addEventListener) { global.addEventListener('hashchange', onHash); global.addEventListener('beforeunload', onLeave); }
    const cid = route();
    if (cid) intake.load(cid); else render();
    return {
      intake,
      destroy() {
        doc.removeEventListener('submit', onSubmit);
        doc.removeEventListener('click', onClick);
        doc.removeEventListener('change', onChange);
        doc.removeEventListener('input', onInput);
        doc.removeEventListener('dragover', onDragOver);
        doc.removeEventListener('dragleave', onDragLeave);
        doc.removeEventListener('drop', onDrop);
        if (global && global.removeEventListener) { global.removeEventListener('hashchange', onHash); global.removeEventListener('beforeunload', onLeave); }
      }
    };
  }

  const api = { MAX_BYTES, EXTENSIONS, KINDS, REGISTERS, SUBJECT_KINDS, CHAPTERS, defaultRegister, nextRegister, guessKind, suggestTextId, checkFile, formatSize, textIdProblem, metaBody, putFile, errorText, createIntake, mount };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (global) global.SourceIntake = api;
})(typeof window !== 'undefined' ? window : null);

