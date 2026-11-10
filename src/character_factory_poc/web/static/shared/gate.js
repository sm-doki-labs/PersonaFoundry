// 관문 상세 화면. 서버의 관문 항목을 읽어 고르기·승인·수정 요청 화면을 만들고,
// 결정은 POST /api/characters/{id}/gates/{gate}/decision 한 곳으로 보낸다(cfp gate import와 같은 답).

// 화면 없이 확인할 수 있는 판단(이름·지난 요청·관문 목록·반려 안내). node 시험이 그대로 불러 쓴다.
(function (root) {
  'use strict';
  function arr(value) { return Array.isArray(value) ? value : []; }
  // 이름: 기획에서 정한 이름 → 원문에서 정한 표시 이름 → '이름 미정 · slug (11/7)'. 내부 ID는 이름으로 쓰지 않는다.
  function characterName(summary, id) {
    var s = summary || {};
    var cid = String(id || '');
    var pick = [s.displayName, s.persona && s.persona.name, s.name].filter(function (n) {
      var t = String(n || '').trim();
      return t && t !== cid && t !== '이름 미정';
    })[0];
    if (pick) return String(pick).trim();
    var m = /^cf-(\d{4})(\d{2})(\d{2})-(.+)$/.exec(cid);
    return m ? '이름 미정 · ' + m[4] + ' (' + Number(m[2]) + '/' + Number(m[3]) + ')' : cid;
  }
  // 다시 만든 버전이면 바로 앞 버전에 남긴 수정 요청 글. 앞 결정이 수정 요청이 아니면 null.
  function previousAsk(view) {
    var v = view || {};
    var recs = arr(v.records).map(function (r) { return r && r.record; }).filter(function (r) {
      return r && r.rev && r.rev !== v.rev;
    });
    recs.sort(function (x, y) { return String(x.decidedAt || '').localeCompare(String(y.decidedAt || '')); });
    var last = recs[recs.length - 1];
    if (!last || last.decision !== 'REQUEST_CHANGES') return null;
    var notes = arr(last.requestedChanges).map(function (c) {
      var note = String((c && c.note) || '').trim();
      var ch = /^ch(\d+)$/.exec(String((c && c.field) || ''));
      return note ? (ch ? ch[1] + '장: ' : '') + note : '';
    }).filter(Boolean);
    var text = notes.length ? notes.join(' / ') : String(last.reasons || '').trim();
    return text || null;
  }
  // 출시 전 점검에서 결정 기록을 확인할 관문: 이 캐릭터 그래프의 관문(G9와 건너뛴 관문 제외).
  var ORIGINAL_GATES = ['G1', 'G3', 'G4a', 'G4b', 'G4', 'G5', 'G5b', 'G6', 'G7a', 'G7', 'G8'];
  function packageGates(gates) {
    var rows = arr(gates).filter(function (g) { return g && g.id; });
    if (!rows.length) return ORIGINAL_GATES.slice();
    return rows.filter(function (g) { return g.id !== 'G9' && g.status !== 'SKIPPED'; }).map(function (g) { return g.id; });
  }
  // 반려해도 그대로 남는 것: 이미 승인한 다른 관문. 없으면(첫 관문) 빈 목록이다.
  function keptOnReject(gates, current) {
    return arr(gates).filter(function (g) { return g && g.id !== current && g.status === 'APPROVED'; })
      .map(function (g) { return g.title || g.id; });
  }
  var helpers = { characterName: characterName, previousAsk: previousAsk, packageGates: packageGates, keptOnReject: keptOnReject };
  if (typeof module !== 'undefined' && module.exports) module.exports = helpers;
  if (root) root.CF_GATE = helpers;
})(typeof window !== 'undefined' ? window : null);

