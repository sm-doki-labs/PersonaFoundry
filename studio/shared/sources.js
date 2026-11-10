(function (global) {
  'use strict';

  // 원문으로 새 캐릭터 만들기 화면(계획 A2 "출처 받기(화면)", 출처 API는 계획 §2).
  // 초안의 파일 목록·문제·시작 가능 여부(canFinalize)는 서버 응답을 그대로 쓴다.
  // 화면이 따로 들고 있는 것은 올리는 중인 파일과 저장 중인 고침뿐이다.
  // 아래 createIntake는 DOM 없이 돌아가서 시험이 가짜 fetch로 올리기 순서를 확인한다. mount는 그 위에 화면을 그린다.

  const MAX_BYTES = 20 * 1024 * 1024;
  const EXTENSIONS = ['.txt', '.srt', '.vtt', '.csv', '.json'];
  // 영상용 사진(계획 4차 약속 5). 원문과 같은 올리기 순서로 보내고, 서버가 fileType "photo"로 돌려준다.
  const PHOTO_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp'];
  const PHOTO_MAX_BYTES = 15 * 1024 * 1024;
  // 영상 등급(약속 5). 화면에는 개수를 쓰지 않고, 무엇을 받는지와 걸리는 시간·비용을 서로 견줘서만 적는다.
  // [값, 이름, 한 줄 설명, 시간·비용 칸 수(0~4)]. 진행 화면(flow.js)도 같은 표를 쓴다(시험이 같은지 본다).
  const VIDEO_TIERS = [
    ['none', '영상 없이', '대화만 만들어요. 영상 비용이 들지 않아요.', 0],
    ['light', '라이트', '자주 쓰는 기본 감정만, 가장 빨리 확인해요.', 1],
    ['standard', '스탠다드', '대화에서 자주 쓰는 감정까지 만들어요.', 2],
    ['pro', '프로', '더 섬세한 감정까지 만들어요.', 3],
    ['max', '맥스', '앱에서 쓰는 반응 전부예요. 가장 오래 걸리고 비용도 가장 커요.', 4]
  ];
  const COST_WORD = ['없음', '적음', '보통', '많음', '가장 많음'];
  const KINDS = [['INTERVIEW', '인터뷰'], ['ARTICLE', '기사'], ['TRANSCRIPT', '받아쓰기'], ['KAKAO_EXPORT', '카톡']];
  const REGISTERS = [['FORMAL', '공식 자리'], ['CASUAL', '캐주얼 자리']];
  const SUBJECT_KINDS = [['PUBLIC_FIGURE', '공인'], ['PRIVATE_PERSON', '개인']];
  const CHAPTERS = [['FAN_CALL', '팬과 첫 통화'], ['FAMILY_CALL', '가족과 통화']];
  // 모델 준비 방식(계획 2차 약속 2). 기본은 프롬프트만이다.
  const MODES = [['PROMPT_ONLY', '프롬프트만'], ['BIND_EXISTING', '학습된 모델 연결'], ['TRAIN', '학습해서 쓰기']];
  // 사용 근거는 선택이다. 메모만 받고 쓰는 곳은 팀 내부 사용으로 보낸다(약속 2 기본값과 같다).
  const DEFAULT_SCOPE = '팀 내부 사용';
  // 파일이 이보다 많으면 목록을 요약 한 줄로 접는다. 확인할 점이 있는 파일은 접어도 보인다.
  const FILE_FOLD = 6;
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
  function tierOf(value) { return VIDEO_TIERS.some((t) => t[0] === value) ? value : 'none'; }
  function tierName(value) { return labelOf(VIDEO_TIERS, tierOf(value)); }
  // 시그니처 포즈(D-0165): 이름과 동작이 있어야 쓴다. 앞뒤 공백은 뗀다.
  function sigOf(value) {
    const v = value || {};
    const sig = { title: text(v.title).trim(), motion: text(v.motion).trim(), useWhen: text(v.useWhen).trim() };
    return sig.title && sig.motion ? sig : null;
  }
  // 등급 고르기 카드. 원문 화면과 진행 화면의 영상 만들기가 같은 카드를 쓴다. paidOnly면 '영상 없이'를 뺀다.
  function tierCardsHTML(name, value, opts) {
    const o = opts || {};
    const cur = tierOf(value);
    return VIDEO_TIERS.filter((t) => !(o.paidOnly && t[0] === 'none')).map((t) => {
      // 시간·비용 네 칸. '영상 없이'는 설명이 비용 없음을 말하므로 칸을 두지 않는다.
      const meter = t[3] ? '<span class="vt-cost" role="img" aria-label="시간·비용 ' + COST_WORD[t[3]] + '">' + [1, 2, 3, 4].map((n) => '<i' + (n <= t[3] ? ' class="on"' : '') + '></i>').join('') + '</span>' : '';
      return '<label class="vt-opt"><input type="radio" name="' + escapeHTML(name) + '" value="' + t[0] + '"' + (t[0] === cur ? ' checked' : '') + (o.disabled ? ' disabled' : '') + '><span class="vt-tx"><span class="vt-top"><b>' + t[1] + '</b>' + meter + '</span><small>' + t[2] + '</small></span></label>';
    }).join('');
  }
  // 영상 상태 한 줄(약속 5 videoStatus·videoLabel). 상태를 알면 등급 이름을 붙여 화면마다 같은 말로 쓰고,
  // 영상이 없으면 빈칸이다(목록마다 '영상 없음'을 붙이지 않는다). 모르는 상태일 때만 서버 videoLabel을 쓴다.
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
  function isPhotoName(name) { return PHOTO_EXTENSIONS.indexOf(extOf(name)) >= 0; }
  // 시작한 뒤 진행 카드에 보일 말(약속 3 상태, 약속 5 영상). 대화가 먼저 되고 영상은 그 뒤에 만든다.
  // c: 캐릭터 진행(createIntake progress), chat: 대화 준비, o: { auto, tier }(이 화면 설정).
  const DONE_LABEL = { chat_ready: '대화 가능', running: '만드는 중', needs_review: '확인 필요', failed: '실패', stopped: '멈춤', draft: '만드는 중' };
  function doneView(c0, chat0, o0) {
    const c = c0 || {};
    const chat = chat0 || {};
    const o = o0 || {};
    const auto = o.auto !== false;
    // 상태 이름은 모든 화면이 같은 말을 쓴다(약속 3 statusLabel). 서버가 상태를 주지 않으면 예전처럼 진행 기록에서 짐작한다.
    const ready = c.chatReady === true || chat.ready === true;
    const st = ready ? 'chat_ready' : c.status || (c.failed ? 'failed' : c.awaiting ? 'needs_review' : 'running');
    const title = (st !== 'chat_ready' && c.statusLabel) || DONE_LABEL[st] || '만드는 중';
    let body = '';
    if (st === 'failed') body = '어느 단계에서 멈췄는지 진행 화면에서 봐 주세요.';
    else if (st === 'needs_review') body = '진행 화면에서 확인할 차례가 있어요. 확인하면 이어서 만들어요.';
    else if (st === 'stopped') body = '진행 화면에서 멈춘 까닭을 봐 주세요.';
    else if (st !== 'chat_ready') body = auto ? (chat.reason && !c.status ? chat.reason : '보통 15~20분 걸려요. 이 화면을 열어 두면 다 됐을 때 대화해 보기 버튼이 생겨요.') : '출처 정리가 끝나면 진행 화면에 확인할 차례가 떠요.';
    const tier = tierOf(c.videoTier || o.tier);
    const vs = c.videoStatus;
    const on = tier !== 'none' || vs === 'making' || vs === 'ready';
    const vReady = on && vs === 'ready';
    const vFailed = on && vs === 'failed';
    // 영상 상태를 주는 서버면 다 되거나 실패할 때까지 '만드는 중'으로 본다. 그 필드가 없는 서버면 기다리는 중으로만 적는다.
    // 사람 확인 모드는 영상을 자동으로 시작하지 않는다(QA v5 E6). 실제 작업이 돌 때만 '만드는 중'이다.
    const making = on && typeof vs === 'string' && !vReady && !vFailed && (vs === 'making' || auto);
    if (on && st === 'chat_ready') {
      if (vReady) body = '영상까지 다 만들었어요. 대화해 보기에서 영상과 함께 대화해요.';
      else if (vFailed) body = '대화는 지금 해 볼 수 있어요. 영상은 만들지 못했어요. 진행 화면에서 까닭을 봐 주세요.';
      else if (!making) body = '대화는 지금 해 볼 수 있어요. 영상은 진행 화면에서 영상 만들기를 눌러 시작해요.';
      else body = '대화는 지금 해 볼 수 있어요. 영상은 이어서 만들고 있어요. 다 되면 대화할 때 영상이 나와요.';
    } else if (on && st === 'running' && body) body += ' 영상은 대화가 된 뒤에 이어서 만들어요.';
    const vText = making ? '영상 만드는 중 · ' + tierName(tier) : (!auto && vs === 'none') ? '영상은 진행 화면에서 시작해요 · ' + tierName(tier) : videoText({ videoTier: tier, videoStatus: vs, videoLabel: c.videoLabel });
    return {
      ready, status: st, title, body,
      tone: { chat_ready: 'ok', failed: 'fail', needs_review: 'wait', stopped: 'wait' }[st] || 'run',
      video: { show: ready && on, text: vText, tone: vReady ? 'ok' : vFailed ? 'fail' : 'run', making },
      chatLabel: vReady ? '영상과 함께 대화해 보기' : '대화해 보기'
    };
  }
  // 시작한 뒤 진행을 다시 읽을지: 대화 준비가 될 때까지, 그리고 영상 등급을 골랐으면 영상이 다 되거나 실패할 때까지.
  // 대화 API가 없는 서버면 멈추고, 영상 상태를 주지 않는 서버면 대화가 된 뒤에 멈춘다.
  function wantsPoll(S) {
    const c = S.character || {};
    if (!(S.finalized && S.cid)) return false;
    if (S.chat && S.chat.unavailable) return false;
    const ready = !!(S.chat && S.chat.ready) || c.chatReady === true;
    if (!ready) return true;
    const tier = tierOf(c.videoTier || (S.settings && S.settings.videoTier));
    // 사람 확인 모드는 영상이 저절로 시작되지 않으니 '없음'에서 기다리지 않는다(QA v5 E6).
    const auto = c.autoReview !== false && !(S.settings && S.settings.autoReview === false);
    return typeof c.videoStatus === 'string' && (c.videoStatus === 'making' || (c.videoStatus === 'none' && tier !== 'none' && auto));
  }
  // 서버 기록이 사진인지. fileType을 주지 않는 서버면 확장자로 본다.
  function isPhotoRecord(rec) {
    const t = text(rec && rec.fileType);
    return t ? t === 'photo' : isPhotoName(rec && rec.filename);
  }

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
  // 파일 이름과 확장자로 종류를 짐작한다. 이름에 실마리가 없으면 null(서버가 내용으로 짐작한 값을 쓴다, 계획 3차 약속 4).
  function kindHint(filename) {
    const ext = extOf(filename);
    const name = text(filename).toLowerCase();
    if (ext === '.srt' || ext === '.vtt') return 'TRANSCRIPT';
    if (/kakao|카톡|카카오/.test(name) || ext === '.csv') return 'KAKAO_EXPORT';
    if (/기사|뉴스|article|news/.test(name)) return 'ARTICLE';
    if (/받아쓰기|자막|transcript|subtitle|vlog|브이로그|방송|유튜브|youtube|라디오|radio|podcast|팟캐스트|라이브|casual/.test(name)) return 'TRANSCRIPT';
    if (/인터뷰|interview|press|기자회견|회견/.test(name)) return 'INTERVIEW';
    return null;
  }
  // 사람이 카드에서 고칠 수 있다. 실마리가 없으면 인터뷰로 둔다.
  function guessKind(filename) { return kindHint(filename) || 'INTERVIEW'; }
  // 서버가 원문에서 찾은 화자 이름(줄 수 많은 순). 없는 서버면 빈 목록.
  function speakersOf(rec) {
    return (Array.isArray(rec && rec.detectedSpeakers) ? rec.detectedSpeakers : []).map((s) => text(s && typeof s === 'object' ? s.name : s).trim()).filter(Boolean);
  }
  // 원문에서 찾은 대상 화자 제안: 서버가 표시 이름과 맞춘 화자만 쓴다. 줄 수만으로 고르지 않는다(QA v5 A-03).
  function suggestedSpeaker(rec) {
    return text(rec && rec.suggested && rec.suggested.subjectSpeaker).trim();
  }
  // 표시 이름과 맞는 화자가 없을 때 고를 후보. 서버가 카톡을 내보낸 본인('나')은 뺀다.
  function speakerChoices(rec) {
    const list = rec && rec.suggested && Array.isArray(rec.suggested.subjectChoices) ? rec.suggested.subjectChoices : [];
    return list.map((s) => text(s).trim()).filter(Boolean);
  }
  // 조사 '으로/로': 받침이 있으면(ㄹ 받침 빼고) '으로'. 한글이 아니면 '(으)로'.
  function ro(word) {
    const c = text(word).trim().slice(-1).charCodeAt(0) - 0xac00;
    if (!(c >= 0 && c < 11172)) return '(으)로';
    const jong = c % 28;
    return jong && jong !== 8 ? '으로' : '로';
  }
  // 만든 날짜 '11/10'. 읽을 수 없으면 빈칸.
  function shortDate(iso) {
    const d = iso ? new Date(iso) : null;
    return d && !isNaN(d.getTime()) ? (d.getMonth() + 1) + '/' + d.getDate() : '';
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
    const size = Number(file && file.size) || 0;
    if (isPhotoName(name)) {
      if (size > PHOTO_MAX_BYTES) return '사진이 15MB보다 커요. 더 작은 사진을 올려 주세요.';
      if (size === 0) return '빈 파일이에요. 다른 사진을 올려 주세요.';
      return null;
    }
    if (EXTENSIONS.indexOf(extOf(name)) < 0) return '이 형식은 받을 수 없어요. 원문은 txt, srt, vtt, csv, json, 사진은 jpg, png, webp로 올려 주세요.';
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
  // 올린 원문 요약: 종류별·말한 자리별 개수와 준비된 수. 긴 목록을 접을 때 이 한 줄을 보인다.
  function fileSummary(items) {
    const list = (items || []).filter((i) => i.phase !== 'rejected');
    const count = (pairs, key) => pairs.map((p) => [p[1], list.filter((i) => (i.meta || {})[key] === p[0]).length]).filter((x) => x[1] > 0);
    return {
      total: list.length,
      ready: list.filter((i) => i.tone === 'ok').length,
      attention: list.filter((i) => i.tone !== 'ok').length,
      kinds: count(KINDS, 'kind'),
      registers: count(REGISTERS, 'register')
    };
  }
  function modeOf(value) { return MODES.some((m) => m[0] === value) ? value : 'PROMPT_ONLY'; }
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
      thumbs: {}, // key → 이 브라우저에서 고른 사진의 미리보기 주소(서버가 주소를 주지 않아도 바로 보인다)
      busy: null, // 'create' | 'import' | 'finalize' | 'delete' | 'remove:<key>'
      error: null,
      notice: null,
      finalized: null,
      settings: null, // { modelMode, autoReview, videoTier } 이 화면에서 만든 초안이면 보낸 값, 다시 열면 서버 값
      character: null, // 시작한 뒤 캐릭터 진행(GET /api/characters/{cid})
      chat: null, // 대화 준비 상태(GET /api/characters/{cid}/chat/meta, 계획 2차 약속 1)
      projects: null,
      drafts: null, // 시작하지 않은 초안(GET /api/sources/drafts). 그 API가 없는 서버면 null로 둔다.
      announce: ''
    };
    let seq = 0;
    let active = 0;
    let lastStatus = null; // 왼쪽 목록을 다시 읽을지 견줄 직전 진행 상태
    const aborts = {};
    const chains = {};
    let pendingSaves = 0;

    function emit() { listeners.forEach((fn) => { try { fn(state); } catch (error) { /* 화면 오류가 상태를 막지 않게 */ } }); }
    const URLS = (global && global.URL) || (typeof URL !== 'undefined' ? URL : null);
    function makeThumb(file) {
      try { return URLS && typeof URLS.createObjectURL === 'function' && file && typeof file === 'object' && typeof file.slice === 'function' ? URLS.createObjectURL(file) : ''; } catch (error) { return ''; }
    }
    function dropThumb(key) {
      const u = state.thumbs[key];
      if (u && URLS && typeof URLS.revokeObjectURL === 'function') { try { URLS.revokeObjectURL(u); } catch (error) { /* 이미 풀린 주소 */ } }
      delete state.thumbs[key];
    }
    function dropThumbs() { Object.keys(state.thumbs).forEach(dropThumb); }
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
    function textFiles() { return files().filter((f) => !isPhotoRecord(f)); }
    function photoFiles() { return files().filter(isPhotoRecord); }
    function takenIds(exceptKey) {
      const ids = [];
      textFiles().forEach((f) => { if (keyOf(f.fileId) !== exceptKey) ids.push(metaOfRecord(f).textId); });
      state.uploads.forEach((u) => { if (u.phase !== 'rejected' && u.fileType !== 'photo' && u.key !== exceptKey) ids.push(u.meta.textId); });
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
      if (cid !== state.cid) { dropThumbs(); Object.assign(state, { uploads: [], overlay: {}, saving: {}, saveError: {}, fieldErrors: {}, rawInput: {}, cardKey: {}, settings: null, character: null, chat: null }); }
      state.cid = cid;
      state.loading = true;
      state.loadError = null;
      state.draft = null;
      state.finalized = null;
      emit();
      try {
        state.draft = await request('GET', '/api/sources/' + encodeURIComponent(cid));
        // 이미 출처 정리를 시작한 초안은 다시 열어도 고치거나 다시 시작하지 못하게 잠근다.
        if (state.draft && state.draft.jobId) state.finalized = { jobId: state.draft.jobId };
      } catch (error) {
        state.loadError = error.status === 404 ? { missing: true, text: '이 초안을 찾을 수 없어요. 이미 지웠거나 주소가 바뀌었을 수 있어요.' } : { missing: false, text: errorText(error) };
      }
      state.loading = false;
      emit();
      if (state.draft) await progress();
    }

    // 진행과 대화 준비를 함께 읽는다. 아직 없는 API·캐릭터는 조용히 넘긴다(다른 묶음이 머지되기 전에도 화면이 돈다).
    async function progress() {
      if (!state.cid) return null;
      const cid = encodeURIComponent(state.cid);
      try {
        const d = await request('GET', '/api/characters/' + cid);
        const stages = Array.isArray(d && d.stages) ? d.stages : [];
        state.character = {
          modelMode: d && d.modelMode ? d.modelMode : null,
          autoReview: d && typeof d.autoReview === 'boolean' ? d.autoReview : null,
          progress: (d && d.progress) || null,
          // 계획 3차 약속 3: 서버가 한 곳에서 정한 상태·대화 가능·목표 진행. 없는 서버면 아래 옛 표시로 돌아간다.
          status: d && d.status ? text(d.status) : null,
          statusLabel: d && d.statusLabel ? text(d.statusLabel) : '',
          chatReady: d && typeof d.chatReady === 'boolean' ? d.chatReady : null,
          goal: d && d.goal && Number(d.goal.total) > 0 ? d.goal : null,
          displayName: d && d.displayName ? text(d.displayName) : '',
          // 약속 5: 영상 등급과 상태. 그 필드가 없는 서버면 null로 두고 영상 줄을 보이지 않는다.
          videoTier: d && d.videoTier ? tierOf(d.videoTier) : null,
          videoStatus: d && typeof d.videoStatus === 'string' ? d.videoStatus : null,
          videoLabel: d && d.videoLabel ? text(d.videoLabel) : '',
          awaiting: Boolean(d && ((d.pendingGates && d.pendingGates.length) || d.awaitingHuman)),
          running: Boolean(d && d.job),
          failed: stages.some((s) => text(s && s.status).toUpperCase() === 'CHECK_FAILED')
        };
      } catch (error) { /* 시작 전에는 캐릭터 진행이 없을 수 있다 */ }
      if (state.finalized) {
        try {
          const m = await request('GET', '/api/characters/' + cid + '/chat/meta');
          state.chat = { ready: m && m.ready === true, reason: text(m && m.reason) };
        } catch (error) {
          if (error.status === 404 || error.status === 405) state.chat = { ready: false, unavailable: true, reason: '' };
        }
      }
      emit();
      // 상태가 바뀌면 왼쪽 캐릭터 목록도 다시 읽는다(본문은 대화 가능인데 목록만 만드는 중으로 남지 않게, QA v5 A-07).
      const c = state.character || {};
      const now = [c.status, c.chatReady, c.videoStatus, state.chat && state.chat.ready].join('|');
      if (lastStatus !== null && now !== lastStatus && state.projects) await projects();
      lastStatus = now;
      return { character: state.character, chat: state.chat };
    }
    async function projects() {
      try {
        const data = await request('GET', '/api/projects');
        state.projects = Array.isArray(data && data.characters) ? data.characters : [];
      } catch (error) { state.projects = state.projects || []; }
      emit();
      return state.projects;
    }
    // 만들다 만 초안 목록. 서버에 API가 없거나 실패하면 조용히 숨긴다.
    async function drafts() {
      try {
        const data = await request('GET', '/api/sources/drafts');
        const list = Array.isArray(data) ? data : Array.isArray(data && data.drafts) ? data.drafts : [];
        state.drafts = list.filter((x) => x && x.characterId);
      } catch (error) { state.drafts = null; }
      emit();
      return state.drafts;
    }
    // 화면에 보일 생성 설정: 서버 값(초안·캐릭터)이 있으면 그것, 없으면 이 화면에서 보낸 값.
    function settings() {
      const d = state.draft || {};
      const c = state.character || {};
      const s = state.settings || {};
      const pick = (k) => (d[k] != null ? d[k] : c[k] != null ? c[k] : s[k] != null ? s[k] : null);
      return { modelMode: pick('modelMode'), autoReview: pick('autoReview'), videoTier: tierOf(pick('videoTier')), signaturePose: sigOf(pick('signaturePose')) };
    }
    // 시작 전에 영상 등급을 바꾼다(약속 5 PATCH settings). 실패하면 화면 값은 그대로 두고 알린다.
    async function setTier(value) {
      const tier = tierOf(value);
      if (!state.cid || state.finalized || state.busy) return false;
      state.busy = 'tier';
      state.error = null;
      emit();
      let ok = false;
      try {
        const data = await request('PATCH', '/api/sources/' + encodeURIComponent(state.cid) + '/settings', { videoTier: tier });
        const saved = tierOf((data && data.videoTier) || tier);
        state.settings = Object.assign({}, state.settings || {}, { videoTier: saved });
        if (state.draft) state.draft.videoTier = saved;
        if (state.character) state.character.videoTier = saved;
        state.announce = '영상을 ' + tierName(saved) + ro(tierName(saved)) + ' 바꿨어요.';
        ok = true;
      } catch (error) {
        state.error = error.status === 404 || error.status === 405 ? '이 서버에서는 아직 영상 등급을 바꿀 수 없어요.' : '영상 등급을 바꾸지 못했어요. ' + errorText(error);
      }
      state.busy = null;
      emit();
      if (ok) await refresh();
      return ok;
    }

    // 시그니처 포즈(D-0165)를 저장한다. 영상 등급은 그대로 두고 함께 보낸다.
    async function setSignature(pose) {
      const sig = sigOf(pose);
      if (!state.cid || state.finalized || state.busy || !sig) return false;
      state.busy = 'tier';
      state.error = null;
      emit();
      let ok = false;
      try {
        const data = await request('PATCH', '/api/sources/' + encodeURIComponent(state.cid) + '/settings', { videoTier: settings().videoTier, signaturePose: sig });
        const saved = sigOf(data && data.signaturePose) || sig;
        state.settings = Object.assign({}, state.settings || {}, { signaturePose: saved });
        if (state.draft) state.draft.signaturePose = saved;
        state.announce = '시그니처 포즈를 저장했어요.';
        ok = true;
      } catch (error) {
        state.error = '시그니처 포즈를 저장하지 못했어요. ' + errorText(error);
      }
      state.busy = null;
      emit();
      if (ok) await refresh();
      return ok;
    }

    function validateDraft(input) {
      const v = input || {};
      const errors = {};
      const tooLong = (name, label, n) => { if (!errors[name] && text(v[name]).trim().length > n) errors[name] = label + ' ' + n + '자까지 적을 수 있어요.'; };
      if (!text(v.displayName).trim()) errors.displayName = '표시 이름을 적어 주세요.';
      if (!SUBJECT_KINDS.some((k) => k[0] === v.subjectKind)) errors.subjectKind = '공인인지 개인인지 골라 주세요.';
      if (!text(v.age).trim()) errors.age = '나이를 적어 주세요.';
      if (!text(v.gender).trim()) errors.gender = '성별을 골라 주세요.';
      if (!text(v.job).trim()) errors.job = '하는 일을 적어 주세요.';
      // 서버 한도와 같다(KnownFacts). 넘으면 그 칸 옆에 알린다(QA v5 A-06).
      tooLong('age', '나이는', 20);
      tooLong('job', '하는 일은', 60);
      tooLong('background', '한 줄 배경은', 400);
      if (tierOf(v.videoTier) !== 'none') {
        if (!text(v.sigTitle).trim()) errors.sigTitle = '시그니처 포즈 이름을 적어 주세요.';
        if (!text(v.sigMotion).trim()) errors.sigMotion = '어떤 동작인지 적어 주세요.';
      }
      return errors;
    }
    async function createDraft(input) {
      const errors = validateDraft(input);
      if (Object.keys(errors).length) {
        // 칸 오류를 보일 때는 지난번 서버 오류 문장을 지운다(고친 뒤 다른 칸 오류가 나도 옛 문장이 남지 않게).
        if (state.error) { state.error = null; emit(); }
        return { errors };
      }
      state.busy = 'create';
      state.error = null;
      emit();
      try {
        const modelMode = modeOf(input.modelMode);
        const autoReview = input.autoReview !== false;
        const videoTier = tierOf(input.videoTier);
        const body = {
          displayName: text(input.displayName).trim(),
          subjectKind: input.subjectKind,
          usageBasis: { scope: text(input.scope).trim() || DEFAULT_SCOPE, notes: text(input.notes).trim() },
          knownFacts: { age: text(input.age).trim(), gender: text(input.gender).trim(), job: text(input.job).trim(), background: text(input.background).trim() },
          modelMode,
          autoReview,
          videoTier
        };
        if (input.chapterTemplate) body.chapterTemplate = input.chapterTemplate;
        const signaturePose = videoTier === 'none' ? null : sigOf({ title: input.sigTitle, motion: input.sigMotion, useWhen: input.sigWhen });
        if (signaturePose) body.signaturePose = signaturePose;
        const data = await request('POST', '/api/sources/drafts', body);
        state.busy = null;
        if (o.onCid) o.onCid(data.characterId);
        await load(data.characterId);
        state.settings = { modelMode, autoReview, videoTier, signaturePose };
        emit();
        return { characterId: data.characterId };
      } catch (error) {
        state.busy = null;
        state.error = errorText(error);
        emit();
        return { error: state.error };
      }
    }

    // 원문과 사진을 같은 줄에 세운다. 사진은 확장자로 알아보고, 만들기를 시작한 뒤에도 사진만은 더 올릴 수 있다(나중에 영상 만들기).
    // photoOnly(사진 칸에서 고르거나 떨어뜨림)면 사진이 아닌 파일은 사진 칸에서 거절한다.
    function addFiles(list, opts) {
      if (!state.draft) return [];
      const photoOnly = !!(opts && opts.photoOnly);
      const added = [];
      Array.from(list || []).forEach((file) => {
        const photo = photoOnly || isPhotoName(file && file.name);
        if (state.finalized && !photo) return;
        const key = 'u' + (++seq);
        const problem = photo && !isPhotoName(file && file.name) ? '사진은 jpg, png, webp 파일로 올려 주세요.' : checkFile(file);
        const hint = photo ? null : kindHint(file.name);
        const kind = hint || 'INTERVIEW';
        const entry = {
          key,
          file,
          fileType: photo ? 'photo' : 'text',
          filename: text(file.name),
          size: Number(file.size) || 0,
          contentType: text(file.type) || 'application/octet-stream',
          phase: problem ? 'rejected' : 'queued',
          progress: 0,
          fileId: null,
          step: 'start',
          error: problem,
          kindFromName: !!hint,
          touched: {}, // 올리는 동안 사람이 고친 칸. 서버 제안으로 덮지 않는다.
          // 원문 이름은 보이지 않게 파일 이름으로 정하고, 대상 화자는 비워 보내 서버가 원문에서 찾은 이름을 쓰게 한다(약속 4).
          // 사진에는 원문 정보가 없어 모두 빈칸으로 보낸다.
          meta: photo ? { textId: '', kind: '', register: '', subjectSpeaker: '', userSpeaker: '', date: '', sourceUrl: '' } : {
            textId: problem ? '' : suggestTextId(file.name, kind, takenIds()),
            // 이름에 실마리가 없으면 종류와 자리를 비워 보내 서버가 내용으로 정하게 한다. 인터뷰로 먼저 읽으면
            // 이름 없는 카톡 파일에서 '[엄마] [오전 9' 같은 화자가 잡힌다.
            kind: hint || '',
            register: hint ? defaultRegister(kind) : '',
            subjectSpeaker: '',
            userSpeaker: '',
            date: '',
            sourceUrl: ''
          }
        };
        if (photo && !problem) { const u = makeThumb(file); if (u) state.thumbs[key] = u; }
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
        // 사진에는 원문 정보가 없어 빈 본문으로 확인만 한다(서버가 사진에 화자 정보를 받지 않는다).
        const rec = await request('POST', filesPath(entry.fileId) + '/complete', entry.fileType === 'photo' ? {} : metaBody(entry.meta));
        if (entry.cancelled) throw Object.assign(new Error('abort'), { aborted: true });
        state.uploads = state.uploads.filter((u) => u !== entry);
        upsert(rec);
        state.announce = entry.filename + (entry.fileType === 'photo' ? ' 사진을 올렸어요.' : ' 파일을 올렸어요.');
        // 확인하는 동안 사람이 고친 값과 서버가 원문에서 짐작한 값을 이어서 저장한다. 사진은 고칠 칸이 없다.
        if (entry.fileType !== 'photo') {
          const next = afterCheck(rec, entry);
          if (!sameMeta(metaOfRecord(rec), next)) queuePatch(rec.fileId, next);
        }
      } catch (error) {
        delete aborts[entry.key];
        if (entry.cancelled || error.aborted) {
          dropThumb(entry.key);
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
    // 확인 응답 뒤 저장할 값: 서버 값에 사람이 올리는 동안 고친 칸을 얹고, 아직 아무도 정하지 않은 칸은 서버 제안(약속 4)으로 채운다.
    // 대상 화자가 비었으면 서버 제안이나 원문에서 가장 많이 말한 화자를 쓴다. 제안을 주지 않는 옛 서버면 예전처럼 표시 이름을 넣는다.
    function afterCheck(rec, entry) {
      const next = {};
      META_FIELDS.forEach((f) => { next[f] = entry.touched[f] ? text(entry.meta[f]) : text(rec[f] == null ? '' : rec[f]); });
      const sug = (rec && rec.suggested) || {};
      if (!entry.touched.kind && !entry.kindFromName && KINDS.some((k) => k[0] === sug.kind) && sug.kind !== next.kind) {
        next.kind = sug.kind;
        if (!entry.touched.register) next.register = REGISTERS.some((x) => x[0] === sug.register) ? sug.register : (defaultRegister(sug.kind) || next.register);
      }
      if (!next.subjectSpeaker.trim()) {
        const old = rec && rec.suggested === undefined && rec.detectedSpeakers === undefined;
        next.subjectSpeaker = suggestedSpeaker(rec) || (old ? text(state.draft && state.draft.subject && state.draft.subject.displayName) : '');
      }
      // 상대 화자도 서버가 찾은 값으로 채운다(QA v5 A-23). 대상 화자와 같은 이름은 넣지 않는다.
      const partner = text(sug.userSpeaker).trim();
      if (!entry.touched.userSpeaker && !next.userSpeaker.trim() && partner && partner !== next.subjectSpeaker.trim()) next.userSpeaker = partner;
      return next;
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
      if (entry) {
        entry.meta = meta;
        entry.touched[field] = true;
        emit();
        return Promise.resolve();
      }
      return queuePatch(rec.fileId, meta);
    }
    // 원문에서 찾은 이름 단추로 대상 화자를 정한다. 상대 화자가 비었거나 같은 이름이면 서버가 권한 상대로 바꾼다.
    function pickSpeaker(key, name) {
      const rec = files().find((f) => keyOf(f.fileId) === key);
      const who = text(name).trim();
      if (!rec || !who || state.finalized) return null;
      const meta = Object.assign({}, metaOfRecord(rec), { subjectSpeaker: who });
      const partner = text(rec.suggested && rec.suggested.userSpeaker).trim();
      const others = speakersOf(rec).filter((n) => n !== who);
      if (!text(meta.userSpeaker).trim() || text(meta.userSpeaker).trim() === who) meta.userSpeaker = partner && partner !== who ? partner : others.length === 1 ? others[0] : '';
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
        dropThumb(key);
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
        dropThumb(key);
        delete state.fieldErrors[key];
        delete state.rawInput[key];
        delete state.overlay[rec.fileId];
        state.announce = rec.filename + (isPhotoRecord(rec) ? ' 사진을 지웠어요.' : ' 파일을 지웠어요.');
      } catch (error) {
        state.error = rec.filename + (isPhotoRecord(rec) ? ' 사진을' : ' 파일을') + ' 지우지 못했어요. ' + errorText(error);
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
        const rec = await request('POST', '/api/sources/' + encodeURIComponent(state.cid) + '/import-path', { path: p });
        state.announce = '경로에서 원문을 가져왔어요.';
        // 서버가 올린 파일과 같은 확인을 마친 기록을 준다. 찾은 화자·상대를 올린 파일처럼 채운다(QA v5 A-05).
        if (rec && rec.fileId) {
          upsert(rec);
          if (!isPhotoRecord(rec)) {
            const next = afterCheck(rec, { touched: {}, kindFromName: false, meta: {} });
            if (!sameMeta(metaOfRecord(rec), next)) queuePatch(rec.fileId, next);
          }
        }
      } catch (error) {
        state.error = '가져오지 못했어요. ' + errorText(error);
      }
      state.busy = null;
      await refresh();
    }

    // 시작 가능 조건: 서버 canFinalize가 참이고, 화면에 올리는 중·실패한 파일, 저장 중이거나 고칠 곳이 남은 칸이 없어야 한다.
    // 영상 등급을 골랐으면 준비된 사진이 1장 이상 있어야 한다(약속 5). 서버가 같은 문제를 적어 주면 그 문장만 쓴다.
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
      const serverProblems = d.canFinalize !== true ? (d.problems || []).map(text) : [];
      // 서버가 같은 뜻을 제 말로 적어 주면(예: '대화나 글이 담긴 원문을 하나 이상 올려 주세요.') 이 화면 문장은 빼서 두 번 보이지 않게 한다.
      const noText = !textFiles().length && !state.uploads.some((u) => u.phase !== 'rejected' && u.fileType !== 'photo');
      if (noText && !serverProblems.some((p) => /원문.*하나 이상/.test(p))) reasons.push('원문 파일을 하나 이상 올려 주세요.');
      const needPhoto = settings().videoTier !== 'none' && !photoFiles().some((f) => f.status === 'ready');
      if (needPhoto && !serverProblems.some((p) => /사진/.test(p))) reasons.push('영상을 만들려면 얼굴이 잘 보이는 사진을 1장 이상 올려 주세요.');
      serverProblems.forEach((p) => { if (reasons.indexOf(p) < 0) reasons.push(p); });
      if (d.canFinalize !== true && !reasons.length) reasons.push('아직 시작할 수 없어요. 파일마다 확인할 점을 봐 주세요.');
      return { ready: d.canFinalize === true && !reasons.length, reasons, needPhoto };
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
        state.announce = '만들기를 시작했어요.';
      } catch (error) {
        state.error = '만들기를 시작하지 못했어요. ' + errorText(error);
      }
      state.busy = null;
      emit();
      if (!state.finalized) await refresh(); else await progress();
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
      dropThumbs();
      Object.assign(state, { cid: null, draft: null, uploads: [], overlay: {}, saving: {}, saveError: {}, fieldErrors: {}, rawInput: {}, cardKey: {}, busy: null, finalized: null, loadError: null, settings: null, character: null, chat: null, announce: '초안과 올린 원문을 지웠어요.' });
      if (o.onCid) o.onCid(null);
      emit();
      // 지운 초안이 만들던 초안 목록과 왼쪽 캐릭터 목록에서도 빠지게 둘 다 다시 읽는다(QA v5 A-04).
      await Promise.all([drafts(), projects()]);
      return true;
    }
    function reset() {
      dropThumbs();
      Object.assign(state, { cid: null, draft: null, uploads: [], overlay: {}, saving: {}, saveError: {}, fieldErrors: {}, rawInput: {}, cardKey: {}, busy: null, finalized: null, loadError: null, error: null, notice: null, settings: null, character: null, chat: null });
      emit();
    }
    function dismiss(key) {
      dropThumb(key);
      state.uploads = state.uploads.filter((u) => !(u.key === key && u.phase === 'rejected'));
      emit();
    }

    // 카드 목록: 서버에 있는 파일 다음에 올리는 중인 파일. 올리는 중인 파일과 같은 자리를 서버 목록이 보여 주면 한 번만 쓴다.
    function items() {
      const uploading = new Set(state.uploads.map((u) => u.fileId).filter(Boolean));
      const out = [];
      textFiles().forEach((f) => {
        if (uploading.has(f.fileId)) return;
        const key = keyOf(f.fileId);
        const st = f.status === 'ready' ? ['ok', '준비됐어요'] : f.status === 'problem' ? ['wait', '확인이 필요해요'] : ['muted', '다 올라가지 않았어요'];
        const problems = (f.problems || []).map(text);
        if (f.status === 'pending' && !problems.length) problems.push('이 파일은 끝까지 올라가지 않았어요. 지우고 다시 올려 주세요.');
        // 원문에서 찾은 화자가 지금 대상 화자와 다르면 한 번에 바꾸는 단추를 건넨다(약속 4 suggested·detectedSpeakers).
        // 표시 이름과 맞는 화자를 찾지 못했으면 후보 이름을 단추로 늘어놓고 고르게 한다(QA v5 A-03).
        const meta = metaOfRecord(f);
        const found = suggestedSpeaker(f);
        const names = speakersOf(f);
        const cur = text(meta.subjectSpeaker).trim();
        const off = !cur || (names.length > 0 && names.indexOf(cur) < 0);
        const look = !state.finalized && f.status !== 'pending' && (f.status === 'problem' || off);
        const speaker = look && found && found !== cur ? found : '';
        const choices = look && !speaker && off ? speakerChoices(f).filter((n) => n !== cur) : [];
        out.push({ key, source: 'record', fileId: f.fileId, filename: text(f.filename), size: f.size, tone: st[0], status: st[1], progress: null, problems, speaker, choices, meta, display: Object.assign(metaOfRecord(f), state.rawInput[key] || {}), editable: f.status !== 'pending' && !state.finalized, removable: !state.finalized && state.busy !== 'remove:' + key, retry: false, saving: state.saving[key] || '', saveError: state.saveError[key] || '', fieldErrors: state.fieldErrors[key] || {} });
      });
      state.uploads.filter((u) => u.fileType !== 'photo').forEach((u) => {
        const map = { queued: ['muted', '기다리는 중'], starting: ['run', '준비하는 중'], sending: ['run', '올리는 중 ' + Math.round(u.progress * 100) + '%'], checking: ['run', '확인하는 중'], failed: ['fail', '올리지 못했어요'], rejected: ['fail', '받을 수 없는 파일'] };
        const st = map[u.phase] || ['muted', ''];
        out.push({ key: u.key, source: 'upload', fileId: u.fileId, filename: u.filename, size: u.size, tone: st[0], status: st[1], phase: u.phase, progress: u.phase === 'sending' ? u.progress : null, problems: u.error ? [u.error] : [], speaker: '', choices: [], meta: u.meta, display: Object.assign({}, u.meta, state.rawInput[u.key] || {}), editable: u.phase !== 'rejected' && !state.finalized, removable: !u.cancelled, retry: u.phase === 'failed', saving: '', saveError: '', fieldErrors: state.fieldErrors[u.key] || {} });
      });
      return out;
    }
    // 영상용 사진 목록(미리보기 칸). 서버가 미리보기 주소(previewUrl·thumbUrl·url)를 주면 쓰고, 없으면 이 브라우저에서 고른 사진을 보인다.
    // 만들기를 시작한 뒤에는 이미 쓴 사진을 지우지 못하게 한다.
    function photoItems() {
      const uploading = new Set(state.uploads.map((u) => u.fileId).filter(Boolean));
      const out = [];
      photoFiles().forEach((f) => {
        if (uploading.has(f.fileId)) return;
        const key = keyOf(f.fileId);
        const st = f.status === 'ready' ? ['ok', '준비됐어요'] : f.status === 'problem' ? ['wait', '확인이 필요해요'] : ['muted', '다 올라가지 않았어요'];
        const problems = (f.problems || []).map(text);
        if (f.status === 'pending' && !problems.length) problems.push('끝까지 올라가지 않았어요. 지우고 다시 올려 주세요.');
        // 열 수 없는 사진은 브라우저 깨진 그림 대신 사진 아이콘을 둔다(QA v5 A-14).
        const thumb = f.status === 'problem' ? '' : text(f.previewUrl || f.thumbUrl || f.url) || state.thumbs[key] || '';
        out.push({ key, source: 'record', fileId: f.fileId, filename: text(f.filename), size: f.size, tone: st[0], status: st[1], progress: null, problems, thumb, removable: !state.finalized && state.busy !== 'remove:' + key, retry: false });
      });
      state.uploads.filter((u) => u.fileType === 'photo').forEach((u) => {
        const map = { queued: ['muted', '기다리는 중'], starting: ['run', '준비하는 중'], sending: ['run', '올리는 중 ' + Math.round(u.progress * 100) + '%'], checking: ['run', '확인하는 중'], failed: ['fail', '올리지 못했어요'], rejected: ['fail', '받을 수 없는 사진'] };
        const st = map[u.phase] || ['muted', ''];
        out.push({ key: u.key, source: 'upload', fileId: u.fileId, filename: u.filename, size: u.size, tone: st[0], status: st[1], phase: u.phase, progress: u.phase === 'sending' ? u.progress : null, problems: u.error ? [u.error] : [], thumb: state.thumbs[u.key] || '', removable: !u.cancelled, retry: u.phase === 'failed' });
      });
      return out;
    }
    function uploading() { return state.uploads.some((u) => ACTIVE.indexOf(u.phase) >= 0); }

    return {
      state, load, refresh, progress, projects, drafts, settings, setTier, setSignature, createDraft, validateDraft, addFiles, retry, dismiss, editFile, pickSpeaker, removeFile, importPath, finalize, deleteDraft, reset, startState, items, photoItems, uploading,
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
    retry: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><polyline points="3 3 3 8 8 8"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5h13L22 12v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-6z"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    monitor: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    photo: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 8"/>',
    plus: '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>'
  };
  // 진행 화면(flow.js)과 같은 브랜드 마크.
  const MARK = '<svg class="fd-mark" viewBox="0 0 24 24" aria-hidden="true"><rect width="24" height="24" rx="6" fill="var(--fd-accent)"/><path d="M8.5 17V7h7.5M8.5 12h5" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="16.4" cy="16.4" r="1.7" fill="#fff"/></svg>';
  const THEMES = [['system', 'monitor', '시스템 설정 따르기'], ['light', 'sun', '밝은 화면'], ['dark', 'moon', '어두운 화면']];
  // 진행 화면과 같은 이름 규칙: 이름이 없으면 '이름 미정 · slug (11/7)'.
  function displayName(name, id) {
    const n = text(name).trim();
    if (n && n !== text(id)) return n;
    const m = /^cf-(\d{4})(\d{2})(\d{2})-(.+)$/.exec(text(id));
    return m ? '이름 미정 · ' + m[4] + ' (' + Number(m[2]) + '/' + Number(m[3]) + ')' : text(id);
  }
  // 사이드바 캐릭터 한 줄. 진행 화면 사이드바와 같은 모양이고 누르면 그 캐릭터의 진행 화면으로 간다.
  // 이름·상태·진행 수는 서버가 정한 값(약속 3 displayName·status·goal)을 먼저 쓰고, 없으면 예전 계산으로 돌아간다.
  const STATUS_DOT = { chat_ready: 'ok', running: 'run', needs_review: 'wait', failed: 'fail' };
  function createdText(c) {
    const t = Date.parse(text(c.createdAt));
    if (!isFinite(t)) return '';
    const d = new Date(t);
    const two = (n) => (n < 10 ? '0' : '') + n;
    return (d.getMonth() + 1) + '/' + d.getDate() + ' ' + two(d.getHours()) + ':' + two(d.getMinutes());
  }
  // 진행 화면 사이드바와 같은 두 줄 모양: 이름(모티브 표시) 아래에 상태, 이름이 겹치면 만든 시각을 붙인다.
  function sideItemHTML(c, dup) {
    const name = text(c.displayName).trim() || displayName(c.name, c.id);
    const failed = (c.stages || []).some((s) => text(s && s.status).toUpperCase() === 'CHECK_FAILED');
    const p = c.progress || {};
    const st = c.status ? (STATUS_DOT[c.status] || '') : failed ? 'fail' : c.awaitingHuman ? 'wait' : c.job ? 'run' : p.total && p.done >= p.total ? 'ok' : '';
    const when = createdText(c);
    const sub = [text(c.statusLabel), dup && when ? when + ' 만듦' : ''].filter(Boolean).join(' · ');
    const motif = c.origin === 'SOURCE';
    return '<a class="fd-nav two" href="factory.html#c/' + E(encodeURIComponent(text(c.id))) + '" title="' + E(name + (sub ? ' · ' + sub : '')) + '">' +
      '<span class="fd-av" aria-hidden="true">' + E(Array.from(name)[0] || '?') + '<span class="st ' + st + '"></span></span>' +
      '<span class="lbl"><span class="nm"><span class="tx">' + E(name) + '</span>' + (motif ? '<span class="fd-org">모티브</span>' : '') + '</span>' +
      (sub ? '<small>' + E(sub) + '</small>' : '') + '</span></a>';
  }
  function sideHTML(list, theme) {
    const shown = (list || []).filter((c) => !c.archived)
      .slice().sort((x, y) => (Date.parse(text(y.createdAt)) || 0) - (Date.parse(text(x.createdAt)) || 0));
    const counts = {};
    shown.forEach((c) => { const n = text(c.displayName).trim() || displayName(c.name, c.id); counts[n] = (counts[n] || 0) + 1; });
    const items = shown.map((c) => sideItemHTML(c, counts[text(c.displayName).trim() || displayName(c.name, c.id)] > 1)).join('');
    const themes = THEMES.map((t) => '<button type="button" data-act="theme" data-theme="' + t[0] + '" aria-pressed="' + (theme === t[0]) + '" aria-label="' + t[2] + '" title="' + t[2] + '">' + icon(t[1]) + '</button>').join('');
    return '<div class="fd-brand">' + MARK + '<div class="fd-word"><b>Foundry</b><small>캐릭터 공장</small></div></div>' +
      '<div class="fd-side-actions"><a class="btn block" href="sources.html" aria-current="page" title="원문으로 새 캐릭터" style="text-decoration:none">' + icon('user') + '<span class="lbl">원문으로 만들기</span></a></div>' +
      '<nav aria-label="캐릭터 탐색"><a class="fd-nav" href="factory.html#all" title="전체 캐릭터">' + icon('grid') + '<span class="lbl">전체 캐릭터</span><span class="num">' + (list ? shown.length + '명' : '') + '</span></a>' +
      '<a class="fd-nav" href="factory.html#all/mine" title="받은 일">' + icon('inbox') + '<span class="lbl">받은 일</span></a>' +
      '<h2>캐릭터</h2>' + (list ? items || '<p class="hint" style="padding:0 8px">아직 없어요</p>' : '<p class="hint" style="padding:0 8px">불러오는 중이에요</p>') + '</nav>' +
      '<div class="fd-side-foot"><a class="fd-help" href="help.html" target="_blank" rel="noopener" title="사용 안내" aria-label="사용 안내">?</a><div class="fd-theme" role="group" aria-label="화면 테마">' + themes + '</div><div class="fd-foot-links"><a href="help.html" target="_blank" rel="noopener">사용 안내</a></div></div>';
  }
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
      '<div class="src-file-acts" data-speaker-row hidden></div>' +
      '<div class="src-file-acts" data-retry-row hidden><button type="button" class="btn" data-act="retry">' + icon('retry') + '다시 올리기</button></div>' +
      '<div class="src-fields" id="' + id('body') + '" data-body>' +
        fld('kind', '종류', '<select id="' + id('kind') + '" data-field="kind" aria-describedby="' + id('kind') + '-h">' + options(KINDS, item.meta.kind) + '</select>', '') +
        fld('register', '말한 자리', '<select id="' + id('register') + '" data-field="register" aria-describedby="' + id('register') + '-h">' + options(REGISTERS, item.meta.register) + '</select>', '') +
        fld('subjectSpeaker', '대상 화자 이름', input('subjectSpeaker', 'text'), '원문에 적힌 그 사람의 이름이에요.') +
        fld('userSpeaker', '상대 화자 이름', input('userSpeaker', 'text'), '카톡·대담에서 이야기 상대의 이름이에요. 없으면 비워 두세요.') +
        fld('date', '날짜', input('date', 'date'), '말하거나 쓴 날이에요.') +
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
      delRow: $('[data-del]'), delConfirm: $('[data-del-confirm]'), publicNote: $('[data-public-note]'),
      side: $('[data-side]'), headTheme: $('[data-head-theme]'), fileSum: $('[data-file-sum]'), startLead: $('[data-start-lead]'),
      doneTitle: $('[data-done-title]'), doneText: $('[data-done-text]'), prog: $('[data-prog]'), progText: $('[data-prog-text]'), chatLink: $('[data-chat-link]'),
      title: $('[data-title]'), intro: $('[data-intro]'), crumb: $('[data-crumb]'), resume: $('[data-resume]'), adv: $('[data-adv]'), startNote: $('[data-start-note]'),
      tierCards: $('[data-tier-cards]'), tierHint: $('[data-tier-hint]'), sumVideo: $('[data-sum-video]'), tierEdit: $('[data-tier-edit]'), sig: $('[data-sig]'), sumSig: $('[data-sum-sig]'),
      photos: $('[data-photos]'), photoList: $('[data-photo-list]'), photoPicker: $('[data-photo-picker]'), photoCount: $('[data-photo-count]'), photoHint: $('[data-photo-hint]'),
      videoLine: $('[data-video-line]'), videoText: $('[data-video-text]')
    };
    if (r.tierCards) r.tierCards.innerHTML = tierCardsHTML('videoTier', 'none');
    let tierEditOpen = false;
    let sigDraft = null; // 바꾸기 칸에 적고 아직 저장하지 않은 시그니처(다시 그려도 지우지 않는다, QA v5 E9)
    const tiles = new Map();
    let chapterTouched = false;
    let confirmDelete = false;
    let listOpen = null; // null이면 파일 수로 정한다(많으면 접는다)
    let pollTimer = null;
    const open = {}; // key → 정보 칸 펼침
    const cards = new Map();
    const store = (() => { try { return global && global.localStorage; } catch (error) { return null; } })();
    let theme = (store && ['light', 'dark'].indexOf(store.getItem('fd-theme')) >= 0) ? store.getItem('fd-theme') : 'system';
    function setTheme(t) {
      theme = t;
      if (store) { try { if (t === 'system') store.removeItem('fd-theme'); else store.setItem('fd-theme', t); } catch (error) { /* 저장 못 해도 이번 화면에는 적용 */ } }
      const html = doc.documentElement;
      if (html) { if (t === 'system') html.removeAttribute('data-fd-theme'); else html.setAttribute('data-fd-theme', t); }
      renderSide();
    }
    function renderSide() {
      if (r.side) r.side.innerHTML = sideHTML(S.projects, theme);
      if (r.headTheme) {
        const i = Math.max(0, THEMES.findIndex((t) => t[0] === theme));
        const cur = THEMES[i];
        const next = THEMES[(i + 1) % THEMES.length];
        r.headTheme.innerHTML = icon(cur[1]);
        r.headTheme.dataset.theme = next[0];
        r.headTheme.setAttribute('aria-label', '화면 테마: 지금 ' + cur[2] + '. 누르면 ' + next[2]);
      }
    }

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
          const kf = d.knownFacts || {};
          const factsEl = r.summary.querySelector('[data-sum-facts]');
          if (factsEl) factsEl.textContent = [kf.age, kf.gender, kf.job].filter(Boolean).join(' · ') + (kf.background ? ' — ' + kf.background : '');
          const set = intake.settings();
          const modeEl = r.summary.querySelector('[data-sum-mode]');
          if (modeEl) { modeEl.textContent = labelOf(MODES, set.modelMode); modeEl.parentElement.hidden = !set.modelMode; }
          const autoEl = r.summary.querySelector('[data-sum-auto]');
          if (autoEl) { autoEl.textContent = set.autoReview === false ? '단계마다 사람이 확인해요' : '사람 확인 없이 대화해 보기까지 가요'; autoEl.parentElement.hidden = set.autoReview == null; }
          if (r.sumVideo) {
            r.sumVideo.textContent = tierName(set.videoTier);
            const edit = r.summary.querySelector('[data-act="tier-edit"]');
            if (edit) { edit.hidden = !!S.finalized; edit.disabled = S.busy === 'tier'; edit.setAttribute('aria-expanded', String(tierEditOpen && !S.finalized)); edit.textContent = tierEditOpen ? '닫기' : '바꾸기'; }
          }
          if (r.sumSig) {
            const sig = set.signaturePose;
            r.sumSig.textContent = sig ? sig.title + ' — ' + sig.motion : '아직 정하지 않았어요';
            r.sumSig.parentElement.hidden = set.videoTier === 'none';
          }
          const notes = r.summary.querySelector('[data-sum-notes]');
          const memo = [text(basis.scope) && text(basis.scope) !== DEFAULT_SCOPE ? text(basis.scope) : '', text(basis.notes)].filter(Boolean).join(' · ');
          notes.textContent = memo;
          notes.parentElement.hidden = !memo;
        }
      }
      if (r.publicNote) r.publicNote.hidden = !(hasDraft && d.subject && d.subject.kind === 'PUBLIC_FIGURE');
      if (r.tierEdit) {
        const show = hasDraft && tierEditOpen && !S.finalized;
        r.tierEdit.hidden = !show;
        const html = show ? '<div class="vt-grid" role="radiogroup" aria-label="영상 등급 바꾸기">' + tierCardsHTML('videoTierEdit', intake.settings().videoTier, { disabled: S.busy === 'tier' }) + '</div><p class="src-fhint">영상 단계는 비용이 들어요. 등급은 고르면 바로 저장해요.</p>' + (intake.settings().videoTier === 'none' ? '' : sigEditHTML(sigDraft || intake.settings().signaturePose, S.busy === 'tier')) : '';
        if (r.tierEdit.dataset.html !== html) { r.tierEdit.innerHTML = html; r.tierEdit.dataset.html = html; }
      }
      renderTitle();
    }
    // 이미 있는 초안·캐릭터면 제목과 위치 표시를 그 이름으로 바꾼다. 새로 만들 때만 소개 문장과 만들던 초안 목록을 보인다.
    function nameNow() {
      const c = S.character || {};
      const d = S.draft;
      return text(c.displayName).trim() || text(d && d.subject && d.subject.displayName).trim();
    }
    function renderTitle() {
      const name = S.cid ? nameNow() : '';
      if (r.title) r.title.textContent = name || '원문으로 새 캐릭터';
      if (r.crumb) r.crumb.textContent = name || '원문으로 새 캐릭터';
      if (r.intro) r.intro.hidden = !!S.cid;
      if (!r.resume) return;
      const list = !S.cid && !S.loading && Array.isArray(S.drafts) ? S.drafts : [];
      const html = list.length
        ? '<p><b>만들던 초안 ' + list.length + '개</b>가 있어요. 이어서 하거나 아래에서 새로 시작해요.</p><ul>' + list.map((x) => {
          const n = Array.isArray(x.files) ? x.files.length : Number(x.files) || 0;
          const meta = [shortDate(x.createdAt), n ? '원문 ' + n + '개' : '원문 없음'].filter(Boolean).join(' · ');
          const nm = text(x.displayName).trim() || displayName('', x.characterId);
          return '<li><span class="nm">' + E(nm) + '</span><span class="meta">' + E(meta) + '</span><a class="btn" href="#c/' + E(encodeURIComponent(text(x.characterId))) + '" aria-label="' + E(nm + ' 초안 이어서 하기') + '">이어서</a></li>';
        }).join('') + '</ul>'
        : '';
      if (r.resume.dataset.html !== html) { r.resume.innerHTML = html; r.resume.dataset.html = html; }
      r.resume.hidden = !html;
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
      // 서버가 이름을 맞춘 화자가 있으면 그 한 사람, 없으면 고를 후보 이름마다 단추를 둔다.
      const sp = q('[data-speaker-row]');
      const chips = item.speaker
        ? [[item.speaker, "원문에서 찾은 '" + item.speaker + "'" + ro(item.speaker), '대상 화자를 원문에서 찾은 ' + item.speaker + ro(item.speaker) + ' 바꾸기: ' + item.filename]]
        : (item.choices || []).map((n) => [n, n, '대상 화자를 ' + n + ro(n) + ' 정하기: ' + item.filename]);
      const sh = chips.map((c) => '<button type="button" class="btn src-chip" data-act="use-speaker" data-name="' + E(c[0]) + '" aria-label="' + E(c[2]) + '">' + E(c[1]) + '</button>').join('');
      if (sp.dataset.html !== sh) { sp.innerHTML = sh; sp.dataset.html = sh; }
      sp.hidden = !sh;
      q('[data-retry-row]').hidden = !item.retry;
      const x = q('[data-act="remove"]');
      x.disabled = !item.removable;
      // 만들기를 시작한 뒤에는 지울 수 없으니 버튼을 아예 숨긴다.
      x.hidden = !!S.finalized;
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

    // 파일이 많으면 요약 한 줄과 펼치기 버튼만 두고, 확인할 점이 있거나 올리는 중인 파일만 보인다.
    function quiet(item) { return item.tone === 'ok' && !item.problems.length && !Object.keys(item.fieldErrors).length && open[item.key] !== true && item.saving !== 'saving' && item.saving !== 'error'; }
    function renderFold(items) {
      if (!r.fileSum) return false;
      const sum = fileSummary(items);
      const fold = sum.total > FILE_FOLD || (!!S.finalized && sum.total > 1);
      const collapsed = fold && (listOpen === null ? true : !listOpen);
      r.fileSum.hidden = !fold;
      if (fold) {
        const parts = sum.kinds.concat(sum.registers).map((x) => E(x[0]) + ' ' + x[1] + '개').join(' · ');
        const hidden = items.filter(quiet).length;
        const html = '<p><b>원문 ' + sum.total + '개</b>' + (parts ? '<span>' + parts + '</span>' : '') +
          '<span>' + (sum.attention ? '확인할 파일 ' + sum.attention + '개' : '모두 준비됐어요') + '</span></p>' +
          '<button type="button" class="btn ghost" data-act="fold" aria-expanded="' + !collapsed + '" aria-controls="src-file-list">' + icon('down') + '<span>' + (collapsed ? '목록 펼치기' + (hidden ? ' · ' + hidden + '개' : '') : '목록 접기') + '</span></button>';
        if (r.fileSum.dataset.html !== html) { r.fileSum.innerHTML = html; r.fileSum.dataset.html = html; }
      }
      return collapsed;
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
      const collapsed = renderFold(items);
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
        el.hidden = collapsed && quiet(item);
      });
      if (r.list) {
        r.list.id = 'src-file-list';
        const want = items.map((i) => cards.get(i.key));
        const now = Array.from(r.list.children);
        if (want.length !== now.length || want.some((el, i) => el !== now[i])) want.forEach((el) => r.list.appendChild(el));
      }
      if (r.pathRow) {
        // 폴더에서 가져오기는 이 컴퓨터에서만 쓰는 기능이라 '고급' 안에 접어 둔다.
        if (r.adv) r.adv.hidden = !(d && d.allowPathImport && !S.finalized);
        if (r.pathBtn) { r.pathBtn.disabled = S.busy === 'import'; r.pathBtn.textContent = S.busy === 'import' ? '가져오는 중…' : '가져오기'; }
      }
      renderPhotos();
    }
    // 영상용 사진: 영상 등급을 골랐거나 이미 올린 사진이 있으면 보인다. 시작한 뒤에도 대화가 되면 영상 만들기용 사진을 더 올릴 수 있다.
    function photoOpen() {
      const d = S.draft;
      if (!d) return { show: false, add: false };
      const c = S.character || {};
      const tier = intake.settings().videoTier;
      const has = intake.photoItems().length > 0;
      const ready = c.chatReady === true || !!(S.chat && S.chat.ready);
      // 사진은 처음 만들 때만 올린다(D-0160). 시작한 뒤에는 올린 사진만 보여 주고 더 받지 않는다(QA v5 E3).
      const show = tier !== 'none' || has;
      return { show, add: show && !S.finalized && c.videoStatus !== 'making', tier, ready };
    }
    function syncTile(el, it) {
      const q = (s) => el.querySelector(s);
      el.dataset.tone = it.tone;
      const box = q('.src-photo-img');
      const want = it.thumb ? '<img alt="" src="' + E(it.thumb) + '">' : icon('photo');
      if (box.dataset.html !== want) { box.innerHTML = want; box.dataset.html = want; }
      q('.nm').textContent = it.filename;
      q('[data-status-text]').textContent = it.problems.length ? it.problems[0] : it.status;
      const bar = q('[data-bar]');
      bar.hidden = it.progress == null;
      if (it.progress != null) bar.firstChild.style.width = Math.round(it.progress * 100) + '%';
      const x = q('[data-act="remove"]');
      x.hidden = !it.removable && !!S.finalized;
      x.disabled = !it.removable;
      x.setAttribute('aria-label', (it.source === 'upload' && it.phase === 'rejected' ? '목록에서 빼기: ' : '지우기: ') + it.filename);
      q('[data-act="retry"]').hidden = !it.retry;
    }
    function renderPhotos() {
      if (!r.photos) return;
      const po = photoOpen();
      r.photos.hidden = !po.show;
      const list = po.show ? intake.photoItems() : [];
      const ready = list.filter((i) => i.tone === 'ok').length;
      if (r.photoCount) r.photoCount.textContent = list.length ? ready + '장 준비' : '';
      if (r.photoHint) r.photoHint.textContent = S.finalized ? '만들 때 올린 사진이에요. 진행 화면에서 영상을 만들 때 이 사진을 써요.' : '얼굴이 잘 보이는 사진 1장 이상 · jpg, png, webp · 한 장에 15MB까지';
      const add = r.photos.querySelector('[data-act="pick-photo"]');
      if (add) { add.hidden = !po.add; add.disabled = !po.add; }
      if (!r.photoList) return;
      const keep = new Set(list.map((i) => i.key));
      tiles.forEach((el, key) => { if (!keep.has(key)) { el.remove(); tiles.delete(key); } });
      list.forEach((it) => {
        let el = tiles.get(it.key);
        if (!el) {
          const holder = doc.createElement('div');
          holder.innerHTML = '<figure class="src-photo" data-key="' + E(it.key) + '"><span class="src-photo-img" aria-hidden="true"></span>' +
            '<span class="src-bar" data-bar hidden><span></span></span>' +
            '<figcaption><span class="nm"></span><span class="st" data-status-text></span></figcaption>' +
            '<button type="button" class="btn ghost src-photo-x" data-act="remove" aria-label="">' + icon('x') + '</button>' +
            '<button type="button" class="btn src-photo-retry" data-act="retry" hidden>' + icon('retry') + '다시 올리기</button></figure>';
          el = holder.firstChild;
          tiles.set(it.key, el);
        }
        syncTile(el, it);
      });
      const want = list.map((i) => tiles.get(i.key));
      const now = Array.from(r.photoList.children);
      if (want.length !== now.length || want.some((el, i) => el !== now[i])) want.forEach((el) => r.photoList.appendChild(el));
    }

    function renderStart() {
      const d = S.draft;
      const st = intake.startState();
      const set = intake.settings();
      const auto = set.autoReview !== false;
      const tier = set.videoTier;
      const vName = tierName(tier);
      setStep(r.steps.info, d ? 'done' : 'active');
      setStep(r.steps.start, !d ? 'todo' : S.finalized ? 'done' : st.ready ? 'active' : 'wait');
      if (r.startLead) r.startLead.hidden = !!S.finalized;
      if (r.startLead) r.startLead.textContent = (auto
        ? '원문에서 그 사람이 한 말을 골라 정리하고, 공인이면 사실 목록도 만들어요. 사람 확인 없이 대화해 보기까지 이어서 만들어요.'
        : '원문에서 그 사람이 한 말을 골라 정리하고, 공인이면 사실 목록도 만들어요. 다 되면 진행 화면에서 출처 확인을 기다려요.') +
        (tier !== 'none' ? ' 대화가 되면 이어서 ' + vName + ' 영상을 만들어요.' : '');
      if (r.startNote) {
        r.startNote.textContent = (auto ? '보통 15~20분 걸려요' : '단계마다 진행 화면에서 확인해요') + (tier !== 'none' ? ' · 영상은 대화가 된 뒤에 만들고 비용이 들어요' : ' · 이미지·영상·학습은 하지 않아요');
        r.startNote.hidden = !!S.finalized;
      }
      if (r.startBtn) {
        r.startBtn.disabled = !st.ready || !!S.busy;
        r.startBtn.hidden = !!S.finalized;
        r.startBtn.textContent = S.busy === 'finalize' ? '시작하는 중…' : '만들기 시작';
      }
      if (r.reasons) {
        const html = d && !S.finalized && st.reasons.length ? '<p>시작하기 전에 봐 주세요</p><ul>' + st.reasons.map((x) => '<li>' + E(x) + '</li>').join('') + '</ul>' : '';
        if (r.reasons.dataset.html !== html) { r.reasons.innerHTML = html; r.reasons.dataset.html = html; }
        r.reasons.hidden = !html;
      }
      if (r.done) {
        r.done.hidden = !S.finalized;
        if (r.doneLink && S.cid) r.doneLink.href = 'factory.html#c/' + encodeURIComponent(S.cid);
        const c = S.character || {};
        const p = c.progress || {};
        const view = doneView(c, S.chat, { auto, tier });
        const ready = view.ready;
        if (r.doneTitle) r.doneTitle.textContent = view.title;
        if (r.doneText) { r.doneText.textContent = view.body; r.doneText.hidden = !view.body; }
        r.done.dataset.tone = view.tone;
        // 영상 줄은 대화가 된 뒤에만 보인다(대화가 먼저, 영상은 그다음).
        if (r.videoLine) {
          r.videoLine.hidden = !(S.finalized && view.video.show);
          r.videoLine.dataset.tone = view.video.tone;
          if (r.videoText) r.videoText.textContent = view.video.text;
          const spin = r.videoLine.querySelector('.src-spin');
          if (spin) spin.hidden = !view.video.making;
        }
        if (r.prog) {
          // 진행 막대는 만드는 동안만 보인다. 대화 가능이면 다 된 것이라 숨긴다. 단계 수는 목표까지 필요한 단계로 센다(약속 3 goal).
          const g = c.goal || (p.total ? { done: p.done, total: p.total } : null);
          r.prog.hidden = !(S.finalized && g && !ready);
          if (g && !ready) {
            const pct = Math.round(g.done / g.total * 100);
            const bar = r.prog.querySelector('[data-prog-bar]');
            if (bar) { bar.firstChild.style.width = pct + '%'; bar.setAttribute('aria-label', g.total + '단계 중 ' + g.done + '단계 완료'); }
            if (r.progText) r.progText.textContent = (g.label ? text(g.label) + ' · ' : '') + g.done + '/' + g.total + '단계';
          }
        }
        if (r.chatLink) {
          r.chatLink.hidden = !ready;
          if (r.chatLink.textContent !== view.chatLabel) r.chatLink.textContent = view.chatLabel;
          if (S.cid) r.chatLink.href = 'chat.html#c/' + encodeURIComponent(S.cid);
          if (r.doneLink) r.doneLink.classList.toggle('pri', !ready);
        }
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
      if (doc.title !== undefined) doc.title = (S.cid && nameNow() ? nameNow() : '원문으로 새 캐릭터') + ' · Foundry';
    }
    // 시작한 뒤에는 대화 준비가 될 때까지 진행을 가끔 다시 읽는다. 화면이 숨으면 쉬고, 대화 API가 없으면 멈춘다.
    // 영상 등급을 골랐으면 대화가 된 뒤에도 영상이 다 되거나 실패할 때까지 읽는다(영상 상태를 주지 않는 서버면 거기서 멈춘다).
    function schedule() {
      const want = wantsPoll(S);
      if (want && !pollTimer && global && global.setInterval) {
        pollTimer = global.setInterval(() => { if (!(doc.hidden)) intake.progress(); }, 6000);
      } else if (!want && pollTimer) { global.clearInterval(pollTimer); pollTimer = null; }
    }
    function render() { renderInfo(); renderFiles(); renderStart(); renderSide(); schedule(); }
    intake.subscribe(render);

    function onSubmit(e) {
      if (e.target !== r.form) {
        if (e.target === r.pathRow) { e.preventDefault(); intake.importPath(r.pathInput.value).then(() => { if (!S.error) r.pathInput.value = ''; }); }
        return;
      }
      e.preventDefault();
      const f = r.form;
      const kind = (f.querySelector('[name="subjectKind"]:checked') || {}).value;
      const mode = (f.querySelector('[name="modelMode"]:checked') || {}).value;
      const tier = (f.querySelector('[name="videoTier"]:checked') || {}).value;
      const auto = f.querySelector('[name="autoReview"]');
      const input = { displayName: f.querySelector('[name="displayName"]').value, subjectKind: kind, notes: f.querySelector('[name="notes"]').value, age: f.querySelector('[name="age"]').value, gender: f.querySelector('[name="gender"]').value, job: f.querySelector('[name="job"]').value, background: f.querySelector('[name="background"]').value, chapterTemplate: f.querySelector('[name="chapterTemplate"]').value || undefined, modelMode: mode, autoReview: auto ? auto.checked : true, videoTier: tier, sigTitle: f.querySelector('[name="sigTitle"]').value, sigMotion: f.querySelector('[name="sigMotion"]').value, sigWhen: f.querySelector('[name="sigWhen"]').value };
      const errors = intake.validateDraft(input);
      ['displayName', 'subjectKind', 'age', 'gender', 'job', 'background', 'sigTitle', 'sigMotion'].forEach((n) => fieldError(n, errors[n]));
      const first = Object.keys(errors)[0];
      if (first) { if (S.error) { S.error = null; render(); } const ctl = f.querySelector('[name="' + first + '"]'); if (ctl) ctl.focus(); return; }
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
      else if (act === 'pick-photo' && r.photoPicker) r.photoPicker.click();
      else if (act === 'tier-edit') { tierEditOpen = !tierEditOpen; render(); if (tierEditOpen && r.tierEdit) { const cur = r.tierEdit.querySelector('input:checked'); if (cur) cur.focus(); } }
      else if (act === 'sig-save' && r.tierEdit) {
        const q = (n) => (r.tierEdit.querySelector('[name="' + n + '"]') || {}).value;
        const pose = { title: q('sigeTitle'), motion: q('sigeMotion'), useWhen: q('sigeWhen') };
        if (!sigOf(pose)) { S.error = '시그니처 포즈의 이름과 동작을 적어 주세요.'; render(); return; }
        intake.setSignature(pose).then((ok) => { if (ok) { sigDraft = null; tierEditOpen = false; render(); const b = r.summary && r.summary.querySelector('[data-act="tier-edit"]'); if (b) b.focus(); } });
      }
      else if (act === 'theme' || act === 'theme-next') setTheme(el.dataset.theme || 'system');
      else if (act === 'fold') { listOpen = el.getAttribute('aria-expanded') !== 'true'; render(); }
      else if (act === 'toggle' && key) { open[key] = el.getAttribute('aria-expanded') !== 'true'; render(); }
      else if (act === 'remove' && key) {
        const item = intake.items().concat(intake.photoItems()).find((i) => i.key === key);
        if (item && item.source === 'upload' && item.phase === 'rejected') intake.dismiss(key); else intake.removeFile(key);
        const next = card.nextElementSibling || card.previousElementSibling;
        const photo = r.photos && r.photos.contains(card);
        setTimeout(() => { const t = next && next.querySelector('[data-act="remove"]'); if (t && doc.contains(t)) t.focus(); else { const p = photo ? r.photos.querySelector('[data-act="pick-photo"]') : r.drop && r.drop.querySelector('[data-act="pick"]'); if (p) p.focus(); } }, 0);
      }
      else if (act === 'retry' && key) intake.retry(key);
      else if (act === 'use-speaker' && key) intake.pickSpeaker(key, el.dataset.name);
      else if (act === 'start') intake.finalize().then((done) => { if (done) intake.projects(); if (done && r.done) { const h = r.done.querySelector('h3'); if (h) h.focus(); } });
      else if (act === 'ask-delete') { confirmDelete = true; render(); const no = r.delRow.querySelector('[data-act="cancel-delete"]'); if (no) no.focus(); }
      else if (act === 'cancel-delete') { confirmDelete = false; render(); const ask = r.delRow.querySelector('[data-act="ask-delete"]'); if (ask) ask.focus(); }
      else if (act === 'delete') intake.deleteDraft().then((ok) => { if (ok) { confirmDelete = false; chapterTemplateReset(); render(); const n = r.form && r.form.querySelector('[name="displayName"]'); if (n) n.focus(); } });
      else if (act === 'reload') { const cid = route(); if (cid) intake.load(cid); }
      else if (act === 'restart') { intake.reset(); clearHash(); render(); intake.drafts(); }
    }
    // 바꾸기 칸의 시그니처 포즈. 등급과 달리 적고 나서 저장 버튼으로 보낸다.
    function sigEditHTML(sig, busy) {
      const s = sig || { title: '', motion: '', useWhen: '' };
      return '<div class="src-sig" data-sig-edit><p class="src-sig-h"><b>시그니처 포즈</b><span class="src-fhint">모든 영상 등급에 한 편씩 들어가요.</span></p>' +
        '<div class="src-fld"><label for="src-sige-title">이름</label><input id="src-sige-title" name="sigeTitle" maxlength="30" autocomplete="off" placeholder="예: 찰칵 세리머니" value="' + E(s.title) + '"></div>' +
        '<div class="src-fld"><label for="src-sige-motion">어떤 동작인가요</label><textarea id="src-sige-motion" name="sigeMotion" rows="2" maxlength="400" placeholder="예: 두 손으로 카메라 모양을 만들어 눈앞에 대고 찰칵 누르는 시늉을 해요.">' + E(s.motion) + '</textarea></div>' +
        '<div class="src-fld"><label for="src-sige-when">언제 나오면 좋을까요 <span class="opt">선택</span></label><input id="src-sige-when" name="sigeWhen" maxlength="200" autocomplete="off" placeholder="예: 골이나 축하 얘기를 할 때" value="' + E(s.useWhen) + '"></div>' +
        '<div class="acts"><button type="button" class="btn" data-act="sig-save"' + (busy ? ' disabled' : '') + '>시그니처 포즈 저장</button></div></div>';
    }
    function chapterTemplateReset() {
      chapterTouched = false;
      tierEditOpen = false;
      sigDraft = null;
      if (r.form) r.form.reset();
      if (r.tierHint) r.tierHint.hidden = true;
      if (r.sig) r.sig.hidden = true;
    }
    function onChange(e) {
      const t = e.target;
      if (t === r.picker) { intake.addFiles(t.files); t.value = ''; return; }
      if (t === r.photoPicker) { intake.addFiles(t.files, { photoOnly: true }); t.value = ''; return; }
      // 등급을 고르면 저장하되 칸은 열어 둔다. 시그니처를 같은 칸에서 이어서 적는다(QA v5 E9·A-11).
      if (t.name === 'videoTierEdit') { const v = t.value; intake.setTier(v).then((ok) => { if (ok) { render(); const c0 = r.tierEdit && r.tierEdit.querySelector('[name="videoTierEdit"][value="' + v + '"]'); if (c0) c0.focus(); } }); return; }
      if (r.form && r.form.contains(t)) {
        if (t.name === 'videoTier') { if (r.tierHint) r.tierHint.hidden = t.value === 'none'; if (r.sig) r.sig.hidden = t.value === 'none'; return; }
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
      if (r.tierEdit && r.tierEdit.contains(t) && /^sige/.test(t.name || '')) {
        const q = (n) => (r.tierEdit.querySelector('[name="' + n + '"]') || {}).value || '';
        sigDraft = { title: q('sigeTitle'), motion: q('sigeMotion'), useWhen: q('sigeWhen') };
        return;
      }
      if (r.form && r.form.contains(t) && t.name && t.getAttribute('aria-invalid')) fieldError(t.name, '');
    }
    function hasFiles(e) { const dt = e.dataTransfer; return !!(dt && Array.from(dt.types || []).indexOf('Files') >= 0); }
    function onDragOver(e) {
      if (!hasFiles(e)) return;
      e.preventDefault();
      const onPhotos = !!(r.photos && !r.photos.hidden && r.photos.contains(e.target) && photoOpen().add);
      const inside = onPhotos || (r.drop && r.drop.contains(e.target) && S.draft && !S.finalized);
      if (e.dataTransfer) e.dataTransfer.dropEffect = inside ? 'copy' : 'none';
      if (r.drop) r.drop.classList.toggle('is-over', !!inside && !onPhotos);
      if (r.photos) r.photos.classList.toggle('is-over', onPhotos);
    }
    function onDragLeave(e) {
      if (r.drop && (!e.relatedTarget || !r.drop.contains(e.relatedTarget))) r.drop.classList.remove('is-over');
      if (r.photos && (!e.relatedTarget || !r.photos.contains(e.relatedTarget))) r.photos.classList.remove('is-over');
    }
    function onDrop(e) {
      if (!hasFiles(e)) return;
      e.preventDefault(); // 화면 밖에 떨어뜨려도 브라우저가 파일을 열며 화면을 떠나지 않게 한다.
      if (r.drop) r.drop.classList.remove('is-over');
      if (r.photos) r.photos.classList.remove('is-over');
      if (r.photos && !r.photos.hidden && r.photos.contains(e.target) && photoOpen().add) intake.addFiles(e.dataTransfer.files, { photoOnly: true });
      else if (r.drop && r.drop.contains(e.target)) intake.addFiles(e.dataTransfer.files);
    }
    function onHash() { const cid = route(); if (cid && cid !== S.cid) intake.load(cid); else if (!cid && S.cid) { intake.reset(); intake.drafts(); } }
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
    if (cid) intake.load(cid); else { render(); intake.drafts(); }
    intake.projects();
    return {
      intake,
      destroy() {
        if (pollTimer && global) { global.clearInterval(pollTimer); pollTimer = null; }
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

  const api = { sigOf, MAX_BYTES, EXTENSIONS, PHOTO_EXTENSIONS, PHOTO_MAX_BYTES, VIDEO_TIERS, KINDS, REGISTERS, SUBJECT_KINDS, CHAPTERS, MODES, DEFAULT_SCOPE, FILE_FOLD, defaultRegister, nextRegister, kindHint, guessKind, speakersOf, suggestedSpeaker, speakerChoices, ro, shortDate, suggestTextId, checkFile, isPhotoName, isPhotoRecord, tierOf, tierName, tierCardsHTML, videoText, doneView, wantsPoll, formatSize, textIdProblem, metaBody, fileSummary, sideHTML, putFile, errorText, createIntake, mount };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (global) global.SourceIntake = api;
})(typeof window !== 'undefined' ? window : null);