(function () {
  'use strict';
  if (typeof window === 'undefined') return;
  var api = window.CF_API;
  var H = window.CF_GATE;
  if (!api) return;
  var params = new URLSearchParams(location.search);
  if (params.get('embedded') === '1') document.body.classList.add('gate-embedded');
  // 진행 화면 시트 안에서는 Escape로 시트를 닫을 수 있게 부모에 알린다.
  if (params.get('embedded') === '1' && window.parent && window.parent !== window) {
    document.addEventListener('keydown', function (event) {
      if (event.key !== 'Escape' || event.defaultPrevented) return;
      try {
        window.parent.postMessage({ type: 'foundry:close' }, window.location.origin);
      } catch (postError) {
        /* 부모가 다른 출처면 무시한다 */
      }
    });
  }
  var state = {
    characterId: params.get('character') || '',
    gate: params.get('gate') || '',
    view: null,
    character: null,
    items: {},
    kind: '',
    pairs: {},
    face: '',
    faceLikes: [],
    faceCompare: false,
    faceFilter: '',
    planPick: '',
    planOnlyDiff: null,
    bgPicks: {},
    bgCustom: {},
    bgOpen: {},
    bgCurrent: '',
    bgRestored: false,
    posePicks: {},
    poseCustom: {},
    poseTweaks: {},
    poseTab: '',
    poseTweakOpen: false,
    poseRestored: false,
    frameVerdict: {},
    frameNote: {},
    frameZoom: '',
    frameRestored: false,
    introPick: '',
    introRestored: false,
    actionPick: {},
    actionNote: {},
    actionOpen: '',
    actionRestored: false,
    actionCarried: 0,
    actionUndo: null,
    pendingSend: null,
    sampleVerdict: {},
    sampleNote: {},
    sampleTab: '',
    sampleOpen: '',
    sampleRestored: false,
    sampleSeen: {},
    pkgManual: {},
    pkgOpen: {},
    pkgRestored: false,
    busy: false,
    source: null,
    review: null,
    reviewIndex: {}
  };

  // 사전 검토가 붙는 관문(D-0049). G7a·G8은 사람 판정·블라인드 비교라 화면을 바꾸지 않는다.
  var REVIEW_GATES = ['G1', 'G3', 'G4a', 'G4b', 'G4', 'G5', 'G5b', 'G6', 'G7', 'G9'];

  var STATUS_KO = {
    PENDING: '대기',
    RUNNING: '진행 중',
    CHECK_FAILED: '검사 실패',
    AWAITING_HUMAN: '검토 대기',
    APPROVED: '승인',
    REJECTED: '반려',
    SKIPPED: '건너뜀'
  };

  var DECISION_KO = {
    SELECT: '고름',
    APPROVE: '승인',
    REQUEST_CHANGES: '수정 요청',
    REJECT: '반려'
  };
  var VERDICT_KO = { ADOPT: '쓰기', FIX: '고쳐 쓰기', REJECT: '버리기' };
  var STAGE_KO = { STRANGER: '처음 만난 사이', ACQUAINTANCE: '친해진 사이', FLIRTING: '썸을 타는 사이', DATING: '연애 중' };
  var GENDER_KO = { female: '여성', male: '남성' };
  function stageLabel(value) {
    return String(value || '').replace(/[A-Z]+/g, function (code) { return STAGE_KO[code] || code; });
  }
  var PICK_KO = { LONG: '긴 프롬프트가 나음', SHORT: '짧은 프롬프트가 나음', TIE: '비슷함', BOTH_BAD: '둘 다 아쉬움', NONE: '판정 없음' };

  // 숫자·낱말 뒤 '로/으로'. 받침이 없거나 ㄹ이면 '로'다(1·2·4·5·7·8·9 → 로, 3·6·0 → 으로).
  function ro(word) {
    var s = String(word);
    var last = s.charAt(s.length - 1);
    if (/[0-9]/.test(last)) return s + ('360'.indexOf(last) >= 0 ? '으로' : '로');
    var code = last.charCodeAt(0) - 0xac00;
    if (code < 0 || code > 11171) return s + '로';
    var jong = code % 28;
    return s + (jong === 0 || jong === 8 ? '로' : '으로');
  }

  // 판(revision) 코드는 'bg1' 같은 개발용 이름이다. 화면에는 '버전 1'로 보인다(D-0129).
  function revLabel(rev) {
    var m = /^[a-z]+(\d+)$/i.exec(String(rev || ''));
    return m ? '버전 ' + m[1] : String(rev || '-');
  }
  // 모티브(받은 사진·원문에서 만든 캐릭터)는 얼굴 고르기 대신 기준 사진 선택을 거친다.
  function isMotif() {
    return (state.view || {}).origin === 'SOURCE';
  }
  var GATE_KO = {
    G0: '출처 확인', G1s: '기준 사진', G1: '얼굴 고르기', G3: '기획안 고르기', G4a: '챕터 배경', G4b: '장면·자세', G4: '완성 이미지',
    G5: '소개 영상', G5b: '동작 영상', G6: '프롬프트', G7a: '데이터 샘플', G7: '학습 데이터', G8: '평가', G9: '패키지'
  };
  // 에이전트가 쓴 글 속 관문 코드(G0 등)는 화면 이름으로 바꿔 보여 준다.
  function plainCodes(value) {
    return String(value == null ? '' : value).replace(/\bG\d+[a-z]?\b/g, function (code) {
      return GATE_KO[code] ? '\'' + GATE_KO[code] + '\' 검토' : code;
    });
  }

  // ---------------------------------------------------------------- 도우미
  // 비어 있어 막힌 입력 칸을 보이게 열고 그 자리로 옮긴다(D-0129).
  function focusField(node) {
    if (!node) return;
    var box = node.closest && node.closest('details');
    if (box) box.open = true;
    node.scrollIntoView({ block: 'center' });
    node.focus({ preventScroll: true });
  }
  function q(sel, root) {
    return (root || document).querySelector(sel);
  }
  function qa(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }
  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function list(value) {
    return Array.isArray(value) ? value : value == null || value === '' ? [] : [value];
  }
  function joinList(value, sep) {
    return list(value)
      .map(function (v) {
        return typeof v === 'string' ? v : JSON.stringify(v);
      })
      .join(sep || ' · ');
  }
  function setStatus(message, kind) {
    var out = q('[data-status]');
    var text = String(message || '');
    // 한글이 없는 오류(브라우저·네트워크 영어 문장)는 쉬운 말로 바꾸고 원문은 툴팁에 둔다.
    var foreign = kind === 'bad' && text && !/[가-힣]/.test(text);
    out.textContent = foreign ? '서버와 연결하지 못했어요. 잠시 뒤 다시 해 주세요.' : text;
    if (foreign) out.title = text; else out.removeAttribute('title');
    out.className = 'side-status' + (kind ? ' is-' + kind : '');
  }
  // 검토한 사람 이름은 한 번 적으면 이 브라우저에 기억해 둔다. 비우면 기록에는 'user'로 남는다.
  function rememberedReviewer() {
    try {
      return window.localStorage.getItem('fd-reviewer') || '';
    } catch (error) {
      return '';
    }
  }
  function details() {
    var minutes = Number(q('[data-minutes]').value || 0);
    var reviewer = q('[data-reviewer]').value.trim();
    try {
      if (reviewer) window.localStorage.setItem('fd-reviewer', reviewer);
    } catch (error) {
      /* 기억하지 못해도 결정은 보낸다 */
    }
    return {
      reviewer: reviewer || 'user',
      minutes: isFinite(minutes) ? minutes : 0,
      reasons: q('[data-reasons]').value || ''
    };
  }
  function fileUrl(file) {
    return file && file.url ? file.url : '';
  }
  function image(file, cls) {
    if (!file || !file.url) return '';
    var broken = file.exists === false ? ' (파일 없음)' : '';
    return (
      '<img class="' + (cls || '') + '" src="' + esc(file.url) + '" alt="' +
      esc(file.name + broken) + '" loading="lazy">'
    );
  }
  function video(file) {
    if (!file || !file.url) return '<p class="empty">영상 파일이 아직 없어요.</p>';
    return (
      '<video src="' + esc(file.url) + '" controls loop muted playsinline preload="metadata"></video>'
    );
  }
  function qaBadge(summary) {
    if (!summary) return '';
    if (summary.passed) {
      return (
        '<span class="badge-chip is-good">자동 검사 통과 · ' + esc(summary.attempts) +
        '회째</span>'
      );
    }
    return '<span class="badge-chip is-bad">자동 검사 미통과 · 사람 확인</span>';
  }
  function qaNote(summary) {
    if (!summary) return '';
    var reasons = list(summary.reasons);
    if (summary.passed && !reasons.length) return '';
    var link = summary.reportUrl
      ? ' <a href="' + esc(summary.reportUrl) + '" target="_blank" rel="noopener">보고서</a>'
      : '';
    return (
      '<p class="qa-note' + (summary.passed ? '' : ' is-bad') + '">' +
      esc(reasons.join(' · ') || '자동 검사 항목을 확인했어요.') + link + '</p>'
    );
  }
  function facts(pairs) {
    var rows = pairs
      .filter(function (pair) {
        return pair[1] !== undefined && pair[1] !== null && pair[1] !== '';
      })
      .map(function (pair) {
        var value = Array.isArray(pair[1]) ? joinList(pair[1]) : pair[1];
        return '<dt>' + esc(pair[0]) + '</dt><dd>' + esc(value) + '</dd>';
      });
    return rows.length ? '<dl class="facts">' + rows.join('') + '</dl>' : '';
  }
  function chips(values, cls) {
    return list(values)
      .filter(function (v) {
        return v !== '' && v !== null && v !== undefined;
      })
      .map(function (v) {
        return '<span class="badge-chip ' + (cls || '') + '">' + esc(v) + '</span>';
      })
      .join('');
  }
  function checkedValue(name) {
    var node = q('input[name="' + name + '"]:checked');
    return node ? node.value : '';
  }
  function reviewItem(candidateId) {
    return state.reviewIndex[candidateId] || null;
  }
  function reviewLine(candidateId) {
    var item = reviewItem(candidateId);
    if (!item) return '';
    var out = '';
    if (item.verdict === 'RECOMMEND') {
      out += '<span class="badge-chip is-good">' +
        (item.rank === 1 ? '검토 1순위' : '검토 추천') + '</span>';
    } else if (item.verdict === 'CONCERN') {
      out += '<span class="badge-chip is-bad">걸리는 점</span>';
    }
    var reasons = list(item.reasons).slice(0, 2).join(' · ');
    var defects = list(item.defects)
      .map(function (defect) {
        return (defect.field ? defect.field + ': ' : '') + defect.note;
      })
      .slice(0, 2)
      .join(' · ');
    var text = [reasons, defects].filter(Boolean).join(' · ');
    if (text) out += '<span class="review-note">' + esc(text) + '</span>';
    return out ? '<span class="review-line">' + out + '</span>' : '';
  }
  function reviewEnabled() {
    return REVIEW_GATES.indexOf(state.gate) >= 0;
  }

  // ---------------------------------------------------------------- 결정 기록(읽기 전용)
  // 이미 승인·반려한 관문은 기록으로만 보여 준다. 결정 버튼·입력칸·단축키 안내 대신
  // 누가 · 언제 · 무엇을 골랐는지 요약을 맨 위에 둔다.
  var AUTO_REVIEWER = '자동 진행';
  function isRecord() {
    var v = state.view;
    return Boolean(v && v.record && (v.status === 'APPROVED' || v.status === 'REJECTED'));
  }
  function pad2(n) {
    return (n < 10 ? '0' : '') + n;
  }
  // 기록 시각은 UTC로 저장된다. 보는 사람의 시간대로 '11월 10일 04:55'처럼 보여 준다.
  function whenKo(value) {
    var d = new Date(value);
    if (!value || isNaN(d.getTime())) return String(value || '').slice(0, 16).replace('T', ' ');
    var year = d.getFullYear() !== new Date().getFullYear() ? d.getFullYear() + '년 ' : '';
    return year + (d.getMonth() + 1) + '월 ' + d.getDate() + '일 ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes());
  }
  var DONE_KO = { SELECT: '골랐어요', APPROVE: '승인했어요', REQUEST_CHANGES: '수정을 요청했어요', REJECT: '반려했어요' };
  function recordTitle(rec) {
    if (rec.reviewer === AUTO_REVIEWER) {
      return (rec.decision === 'SELECT' ? '자동 진행으로 첫 후보를 골랐어요'
        : rec.decision === 'REJECT' ? '자동 진행으로 반려됐어요' : '자동 진행으로 승인됐어요') + ' · 사람 확인 없음';
    }
    return DONE_KO[rec.decision] || '결정했어요';
  }
  // 무엇을 골랐는지 한 줄. 따로 정하지 않은 화면은 고른 후보 수만 적는다.
  function recordPicked(rec) {
    if (state.kind === 'planVariants') {
      var plan = planById(list(rec.selections)[0]);
      return plan ? (planCandidates().length > 1 ? planLabel(plan) + ' · ' : '') + (plan.name || '') : '';
    }
    if (state.kind === 'sourcePack') {
      var out = list((state.items.publicFacts || {}).items).filter(function (f) { return f && f.excluded; }).length;
      return out ? '빼기로 한 공개 사실 ' + out + '개' : '';
    }
    if (state.kind === 'prompts') return state.items.shortAdopted ? '짧은 프롬프트' : '';
    var n = list(rec.selections).length;
    return n ? '후보 ' + n + '개' : '';
  }
  // 자동 진행이 사람 확인 없이 넘긴 경고. 나중에 볼 수 있게 기록 요약에 남긴다.
  function recordLater(rec) {
    if (rec.reviewer !== AUTO_REVIEWER || state.kind !== 'sourcePack') return [];
    return sourceChecks(state.items)
      .filter(function (c) { return c.tone === 'warn' || c.tone === 'bad'; })
      .map(function (c) { return c.title + ': ' + c.detail; });
  }
  function recordCard(rec) {
    var auto = rec.reviewer === AUTO_REVIEWER;
    var rows = [];
    if (!auto) rows.push(['누가', rec.reviewer && rec.reviewer !== 'user' ? rec.reviewer : '이름을 남기지 않았어요']);
    if (rec.decidedAt) rows.push(['언제', whenKo(rec.decidedAt)]);
    var picked = recordPicked(rec);
    if (picked) rows.push(['고른 것', picked]);
    if (!auto && rec.reasons) rows.push(['메모', rec.reasons]);
    var later = recordLater(rec);
    return '<div class="gate-banner gate-record-card is-' + (later.length ? 'warn' : 'ok') + '" data-record-card><b>' + esc(recordTitle(rec)) + '</b>' +
      (rows.length ? '<dl class="record-facts">' + rows.map(function (r) { return '<dt>' + esc(r[0]) + '</dt><dd>' + esc(r[1]) + '</dd>'; }).join('') + '</dl>' : '') +
      (later.length ? '<p class="record-later-title">나중에 볼 것 ' + later.length + '건</p><ul class="record-later">' +
        later.map(function (t) { return '<li>' + esc(t) + '</li>'; }).join('') + '</ul>' : '') + '</div>';
  }
  // 서버가 준 자료 문제 문장에 파일 이름이나 영어가 섞이면 쉬운 말로 보여 주고, 원래 문장은 툴팁에 둔다.
  function problemBanner(problem) {
    var s = String(problem || '');
    var dev = /[A-Za-z]{3,}|\//.test(s);
    return '<div class="gate-banner is-bad"' + (dev ? ' title="' + esc(s) + '"' : '') + '><b>자료 확인</b>' +
      esc(dev ? '이 단계의 자료 일부를 찾지 못했어요.' : s) + '</div>';
  }

  // ---------------------------------------------------------------- 화면 정의
  var KINDS = {
    faces: {
      hint: '얼굴 하나를 고르면 그 얼굴이 이후 모든 장면과 영상의 얼굴 기준이 돼요.',
      actions: [
        ['SELECT', '이 얼굴로 확정', 'primary'],
        ['REQUEST_CHANGES', '수정 요청', 'ghost'],
        ['REJECT', '반려(처음부터)', 'danger']
      ],
      render: renderFaces,
      build: buildFaces
    },
    planVariants: {
      hint: '같은 상황에서 무엇을 먼저 고르는지 비교해요. 고른 안의 내용은 확정 전에 고칠 수 있어요.',
      // 후보가 하나면 비교할 것이 없다. 그 안을 읽고 확정하거나 고칠 점을 적는다.
      hintFor: function (items) {
        return list(items.candidates).length === 1 ? '기획안을 읽어 보고, 괜찮으면 확정해요. 고칠 칸은 확정 전에 바로 고칠 수 있어요.' : null;
      },
      actionsFor: function (items) {
        if (list(items.candidates).length !== 1) return null;
        return KINDS.planVariants.actions.filter(function (a) { return a[0] !== 'APPROVE'; });
      },
      actions: [
        ['SELECT', '이 안으로 확정', 'primary'],
        ['APPROVE', '보지 않고 첫 후보로 확정', 'ghost'],
        ['REQUEST_CHANGES', '수정 요청', 'ghost'],
        ['REJECT', '반려(처음부터)', 'danger']
      ],
      render: renderPlans,
      build: buildPlans
    },
    backgrounds: {
      hint: '챕터마다 배경 하나를 고르거나, 원하는 배경을 한두 줄로 직접 적어 주세요.',
      actions: [
        ['SELECT', '고른 배경으로 확정', 'primary'],
        ['APPROVE', '보지 않고 첫 후보로 확정', 'ghost'],
        ['REQUEST_CHANGES', '수정 요청', 'ghost'],
        ['REJECT', '반려(처음부터)', 'danger']
      ],
      render: renderBackgrounds,
      build: buildBackgrounds
    },
    poses: {
      hint: '장면 내용을 확인하고 챕터마다 자세·의상을 하나 골라 주세요. 고른 후보의 세부 항목은 바로 고칠 수 있어요.',
      actions: [
        ['SELECT', '고른 자세로 확정', 'primary'],
        ['APPROVE', '보지 않고 첫 후보로 확정', 'ghost'],
        ['REQUEST_CHANGES', '수정 요청', 'ghost'],
        ['REJECT', '반려(처음부터)', 'danger']
      ],
      render: renderPoses,
      build: buildPoses
    },
    frames: {
      hint: '챕터마다 괜찮은지 골라 주세요. 고칠 챕터만 다시 만들어요.',
      actions: [
        ['APPROVE', '모두 승인', 'primary'],
        ['REQUEST_CHANGES', '수정 요청', 'ghost'],
        ['REJECT', '반려(처음부터)', 'danger']
      ],
      render: renderFrames,
      build: buildFrames
    },
    intro: {
      hint: '첫 프레임과 같은 사람이 자연스럽게 움직이는 영상을 하나 골라 주세요.',
      actions: [
        ['SELECT', '이 영상으로 확정', 'primary'],
        ['REQUEST_CHANGES', '수정 요청', 'ghost'],
        ['REJECT', '반려(처음부터)', 'danger']
      ],
      render: renderIntro,
      build: buildIntro
    },
    actions: {
      hint: '동작마다 영상 하나를 고르거나 빼 주세요. 챕터마다 하나 이상은 남겨야 해요.',
      actions: [
        ['SELECT', '고른 영상으로 확정', 'primary'],
        ['APPROVE', '보지 않고 첫 후보로 확정', 'ghost'],
        ['REQUEST_CHANGES', '수정 요청', 'ghost'],
        ['REJECT', '반려(처음부터)', 'danger']
      ],
      render: renderActions,
      build: buildActions
    },
    prompts: {
      hint: '표본 응답을 먼저 보고, 필요하면 프롬프트 원문을 열어 확인해요. 괜찮으면 승인하고, 아니면 고칠 점을 적어 주세요.',
      // 표본이 없을 때 '표본 응답을 먼저 보고'라고 하지 않는다. 대신 무엇을 보면 되는지 말한다.
      hintFor: function (items) {
        if (list(items.samples).length || list(items.probes).length) {
          return '대화 표본을 먼저 읽고, 필요하면 프롬프트 원문을 열어 확인해요. 괜찮으면 승인하고, 아니면 고칠 점을 적어 주세요.';
        }
        return chatReady()
          ? '아직 대화 표본이 없어요. 대화해 보기에서 직접 말을 걸어 보고, 괜찮으면 승인하고 아니면 고칠 점을 적어 주세요.'
          : '아직 대화 표본이 없어요. 프롬프트 원문을 읽어 보고, 괜찮으면 승인하고 아니면 고칠 점을 적어 주세요.';
      },
      actions: [
        ['APPROVE', '프롬프트 승인', 'primary'],
        ['REQUEST_CHANGES', '수정 요청', 'ghost'],
        ['REJECT', '반려(처음부터)', 'danger']
      ],
      render: renderPrompts,
      build: buildPrompts
    },
    samples: {
      hint: '묶음별 작성 지침과 샘플 대화를 보고 대화마다 쓸지 고칠지 정해요. 묶음마다 따로 보내요.',
      actions: [
        ['SELECT', '이 판정 보내기', 'primary'],
        ['REQUEST_CHANGES', '수정 요청 · 작성 지침', 'ghost']
      ],
      render: renderSamples,
      build: buildSamples
    },
    dataset: {
      hint: '검사 요약과 무작위 표본 20개를 본 뒤 승인해요.',
      actions: [
        ['APPROVE', '데이터셋 승인', 'primary'],
        ['REQUEST_CHANGES', '수정 요청', 'ghost']
      ],
      render: renderDataset,
      build: buildDataset
    },
    eval: {
      hint: '어느 응답이 어떤 조건인지 숨겨요. 쌍마다 나은 쪽이나 비슷함을 고르고, 다 고르면 채택할 조건을 정해요.',
      actions: [['SELECT', '블라인드 판정 보내기', 'primary']],
      render: renderEval,
      build: buildEval
    },
    promptOnly: {
      hint: '학습 결과가 아직 없어요. 긴 프롬프트로 패키지까지 갈지, 학습을 기다릴지 정해 주세요.',
      // 모티브(PROMPT_ONLY·BIND_EXISTING)은 학습을 기다리지 않는다. 버튼 문구는 서버의 items.adoptLabel을 따른다.
      hintFor: function (items) {
        if (!isTwinDecision(items)) return null;
        return (items.decision || {}).mode === 'BIND_EXISTING'
          ? '같은 장면에서 실제 답과 생성 답을 비교한 결과를 보고, 연결한 모델로 이 캐릭터를 진행할지 정해요.'
          : '같은 장면에서 실제 답과 생성 답을 비교한 결과를 보고, 긴 프롬프트로 이 캐릭터를 진행할지 정해요.';
      },
      actionsFor: function (items) {
        var label = items.adoptLabel || '긴 프롬프트로 진행';
        return isTwinDecision(items)
          ? [['SELECT', label, 'primary'], ['REJECT', '반려(다시 만들기)', 'danger']]
          : [['SELECT', label, 'primary'], ['REJECT', '학습을 기다릴게요', 'ghost']];
      },
      actions: [
        ['SELECT', '긴 프롬프트로 진행', 'primary'],
        ['REJECT', '학습을 기다릴게요', 'ghost']
      ],
      render: renderPromptOnly,
      build: buildPromptOnly
    },
    sourcePack: {
      hint: '출처가 맞게 정리됐는지 확인해요. 승인하면 이 묶음으로 얼굴·기획·말투를 만들어요.',
      actions: [
        ['APPROVE', '출처 승인', 'primary'],
        ['REQUEST_CHANGES', '수정 요청', 'ghost'],
        ['REJECT', '반려(처음부터)', 'danger']
      ],
      render: renderSourcePack,
      build: buildSourcePack
    },
    sourcePhotos: {
      hint: '본인과 닮고 얼굴이 잘 보이는 사진을 하나 골라 주세요. 고른 사진이 이후 모든 장면과 영상의 얼굴 기준이 돼요.',
      actions: [
        ['SELECT', '이 사진으로 확정', 'primary'],
        ['REQUEST_CHANGES', '수정 요청', 'ghost'],
        ['REJECT', '반려(처음부터)', 'danger']
      ],
      render: renderPhotos,
      build: buildPhotos
    },
    package: {
      hint: '패키지 요약을 확인하고 승인해요. 승인한 뒤 우리 앱으로 내보내는 일은 다음 단계에서 해요.',
      actions: [
        ['APPROVE', '패키지 승인', 'primary'],
        ['REJECT', '반려(처음부터)', 'danger']
      ],
      render: renderPackage,
      build: buildPackage
    }
  };

  // ---------------------------------------------------------------- G1
  // 얼굴 고르기 갤러리(D-0105): 외모군 3~4개 × 2~3장을 한 판에 깔고 한 장을 고른다.
  // 비슷한 얼굴은 ♡로 3장까지 추려 크게 나란히 비교한다. 숫자 키 1~0으로 고르고 S로 추린다.
  var POSE_KO = { 1: '정면 · 다문 미소', 2: '3/4 측면 · 차분한 표정', 3: '고개 기울임 · 밝은 표정' };
  function faceList() {
    var out = [];
    list(state.items.clusters).forEach(function (cluster, ci) {
      list(cluster.faces).forEach(function (face) {
        out.push({
          id: face.previewId,
          face: face,
          cluster: cluster,
          letter: String.fromCharCode(65 + ci),
          n: out.length + 1
        });
      });
    });
    return out;
  }
  function faceById(id) {
    return faceList().filter(function (f) { return f.id === id; })[0] || null;
  }
  function faceLocked() {
    return state.view && (state.view.status === 'APPROVED' || state.view.status === 'REJECTED');
  }
  function clusterSummary(cluster) {
    return list(cluster.tags).slice(0, 2).map(function (tag) { return tag.text; }).join(' · ');
  }
  function renderFaces(items) {
    var faces = faceList();
    if (!state.face && state.view && state.view.record) {
      // 기록은 고른 얼굴을 referencePreviews 또는 selections(외모군, 얼굴 순)에 남긴다.
      var rec = state.view.record;
      var ids = faces.map(function (f) { return f.id; });
      var chosen = list(rec.referencePreviews).concat(list(rec.selections)).filter(function (id) {
        return ids.indexOf(id) >= 0;
      })[0];
      if (chosen) state.face = chosen;
    }
    var clusters = list(items.clusters);
    var cautions = list(items.cautions);
    return (
      '<section class="gate-section face-gallery"><h2>얼굴 후보 ' + faces.length + '장</h2>' +
      '<p class="section-sub">' + esc(items.helper || '') + ' 숫자 키 1~0으로 고르고, 비슷한 얼굴은 ♡로 3장까지 추려 크게 나란히 비교할 수 있어요.</p>' +
      '<div class="face-chips" role="group" aria-label="외모군으로 거르기" data-face-chips></div>' +
      '<div data-face-compare hidden></div>' +
      '<div class="face-grid" data-face-grid></div>' +
      '<div class="face-tray" data-face-tray></div>' +
      '</section>' +
      '<section class="gate-section"><details class="gate-more"><summary>외모군 근거 · ' + clusters.length + '개</summary>' +
      clusters.map(function (cluster, ci) {
        return '<div class="face-cluster"><h3>' + String.fromCharCode(65 + ci) + ' · ' + esc(clusterSummary(cluster) || cluster.clusterId) +
          (cluster.recommended ? ' <span class="badge-chip is-good">추천</span>' : '') + '</h3>' +
          '<p class="section-sub">' + esc(cluster.rationale || '') + '</p>' +
          '<dl class="facts">' + list(cluster.tags).map(function (tag) {
            return '<dt>' + esc(tag.label) + '</dt><dd>' + esc(tag.text) + '</dd>';
          }).join('') + '</dl>' +
          '<details class="card-tech"><summary>구성원 ' + esc(cluster.memberCount) + '명 (검토용)</summary>' +
          list(cluster.members).map(function (m) { return esc(m.name || m.personId); }).join(', ') + '</details></div>';
      }).join('') +
      (cautions.length ? '<div class="face-cluster"><h3>읽을 때 주의</h3><ul>' + cautions.map(function (c) { return '<li>' + esc(c) + '</li>'; }).join('') + '</ul></div>' : '') +
      '</details></section>' +
      '<section class="gate-section"><h2>다시 만들 때 고칠 점</h2>' +
      '<p class="section-sub">마음에 드는 얼굴이 없을 때만 적어 주세요. 이 메모로 얼굴만 다시 만들어요.</p>' +
      '<textarea data-face-note placeholder="예: 눈매를 조금 더 부드럽게, 머리 길이는 그대로"></textarea>' +
      '</section>'
    );
  }
  function faceThumb(f, cls) {
    return f.face.file && f.face.file.url
      ? '<img class="' + (cls || '') + '" src="' + esc(f.face.file.url) + '" alt="' + esc('얼굴 ' + f.n + ', 외모군 ' + f.letter) + '" loading="lazy">'
      : '<span class="face-missing">파일 없음</span>';
  }
  function paintFaces() {
    if (state.kind !== 'faces') return;
    var grid = q('[data-face-grid]');
    if (!grid) return;
    var faces = faceList();
    var locked = faceLocked();
    var letters = [];
    faces.forEach(function (f) { if (letters.indexOf(f.letter) < 0) letters.push(f.letter); });
    q('[data-face-chips]').innerHTML = [''].concat(letters).map(function (letter) {
      var count = faces.filter(function (f) { return !letter || f.letter === letter; }).length;
      var cluster = letter ? faces.filter(function (f) { return f.letter === letter; })[0].cluster : null;
      return '<button type="button" class="face-chip" data-face-filter="' + letter + '" aria-pressed="' + (state.faceFilter === letter) + '">' +
        (letter ? letter + ' · ' + esc(clusterSummary(cluster) || cluster.clusterId) : '전체') + ' <span>' + count + '</span></button>';
    }).join('');
    var shown = faces.filter(function (f) { return !state.faceFilter || f.letter === state.faceFilter; });
    grid.innerHTML = shown.map(function (f, i) {
      var liked = state.faceLikes.indexOf(f.id) >= 0;
      return '<div class="face-tile' + (state.face === f.id ? ' is-picked' : '') + '">' +
        '<button type="button" class="face-pick" data-face="' + esc(f.id) + '" aria-pressed="' + (state.face === f.id) + '"' + (locked ? ' disabled' : '') + '>' +
        faceThumb(f) +
        '<span class="face-cap"><b>' + f.n + '</b><span class="face-letter">' + f.letter + '</span>' +
        (f.face.recommended ? '<span class="badge-chip is-good">추천</span>' : '') +
        (i < 10 ? '<kbd>' + ((i + 1) % 10) + '</kbd>' : '') + '</span>' + reviewLine(f.id) + '</button>' +
        (locked ? '' : '<button type="button" class="face-like" data-like="' + esc(f.id) + '" aria-pressed="' + liked + '" aria-label="' + esc('얼굴 ' + f.n + (liked ? ' 추린 목록에서 빼기' : ' 추리기')) + '">' + (liked ? '♥' : '♡') + '</button>') +
        '</div>';
    }).join('');
    var tray = q('[data-face-tray]');
    var likes = state.faceLikes.map(faceById).filter(Boolean);
    tray.hidden = locked;
    tray.innerHTML = '<span class="face-tray-count">추린 얼굴 <b>' + likes.length + '</b> / 3</span>' +
      '<span class="face-tray-minis">' + [0, 1, 2].map(function (i) {
        return likes[i] ? faceThumb(likes[i], 'mini') : '<span class="face-slot"></span>';
      }).join('') + '</span>' +
      '<span class="face-tray-hint">비슷한 얼굴은 ♡로 추려 크게 비교해요. 단축키 S</span>' +
      (likes.length ? '<button type="button" class="btn btn--ghost" data-face-clear>비우기</button>' : '') +
      (state.faceCompare && likes.length >= 2
        ? '<button type="button" class="btn btn--primary" data-face-compare-close>전체 보기</button>'
        : '<button type="button" class="btn btn--primary" data-face-compare-open' + (likes.length >= 2 ? '' : ' disabled') + '>나란히 비교</button>');
    var compare = q('[data-face-compare]');
    var open = state.faceCompare && likes.length >= 2 && !locked;
    compare.hidden = !open;
    grid.hidden = open;
    q('[data-face-chips]').hidden = open;
    if (open) {
      compare.innerHTML = '<div class="face-compare-head"><b>추린 ' + likes.length + '장 나란히 비교</b><button type="button" class="btn btn--ghost" data-face-compare-close>← 전체 보기</button></div>' +
        '<div class="face-compare" style="grid-template-columns:repeat(' + likes.length + ',minmax(0,1fr))">' +
        likes.map(function (f) {
          return '<button type="button" class="face-compare-card' + (state.face === f.id ? ' is-picked' : '') + '" data-face="' + esc(f.id) + '" aria-pressed="' + (state.face === f.id) + '">' +
            faceThumb(f, 'big') + '<span class="face-cap"><b>얼굴 ' + f.n + '</b><span class="face-letter">' + f.letter + '</span>' +
            (f.face.recommended ? '<span class="badge-chip is-good">추천</span>' : '') + '</span>' +
            '<span class="card-sub">' + esc(clusterSummary(f.cluster)) + ' · ' + esc(POSE_KO[f.face.variation] || '') + '</span></button>';
        }).join('') + '</div>';
    } else {
      compare.innerHTML = '';
    }
    paintFaceSide();
  }
  function paintFaceSide() {
    var host = q('[data-side-extra]');
    if (!host) return;
    if (state.kind !== 'faces') { host.innerHTML = ''; return; }
    var f = state.face ? faceById(state.face) : null;
    if (!f) {
      host.innerHTML = '<p class="face-side-empty">얼굴을 고르면 여기에 크게 보여요.</p>';
    } else {
      host.innerHTML = '<div class="face-side">' + faceThumb(f, 'big') +
        '<p class="face-side-title"><b>얼굴 ' + f.n + '</b><span class="face-letter">' + f.letter + '</span>' +
        (f.face.recommended ? '<span class="badge-chip is-good">추천</span>' : '') + '</p>' +
        '<dl class="facts">' + list(f.cluster.tags).slice(0, 4).map(function (tag) {
          return '<dt>' + esc(tag.label) + '</dt><dd>' + esc(tag.text) + '</dd>';
        }).join('') + (POSE_KO[f.face.variation] ? '<dt>각도·표정</dt><dd>' + esc(POSE_KO[f.face.variation]) + '</dd>' : '') + '</dl>' +
        '<p class="section-sub">' + esc(f.cluster.rationale || '') + '</p>' +
        (f.face.prompt ? '<details class="card-tech"><summary>생성 지시</summary>' + esc(f.face.prompt) + '</details>' : '') + '</div>';
    }
    var primary = q('[data-decide="SELECT"]');
    if (primary && !faceLocked()) primary.textContent = f ? ro('얼굴 ' + f.n) + ' 확정' : '이 얼굴로 확정';
  }
  function pickFace(id) {
    if (faceLocked() || !faceById(id)) return;
    state.face = id;
    paintFaces();
  }
  function toggleLike(id) {
    if (faceLocked() || !faceById(id)) return;
    var i = state.faceLikes.indexOf(id);
    if (i >= 0) state.faceLikes.splice(i, 1);
    else if (state.faceLikes.length < 3) state.faceLikes.push(id);
    else { setStatus('추린 얼굴은 3장까지예요. 하나를 빼고 추려 주세요.', 'bad'); return; }
    if (state.faceLikes.length < 2) state.faceCompare = false;
    setStatus('');
    paintFaces();
  }
  function onFaceKey(event) {
    if (state.kind !== 'faces' || event.altKey || event.ctrlKey || event.metaKey) return;
    var tag = event.target && event.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    var key = String(event.key || '').toLowerCase();
    var shown = faceList().filter(function (f) { return !state.faceFilter || f.letter === state.faceFilter; });
    if (/^[0-9]$/.test(key)) {
      var idx = key === '0' ? 9 : Number(key) - 1;
      if (shown[idx]) { event.preventDefault(); pickFace(shown[idx].id); }
    } else if (key === 's' && state.face) {
      event.preventDefault();
      toggleLike(state.face);
    } else if (key === 'escape' && state.faceCompare) {
      event.preventDefault();
      state.faceCompare = false;
      paintFaces();
    }
  }

  function buildFaces(decision) {
    var answer = { decision: decision };
    if (decision === 'SELECT') {
      var f = state.face ? faceById(state.face) : null;
      if (!f) throw Error('얼굴 하나를 골라 주세요.');
      answer.selections = [f.cluster.clusterId];
      answer.referencePreviews = [f.id];
    }
    if (decision === 'REQUEST_CHANGES') {
      var note = q('[data-face-note]').value.trim();
      if (!note) { focusField(q('[data-face-note]')); throw Error('아래 칸에 다시 만들 때 고칠 점을 적어 주세요.'); }
      answer.note = note;
    }
    return Object.assign(answer, details());
  }

  // ---------------------------------------------------------------- G3
  // 기획안 고르기: 같은 항목을 가로로 맞춘 비교표(D-0106). 다른 줄을 표시하고 같은 줄은 접을 수 있다.
  var FIELD_KO = {
    name: '이름', age: '나이', gender: '성별', job: '직업', tagline: '한 줄 소개', background: '배경',
    coreTraits: '핵심 성격', contrastTrait: '대비되는 면', choices: '상황별 행동',
    lifeAndTastes: '생활·취향', wantsAndFears: '바람·두려움', misreadings: '오해받기 쉬운 점',
    voiceSummary: '말투', voiceExamples: '말투 예시', boundaries: '경계', profileCard: '프로필 카드', notes: '메모'
  };
  function planCandidates() {
    return list(state.items.candidates);
  }
  function planById(id) {
    return planCandidates().filter(function (c) { return c.variantId === id; })[0] || null;
  }
  function planLabel(plan) {
    var i = planCandidates().indexOf(plan);
    return plan && plan.variantId && plan.variantId.charAt(0) === 'u' ? '직접 쓴 안' : '안 ' + (i + 1);
  }
  function planLocked() {
    return state.view && (state.view.status === 'APPROVED' || state.view.status === 'REJECTED');
  }
  function cellText(value) {
    if (value == null || value === '') return '';
    if (Array.isArray(value)) return value.map(function (v) { return typeof v === 'string' ? v : JSON.stringify(v); });
    return String(value);
  }
  function cellHTML(value) {
    var v = cellText(value);
    if (Array.isArray(v)) {
      return v.length ? '<ul>' + v.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : '<span class="plan-none">비어 있음</span>';
    }
    return v ? esc(v) : '<span class="plan-none">비어 있음</span>';
  }
  function cellEmpty(value) {
    var v = cellText(value);
    return Array.isArray(v) ? !v.length : !v;
  }
  // 말투 칸에서 원문 통계 문장을 뺀 글(서버 planDisplay). 통계는 '기술 정보'에 접어 둔다.
  function planVoice(p) {
    var d = (state.items.planDisplay || {})[p.variantId];
    return d && typeof d.voiceSummary === 'string' ? d.voiceSummary : p.voiceSummary;
  }
  function planStats(plans) {
    var disp = state.items.planDisplay || {};
    var parts = plans.filter(function (p) { return disp[p.variantId] && list(disp[p.variantId].voiceStats).length; }).map(function (p) {
      return (plans.length > 1 ? '<p class="section-sub">' + esc(planLabel(p)) + '</p>' : '') +
        '<ul class="src-list">' + list(disp[p.variantId].voiceStats).map(function (s) { return '<li>' + esc(s) + '</li>'; }).join('') + '</ul>';
    });
    return parts.length ? '<details class="gate-more plan-tech"><summary>기술 정보 · 원문 말투 통계</summary>' + parts.join('') + '</details>' : '';
  }
  // 비교표 줄: [묶음, 이름, 후보 → 값]. 같은 상황은 상황 문장을 줄 이름으로 맞춘다.
  function planRows(plans) {
    var rows = [];
    var add = function (group, label, get) { rows.push({ group: group, label: label, get: get }); };
    add('기본', '이름 · 나이', function (p) { return [p.name, p.age ? p.age + '세' : '', { female: '여성', male: '남성' }[p.gender] || p.gender].filter(Boolean).join(' · '); });
    add('기본', '직업', function (p) { return p.job; });
    add('기본', '한 줄 소개', function (p) { return p.tagline; });
    add('기본', '배경', function (p) { return p.background; });
    add('성격', '핵심 성격', function (p) { return p.coreTraits; });
    add('성격', '대비되는 면', function (p) { return p.contrastTrait; });
    add('성격', '말투', planVoice);
    add('성격', '말투 예시', function (p) { return p.voiceExamples; });
    var situations = [];
    plans.forEach(function (p) {
      list(p.choices).forEach(function (c) { if (c && c.situation && situations.indexOf(c.situation) < 0) situations.push(c.situation); });
    });
    situations.forEach(function (sit) {
      add('같은 상황에서 고르는 행동', sit, function (p) {
        var c = list(p.choices).filter(function (x) { return x && x.situation === sit; })[0];
        return c ? c.firstMove : '';
      });
    });
    var evidence = state.items.choiceEvidence || {};
    var ruleSits = [];
    Object.keys(evidence).forEach(function (k) {
      list(evidence[k]).forEach(function (r) { if (r && r.situation && ruleSits.indexOf(r.situation) < 0) ruleSits.push(r.situation); });
    });
    ruleSits.forEach(function (sit) {
      add('선택 근거', sit, function (p) {
        var r = list(evidence[p.variantId]).filter(function (x) { return x && x.situation === sit; })[0];
        return r ? ['먼저 지키는 것: ' + (r.priority || ''), '감수하는 것: ' + (r.acceptedCost || ''), '생각을 바꾸는 조건: ' + (r.switchWhen || '')] : '';
      });
    });
    add('생활', '생활·취향', function (p) { return p.lifeAndTastes; });
    add('생활', '바람·두려움', function (p) { return p.wantsAndFears; });
    add('생활', '오해받기 쉬운 점', function (p) { return p.misreadings; });
    add('생활', '경계', function (p) { return p.boundaries; });
    [['hobby', '취미'], ['likes', '좋아함'], ['dislikes', '싫어함'], ['idealDate', '이상형 데이트'], ['mbti', 'MBTI']].forEach(function (f) {
      add('프로필 카드', f[1], function (p) { return (p.profileCard || {})[f[0]]; });
    });
    add('프로필 카드', '태그', function (p) { return joinList((p.profileCard || {}).tags, ', '); });
    add('챕터 흐름', '챕터별 흐름', function (p) {
      return list(p.chapterArc).map(function (c) { return (c.title || c.chapterId) + ': ' + (c.arc || ''); });
    });
    rows.forEach(function (row) {
      var keys = plans.map(function (p) { return JSON.stringify(cellText(row.get(p))); });
      row.diff = keys.some(function (k) { return k !== keys[0]; });
      // 모든 안에서 빈 칸이면 줄을 보이지 않는다('취미 없음'처럼 읽히지 않게).
      row.empty = plans.every(function (p) { return cellEmpty(row.get(p)); });
    });
    return rows.filter(function (row) { return !row.empty; });
  }
  function renderPlans(items) {
    var plans = planCandidates();
    var record = isRecord();
    if (!state.planPick && state.view && state.view.record) {
      var chosen = list(state.view.record.selections).filter(function (id) { return planById(id); })[0];
      if (chosen) state.planPick = chosen;
    }
    // 후보가 하나면 고를 것이 없다. 그 안을 고른 상태로 연다.
    if (!state.planPick && plans.length === 1 && !planLocked()) state.planPick = plans[0].variantId;
    var rows = planRows(plans);
    var diffs = rows.filter(function (r) { return r.diff; }).length;
    if (state.planOnlyDiff == null) state.planOnlyDiff = diffs > 0 && diffs <= rows.length / 2;
    var single = plans.length === 1;
    var top = single
      ? '<section class="gate-section plan-compare is-single"><h2>기획안</h2>' +
        '<div class="plan-scroll"><table class="plan-table is-single" data-plan-table></table></div>' + planStats(plans) + '</section>'
      : '<section class="gate-section plan-compare"><h2>기획 후보 ' + plans.length + '안 나란히 보기</h2>' +
        '<p class="section-sub">' + esc(String(items.axisNote || '같은 상황에서 고르는 행동이 서로 달라요').replace(/[.。]?\s*$/, '.')) +
        (record ? ' 고른 안에 표시했어요.' : ' 같은 항목을 가로로 맞췄어요. 열 위의 버튼으로 한 안을 골라 주세요.') + '</p>' +
        '<div class="plan-bar"><span><b>' + diffs + '</b>개 항목이 서로 달라요 · 같은 항목 ' + (rows.length - diffs) + '개</span>' +
        '<label class="plan-toggle"><input type="checkbox" data-plan-only-diff' + (state.planOnlyDiff ? ' checked' : '') + '> 다른 항목만 보기</label></div>' +
        '<div class="plan-scroll"><table class="plan-table" data-plan-table></table></div>' + planStats(plans) + '</section>';
    if (record) return top;
    return (
      top +
      '<section class="gate-section"><details class="gate-more" data-plan-edit><summary>' + (single ? '기획안 고치기 (선택)' : '고른 안 고치기 (선택)') + '</summary>' +
      '<p class="section-sub">고른 안에서 바꿀 칸만 고쳐 주세요. 목록 칸은 한 줄에 하나씩 적어요. ' +
      '바꾼 칸만 결정에 담겨요.</p>' +
      (items.mode === 'own'
        ? '<p class="section-sub">사람이 직접 쓴 글을 정리한 안이에요. 후보를 고르거나 ' +
          '칸을 고쳐 확정해요.</p>'
        : '') +
      '<div class="field-list" data-plan-fields><p class="empty">후보를 고르면 고칠 칸이 열려요.</p>' +
      '</div>' + (items.requireExplicitSelection ?
        '<p class="section-sub">수정한 내용은 새 버전에서 다시 검토해요. 원래 요구를 바꿀 때만 아래에서 그 요구를 골라 주세요.</p>' +
        list(items.seedRequirements).map(function (r) {
          return '<label class="pick-line"><input type="checkbox" data-replace-requirement="' +
            esc(r.id) + '"> ' + esc(r.quote) + '</label>';
        }).join('') : '') + '</details></section>' +
      // 수정 요청은 고칠 점이 있어야 보낸다(G0·G1·G6와 같은 규칙, QA v5 B-F10).
      '<section class="gate-section"><h2>수정 요청 (선택)</h2>' +
      '<p class="section-sub">안을 다시 만들어 달라고 할 때만 적어 주세요.</p>' +
      '<textarea data-plan-note placeholder="예: 직업을 더 평범하게, 말투를 덜 딱딱하게"></textarea></section>'
    );
  }
  function paintPlans() {
    if (state.kind !== 'planVariants') return;
    var table = q('[data-plan-table]');
    if (!table) return;
    var plans = planCandidates();
    var rows = planRows(plans);
    var locked = planLocked();
    var single = plans.length === 1;
    var pickCls = function (p) { return state.planPick === p.variantId ? ' is-picked' : ''; };
    // 후보가 하나면 열 머리(고르기 버튼·번호)가 필요 없다. 항목과 값만 보여 준다.
    var head = single ? '' : '<thead><tr><th scope="col" class="plan-corner">항목</th>' + plans.map(function (p, i) {
      return '<th scope="col" class="plan-col' + pickCls(p) + '">' +
        '<span class="plan-col-label">' + esc(planLabel(p)) + (i < 9 && !locked ? ' <kbd>' + (i + 1) + '</kbd>' : '') + '</span>' +
        '<b>' + esc(p.name || '') + '</b><span class="plan-col-sub">' + esc(p.tagline || '') + '</span>' + reviewLine(p.variantId) +
        (locked ? (state.planPick === p.variantId ? '<span class="badge-chip is-good">고른 안</span>' : '')
          : '<button type="button" class="btn ' + (state.planPick === p.variantId ? 'btn--primary' : 'btn--ghost') + ' plan-pick" data-plan-pick="' + esc(p.variantId) + '" aria-pressed="' + (state.planPick === p.variantId) + '">' +
            (state.planPick === p.variantId ? '고른 안' : '이 안 고르기') + '</button>') +
        '</th>';
    }).join('') + '</tr></thead>';
    var body = '';
    var group = '';
    var hidden = 0;
    rows.forEach(function (row) {
      if (state.planOnlyDiff && !row.diff && !single) { hidden += 1; return; }
      if (row.group !== group) {
        group = row.group;
        body += '<tr class="plan-group"><th scope="rowgroup" colspan="' + (plans.length + 1) + '">' + esc(group) + '</th></tr>';
      }
      body += '<tr class="' + (row.diff ? 'is-diff' : 'is-same') + '"><th scope="row">' +
        (row.diff ? '<span class="plan-diff-dot" aria-hidden="true"></span>' : '') + esc(row.label) +
        (row.diff ? '<span class="sr-only"> (안마다 달라요)</span>' : '') + '</th>' +
        plans.map(function (p) { return '<td class="' + (single ? '' : pickCls(p).trim()) + '">' + cellHTML(row.get(p)) + '</td>'; }).join('') + '</tr>';
    });
    if (hidden) {
      body += '<tr class="plan-hidden-note"><td colspan="' + (plans.length + 1) + '">같은 항목 ' + hidden + '개를 접었어요. <button type="button" class="btn btn--ghost" data-plan-show-all>모두 보기</button></td></tr>';
    }
    table.innerHTML = '<colgroup><col class="plan-label-col">' + plans.map(function () { return '<col>'; }).join('') + '</colgroup>' + head + '<tbody>' + body + '</tbody>';
    // 후보가 많으면 열 하나가 150px보다 좁아지지 않게 가로로 넘긴다.
    table.style.minWidth = (112 + plans.length * 150) + 'px';
    var toggle = q('[data-plan-only-diff]');
    if (toggle) toggle.checked = Boolean(state.planOnlyDiff);
    renderPlanFields();
    paintPlanSide();
  }
  function paintPlanSide() {
    var host = q('[data-side-extra]');
    if (!host || state.kind !== 'planVariants') return;
    // 기록에서는 본문 맨 위 요약이 고른 안을 말한다. 옆 칸은 비운다.
    if (isRecord()) { host.innerHTML = ''; return; }
    var plan = state.planPick ? planById(state.planPick) : null;
    host.innerHTML = plan
      ? '<div class="plan-side"><p class="plan-side-title"><span class="face-letter">' + esc(planLabel(plan)) + '</span><b>' + esc(plan.name || '') + '</b></p>' +
        '<p class="section-sub">' + esc(plan.tagline || '') + '</p>' +
        '<dl class="facts"><dt>핵심</dt><dd>' + esc(joinList(plan.coreTraits, ' / ')) + '</dd><dt>말투</dt><dd>' + esc(planVoice(plan) || '') + '</dd></dl></div>'
      : '<p class="face-side-empty">안을 고르면 여기에 요약이 보여요.</p>';
    var primary = q('[data-decide="SELECT"]');
    if (primary && !planLocked()) primary.textContent = plan && planCandidates().length > 1 ? ro(planLabel(plan)) + ' 확정' : '이 안으로 확정';
    guardQuickApprove(plan ? 1 : 0);
  }
  function pickPlan(id) {
    if (planLocked() || !planById(id)) return;
    state.planPick = id;
    paintPlans();
  }
  function onPlanKey(event) {
    if (state.kind !== 'planVariants' || event.altKey || event.ctrlKey || event.metaKey) return;
    if (planLocked() || planCandidates().length < 2) return;
    var tag = event.target && event.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    var n = Number(event.key);
    var plans = planCandidates();
    if (n >= 1 && n <= plans.length) {
      event.preventDefault();
      pickPlan(plans[n - 1].variantId);
    }
  }

  function renderPlanFields() {
    var host = q('[data-plan-fields]');
    if (!host) return;
    var plan = state.planPick ? planById(state.planPick) : null;
    if (!plan || planLocked()) {
      host.innerHTML = '<p class="empty">' + (planLocked() ? '이미 결정한 관문이에요.' : '후보를 고르면 고칠 칸이 열려요.') + '</p>';
      host.removeAttribute('data-for');
      return;
    }
    // 같은 안을 다시 그릴 때는 고치던 내용을 지키려고 칸을 다시 만들지 않는다.
    if (host.getAttribute('data-for') === plan.variantId) return;
    host.setAttribute('data-for', plan.variantId);
    var fields = list(state.items.editableFields);
    // 글·숫자·글 목록은 쉬운 입력란으로 보이고, 그 밖의 구조는 '고급' 칸으로 접는다(D-0129).
    var simple = [];
    var advanced = [];
    fields.forEach(function (field) {
      var value = plan[field];
      var orig = esc(JSON.stringify(value === undefined ? null : value));
      var label = esc(FIELD_KO[field] || field);
      if (field === 'gender' && (value == null || typeof value === 'string')) {
        // 성별은 저장 값(female·male)을 그대로 보이지 않고 여성·남성 중에서 고른다(QA v5 C-11).
        var genders = Object.keys(GENDER_KO);
        if (value && genders.indexOf(value) < 0) genders.push(value);
        simple.push('<div class="field"><span>' + label + '</span><select data-edit="gender" data-edit-kind="text" data-orig="' + orig + '">' +
          (value ? '' : '<option value="" selected>정하지 않음</option>') +
          genders.map(function (g) { return '<option value="' + esc(g) + '"' + (g === value ? ' selected' : '') + '>' + esc(GENDER_KO[g] || g) + '</option>'; }).join('') +
          '</select></div>');
      } else if (value == null || typeof value === 'string') {
        var t = value == null ? '' : value;
        simple.push('<div class="field"><span>' + label + '</span>' + (t.length > 70
          ? '<textarea data-edit="' + esc(field) + '" data-edit-kind="text" data-orig="' + orig + '">' + esc(t) + '</textarea>'
          : '<input type="text" data-edit="' + esc(field) + '" data-edit-kind="text" data-orig="' + orig + '" value="' + esc(t) + '">') + '</div>');
      } else if (typeof value === 'number') {
        simple.push('<div class="field"><span>' + label + '</span><input type="number" data-edit="' + esc(field) + '" data-edit-kind="number" data-orig="' + orig + '" value="' + esc(value) + '"></div>');
      } else if (Array.isArray(value) && value.every(function (v) { return typeof v === 'string'; })) {
        simple.push('<div class="field"><span>' + label + '<small>한 줄에 하나</small></span><textarea data-edit="' + esc(field) + '" data-edit-kind="lines" data-orig="' + orig + '" rows="' + Math.max(2, value.length + 1) + '">' + esc(value.join('\n')) + '</textarea></div>');
      } else {
        advanced.push('<div class="field"><span>' + label + '</span><textarea data-edit="' + esc(field) + '" data-edit-kind="json" data-orig="' + orig + '">' + esc(JSON.stringify(value, null, 2)) + '</textarea></div>');
      }
    });
    host.innerHTML = simple.join('') + (advanced.length
      ? '<details class="gate-more"><summary>고급 · 형식을 지켜야 하는 칸 ' + advanced.length + '개</summary><p class="section-sub">괄호·따옴표 형식을 그대로 두고 값만 바꿔 주세요.</p>' + advanced.join('') + '</details>'
      : '');
  }

  function collectEdits() {
    var edits = {};
    qa('[data-edit]').forEach(function (node) {
      var field = node.getAttribute('data-edit');
      var orig = node.getAttribute('data-orig');
      var kind = node.getAttribute('data-edit-kind') || 'text';
      var raw = node.value;
      var value = raw;
      // 원래 비어 있던 칸을 그대로 두면 바꾼 칸으로 담지 않는다.
      if (kind === 'text' && raw === '' && orig === 'null') return;
      if (kind === 'lines') {
        value = raw.split('\n').map(function (x) { return x.trim(); }).filter(Boolean);
      } else if (kind === 'number') {
        value = raw === '' ? null : Number(raw);
        if (value !== null && !isFinite(value)) throw Error((FIELD_KO[field] || field) + ' 칸에는 숫자를 적어 주세요.');
      } else if (kind === 'json') {
        try {
          value = JSON.parse(raw);
        } catch (e) {
          throw Error((FIELD_KO[field] || field) + ' 칸의 괄호나 따옴표가 맞지 않아요. 고급 칸은 형식을 그대로 두고 값만 바꿔 주세요.');
        }
      }
      if (JSON.stringify(value) !== orig) edits[field] = value;
    });
    return edits;
  }

  function buildPlans(decision) {
    var answer = { decision: decision };
    if (decision === 'SELECT' || decision === 'APPROVE') {
      var pick = state.planPick || '';
      if (decision === 'SELECT' && !pick) throw Error('기획 후보 하나를 골라 주세요.');
      answer.selections = pick ? [pick] : [];
      answer.edits = collectEdits();
      if (state.items.requireExplicitSelection) {
        if (decision !== 'SELECT') throw Error('후보 하나를 직접 골라 주세요.');
        answer.supersedesRequirements = qa('[data-replace-requirement]:checked').map(function (node) {
          return node.getAttribute('data-replace-requirement');
        });
        if (answer.supersedesRequirements.length && !Object.keys(answer.edits).length)
          throw Error('기존 요구를 바꾸려면 수정 내용도 함께 적어 주세요.');
      }
    }
    if (decision === 'REQUEST_CHANGES') {
      var box = q('[data-plan-note]');
      var note = box ? box.value.trim() : '';
      if (!note) { focusField(box); throw Error('아래 수정 요청 칸에 고칠 점을 적어 주세요.'); }
      answer.requestedChanges = [{ field: 'plan', note: note }];
    }
    var more = details();
    if (answer.requestedChanges && !more.reasons) more.reasons = answer.requestedChanges[0].note;
    return Object.assign(answer, more);
  }

  // ---------------------------------------------------------------- G4a
  // 챕터별 줄(D-0107): 챕터 한 줄에 배경 후보를 가로로 늘어놓고, 마지막 칸에서 직접 적는다.
  // 고르면 다음 챕터로 넘어가고, 모든 챕터를 골라야 확정할 수 있다. 숫자 키로 고르고 N/P로 챕터를 옮긴다.
  function bgChapters() {
    return list(state.items.chapters).filter(function (c) { return c && c.chapterId; });
  }
  function bgLabel(chapter) {
    var m = /^ch(\d+)$/i.exec(String(chapter.chapterId || ''));
    return m ? m[1] + '장' : String(chapter.chapterId || '');
  }
  function bgCandidate(chapterId, candidateId) {
    var chapter = bgChapters().filter(function (c) { return c.chapterId === chapterId; })[0];
    return chapter ? list(chapter.candidates).filter(function (x) { return x.candidateId === candidateId; })[0] || null : null;
  }
  function bgRatio() {
    var m = /^(\d+)\s*[:x/]\s*(\d+)$/.exec(String(state.items.aspectRatio || ''));
    return m ? m[1] + ' / ' + m[2] : '9 / 16';
  }
  // 고른 값: 후보 id 또는 'custom'. 직접 적은 글은 bgCustom에 따로 둔다.
  function bgDone(chapterId) {
    var pick = state.bgPicks[chapterId];
    if (pick === 'custom') return Boolean(String(state.bgCustom[chapterId] || '').trim());
    return Boolean(pick && bgCandidate(chapterId, pick));
  }
  function bgRemaining() {
    return bgChapters().filter(function (c) { return !bgDone(c.chapterId); });
  }
  function bgRestore() {
    if (state.bgRestored) return;
    state.bgRestored = true;
    var rec = (state.view && state.view.record) || {};
    var sel = state.items.selection || {};
    var picks = rec.picks || sel.picks || {};
    var custom = rec.custom || sel.custom || {};
    Object.keys(picks || {}).forEach(function (ch) { state.bgPicks[ch] = picks[ch]; });
    Object.keys(custom || {}).forEach(function (ch) {
      state.bgPicks[ch] = 'custom';
      state.bgCustom[ch] = custom[ch];
    });
    var first = bgRemaining()[0] || bgChapters()[0];
    state.bgCurrent = first ? first.chapterId : '';
  }
  function renderBackgrounds(items) {
    bgRestore();
    var chapters = bgChapters();
    var locked = faceLocked();
    var most = Math.max.apply(null, [1].concat(chapters.map(function (c) { return list(c.candidates).length; })));
    return (
      '<section class="gate-section bg-board"><h2>챕터별 배경 ' + chapters.length + '줄</h2>' +
      '<p class="section-sub">' + (locked
        ? '한 줄이 한 챕터예요. 이 관문에서 고른 배경이에요.'
        : '한 줄이 한 챕터예요. 고르면 다음 챕터로 넘어가요. 마음에 드는 후보가 없으면 줄 끝 칸에 직접 적어 주세요.') + '</p>' +
      '<div class="bg-bar"><span class="blind-progress"><span data-bg-count></span>' +
      '<span class="blind-meter" aria-hidden="true"><i data-bg-meter></i></span></span>' +
      (locked ? '' : '<span class="bg-keys">숫자 키 <kbd>1</kbd>~<kbd>' + Math.min(9, most + 1) + '</kbd> 고르기 · ' + NAV_KEYS + ' 챕터</span>') + '</div>' +
      '<div class="bg-rows" data-bg-rows></div></section>' +
      '<section class="gate-section"><details class="gate-more"><summary>다시 만들 때 고칠 점</summary>' +
      '<p class="section-sub">다시 만들 챕터에만 적어 주세요. 적지 않은 챕터는 그대로 둬요.</p>' +
      chapters.map(function (chapter) {
        var ch = chapter.chapterId;
        return '<label class="card-sub">' + esc(bgLabel(chapter)) + (chapter.title ? ' · ' + esc(chapter.title) : '') + '</label>' +
          '<textarea data-chapter-note="' + esc(ch) + '" placeholder="' + esc(bgLabel(chapter)) + '을 다시 만들 때만: 무엇을 바꿀지"></textarea>';
      }).join('') + '</details></section>'
    );
  }
  function bgTile(chapter, candidate, i, locked) {
    var ch = chapter.chapterId;
    var on = state.bgPicks[ch] === candidate.candidateId;
    var art = candidate.plate && candidate.plate.url
      ? '<img src="' + esc(candidate.plate.url) + '" alt="' + esc(bgLabel(chapter) + ' 후보 ' + (i + 1) + ', ' + (candidate.place || '')) + '" loading="lazy">'
      : '<span class="bg-missing">사진 없음</span>';
    var qaBad = candidate.qa && !candidate.qa.passed;
    return '<button type="button" class="bg-tile' + (on ? ' is-picked' : '') + '" data-bg-pick="' + esc(ch) + '|' + esc(candidate.candidateId) + '" aria-pressed="' + on + '"' + (locked ? ' disabled' : '') + '>' +
      '<span class="bg-art" style="aspect-ratio:' + bgRatio() + '">' + art +
      (on ? '<span class="bg-check" aria-hidden="true">✓</span>' : '') + '</span>' +
      '<span class="bg-cap">' + (locked || i >= 9 ? '' : '<kbd>' + (i + 1) + '</kbd>') + '<b>' + esc(candidate.place || ('후보 ' + (i + 1))) + '</b></span>' +
      '<span class="bg-sub">' + esc([candidate.timeOfDay, candidate.mood].filter(Boolean).join(' · ')) + '</span>' +
      (qaBad ? '<span class="badge-chip is-bad">자동 검사 미통과</span>' : '') +
      reviewLine(candidate.candidateId) + '</button>';
  }
  function bgCustomTile(chapter, n, locked) {
    var ch = chapter.chapterId;
    var on = state.bgPicks[ch] === 'custom';
    var text = state.bgCustom[ch] || '';
    if (locked && !on) return '';
    return '<div class="bg-tile bg-custom' + (on ? ' is-picked' : '') + '">' +
      (locked
        ? '<span class="bg-cap"><b>직접 적은 배경</b></span><p class="bg-custom-text">' + esc(text) + '</p>'
        : '<button type="button" class="bg-custom-pick" data-bg-pick="' + esc(ch) + '|custom" aria-pressed="' + on + '">' +
          (n <= 9 ? '<kbd>' + n + '</kbd>' : '') + '<b>' + (on ? '직접 적기 · 고름' : '+ 직접 적기') + '</b></button>' +
          '<textarea data-bg-custom="' + esc(ch) + '" aria-label="' + esc(bgLabel(chapter) + ' 배경 직접 적기') + '" placeholder="장소·시간대·분위기를 한두 줄로 적어 주세요">' + esc(text) + '</textarea>') +
      '</div>';
  }
  function bgDetail(chapter) {
    var ch = chapter.chapterId;
    var c = state.bgPicks[ch] && state.bgPicks[ch] !== 'custom' ? bgCandidate(ch, state.bgPicks[ch]) : null;
    if (!c) return '';
    return '<details class="bg-detail" data-bg-detail="' + esc(ch) + '"' + (state.bgOpen[ch] ? ' open' : '') + '>' +
      '<summary>고른 배경 자세히 · 장면 내용·지킬 점</summary>' +
      facts([
        ['고른 이유', c.why],
        ['소품', joinList(c.props, ', ')],
        ['장면 내용', joinList(c.sceneFactsDraft, ' / ')],
        ['지킬 점', joinList(c.boundariesDraft, ' / ')]
      ]) + qaBadge(c.qa) + qaNote(c.qa) +
      (c.plateBrief ? '<details class="card-tech"><summary>생성 지시</summary>' + esc(c.plateBrief) + '</details>' : '') +
      '</details>';
  }
  function paintBackgrounds() {
    if (state.kind !== 'backgrounds') return;
    var host = q('[data-bg-rows]');
    if (!host) return;
    var locked = faceLocked();
    host.innerHTML = bgChapters().map(function (chapter) {
      var ch = chapter.chapterId;
      var cands = list(chapter.candidates);
      var current = !locked && state.bgCurrent === ch;
      return '<article class="bg-row' + (current ? ' is-current' : '') + '" data-bg-row="' + esc(ch) + '" tabindex="-1" aria-label="' + esc(bgLabel(chapter) + ' ' + (chapter.title || '')) + '">' +
        '<header class="bg-row-head"><span class="bg-ch">' + esc(bgLabel(chapter)) + '</span>' +
        '<b class="bg-title">' + esc(chapter.title || '') + '</b>' +
        '<span class="bg-arc">' + esc(chapter.arc || '') + '</span>' +
        '<span class="bg-state" data-bg-state="' + esc(ch) + '"></span></header>' +
        '<div class="bg-strip' + (locked ? ' is-locked' : '') + '" style="--bg-n:' + (cands.length + (locked && state.bgPicks[ch] !== 'custom' ? 0 : 1)) + '">' + cands.map(function (c, i) { return bgTile(chapter, c, i, locked); }).join('') +
        bgCustomTile(chapter, cands.length + 1, locked) + '</div>' + bgDetail(chapter) + '</article>';
    }).join('');
    // 좁은 화면에서 줄이 옆으로 넘어가면 고른 후보가 보이도록 그 자리로 옮겨 둔다.
    qa('.bg-strip', host).forEach(function (strip) {
      var on = q('.is-picked', strip);
      if (!on || strip.scrollWidth <= strip.clientWidth) return;
      if (on.offsetLeft + on.offsetWidth > strip.scrollLeft + strip.clientWidth || on.offsetLeft < strip.scrollLeft) {
        strip.scrollLeft = Math.max(0, on.offsetLeft - 8);
      }
    });
    paintBgMeta();
  }
  // 줄 머리 상태·진행 막대·결정 칸은 글을 적는 동안에도 다시 그린다(입력 칸은 그대로 둔다).
  function paintBgMeta() {
    if (state.kind !== 'backgrounds') return;
    var chapters = bgChapters();
    var left = bgRemaining();
    var done = chapters.length - left.length;
    var locked = faceLocked();
    var count = q('[data-bg-count]');
    if (count) count.innerHTML = '<b>' + done + ' / ' + chapters.length + '</b> 챕터 골랐어요';
    var meter = q('[data-bg-meter]');
    if (meter) meter.style.width = (chapters.length ? Math.round(done / chapters.length * 100) : 0) + '%';
    chapters.forEach(function (chapter) {
      var ch = chapter.chapterId;
      var node = q('[data-bg-state="' + ch + '"]');
      var row = q('[data-bg-row="' + ch + '"]');
      var ok = bgDone(ch);
      if (row) row.classList.toggle('is-done', ok);
      if (!node) return;
      var pick = state.bgPicks[ch];
      node.className = 'bg-state' + (ok ? ' is-done' : '');
      node.textContent = ok ? (pick === 'custom' ? '✓ 직접 적음' : '✓ 골랐어요')
        : pick === 'custom' ? '직접 적을 내용을 써 주세요' : '아직 안 골랐어요';
    });
    var side = q('[data-side-extra]');
    if (side) {
      side.innerHTML = '<div class="bg-side"><p class="bg-side-title"><b>고른 배경</b><span>' + done + ' / ' + chapters.length + '</span></p><ol class="bg-side-list">' +
        chapters.map(function (chapter) {
          var ch = chapter.chapterId;
          var pick = state.bgPicks[ch];
          var c = pick && pick !== 'custom' ? bgCandidate(ch, pick) : null;
          var ok = bgDone(ch);
          var thumb = c && c.plate && c.plate.url ? '<img src="' + esc(c.plate.url) + '" alt="" loading="lazy">' : '<span class="bg-side-slot">' + (pick === 'custom' && ok ? '글' : '') + '</span>';
          var what = c ? c.place : pick === 'custom' && ok ? '직접: ' + String(state.bgCustom[ch]).trim() : '아직 안 골랐어요';
          return '<li><button type="button" class="bg-side-item' + (ok ? ' is-done' : '') + '" data-bg-goto="' + esc(ch) + '">' + thumb +
            '<span><b>' + esc(bgLabel(chapter)) + ' · ' + esc(chapter.title || '') + '</b><span class="bg-side-what">' + esc(what) + '</span></span></button></li>';
        }).join('') + '</ol></div>';
    }
    guardQuickApprove(Object.keys(state.bgPicks).length);
    var primary = q('[data-decide="SELECT"]');
    if (primary && !locked) {
      primary.textContent = left.length ? '고른 배경으로 확정' : ro('배경 ' + chapters.length + '개') + ' 확정';
      primary.disabled = Boolean(state.busy || left.length);
      var hint = q('[data-side-hint]');
      if (hint) hint.textContent = left.length
        ? left.length + '개 챕터가 남았어요(' + left.map(bgLabel).join(', ') + '). 모두 고르면 확정할 수 있어요.'
        : '모든 챕터를 골랐어요. 확인하고 확정해 주세요.';
    }
  }
  function bgFocusRow(ch) {
    var row = q('[data-bg-row="' + ch + '"]');
    if (!row) return;
    row.focus({ preventScroll: true });
    var smooth = !(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    row.scrollIntoView({ block: 'nearest', behavior: smooth ? 'smooth' : 'auto' });
  }
  function bgMove(step) {
    var ids = bgChapters().map(function (c) { return c.chapterId; });
    if (!ids.length) return;
    var i = ids.indexOf(state.bgCurrent);
    state.bgCurrent = ids[(i + step + ids.length) % ids.length];
    paintBackgrounds();
    bgFocusRow(state.bgCurrent);
  }
  function pickBackground(ch, value) {
    if (faceLocked()) return;
    if (value !== 'custom' && !bgCandidate(ch, value)) return;
    state.bgPicks[ch] = value;
    state.bgCurrent = ch;
    if (value !== 'custom') {
      // 다 고르지 않은 다음 챕터로 넘어간다. 모두 골랐으면 그 자리에 둔다.
      var ids = bgChapters().map(function (c) { return c.chapterId; });
      var start = ids.indexOf(ch);
      for (var step = 1; step < ids.length; step += 1) {
        var next = ids[(start + step) % ids.length];
        if (!bgDone(next)) { state.bgCurrent = next; break; }
      }
    }
    setStatus('');
    paintBackgrounds();
    if (value === 'custom') {
      var box = q('[data-bg-custom="' + ch + '"]');
      if (box) box.focus();
    } else if (state.bgCurrent !== ch) {
      bgFocusRow(state.bgCurrent);
    }
  }
  function onBackgroundKey(event) {
    if (state.kind !== 'backgrounds' || faceLocked() || event.altKey || event.ctrlKey || event.metaKey) return;
    var tag = event.target && event.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    var key = String(event.key || '').toLowerCase();
    var chapter = bgChapters().filter(function (c) { return c.chapterId === state.bgCurrent; })[0];
    if (!chapter) return;
    var cands = list(chapter.candidates);
    var n = Number(key);
    if (/^[1-9]$/.test(key) && n <= cands.length) { event.preventDefault(); pickBackground(chapter.chapterId, cands[n - 1].candidateId); }
    else if (/^[1-9]$/.test(key) && n === cands.length + 1) { event.preventDefault(); pickBackground(chapter.chapterId, 'custom'); }
    else if (navStep(key)) { event.preventDefault(); bgMove(navStep(key)); }
  }

  // D-0049: 수정 요청은 챕터별 메모(requestedChanges)로 보내 요청한 챕터만 다시 만든다.
  function collectChapterChanges() {
    var changes = [];
    qa('[data-chapter-note]').forEach(function (node) {
      var note = node.value.trim();
      if (note) changes.push({ field: node.getAttribute('data-chapter-note'), note: note });
    });
    if (!changes.length) throw Error('다시 만들 챕터에 고칠 점을 적어 주세요.');
    return changes;
  }

  function buildBackgrounds(decision) {
    var answer = { decision: decision };
    if (decision === 'SELECT') {
      var picks = {};
      var custom = {};
      bgChapters().forEach(function (chapter) {
        var ch = chapter.chapterId;
        var pick = state.bgPicks[ch];
        if (!pick) throw Error(bgLabel(chapter) + '에서 배경 하나를 고르거나 직접 적어 주세요.');
        if (pick === 'custom') {
          var text = String(state.bgCustom[ch] || '').trim();
          if (!text) throw Error(bgLabel(chapter) + '에 직접 적을 배경을 한두 줄로 써 주세요.');
          custom[ch] = text;
        } else {
          picks[ch] = pick;
        }
      });
      answer.picks = picks;
      answer.custom = custom;
    }
    if (decision === 'REQUEST_CHANGES') {
      try {
        answer.requestedChanges = collectChapterChanges();
      } catch (error) {
        // 접어 둔 메모 칸을 열고 첫 칸으로 옮겨 어디에 적을지 바로 보이게 한다.
        var note = q('[data-chapter-note]');
        var box = note && note.closest('details');
        if (box) box.open = true;
        if (note) note.focus();
        throw error;
      }
    }
    return Object.assign(answer, details());
  }

  // ---------------------------------------------------------------- G4b
  // 챕터 탭(D-0108): 한 번에 한 챕터의 장면과 자세 후보를 본다. 자세 후보는 같은 항목을 가로로 맞춘 표다.
  var POSE_FIELD_KO = { body: '몸', hands: '손', props: '소품', gaze: '시선', expression: '표정', shot: '구도', outfit: '의상', motionHint: '움직임' };
  function poseChapters() {
    return list(state.items.chapters).filter(function (c) { return c && c.chapterId; });
  }
  function poseChapter(ch) {
    return poseChapters().filter(function (c) { return c.chapterId === ch; })[0] || null;
  }
  function poseById(ch, id) {
    var chapter = poseChapter(ch);
    return chapter ? list(chapter.candidates).filter(function (p) { return p.poseId === id; })[0] || null : null;
  }
  function poseDone(ch) {
    var pick = state.posePicks[ch];
    if (pick === 'custom') return Boolean(String(state.poseCustom[ch] || '').trim());
    return Boolean(pick && poseById(ch, pick));
  }
  function poseLeft() {
    return poseChapters().filter(function (c) { return !poseDone(c.chapterId); });
  }
  function poseTweakCount(ch) {
    var t = state.poseTweaks[ch] || {};
    return Object.keys(t).filter(function (k) { return String(t[k] || '').trim(); }).length;
  }
  function poseRestore() {
    if (state.poseRestored) return;
    state.poseRestored = true;
    var rec = (state.view && state.view.record) || {};
    var sel = state.items.selection || {};
    var picks = rec.picks || sel.picks || {};
    var custom = rec.custom || sel.custom || {};
    var tweaks = rec.tweaks || sel.tweaks || {};
    Object.keys(picks).forEach(function (ch) { state.posePicks[ch] = picks[ch]; });
    Object.keys(custom).forEach(function (ch) { state.posePicks[ch] = 'custom'; state.poseCustom[ch] = custom[ch]; });
    Object.keys(tweaks).forEach(function (ch) { state.poseTweaks[ch] = Object.assign({}, tweaks[ch]); });
    var first = poseLeft()[0] || poseChapters()[0];
    state.poseTab = first ? first.chapterId : '';
  }
  function chapterNotes(chapters, label) {
    return '<section class="gate-section"><details class="gate-more"><summary>다시 만들 때 고칠 점</summary>' +
      '<p class="section-sub">다시 만들 챕터에만 적어 주세요. 적지 않은 챕터는 그대로 둬요.</p>' +
      list(chapters).map(function (chapter) {
        var ch = chapter.chapterId;
        return '<label class="card-sub">' + esc(label(chapter)) + '</label>' +
          '<textarea data-chapter-note="' + esc(ch) + '" placeholder="' + esc(bgLabel(chapter)) + '을 다시 만들 때만: 무엇을 바꿀지"></textarea>';
      }).join('') + '</details></section>';
  }
  function openChapterNotes() {
    var note = q('[data-chapter-note]');
    var box = note && note.closest('details');
    if (box) box.open = true;
    if (note) note.focus();
  }
  function renderPoses(items) {
    poseRestore();
    var locked = faceLocked();
    return (
      '<section class="gate-section pose-board"><h2>챕터별 장면과 자세</h2>' +
      '<p class="section-sub">' + (locked ? '챕터마다 고른 자세예요.'
        : '챕터마다 장면을 확인하고 자세 하나를 골라 주세요. 자세 후보는 같은 항목끼리 가로로 맞췄어요. 고른 자세의 세부 항목은 표 아래에서 고칠 수 있어요.') + '</p>' +
      '<div class="pose-tabs" role="tablist" aria-label="챕터" data-pose-tabs></div>' +
      '<div class="pose-panel" role="tabpanel" data-pose-panel></div></section>' +
      chapterNotes(items.chapters, function (c) { return bgLabel(c) + (c.place ? ' · ' + c.place : ''); })
    );
  }
  function paintPoses() {
    if (state.kind !== 'poses') return;
    var tabs = q('[data-pose-tabs]');
    var panel = q('[data-pose-panel]');
    if (!tabs || !panel) return;
    var locked = faceLocked();
    var chapter = poseChapter(state.poseTab) || poseChapters()[0];
    if (!chapter) { panel.innerHTML = '<p class="empty">장면이 아직 없어요.</p>'; return; }
    var ch = chapter.chapterId;
    var cands = list(chapter.candidates);
    var fields = list(state.items.poseFields);
    var pick = state.posePicks[ch] || '';
    var cls = function (id) { return pick === id ? ' is-picked' : ''; };
    var head = '<thead><tr><th scope="col" class="plan-corner">항목</th>' + cands.map(function (p, i) {
      return '<th scope="col" class="plan-col' + cls(p.poseId) + '"><span class="plan-col-label">' + (locked ? '' : '<kbd>' + (i + 1) + '</kbd>') + '</span>' +
        '<b>' + esc(p.title || ('자세 ' + (i + 1))) + '</b>' + (p.animatable === false ? '<span class="badge-chip is-bad">움직이기 어려움</span>' : '') + reviewLine(p.poseId) +
        (locked ? (pick === p.poseId ? '<span class="badge-chip is-good">고른 자세</span>' : '')
          : '<button type="button" class="btn ' + (pick === p.poseId ? 'btn--primary' : 'btn--ghost') + ' plan-pick" data-pose-pick="' + esc(ch) + '|' + esc(p.poseId) + '" aria-pressed="' + (pick === p.poseId) + '">' + (pick === p.poseId ? '고른 자세' : '이 자세 고르기') + '</button>') + '</th>';
    }).join('') + (locked && pick !== 'custom' ? '' :
      '<th scope="col" class="plan-col pose-custom-col' + cls('custom') + '"><span class="plan-col-label">' + (locked ? '' : '<kbd>' + (cands.length + 1) + '</kbd>') + '</span><b>직접 적기</b>' +
      (locked ? '<span class="badge-chip is-good">고른 자세</span>'
        : '<button type="button" class="btn ' + (pick === 'custom' ? 'btn--primary' : 'btn--ghost') + ' plan-pick" data-pose-pick="' + esc(ch) + '|custom" aria-pressed="' + (pick === 'custom') + '">' + (pick === 'custom' ? '직접 적기 고름' : '직접 적기') + '</button>') + '</th>') + '</tr></thead>';
    var body = fields.map(function (field, row) {
      var vals = cands.map(function (p) { return String(p[field] == null ? '' : p[field]); });
      var diff = vals.some(function (v) { return v !== vals[0]; });
      var tweak = (state.poseTweaks[ch] || {})[field];
      return '<tr class="' + (diff ? 'is-diff' : 'is-same') + '"><th scope="row">' + (diff ? '<span class="plan-diff-dot" aria-hidden="true"></span>' : '') + esc(POSE_FIELD_KO[field] || field) + (diff ? '<span class="sr-only"> (자세마다 달라요)</span>' : '') + '</th>' +
        cands.map(function (p, i) {
          var changed = pick === p.poseId && tweak && String(tweak).trim();
          return '<td class="' + cls(p.poseId).trim() + '">' + (changed ? '<s class="pose-old">' + esc(vals[i]) + '</s> <span class="pose-new">' + esc(tweak) + '</span>' : esc(vals[i]) || '<span class="plan-none">—</span>') + '</td>';
        }).join('') +
        (locked && pick !== 'custom' ? '' : row === 0
          ? '<td class="pose-custom-cell' + cls('custom') + '" rowspan="' + fields.length + '">' + (locked
              ? '<p class="bg-custom-text">' + esc(state.poseCustom[ch] || '') + '</p>'
              : '<textarea data-pose-custom="' + esc(ch) + '" aria-label="' + esc(bgLabel(chapter) + ' 자세 직접 적기') + '" placeholder="몸·손·표정·의상을 한두 줄로 적어 주세요">' + esc(state.poseCustom[ch] || '') + '</textarea>') + '</td>'
          : '') + '</tr>';
    }).join('');
    var picked = pick && pick !== 'custom' ? poseById(ch, pick) : null;
    var tweakBox = picked
      ? '<details class="gate-more pose-tweak" data-pose-tweak-box' + (state.poseTweakOpen || locked && poseTweakCount(ch) ? ' open' : '') + '><summary>' + esc(picked.title || '고른 자세') + ' 세부 고치기 (선택)' + (poseTweakCount(ch) ? ' · ' + poseTweakCount(ch) + '곳 고침' : '') + '</summary>' +
        '<p class="section-sub">바꿀 칸에만 새 값을 적어 주세요. 비운 칸은 원래 값을 그대로 써요.</p><div class="field-list">' +
        fields.map(function (field) {
          var v = (state.poseTweaks[ch] || {})[field] || '';
          return '<div class="field"><span>' + esc(POSE_FIELD_KO[field] || field) + '</span><input type="text" data-pose-tweak="' + esc(ch) + ':' + esc(field) + '" value="' + esc(v) + '" placeholder="' + esc(picked[field] || '') + '"' + (locked ? ' readonly' : '') + '></div>';
        }).join('') + '</div></details>'
      : '';
    var ids = poseChapters().map(function (c) { return c.chapterId; });
    var at = ids.indexOf(ch);
    var nextLeft = poseLeft().filter(function (c) { return c.chapterId !== ch; })[0];
    var nav = locked ? '' : '<div class="pose-nav">' +
      (at > 0 ? '<button type="button" class="btn btn--ghost" data-pose-tab="' + esc(ids[at - 1]) + '">← ' + esc(bgLabel(poseChapter(ids[at - 1]))) + '</button>' : '<span></span>') +
      (nextLeft && poseDone(ch) ? '<button type="button" class="btn btn--primary" data-pose-tab="' + esc(nextLeft.chapterId) + '">다음: ' + esc(bgLabel(nextLeft)) + ' 고르기 →</button>'
        : at < ids.length - 1 ? '<button type="button" class="btn btn--ghost" data-pose-tab="' + esc(ids[at + 1]) + '">' + esc(bgLabel(poseChapter(ids[at + 1]))) + ' →</button>' : '<span></span>') + '</div>';
    panel.innerHTML =
      '<div class="pose-scene">' + (chapter.plate && chapter.plate.url ? '<img class="pose-plate" src="' + esc(chapter.plate.url) + '" alt="' + esc(bgLabel(chapter) + ' 배경') + '" loading="lazy">' : '') +
      '<div class="pose-scene-text"><p class="pose-scene-title"><span class="bg-ch">' + esc(bgLabel(chapter)) + '</span><b>' + esc(chapter.place || '') + '</b></p>' +
      facts([
        ['시간대', chapter.timeOfDay],
        ['분위기', chapter.mood],
        ['장면 내용', joinList(chapter.sceneFacts, ' / ')],
        ['만나는 경위', chapter.meetingContext],
        ['관계', joinList(chapter.relationshipCanon, ' / ')],
        ['지킬 점', joinList(chapter.sceneBoundaries, ' / ')]
      ]) + qaBadge(chapter.qa) + qaNote(chapter.qa) + '</div></div>' +
      '<div class="plan-scroll"><table class="plan-table pose-table" style="min-width:' + (112 + (cands.length + (locked && pick !== 'custom' ? 0 : 1)) * 140) + 'px"><colgroup><col class="plan-label-col">' + cands.map(function () { return '<col>'; }).join('') + (locked && pick !== 'custom' ? '' : '<col>') + '</colgroup>' + head + '<tbody>' + body + '</tbody></table></div>' +
      tweakBox + nav;
    paintPoseMeta();
  }
  function paintPoseMeta() {
    if (state.kind !== 'poses') return;
    var chapters = poseChapters();
    var left = poseLeft();
    var locked = faceLocked();
    var tabs = q('[data-pose-tabs]');
    if (tabs) tabs.innerHTML = chapters.map(function (c) {
      var on = c.chapterId === state.poseTab;
      var ok = poseDone(c.chapterId);
      return '<button type="button" role="tab" class="pose-tab' + (ok ? ' is-done' : '') + '" data-pose-tab="' + esc(c.chapterId) + '" aria-selected="' + on + '">' +
        '<span class="pose-tab-mark" aria-hidden="true">' + (ok ? '✓' : '') + '</span><b>' + esc(bgLabel(c)) + '</b><span class="pose-tab-sub">' + esc(c.place || '') + '</span>' +
        '<span class="sr-only">' + (ok ? ' 골랐어요' : ' 아직 안 골랐어요') + '</span></button>';
    }).join('') + '<span class="pose-tabs-count">' + (chapters.length - left.length) + ' / ' + chapters.length + ' 골랐어요</span>';
    var side = q('[data-side-extra]');
    if (side) side.innerHTML = '<div class="bg-side"><p class="bg-side-title"><b>고른 자세</b><span>' + (chapters.length - left.length) + ' / ' + chapters.length + '</span></p><ol class="bg-side-list">' +
      chapters.map(function (c) {
        var ch = c.chapterId;
        var pick = state.posePicks[ch];
        var pose = pick && pick !== 'custom' ? poseById(ch, pick) : null;
        var ok = poseDone(ch);
        var what = pose ? (pose.title || pose.poseId) + ' · ' + (pose.body || '') : pick === 'custom' && ok ? '직접: ' + String(state.poseCustom[ch]).trim() : '아직 안 골랐어요';
        var n = poseTweakCount(ch);
        return '<li><button type="button" class="bg-side-item' + (ok ? ' is-done' : '') + '" data-pose-tab="' + esc(ch) + '">' +
          (c.plate && c.plate.url ? '<img src="' + esc(c.plate.url) + '" alt="" loading="lazy">' : '<span class="bg-side-slot"></span>') +
          '<span><b>' + esc(bgLabel(c)) + ' · ' + esc(c.place || '') + '</b><span class="bg-side-what">' + esc(what) + '</span>' +
          (pose && n ? '<span class="bg-side-what">세부 ' + n + '곳 고침</span>' : '') + '</span></button></li>';
      }).join('') + '</ol></div>';
    guardQuickApprove(Object.keys(state.posePicks).length);
    var primary = q('[data-decide="SELECT"]');
    if (primary && !locked) {
      primary.textContent = left.length ? '고른 자세로 확정' : ro('자세 ' + chapters.length + '개') + ' 확정';
      primary.disabled = Boolean(state.busy || left.length);
      var hint = q('[data-side-hint]');
      if (hint) hint.textContent = left.length
        ? left.length + '개 챕터가 남았어요(' + left.map(bgLabel).join(', ') + '). 모두 고르면 확정할 수 있어요.'
        : '모든 챕터를 골랐어요. 확인하고 확정해 주세요.';
    }
  }
  function poseTab(ch) {
    if (!poseChapter(ch)) return;
    state.poseTab = ch;
    paintPoses();
    var tab = q('[data-pose-tabs] [aria-selected="true"]');
    if (tab) tab.focus({ preventScroll: true });
    var board = q('.pose-board');
    if (board && board.getBoundingClientRect().top < 0) board.scrollIntoView({ block: 'start' });
  }
  function pickPose(ch, value) {
    if (faceLocked()) return;
    if (value !== 'custom' && !poseById(ch, value)) return;
    state.posePicks[ch] = value;
    state.poseTab = ch;
    setStatus('');
    if (value !== 'custom') {
      // G4a처럼 다 고르지 않은 다음 챕터로 넘어간다. 모두 골랐으면 그 자리에 둔다(QA v5 C-16).
      var ids = poseChapters().map(function (c) { return c.chapterId; });
      var start = ids.indexOf(ch);
      for (var step = 1; step < ids.length; step += 1) {
        var next = ids[(start + step) % ids.length];
        if (!poseDone(next)) { poseTab(next); return; }
      }
    }
    paintPoses();
    if (value === 'custom') {
      var box = q('[data-pose-custom="' + ch + '"]');
      if (box) box.focus();
    }
  }
  function onPoseKey(event) {
    if (state.kind !== 'poses' || faceLocked() || event.altKey || event.ctrlKey || event.metaKey) return;
    var tag = event.target && event.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    var key = String(event.key || '').toLowerCase();
    var chapter = poseChapter(state.poseTab);
    if (!chapter) return;
    var cands = list(chapter.candidates);
    var n = Number(key);
    var ids = poseChapters().map(function (c) { return c.chapterId; });
    var at = ids.indexOf(state.poseTab);
    if (/^[1-9]$/.test(key) && n <= cands.length) { event.preventDefault(); pickPose(chapter.chapterId, cands[n - 1].poseId); }
    else if (/^[1-9]$/.test(key) && n === cands.length + 1) { event.preventDefault(); pickPose(chapter.chapterId, 'custom'); }
    else if (navStep(key)) { event.preventDefault(); poseTab(ids[(at + navStep(key) + ids.length) % ids.length]); }
  }

  function buildPoses(decision) {
    var answer = { decision: decision };
    if (decision === 'SELECT') {
      var picks = {};
      var custom = {};
      var tweaks = {};
      poseChapters().forEach(function (chapter) {
        var ch = chapter.chapterId;
        var pick = state.posePicks[ch];
        if (!pick) throw Error(bgLabel(chapter) + '에서 자세 하나를 고르거나 직접 적어 주세요.');
        if (pick === 'custom') {
          var text = String(state.poseCustom[ch] || '').trim();
          if (!text) throw Error(bgLabel(chapter) + '에 직접 적을 자세를 한두 줄로 써 주세요.');
          custom[ch] = text;
          return;
        }
        picks[ch] = pick;
        var t = state.poseTweaks[ch] || {};
        var changes = {};
        Object.keys(t).forEach(function (field) { var v = String(t[field] || '').trim(); if (v) changes[field] = v; });
        if (Object.keys(changes).length) tweaks[ch] = changes;
      });
      answer.picks = picks;
      answer.custom = custom;
      answer.tweaks = tweaks;
    }
    if (decision === 'REQUEST_CHANGES') {
      try {
        answer.requestedChanges = collectChapterChanges();
      } catch (error) {
        openChapterNotes();
        throw error;
      }
    }
    return Object.assign(answer, details());
  }

  // ---------------------------------------------------------------- G4
  // 큰 이미지와 챕터별 확인(D-0109): 완성 이미지를 크게 나란히 두고 챕터마다 '괜찮아요/고칠게요'를 고른다.
  // 이미지를 누르면 기준 얼굴과 나란히 크게 본다. 모두 괜찮으면 승인, 하나라도 고치면 수정 요청이다.
  function frameList() {
    return list(state.items.frames).filter(function (f) { return f && f.chapterId; });
  }
  // 지난 판에서 보낸 수정 요청(가장 최근 것). 다시 만든 판에서 무엇을 고쳐 달라고 했는지 보인다.
  function lastAsk() {
    var view = state.view || {};
    var recs = list(view.records).map(function (r) { return r && r.record; }).filter(function (r) {
      return r && r.rev && r.rev !== view.rev && r.decision === 'REQUEST_CHANGES';
    });
    recs.sort(function (x, y) { return String(x.decidedAt || '').localeCompare(String(y.decidedAt || '')); });
    var last = recs[recs.length - 1];
    var out = {};
    if (last) list(last.requestedChanges).forEach(function (c) { if (c && c.field) out[c.field] = c.note || ''; });
    return last ? out : null;
  }
  function frameRestore() {
    if (state.frameRestored) return;
    state.frameRestored = true;
    var rec = (state.view && state.view.record) || {};
    var ask = lastAsk();
    if (!rec.decision && ask) {
      // 지난 판에서 괜찮다고 한 챕터는 미리 '괜찮아요'로 둔다. 다시 만든 챕터만 보면 된다.
      frameList().forEach(function (f) { if (!(f.chapterId in ask)) state.frameVerdict[f.chapterId] = 'ok'; });
    }
    if (rec.decision === 'APPROVE') frameList().forEach(function (f) { state.frameVerdict[f.chapterId] = 'ok'; });
    list(rec.requestedChanges).forEach(function (c) {
      if (!c || !c.field) return;
      state.frameVerdict[c.field] = 'fix';
      state.frameNote[c.field] = c.note || '';
    });
    if (rec.decision === 'REQUEST_CHANGES') frameList().forEach(function (f) { if (!state.frameVerdict[f.chapterId]) state.frameVerdict[f.chapterId] = 'ok'; });
  }
  function frameCounts() {
    var frames = frameList();
    var n = { total: frames.length, ok: 0, fix: 0, fixReady: 0, judged: 0 };
    frames.forEach(function (f) {
      var v = state.frameVerdict[f.chapterId];
      if (v) n.judged += 1;
      if (v === 'ok') n.ok += 1;
      if (v === 'fix') { n.fix += 1; if (String(state.frameNote[f.chapterId] || '').trim()) n.fixReady += 1; }
    });
    return n;
  }
  function renderFrames(items) {
    frameRestore();
    var locked = faceLocked();
    return (
      '<section class="gate-section frame-board"><h2>챕터 완성 이미지 ' + frameList().length + '개</h2>' +
      '<p class="section-sub">' + (locked ? '챕터마다 확인한 결과예요.'
        : '기준 얼굴과 같은 사람인지, 장면·자세가 맞는지 보고 챕터마다 골라 주세요. 이미지를 누르면 기준 얼굴과 나란히 크게 볼 수 있어요.') + '</p>' +
      '<div class="frame-ref">' + (items.identityReference && items.identityReference.url
        ? '<button type="button" class="frame-ref-img" data-frame-zoom="__ref">' + image(items.identityReference) + '</button>' : '') +
      '<div><b>기준 얼굴</b><p class="section-sub">' + (isMotif() ? '기준 사진 선택에서 고른 사진이에요.' : '얼굴 고르기에서 고른 얼굴로 만든 기준 사진이에요.') + ' 모든 챕터 이미지가 이 사람이어야 해요.</p>' +
      '<details class="card-tech"><summary>만든 근거</summary>' + facts([
        ['외모', items.appearanceRev], ['장면', items.sceneRev], ['얼굴 참조', items.referenceCrop], ['참조 메모', items.cropNote]
      ]) + '</details></div></div>' +
      '<div class="frame-grid" data-frame-grid></div></section>' +
      '<div class="frame-zoom" data-frame-zoom-box hidden></div>'
    );
  }
  function paintFrames() {
    if (state.kind !== 'frames') return;
    var grid = q('[data-frame-grid]');
    if (!grid) return;
    var locked = faceLocked();
    var ask = lastAsk();
    grid.style.setProperty('--frame-n', String(Math.max(1, frameList().length)));
    grid.innerHTML = frameList().map(function (f) {
      var ch = f.chapterId;
      var v = state.frameVerdict[ch] || '';
      return '<article class="frame-card' + (v ? ' is-' + v : '') + '" data-frame-card="' + esc(ch) + '">' +
        '<p class="frame-head"><span class="bg-ch">' + esc(bgLabel(f)) + '</span>' + qaBadge(f.qa) + '</p>' +
        '<button type="button" class="frame-img" data-frame-zoom="' + esc(ch) + '" aria-label="' + esc(bgLabel(f) + ' 크게 보기') + '">' +
        (f.file && f.file.url ? image(f.file) : '<span class="bg-missing">이미지 없음</span>') + '<span class="frame-zoom-hint">크게 보기</span></button>' +
        reviewLine(f.frameId) + qaNote(f.qa) +
        (ask && (ch in ask) ? '<p class="qa-note is-ask"><b>다시 만든 챕터</b> 지난 요청: ' + esc(ask[ch]) + '</p>'
          : ask && !locked ? '<p class="frame-kept">지난 버전에서 괜찮다고 했어요</p>' : '') +
        (locked
          ? '<p class="frame-verdict-ro">' + (v === 'fix' ? '고칠게요' : v === 'ok' ? '괜찮아요' : '확인 안 함') + '</p>' +
            (v === 'fix' && state.frameNote[ch] ? '<p class="bg-custom-text">' + esc(state.frameNote[ch]) + '</p>' : '')
          : '<div class="seg frame-seg" role="group" aria-label="' + esc(bgLabel(f) + ' 확인') + '">' +
            '<button type="button" data-frame-verdict="' + esc(ch) + '|ok" aria-pressed="' + (v === 'ok') + '">괜찮아요</button>' +
            '<button type="button" data-frame-verdict="' + esc(ch) + '|fix" aria-pressed="' + (v === 'fix') + '">고칠게요</button></div>' +
            '<textarea data-frame-note="' + esc(ch) + '"' + (v === 'fix' ? '' : ' hidden') + ' placeholder="무엇을 바꿀지 적어 주세요. 예: 손 모양이 어색해요">' + esc(state.frameNote[ch] || '') + '</textarea>') +
        '<details class="card-tech"><summary>생성 지시 원문</summary>' + esc(f.prompt || '') + '</details>' +
        '</article>';
    }).join('');
    paintFrameMeta();
    paintFrameZoom();
  }
  function paintFrameMeta() {
    if (state.kind !== 'frames') return;
    var n = frameCounts();
    var locked = faceLocked();
    var side = q('[data-side-extra]');
    if (side) side.innerHTML = '<div class="bg-side"><p class="bg-side-title"><b>확인한 챕터</b><span>' + n.judged + ' / ' + n.total + '</span></p><ol class="bg-side-list">' +
      frameList().map(function (f) {
        var v = state.frameVerdict[f.chapterId];
        var what = v === 'ok' ? '괜찮아요' : v === 'fix' ? '고칠게요' + (String(state.frameNote[f.chapterId] || '').trim() ? ': ' + state.frameNote[f.chapterId].trim() : ' · 고칠 점을 적어 주세요') : '아직 안 봤어요';
        return '<li><button type="button" class="bg-side-item' + (v === 'ok' ? ' is-done' : '') + (v === 'fix' ? ' is-fix' : '') + '" data-frame-zoom="' + esc(f.chapterId) + '">' +
          (f.file && f.file.url ? '<img src="' + esc(f.file.url) + '" alt="" loading="lazy">' : '<span class="bg-side-slot"></span>') +
          '<span><b>' + esc(bgLabel(f)) + '</b><span class="bg-side-what">' + esc(what) + '</span></span></button></li>';
      }).join('') + '</ol></div>';
    if (locked) return;
    var approve = q('[data-decide="APPROVE"]');
    var change = q('[data-decide="REQUEST_CHANGES"]');
    var allOk = n.total > 0 && n.ok === n.total;
    if (approve) {
      approve.disabled = Boolean(state.busy || !allOk);
      approve.textContent = '챕터 ' + n.total + '개 모두 승인';
      approve.className = 'btn btn--wide ' + (n.fix ? 'btn--ghost' : 'btn--primary');
    }
    if (change) {
      change.disabled = Boolean(state.busy || !n.fix || n.fixReady < n.fix);
      change.textContent = n.fix ? '수정 요청 · 챕터 ' + n.fix + '개' : '수정 요청';
      change.className = 'btn btn--wide ' + (n.fix ? 'btn--primary' : 'btn--ghost');
    }
    var hint = q('[data-side-hint]');
    if (hint) hint.textContent = n.fix
      ? (n.fixReady < n.fix ? '고칠 챕터에 무엇을 바꿀지 적어 주세요. 적으면 수정 요청을 보낼 수 있어요.' : '고칠 챕터만 다시 만들어요. 괜찮은 챕터는 그대로 둬요.')
      : allOk ? '모두 괜찮아요. 승인하면 다음 단계로 넘어가요.'
      : (n.total - n.judged) + '개 챕터가 남았어요. 챕터마다 괜찮은지 골라 주세요.';
  }
  function paintFrameZoom() {
    var box = q('[data-frame-zoom-box]');
    if (!box) return;
    var ch = state.frameZoom;
    var frames = frameList();
    var at = -1;
    frames.forEach(function (f, i) { if (f.chapterId === ch) at = i; });
    var ref = state.items.identityReference;
    if (!ch || (ch !== '__ref' && at < 0)) { box.hidden = true; box.innerHTML = ''; return; }
    var f = at >= 0 ? frames[at] : null;
    var v = f ? state.frameVerdict[f.chapterId] || '' : '';
    var locked = faceLocked();
    box.hidden = false;
    box.innerHTML = '<div class="frame-zoom-inner" role="dialog" aria-modal="true" aria-label="' + esc(f ? bgLabel(f) + ' 크게 보기' : '기준 얼굴') + '">' +
      '<div class="frame-zoom-head"><b>' + esc(f ? bgLabel(f) + ' · 기준 얼굴과 비교' : '기준 얼굴') + '</b>' +
      '<span class="bg-keys">' + NAV_KEYS + ' 챕터 · <kbd>Esc</kbd> 닫기</span>' +
      '<button type="button" class="btn btn--ghost" data-frame-zoom-close>닫기</button></div>' +
      '<div class="frame-zoom-pair">' + (ref && ref.url ? '<figure>' + image(ref) + '<figcaption>기준 얼굴</figcaption></figure>' : '') +
      (f ? '<figure>' + image(f.file) + '<figcaption>' + esc(bgLabel(f)) + '</figcaption></figure>' : '') + '</div>' +
      (f && !locked ? '<div class="frame-zoom-foot"><div class="seg frame-seg">' +
        '<button type="button" data-frame-verdict="' + esc(f.chapterId) + '|ok" aria-pressed="' + (v === 'ok') + '">괜찮아요</button>' +
        '<button type="button" data-frame-verdict="' + esc(f.chapterId) + '|fix" aria-pressed="' + (v === 'fix') + '">고칠게요</button></div>' +
        (frames.length > 1 ? '<button type="button" class="btn btn--ghost" data-frame-zoom="' + esc(frames[(at + 1) % frames.length].chapterId) + '">다음 챕터 →</button>' : '') + '</div>' : '') +
      '</div>';
    var close = q('[data-frame-zoom-close]', box);
    if (close && !box.contains(document.activeElement)) close.focus();
  }
  function setFrameVerdict(ch, v) {
    if (faceLocked()) return;
    state.frameVerdict[ch] = v;
    setStatus('');
    var zoomed = state.frameZoom;
    if (zoomed && v === 'ok') {
      // 크게 보기에서 괜찮다고 하면 아직 안 본 다음 챕터로 넘어간다. 다 봤으면 닫는다.
      var next = frameList().filter(function (f) { return !state.frameVerdict[f.chapterId]; })[0];
      state.frameZoom = next ? next.chapterId : '';
    } else if (zoomed && v === 'fix') {
      state.frameZoom = '';
    }
    paintFrames();
    if (v === 'fix') {
      var note = q('[data-frame-note="' + ch + '"]');
      if (note) { note.scrollIntoView({ block: 'nearest' }); note.focus(); }
    }
  }
  function onFrameKey(event) {
    if (state.kind !== 'frames' || !state.frameZoom) return;
    var frames = frameList();
    var at = -1;
    frames.forEach(function (f, i) { if (f.chapterId === state.frameZoom) at = i; });
    if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); state.frameZoom = ''; paintFrameZoom(); return; }
    if (at < 0 || frames.length < 2) return;
    var tagF = event.target && event.target.tagName;
    if (tagF === 'TEXTAREA' || tagF === 'INPUT') return;
    var stepF = navStep(String(event.key || '').toLowerCase());
    if (stepF) { event.preventDefault(); state.frameZoom = frames[(at + stepF + frames.length) % frames.length].chapterId; paintFrameZoom(); }
  }
  function buildFrames(decision) {
    var answer = { decision: decision };
    var n = frameCounts();
    if (decision === 'APPROVE' && n.ok < n.total) throw Error('모든 챕터를 괜찮다고 골라야 승인할 수 있어요.');
    if (decision === 'REQUEST_CHANGES') {
      var changes = [];
      frameList().forEach(function (f) {
        if (state.frameVerdict[f.chapterId] !== 'fix') return;
        var note = String(state.frameNote[f.chapterId] || '').trim();
        if (!note) throw Error(bgLabel(f) + '에서 바꿀 내용을 적어 주세요.');
        changes.push({ field: f.chapterId, note: note });
      });
      if (!changes.length) throw Error('고칠 챕터를 하나 이상 골라 주세요.');
      answer.requestedChanges = changes;
    }
    return Object.assign(answer, details());
  }

  // ---------------------------------------------------------------- G5
  // 영상 나란히 보기(D-0110): 첫 프레임 옆에 후보 영상을 나란히 두고 한 번에 같이 재생한다.
  function introCandidates() {
    return list(state.items.candidates).filter(function (c) { return c && c.candidateId; });
  }
  function introById(id) {
    return introCandidates().filter(function (c) { return c.candidateId === id; })[0] || null;
  }
  function introLabel(c) {
    var i = introCandidates().indexOf(c);
    return '영상 ' + (i + 1);
  }
  function measured(probe) {
    probe = probe || {};
    if (!probe.durationS && !probe.width) return '';
    return [probe.durationS ? Math.round(probe.durationS * 10) / 10 + '초' : '', probe.width ? probe.width + '×' + probe.height : ''].filter(Boolean).join(' · ');
  }
  function clipVideo(file, attrs) {
    if (!file || !file.url) return '<span class="clip-broken">영상 파일이 없어요</span>';
    return '<span class="clip"><video src="' + esc(file.url) + '" muted loop playsinline preload="metadata" ' + (attrs || '') + '></video>' +
      '<span class="clip-broken" hidden>이 영상을 재생하지 못했어요. <a href="' + esc(file.url) + '" target="_blank" rel="noopener">파일 열기</a></span></span>';
  }
  // 재생하지 못한 영상은 회색 칸 대신 이유와 파일 링크를 보인다.
  function watchClips(root) {
    qa('.clip video', root).forEach(function (v) {
      v.addEventListener('error', function () {
        v.hidden = true;
        var note = v.parentNode && v.parentNode.querySelector('.clip-broken');
        if (note) note.hidden = false;
        // 재생할 수 있는 영상이 하나도 없으면 재생 버튼을 잠근다.
        if (!qa('[data-intro-video]').some(function (x) { return !x.hidden; })) {
          qa('[data-intro-play], [data-intro-restart]').forEach(function (btn) { btn.disabled = true; btn.title = '재생할 수 있는 영상이 없어요'; });
        }
      });
    });
  }
  function renderIntro(items) {
    if (!state.introRestored) {
      state.introRestored = true;
      var rec = (state.view && state.view.record) || {};
      var chosen = list(rec.selections).filter(function (id) { return introById(id); })[0];
      if (chosen) state.introPick = chosen;
    }
    var settings = items.settings || {};
    var locked = faceLocked();
    return (
      '<section class="gate-section intro-board"><h2>소개 영상 후보 ' + introCandidates().length + '개 나란히 보기</h2>' +
      '<p class="section-sub">' + (locked ? '이 관문에서 고른 영상이에요.' : '첫 프레임과 같은 사람이 자연스럽게 움직이는지 보고 하나를 골라 주세요. 재생하면 모든 후보가 처음부터 같이 움직여요.') + '</p>' +
      '<div class="bg-bar"><span class="intro-ctrl"><button type="button" class="btn btn--primary" data-intro-play>▶ 모두 재생</button>' +
      '<button type="button" class="btn btn--ghost" data-intro-restart>처음부터</button></span>' +
      '<span class="bg-keys"><kbd>Space</kbd> 재생·멈춤' + (locked ? '' : ' · <kbd>1</kbd>~<kbd>' + Math.min(9, introCandidates().length) + '</kbd> 고르기') + '</span></div>' +
      '<div class="intro-grid" data-intro-grid></div></section>' +
      '<section class="gate-section"><details class="gate-more"><summary>움직임 지시와 설정</summary>' + facts([
        ['첫 프레임', (items.firstFrameSource || {}).mode === 'generated' ? '새로 만든 첫 프레임' : (items.firstFrameSource || {}).mode],
        ['모델', items.model],
        ['해상도', settings.resolution],
        ['길이', settings.duration ? settings.duration + '초' : ''],
        ['비율', settings.aspectRatio]
      ]) + '<pre class="answer-json">' + esc(settings.prompt || items.prompt || '') + '</pre>' +
      (items.hero && items.hero.url ? '<p class="section-sub">대표 이미지</p>' + image(items.hero, 'intro-hero') : '') + '</details></section>'
    );
  }
  function paintIntro() {
    if (state.kind !== 'intro') return;
    var grid = q('[data-intro-grid]');
    if (!grid) return;
    var locked = faceLocked();
    var cands = introCandidates();
    grid.style.setProperty('--intro-n', String(cands.length + 1));
    grid.innerHTML = '<figure class="intro-col intro-first"><p class="intro-cap"><b>첫 프레임</b></p>' + image(state.items.firstFrame) + '<figcaption class="section-sub">영상이 여기서 시작해요</figcaption></figure>' +
      cands.map(function (c, i) {
        var on = state.introPick === c.candidateId;
        var m = measured(c.probe);
        return '<figure class="intro-col' + (on ? ' is-picked' : '') + '"><p class="intro-cap">' + (locked ? '' : '<kbd>' + (i + 1) + '</kbd>') + '<b>영상 ' + (i + 1) + '</b>' +
          (m ? '<span class="badge-chip">' + esc(m) + '</span>' : '<span class="badge-chip is-bad">길이·해상도를 못 읽음</span>') + '</p>' +
          clipVideo(c.file, 'data-intro-video') + reviewLine(c.candidateId) +
          (locked ? (on ? '<span class="badge-chip is-good">고른 영상</span>' : '')
            : '<button type="button" class="btn ' + (on ? 'btn--primary' : 'btn--ghost') + '" data-intro-pick="' + esc(c.candidateId) + '" aria-pressed="' + on + '">' + (on ? '고른 영상' : '이 영상 고르기') + '</button>') + '</figure>';
      }).join('');
    watchClips(grid);
    var side = q('[data-side-extra]');
    var picked = introById(state.introPick);
    if (side) side.innerHTML = picked
      ? '<div class="plan-side"><p class="plan-side-title"><b>' + esc(introLabel(picked)) + '</b></p><dl class="facts"><dt>모델</dt><dd>' + esc(picked.model || '') + '</dd><dt>실측</dt><dd>' + esc(measured(picked.probe) || '읽지 못했어요') + '</dd></dl></div>'
      : '<p class="face-side-empty">영상을 고르면 여기에 요약이 보여요.</p>';
    var primary = q('[data-decide="SELECT"]');
    if (primary && !locked) {
      primary.textContent = picked ? ro(introLabel(picked)) + ' 확정' : '이 영상으로 확정';
      primary.disabled = Boolean(state.busy || !picked);
    }
  }
  function introPlay(restart) {
    var videos = qa('[data-intro-video]').filter(function (v) { return !v.hidden; });
    if (!videos.length) { setStatus('재생할 수 있는 영상이 없어요.', 'bad'); return; }
    var playing = videos.some(function (v) { return !v.paused; });
    if (playing && !restart) { videos.forEach(function (v) { v.pause(); }); }
    else {
      videos.forEach(function (v) { if (restart || v.ended) v.currentTime = 0; });
      videos.forEach(function (v) { var p = v.play(); if (p && p.catch) p.catch(function () { /* 재생 실패는 error 표시로 알린다 */ }); });
    }
    var btn = q('[data-intro-play]');
    if (btn) btn.textContent = playing && !restart ? '▶ 모두 재생' : 'Ⅱ 모두 멈춤';
  }
  function onIntroKey(event) {
    if (state.kind !== 'intro' || event.altKey || event.ctrlKey || event.metaKey) return;
    var tag = event.target && event.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || tag === 'BUTTON') return;
    if (event.key === ' ') { event.preventDefault(); introPlay(false); return; }
    var n = Number(event.key);
    var cands = introCandidates();
    if (!faceLocked() && n >= 1 && n <= cands.length) { event.preventDefault(); state.introPick = cands[n - 1].candidateId; paintIntro(); }
  }
  function buildIntro(decision) {
    var answer = { decision: decision };
    if (decision === 'SELECT') {
      if (!introById(state.introPick)) throw Error('영상 후보 하나를 골라 주세요.');
      answer.selections = [state.introPick];
    }
    return Object.assign(answer, details());
  }

  // ---------------------------------------------------------------- G5b
  // 챕터 × 동작 표(D-0111): 줄은 동작, 열은 챕터다. 칸을 누르면 그 칸의 영상을 크게 보고 쓰기·빼기를 정한다.
  function actionGrid() {
    var chapters = list(state.items.chapters).filter(function (c) { return c && c.chapterId; });
    var keys = [];
    var byKey = {};
    chapters.forEach(function (chapter) {
      list(chapter.actions).forEach(function (a) {
        if (!byKey[a.actionKey]) { byKey[a.actionKey] = a; keys.push(a.actionKey); }
      });
    });
    return { chapters: chapters, keys: keys, byKey: byKey };
  }
  function allActions() {
    var out = [];
    list(state.items.chapters).forEach(function (chapter) {
      list(chapter.actions).forEach(function (action) { out.push(action); });
    });
    return out;
  }
  function actionById(id) {
    return allActions().filter(function (a) { return a.actionId === id; })[0] || null;
  }
  function actionChapter(id) {
    return list(state.items.chapters).filter(function (c) {
      return list(c.actions).some(function (a) { return a.actionId === id; });
    })[0] || null;
  }
  function actionRestore() {
    if (state.actionRestored) return;
    state.actionRestored = true;
    var rec = (state.view && state.view.record) || {};
    var sel = state.items.selection || {};
    var picks = rec.picks || sel.picks || null;
    if (!picks && list(rec.selections).length) {
      picks = {};
      list(rec.selections).forEach(function (s) { var i = String(s).lastIndexOf(':'); if (i > 0) picks[s.slice(0, i)] = s.slice(i + 1); });
    }
    Object.keys(picks || {}).forEach(function (aid) { state.actionPick[aid] = picks[aid]; });
    list(rec.excluded || sel.excluded).forEach(function (aid) { state.actionPick[aid] = 'exclude'; });
    if (rec.decision && rec.decision !== 'REQUEST_CHANGES') allActions().forEach(function (a) { if (!state.actionPick[a.actionId]) state.actionPick[a.actionId] = 'exclude'; });
    list(rec.requestedChanges).forEach(function (c) { if (c && c.field) state.actionNote[c.field] = c.note || ''; });
    // 다시 만든 판이면 지난 판에서 정한 쓰기·빼기 중 그대로 쓴 칸을 미리 채운다(D-0115).
    var carried = state.items.carried;
    state.actionCarried = 0;
    if (!rec.decision && carried) {
      Object.keys(carried.picks || {}).forEach(function (aid) {
        if (actionById(aid) && !state.actionPick[aid]) { state.actionPick[aid] = carried.picks[aid]; state.actionCarried += 1; }
      });
      list(carried.excluded).forEach(function (aid) {
        if (actionById(aid) && !state.actionPick[aid]) { state.actionPick[aid] = 'exclude'; state.actionCarried += 1; }
      });
    }
  }
  function actionCounts() {
    var all = allActions();
    var n = { total: all.length, done: 0, keep: 0, out: 0, notes: 0, emptyChapters: [] };
    all.forEach(function (a) {
      var v = state.actionPick[a.actionId];
      if (v) n.done += 1;
      if (v === 'exclude') n.out += 1; else if (v) n.keep += 1;
      if (String(state.actionNote[a.actionId] || '').trim()) n.notes += 1;
    });
    list(state.items.chapters).forEach(function (c) {
      var acts = list(c.actions);
      if (acts.length && acts.every(function (a) { return state.actionPick[a.actionId] === 'exclude'; })) n.emptyChapters.push(c);
    });
    return n;
  }
  function renderActions(items) {
    actionRestore();
    var locked = faceLocked();
    var g = actionGrid();
    return (
      '<section class="gate-section action-board"><h2>동작 영상 ' + allActions().length + '칸</h2>' +
      '<p class="section-sub">' + (locked ? '칸마다 쓰기로 한 영상과 뺀 동작이에요.'
        : '줄은 동작, 열은 챕터예요. 칸을 누르면 영상을 크게 보고 쓸지 뺄지 정해요. 정하면 다음 칸으로 넘어가요. 챕터마다 하나 이상은 남겨야 해요.') + '</p>' +
      '<div class="bg-bar"><span class="blind-progress"><span data-action-count></span><span class="blind-meter" aria-hidden="true"><i data-action-meter></i></span></span>' +
      (locked ? '' : '<span class="intro-ctrl"><button type="button" class="btn btn--primary" data-action-next>남은 칸 열기</button><button type="button" class="btn btn--ghost" data-action-fill>남은 칸 첫 후보로 채우기</button></span>') + '<span class="action-undo" data-action-undo-box role="status"></span></div>' +
      '<div class="plan-scroll"><table class="plan-table action-table" data-action-table></table></div></section>' +
      '<div class="frame-zoom" data-action-box hidden></div>'
    );
  }
  function actionCell(a) {
    var v = state.actionPick[a.actionId] || '';
    var chapter = actionChapter(a.actionId) || {};
    var frame = a.mood === 'good' ? chapter.goodFrame : chapter.badFrame;
    var cands = list(a.candidates);
    var idx = -1;
    cands.forEach(function (c, i) { if (c.candidateId === v) idx = i; });
    var note = String(state.actionNote[a.actionId] || '').trim();
    var label = v === 'exclude' ? '뺌' : idx >= 0 ? (cands.length > 1 ? '후보 ' + (idx + 1) + ' 씀' : '씀') : '정하기';
    return '<button type="button" class="action-cell' + (v === 'exclude' ? ' is-out' : v ? ' is-keep' : '') + (state.actionOpen === a.actionId ? ' is-open' : '') + '" data-action-open="' + esc(a.actionId) + '" aria-label="' + esc(bgLabel(chapter) + ' ' + (a.title || a.actionKey) + ': ' + label) + '">' +
      (frame && frame.url ? '<img src="' + esc(frame.url) + '" alt="" loading="lazy">' : '<span class="bg-side-slot"></span>') +
      '<span class="action-cell-state">' + (v === 'exclude' ? '— 뺌' : v ? '✓ ' + label : '정하기') + '</span>' +
      (cands.length > 1 ? '<span class="action-cell-n">후보 ' + cands.length + '</span>' : '') +
      (a.reviewNote ? '<span class="action-cell-note is-new" title="' + esc('지난 요청: ' + a.reviewNote) + '">다시 만듦</span>' : '') +
      (note ? '<span class="action-cell-note" title="' + esc(note) + '">고칠 점</span>' : '') +
      (reviewItem(a.actionId + ':' + (cands[0] || {}).candidateId) && reviewItem(a.actionId + ':' + (cands[0] || {}).candidateId).verdict === 'CONCERN' ? '<span class="action-cell-note is-bad">걸리는 점</span>' : '') +
      '</button>';
  }
  function paintActions() {
    if (state.kind !== 'actions') return;
    var table = q('[data-action-table]');
    if (!table) return;
    var g = actionGrid();
    var n = actionCounts();
    table.innerHTML = '<colgroup><col class="action-label-col">' + g.chapters.map(function () { return '<col>'; }).join('') + '</colgroup>' +
      '<thead><tr><th scope="col" class="plan-corner">동작</th>' + g.chapters.map(function (c) {
        var acts = list(c.actions);
        var kept = acts.filter(function (a) { var v = state.actionPick[a.actionId]; return v && v !== 'exclude'; }).length;
        var empty = n.emptyChapters.indexOf(c) >= 0;
        return '<th scope="col" class="plan-col"><b>' + esc(bgLabel(c)) + '</b><span class="plan-col-sub' + (empty ? ' is-bad' : '') + '">' + (empty ? '모두 뺐어요 · 하나는 남겨 주세요' : '쓰는 동작 ' + kept + ' / ' + acts.length) + '</span>' +
          (faceLocked() ? '' : '<span class="action-col-acts"><button type="button" class="btn btn--ghost" data-action-col="' + esc(c.chapterId) + '|keep">모두 쓰기</button><button type="button" class="btn btn--ghost" data-action-col="' + esc(c.chapterId) + '|exclude">모두 빼기</button></span>') + '</th>';
      }).join('') + '</tr></thead><tbody>' +
      g.keys.map(function (key) {
        var head = g.byKey[key];
        return '<tr><th scope="row"><b class="action-title">' + esc(head.title || key) + '</b><span class="action-mood">' + (head.mood === 'good' ? '미소 출발' : '무표정 출발') + ' · ' + esc(head.duration) + '초</span></th>' +
          g.chapters.map(function (c) {
            var a = list(c.actions).filter(function (x) { return x.actionKey === key; })[0];
            return '<td>' + (a ? actionCell(a) : '<span class="plan-none">—</span>') + '</td>';
          }).join('') + '</tr>';
      }).join('') + '</tbody>';
    // 좁은 화면에서는 칸이 눌리지 않게 표를 옆으로 넘긴다.
    table.style.minWidth = (150 + g.chapters.length * 132) + 'px';
    var count = q('[data-action-count]');
    if (count) count.innerHTML = '<b>' + n.done + ' / ' + n.total + '</b> 칸 정했어요 · 씀 ' + n.keep + ' · 뺌 ' + n.out +
      (state.actionCarried ? ' · <span class="action-carried">지난 버전에서 ' + state.actionCarried + '칸 이어받음</span>' : '');
    var meter = q('[data-action-meter]');
    if (meter) meter.style.width = (n.total ? Math.round(n.done / n.total * 100) : 0) + '%';
    var nextBtn = q('[data-action-next]');
    if (nextBtn) nextBtn.hidden = n.done >= n.total;
    var fillBtn = q('[data-action-fill]');
    if (fillBtn) { fillBtn.hidden = n.done >= n.total; fillBtn.textContent = '남은 ' + (n.total - n.done) + '칸 첫 후보로 채우기'; }
    var undo = q('[data-action-undo-box]');
    if (undo) undo.innerHTML = state.actionUndo ? esc(state.actionUndo.label) + ' <button type="button" class="btn btn--ghost" data-action-undo>되돌리기</button>' : '';
    paintActionMeta();
    paintActionBox();
  }
  function paintActionMeta() {
    if (state.kind !== 'actions') return;
    var n = actionCounts();
    var locked = faceLocked();
    var side = q('[data-side-extra]');
    if (side) side.innerHTML = '<div class="bg-side"><p class="bg-side-title"><b>챕터별 쓰는 동작</b><span>' + n.done + ' / ' + n.total + '</span></p><ol class="bg-side-list">' +
      list(state.items.chapters).map(function (c) {
        var acts = list(c.actions);
        var kept = acts.filter(function (a) { var v = state.actionPick[a.actionId]; return v && v !== 'exclude'; });
        var left = acts.filter(function (a) { return !state.actionPick[a.actionId]; }).length;
        var empty = n.emptyChapters.indexOf(c) >= 0;
        return '<li><div class="bg-side-item' + (!left && !empty ? ' is-done' : '') + (empty ? ' is-fix' : '') + '">' +
          (c.goodFrame && c.goodFrame.url ? '<img src="' + esc(c.goodFrame.url) + '" alt="" loading="lazy">' : '<span class="bg-side-slot"></span>') +
          '<span><b>' + esc(bgLabel(c)) + '</b><span class="bg-side-what">' + (empty ? '모두 뺐어요. 하나는 남겨 주세요' : '씀 ' + kept.length + (left ? ' · 남은 칸 ' + left : ' · 다 정했어요')) + '</span></span></div></li>';
      }).join('') + '</ol></div>';
    if (locked) return;
    guardQuickApprove(n.done);
    var primary = q('[data-decide="SELECT"]');
    var left = n.total - n.done;
    if (primary) {
      primary.disabled = Boolean(state.busy || left || n.emptyChapters.length);
      primary.textContent = left ? '고른 영상으로 확정' : '동작 ' + n.keep + '개로 확정';
    }
    var change = q('[data-decide="REQUEST_CHANGES"]');
    if (change) {
      change.disabled = Boolean(state.busy || !n.notes);
      change.textContent = n.notes ? '수정 요청 · 동작 ' + n.notes + '개' : '수정 요청';
    }
    var hint = q('[data-side-hint]');
    if (hint) hint.textContent = n.emptyChapters.length
      ? n.emptyChapters.map(bgLabel).join(', ') + '에서 동작을 모두 뺐어요. 챕터마다 하나 이상은 남겨 주세요.'
      : left && state.actionCarried ? '지난 버전에서 정한 ' + state.actionCarried + '칸을 미리 채웠어요. 남은 ' + left + '칸(다시 만든 칸 포함)을 정하면 확정할 수 있어요.'
      : left ? left + '칸이 남았어요. 모두 정하면 확정할 수 있어요. 다시 만들 동작은 칸을 열어 고칠 점을 적어 주세요.'
      : n.notes ? '고칠 점을 적은 동작이 ' + n.notes + '개 있어요. 다시 만들려면 수정 요청을 눌러 주세요. 확정하면 적은 고칠 점은 보내지 않아요.'
      : '모두 정했어요. 확인하고 확정해 주세요.';
  }
  function paintActionBox() {
    var box = q('[data-action-box]');
    if (!box) return;
    var a = actionById(state.actionOpen);
    if (!a) { box.hidden = true; box.innerHTML = ''; return; }
    var chapter = actionChapter(a.actionId) || {};
    var frame = a.mood === 'good' ? chapter.goodFrame : chapter.badFrame;
    var v = state.actionPick[a.actionId] || '';
    var locked = faceLocked();
    var cands = list(a.candidates);
    box.hidden = false;
    box.innerHTML = '<div class="frame-zoom-inner action-inner" role="dialog" aria-modal="true" aria-label="' + esc(bgLabel(chapter) + ' ' + (a.title || '')) + '">' +
      '<div class="frame-zoom-head"><span class="bg-ch">' + esc(bgLabel(chapter)) + '</span><b>' + esc(a.title || a.actionKey) + '</b>' +
      '<span class="bg-keys">' + (locked ? '' : (cands.length > 1 ? '<kbd>1</kbd>~<kbd>' + Math.min(9, cands.length) + '</kbd>' : '<kbd>1</kbd>') + ' 쓰기 · <kbd>X</kbd> 빼기 · ') + NAV_KEYS + ' 칸 · <kbd>Esc</kbd> 닫기</span>' +
      '<button type="button" class="btn btn--ghost" data-action-close>닫기</button></div>' +
      // '이럴 때' 규칙 원문은 모델용이라 서버가 사람용으로 줄인 글(whenText)만 보인다(QA v5 C-07).
      '<p class="section-sub">' + esc(a.description || '') + ' · ' + (a.mood === 'good' ? '미소 출발' : '무표정 출발') + ' · ' + esc(a.duration) + '초</p>' +
      (a.whenText ? '<p class="section-sub">' + esc(a.whenText) + '</p>' : '') +
      (a.reviewNote ? '<p class="qa-note is-ask"><b>다시 만든 동작</b> 지난 요청: ' + esc(a.reviewNote) + '</p>' : '') +
      '<div class="frame-zoom-pair">' + (frame && frame.url ? '<figure>' + image(frame) + '<figcaption>첫 프레임</figcaption></figure>' : '') +
      cands.map(function (c, i) {
        var on = v === c.candidateId;
        return '<figure class="' + (on ? 'is-picked' : '') + '">' + clipVideo(c.file, 'autoplay data-action-video') +
          '<figcaption>' + (cands.length > 1 ? '후보 ' + (i + 1) : '영상') + (c.reusedFrom ? ' · ' + esc(c.reusedFrom) + '에서 재사용' : '') + '</figcaption>' + reviewLine(a.actionId + ':' + c.candidateId) +
          (locked ? '' : '<button type="button" class="btn ' + (on ? 'btn--primary' : 'btn--ghost') + '" data-action-pick="' + esc(a.actionId) + '|' + esc(c.candidateId) + '" aria-pressed="' + on + '">' + (on ? '쓰기로 했어요' : '이 영상 쓰기') + '</button>') + '</figure>';
      }).join('') + '</div>' +
      (locked
        ? (state.actionNote[a.actionId] ? '<p class="bg-custom-text">고칠 점: ' + esc(state.actionNote[a.actionId]) + '</p>' : '')
        : '<div class="frame-zoom-foot"><button type="button" class="btn ' + (v === 'exclude' ? 'btn--primary' : 'btn--ghost') + '" data-action-pick="' + esc(a.actionId) + '|exclude" aria-pressed="' + (v === 'exclude') + '">' + (v === 'exclude' ? '뺐어요' : '이 동작 빼기') + '</button>' +
          '<textarea data-action-note="' + esc(a.actionId) + '" placeholder="다시 만들 때만: 무엇을 고칠지">' + esc(state.actionNote[a.actionId] || '') + '</textarea>' +
          '<button type="button" class="btn btn--ghost" data-action-step="1">다음 칸 →</button></div>') +
      '</div>';
    watchClips(box);
    var close = q('[data-action-close]', box);
    if (close && !box.contains(document.activeElement)) close.focus();
  }
  function actionOrder() {
    var g = actionGrid();
    var out = [];
    g.chapters.forEach(function (c) {
      g.keys.forEach(function (key) {
        var a = list(c.actions).filter(function (x) { return x.actionKey === key; })[0];
        if (a) out.push(a.actionId);
      });
    });
    return out;
  }
  function actionStep(step) {
    var order = actionOrder();
    var at = order.indexOf(state.actionOpen);
    state.actionOpen = order[(at + step + order.length) % order.length];
    paintActions();
  }
  // 여러 칸을 한 번에 바꾸기 전 상태를 남겨 되돌릴 수 있게 한다(D-0129).
  function bulkActions(label, change) {
    if (faceLocked()) return;
    var before = Object.assign({}, state.actionPick);
    var changed = change();
    if (!changed) { setStatus('바꿀 칸이 없어요.'); return; }
    state.actionUndo = { picks: before, label: label.replace('N', changed) };
    paintActions();
  }
  function pickAction(aid, value) {
    if (faceLocked() || !actionById(aid)) return;
    state.actionUndo = null;
    state.actionPick[aid] = value;
    setStatus('');
    // 정하면 아직 안 정한 다음 칸으로 넘어간다. 다 정했으면 그 칸에 머문다.
    var order = actionOrder();
    var at = order.indexOf(aid);
    var next = aid;
    for (var i = 1; i < order.length; i += 1) {
      var id = order[(at + i) % order.length];
      if (!state.actionPick[id]) { next = id; break; }
    }
    state.actionOpen = next;
    paintActions();
  }
  function onActionKey(event) {
    if (state.kind !== 'actions' || !state.actionOpen) return;
    if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); state.actionOpen = ''; paintActions(); return; }
    var tag = event.target && event.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    var stepA = navStep(String(event.key || '').toLowerCase());
    if (stepA) { event.preventDefault(); actionStep(stepA); return; }
    if (faceLocked()) return;
    var a = actionById(state.actionOpen);
    var cands = list(a && a.candidates);
    var n = Number(event.key);
    if (n >= 1 && n <= cands.length) { event.preventDefault(); pickAction(a.actionId, cands[n - 1].candidateId); }
    else if (String(event.key).toLowerCase() === 'x') { event.preventDefault(); pickAction(a.actionId, 'exclude'); }
  }
  function buildActions(decision) {
    var answer = { decision: decision };
    if (decision === 'SELECT') {
      var picks = {};
      var excluded = [];
      allActions().forEach(function (action) {
        var v = state.actionPick[action.actionId];
        if (!v) throw Error((action.title || action.actionId) + ': 영상 또는 빼기를 골라 주세요.');
        if (v === 'exclude') excluded.push(action.actionId);
        else picks[action.actionId] = v;
      });
      var n = actionCounts();
      if (n.emptyChapters.length) throw Error(n.emptyChapters.map(bgLabel).join(', ') + '에서 동작을 하나 이상 남겨 주세요.');
      answer.picks = picks;
      answer.excluded = excluded;
    }
    if (decision === 'REQUEST_CHANGES') {
      var changes = [];
      allActions().forEach(function (action) {
        var note = String(state.actionNote[action.actionId] || '').trim();
        if (note) changes.push({ field: action.actionId, note: note });
      });
      if (!changes.length) throw Error('다시 만들 동작의 칸을 열고 고칠 점을 적어 주세요.');
      answer.requestedChanges = changes;
      // 이미 정한 쓰기·빼기도 함께 보내 새 판에서 다시 고르지 않게 한다(D-0115).
      var draftPicks = {};
      var draftOut = [];
      allActions().forEach(function (action) {
        var v = state.actionPick[action.actionId];
        if (v === 'exclude') draftOut.push(action.actionId);
        else if (v) draftPicks[action.actionId] = v;
      });
      answer.picks = draftPicks;
      answer.excluded = draftOut;
    }
    return Object.assign(answer, details());
  }

  // ---------------------------------------------------------------- G6
  // 시연 상황 이름(trait_ledger.demoSituation). 코드 값은 화면에 보이지 않는다.
  var SITUATION_KO = { TEASE: '장난·놀림', WORRY: '고민 털어놓기', CRITICISM: '비판', UNKNOWN: '모르는 질문', PRIVATE: '사생활 질문' };
  var INFERRED_LINE = /^원문 경향 없음 · ([A-Z_]+) \(INFERRED, 참고 ([^)]*)\): ([\s\S]*?) → ([\s\S]*)$/;
  function charName() {
    var s = (state.character && state.character.summary) || {};
    return s.name && s.name !== state.characterId ? s.name : '캐릭터';
  }
  // 대화해 보기로 보낼 수 있는지는 서버 판정(약속 3의 chatReady)만 따른다. 값이 없으면 보내지 않는다.
  function chatReady() {
    var c = state.character || {};
    return c.chatReady === true || (c.summary || {}).chatReady === true;
  }
  function chatHref() {
    return '/studio/chat.html#c/' + encodeURIComponent(state.characterId);
  }
  // 서버가 inferredTraits(약속 1)를 주면 그대로, 없으면 특질 시트 미정 줄에서 같은 모양으로 읽는다.
  function inferredTraits(items) {
    if (Array.isArray(items.inferredTraits)) return items.inferredTraits;
    return list((items.traitSheet || {}).unresolved).map(function (line) {
      var m = INFERRED_LINE.exec(String(line || ''));
      return m ? { situation: m[1], trigger: m[3], behavior: m[4], refs: m[2] ? [{ msgId: m[2] }] : [] } : null;
    }).filter(Boolean);
  }
  function sampleTranscripts(items) {
    var samples = list(items.samples).filter(function (s) { return s && list(s.turns).length; });
    if (!samples.length) return '';
    var who = charName();
    var chat = state.characterId ? chatHref() : '';
    return '<section class="gate-section"><div class="chat-samples-head"><h2>대화 표본 ' + samples.length + '개 장면</h2>' +
      (chat ? '<a class="btn btn--ghost" href="' + esc(chat) + '" target="_blank" rel="noopener">대화해 보기</a>' : '') + '</div>' +
      '<p class="section-sub">장면마다 이 프롬프트로 한 번씩 대화해 본 결과예요.' + (isRecord() ? '' : ' 이 인물답게 답하는지 읽어 보고 승인해 주세요.') + '</p>' +
      '<div class="chat-samples">' + samples.map(function (s) {
        return '<article class="chat-sample"><h3>' + esc(s.title || '장면') + '<span>' + list(s.turns).length + '턴</span></h3><div class="chat-log">' +
          list(s.turns).map(function (t) {
            return (t.user ? '<p class="bubble is-user"><span>사용자</span>' + esc(t.user) + '</p>' : '') +
              (t.reply ? '<p class="bubble is-char"><span>' + esc(who) + '</span>' + esc(t.reply) + '</p>' : '<p class="bubble is-char is-none"><span>' + esc(who) + '</span>(답이 없어요)</p>');
          }).join('') + '</div></article>';
      }).join('') + '</div></section>';
  }
  function inferredCards(items) {
    var traits = inferredTraits(items);
    if (!traits.length) return '';
    return '<section class="gate-section"><h2>원문에 직접 근거가 없어 추론한 특질 ' + traits.length + '개</h2>' +
      '<p class="section-sub">원문에서 이 상황의 말버릇을 찾지 못해 공장이 다른 원문을 보고 짐작했어요. 이 인물답지 않으면 아래 수정 요청에 적어 주세요.</p>' +
      '<ul class="trait-cards">' + traits.map(function (t) {
        var refs = list(t.refs).filter(function (r) { return r && r.quote; });
        var tip = list(t.refs).map(function (r) { return r && r.msgId; }).filter(Boolean).join(', ');
        return '<li class="trait-card"' + (tip && !refs.length ? ' title="' + esc('참고한 원문 위치 ' + tip) + '"' : '') + '>' +
          '<div class="trait-top"><b>' + esc(t.situationKo || SITUATION_KO[t.situation] || '그 밖의 상황') + '</b><span class="badge-chip is-warn">추론</span></div>' +
          (t.trigger ? '<p class="trait-when">' + esc(t.trigger) + '</p>' : '') +
          '<p class="trait-do">' + esc(t.behavior || '') + '</p>' +
          (refs.length ? '<div class="trait-refs"><span class="fact-label">참고한 원문</span>' + refs.map(function (r) {
            return '<blockquote' + (r.msgId ? ' title="' + esc('원문 위치 ' + r.msgId) + '"' : '') + '>' + esc(r.quote) + '</blockquote>';
          }).join('') + '</div>' : '') + '</li>';
      }).join('') + '</ul></section>';
  }
  function renderPrompts(items) {
    var long = items.long || {};
    var short = items.short || {};
    var record = isRecord();
    // 긴·짧은 프롬프트 글이 같으면 하나만 보여 주고, 어느 쪽을 고칠지 묻지 않는다.
    var same = Boolean(items.samePrompt || (long.text && long.text === short.text));
    var probes = list(items.probes)
      .map(function (probe) {
        var judge = probe.judge || {};
        return (
          '<div class="probe"><p class="probe-q">' + esc(probe.sentence) + '</p>' +
          '<div class="probe-a"><div><b>긴 프롬프트</b>' + esc(probe.longResponse) + '</div>' +
          '<div><b>짧은 프롬프트</b>' + esc(probe.shortResponse) + '</div></div>' +
          '<p class="qa-note">검토 모델(참고): ' + esc(PICK_KO[judge.pick] || judge.pick || '판정 없음') + ' · ' +
          esc(judge.reasons || '') + '</p></div>'
        );
      })
      .join('');
    var sheet = items.traitSheet;
    var samples = sampleTranscripts(items);
    var noSamples = !probes && !samples
      ? '<section class="gate-section"><div class="chat-samples-head"><h2>대화 표본</h2>' +
        (chatReady() ? '<a class="btn btn--ghost" href="' + esc(chatHref()) + '" target="_blank" rel="noopener">대화해 보기</a>' : '') + '</div>' +
        '<p class="section-sub">' + (chatReady()
          ? '아직 대화 표본이 없어요. 대화해 보기에서 직접 말을 걸어 볼 수 있어요.'
          : '아직 대화 표본이 없어요. 아래 프롬프트 원문을 열어 읽어 볼 수 있어요.') + '</p></section>'
      : '';
    var doc = function (title, p, key) {
      return '<div class="doc"><h3>' + title + ' <span class="badge-chip">' + esc(num(p.chars)) + '자</span>' + reviewLine(key) +
        '</h3><pre>' + esc(p.text || '') + '</pre></div>';
    };
    return (
      samples + inferredCards(items) +
      (probes
        ? '<section class="gate-section"><h2>' + (samples ? '긴·짧은 프롬프트 비교' : '표본 응답') + '</h2>' +
          '<p class="section-sub">검토 모델의 판정은 참고용이에요. 승인은 사람이 해요.</p>' +
          probes + '</section>'
        : noSamples) +
      '<section class="gate-section"><details class="gate-more"><summary>' +
      (same ? '프롬프트 원문 · ' + esc(num(long.chars)) + '자'
        : '프롬프트 원문 · 긴 ' + esc(num(long.chars)) + '자 · 짧은 ' + esc(num(short.chars)) + '자' + (items.shortAdopted ? ' · 짧은 프롬프트 채택' : '')) +
      '</summary><p class="section-sub">구성: ' + esc(joinList(items.sections, ', ')) + '</p>' +
      '<div class="doc-block' + (same ? ' is-single' : '') + '">' +
      (same ? doc('프롬프트', long, 'long') : doc('긴 프롬프트', long, 'long') + doc('짧은 프롬프트', short, 'short')) +
      '</div></details></section>' +
      (sheet
        ? '<section class="gate-section"><h2>특질 시트</h2>' +
          (sheet.card
            ? facts([
                ['태도', sheet.card.stance],
                ['판단 기준', list(sheet.card.judgmentPriorities)
                  .map(function (p) { return p.dilemma + ' → ' + p.choice; })
                  .join(' / ')],
                ['말버릇', (sheet.card.dialogueHabits || {}).lexicon]
              ])
            : '') +
          '<p class="section-sub"><a href="' + esc(sheet.url) +
          '" target="_blank" rel="noopener">특질 시트 원문 열기</a></p></section>'
        : '') +
      (record ? '' : '<section class="gate-section"><h2>수정 요청 (선택)</h2>' +
        (same ? '' : '<div class="field-list"><div class="field"><span>어느 프롬프트</span>' +
          '<select data-prompt-scope><option value="long">긴 프롬프트</option>' +
          '<option value="short">짧은 프롬프트</option></select></div></div>') +
        '<textarea data-prompt-note placeholder="예: 첫 인사를 더 짧게, 감탄사 줄이기"></textarea>' +
        '</section>')
    );
  }

  function buildPrompts(decision) {
    var answer = { decision: decision };
    if (decision === 'REQUEST_CHANGES') {
      var note = q('[data-prompt-note]').value.trim();
      if (!note) { focusField(q('[data-prompt-note]')); throw Error('아래 수정 요청 칸에 고칠 점을 적어 주세요.'); }
      var scope = q('[data-prompt-scope]');
      answer.requestedChanges = [{ field: scope ? scope.value : 'long', note: note }];
    }
    return Object.assign(answer, details());
  }

  // ---------------------------------------------------------------- G7a
  function validationText(value) {
    if (!value || typeof value !== 'object') return '';
    var parts = [];
    if (value.baseConversations != null) parts.push('기반 ' + value.baseConversations + '대화');
    if (value.augmentedShare != null) {
      parts.push('보강 ' + Math.round(Number(value.augmentedShare) * 1000) / 10 + '%');
    }
    return parts.join(' · ');
  }

  // 받은 편지함식 판정(D-0112): 묶음 탭 아래 왼쪽은 대화 목록, 오른쪽은 읽기 창이다.
  // 숫자 키 1·2·3으로 쓰기·고쳐 쓰기·버리기를 고르면 다음 대화로 넘어간다. 묶음마다 따로 보낸다.
  var VERDICT_KEYS = ['ADOPT', 'FIX', 'REJECT'];
  function sampleClusters() {
    // G7 학습 데이터는 무작위 표본 한 묶음을 같은 받은 편지함으로 본다.
    if (state.kind === 'dataset') return [{ clusterId: '표본', samples: list(state.items.samples), single: true }];
    return list(state.items.clusters).filter(function (c) { return c && c.clusterId; });
  }
  function sampleCluster(id) {
    return sampleClusters().filter(function (c) { return c.clusterId === id; })[0] || null;
  }
  function clusterName(c) {
    return '묶음 ' + (sampleClusters().indexOf(c) + 1);
  }
  function clusterLabel(c) {
    var plan = list((state.items.plan || {}).clusters).filter(function (x) { return x.clusterId === c.clusterId; })[0];
    return (plan && plan.label) || c.clusterId;
  }
  // 이미 보낸 묶음의 판정은 결정 기록에서 읽는다.
  function sampleSent(c) {
    if (state.kind === 'dataset') return Boolean(faceLocked());
    return Boolean(c.reviewed);
  }
  function sampleRestore() {
    if (state.sampleRestored) return;
    state.sampleRestored = true;
    // 이미 보낸 판정은 서버가 묶음마다 sentVerdicts·sentNotes로 준다(G7은 항목 맨 위에 있다).
    var sources = state.kind === 'dataset' ? [state.items] : sampleClusters();
    sources.forEach(function (c) {
      var verdicts = c.sentVerdicts || {};
      var notes = c.sentNotes || {};
      Object.keys(verdicts).forEach(function (id) { state.sampleVerdict[id] = verdicts[id]; });
      Object.keys(notes).forEach(function (id) { state.sampleNote[id] = notes[id]; });
    });
    if (state.kind === 'dataset' && !Object.keys(state.items.sentVerdicts || {}).length) {
      // 표본은 기본이 쓰기다. 고칠 대화만 바꾸면 된다.
      list(state.items.samples).forEach(function (x) { if (!state.sampleVerdict[x.conversationId]) state.sampleVerdict[x.conversationId] = 'ADOPT'; });
    }
    var open = sampleClusters().filter(function (c) { return !sampleSent(c); })[0] || sampleClusters()[0];
    state.sampleTab = open ? open.clusterId : '';
    var first = open && list(open.samples)[0];
    state.sampleOpen = first ? first.conversationId : '';
  }
  function sampleLeft(c) {
    return list(c.samples).filter(function (x) {
      var v = state.sampleVerdict[x.conversationId];
      return !v || (v === 'FIX' && !String(state.sampleNote[x.conversationId] || '').trim());
    });
  }
  function renderSamples(items) {
    sampleRestore();
    var plan = items.plan || {};
    return (
      '<section class="gate-section sample-board"><h2>묶음별 샘플 대화</h2>' +
      '<p class="section-sub">묶음마다 대화를 읽고 쓰기·고쳐 쓰기·버리기를 정해 주세요. 정하면 다음 대화로 넘어가요. 묶음의 대화를 모두 정하면 그 묶음을 보낼 수 있어요.</p>' +
      '<div class="pose-tabs" role="tablist" aria-label="묶음" data-sample-tabs></div>' +
      '<details class="gate-more sample-guide" data-sample-guide><summary>이 묶음의 작성 지침</summary><div data-sample-guide-body></div></details>' +
      '<div class="sample-inbox"><ol class="sample-list" data-sample-list aria-label="대화 목록"></ol><div class="sample-read" data-sample-read></div></div></section>' +
      '<section class="gate-section"><details class="gate-more"><summary>계획과 지침 수정 요청</summary>' +
      facts([
        ['목표 대화', plan.targetTrainConversations],
        ['묶음 비율', list(plan.clusters).map(function (c) { return (c.label || c.clusterId) + ' ' + Math.round(Number(c.share) * 100) + '%'; }).join(' / ')],
        ['검증', validationText(plan.validation)]
      ]) +
      '<p class="section-sub">지금 묶음의 작성 지침을 고쳐 다시 만들려면 아래에 적고 작성 지침 수정 요청을 눌러 주세요.</p>' +
      '<textarea data-cluster-note placeholder="이 묶음의 작성 지침을 어떻게 고칠지 적어 주세요"></textarea></details></section>'
    );
  }
  function paintSamples() {
    if (state.kind !== 'samples' && state.kind !== 'dataset') return;
    var tabs = q('[data-sample-tabs]');
    if (!tabs) return;
    var cluster = sampleCluster(state.sampleTab) || sampleClusters()[0];
    if (!cluster) return;
    var sent = sampleSent(cluster);
    var locked = faceLocked() || sent;
    tabs.innerHTML = sampleClusters().map(function (c) {
      var on = c.clusterId === cluster.clusterId;
      var done = sampleSent(c);
      var left = sampleLeft(c).length;
      return '<button type="button" role="tab" class="pose-tab' + (done ? ' is-done' : '') + '" data-sample-tab="' + esc(c.clusterId) + '" aria-selected="' + on + '" title="' + esc(clusterLabel(c)) + '">' +
        '<span class="pose-tab-mark" aria-hidden="true">' + (done ? '✓' : '') + '</span><b>' + esc(clusterName(c)) + '</b>' +
        '<span class="pose-tab-sub">' + esc(clusterLabel(c)) + '</span><span class="pose-tab-sub sample-tab-state">' + (done ? '보냈어요' : left ? '남은 대화 ' + left : '보낼 수 있어요') + '</span></button>';
    }).join('') + '<span class="pose-tabs-count">' + sampleClusters().filter(sampleSent).length + ' / ' + sampleClusters().length + ' 묶음 보냈어요</span>';
    tabs.hidden = Boolean(cluster.single);
    var h = cluster.handoff || {};
    var guide = q('[data-sample-guide]');
    if (guide) guide.hidden = !cluster.handoff;
    if (cluster.handoff) q('[data-sample-guide-body]').innerHTML = '<p class="section-sub">' + esc(clusterLabel(cluster)) + '</p>' +
      '<table class="gate-table"><thead><tr><th>상황</th><th>먼저 보는 것</th><th>고르는 행동</th><th>말투</th></tr></thead><tbody>' +
      list(h.behaviorTable).map(function (row) {
        return '<tr><td>' + esc(row.situation) + '</td><td>' + esc(row.attention) + '</td><td>' + esc(row.choice) + '</td><td>' + esc(row.voice) + '</td></tr>';
      }).join('') + '</tbody></table>' +
      facts([['말투 예시', joinList(h.voiceExamples, ' / ')], ['하지 않을 것', joinList(h.forbidden, ' / ')], ['메모', h.notes]]);
    var samples = list(cluster.samples);
    if (!samples.some(function (x) { return x.conversationId === state.sampleOpen; })) state.sampleOpen = samples[0] ? samples[0].conversationId : '';
    if (state.sampleOpen) state.sampleSeen[state.sampleOpen] = true;
    q('[data-sample-list]').innerHTML = samples.map(function (x, i) {
      var v = state.sampleVerdict[x.conversationId] || '';
      var firstUser = list(x.messages).filter(function (m) { return m.role === 'user'; })[0];
      var on = x.conversationId === state.sampleOpen;
      return '<li><button type="button" class="sample-row' + (on ? ' is-open' : '') + (v ? ' is-' + v.toLowerCase() : '') + '" data-sample-open="' + esc(x.conversationId) + '" aria-current="' + (on ? 'true' : 'false') + '">' +
        '<span class="sample-row-top"><b>대화 ' + (i + 1) + '</b><span class="sample-chip">' + (v ? esc(VERDICT_KO[v] || v) + (state.kind === 'dataset' && v === 'ADOPT' && !state.sampleSeen[x.conversationId] ? ' · 기본' : '') : '아직') + '</span></span>' +
        '<span class="sample-row-text">' + esc(firstUser ? firstUser.content : '') + '</span>' +
        (v === 'FIX' && !String(state.sampleNote[x.conversationId] || '').trim() ? '<span class="sample-row-warn">고칠 점을 적어 주세요</span>' : '') + '</button></li>';
    }).join('');
    var open = samples.filter(function (x) { return x.conversationId === state.sampleOpen; })[0];
    var at = samples.indexOf(open);
    var read = q('[data-sample-read]');
    if (!open) { read.innerHTML = '<p class="empty">대화가 없어요.</p>'; }
    else {
      var v = state.sampleVerdict[open.conversationId] || '';
      read.innerHTML = '<div class="sample-read-head"><b>대화 ' + (at + 1) + ' / ' + samples.length + '</b>' + reviewLine(open.conversationId) +
        '<span class="bg-keys">' + (locked ? '' : '<kbd>1</kbd> 쓰기 · <kbd>2</kbd> 고쳐 쓰기 · <kbd>3</kbd> 버리기 · ') + NAV_KEYS + '</span></div>' +
        '<div class="sample-chat">' + list(open.messages).map(function (m) {
          return '<p class="bubble ' + (m.role === 'assistant' ? 'is-char' : 'is-user') + '"><span>' + (m.role === 'assistant' ? '캐릭터' : '사용자') + '</span>' + esc(m.content) + '</p>';
        }).join('') + '</div>' +
        (open.system ? '<details class="card-tech"><summary>상황 설정(프롬프트) 보기</summary>' + esc(open.system) + '</details>' : '') +
        (locked
          ? '<p class="frame-verdict-ro">' + esc(VERDICT_KO[v] || '판정 없음') + '</p>' + (state.sampleNote[open.conversationId] ? '<p class="bg-custom-text">' + esc(state.sampleNote[open.conversationId]) + '</p>' : '')
          : '<div class="seg frame-seg sample-seg" role="group" aria-label="판정">' + VERDICT_KEYS.map(function (k, i) {
              return '<button type="button" data-sample-verdict="' + esc(open.conversationId) + '|' + k + '" aria-pressed="' + (v === k) + '">' + esc(VERDICT_KO[k]) + '<kbd>' + (i + 1) + '</kbd></button>';
            }).join('') + '</div>' +
            '<textarea data-sample-note="' + esc(open.conversationId) + '"' + (v === 'FIX' ? '' : ' hidden') + ' placeholder="어디를 어떻게 고칠지 적어 주세요. 예: 두 번째 답이 첫 답을 그대로 반복해요">' + esc(state.sampleNote[open.conversationId] || '') + '</textarea>');
    }
    paintSampleMeta();
  }
  function paintSampleMeta() {
    if (state.kind === 'dataset') { paintDatasetMeta(); return; }
    if (state.kind !== 'samples') return;
    var cluster = sampleCluster(state.sampleTab);
    if (!cluster) return;
    var sent = sampleSent(cluster);
    var left = sampleLeft(cluster);
    var samples = list(cluster.samples);
    var count = { ADOPT: 0, FIX: 0, REJECT: 0 };
    samples.forEach(function (x) { var v = state.sampleVerdict[x.conversationId]; if (v) count[v] += 1; });
    var side = q('[data-side-extra]');
    if (side) side.innerHTML = '<div class="bg-side"><p class="bg-side-title"><b>' + esc(clusterName(cluster)) + '</b><span>' + (samples.length - left.length) + ' / ' + samples.length + '</span></p>' +
      '<p class="section-sub">' + esc(clusterLabel(cluster)) + '</p>' +
      '<dl class="facts"><dt>쓰기</dt><dd>' + count.ADOPT + '</dd><dt>고쳐 쓰기</dt><dd>' + count.FIX + '</dd><dt>버리기</dt><dd>' + count.REJECT + '</dd></dl></div>';
    if (faceLocked()) return;
    var primary = q('[data-decide="SELECT"]');
    if (primary) {
      primary.disabled = Boolean(state.busy || sent || left.length);
      primary.textContent = sent ? clusterName(cluster) + '은 보냈어요' : clusterName(cluster) + ' 판정 보내기';
    }
    var change = q('[data-decide="REQUEST_CHANGES"]');
    if (change) change.disabled = Boolean(state.busy || sent);
    var hint = q('[data-side-hint]');
    if (hint) hint.textContent = sent ? '이 묶음은 보냈어요. 남은 묶음 탭을 골라 주세요.'
      : left.length ? '대화 ' + left.length + '개가 남았어요. 모두 정하면 이 묶음을 보낼 수 있어요. 고쳐 쓰기는 고칠 점을 적어야 해요.'
      : '이 묶음을 모두 정했어요. 보내면 다음 묶음으로 넘어가요.';
  }
  function sampleMove(step) {
    var cluster = sampleCluster(state.sampleTab);
    var samples = list(cluster && cluster.samples);
    if (!samples.length) return;
    var at = -1;
    samples.forEach(function (x, i) { if (x.conversationId === state.sampleOpen) at = i; });
    state.sampleOpen = samples[(at + step + samples.length) % samples.length].conversationId;
    paintSamples();
  }
  function setSampleVerdict(id, v) {
    var cluster = sampleCluster(state.sampleTab);
    if (faceLocked() || !cluster || sampleSent(cluster)) return;
    state.sampleVerdict[id] = v;
    setStatus('');
    if (v !== 'FIX') {
      // 정하면 아직 안 정한 다음 대화로 넘어간다.
      var next = sampleLeft(cluster)[0];
      if (next) state.sampleOpen = next.conversationId;
    }
    paintSamples();
    if (v === 'FIX') {
      var note = q('[data-sample-note="' + id + '"]');
      if (note) note.focus();
    }
  }
  function onSampleKey(event) {
    if ((state.kind !== 'samples' && state.kind !== 'dataset') || event.altKey || event.ctrlKey || event.metaKey) return;
    var tag = event.target && event.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    var key = String(event.key || '').toLowerCase();
    if (navStep(key)) { event.preventDefault(); sampleMove(navStep(key)); return; }
    var n = Number(key);
    if (n >= 1 && n <= 3 && state.sampleOpen) { event.preventDefault(); setSampleVerdict(state.sampleOpen, VERDICT_KEYS[n - 1]); }
  }
  function buildSamples(decision) {
    var cluster = sampleCluster(state.sampleTab);
    if (!cluster) throw Error('묶음을 골라 주세요.');
    if (sampleSent(cluster)) throw Error('이 묶음은 이미 보냈어요. 남은 묶음을 골라 주세요.');
    var verdicts = {};
    var notes = {};
    if (decision === 'SELECT') {
      list(cluster.samples).forEach(function (x, i) {
        var v = state.sampleVerdict[x.conversationId];
        if (!v) throw Error('대화 ' + (i + 1) + '의 판정을 골라 주세요.');
        verdicts[x.conversationId] = v;
        var note = String(state.sampleNote[x.conversationId] || '').trim();
        if (v === 'FIX') {
          if (!note) throw Error('대화 ' + (i + 1) + '에서 고칠 점을 적어 주세요.');
          notes[x.conversationId] = note;
        }
      });
    } else {
      list(cluster.samples).forEach(function (x) { verdicts[x.conversationId] = state.sampleVerdict[x.conversationId] || 'ADOPT'; });
    }
    var answer = { decision: decision, cluster: cluster.clusterId, verdicts: verdicts, notes: notes };
    if (decision === 'REQUEST_CHANGES') {
      var box = q('[data-cluster-note]');
      var clusterNote = box ? box.value.trim() : '';
      if (!clusterNote) {
        var d = box && box.closest('details');
        if (d) d.open = true;
        if (box) box.focus();
        throw Error('작성 지침에서 고칠 점을 적어 주세요.');
      }
      answer.reasons = details().reasons || clusterNote;
    }
    return Object.assign(answer, details());
  }

  // ---------------------------------------------------------------- G7
  // 요약 먼저(D-0113): 검사 숫자와 묶음별 분량을 위에 두고, 무작위 표본은 G7a와 같은 받은 편지함으로 본다.
  function renderDataset(items) {
    sampleRestore();
    var dataset = items.dataset || {};
    var counts = dataset.clusterCounts || {};
    var keys = Object.keys(counts);
    var total = { conversations: 0, replies: 0, supervisedTokens: 0 };
    keys.forEach(function (k) { var r = counts[k] || {}; Object.keys(total).forEach(function (f) { total[f] += Number(r[f] || 0); }); });
    var most = Math.max.apply(null, [1].concat(keys.map(function (k) { return Number((counts[k] || {}).conversations || 0); })));
    // 학습 토큰을 세지 않은 데이터셋은 0 대신 빈칸 표시(—)로 보인다.
    var hasTokens = keys.some(function (k) { return (counts[k] || {}).supervisedTokens != null; });
    var num = function (v) { return v == null || v === '' ? '—' : Number(v).toLocaleString('ko-KR'); };
    var blocking = Array.isArray(dataset.blockingFailures) ? dataset.blockingFailures.length : Number(dataset.blockingFailures || 0);
    var warnCount = Array.isArray(dataset.warnings) ? dataset.warnings.length : Number(dataset.warnings || 0);
    // 첫 메모는 위 숫자와 같은 요약이라 빼고, 검사 보고서의 경고 문장만 보인다.
    var warnings = list(items.notes).slice(1);
    var kpi = function (label, value, tone) {
      return '<div class="kpi' + (tone ? ' is-' + tone : '') + '"><span>' + esc(label) + '</span><b>' + esc(value) + '</b></div>';
    };
    return (
      '<section class="gate-section dataset-board"><h2>학습 데이터 요약</h2>' +
      '<div class="kpis">' + kpi('대화', total.conversations.toLocaleString('ko-KR')) + kpi('답변', total.replies.toLocaleString('ko-KR')) +
      kpi('학습 토큰', hasTokens ? total.supervisedTokens.toLocaleString('ko-KR') : '—') +
      kpi('막는 문제', blocking ? blocking + '건' : '없음', blocking ? 'bad' : 'good') +
      kpi('경고', warnCount ? warnCount + '건' : '없음', warnCount ? 'warn' : '') + '</div>' +
      (warnings.length ? '<ul class="dataset-warn">' + warnings.map(function (w) { return '<li>' + esc(typeof w === 'string' ? w : JSON.stringify(w)) + '</li>'; }).join('') + '</ul>' : '') +
      '<table class="metric-table dataset-table"><thead><tr><th>묶음</th><th>대화</th><th class="num">답변</th><th class="num">학습 토큰</th></tr></thead><tbody>' +
      keys.map(function (k) {
        var r = counts[k] || {};
        var w = Math.round(Number(r.conversations || 0) / most * 100);
        return '<tr><td>' + esc((items.clusterLabels || {})[k] || k) + '</td><td><span class="dataset-bar"><i style="width:' + w + '%"></i></span><span class="num">' + esc(num(r.conversations)) + '</span></td><td class="num">' + esc(num(r.replies)) + '</td><td class="num">' + esc(num(r.supervisedTokens)) + '</td></tr>';
      }).join('') + '</tbody></table>' +
      '<details class="gate-more"><summary>분할 파일 · ' + esc(dataset.datasetRev || '') + '</summary><table class="metric-table"><thead><tr><th>분할</th><th>파일</th><th class="num">대화</th></tr></thead><tbody>' +
      list(dataset.files).map(function (f) { return '<tr><td>' + esc(f.split) + '</td><td><code>' + esc(f.path) + '</code></td><td class="num">' + esc(f.conversations) + '</td></tr>'; }).join('') +
      '</tbody></table></details></section>' +
      '<section class="gate-section sample-board"><h2>무작위 표본 ' + list(items.samples).length + '개</h2>' +
      '<p class="section-sub">기본은 모두 쓰기예요. 읽어 보고 고치거나 버릴 대화만 바꿔 주세요. 숫자 키 1·2·3으로 고르고 J·K(또는 ←·→)로 옮겨요.</p>' +
      '<div class="pose-tabs" data-sample-tabs hidden></div>' +
      '<details class="gate-more sample-guide" data-sample-guide hidden><summary>작성 지침</summary><div data-sample-guide-body></div></details>' +
      '<div class="sample-inbox"><ol class="sample-list" data-sample-list aria-label="대화 목록"></ol><div class="sample-read" data-sample-read></div></div></section>'
    );
  }
  function paintDatasetMeta() {
    var samples = list(state.items.samples);
    var count = { ADOPT: 0, FIX: 0, REJECT: 0 };
    samples.forEach(function (x) { var v = state.sampleVerdict[x.conversationId]; if (v) count[v] += 1; });
    var missingNote = samples.filter(function (x) { return state.sampleVerdict[x.conversationId] === 'FIX' && !String(state.sampleNote[x.conversationId] || '').trim(); }).length;
    var side = q('[data-side-extra]');
    var seen = samples.filter(function (x) { return state.sampleSeen[x.conversationId]; }).length;
    if (side) side.innerHTML = '<div class="bg-side"><p class="bg-side-title"><b>표본 판정</b><span>' + samples.length + '개</span></p>' +
      '<dl class="facts"><dt>직접 본 대화</dt><dd>' + seen + ' / ' + samples.length + '</dd><dt>쓰기</dt><dd>' + count.ADOPT + '</dd><dt>고쳐 쓰기</dt><dd>' + count.FIX + '</dd><dt>버리기</dt><dd>' + count.REJECT + '</dd></dl></div>';
    if (faceLocked()) return;
    var approve = q('[data-decide="APPROVE"]');
    if (approve) approve.disabled = Boolean(state.busy || missingNote);
    var hint = q('[data-side-hint]');
    var unseen = samples.length - seen;
    if (hint) hint.textContent = missingNote ? '고쳐 쓰기로 바꾼 대화 ' + missingNote + '개에 고칠 점을 적어 주세요.'
      : (unseen ? '아직 안 본 대화 ' + unseen + '개는 기본값인 쓰기로 들어가요. ' : '') +
        (count.FIX + count.REJECT ? '바꾼 대화 ' + (count.FIX + count.REJECT) + '개를 담아 승인하거나 수정 요청을 보내요.'
          : '요약에 문제가 없으면 승인해요.');
  }
  function buildDataset(decision) {
    var verdicts = {};
    var notes = {};
    list(state.items.samples).forEach(function (x, i) {
      var v = state.sampleVerdict[x.conversationId] || 'ADOPT';
      verdicts[x.conversationId] = v;
      var note = String(state.sampleNote[x.conversationId] || '').trim();
      if (v === 'FIX') {
        if (!note) throw Error('대화 ' + (i + 1) + '에서 고칠 점을 적어 주세요.');
        notes[x.conversationId] = note;
      }
    });
    return Object.assign({ decision: decision, verdicts: verdicts, notes: notes }, details());
  }

  // ---------------------------------------------------------------- G8
  function renderEval(items) {
    var report = items.report || {};
    var metrics = list(report.metrics)
      .map(function (metric) {
        return '<tr><td>' + esc(adoptLabel(metric.armId)) + '</td><td>' + esc(METRIC_KO[metric.metric] || metric.metric) +
          '</td><td class="num">' + esc(metric.value) + '</td><td class="metric-help">' + esc(METRIC_HELP[metric.metric] || '') + '</td></tr>';
      })
      .join('');
    var criteria = list(report.criteriaResults)
      .map(function (result) {
        return '<tr><td>' + esc(result.id) + '</td><td>' + esc(adoptLabel(result.armId)) +
          '</td><td class="num">' + esc(result.value) + '</td><td>' +
          (result.passed
            ? '<span class="badge-chip is-good">통과</span>'
            : '<span class="badge-chip is-bad">미달</span>') + '</td></tr>';
      })
      .join('');
    var total = list(items.pairs).length;
    var pairs = list(items.pairs)
      .map(function (pair, index) {
        var pick = state.pairs[pair.pairId] || '';
        var prompt = String(pair.prompt || '');
        var cut = prompt.lastIndexOf('\n\n');
        var history = cut > 0 ? prompt.slice(0, cut) : '';
        var last = cut > 0 ? prompt.slice(cut + 2) : prompt;
        var button = function (value, label, key) {
          return '<button type="button" data-pick="' + value + '" data-pair-id="' + esc(pair.pairId) +
            '" aria-pressed="' + (pick === value) + '">' + label + '<kbd>' + key + '</kbd></button>';
        };
        return (
          '<article class="pair' + (pick ? ' is-done' : '') + '" data-pair="' + esc(pair.pairId) +
          '" tabindex="-1" aria-label="' + esc((index + 1) + '번째 쌍, 전체 ' + total + '쌍') + '">' +
          '<div class="pair-head"><span class="pair-no">' + (index + 1) + ' / ' + total + '</span>' +
          '<span class="pair-state">' + (pick ? '골랐어요' : '아직 안 골랐어요') + '</span>' +
          '<div class="seg" role="group" aria-label="' + esc((index + 1) + '번째 쌍 선택') + '">' +
          button('A', 'A가 나아요', '1') + button('B', 'B가 나아요', '2') + button('TIE', '비슷해요', '3') +
          '</div></div>' +
          (history ? '<details class="pair-history"><summary>앞 대화 보기</summary><p>' + esc(history) + '</p></details>' : '') +
          '<p class="pair-prompt"><span>사용자</span>' + esc(last) + '</p>' +
          '<div class="pair-answers">' +
          '<div class="pair-answer' + (pick === 'A' ? ' is-picked' : '') + '" data-answer="A"><b>응답 A</b>' + esc(pair.a) + '</div>' +
          '<div class="pair-answer' + (pick === 'B' ? ' is-picked' : '') + '" data-answer="B"><b>응답 B</b>' + esc(pair.b) + '</div>' +
          '</div></article>'
        );
      })
      .join('');
    var adopt = list(items.adoptOptions)
      .map(function (option) {
        return '<option value="' + esc(option) + '">' + esc(adoptLabel(option)) + '</option>';
      })
      .join('');
    // 지표에는 조건 이름과 값이 있어 판정을 흔들 수 있다. 블라인드를 다 고른 뒤에 연다.
    var blindOpen =
      !list(items.pairs).length || (state.view && state.view.status !== 'AWAITING_HUMAN');
    return (
      '<section class="gate-section" data-blind-wait' + (blindOpen ? ' hidden' : '') + '>' +
      '<h2>지표</h2><p class="section-sub">조건 이름과 지표 값은 블라인드 ' +
      list(items.pairs).length + '쌍을 모두 고르면 열려요.' +
      (items.twin ? ' 실제 답 비교의 조건별 구별률도 그때 함께 열려요.' : '') + '</p></section>' +
      '<section class="gate-section" data-after-blind' + (blindOpen ? '' : ' hidden') + '>' +
      '<h2>지표</h2>' +
      '<p class="section-sub">블라인드 판정을 마친 뒤에 보는 조건별 지표예요.</p>' +
      '<table class="metric-table"><thead><tr><th>조건</th><th>지표</th><th>값</th><th>보는 법</th></tr>' +
      '</thead><tbody>' + metrics + '</tbody></table>' +
      '<details class="gate-more"><summary>기준 결과</summary>' +
      '<table class="metric-table"><thead><tr><th>기준</th><th>조건</th><th>값</th><th>결과</th>' +
      '</tr></thead><tbody>' + criteria + '</tbody></table>' +
      '<p class="section-sub">' + esc(report.recommendation || '') + '</p></details>' +
      twinTable(items.twin) + '</section>' +
      '<section class="gate-section"><h2>블라인드 비교</h2>' +
      '<p class="section-sub">어느 응답이 어떤 조건인지 숨겨요. 사용자 말에 더 자연스럽게 답한 쪽을 고르고, ' +
      '차이가 없으면 비슷해요를 골라 주세요. 고르면 다음 쌍으로 넘어가요.</p>' +
      '<div class="blind-bar" data-blind-bar><div class="blind-progress"><span class="blind-count" data-blind-count>' +
      Object.keys(state.pairs).length + ' / ' + total + '</span> 골랐어요' +
      '<span class="blind-meter" aria-hidden="true"><i data-blind-meter style="width:' +
      (total ? Math.round(Object.keys(state.pairs).length / total * 100) : 0) + '%"></i></span></div>' +
      '<button type="button" class="btn btn--ghost" data-next-pair>안 고른 쌍으로</button>' +
      '<p class="blind-keys">단축키 <kbd>1</kbd> A가 나아요 · <kbd>2</kbd> B가 나아요 · <kbd>3</kbd> 비슷해요 · ' +
      NAV_KEYS + ' 쌍</p></div>' +
      '<div class="pair-list">' + pairs + '</div></section>' +
      twinBallots(items.twin) +
      '<section class="gate-section" data-adopt-section><h2>채택 기준</h2>' +
      '<p class="section-sub">블라인드 결과와 지표를 본 뒤 어떤 조건을 채택할지 정해요.</p>' +
      '<label class="field"><span>채택</span><select data-adopt>' + adopt +
      '</select></label></section>'
    );
  }

  function buildEval(decision) {
    var pairs = list(state.items.pairs);
    var picks = [];
    pairs.forEach(function (pair) {
      var pick = state.pairs[pair.pairId];
      if (!pick) throw Error(pair.pairId + '를 아직 고르지 않았어요.');
      picks.push({ pairId: pair.pairId, pick: pick });
    });
    var adopted = q('[data-adopt]');
    if (!adopted || !adopted.value) throw Error('채택 기준을 골라 주세요.');
    return Object.assign(
      { decision: decision, adopted: adopted.value, humanPicks: picks },
      details()
    );
  }

  var ARM_KO = {
    LONG_BASE: '긴 프롬프트 (학습 없이)',
    BOUND_SFT: '연결한 모델',
    SHORT_GEMMA_SFT: '짧은 프롬프트 + Gemma 학습',
    SHORT_GEMINI_SFT: '짧은 프롬프트 + Gemini 학습'
  };
  var METRIC_KO = {
    repeat_rate_101_200: '같은 말 반복률 (101~200턴)',
    memory_recall_200: '기억 재현 (200턴)',
    apology_recovery: '사과 뒤 관계 회복'
  };
  // 지표마다 무엇을 재는지와 좋은 방향(D-0129).
  var METRIC_HELP = {
    repeat_rate_101_200: '낮을수록 좋아요 · 긴 대화 뒷부분(101~200번째 턴)에서 앞서 한 말을 되풀이한 비율',
    memory_recall_200: '높을수록 좋아요 · 200턴 대화에서 앞에 나온 사실을 맞게 기억한 정도',
    apology_recovery: '높을수록 좋아요 · 사과 장면 뒤 관계를 자연스럽게 회복한 정도'
  };
  function adoptLabel(option) {
    return ARM_KO[option] || '학습한 모델 · ' + option;
  }
  function pairNodes() {
    return qa('.pair[data-pair]');
  }
  function evalTotals() {
    var total = list(state.items.pairs).length;
    var done = list(state.items.pairs).filter(function (pair) {
      return state.pairs[pair.pairId];
    }).length;
    return { total: total, done: done };
  }
  function updateBlind() {
    if (state.kind !== 'eval') return;
    var n = evalTotals();
    var counter = q('[data-blind-count]');
    if (counter) counter.textContent = n.done + ' / ' + n.total;
    var meter = q('[data-blind-meter]');
    if (meter) meter.style.width = (n.total ? Math.round(n.done / n.total * 100) : 0) + '%';
    var all = n.total > 0 && n.done >= n.total;
    var after = q('[data-after-blind]');
    var wait = q('[data-blind-wait]');
    if (all && after) after.hidden = false;
    if (all && wait) wait.hidden = true;
    var next = q('[data-next-pair]');
    if (next) next.hidden = all;
    // 다 고르기 전에는 보내지 못하게 잠그고, 왜 잠겼는지 적는다.
    var locked = state.view && (state.view.status === 'APPROVED' || state.view.status === 'REJECTED');
    qa('[data-decide]').forEach(function (node) {
      node.disabled = Boolean(locked || state.busy || !all);
    });
    var hint = q('[data-side-hint]');
    if (hint && !locked) {
      hint.textContent = all
        ? '모두 골랐어요. 아래 지표를 보고 채택할 조건을 고른 뒤 보내 주세요.'
        : (n.total - n.done) + '쌍이 남았어요. 모두 고르면 보낼 수 있어요.';
    }
  }
  function focusPair(node) {
    if (!node) return;
    node.focus({ preventScroll: true });
    var smooth = !(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    node.scrollIntoView({ block: 'center', behavior: smooth ? 'smooth' : 'auto' });
  }
  function nextUnpicked(from) {
    var nodes = pairNodes();
    var start = from ? nodes.indexOf(from) : -1;
    for (var step = 1; step <= nodes.length; step += 1) {
      var node = nodes[(start + step + nodes.length) % nodes.length];
      if (!state.pairs[node.getAttribute('data-pair')]) return node;
    }
    return null;
  }
  // 시트를 닫거나 새로 고쳐도 고른 쌍을 잃지 않게 이 탭에 잠시 둔다(같은 판일 때만 되살린다).
  function picksKey() {
    return 'fd-blind:' + state.characterId + ':' + state.gate + ':' + ((state.view && state.view.rev) || '');
  }
  function savePicks() {
    try {
      window.sessionStorage.setItem(picksKey(), JSON.stringify(state.pairs));
    } catch (error) {
      /* 저장하지 못해도 고르기는 된다 */
    }
  }
  function restorePicks() {
    if (state.kind !== 'eval') return;
    try {
      var saved = JSON.parse(window.sessionStorage.getItem(picksKey()) || '{}');
      var ids = list(state.items.pairs).map(function (pair) { return pair.pairId; });
      Object.keys(saved).forEach(function (id) {
        if (ids.indexOf(id) >= 0 && ['A', 'B', 'TIE'].indexOf(saved[id]) >= 0 && !state.pairs[id]) state.pairs[id] = saved[id];
      });
    } catch (error) {
      /* 깨진 저장값은 무시한다 */
    }
  }
  function applyPick(pairId, choice, advance) {
    state.pairs[pairId] = choice;
    savePicks();
    var pair = pairNodes().filter(function (node) {
      return node.getAttribute('data-pair') === pairId;
    })[0];
    if (pair) {
      qa('[data-pick]', pair).forEach(function (node) {
        node.setAttribute('aria-pressed', String(node.getAttribute('data-pick') === choice));
      });
      qa('.pair-answer', pair).forEach(function (box) {
        box.classList.toggle('is-picked', box.getAttribute('data-answer') === choice);
      });
      pair.classList.add('is-done');
      var label = q('.pair-state', pair);
      if (label) label.textContent = '골랐어요';
    }
    updateBlind();
    if (!advance) return;
    var next = nextUnpicked(pair);
    if (next) setTimeout(function () { focusPair(next); }, 180);
    else {
      var adopt = q('[data-adopt-section]');
      if (adopt) setTimeout(function () { focusPair(adopt); var sel = q('[data-adopt]'); if (sel) sel.focus({ preventScroll: true }); }, 180);
    }
  }
  function currentPair() {
    var active = document.activeElement;
    var pair = active && active.closest ? active.closest('.pair[data-pair]') : null;
    return pair || nextUnpicked(null) || pairNodes()[0] || null;
  }
  function onEvalKey(event) {
    if (state.kind !== 'eval' || event.altKey || event.ctrlKey || event.metaKey) return;
    var target = event.target;
    var tag = target && target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (target && target.isContentEditable)) return;
    var key = String(event.key || '').toLowerCase();
    var map = { '1': 'A', 'a': 'A', '2': 'B', 'b': 'B', '3': 'TIE' };
    var pair = currentPair();
    if (!pair) return;
    if (map[key]) {
      event.preventDefault();
      applyPick(pair.getAttribute('data-pair'), map[key], true);
    } else if (navStep(key)) {
      event.preventDefault();
      var nodes = pairNodes();
      var i = nodes.indexOf(pair);
      focusPair(nodes[Math.max(0, Math.min(nodes.length - 1, i + navStep(key)))]);
    }
  }

  // ---------------------------------------------------------------- G9
  // ---------------------------------------------------------------- G8(학습 없이 진행, K-0038)
  function renderPromptOnly(items) {
    var doc = items.decision || {};
    if (isTwinDecision(items)) return renderTwinAdopt(items);
    var runs = list(doc.trainingRuns)
      .map(function (run) {
        var usd = run.estimateUsd == null ? '-' : '$' + Number(run.estimateUsd).toFixed(2);
        return '<tr><td>' + esc(run.provider) + '</td><td>' + esc(run.status) + '</td><td>' +
          (run.dryRun ? '계획만' : '실행') + '</td><td class="num">' + esc(usd) +
          '</td></tr>';
      })
      .join('');
    return (
      '<section class="gate-section"><h2>학습 결과가 없어요</h2>' +
      '<p class="section-sub">' + esc(doc.reason || '') + '</p>' +
      '<table class="metric-table"><thead><tr><th>학습 환경</th><th>상태</th><th>실행</th>' +
      '<th>추정 비용</th></tr></thead><tbody>' +
      (runs || '<tr><td colspan="4">학습 계획 없음</td></tr>') + '</tbody></table></section>' +
      '<section class="gate-section"><h2>이렇게 진행돼요</h2>' +
      '<p class="section-sub"><b>' + esc(items.adoptLabel || '긴 프롬프트로 진행') + '</b>을 누르면 학습 모델 평가 없이 패키지를 만들고, ' +
      '패키지에는 긴 프롬프트·짧은 프롬프트·데이터셋(' + esc(doc.datasetRev || '없음') +
      ')과 학습 계획이 들어가요. <b>학습을 기다릴게요</b>를 누르면 학습 결과가 생길 때까지 ' +
      '평가 단계가 멈춰요.</p></section>'
    );
  }

  function buildPromptOnly(decision) {
    var answer = { decision: decision };
    if (decision === 'SELECT') answer.adopted = state.items.adoptTarget || list(state.items.adoptOptions)[0] || 'LONG_BASE';
    return Object.assign(answer, details());
  }

  // ---------------------------------------------------------------- 모티브 G8(실제 답 비교, twin-comparison-v1)
  // 조건 이름이 붙은 구별률 표와 가족 블라인드 파일 목록을 나눈다. 블라인드 파일은 판 번호로만 알린다.
  // 실제 답과 생성 답을 나란히 보이는 시연 화면은 그 판의 가족 판정을 가져온 뒤에만 서버가 연다.
  var TWIN_ARM_KO = { LONG_BASE: '긴 프롬프트', BOUND_SFT: '연결한 모델' };
  var TWIN_STATUS_KO = {
    COMPLETE: ['심사 완료', 'is-good'],
    NO_SERVING: ['서빙 없음', ''],
    PLANNED: ['실행 전', ''],
    NO_JUDGE: ['심사 모델 미설정', 'is-warn']
  };
  var OVERLAP_KO = { TRAIN: '학습 대화', PROMPT: '대화 프롬프트', VOICE: '말투 예시' };
  function isTwinDecision(items) {
    return Boolean(items && items.decision && items.decision.schemaVersion === 'eval-twin-decision-v1');
  }
  function twinArm(armId) {
    return TWIN_ARM_KO[armId] || adoptLabel(armId);
  }
  function twinRate(score) {
    if (!score || !score.total) return '—';
    return score.correct + '/' + score.total + ' · ' + Math.round(Number(score.rate) * 100) + '%';
  }
  function twinTable(twin) {
    if (!twin) return '';
    var rows = list(twin.conditions).map(function (c) {
      var st = TWIN_STATUS_KO[c.status] || [c.status, ''];
      var kinds = Object.keys(c.overlapKinds || {}).map(function (k) { return (OVERLAP_KO[k] || k) + ' ' + c.overlapKinds[k]; }).join(' · ');
      return '<tr><td>' + esc(twinArm(c.armId)) + '</td><td><span class="badge-chip ' + st[1] + '">' + esc(st[0]) + '</span></td>' +
        '<td class="num">' + esc(twinRate(c.modelScore)) + '</td><td class="num">' + esc(!c.blind ? '—' : c.voted ? twinRate(c.humanScore) : '판정 전') + '</td>' +
        '<td class="num">' + (c.trials ? esc(c.exact) + '건' : '—') + '</td>' +
        '<td>' + (c.trials ? '<span class="num">' + esc(c.overlap) + '건</span>' + (kinds ? '<span class="twin-sub">' + esc(kinds) + '</span>' : '') : '—') + '</td>' +
        '<td>' + (c.demo && c.demo.url ? '<a href="' + esc(c.demo.url) + '" target="_blank" rel="noopener">열기</a>' : c.blind ? '<span class="twin-sub">가족 판정 뒤</span>' : '—') + '</td></tr>';
    }).join('');
    var planned = twin.phase === 'PLANNED';
    return (
      '<h3 class="twin-h">조건별 구별률</h3>' +
      '<p class="section-sub">비교 세트 ' + esc(twin.sceneCount) + '장면에서 실제로 보낸 답과 생성 답을 나란히 두고, 어느 쪽이 실제인지 골랐어요. ' +
      '구별률이 50%에 가까울수록 둘을 가려내기 어렵다는 뜻이에요. 장면 수가 적으면 차이를 일반화하기 어려워요.' +
      (planned ? ' 아직 실행 전이라 판정이 없어요(예상 호출 ' + esc(twin.plannedCalls) + '회).' : '') + '</p>' +
      '<div class="twin-scroll"><table class="metric-table twin-table"><thead><tr><th>조건</th><th>상태</th><th class="num">심사 모델</th><th class="num">가족</th>' +
      '<th class="num">정답과 같음</th><th>외운 답 의심</th><th>시연</th></tr></thead><tbody>' + rows + '</tbody></table></div>' +
      '<p class="metric-help">정답과 같음은 생성 답이 실제 답과 글자까지 같아 문장만으로는 가릴 수 없는 장면이에요(분모에 들어가요). ' +
      '외운 답 의심은 생성 답이 학습 대화·프롬프트·말투 예시와 ' + esc(twin.overlapChars) + '자 이상 겹친 장면이에요. ' +
      '시연 화면에는 정답이 나오고 "AI 생성 · 본인과 무관한 기술 시연" 표시가 붙어요.</p>' +
      '<details class="card-tech"><summary>상세 · 모델 ID</summary>' +
      '심사 모델: ' + esc(twin.judgeModel || '-') + '\n' +
      list(twin.conditions).map(function (c) { return esc(twinArm(c.armId)) + ': ' + esc(c.model || '-') + (c.servingModel ? ' · 서빙 ' + esc(c.servingModel) : ''); }).join('\n') +
      '\n예상 호출 ' + esc(twin.plannedCalls) + '회 · 비용 상한 ' + (twin.costUpperUsd == null ? '견적 없음' : '$' + Number(twin.costUpperUsd).toFixed(2)) + '</details>'
    );
  }
  function twinBallots(twin) {
    if (!twin) return '';
    var dir = (state.view && state.view.stageDir) || '';
    var ballots = list(twin.ballots);
    var rows = ballots.map(function (b, i) {
      var file = b.file || {};
      return '<li class="twin-ballot"><b>판 ' + (i + 1) + '</b><span class="twin-sub">번호 ' + esc(String(b.ballot).slice(0, 8)) + '</span>' +
        '<span class="badge-chip' + (b.voted ? ' is-good' : '') + '">' + (b.voted ? '답 가져옴' : '답 기다리는 중') + '</span>' +
        '<code class="twin-path">' + esc((dir ? dir + '/' : '') + (file.name || '')) + '</code>' +
        (file.url ? '<a href="' + esc(file.url) + '" target="_blank" rel="noopener">블라인드 화면 열기</a>' : '') + '</li>';
    }).join('');
    return (
      '<section class="gate-section"><h2>가족 블라인드 판정</h2>' +
      (ballots.length
        ? '<p class="section-sub">가족 한 사람에게 블라인드 파일 하나만 전달해 주세요. 파일에는 조건 이름과 정답이 없어요. ' +
          '시연 화면에는 정답이 나오니 판정 전에는 보여 주지 마세요.</p><ul class="twin-ballots">' + rows + '</ul>' +
          '<ol class="twin-steps"><li>블라인드 파일을 가족에게 전달해요.</li>' +
          '<li>가족이 장면마다 실제로 보낸 답을 고르고 <b>답 파일 저장</b>을 눌러요. answers-번호.json 파일이 저장돼요.</li>' +
          '<li>받은 답 파일을 공장에서 가져오면 가족 구별률이 채워지고 그 판의 시연 화면이 열려요. 이 화면에는 아직 가져오기 버튼이 없어 담당자가 가져와요.</li></ol>' +
          '<details class="card-tech"><summary>상세 · 가져오기</summary>' + esc(twin.importHint || '') + '\n' + esc(twin.importCall || '') + '</details>'
        : '<p class="section-sub">판정까지 마친 조건이 없어 블라인드 파일이 없어요. 심사 모델과 서빙이 설정된 뒤 다시 만들어요.</p>') +
      '</section>'
    );
  }
  function renderTwinAdopt(items) {
    var doc = items.decision || {};
    var bind = doc.mode === 'BIND_EXISTING';
    var binding = doc.binding || {};
    var check = doc.preflight || {};
    var twin = items.twin;
    var label = items.adoptLabel || '긴 프롬프트로 진행';
    return (
      '<section class="gate-section"><h2>채택할 대상</h2>' +
      facts([
        ['진행 방식', bind ? '연결한 모델 · 이미 학습된 모델을 이 캐릭터에 연결해요' : '긴 프롬프트 · 학습 없이 긴 프롬프트로 대화해요'],
        ['비교 세트', doc.sceneCount + '장면'],
        bind ? ['연결 사전 확인', ({ PASSED: '통과', PASS: '통과', OK: '통과', FAILED: '실패', SKIPPED: '건너뜀' })[check.status] || check.status || '기록 없음'] : null
      ].filter(Boolean)) +
      '<details class="card-tech"><summary>상세 · 채택 값</summary>' +
      '결정에 실을 값: ' + esc(items.adoptTarget || '') + '\n' +
      (bind ? '모델: ' + esc(binding.ref || '-') + '@' + esc(binding.revision || '-') + '\n서빙 경로: ' + esc(binding.servingRoute || '-') + '\n' +
        (check.reason ? '사전 확인: ' + esc(check.reason) + '\n' : '') : '') +
      esc(doc.reason || '') + '</details></section>' +
      (twin
        ? '<section class="gate-section"><h2>실제 답 비교</h2>' + twinTable(twin) + '</section>' + twinBallots(twin)
        : '<section class="gate-section"><h2>실제 답 비교</h2><p class="section-sub">비교 보고가 아직 없어요.</p></section>') +
      '<section class="gate-section"><h2>이렇게 진행돼요</h2>' +
      '<p class="section-sub"><b>' + esc(label) + '</b>을 누르면 ' + (bind ? '연결한 모델을' : '긴 프롬프트를') +
      ' 이 캐릭터의 대화 방식으로 정하고 패키지를 만들어요. 가족 판정은 결정 전에 가져오면 기록에 함께 남아요. ' +
      '<b>반려</b>하면 이 판을 버리고 다시 만들어요.</p></section>'
    );
  }

  // ---------------------------------------------------------------- G0 출처 확인(모티브, 사람 전용)
  // 비교 세트는 개수만 보여요. 원문은 서버가 화면 자료·파일 목록 어디에도 싣지 않는다(D-0120).
  var TEXT_KIND_KO = { KAKAO_EXPORT: '카톡 내보내기', INTERVIEW: '인터뷰', ARTICLE: '기사', TRANSCRIPT: '받아쓰기' };
  var SUBJECT_KO = { PUBLIC_FIGURE: '공개 인물', PRIVATE_PERSON: '가까운 사람' };
  var MASK_KO = { phone: '전화번호', email: '이메일', account: '계좌·번호', participant: '다른 참여자 이름' };
  var DIGEST_KO = { DAILY: '일상', AFFECTION: '애정', CONFLICT: '갈등', ADVICE: '조언', HUMOR: '농담', WORK: '일', OTHER: '기타' };
  function num(value) {
    return Number(value || 0).toLocaleString('ko-KR');
  }
  function maskedTotal(items) {
    var m = items.masked || {};
    return Object.keys(m).reduce(function (sum, k) { return sum + Number(m[k] || 0); }, 0);
  }
  function sourceChecks(items) {
    var usage = items.usage || {};
    var counts = items.counts || {};
    var agent = items.agent || {};
    var speaker = agent.speakerCheck || {};
    var flags = list(agent.piiFlags).length;
    var m = items.masked || {};
    var maskText = Object.keys(MASK_KO).filter(function (k) { return m[k]; }).map(function (k) { return MASK_KO[k] + ' ' + m[k]; }).join(' · ');
    // 팀 내부 도구라 동의 기록은 보지 않는다. 사용 범위가 비면 '팀 내부 사용'으로 본다(계획 2차 약속 2).
    return [
      { title: '쓰는 곳', tone: usage.scope ? 'ok' : 'info', detail: usage.scope ? (usage.scope.length > 80 ? usage.scope.slice(0, 80) + '…' : usage.scope) : '적지 않아서 팀 내부 사용으로 봐요.' },
      {
        title: '화자 지정',
        tone: speaker.confirmed ? 'ok' : 'warn',
        detail: (speaker.confirmed ? '출처 정리 에이전트가 화자를 확인했어요' : '출처 정리 에이전트가 화자를 확인하지 못했어요') +
          (speaker.note && speaker.note.length <= 90 ? ' · ' + plainCodes(speaker.note) : ''),
        more: speaker.note && speaker.note.length > 90 ? plainCodes(speaker.note) : ''
      },
      {
        title: '개인정보 가림',
        tone: flags ? 'warn' : 'ok',
        detail: (maskText ? maskText + '를 가렸어요' : '가린 항목이 없어요') + (flags ? ' · 더 가릴 것 ' + flags + '건이 있어요' : '')
      },
      {
        title: '비교 세트',
        tone: counts.holdoutConversations ? 'ok' : 'warn',
        detail: counts.holdoutConversations
          ? '대화 ' + num(counts.holdoutConversations) + '개(메시지 ' + num(counts.holdoutMessages) + '개)를 떼어 뒀어요. 원문은 이 화면에 보이지 않아요.'
          : '떼어 둔 대화가 없어요. 실제 답 비교를 할 수 없어요.'
      }
    ];
  }
  function checkRow(c) {
    var mark = { ok: '✓', bad: '✕', warn: '!', info: 'i' }[c.tone];
    return '<li><div class="pkg-check src-check is-' + c.tone + '"><span class="pkg-mark" aria-hidden="true">' + mark + '</span>' +
      '<b>' + esc(c.title) + '</b><span class="pkg-detail-text">' + esc(c.detail) +
      (c.more ? '<details class="src-check-more"><summary>에이전트 메모 보기</summary>' + esc(c.more) + '</details>' : '') + '</span><span class="sr-only">' +
      ({ ok: ' 통과', bad: ' 막힘', warn: ' 확인 필요', info: ' 안내' }[c.tone]) + '</span></div></li>';
  }
  // 사실 종류·말한 자리 이름. 코드 값은 화면에 보이지 않는다.
  var FACT_CAT_KO = { BIO: '기본 정보', CAREER: '경력', RESULT: '경기 결과', AWARD: '수상', RECORD: '기록', CURRENT_STATUS: '지금 상태' };
  var REGISTER_KO = { FORMAL: '공식 자리', CASUAL: '캐주얼 자리' };
  var SOURCE_ROWS = 10;
  // 계획 §1 default_register와 같은 표: 인터뷰·기사는 공식 자리, 카톡·받아쓰기는 캐주얼 자리.
  function registerOf(t) {
    var r = t && t.register;
    if (r === 'FORMAL' || r === 'CASUAL') return r;
    var k = t && t.kind;
    return k === 'INTERVIEW' || k === 'ARTICLE' ? 'FORMAL' : k === 'KAKAO_EXPORT' || k === 'TRANSCRIPT' ? 'CASUAL' : '';
  }
  function hostOf(url) {
    var m = /^https?:\/\/([^\/?#:@]+)/i.exec(String(url || ''));
    return m ? m[1].replace(/^www\./i, '').toLowerCase() : '';
  }
  function dateKo(value) {
    var m = /^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?/.exec(String(value || ''));
    if (!m) return String(value || '');
    return m[1] + '년' + (m[2] ? ' ' + Number(m[2]) + '월' : '') + (m[3] ? ' ' + Number(m[3]) + '일' : '');
  }
  // 출처 칩: 주소 전체 대신 도메인만 보이고, 누르면 새 탭에서 열린다. 긴 주소는 툴팁에만 둔다.
  function sourceChip(s) {
    var url = String((s && s.url) || '');
    var host = hostOf(url);
    if (!host) return s && s.title ? '<span class="fact-chip">' + esc(s.title) + '</span>' : '';
    var title = s.title && s.title !== host ? s.title + ' · ' + host : host;
    return '<a class="fact-chip" href="' + esc(url) + '" target="_blank" rel="noopener noreferrer" title="' + esc(title) + '">' + esc(host) +
      '<span aria-hidden="true">↗</span><span class="sr-only"> (새 탭)</span></a>';
  }
  function factCard(f, locked) {
    var out = Boolean(f.excluded);
    var srcs = list(f.sources).map(sourceChip).join('');
    var self = f.selfView && (f.selfView.paraphrase || f.selfView.quote) ? f.selfView : null;
    return '<li class="fact-card' + (out ? ' is-out' : '') + '">' +
      '<div class="fact-top"><span class="fact-cat">' + esc(FACT_CAT_KO[f.category] || '사실') + '</span>' +
      (f.eventDate ? '<time datetime="' + esc(f.eventDate) + '">' + esc(dateKo(f.eventDate)) + '</time>' : '') +
      '<span class="fact-out-badge">빼기로 했어요</span></div>' +
      '<p class="fact-text">' + esc(f.text) + '</p>' +
      (srcs ? '<div class="fact-srcs"><span class="fact-label">출처</span>' + srcs + '</div>' : '') +
      (self ? '<div class="fact-self"><span class="fact-label">본인 시점</span>' + (self.paraphrase ? '<p>' + esc(self.paraphrase) + '</p>' : '') +
        (self.quote ? '<blockquote' + (self.msgId ? ' title="' + esc('원문 위치 ' + self.msgId) + '"' : '') + '>' + esc(self.quote) + '</blockquote>' : '') + '</div>' : '') +
      // 결정한 관문에서는 빼기 칸을 그리지 않는다. 뺀 사실은 '빼기로 했어요' 표시로 남는다.
      (locked ? '' : '<label class="fact-toggle"><input type="checkbox" data-exclude-fact value="' + esc(f.factId) + '"' + (out ? ' checked' : '') + (out ? ' disabled' : '') + '>' +
        '<span>' + (out ? '이미 뺀 사실이에요' : '이 사실 빼기') + '</span></label>') + '</li>';
  }
  function renderFacts(pf) {
    var facts = list(pf.items);
    var locked = faceLocked();
    var deflections = list(pf.deflections).filter(function (d) { return d && d.quote; });
    return '<section class="gate-section"><h2>공개 사실 ' + facts.length + '개</h2>' +
      '<p class="section-sub">' + (locked ? '공개 기사에서 모은 사실이에요. 대화에서 이 인물의 사실로 써요.' : '공개 기사에서 모은 사실이에요. 대화에서 이 인물의 사실로 쓰니, 틀렸거나 쓰지 않을 사실은 \'이 사실 빼기\'를 눌러 주세요. 승인할 때 함께 빠져요.') + '</p>' +
      (facts.length ? '<ol class="fact-cards">' + facts.map(function (f) { return factCard(f, locked); }).join('') + '</ol>' : '<p class="empty">모은 사실이 없어요.</p>') +
      (deflections.length ? '<h3 class="twin-h">사적인 질문을 넘기는 말</h3>' +
        '<p class="section-sub">사생활을 물으면 이 말투로 넘겨요. 원문에서 본인이 한 말이에요.</p>' +
        '<ul class="fact-deflect">' + deflections.map(function (d) {
          return '<li><q' + (d.msgId ? ' title="' + esc('원문 위치 ' + d.msgId) + '"' : '') + '>' + esc(d.quote) + '</q></li>';
        }).join('') + '</ul>' : '') +
      '</section>';
  }
  // 원문 표 위의 요약: 종류별·말한 자리별 원문 수와 대상 인물 메시지 비율.
  function sourceMix(texts) {
    var kinds = {};
    var regs = { FORMAL: { n: 0, m: 0 }, CASUAL: { n: 0, m: 0 } };
    texts.forEach(function (t) {
      var k = TEXT_KIND_KO[t.kind] || '그 밖';
      kinds[k] = (kinds[k] || 0) + 1;
      var r = regs[registerOf(t)];
      if (r) { r.n += 1; r.m += Number(t.subjectMessages || 0); }
    });
    var total = regs.FORMAL.m + regs.CASUAL.m;
    var share = total ? Math.round(regs.FORMAL.m / total * 100) : 0;
    return '<div class="src-mix">' +
      '<p><b>원문 ' + num(texts.length) + '개</b>' + Object.keys(kinds).map(function (k) { return '<span>' + esc(k) + ' ' + num(kinds[k]) + '개</span>'; }).join('') + '</p>' +
      (total ? '<p><b>말한 자리</b><span>공식 자리 ' + num(regs.FORMAL.n) + '개 · 메시지 ' + num(regs.FORMAL.m) + '개</span><span>캐주얼 자리 ' + num(regs.CASUAL.n) + '개 · 메시지 ' + num(regs.CASUAL.m) + '개</span></p>' +
        '<div class="src-mix-bar" role="img" aria-label="' + esc('대상 인물 메시지 중 공식 자리 ' + share + '%, 캐주얼 자리 ' + (100 - share) + '%') + '"><i style="width:' + share + '%"></i></div>' +
        '<p class="src-mix-legend"><span class="is-formal">공식 자리 ' + share + '%</span><span class="is-casual">캐주얼 자리 ' + (100 - share) + '%</span></p>' : '') +
      '</div>';
  }
  function sourceRow(t) {
    var who = [t.subjectSpeaker, t.userSpeaker].filter(Boolean).join(' · ');
    var a = String(t.first || '').slice(0, 10);
    var b = String(t.last || '').slice(0, 10);
    var period = a || b ? (a === b || !b ? a : !a ? b : a + ' ~ ' + b) : (t.date || '-');
    var host = hostOf(t.sourceUrl);
    var reg = registerOf(t);
    return '<tr><td><span class="src-name">' + esc(t.textId) + '</span>' +
      (host ? ' <a class="fact-chip" href="' + esc(t.sourceUrl) + '" target="_blank" rel="noopener noreferrer" title="' + esc(host) + '">' + esc(host) + '<span aria-hidden="true">↗</span><span class="sr-only"> (새 탭)</span></a>' : '') + '</td>' +
      '<td>' + esc(TEXT_KIND_KO[t.kind] || '그 밖') + '</td>' +
      '<td><span class="src-reg is-' + (reg === 'FORMAL' ? 'formal' : reg === 'CASUAL' ? 'casual' : 'none') + '">' + esc(REGISTER_KO[reg] || '-') + '</span></td>' +
      '<td>' + esc(who || '-') + '</td>' +
      '<td class="num">' + num(t.subjectMessages) + ' / ' + num(t.messages) + '</td><td class="num">' + num(t.conversations) + '</td><td class="num">' + esc(period) + '</td></tr>';
  }
  function sourceTable(rows) {
    return '<table class="metric-table src-table"><colgroup><col class="c-name"><col class="c-kind"><col class="c-reg"><col class="c-who"><col class="c-msg"><col class="c-conv"><col class="c-date"></colgroup>' +
      '<thead><tr><th scope="col">원문</th><th scope="col">종류</th><th scope="col">말한 자리</th><th scope="col">화자 (대상 · 상대)</th><th scope="col" class="num">대상 인물 / 전체 메시지</th><th scope="col" class="num">대화</th><th scope="col" class="num">날짜</th></tr></thead>' +
      '<tbody>' + rows.map(sourceRow).join('') + '</tbody></table>';
  }
  function renderSourcePack(items) {
    var counts = items.counts || {};
    var usage = items.usage || {};
    var subject = items.subject || {};
    var agent = items.agent || {};
    var kpi = function (label, value, tone) {
      return '<div class="kpi' + (tone ? ' is-' + tone : '') + '"><span>' + esc(label) + '</span><b>' + esc(value) + '</b></div>';
    };
    var photos = items.photos || {};
    var origins = list(photos.origins).filter(Boolean);
    var texts = list(items.texts);
    var head = texts.slice(0, SOURCE_ROWS);
    var rest = texts.slice(SOURCE_ROWS);
    var reps = list(agent.representative).map(function (r) {
      return '<li><p class="bubble is-char"><span>' + esc(DIGEST_KO[r.category] || '기타') + '</span>' + esc(r.text || '(메시지를 찾지 못했어요)') + '</p>' +
        '<p class="src-why">' + esc(r.why) + '</p></li>';
    }).join('');
    var flags = list(agent.piiFlags).map(function (p) {
      return '<li><b>' + esc(p.reason) + '</b>' + (p.text ? '<span class="src-why">' + esc(p.text) + '</span>' : '') + '</li>';
    }).join('');
    var bullets = function (values) {
      return list(values).length ? '<ul class="src-list">' + list(values).map(function (v) { return '<li>' + esc(plainCodes(v)) + '</li>'; }).join('') + '</ul>' : '<p class="section-sub">없어요</p>';
    };
    var notes = String(usage.notes || '');
    var record = isRecord();
    return (
      '<section class="gate-section"><h2>' + (record ? '확인 결과' : '승인 전 확인') + '</h2>' +
      '<p class="section-sub">' + (record ? '결정할 때의 확인 결과예요.' : '빨간 항목이 있으면 승인할 수 없어요. 출처 묶음을 채워 다시 돌린 뒤 승인해 주세요.') + '</p>' +
      '<ul class="pkg-checks">' + sourceChecks(items).map(checkRow).join('') + '</ul></section>' +
      (items.publicFacts ? renderFacts(items.publicFacts) : '') +
      '<section class="gate-section"><h2>정리한 자료</h2>' +
      '<div class="kpis">' + kpi('대화', num(counts.conversations) + '개') + kpi('쓸 대상 인물 메시지', num(counts.corpusSubjectMessages) + '개') +
      kpi('가린 개인정보', num(maskedTotal(items)) + '건') +
      kpi('비교 세트로 뗀 대화', num(counts.holdoutConversations) + '개') + kpi('사진', num(photos.count) + '장') + '</div>' +
      '<p class="section-sub">비교 세트로 뗀 대화는 학습과 프롬프트에 넣지 않고, 나중에 실제 답과 생성 답을 비교할 때만 써요.' +
      (counts.otherParticipants ? ' 다른 참여자 ' + num(counts.otherParticipants) + '명의 이름은 참여자 번호로 바꿨어요.' : '') + '</p>' +
      (texts.length ? sourceMix(texts) : '') +
      '<div class="twin-scroll">' + sourceTable(head) + '</div>' +
      (rest.length ? '<details class="src-more"><summary>나머지 원문 ' + num(rest.length) + '개 보기</summary><div class="twin-scroll">' + sourceTable(rest) + '</div></details>' : '') +
      '<p class="section-sub">표의 숫자는 비교 세트를 떼기 전 전체예요. 위의 쓸 메시지 수는 비교 세트를 뺀 수예요.</p>' +
      '<p class="section-sub">사진 ' + num(photos.count) + '장' + (origins.length ? ' · 받은 곳: ' + esc(origins.join(', ')) : '') + '. 사진은 다음 관문(기준 사진)에서 크게 보고 골라요.</p></section>' +
      '<section class="gate-section"><h2>대상과 메모</h2>' +
      facts([
        ['대상', (subject.displayName || '-') + ' · ' + (SUBJECT_KO[subject.kind] || '구분 없음')],
        ['쓰는 곳', usage.scope || '팀 내부 사용']
      ]) +
      (notes ? (notes.length > 160
        ? '<details class="src-notes"><summary>메모 보기 · ' + num(notes.length) + '자</summary><p>' + esc(notes) + '</p></details>'
        : '<p class="src-notes-text">' + esc(notes) + '</p>') : '') + '</section>' +
      '<section class="gate-section"><h2>출처 정리 에이전트 의견</h2>' +
      '<p class="section-sub">에이전트가 정리한 원문 일부를 읽고 남긴 의견이에요.' + (record ? '' : ' 참고만 하고 결정은 직접 해 주세요.') + '</p>' +
      '<h3 class="twin-h">대표 메시지 ' + list(agent.representative).length + '개</h3>' +
      (reps ? '<ul class="src-msgs">' + reps + '</ul>' : '<p class="section-sub">없어요</p>') +
      '<h3 class="twin-h">말투 관찰</h3>' + bullets(agent.observations) +
      '<h3 class="twin-h">더 가릴 것</h3>' + (flags ? '<ul class="src-list src-flags">' + flags + '</ul>' : '<p class="section-sub">없어요</p>') +
      '<h3 class="twin-h">자료 품질</h3>' + bullets(agent.qualityNotes) + '</section>' +
      (record ? '' : '<section class="gate-section"><h2>수정 요청할 점</h2>' +
      '<p class="section-sub">출처를 고쳐 다시 정리해야 할 때만 적어 주세요. 예: 화자가 바뀌었어요, 이 대화는 빼 주세요.</p>' +
      '<textarea data-source-note placeholder="예: 두 번째 카톡 파일의 화자가 바뀌었어요"></textarea>' +
      '<details class="card-tech"><summary>상세 · 출처 판</summary>출처 판: ' + esc(items.sourceRev || '-') +
      (list(items.usageProblems).length ? '\n승인 잠김 사유:\n- ' + list(items.usageProblems).map(esc).join('\n- ') : '') + '</details></section>')
    );
  }
  function sourceLocked() {
    return state.kind === 'sourcePack' && list(state.items.usageProblems).length > 0;
  }
  function paintSourceSide() {
    if (state.kind !== 'sourcePack') return;
    var items = state.items;
    var checks = sourceChecks(items);
    var bad = checks.filter(function (c) { return c.tone === 'bad'; });
    var warn = checks.filter(function (c) { return c.tone === 'warn'; });
    var counts = items.counts || {};
    var side = q('[data-side-extra]');
    // 기록에서는 본문 맨 위 요약과 확인 결과가 같은 내용을 말한다. 옆 칸은 비운다.
    if (isRecord()) { if (side) side.innerHTML = ''; return; }
    var out = qa('[data-exclude-fact]:checked').length;
    if (side) side.innerHTML = '<div class="bg-side"><p class="bg-side-title"><b>출처 확인</b><span>' +
      (checks.length - bad.length - warn.length) + ' / ' + checks.length + ' 통과</span></p>' +
      '<dl class="facts"><dt>대상</dt><dd>' + esc((items.subject || {}).displayName || '-') + '</dd><dt>대화</dt><dd>' + num(counts.conversations) + '개</dd>' +
      (items.publicFacts ? '<dt>공개 사실</dt><dd>' + list(items.publicFacts.items).length + '개' + (out ? ' · 뺄 사실 ' + out + '개' : '') + '</dd>' : '') +
      '<dt>비교 세트</dt><dd>' + num(counts.holdoutConversations) + '개</dd><dt>확인 필요</dt><dd>' + warn.length + '</dd><dt>막는 문제</dt><dd>' + bad.length + '</dd></dl></div>';
    if (faceLocked()) return;
    var approve = q('[data-decide="APPROVE"]');
    if (approve) approve.disabled = Boolean(state.busy || sourceLocked());
    var hint = q('[data-side-hint]');
    if (hint) hint.textContent = sourceLocked()
      ? '출처 묶음에 막는 문제가 있어 승인할 수 없어요. 본문 아래 상세에서 이유를 보고, 수정 요청을 보내거나 출처 묶음을 채워 다시 돌려 주세요.'
      : warn.length ? '확인할 항목 ' + warn.length + '개가 있지만 승인할 수 있어요. 승인하면 기준 사진과 기획이 이어서 만들어져요.'
      : '모두 갖췄어요. 승인하면 기준 사진과 기획이 이어서 만들어져요.';
  }
  function buildSourcePack(decision) {
    var answer = { decision: decision };
    if (state.items.publicFacts) answer.excludedFactIds = qa('[data-exclude-fact]:checked').map(function (el) { return el.value; });
    if (decision === 'APPROVE' && sourceLocked()) throw Error('출처 묶음에 막는 문제가 있어 승인할 수 없어요. 출처 묶음을 채워 다시 돌려 주세요.');
    if (decision === 'REQUEST_CHANGES') {
      var box = q('[data-source-note]');
      var note = box ? box.value.trim() : '';
      if (!note) { focusField(box); throw Error('수정 요청할 점을 적어 주세요.'); }
      answer.requestedChanges = [{ field: 'source', note: note }];
    }
    var more = details();
    if (answer.requestedChanges && !more.reasons) more.reasons = answer.requestedChanges[0].note;
    return Object.assign(answer, more);
  }

  // ---------------------------------------------------------------- G1s 기준 사진(모티브, 사람 전용)
  // G1 얼굴 고르기 갤러리 부품(face-grid·face-tile·face-side)을 그대로 쓴다. 첫 사진이 기본이다.
  function photoList() {
    return list(state.items.photos);
  }
  function photoById(id) {
    return photoList().filter(function (p) { return p.photoId === id; })[0] || null;
  }
  function photoThumb(p, cls) {
    return p.file && p.file.url
      ? '<img class="' + (cls || '') + '" src="' + esc(p.file.url) + '" alt="' + esc('기준 사진 후보 ' + p.n) + '" loading="lazy">'
      : '<span class="face-missing">파일 없음</span>';
  }
  function renderPhotos(items) {
    var photos = photoList();
    if (!state.photo) {
      var rec = state.view && state.view.record;
      var chosen = rec ? list(rec.selections).filter(function (id) { return photoById(id); })[0] : '';
      state.photo = chosen || ((photos.filter(function (p) { return p.default; })[0] || photos[0] || {}).photoId || '');
    }
    return (
      '<section class="gate-section face-gallery"><h2>기준 사진 후보 ' + photos.length + '장</h2>' +
      '<p class="section-sub">' + esc(items.helper || '') + ' 숫자 키 1~9로 골라요.</p>' +
      '<div class="face-grid photo-grid" data-photo-grid></div></section>' +
      '<section class="gate-section"><h2>다시 받을 때 고칠 점</h2>' +
      '<p class="section-sub">마음에 드는 사진이 없을 때만 적어 주세요. 출처 묶음에 사진을 더 넣어 다시 돌려요.</p>' +
      '<textarea data-photo-note placeholder="예: 정면 사진이 없어요. 최근 사진으로 더 넣어 주세요"></textarea></section>'
    );
  }
  function paintPhotos() {
    if (state.kind !== 'sourcePhotos') return;
    var grid = q('[data-photo-grid]');
    if (!grid) return;
    var locked = faceLocked();
    grid.innerHTML = photoList().map(function (p, i) {
      var on = state.photo === p.photoId;
      return '<div class="face-tile' + (on ? ' is-picked' : '') + '">' +
        '<button type="button" class="face-pick" data-photo-pick="' + esc(p.photoId) + '" aria-pressed="' + on + '"' + (locked ? ' disabled' : '') + '>' +
        photoThumb(p) + '<span class="face-cap"><b>' + p.n + '</b>' + (p.default ? '<span class="badge-chip">기본</span>' : '') +
        (i < 9 ? '<kbd>' + (i + 1) + '</kbd>' : '') + '</span>' +
        '<span class="card-sub photo-desc">' + esc(p.descriptionKo || '') + '</span></button></div>';
    }).join('');
    var host = q('[data-side-extra]');
    var p = photoById(state.photo);
    if (host) {
      host.innerHTML = p
        ? '<div class="face-side">' + photoThumb(p, 'big') +
          '<p class="face-side-title"><b>사진 ' + p.n + '</b>' + (p.default ? '<span class="badge-chip">기본</span>' : '') + '</p>' +
          '<dl class="facts">' + list(p.tags).slice(0, 6).map(function (tag) { return '<dt>' + esc(tag.label) + '</dt><dd>' + esc(tag.text) + '</dd>'; }).join('') + '</dl>' +
          (list(p.tags).length ? '' : '<p class="section-sub">' + esc(p.descriptionKo || '') + '</p>') +
          '<details class="card-tech"><summary>상세</summary>사진 ID: ' + esc(p.photoId) + '\n' + esc(p.descriptionEn || '') + (p.notes ? '\n' + esc(p.notes) : '') + '</details></div>'
        : '<p class="face-side-empty">사진을 고르면 여기에 크게 보여요.</p>';
    }
    var primary = q('[data-decide="SELECT"]');
    if (primary && !locked) {
      primary.textContent = p ? ro('사진 ' + p.n) + ' 확정' : '이 사진으로 확정';
      primary.disabled = Boolean(state.busy || !p);
    }
  }
  function pickPhoto(id) {
    if (faceLocked() || !photoById(id)) return;
    state.photo = id;
    paintPhotos();
  }
  function onPhotoKey(event) {
    if (state.kind !== 'sourcePhotos' || event.altKey || event.ctrlKey || event.metaKey) return;
    var tag = event.target && event.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    if (/^[1-9]$/.test(String(event.key))) {
      var p = photoList()[Number(event.key) - 1];
      if (p) { event.preventDefault(); pickPhoto(p.photoId); }
    }
  }
  function buildPhotos(decision) {
    var answer = { decision: decision };
    if (decision === 'SELECT') {
      if (!photoById(state.photo)) throw Error('사진 하나를 골라 주세요.');
      answer.selections = [state.photo];
    }
    if (decision === 'REQUEST_CHANGES') {
      var box = q('[data-photo-note]');
      var note = box ? box.value.trim() : '';
      if (!note) { focusField(box); throw Error('아래 칸에 다시 받을 때 고칠 점을 적어 주세요.'); }
      answer.requestedChanges = [{ field: 'photos', note: note }];
    }
    var more = details();
    if (answer.requestedChanges && !more.reasons) more.reasons = answer.requestedChanges[0].note;
    return Object.assign(answer, more);
  }

  // 출시 전 점검표(D-0114): 자동 점검과 사람이 볼 항목을 위에 두고, 세부 내용은 항목을 눌러 연다.
  var PKG_AFTER = '승인하면 다음 단계인 우리 앱 내보내기로 넘어가요. 자동 이어 실행이 켜져 있으면 바로 시작하고, 시험용 DB에서 먼저 확인해요.';
  var PKG_MANUAL = [
    ['copy', '프로필 문구와 챕터 소개를 읽어 봤어요'],
    ['media', '대표 이미지와 영상을 열어 봤어요'],
    ['names', '실제 사람 이름이나 상호가 들어가지 않았어요']
  ];
  // 모티브 발표 점검(D-0126): 서버가 만든 presentation-check.json의 자동 결과와 사람 확인 항목.
  // 모티브는 본인 이름이 들어가는 게 맞으니 이름 항목을 '다른 사람'으로 바꾼다.
  var PKG_TWIN_NAMES = '본인 말고 다른 실제 사람 이름이나 상호가 들어가지 않았어요';
  function pkgPresentation() {
    return (state.items && state.items.presentation) || null;
  }
  function pkgManual() {
    var pres = pkgPresentation();
    var out = PKG_MANUAL.map(function (m) {
      return { id: m[0], title: pres && m[0] === 'names' ? PKG_TWIN_NAMES : m[1], required: true };
    });
    if (pres) list(pres.humanChecks).forEach(function (h) {
      out.push({ id: 'pres:' + h.id, presId: h.id, title: h.title, detail: h.detail, required: Boolean(h.required), presentation: true });
    });
    return out;
  }
  function pkgRestoreManual() {
    var rec = (state.view && state.view.record) || {};
    var reasons = String(rec.reasons || '');
    pkgManual().forEach(function (m) {
      // 승인 기록의 사람 확인 요약("[예] 항목")에서 권장 항목의 답을 되살린다.
      state.pkgManual[m.id] = m.presentation && !m.required ? reasons.indexOf('[예] ' + m.title) >= 0 : rec.decision === 'APPROVE' || !m.presentation;
    });
  }
  function pkgChecks() {
    var items = state.items;
    var pkg = items.package || {};
    var profile = pkg.profile || {};
    var counts = items.counts || {};
    var out = [];
    var need = [['name', '이름'], ['age', '나이'], ['gender', '성별'], ['job', '직업'], ['tagline', '한 줄 소개'], ['hobby', '취미'], ['likes', '좋아함'], ['dislikes', '싫어함'], ['mbti', 'MBTI']];
    var empty = need.filter(function (f) { return !profile[f[0]]; }).map(function (f) { return f[1]; });
    out.push({ id: 'profile', title: '프로필 카드', ok: !empty.length, block: !profile.name, detail: empty.length ? '비어 있는 칸: ' + empty.join(', ') : '칸 ' + need.length + '개가 모두 채워졌어요' });
    var chapters = list(pkg.chapters);
    var noIntro = chapters.filter(function (c) { return !c.intro; }).length;
    out.push({ id: 'chapters', title: '챕터', ok: chapters.length > 0 && !noIntro, block: !chapters.length, detail: chapters.length ? '챕터 ' + chapters.length + '개' + (noIntro ? ' · 소개가 빈 챕터 ' + noIntro + '개' : ' · 모두 소개가 있어요') : '챕터가 없어요' });
    var videos = list(pkg.videos);
    var intro = videos.filter(function (v) { return v.kind === 'INTRO'; }).length;
    var acts = videos.filter(function (v) { return v.kind === 'ACTION'; }).length;
    var fake = videos.filter(function (v) { return v.synthetic; }).length;
    out.push({ id: 'videos', title: '영상', ok: intro > 0 && acts > 0 && !fake, warn: fake > 0, block: !videos.length, detail: '소개 ' + intro + '개 · 동작 ' + acts + '개' + (fake ? ' · 가짜 공급자 영상 ' + fake + '개가 섞여 있어요' : '') });
    var sft = pkg.sft || {};
    var learned = sft.adoptedBinding && sft.adoptedBinding !== 'LONG_BASE';
    out.push({ id: 'persona', title: '페르소나·학습', ok: Boolean(sft.adoptedBinding), warn: !learned, detail: learned ? '학습한 모델을 써요 · 데이터셋 ' + (sft.datasetRev || '-') : '학습 없이 긴 프롬프트로 진행해요' + (sft.evalReport ? ' · 평가 보고서 있음' : '') });
    var decided = {};
    list(pkg.gates).forEach(function (g) { if (g.decision !== 'REQUEST_CHANGES' && g.decision !== 'REJECT') decided[g.gate] = true; });
    // 이 캐릭터 그래프의 관문(G7a 포함, 모티브는 G0·G1s)을 기준으로 본다(QA v5 C-15).
    var pkgGates = H.packageGates(state.character && state.character.gates);
    var missingGates = pkgGates.filter(function (g) { return !decided[g]; });
    out.push({ id: 'gates', title: '관문 기록', ok: !missingGates.length, warn: missingGates.length > 0, detail: missingGates.length ? '기록이 없는 관문: ' + missingGates.map(function (g) { return GATE_KO[g] || g; }).join(', ') : '관문 ' + pkgGates.length + '개를 모두 결정했어요' });
    var missing = list(counts.missing);
    out.push({ id: 'files', title: '파일', ok: !missing.length, block: missing.length > 0, detail: missing.length ? '빠진 파일 ' + missing.length + '개' : '파일 ' + (counts.files || 0) + '개, 빠진 파일 없음' });
    var ver = items.verification || {};
    out.push({ id: 'verify', title: '앱 적재 확인', ok: ver.status === 'PASSED' || ver.status === 'OK', info: ver.status === 'NOT_RUN' || !ver.status, detail: ver.status === 'NOT_RUN' || !ver.status ? '승인한 뒤 내보내기 단계에서 시험용 DB로 확인해요' : '상태: ' + ver.status });
    var pres = pkgPresentation();
    if (pres) list(pres.checks).forEach(function (c) {
      out.push({ id: 'presentation', title: '발표 · ' + c.title, ok: Boolean(c.ok), block: c.required !== false, detail: c.detail });
    });
    return out;
  }
  function pkgPresentationBlock(pres) {
    var hits = [];
    list(pres.checks).forEach(function (c) { list(c.hits).forEach(function (h) { hits.push(h); }); });
    var endorsement = list(pres.checks).filter(function (c) { return c.id === 'endorsement'; })[0] || {};
    var disclosure = list(pres.checks).filter(function (c) { return c.id === 'disclosure'; })[0] || {};
    var consent = list(pres.checks).filter(function (c) { return c.id === 'consent'; })[0] || {};
    var places = disclosure.places || {};
    return facts([
      ['표시 문구', pres.disclosure],
      ['표시 위치', [['package', '패키지'], ['appSeed', '앱 시드'], ['chat', '대화 프롬프트']].map(function (p) { return p[1] + (places[p[0]] ? ' ✓' : ' ✕'); }).join(' · ')],
      ['대상', pres.subjectKind === 'PUBLIC_FIGURE' ? '공인' : pres.subjectKind === 'PRIVATE_PERSON' ? '사인(가족·지인)' : '-'],
      ['공개 동의', consent.detail],
      ['찾는 표현', joinList(endorsement.terms, ', ')]
    ]) +
      (hits.length
        ? '<table class="gate-table pres-hits"><thead><tr><th>위치</th><th>표현</th><th>앞뒤 문장</th></tr></thead><tbody>' +
          hits.map(function (h) { return '<tr><td>' + esc(h.where) + '</td><td><b>' + esc(h.term) + '</b></td><td>' + esc(h.excerpt) + '</td></tr>'; }).join('') + '</tbody></table>' +
          '<p class="qa-note">문구를 고친 뒤 패키지를 다시 만들면 다시 점검해요. 다른 뜻으로 쓴 말이면 설정의 찾는 표현 목록을 바꿀 수 있어요.</p>'
        : '<p class="qa-note">추천·협력·공식처럼 보이는 표현을 찾지 못했어요.</p>');
  }
  function renderPackage(items) {
    if (!state.pkgRestored) {
      state.pkgRestored = true;
      if (faceLocked()) pkgRestoreManual();
    }
    var pkg = items.package || {};
    var pres = items.presentation || null;
    var profile = pkg.profile || {};
    var profileRows = [
      ['이름', profile.name],
      ['성별·나이', (GENDER_KO[profile.gender] || profile.gender || '') + ' · ' + (profile.age ? profile.age + '세' : '')],
      ['직업', profile.job], ['한 줄', profile.tagline], ['소개', profile.description], ['취미', profile.hobby],
      ['좋아함', profile.likes], ['싫어함', profile.dislikes], ['MBTI', profile.mbti],
      ['태그', joinList(profile.tags, ', ')],
      ['TMI', list(profile.tmiItems).map(function (t) { return t.text; }).join(' / ')]
    ];
    var sft = pkg.sft || {};
    var verification = items.verification || {};
    var block = function (id, title, body) {
      return '<details class="gate-more pkg-detail" data-pkg-detail="' + id + '"' + (state.pkgOpen[id] ? ' open' : '') + '><summary>' + esc(title) + '</summary>' + body + '</details>';
    };
    return (
      (pres ? '<p class="pres-label" role="note"><span>발표 표시</span><b>' + esc(pres.disclosure) + '</b></p>' : '') +
      '<section class="gate-section pkg-board"><h2>출시 전 점검</h2>' +
      '<p class="section-sub">' + (faceLocked() ? '승인할 때 확인한 점검표예요.' : '자동 점검을 확인하고, 사람이 볼 항목에 표시한 뒤 승인해 주세요. 항목을 누르면 아래에서 자세히 볼 수 있어요.') + '</p>' +
      '<ul class="pkg-checks" data-pkg-checks></ul>' +
      '<h3 class="pkg-sub">사람이 볼 항목</h3><ul class="pkg-checks pkg-manual" data-pkg-manual></ul></section>' +
      '<section class="gate-section pkg-details">' +
      block('profile', '프로필 카드', '<div class="profile-card">' + profileRows.filter(function (r) { return r[1] && String(r[1]).replace(/[ ·]/g, ''); }).map(function (r) {
        return '<div><b>' + esc(r[0]) + '</b>' + esc(r[1]) + '</div>';
      }).join('') + '</div>') +
      block('chapters', '챕터 ' + list(pkg.chapters).length + '개', '<table class="gate-table"><thead><tr><th>#</th><th>제목</th><th>관계 단계</th><th>소개</th></tr></thead><tbody>' +
        list(pkg.chapters).map(function (c) { return '<tr><td class="num">' + esc(c.chapterNo) + '</td><td>' + esc(c.title) + '</td><td>' + esc(stageLabel(c.relationshipStage)) + '</td><td>' + esc(c.intro) + '</td></tr>'; }).join('') + '</tbody></table>') +
      block('videos', '영상 ' + list(pkg.videos).length + '개', '<table class="gate-table"><thead><tr><th>종류</th><th>챕터</th><th>길이</th><th>출처</th></tr></thead><tbody>' +
        list(pkg.videos).map(function (v) {
          return '<tr><td>' + esc({ INTRO: '소개', ACTION: '동작' }[v.kind] || v.kind) + '</td><td>' + esc(v.chapterNo || '-') + '</td><td>' + (v.durationS ? esc(v.durationS) + '초' : '-') + '</td><td>' + (v.synthetic ? '가짜 공급자' : '실제') + '</td></tr>';
        }).join('') + '</tbody></table>') +
      block('persona', '페르소나·학습', facts([
        ['페르소나 버전', (pkg.persona || {}).personaVersion],
        ['데이터셋', sft.datasetRev],
        ['학습 기록', joinList(sft.trainingRuns, ' / ')],
        ['평가 보고서', sft.evalReport || (sft.adoptedBinding === 'LONG_BASE' ? '없음 · 학습 없이 긴 프롬프트로 진행' : '없음')],
        ['쓰는 모델', sft.adoptedBinding === 'LONG_BASE' ? '긴 프롬프트' : sft.adoptedBinding]
      ])) +
      block('gates', '관문 기록', '<table class="gate-table"><thead><tr><th>관문</th><th>버전</th><th>결정</th></tr></thead><tbody>' +
        list(pkg.gates).map(function (g) { return '<tr><td>' + esc((GATE_KO[g.gate] || g.gate)) + '</td><td>' + esc(revLabel(g.rev)) + '</td><td>' + esc(DECISION_KO[g.decision] || g.decision) + '</td></tr>'; }).join('') + '</tbody></table>') +
      block('files', '파일', facts([['파일 수', (items.counts || {}).files], ['빠진 파일', joinList((items.counts || {}).missing, ', ') || '없음']])) +
      block('verify', '앱 적재 확인', facts([['상태', verification.status === 'NOT_RUN' ? '아직 안 함' : verification.status], ['시험용 DB에서 확인', verification.disposableDb ? '예' : '아니오']]) +
        list(verification.steps).map(function (step) { return '<p class="qa-note">' + (step.ok ? '✓ ' : '· ') + esc(step.name) + ' — ' + esc(step.detail) + '</p>'; }).join('')) +
      (pres ? block('presentation', '발표 점검', pkgPresentationBlock(pres)) : '') +
      '</section>'
    );
  }
  function paintPackage() {
    if (state.kind !== 'package') return;
    var host = q('[data-pkg-checks]');
    if (!host) return;
    var locked = faceLocked();
    var checks = pkgChecks();
    host.innerHTML = checks.map(function (c) {
      var tone = c.block && !c.ok ? 'bad' : c.ok && !c.warn ? 'ok' : c.info ? 'info' : 'warn';
      var mark = { ok: '✓', bad: '✕', warn: '!', info: 'i' }[tone];
      return '<li><button type="button" class="pkg-check is-' + tone + '" data-pkg-jump="' + c.id + '"><span class="pkg-mark" aria-hidden="true">' + mark + '</span>' +
        '<b>' + esc(c.title) + '</b><span class="pkg-detail-text">' + esc(c.detail) + '</span><span class="sr-only">' + ({ ok: ' 통과', bad: ' 막힘', warn: ' 확인 필요', info: ' 안내' }[tone]) + '</span></button></li>';
    }).join('');
    var manual = pkgManual();
    q('[data-pkg-manual]').innerHTML = manual.map(function (m) {
      var on = Boolean(state.pkgManual[m.id]);
      var tag = m.presentation ? '<span class="pres-tag' + (m.required ? ' is-required' : '') + '">' + (m.required ? '발표 · 필수' : '발표 · 권장') + '</span>' : '';
      return '<li><label class="pkg-check pkg-manual-row' + (m.presentation ? ' pres-row' : '') + (on ? ' is-ok' : '') + '"><input type="checkbox" data-pkg-manual-box="' + esc(m.id) + '"' + (on ? ' checked' : '') + (locked ? ' disabled' : '') + '>' +
        '<span class="pres-text"><b>' + esc(m.title) + '</b>' + tag + (m.detail ? '<span class="pkg-detail-text">' + esc(m.detail) + '</span>' : '') + '</span></label></li>';
    }).join('');
    var ok = checks.filter(function (c) { return c.ok && !c.warn; }).length;
    var warn = checks.filter(function (c) { return c.warn || (!c.ok && !c.block && !c.info); }).length;
    var blocks = checks.filter(function (c) { return c.block && !c.ok; });
    var manualLeft = manual.filter(function (m) { return m.required && !state.pkgManual[m.id]; }).length;
    var manualDone = manual.filter(function (m) { return state.pkgManual[m.id]; }).length;
    var side = q('[data-side-extra]');
    if (side) side.innerHTML = '<div class="bg-side"><p class="bg-side-title"><b>점검</b><span>' + ok + ' / ' + checks.length + ' 통과</span></p>' +
      '<dl class="facts"><dt>확인 필요</dt><dd>' + warn + '</dd><dt>막는 문제</dt><dd>' + blocks.length + '</dd><dt>사람 확인</dt><dd>' + manualDone + ' / ' + manual.length + '</dd></dl></div>';
    if (locked) return;
    var approve = q('[data-decide="APPROVE"]');
    if (approve) approve.disabled = Boolean(state.busy || blocks.length || manualLeft);
    var hint = q('[data-side-hint]');
    if (hint) hint.textContent = blocks.length ? blocks.map(function (c) { return c.title; }).join(', ') + '에 막는 문제가 있어요. 고친 뒤 승인할 수 있어요.'
      : manualLeft ? '꼭 확인할 항목 ' + manualLeft + '개가 남았어요. 확인하고 표시해 주세요.'
      : warn ? '확인할 항목 ' + warn + '개가 있지만 승인할 수 있어요. ' + PKG_AFTER
      : '모두 통과했어요. ' + PKG_AFTER;
  }

  function buildPackage(decision) {
    var answer = { decision: decision };
    if (decision === 'APPROVE') {
      var blocks = pkgChecks().filter(function (c) { return c.block && !c.ok; });
      if (blocks.length) throw Error(blocks.map(function (c) { return c.title; }).join(', ') + '에 막는 문제가 있어요.');
      if (pkgManual().some(function (m) { return m.required && !state.pkgManual[m.id]; })) throw Error('꼭 확인할 항목을 모두 표시해 주세요.');
    }
    if (pkgPresentation()) {
      // 서버(presentation.guard_g9)가 필수 항목을 다시 확인하고 결정 기록에 요약을 남긴다.
      answer.presentationChecks = {};
      pkgManual().forEach(function (m) { if (m.presentation) answer.presentationChecks[m.presId] = Boolean(state.pkgManual[m.id]); });
    }
    return Object.assign(answer, details());
  }

  // ---------------------------------------------------------------- 렌더
  function connectionLabel(view) {
    if (view && view.connected === false) return '아직 연결 전';
    if (view && (view.status === 'APPROVED' || view.status === 'REJECTED')) return '결정 완료';
    return view && view.status === 'AWAITING_HUMAN' ? '결정 가능' : '단계 대기';
  }

  function banner(kind, title, body) {
    return (
      '<div class="gate-banner is-' + kind + '"><b>' + esc(title) + '</b>' + esc(body) + '</div>'
    );
  }

  function renderBanners(view, items) {
    var out = [];
    if (view.connected === false) {
      out.push(
        banner(
          'synthetic',
          '아직 연결 전',
          '이 관문은 아직 공장 단계와 연결되지 않았어요. 지금 보이는 자료는 화면 확인용 예시이고, ' +
            '결정을 보내도 기록되지 않아요.'
        )
      );
    }
    if (view.synthetic) {
      out.push(banner('warn', '화면 확인용 예시', '실제 산출물이 아직 없어 예시 자료를 보여 줘요.'));
    }
    list(view.missing).forEach(function (problem) {
      out.push(problemBanner(problem));
    });
    if (isRecord()) {
      out.push(recordCard(view.record));
    } else if (view.record && view.status !== 'AWAITING_HUMAN') {
      // 검토가 아직 열려 있으면(G7a처럼 묶음마다 보내는 관문) 결정을 끝낸 것처럼 보이지 않는다.
      out.push(
        banner(
          'ok',
          '이미 결정했어요',
          (DECISION_KO[view.record.decision] || '결정') +
            (view.record.reviewer && view.record.reviewer !== 'user' ? ' · ' + view.record.reviewer : '') +
            (view.record.decidedAt ? ' · ' + whenKo(view.record.decidedAt) : '')
        )
      );
    }
    // '내 차례예요'·'검토 모델 의견 없음'은 머리줄 상태·칩으로 옮겨 본문을 밀지 않는다(D-0129).
    if (view.status === 'PENDING' && view.connected !== false) {
      out.push(
        banner('warn', '아직 차례가 아니에요', '앞 단계가 끝나야 이 관문이 열려요. 먼저 작업을 돌려 주세요.')
      );
    }
    // 다시 만든 버전에는 지난 버전에 남긴 수정 요청을 보인다. G4·G5b는 챕터·칸마다 따로 보여 준다.
    if (!isRecord() && view.status === 'AWAITING_HUMAN' && ['frames', 'actions', 'samples'].indexOf(state.kind) < 0) {
      var ask = H.previousAsk(view);
      if (ask) out.push(banner('muted', '다시 만든 버전', '지난 요청: ' + ask));
    }
    var rework = view.rework || {};
    if (rework.capReached) {
      out.push(
        banner(
          'bad',
          '수정 요청을 모두 썼어요',
          '이 관문의 수정 요청 횟수를 다 썼어요. 더 고치려면 수정 횟수를 한 번 더 허락해야 해요.'
        )
      );
    }
    if (reviewEnabled() && view.status !== 'PENDING' && !isRecord()) {
      if (view.review) {
        var reviewer = view.review.reviewer || {};
        var who = [reviewer.provider, reviewer.model].filter(Boolean).join(' · ');
        var summary = view.review.summary || '후보마다 근거를 카드에 붙였어요.';
        var concern = list(view.review.items).some(function (item) {
          return item.verdict === 'CONCERN';
        });
        var missing = summary.indexOf('빠진 파일') >= 0 && summary.indexOf('빠진 파일 없음') < 0;
        out.push(
          banner(
            concern || missing ? 'warn' : 'ok',
            '검토 모델 의견 · 추천은 참고예요',
            summary + (who ? ' (' + who + ')' : '')
          )
        );
      }
    }
    return out.join('');
  }

  function renderActionsBar(view, meta) {
    var host = q('[data-actions]');
    var locked = view.status === 'APPROVED' || view.status === 'REJECTED';
    var actions = (meta.actionsFor && meta.actionsFor(state.items)) || meta.actions;
    host.innerHTML = actions
      .filter(function (action) {
        return !(state.kind === 'planVariants' && state.items.requireExplicitSelection && action[0] === 'APPROVE');
      })
      .map(function (action) {
        var decision = action[0];
        var label = action[1];
        var style = action[2];
        return (
          '<button type="button" class="btn btn--' + style + ' btn--wide" data-decide="' +
          esc(decision) + '"' + (locked ? ' disabled' : '') + '>' + esc(label) + '</button>'
        );
      })
      .join('');
  }

  function renderRaw(view) {
    var raw = q('[data-raw]');
    raw.hidden = false;
    q('[data-files]').innerHTML = list(view.files)
      .slice(0, 60)
      .map(function (file) {
        return '<li><a href="' + esc(file.url) + '" target="_blank" rel="noopener">' +
          esc(file.path) + '</a></li>';
      })
      .join('');
    q('[data-records]').textContent = view.records && view.records.length
      ? list(view.records).map(function (record) {
          return JSON.stringify(record.record, null, 2);
        }).join('\n\n')
      : '결정 기록이 아직 없어요';
  }

  function render() {
    var view = state.view;
    var items = state.items;
    var meta = KINDS[state.kind];
    state.review = view.review || null;
    state.reviewIndex = {};
    list(state.review && state.review.items).forEach(function (item) {
      if (item && item.candidateId) state.reviewIndex[item.candidateId] = item;
    });
    var summary = (state.character && state.character.summary) || {};
    // 기획 전 모티브는 원문에서 정한 표시 이름을 쓴다. 이름이 아직 없을 때만 '이름 미정 · slug (11/7)'(D-0129).
    var name = H.characterName(summary, state.characterId);
    var back = 'c-glass.html?character=' + encodeURIComponent(state.characterId) +
      '&gate=' + encodeURIComponent(state.gate);
    var record = isRecord();
    document.body.classList.toggle('gate-record', record);
    q('[data-workroom-link]').setAttribute('href', back);
    q('[data-crumbs]').innerHTML =
      '<a href="c-glass.html">작업실</a> › <a href="' + esc(back) + '">' + esc(name) +
      '</a> › <b>' + esc(view.title || '검토') + '</b>';
    var status = q('[data-gate-status]');
    status.textContent =
      ((view.status && STATUS_KO[view.status]) || view.status || '-') +
      ' · ' +
      connectionLabel(view);
    status.className =
      'gate-status' +
      (view.status === 'AWAITING_HUMAN' ? ' is-awaiting' : '') +
      (view.status === 'APPROVED' ? ' is-approved' : '') +
      (view.status === 'REJECTED' ? ' is-rejected' : '');
    q('[data-kicker]').textContent = name;
    q('[data-title]').textContent = view.title || '검토';
    var hint = (meta && ((meta.hintFor && meta.hintFor(items)) || meta.hint)) || '';
    // 기록에서는 '확인해요·승인하면' 같은 결정 안내와 버전·상태 줄을 감춘다. 요약 카드가 대신 말한다.
    q('[data-desc]').textContent = record ? '' : hint;
    q('[data-desc]').hidden = record;
    q('[data-meta]').hidden = record;
    q('[data-meta]').innerHTML = record ? '' :
      '<span>' + esc(revLabel(view.rev)) + '</span>' +
      '<span>' + esc(STATUS_KO[view.status] || view.status || '-') + '</span>' +
      (reviewEnabled() && !view.review && view.status === 'AWAITING_HUMAN' ? '<span class="gate-chip" title="미리 검토한 기록이 없어요. 추천 없이 직접 골라 주세요.">검토 모델 의견 없음</span>' : '') +
      (view.rework && view.rework.round
        ? '<span class="gate-chip">수정 ' + esc(view.rework.round) + '/' +
          esc(view.rework.maxRounds == null ? '?' : view.rework.maxRounds) + '</span>'
        : '') +
      '';
    q('[data-banners]').innerHTML = renderBanners(view, items);
    q('[data-body]').innerHTML = meta
      ? meta.render(items)
      : '<p class="empty">이 관문 화면을 아직 지원하지 않아요: ' + esc(state.kind) + '</p>';
    q('[data-side-hint]').textContent = hint;
    var sideTitle = q('.gate-side h2');
    if (sideTitle) sideTitle.textContent = record ? '고른 것' : '결정';
    if (meta) renderActionsBar(view, meta);
    renderRaw(view);
    setStatus('');
    bindBody();
    updateBlind();
    paintFaces();
    paintPlans();
    paintBackgrounds();
    paintPoses();
    paintFrames();
    paintIntro();
    paintActions();
    paintSamples();
    paintPackage();
    paintSourceSide();
    paintPhotos();
    if (['faces', 'planVariants', 'backgrounds', 'poses', 'frames', 'intro', 'actions', 'samples', 'dataset', 'package', 'sourcePack', 'sourcePhotos'].indexOf(state.kind) < 0) paintFaceSide();
    // 기록인데 옆 칸에 보여 줄 것이 없으면 옆 칸을 접고 본문을 넓게 쓴다.
    var extra = q('[data-side-extra]');
    document.body.classList.toggle('gate-side-empty', record && !(extra && extra.textContent.trim()));
  }

  function bindBody() {
    /* 묶음 고르기는 탭(paintSamples)으로 바꿨다(D-0112). */
  }

  // ---------------------------------------------------------------- 전송
  function currentAnswer(decision) {
    var meta = KINDS[state.kind];
    if (!meta) throw Error('이 관문 화면을 아직 지원하지 않아요: ' + state.kind);
    var answer = meta.build(decision);
    if (state.view && state.view.rev) answer.expectedRev = state.view.rev;
    return answer;
  }

  function showAnswer(answer) {
    var out = q('[data-answer-json]');
    out.hidden = false;
    out.textContent = JSON.stringify(answer, null, 2);
  }

  // 반려 확인: 무엇을 버리고 무엇이 남는지 적는다(D-0129).
  function rejectQuestion() {
    var view = state.view || {};
    var title = view.title || GATE_KO[state.gate] || state.gate;
    var paid = state.kind === 'intro' || state.kind === 'actions';
    // 남는 것은 이미 승인한 다른 관문만 적는다. 첫 관문(출처 확인·얼굴 고르기 등)에는 이 줄이 없다.
    var kept = H.keptOnReject(state.character && state.character.gates, state.gate);
    var lines = [title + ' ' + revLabel(view.rev) + '을 반려하면 이 단계를 처음부터 다시 만들어요.'];
    if (kept.length) lines.push('이미 정한 결과는 그대로 둬요: ' + kept.slice(0, 3).join(', ') + (kept.length > 3 ? ' 등' : ''));
    if (paid) lines.push('유료 단계라 다시 만들기 전에 비용 확인을 다시 받아요.');
    lines.push('고칠 부분만 바꾸려면 취소하고 수정 요청을 쓰세요. 반려할까요?');
    return lines.join('\n');
  }
  var NAV_KEYS = '<kbd>J</kbd><kbd>→</kbd> 다음 · <kbd>K</kbd><kbd>←</kbd> 이전';
  function navStep(key) {
    if (key === 'j' || key === 'n' || key === 'arrowright') return 1;
    if (key === 'k' || key === 'p' || key === 'arrowleft') return -1;
    return 0;
  }
  var QUICK_KINDS = ['planVariants', 'backgrounds', 'poses', 'actions'];
  // 일괄 확정은 고른 게 하나라도 있으면 숨기고, 아무것도 고르지 않았을 때만 한 번 더 묻고 보낸다(D-0129).
  function guardQuickApprove(picked) {
    var btn = q('[data-decide="APPROVE"]');
    if (!btn || QUICK_KINDS.indexOf(state.kind) < 0 || faceLocked()) return;
    btn.hidden = picked > 0;
  }
  // 수정 요청·반려는 새 버전을 만들기 시작하므로 몇 초 기다렸다 보낸다. 그동안 취소할 수 있다(D-0129).
  var SEND_DELAY = 5;
  function delayedSend(answer) {
    var left = SEND_DELAY;
    state.busy = true;
    qa('[data-decide]').forEach(function (node) { node.disabled = true; });
    var out = q('[data-status]');
    var tick = function () {
      out.className = 'side-status is-wait';
      out.innerHTML = '<span>' + left + '초 뒤에 보내요.</span> <button type="button" class="btn btn--ghost" data-send-now>지금 보내기</button> <button type="button" class="btn btn--ghost" data-send-cancel>보내기 취소</button>';
    };
    tick();
    state.pendingSend = {
      answer: answer,
      timer: setInterval(function () {
        left -= 1;
        if (left <= 0) { flushSend(); return; }
        tick();
      }, 1000)
    };
  }
  function flushSend() {
    var p = state.pendingSend;
    if (!p) return;
    clearInterval(p.timer);
    state.pendingSend = null;
    state.busy = false;
    postAnswer(p.answer);
  }
  function cancelSend() {
    var p = state.pendingSend;
    if (!p) return;
    clearInterval(p.timer);
    state.pendingSend = null;
    state.busy = false;
    setStatus('보내지 않았어요. 고른 내용은 그대로예요.');
    releaseButtons();
  }
  // 결정 버튼을 다시 풀고 관문별 잠금 조건을 다시 맞춘다.
  function releaseButtons() {
    var locked = state.view && (state.view.status === 'APPROVED' || state.view.status === 'REJECTED');
    qa('[data-decide]').forEach(function (node) { node.disabled = Boolean(locked); });
    updateBlind();
    paintBgMeta();
    paintPoseMeta();
    paintFrameMeta();
    paintIntro();
    paintActionMeta();
    paintSampleMeta();
    paintPackage();
    if (state.kind === 'planVariants') paintPlanSide();
  }

  // 관문마다 쓰는 단축키(D-0129). ?로 열고 Esc로 닫는다.
  var KEYS_COMMON = [['⌘/Ctrl + Enter', '주 버튼 누르기'], ['?', '단축키 보기'], ['Esc', '열린 창 닫기']];
  var KEYS_BY_KIND = {
    faces: [['1 ~ 0', '얼굴 고르기'], ['S', '고른 얼굴 추리기(♡)']],
    planVariants: [['1 ~ 9', '안 고르기']],
    backgrounds: [['1 ~ 9', '후보 고르기 · 마지막 번호는 직접 적기'], ['J / →', '다음 챕터'], ['K / ←', '이전 챕터']],
    poses: [['1 ~ 9', '자세 고르기 · 마지막 번호는 직접 적기'], ['J / →', '다음 챕터'], ['K / ←', '이전 챕터']],
    frames: [['J / →', '크게 보기에서 다음 챕터'], ['K / ←', '크게 보기에서 이전 챕터']],
    intro: [['Space', '모두 재생·멈춤'], ['1 ~ 9', '영상 고르기']],
    actions: [['1 ~ 9', '칸 크게 보기에서 쓰기'], ['X', '칸 크게 보기에서 빼기'], ['J / →', '다음 칸'], ['K / ←', '이전 칸']],
    samples: [['1 · 2 · 3', '쓰기 · 고쳐 쓰기 · 버리기'], ['J / →', '다음 대화'], ['K / ←', '이전 대화']],
    dataset: [['1 · 2 · 3', '쓰기 · 고쳐 쓰기 · 버리기'], ['J / →', '다음 대화'], ['K / ←', '이전 대화']],
    eval: [['1 / A', '앞 응답이 나음'], ['2 / B', '뒤 응답이 나음'], ['3', '비슷함'], ['J / →', '다음 쌍'], ['K / ←', '이전 쌍']],
    sourcePhotos: [['1 ~ 9', '사진 고르기']]
  };
  function toggleKeys(open) {
    var box = q('[data-keys-box]');
    if (!box) {
      box = document.createElement('div');
      box.className = 'frame-zoom';
      box.setAttribute('data-keys-box', '');
      document.body.appendChild(box);
    }
    if (!open) { box.hidden = true; box.innerHTML = ''; return; }
    var kindKeys = state.kind === 'planVariants' && planCandidates().length < 2 ? [] : KEYS_BY_KIND[state.kind];
    var rows = (kindKeys || []).concat(KEYS_COMMON);
    box.hidden = false;
    box.innerHTML = '<div class="frame-zoom-inner keys-inner" role="dialog" aria-modal="true" aria-label="단축키"><div class="frame-zoom-head"><b>이 화면의 단축키</b><button type="button" class="btn btn--ghost" data-keys-close>닫기</button></div>' +
      '<dl class="keys-list">' + rows.map(function (r) { return '<dt><kbd>' + esc(r[0]) + '</kbd></dt><dd>' + esc(r[1]) + '</dd>'; }).join('') + '</dl>' +
      '<p class="section-sub">다음·이전은 모든 관문에서 J·K 또는 ←·→로 같아요. 글을 적는 칸 안에서는 단축키가 꺼져요.</p></div>';
    var c = q('[data-keys-close]', box);
    if (c) c.focus();
  }
  // 모든 관문 공통: ⌘/Ctrl+Enter는 주 버튼, ?는 단축키 목록, Esc는 단축키 창 닫기.
  function onCommonKey(event) {
    var box = q('[data-keys-box]');
    if (event.key === 'Escape' && box && !box.hidden) { event.preventDefault(); event.stopPropagation(); toggleKeys(false); return; }
    // 기록은 읽기만 한다. 주 버튼·단축키 창을 열지 않는다.
    if (isRecord()) return;
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      var primary = qa('[data-decide].btn--primary').filter(function (b) { return !b.hidden && !b.disabled; })[0];
      if (primary) primary.click();
      else setStatus(((q('[data-side-hint]') || {}).textContent || '아직 확정할 수 없어요.'), 'bad');
      return;
    }
    var tag = event.target && event.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    if (event.key === '?') { event.preventDefault(); toggleKeys(!(box && !box.hidden)); }
  }
  // 옆으로 넘겨야 다 보이는 표·줄 아래에 안내를 붙인다(좁은 화면, D-0129).
  function markScroll() {
    qa('.plan-scroll, .bg-strip, .sample-list, .twin-scroll').forEach(function (el) {
      var more = el.scrollWidth > el.clientWidth + 4;
      var hint = el.nextElementSibling;
      if (!hint || !hint.classList || !hint.classList.contains('scroll-hint')) {
        if (!more) return;
        hint = document.createElement('p');
        hint.className = 'scroll-hint';
        el.parentNode.insertBefore(hint, el.nextSibling);
      }
      var end = el.scrollLeft + el.clientWidth >= el.scrollWidth - 4;
      hint.hidden = !more;
      hint.textContent = end ? '← 옆으로 넘겨 앞부분 보기' : '옆으로 넘겨 더 보기 →';
    });
  }
  var scrollTimer = null;
  function queueScrollMark() {
    if (scrollTimer) return;
    scrollTimer = setTimeout(function () { scrollTimer = null; markScroll(); }, 60);
  }
  if (window.MutationObserver) {
    new window.MutationObserver(queueScrollMark).observe(document.body, { childList: true, subtree: true });
  }
  window.addEventListener('resize', queueScrollMark);
  document.addEventListener('scroll', queueScrollMark, true);

  function send(decision) {
    if (state.busy) return;
    if (decision === 'REJECT' && typeof window.confirm === 'function' && !window.confirm(rejectQuestion())) {
      return;
    }
    if (decision === 'APPROVE' && QUICK_KINDS.indexOf(state.kind) >= 0 && typeof window.confirm === 'function' &&
      !window.confirm('후보를 보지 않고 모두 첫 후보로 확정해요. 계속할까요?')) {
      return;
    }
    var answer;
    try {
      answer = currentAnswer(decision);
    } catch (error) {
      setStatus(error.message, 'bad');
      return;
    }
    if (decision === 'REQUEST_CHANGES' || decision === 'REJECT') {
      showAnswer(answer);
      delayedSend(answer);
      return;
    }
    postAnswer(answer);
  }

  function postAnswer(answer) {
    showAnswer(answer);
    state.busy = true;
    qa('[data-decide]').forEach(function (node) {
      node.disabled = true;
    });
    setStatus('저장 중…');
    api
      .decide(state.characterId, state.gate, answer)
      .then(function (data) {
        var gateState = ((data || {}).state || {}).gates || {};
        var recorded = (gateState[state.gate] || {}).status || '';
        var message = '결정을 기록했어요' + (recorded ? ' · ' + (STATUS_KO[recorded] || recorded) : '');
        // 진행 화면 시트 안에서 열렸으면 결정을 바로 알린다. 새 판이 빨리 생겨 상태 변화를
        // 진행 화면이 못 보더라도 시트를 닫고 알림을 남길 수 있다.
        if (params.get('embedded') === '1' && window.parent && window.parent !== window) {
          try {
            window.parent.postMessage(
              {
                type: 'foundry:gate-decided',
                characterId: state.characterId,
                gate: state.gate,
                decision: answer.decision,
                status: recorded
              },
              window.location.origin
            );
          } catch (postError) {
            /* 알림만 못 보낸다. 진행 화면은 다음 갱신에서 상태를 읽는다. */
          }
        }
        // 다시 그리면 상태 줄이 지워지므로 새로 읽은 뒤에 기록 결과를 보여 준다.
        return load().then(function () {
          if (state.kind === 'samples') {
            // 묶음 하나를 보내면 아직 안 보낸 다음 묶음으로 넘어간다.
            var nextCluster = sampleClusters().filter(function (c) { return !sampleSent(c); })[0];
            if (nextCluster) { state.sampleTab = nextCluster.clusterId; state.sampleOpen = ''; paintSamples(); }
          }
          setStatus(message, 'ok');
        });
      })
      .catch(function (error) {
        if (error.status === 501) {
          setStatus('이 관문은 아직 공장 단계와 연결되지 않아 결정을 기록하지 못했어요.', 'bad');
          q('[data-banners]').insertAdjacentHTML(
            'afterbegin',
            banner(
              'synthetic',
              '아직 연결 전',
              '결정을 기록하지 못했어요. 이 관문은 아직 공장 단계와 연결되지 않았어요.'
            )
          );
        } else {
          setStatus(error.message, 'bad');
        }
        qa('[data-decide]').forEach(function (node) {
          node.disabled = false;
        });
      })
      .then(function () {
        // 성공·실패 모두 다음 결정을 보낼 수 있게 푼다(G7a는 클러스터마다 따로 보낸다).
        state.busy = false;
        updateBlind();
        paintBgMeta();
        paintPoseMeta();
        paintFrameMeta();
        paintIntro();
        paintActionMeta();
        paintSampleMeta();
        paintPackage();
        paintSourceSide();
        paintPhotos();
      });
  }

  // ---------------------------------------------------------------- 초기화
  function showEmpty(message) {
    q('[data-title]').textContent = '관문을 열지 못했어요';
    q('[data-desc]').textContent = message;
    q('[data-body]').innerHTML = '<p class="empty">' + esc(message) + '</p>';
    setStatus(message, 'bad');
  }

  function load() {
    var who = q('[data-reviewer]');
    if (who && !who.value) who.value = rememberedReviewer();
    if (!state.characterId || !state.gate) {
      showEmpty('어느 캐릭터의 어떤 관문인지 알 수 없어요. 진행 화면에서 검토하기를 눌러 열어 주세요.');
      return Promise.resolve();
    }
    return Promise.all([
      api.gate(state.characterId, state.gate),
      api.character(state.characterId)
    ])
      .then(function (result) {
        var view = result[0];
        view.connected = view.connected !== false;
        state.view = view;
        state.character = result[1];
        state.items = view.items || {};
        state.kind = view.kind || (view.items || {}).kind || '';
        restorePicks();
        render();
        document.title = '캐릭터 공장 · ' + (view.title || '검토');
      })
      .catch(function (error) {
        // 서버·네트워크 오류 원문(영어일 수 있다)은 콘솔에만 남긴다.
        if (window.console) window.console.warn(error);
        showEmpty('검토 자료를 읽지 못했어요. 잠시 뒤 다시 열어 주세요.');
      });
  }

  function watch() {
    if (!api.events || state.source) return;
    state.source = api.events(function (name, data) {
      if (state.busy) return;
      if (name !== 'state' && name !== 'gate' && name !== 'job') return;
      if (data && data.characterId && data.characterId !== state.characterId) return;
      api
        .gate(state.characterId, state.gate)
        .then(function (view) {
          var before = state.view || {};
          if (before.status === view.status && before.rev === view.rev) return;
          state.view = view;
          state.items = view.items || {};
          state.kind = view.kind || state.kind;
          render();
        })
        .catch(function () {});
    }, { characterId: state.characterId });
  }

  document.addEventListener('click', function (event) {
    var decide = event.target.closest('[data-decide]');
    if (decide) {
      send(decide.getAttribute('data-decide'));
      return;
    }
    var preview = event.target.closest('[data-preview]');
    if (preview) {
      try {
        showAnswer(currentAnswer((KINDS[state.kind] || {}).actions[0][0]));
        setStatus('보낼 답을 만들었어요. 아직 보내지 않았어요.');
      } catch (error) {
        setStatus(error.message, 'bad');
      }
      return;
    }
    var pkgJump = event.target.closest('[data-pkg-jump]');
    if (pkgJump) {
      var pid = pkgJump.getAttribute('data-pkg-jump');
      var box = q('[data-pkg-detail="' + pid + '"]');
      if (box) { box.open = true; state.pkgOpen[pid] = true; box.scrollIntoView({ block: 'start', behavior: 'smooth' }); var sm = q('summary', box); if (sm) sm.focus({ preventScroll: true }); }
      return;
    }
    var sampleVerdictNode = event.target.closest('[data-sample-verdict]');
    if (sampleVerdictNode) {
      var sv = sampleVerdictNode.getAttribute('data-sample-verdict').split('|');
      setSampleVerdict(sv[0], sv[1]);
      return;
    }
    var sampleOpenNode = event.target.closest('[data-sample-open]');
    if (sampleOpenNode) { state.sampleOpen = sampleOpenNode.getAttribute('data-sample-open'); paintSamples(); return; }
    var sampleTabNode = event.target.closest('[data-sample-tab]');
    if (sampleTabNode) { state.sampleTab = sampleTabNode.getAttribute('data-sample-tab'); state.sampleOpen = ''; paintSamples(); return; }
    var introPickNode = event.target.closest('[data-intro-pick]');
    if (introPickNode) { if (!faceLocked()) { state.introPick = introPickNode.getAttribute('data-intro-pick'); paintIntro(); } return; }
    if (event.target.closest('[data-intro-play]')) { introPlay(false); return; }
    if (event.target.closest('[data-intro-restart]')) { introPlay(true); return; }
    var actionPickNode = event.target.closest('[data-action-pick]');
    if (actionPickNode) {
      var ap = actionPickNode.getAttribute('data-action-pick').split('|');
      pickAction(ap[0], ap.slice(1).join('|'));
      return;
    }
    var actionOpenNode = event.target.closest('[data-action-open]');
    if (actionOpenNode) { state.actionOpen = actionOpenNode.getAttribute('data-action-open'); paintActions(); return; }
    var actionStepNode = event.target.closest('[data-action-step]');
    if (actionStepNode) { actionStep(Number(actionStepNode.getAttribute('data-action-step'))); return; }
    if (event.target.closest('[data-action-close]') || (event.target.matches && event.target.matches('[data-action-box]'))) { state.actionOpen = ''; paintActions(); return; }
    if (event.target.closest('[data-action-next]')) {
      var firstLeft = actionOrder().filter(function (id) { return !state.actionPick[id]; })[0];
      if (firstLeft) { state.actionOpen = firstLeft; paintActions(); }
      return;
    }
    if (event.target.closest('[data-action-fill]')) {
      bulkActions('N칸을 첫 후보로 채웠어요.', function () {
        var n = 0;
        allActions().forEach(function (a) { if (!state.actionPick[a.actionId] && list(a.candidates).length) { state.actionPick[a.actionId] = a.candidates[0].candidateId; n += 1; } });
        return n;
      });
      return;
    }
    var colNode = event.target.closest('[data-action-col]');
    if (colNode) {
      var cp = colNode.getAttribute('data-action-col').split('|');
      var chapterAll = list(state.items.chapters).filter(function (c) { return c.chapterId === cp[0]; })[0];
      bulkActions(bgLabel({ chapterId: cp[0] }) + ' N칸을 ' + (cp[1] === 'keep' ? '쓰기' : '빼기') + '로 바꿨어요.', function () {
        var n = 0;
        list(chapterAll && chapterAll.actions).forEach(function (a) {
          var v = cp[1] === 'keep' ? (state.actionPick[a.actionId] && state.actionPick[a.actionId] !== 'exclude' ? state.actionPick[a.actionId] : (list(a.candidates)[0] || {}).candidateId) : 'exclude';
          if (v && state.actionPick[a.actionId] !== v) { state.actionPick[a.actionId] = v; n += 1; }
        });
        return n;
      });
      return;
    }
    if (event.target.closest('[data-action-undo]')) {
      if (state.actionUndo) { state.actionPick = state.actionUndo.picks; state.actionUndo = null; setStatus('되돌렸어요.'); paintActions(); }
      return;
    }
    if (event.target.closest('[data-send-now]')) { flushSend(); return; }
    if (event.target.closest('[data-send-cancel]')) { cancelSend(); return; }
    if (event.target.closest('[data-keys-close]') || (event.target.matches && event.target.matches('[data-keys-box]'))) { toggleKeys(false); return; }
    if (event.target.closest('[data-keys-open]')) { toggleKeys(true); return; }
    var frameVerdictNode = event.target.closest('[data-frame-verdict]');
    if (frameVerdictNode) {
      var fv = frameVerdictNode.getAttribute('data-frame-verdict').split('|');
      setFrameVerdict(fv[0], fv[1]);
      return;
    }
    var frameZoomNode = event.target.closest('[data-frame-zoom]');
    if (frameZoomNode) { state.frameZoom = frameZoomNode.getAttribute('data-frame-zoom'); paintFrameZoom(); return; }
    if (event.target.closest('[data-frame-zoom-close]') || (event.target.matches && event.target.matches('[data-frame-zoom-box]'))) { state.frameZoom = ''; paintFrameZoom(); return; }
    var posePickNode = event.target.closest('[data-pose-pick]');
    if (posePickNode) {
      var poseParts = posePickNode.getAttribute('data-pose-pick').split('|');
      pickPose(poseParts[0], poseParts.slice(1).join('|'));
      return;
    }
    var poseTabNode = event.target.closest('[data-pose-tab]');
    if (poseTabNode) { poseTab(poseTabNode.getAttribute('data-pose-tab')); return; }
    var bgPickNode = event.target.closest('[data-bg-pick]');
    if (bgPickNode) {
      var bgParts = bgPickNode.getAttribute('data-bg-pick').split('|');
      pickBackground(bgParts[0], bgParts.slice(1).join('|'));
      return;
    }
    var bgGoto = event.target.closest('[data-bg-goto]');
    if (bgGoto) {
      state.bgCurrent = bgGoto.getAttribute('data-bg-goto');
      paintBackgrounds();
      bgFocusRow(state.bgCurrent);
      return;
    }
    var planPickNode = event.target.closest('[data-plan-pick]');
    if (planPickNode) { pickPlan(planPickNode.getAttribute('data-plan-pick')); return; }
    if (event.target.closest('[data-plan-show-all]')) { state.planOnlyDiff = false; paintPlans(); return; }
    var faceLike = event.target.closest('[data-like]');
    if (faceLike) { toggleLike(faceLike.getAttribute('data-like')); return; }
    var facePick = event.target.closest('[data-face]');
    if (facePick) { pickFace(facePick.getAttribute('data-face')); return; }
    var photoPick = event.target.closest('[data-photo-pick]');
    if (photoPick) { pickPhoto(photoPick.getAttribute('data-photo-pick')); return; }
    var faceFilter = event.target.closest('[data-face-filter]');
    if (faceFilter) { state.faceFilter = faceFilter.getAttribute('data-face-filter'); paintFaces(); return; }
    if (event.target.closest('[data-face-compare-open]')) { state.faceCompare = true; paintFaces(); return; }
    if (event.target.closest('[data-face-compare-close]')) { state.faceCompare = false; paintFaces(); return; }
    if (event.target.closest('[data-face-clear]')) { state.faceLikes = []; state.faceCompare = false; paintFaces(); return; }
    var pick = event.target.closest('[data-pick]');
    if (pick) {
      applyPick(pick.getAttribute('data-pair-id'), pick.getAttribute('data-pick'), true);
      return;
    }
    if (event.target.closest('[data-next-pair]')) {
      focusPair(nextUnpicked(currentPair()) || nextUnpicked(null));
    }
  });
  document.addEventListener('keydown', onEvalKey);
  document.addEventListener('keydown', onFaceKey);
  document.addEventListener('keydown', onPhotoKey);
  document.addEventListener('keydown', onPlanKey);
  document.addEventListener('keydown', onBackgroundKey);
  document.addEventListener('keydown', onPoseKey);
  document.addEventListener('keydown', onFrameKey, true);
  document.addEventListener('keydown', onActionKey, true);
  document.addEventListener('keydown', onIntroKey);
  document.addEventListener('keydown', onSampleKey);
  document.addEventListener('keydown', onCommonKey, true);
  document.addEventListener('input', function (event) {
    var box = event.target && event.target.closest && event.target.closest('[data-bg-custom]');
    if (!box || faceLocked()) return;
    var ch = box.getAttribute('data-bg-custom');
    state.bgCustom[ch] = box.value;
    if (box.value.trim()) state.bgPicks[ch] = 'custom';
    // 글을 적는 칸은 다시 그리지 않고 고름 표시만 맞춘다.
    var row = q('[data-bg-row="' + ch + '"]');
    if (row) qa('[data-bg-pick]', row).forEach(function (node) {
      var on = node.getAttribute('data-bg-pick') === ch + '|' + state.bgPicks[ch];
      node.setAttribute('aria-pressed', String(on));
      (node.classList.contains('bg-custom-pick') ? node.parentNode : node).classList.toggle('is-picked', on);
    });
    paintBgMeta();
  });
  document.addEventListener('input', function (event) {
    var t = event.target;
    if (!t || !t.getAttribute || faceLocked()) return;
    var custom = t.getAttribute('data-pose-custom');
    if (custom) {
      state.poseCustom[custom] = t.value;
      if (t.value.trim() && state.posePicks[custom] !== 'custom') {
        state.posePicks[custom] = 'custom';
        // 표 강조를 맞추려고 다시 그리고, 적던 칸으로 초점을 돌린다.
        paintPoses();
        var again = q('[data-pose-custom="' + custom + '"]');
        if (again) { again.focus(); again.setSelectionRange(again.value.length, again.value.length); }
        return;
      }
      paintPoseMeta();
      return;
    }
    var sampleNote = t.getAttribute('data-sample-note');
    if (sampleNote) {
      state.sampleNote[sampleNote] = t.value;
      var row = q('[data-sample-open="' + sampleNote + '"] .sample-row-warn');
      if (row && t.value.trim()) row.remove();
      paintSampleMeta();
      return;
    }
    var actionNote = t.getAttribute('data-action-note');
    if (actionNote) {
      state.actionNote[actionNote] = t.value;
      // 표 칸의 '고칠 점' 표시와 버튼만 맞춘다(입력 칸은 다시 그리지 않는다).
      var cell = q('[data-action-open="' + actionNote + '"]');
      var a = actionById(actionNote);
      if (cell && a) cell.outerHTML = actionCell(a);
      paintActionMeta();
      return;
    }
    var frameNote = t.getAttribute('data-frame-note');
    if (frameNote) { state.frameNote[frameNote] = t.value; paintFrameMeta(); return; }
    var tweak = t.getAttribute('data-pose-tweak');
    if (tweak) {
      var parts = tweak.split(':');
      state.poseTweaks[parts[0]] = state.poseTweaks[parts[0]] || {};
      state.poseTweaks[parts[0]][parts[1]] = t.value;
      paintPoseMeta();
    }
  });
  document.addEventListener('change', function (event) {
    var pm = event.target && event.target.getAttribute && event.target.getAttribute('data-pkg-manual-box');
    if (pm && !faceLocked()) { state.pkgManual[pm] = event.target.checked; paintPackage(); return; }
    // 세부 고치기는 칸을 벗어날 때 표에 반영한다(적는 동안 다시 그리지 않는다).
    if (state.kind === 'poses' && event.target && event.target.getAttribute && event.target.getAttribute('data-pose-tweak')) {
      // 초점이 다음 칸으로 옮겨 간 뒤 다시 그리고, 그 칸으로 초점을 돌린다.
      setTimeout(function () {
        var active = document.activeElement;
        var key = active && active.getAttribute ? active.getAttribute('data-pose-tweak') : null;
        paintPoses();
        if (key) {
          var back = q('[data-pose-tweak="' + key + '"]');
          if (back) back.focus();
        }
      }, 0);
    }
  });
  document.addEventListener('toggle', function (event) {
    var node = event.target;
    if (node && node.hasAttribute && node.hasAttribute('data-pose-tweak-box')) state.poseTweakOpen = node.open;
    if (node && node.getAttribute && node.getAttribute('data-pkg-detail')) state.pkgOpen[node.getAttribute('data-pkg-detail')] = node.open;
    if (node && node.getAttribute && node.getAttribute('data-bg-detail')) state.bgOpen[node.getAttribute('data-bg-detail')] = node.open;
  }, true);
  document.addEventListener('change', function (event) {
    if (event.target && event.target.matches && event.target.matches('[data-plan-only-diff]')) {
      state.planOnlyDiff = event.target.checked;
      paintPlans();
    }
    if (event.target && event.target.matches && event.target.matches('[data-exclude-fact]')) paintSourceSide();
  });

  load().then(watch);
})();
