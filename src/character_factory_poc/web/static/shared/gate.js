// 관문 상세 화면. 서버의 관문 항목을 읽어 고르기·승인·수정 요청 화면을 만들고,
// 결정은 POST /api/characters/{id}/gates/{gate}/decision 한 곳으로 보낸다(cfp gate import와 같은 답).
(function () {
  'use strict';
  var api = window.CF_API;
  if (!api) return;
  var params = new URLSearchParams(location.search);
  var state = {
    characterId: params.get('character') || '',
    gate: params.get('gate') || '',
    view: null,
    character: null,
    items: {},
    kind: '',
    pairs: {},
    busy: false,
    source: null
  };

  var STATUS_KO = {
    PENDING: '대기',
    RUNNING: '진행 중',
    CHECK_FAILED: '검사 실패',
    AWAITING_HUMAN: '사람 검토',
    APPROVED: '승인',
    REJECTED: '반려',
    SKIPPED: '건너뜀'
  };

  // ---------------------------------------------------------------- 도우미
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
    out.textContent = message || '';
    out.className = 'side-status' + (kind ? ' is-' + kind : '');
  }
  function details() {
    var minutes = Number(q('[data-minutes]').value || 0);
    return {
      reviewer: q('[data-reviewer]').value || 'user',
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
    if (!file || !file.url) return '<p class="empty">영상 파일이 아직 없다.</p>';
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
      esc(reasons.join(' · ') || '자동 검사 항목을 확인했다.') + link + '</p>'
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

  // ---------------------------------------------------------------- 화면 정의
  var KINDS = {
    faces: {
      hint: '얼굴 하나를 고르면 그 외모군이 S2 기준 이미지와 이후 모든 장면의 얼굴 기준이 된다.',
      actions: [
        ['SELECT', '이 얼굴로 확정', 'primary'],
        ['REQUEST_CHANGES', '얼굴 다시 만들기', 'ghost'],
        ['REJECT', '반려', 'danger']
      ],
      render: renderFaces,
      build: buildFaces
    },
    planVariants: {
      hint: '같은 상황에서 무엇을 먼저 고르는지 본다. 고른 안의 칸은 확정 전에 고칠 수 있다.',
      actions: [
        ['SELECT', '이 안으로 확정', 'primary'],
        ['APPROVE', '첫 안으로 바로 확정', 'ghost'],
        ['REQUEST_CHANGES', '수정 요청', 'ghost'],
        ['REJECT', '반려', 'danger']
      ],
      render: renderPlans,
      build: buildPlans
    },
    backgrounds: {
      hint: '챕터마다 배경 하나를 고르거나 원하는 배경을 한두 줄로 직접 적는다.',
      actions: [
        ['SELECT', '고른 배경으로 확정', 'primary'],
        ['APPROVE', '첫 배경으로 모두 확정', 'ghost'],
        ['REQUEST_CHANGES', '다시 만들기', 'ghost'],
        ['REJECT', '반려', 'danger']
      ],
      render: renderBackgrounds,
      build: buildBackgrounds
    },
    poses: {
      hint: '장면 사실을 확인하고 챕터마다 자세·의상을 하나 고른다. 고른 후보의 칸은 세부 수정으로 바꾼다.',
      actions: [
        ['SELECT', '고른 자세로 확정', 'primary'],
        ['APPROVE', '첫 자세로 모두 확정', 'ghost'],
        ['REQUEST_CHANGES', '다시 만들기', 'ghost'],
        ['REJECT', '반려', 'danger']
      ],
      render: renderPoses,
      build: buildPoses
    },
    frames: {
      hint: '챕터마다 승인하거나 바꿀 내용을 적는다. 수정 요청한 챕터만 다시 만든다.',
      actions: [
        ['APPROVE', '세 장 모두 승인', 'primary'],
        ['REQUEST_CHANGES', '수정 요청 보내기', 'ghost'],
        ['REJECT', '반려', 'danger']
      ],
      render: renderFrames,
      build: buildFrames
    },
    intro: {
      hint: '첫 프레임과 같은 사람으로 자연스럽게 움직이는 영상을 하나 고른다.',
      actions: [
        ['SELECT', '이 영상으로 확정', 'primary'],
        ['REQUEST_CHANGES', '영상 다시 만들기', 'ghost'],
        ['REJECT', '반려', 'danger']
      ],
      render: renderIntro,
      build: buildIntro
    },
    actions: {
      hint: '동작마다 영상 하나를 고르거나 뺀다. 챕터마다 하나 이상은 남긴다.',
      actions: [
        ['SELECT', '고른 영상으로 확정', 'primary'],
        ['APPROVE', '첫 후보로 모두 확정', 'ghost'],
        ['REQUEST_CHANGES', '다시 만들기 요청', 'ghost'],
        ['REJECT', '반려', 'danger']
      ],
      render: renderActions,
      build: buildActions
    },
    prompts: {
      hint: '긴·짧은 프롬프트와 표본 응답을 보고 승인하거나 고칠 점을 적는다.',
      actions: [
        ['APPROVE', '프롬프트 승인', 'primary'],
        ['REQUEST_CHANGES', '수정 요청', 'ghost'],
        ['REJECT', '반려', 'danger']
      ],
      render: renderPrompts,
      build: buildPrompts
    },
    samples: {
      hint: '클러스터별 인계안과 샘플을 보고 대화마다 판정한다. 판정은 서버가 data-qa-v2로 남긴다.',
      actions: [
        ['SELECT', '이 판정 보내기', 'primary'],
        ['REQUEST_CHANGES', '인계안 수정 요청', 'ghost']
      ],
      render: renderSamples,
      build: buildSamples
    },
    dataset: {
      hint: '검사 요약과 무작위 표본 20개를 본 뒤 승인한다.',
      actions: [
        ['APPROVE', '데이터셋 승인', 'primary'],
        ['REQUEST_CHANGES', '수정 요청', 'ghost']
      ],
      render: renderDataset,
      build: buildDataset
    },
    eval: {
      hint: '조건 이름은 숨긴다. 두 응답 중 나은 쪽 또는 비슷함을 고르고, 마지막에 채택 기준을 정한다.',
      actions: [['SELECT', '블라인드 판정 보내기', 'primary']],
      render: renderEval,
      build: buildEval
    },
    promptOnly: {
      hint: '학습 결과가 아직 없다. 긴 프롬프트로 패키지까지 갈지, 학습을 기다릴지 정한다.',
      actions: [
        ['SELECT', '긴 프롬프트로 진행', 'primary'],
        ['REJECT', '학습을 기다린다', 'ghost']
      ],
      render: renderPromptOnly,
      build: buildPromptOnly
    },
    package: {
      hint: '패키지 요약을 확인하고 승인한다. 승인 뒤 우리 앱 변환·적재는 별도 단계다.',
      actions: [
        ['APPROVE', '패키지 승인', 'primary'],
        ['REJECT', '반려', 'danger']
      ],
      render: renderPackage,
      build: buildPackage
    }
  };

  // ---------------------------------------------------------------- G1
  function renderFaces(items) {
    var out = [
      '<section class="gate-section"><h2>얼굴 후보</h2><p class="section-sub">' +
        esc(items.helper || '') +
        '</p><div class="gate-grid">'
    ];
    list(items.clusters).forEach(function (cluster) {
      var cards = list(cluster.faces)
        .map(function (face) {
          return (
            '<label class="gate-card">' +
            image(face.file) +
            '<span class="card-title">' +
            esc(face.previewId) +
            (face.recommended ? ' <span class="badge-chip is-good">추천</span>' : '') +
            '</span>' +
            '<span class="card-sub">' + esc(face.prompt || '') + '</span>' +
            '<span class="pick-line"><input type="radio" name="face" value="' +
            esc(face.previewId) + '" data-cluster="' + esc(cluster.clusterId) +
            '"> 이 얼굴</span></label>'
          );
        })
        .join('');
      out.push(
        '<div class="gate-section" style="background:rgba(0,0,0,.14)">' +
          '<h2>' + esc(cluster.clusterId) +
          (cluster.recommended ? ' <span class="badge-chip is-good">추천</span>' : '') +
          '</h2><p class="section-sub">' + esc(cluster.rationale || '') + '</p>' +
          '<div class="gate-cards">' +
          (cards || '<p class="empty">이 외모군의 얼굴이 아직 없다.</p>') +
          '</div>' +
          '<dl class="facts">' +
          list(cluster.tags)
            .map(function (tag) {
              return '<dt>' + esc(tag.label) + '</dt><dd>' + esc(tag.text) + '</dd>';
            })
            .join('') +
          '</dl>' +
          '<details class="gate-more"><summary>구성원 ' + esc(cluster.memberCount) +
          '명 (검토용)</summary><ul>' +
          list(cluster.members)
            .map(function (member) {
              return '<li>' + esc(member.name || member.personId) + '</li>';
            })
            .join('') +
          '</ul></details></div>'
      );
    });
    out.push('</div>');
    var cautions = list(items.cautions);
    if (cautions.length) {
      out.push(
        '<details class="gate-more"><summary>읽을 때 주의</summary><ul>' +
          cautions.map(function (text) { return '<li>' + esc(text) + '</li>'; }).join('') +
          '</ul></details>'
      );
    }
    out.push(
      '</section><section class="gate-section"><h2>다시 만들 때 고칠 점</h2>' +
        '<p class="section-sub">마음에 드는 얼굴이 없을 때만 적는다. 이 메모로 얼굴만 다시 만든다.</p>' +
        '<textarea data-face-note placeholder="예: 눈매를 조금 더 부드럽게, 머리 길이는 그대로"></textarea>' +
        '</section>'
    );
    return out.join('');
  }

  function buildFaces(decision) {
    var answer = { decision: decision };
    if (decision === 'SELECT') {
      var node = q('input[name="face"]:checked');
      if (!node) throw Error('얼굴 하나를 골라 주세요.');
      answer.selections = [node.getAttribute('data-cluster')];
      answer.referencePreviews = [node.value];
    }
    if (decision === 'REQUEST_CHANGES') {
      var note = q('[data-face-note]').value.trim();
      if (!note) throw Error('다시 만들 때 고칠 점을 적어 주세요.');
      answer.note = note;
    }
    return Object.assign(answer, details());
  }

  // ---------------------------------------------------------------- G3
  function planSummary(plan) {
    return (
      chips([plan.variantId, plan.age ? plan.age + '세' : '', plan.gender, plan.job], '') +
      '<dl class="facts">' +
      '<dt>한 줄</dt><dd>' + esc(plan.tagline || '') + '</dd>' +
      '<dt>핵심</dt><dd>' + esc(joinList(plan.coreTraits, ' / ')) + '</dd>' +
      '<dt>대비</dt><dd>' + esc(plan.contrastTrait || '') + '</dd>' +
      '<dt>말투</dt><dd>' + esc(plan.voiceSummary || '') + '</dd>' +
      '<dt>예시</dt><dd>' + esc(joinList(plan.voiceExamples, ' / ')) + '</dd>' +
      '</dl>'
    );
  }

  function planDetails(plan) {
    var moves = list(plan.choices)
      .map(function (choice) {
        return (
          '<li><b>' + esc(choice.situation || '') + '</b> → ' +
          esc(choice.firstMove || '') + '</li>'
        );
      })
      .join('');
    var card = plan.profileCard || {};
    var cardRows = [
      ['취미', card.hobby],
      ['좋아함', card.likes],
      ['싫어함', card.dislikes],
      ['이상형 데이트', card.idealDate],
      ['MBTI', card.mbti],
      ['태그', joinList(card.tags, ', ')]
    ];
    return (
      (moves ? '<ul>' + moves + '</ul>' : '') +
      facts(cardRows) +
      facts([
        ['생활·취향', joinList(plan.lifeAndTastes, ' / ')],
        ['바람·두려움', joinList(plan.wantsAndFears, ' / ')],
        ['오해', joinList(plan.misreadings, ' / ')],
        ['경계', joinList(plan.boundaries, ' / ')]
      ])
    );
  }

  function renderPlans(items) {
    var candidates = list(items.candidates);
    var cards = candidates
      .map(function (plan) {
        return (
          '<label class="gate-card">' +
          '<span class="card-title">' + esc(plan.variantId) + ' · ' + esc(plan.name || '') +
          '</span><span class="card-sub">' + esc(plan.tagline || '') + '</span>' +
          planSummary(plan) +
          '<details class="gate-more" data-keep><summary>선택 기준·프로필 카드</summary>' +
          planDetails(plan) + '</details>' +
          '<span class="pick-line"><input type="radio" name="planPick" value="' +
          esc(plan.variantId) + '" data-plan="' + esc(plan.variantId) + '"> 이 안</span></label>'
        );
      })
      .join('');
    return (
      '<section class="gate-section"><h2>기획 후보 ' + candidates.length + '안</h2>' +
      '<p class="section-sub">' + esc(items.axisNote || '같은 상황에서 고르는 행동이 다르다.') +
      '</p><div class="gate-cards">' + cards + '</div></section>' +
      '<section class="gate-section"><h2>칸 수정 (선택)</h2>' +
      '<p class="section-sub">고른 안에서 바꿀 칸만 고친다. JSON 칸은 JSON 그대로 적는다. ' +
      '바꾼 칸만 수정 요청에 담긴다.</p>' +
      (items.mode === 'own'
        ? '<p class="section-sub">사람이 직접 쓴 글을 정리한 revision(u1)이다. 후보를 고르거나 ' +
          '칸을 고쳐 확정한다.</p>'
        : '<p class="section-sub">직접 쓴 안을 쓰려면 S3 own으로 새 revision을 만든 뒤 다시 ' +
          '연다. 그 revision의 u1 후보가 여기에 나타난다.</p>') +
      '<div class="field-list" data-plan-fields><p class="empty">후보를 고르면 칸이 열린다.</p>' +
      '</div></section>'
    );
  }

  function renderPlanFields() {
    var pick = q('input[name="planPick"]:checked');
    var host = q('[data-plan-fields]');
    if (!host) return;
    if (!pick) {
      host.innerHTML = '<p class="empty">후보를 고르면 칸이 열린다.</p>';
      return;
    }
    var plan = list(state.items.candidates).filter(function (c) {
      return c.variantId === pick.value;
    })[0];
    if (!plan) return;
    var fields = list(state.items.editableFields);
    host.innerHTML = fields
      .map(function (field) {
        var value = plan[field];
        var orig = JSON.stringify(value === undefined ? null : value);
        var text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
        var long = typeof value !== 'string' || String(text).length > 70;
        return (
          '<div class="field"><span>' + esc(field) + '</span>' +
          (long
            ? '<textarea data-edit="' + esc(field) + '" data-orig="' + esc(orig) + '">' +
              esc(text == null ? '' : text) + '</textarea>'
            : '<input type="text" data-edit="' + esc(field) + '" data-orig="' + esc(orig) +
              '" value="' + esc(text == null ? '' : text) + '">') +
          '</div>'
        );
      })
      .join('');
  }

  function collectEdits() {
    var edits = {};
    qa('[data-edit]').forEach(function (node) {
      var field = node.getAttribute('data-edit');
      var orig = node.getAttribute('data-orig');
      var raw = node.value;
      var value = raw;
      if (orig && orig.charAt(0) !== '"') {
        try {
          value = JSON.parse(raw);
        } catch (e) {
          throw Error(field + ' 칸은 JSON이어야 합니다: ' + e.message);
        }
      }
      if (JSON.stringify(value) !== orig) edits[field] = value;
    });
    return edits;
  }

  function buildPlans(decision) {
    var answer = { decision: decision };
    if (decision === 'SELECT' || decision === 'APPROVE') {
      var pick = q('input[name="planPick"]:checked');
      if (decision === 'SELECT' && !pick) throw Error('기획 후보 하나를 골라 주세요.');
      answer.selections = pick ? [pick.value] : [];
      answer.edits = collectEdits();
    }
    return Object.assign(answer, details());
  }

  // ---------------------------------------------------------------- G4a
  function backgroundCard(chapter, candidate) {
    return (
      '<label class="gate-card">' +
      image(candidate.plate, 'wide') +
      '<span class="card-title">' + esc(candidate.candidateId) + ' · ' +
      esc(candidate.place) + '</span>' +
      '<span class="card-sub">' + esc(candidate.why || '') + '</span>' +
      qaBadge(candidate.qa) +
      facts([
        ['시간대', candidate.timeOfDay],
        ['분위기', candidate.mood],
        ['소품', joinList(candidate.props, ', ')],
        ['장면 사실', joinList(candidate.sceneFactsDraft, ' / ')],
        ['경계', joinList(candidate.boundariesDraft, ' / ')]
      ]) +
      qaNote(candidate.qa) +
      '<span class="pick-line"><input type="radio" name="' + esc(chapter) + '" value="' +
      esc(candidate.candidateId) + '"> 이 배경</span></label>'
    );
  }

  function customCard(chapter, label, hint) {
    return (
      '<div class="gate-card"><span class="card-title">' + esc(label) + '</span>' +
      '<span class="card-sub">' + esc(hint) + '</span>' +
      '<textarea data-custom="' + esc(chapter) + '" placeholder="한두 줄로 적어 주세요"></textarea>' +
      '<label class="pick-line"><input type="radio" name="' + esc(chapter) +
      '" value="custom"> 이 내용으로</label></div>'
    );
  }

  function renderBackgrounds(items) {
    var sections = list(items.chapters)
      .map(function (chapter) {
        return (
          '<section class="gate-section"><h2>' + esc(chapter.chapterId) + ' · ' +
          esc(chapter.title || '') + '</h2><p class="section-sub">' + esc(chapter.arc || '') +
          '</p><div class="gate-cards">' +
          list(chapter.candidates).map(function (candidate) {
            return backgroundCard(chapter.chapterId, candidate);
          }).join('') +
          customCard(chapter.chapterId, '배경 직접 정의', '장소·시간대·분위기를 한두 줄로') +
          '</div></section>'
        );
      })
      .join('');
    return (
      '<section class="gate-body">' + sections + '</section>' +
      changeNoteSection('다시 만들 때 고칠 점', '어떤 배경을 어떻게 바꿀지 챕터와 함께 적는다.')
    );
  }

  function changeNoteSection(title, hint) {
    return (
      '<section class="gate-section"><h2>' + esc(title) + '</h2>' +
      '<p class="section-sub">' + esc(hint) + '</p>' +
      '<textarea data-change-note placeholder="예: ch2를 낮 시간 실내로, 사람은 없이"></textarea>' +
      '</section>'
    );
  }

  function collectPicks(container) {
    var picks = {};
    var custom = {};
    qa('[data-custom]', container).forEach(function (node) {
      var chapter = node.getAttribute('data-custom');
      var pick = q('input[name="' + chapter + '"]:checked');
      if (!pick) throw Error(chapter + '에서 후보 또는 직접 정의를 골라 주세요.');
      if (pick.value === 'custom') {
        var text = node.value.trim();
        if (!text) throw Error(chapter + '의 직접 정의를 적어 주세요.');
        custom[chapter] = text;
      } else {
        picks[chapter] = pick.value;
      }
    });
    return { picks: picks, custom: custom };
  }

  function buildBackgrounds(decision) {
    var answer = { decision: decision };
    if (decision === 'SELECT') Object.assign(answer, collectPicks(document));
    if (decision === 'REQUEST_CHANGES') {
      var note = (q('[data-change-note]') || {}).value || '';
      if (!note.trim()) throw Error('다시 만들 때 고칠 점을 적어 주세요.');
      answer.reasons = details().reasons || note.trim();
    }
    return Object.assign(answer, details());
  }

  // ---------------------------------------------------------------- G4b
  function poseCard(chapter, pose) {
    return (
      '<label class="gate-card"><span class="card-title">' + esc(pose.title || pose.poseId) +
      '</span>' +
      facts([
        ['몸', pose.body],
        ['손', pose.hands],
        ['소품', pose.props],
        ['시선', pose.gaze],
        ['표정', pose.expression],
        ['구도', pose.shot],
        ['의상', pose.outfit],
        ['움직임', pose.motionHint]
      ]) +
      '<span class="pick-line"><input type="radio" name="' + esc(chapter) + '" value="' +
      esc(pose.poseId) + '"> 이 자세</span></label>'
    );
  }

  function tweakFields(chapter, fields) {
    return (
      '<details class="gate-more"><summary>고른 후보의 세부 항목 수정 (선택)</summary>' +
      '<div class="field-list">' +
      fields.map(function (field) {
        return (
          '<div class="field"><span>' + esc(field) + '</span>' +
          '<input type="text" data-tweak="' + esc(chapter) + ':' + esc(field) +
          '" placeholder="바꿀 값만 적는다"></div>'
        );
      }).join('') +
      '</div></details>'
    );
  }

  function renderPoses(items) {
    var fields = list(items.poseFields);
    var sections = list(items.chapters)
      .map(function (chapter) {
        var ch = chapter.chapterId;
        return (
          '<section class="gate-section"><h2>' + esc(ch) + ' 장면과 자세</h2>' +
          '<div class="gate-grid">' + image(chapter.plate, 'wide') +
          '<div>' + facts([
            ['장소', chapter.place],
            ['시간대', chapter.timeOfDay],
            ['분위기', chapter.mood],
            ['장면 사실', joinList(chapter.sceneFacts, ' / ')],
            ['만나는 경위', chapter.meetingContext],
            ['관계 정본', joinList(chapter.relationshipCanon, ' / ')],
            ['경계', joinList(chapter.sceneBoundaries, ' / ')]
          ]) + qaBadge(chapter.qa) + qaNote(chapter.qa) + '</div></div>' +
          '<div class="gate-cards">' +
          list(chapter.candidates).map(function (pose) {
            return poseCard(ch, pose);
          }).join('') +
          customCard(ch, '자세·의상 직접 정의', '몸·손·표정·의상을 한두 줄로') +
          '</div>' + tweakFields(ch, fields) + '</section>'
        );
      })
      .join('');
    return (
      sections +
      changeNoteSection('다시 만들 때 고칠 점', '어떤 자세를 어떻게 바꿀지 챕터와 함께 적는다.')
    );
  }

  function collectTweaks(picks) {
    var tweaks = {};
    qa('[data-tweak]').forEach(function (node) {
      var parts = node.getAttribute('data-tweak').split(':');
      var chapter = parts[0];
      var field = parts[1];
      if (!picks[chapter]) return;
      var value = node.value.trim();
      if (!value) return;
      tweaks[chapter] = tweaks[chapter] || {};
      tweaks[chapter][field] = value;
    });
    return tweaks;
  }

  function buildPoses(decision) {
    var answer = { decision: decision };
    if (decision === 'SELECT') {
      var choices = collectPicks(document);
      answer.picks = choices.picks;
      answer.custom = choices.custom;
      answer.tweaks = collectTweaks(choices.picks);
    }
    if (decision === 'REQUEST_CHANGES') {
      var note = (q('[data-change-note]') || {}).value || '';
      if (!note.trim()) throw Error('다시 만들 때 고칠 점을 적어 주세요.');
      answer.reasons = details().reasons || note.trim();
    }
    return Object.assign(answer, details());
  }

  // ---------------------------------------------------------------- G4
  function renderFrames(items) {
    var refs =
      '<div class="gate-grid">' + image(items.referenceImage, 'wide') +
      image(items.identityReference, 'wide') +
      '<div>' + facts([
        ['외모', items.appearanceRev],
        ['장면', items.sceneRev],
        ['얼굴 참조', items.referenceCrop],
        ['참조 메모', items.cropNote]
      ]) + '</div></div>';
    var chapters = list(items.frames)
      .map(function (frame) {
        var ch = frame.chapterId;
        return (
          '<section class="gate-section"><h2>' + esc(ch) + ' · ' + esc(frame.frameId) + '</h2>' +
          '<div class="gate-grid">' + image(frame.file, 'wide') +
          '<div>' + qaBadge(frame.qa) + qaNote(frame.qa) +
          '<details class="gate-more"><summary>생성 지시 확인</summary><pre class="answer-json">' +
          esc(frame.prompt || '') + '</pre></details>' +
          '<div class="verdict-row">' +
          '<label><input type="radio" name="frame-' + esc(ch) + '" value="APPROVE"> 이 챕터 승인' +
          '</label><label><input type="radio" name="frame-' + esc(ch) +
          '" value="REQUEST_CHANGES"> 이 챕터 수정</label></div>' +
          '<textarea data-frame-note="' + esc(ch) +
          '" placeholder="수정할 때만: 무엇을 바꿀지"></textarea></div></div></section>'
        );
      })
      .join('');
    return refs + chapters;
  }

  function buildFrames(decision) {
    var answer = { decision: decision };
    if (decision === 'REQUEST_CHANGES') {
      var changes = [];
      list(state.items.frames).forEach(function (frame) {
        var pick = q('input[name="frame-' + frame.chapterId + '"]:checked');
        if (!pick) throw Error(frame.chapterId + '의 승인 또는 수정을 골라 주세요.');
        if (pick.value !== 'REQUEST_CHANGES') return;
        var note = (q('[data-frame-note="' + frame.chapterId + '"]') || {}).value || '';
        if (!note.trim()) throw Error(frame.chapterId + '에서 바꿀 내용을 적어 주세요.');
        changes.push({ field: frame.chapterId, note: note.trim() });
      });
      if (!changes.length) throw Error('수정할 챕터를 하나 이상 고르거나 전체 승인을 누르세요.');
      answer.requestedChanges = changes;
    }
    return Object.assign(answer, details());
  }

  // ---------------------------------------------------------------- G5
  function renderIntro(items) {
    var settings = items.settings || {};
    var cards = list(items.candidates)
      .map(function (candidate) {
        var probe = candidate.probe || {};
        var measured = probe.durationS || probe.width
          ? '실측 ' + (probe.durationS || '?') + '초 · ' + (probe.width || '?') + '×' +
            (probe.height || '?')
          : '실측 없음';
        return (
          '<label class="gate-card">' + video(candidate.file) +
          '<span class="card-title">' + esc(candidate.candidateId) + '</span>' +
          '<span class="card-sub">' + esc(candidate.provider) + ' · ' +
          esc(candidate.model) + ' · ' + esc(measured) + '</span>' +
          '<span class="pick-line"><input type="radio" name="introPick" value="' +
          esc(candidate.candidateId) + '"> 이 영상</span></label>'
        );
      })
      .join('');
    return (
      '<section class="gate-section"><h2>첫 프레임과 대표 이미지</h2>' +
      '<div class="gate-grid">' + image(items.hero, 'wide') + image(items.firstFrame, 'wide') +
      '<div>' + facts([
        ['첫 프레임', (items.firstFrameSource || {}).mode],
        ['모델', items.model],
        ['해상도', settings.resolution],
        ['길이', settings.duration ? settings.duration + '초' : ''],
        ['비율', settings.aspectRatio]
      ]) +
      '<details class="gate-more"><summary>움직임 프롬프트</summary><pre class="answer-json">' +
      esc(items.prompt || '') + '</pre></details></div></div></section>' +
      '<section class="gate-section"><h2>영상 후보</h2>' +
      (cards || '<p class="empty">영상 후보가 아직 없다.</p>') + '</section>'
    );
  }

  function buildIntro(decision) {
    var answer = { decision: decision };
    if (decision === 'SELECT') {
      var pick = q('input[name="introPick"]:checked');
      if (!pick) throw Error('영상 후보 하나를 골라 주세요.');
      answer.selections = [pick.value];
    }
    return Object.assign(answer, details());
  }

  // ---------------------------------------------------------------- G5b
  function actionCard(action) {
    var candidates = list(action.candidates)
      .map(function (candidate) {
        return (
          '<label class="gate-card">' + video(candidate.file) +
          '<span class="card-title">' + esc(candidate.candidateId) +
          (candidate.reusedFrom ? ' <span class="badge-chip">재사용 ' +
            esc(candidate.reusedFrom) + '</span>' : '') + '</span>' +
          '<span class="pick-line"><input type="radio" name="' + esc(action.actionId) +
          '" value="' + esc(candidate.candidateId) + '"> 이 영상</span></label>'
        );
      })
      .join('');
    return (
      '<section class="gate-section"><h2>' + esc(action.title || action.actionKey) + '</h2>' +
      '<p class="section-sub"><code>' + esc(action.actionKey) + '</code> · ' +
      (action.mood === 'good' ? '미소 출발' : '무표정 출발') + ' · ' +
      esc(action.duration) + '초 · ' + esc(action.playType) +
      (action.actionCategory ? ' · ' + esc(action.actionCategory) : '') + ' · ' +
      esc(action.actionId) + '</p>' +
      (action.useWhen ? '<p class="section-sub">언제: ' + esc(action.useWhen) + '</p>' : '') +
      (action.reviewNote ? '<p class="qa-note">이전 요청: ' + esc(action.reviewNote) +
        '</p>' : '') +
      '<div class="gate-cards">' + (candidates || '<p class="empty">영상 후보가 아직 없다.</p>') +
      '<label class="gate-card"><span class="card-title">빼기</span>' +
      '<span class="card-sub">이 동작은 이번 세트에서 뺀다.</span>' +
      '<span class="pick-line"><input type="radio" name="' + esc(action.actionId) +
      '" value="exclude"> 이 동작 빼기</span></label></div>' +
      '<textarea data-action-note="' + esc(action.actionId) +
      '" placeholder="다시 만들 때만: 고칠 점"></textarea></section>'
    );
  }

  function renderActions(items) {
    var sections = list(items.chapters)
      .map(function (chapter) {
        return (
          '<section class="gate-section"><h2>' + esc(chapter.chapterId) + ' 첫 프레임</h2>' +
          '<p class="section-sub">' + esc(chapter.stageNote || '') + '</p>' +
          '<div class="gate-grid">' + image(chapter.goodFrame, 'wide') +
          image(chapter.badFrame, 'wide') + '<div>' + facts([
            ['미소 출발', chapter.goodFrame ? '있음' : '없음'],
            ['무표정 출발', chapter.badFrame ? '있음' : '없음'],
            ['동작 수', list(chapter.actions).length]
          ]) + '</div></div>' +
          list(chapter.actions).map(actionCard).join('') + '</section>'
        );
      })
      .join('');
    return sections;
  }

  function allActions() {
    var out = [];
    list(state.items.chapters).forEach(function (chapter) {
      list(chapter.actions).forEach(function (action) {
        out.push(action);
      });
    });
    return out;
  }

  function buildActions(decision) {
    var answer = { decision: decision };
    if (decision === 'SELECT') {
      var picks = {};
      var excluded = [];
      allActions().forEach(function (action) {
        var pick = q('input[name="' + action.actionId + '"]:checked');
        if (!pick) {
          throw Error((action.title || action.actionId) + ': 영상 또는 빼기를 골라 주세요.');
        }
        if (pick.value === 'exclude') excluded.push(action.actionId);
        else picks[action.actionId] = pick.value;
      });
      answer.picks = picks;
      answer.excluded = excluded;
    }
    if (decision === 'REQUEST_CHANGES') {
      var changes = [];
      allActions().forEach(function (action) {
        var node = q('[data-action-note="' + action.actionId + '"]');
        var note = node ? node.value.trim() : '';
        if (note) changes.push({ field: action.actionId, note: note });
      });
      if (!changes.length) throw Error('다시 만들 동작에 고칠 점을 적어 주세요.');
      answer.requestedChanges = changes;
    }
    return Object.assign(answer, details());
  }

  // ---------------------------------------------------------------- G6
  function renderPrompts(items) {
    var long = items.long || {};
    var short = items.short || {};
    var probes = list(items.probes)
      .map(function (probe) {
        var judge = probe.judge || {};
        return (
          '<div class="probe"><p class="probe-q">' + esc(probe.sentence) + '</p>' +
          '<div class="probe-a"><div><b>긴 프롬프트</b>' + esc(probe.longResponse) + '</div>' +
          '<div><b>짧은 프롬프트</b>' + esc(probe.shortResponse) + '</div></div>' +
          '<p class="qa-note">판정(참고): ' + esc(judge.pick || '-') + ' · ' +
          esc(judge.reasons || '') + '</p></div>'
        );
      })
      .join('');
    var sheet = items.traitSheet;
    return (
      '<section class="gate-section"><h2>프롬프트</h2>' +
      '<p class="section-sub">섹션 ' + esc(joinList(items.sections, ', ')) +
      ' · 짧은 프롬프트 ' + esc(short.chars || 0) + '자' +
      (items.shortAdopted ? ' · 짧은 프롬프트 채택됨' : '') + '</p>' +
      '<div class="doc-block">' +
      '<div class="doc"><h3>긴 프롬프트 <span class="badge-chip">' + esc(long.chars || 0) +
      '자</span></h3><pre>' + esc(long.text || '') + '</pre></div>' +
      '<div class="doc"><h3>짧은 프롬프트 <span class="badge-chip">' + esc(short.chars || 0) +
      '자</span></h3><pre>' + esc(short.text || '') + '</pre></div></div></section>' +
      '<section class="gate-section"><h2>표본 응답</h2>' +
      '<p class="section-sub">판정은 참고용이다. 승인은 사람이 한다.</p>' +
      (probes || '<p class="empty">표본 응답이 아직 없다.</p>') + '</section>' +
      (sheet
        ? '<section class="gate-section"><h2>특질 시트</h2><p class="section-sub">' +
          esc(sheet.path) + '</p>' +
          (sheet.card
            ? facts([
                ['태도', sheet.card.stance],
                ['판단 기준', list(sheet.card.judgmentPriorities)
                  .map(function (p) { return p.dilemma + ' → ' + p.choice; })
                  .join(' / ')],
                ['말버릇', (sheet.card.dialogueHabits || {}).lexicon],
                ['미정', joinList(sheet.unresolved, ', ')]
              ])
            : '') +
          '<p class="section-sub"><a href="' + esc(sheet.url) +
          '" target="_blank" rel="noopener">특질 시트 JSON 열기</a></p></section>'
        : '') +
      '<section class="gate-section"><h2>수정 요청 (선택)</h2>' +
      '<div class="field-list"><div class="field"><span>어느 프롬프트</span>' +
      '<select data-prompt-scope><option value="long">긴 프롬프트</option>' +
      '<option value="short">짧은 프롬프트</option></select></div></div>' +
      '<textarea data-prompt-note placeholder="예: 첫 인사를 더 짧게, 감탄사 줄이기"></textarea>' +
      '</section>'
    );
  }

  function buildPrompts(decision) {
    var answer = { decision: decision };
    if (decision === 'REQUEST_CHANGES') {
      var note = q('[data-prompt-note]').value.trim();
      if (!note) throw Error('고칠 점을 적어 주세요.');
      answer.requestedChanges = [{ field: q('[data-prompt-scope]').value, note: note }];
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

  function conversationCard(conversation, namePrefix, defaultVerdict) {
    var messages = list(conversation.messages)
      .map(function (message) {
        return (
          '<div class="pair-answer"><b>' + (message.role === 'assistant' ? '캐릭터' : '사용자') +
          '</b>' + esc(message.content) + '</div>'
        );
      })
      .join('');
    var id = conversation.conversationId;
    return (
      '<div class="pair"><div class="pair-head"><span>' + esc(id) + '</span>' +
      '<span>' + esc(conversation.clusterId || '') + '</span></div>' +
      (conversation.system ? '<p class="card-sub">system: ' + esc(conversation.system) +
        '</p>' : '') +
      '<div class="pair-answers">' + messages + '</div>' +
      '<div class="verdict-row" role="group" aria-label="' + esc(id) + ' 판정">' +
      ['ADOPT', 'FIX', 'REJECT']
        .map(function (verdict) {
          return (
            '<label><input type="radio" name="' + esc(namePrefix + id) + '" value="' +
            esc(verdict) + '"' + (verdict === defaultVerdict ? ' checked' : '') + '> ' +
            esc(verdict) + '</label>'
          );
        })
        .join('') +
      '</div><textarea data-conv-note="' + esc(id) +
      '" placeholder="FIX일 때만: 고칠 점"></textarea></div>'
    );
  }

  function renderSamples(items) {
    var clusters = list(items.clusters);
    // 판정을 마친 클러스터는 표시하고, 아직 안 한 첫 클러스터를 기본으로 고른다.
    var firstOpen = clusters.findIndex(function (cluster) {
      return !cluster.reviewed;
    });
    if (firstOpen < 0) firstOpen = 0;
    var reviewed = clusters.filter(function (cluster) {
      return cluster.reviewed;
    }).length;
    var options = clusters
      .map(function (cluster, index) {
        return (
          '<option value="' + esc(cluster.clusterId) + '"' +
          (index === firstOpen ? ' selected' : '') + '>' + esc(cluster.clusterId) +
          (cluster.reviewed ? ' · 판정 완료' : '') + '</option>'
        );
      })
      .join('');
    return (
      '<section class="gate-section"><h2>계획</h2>' +
      facts([
        ['목표 대화', (items.plan || {}).targetTrainConversations],
        ['클러스터', list((items.plan || {}).clusters)
          .map(function (c) { return c.clusterId + ' ' + c.share; }).join(' / ')],
        ['검증', validationText((items.plan || {}).validation)]
      ]) +
      '</section>' +
      '<section class="gate-section"><h2>클러스터 샘플 <span class="blind-count">' +
      reviewed + ' / ' + clusters.length + ' 판정</span></h2>' +
      '<label class="field"><span>클러스터</span><select data-cluster-pick>' + options +
      '</select></label><div data-cluster-body></div></section>' +
      '<section class="gate-section"><h2>인계안 수정 요청 (선택)</h2>' +
      '<textarea data-cluster-note placeholder="인계안을 어떻게 고칠지"></textarea></section>'
    );
  }

  function renderClusterBody(clusterId) {
    var host = q('[data-cluster-body]');
    var cluster = list(state.items.clusters).filter(function (c) {
      return c.clusterId === clusterId;
    })[0];
    if (!host || !cluster) return;
    var handoff = cluster.handoff || {};
    host.innerHTML =
      '<div class="gate-section" style="background:rgba(0,0,0,.14)"><h2>행동 기준표</h2>' +
      '<table class="gate-table"><thead><tr><th>상황</th><th>먼저 보는 것</th><th>고르는 행동</th>' +
      '<th>말투</th></tr></thead><tbody>' +
      list(handoff.behaviorTable)
        .map(function (row) {
          return '<tr><td>' + esc(row.situation) + '</td><td>' + esc(row.attention) +
            '</td><td>' + esc(row.choice) + '</td><td>' + esc(row.voice) + '</td></tr>';
        })
        .join('') +
      '</tbody></table>' +
      facts([['말투 예시', joinList(handoff.voiceExamples, ' / ')],
        ['금지', joinList(handoff.forbidden, ' / ')], ['메모', handoff.notes]]) +
      '</div>' +
      list(cluster.samples).map(function (sample) {
        return conversationCard(sample, 'verdict-', 'ADOPT');
      }).join('');
  }

  function buildSamples(decision) {
    var cluster = q('[data-cluster-pick]').value;
    var verdicts = {};
    var notes = {};
    var entry = list(state.items.clusters).filter(function (c) {
      return c.clusterId === cluster;
    })[0] || { samples: [] };
    list(entry.samples).forEach(function (sample) {
      var pick = q('input[name="verdict-' + sample.conversationId + '"]:checked');
      if (!pick) throw Error(sample.conversationId + '의 판정을 골라 주세요.');
      verdicts[sample.conversationId] = pick.value;
      var note = q('[data-conv-note="' + sample.conversationId + '"]');
      if (pick.value === 'FIX' && note && note.value.trim()) {
        notes[sample.conversationId] = note.value.trim();
      }
    });
    var answer = { decision: decision, cluster: cluster, verdicts: verdicts, notes: notes };
    if (decision === 'REQUEST_CHANGES') {
      var clusterNote = q('[data-cluster-note]').value.trim();
      if (!clusterNote) throw Error('인계안에서 고칠 점을 적어 주세요.');
      answer.reasons = details().reasons || clusterNote;
    }
    return Object.assign(answer, details());
  }

  // ---------------------------------------------------------------- G7
  function renderDataset(items) {
    var dataset = items.dataset || {};
    var counts = dataset.clusterCounts || {};
    var rows = Object.keys(counts)
      .map(function (key) {
        var row = counts[key] || {};
        return '<tr><td>' + esc(key) + '</td><td class="num">' + esc(row.conversations) +
          '</td><td class="num">' + esc(row.replies) + '</td><td class="num">' +
          esc(row.supervisedTokens) + '</td></tr>';
      })
      .join('');
    var files = list(dataset.files)
      .map(function (file) {
        return '<tr><td>' + esc(file.split) + '</td><td><code>' + esc(file.path) +
          '</code></td><td class="num">' + esc(file.conversations) + '</td></tr>';
      })
      .join('');
    var samples = list(items.samples)
      .map(function (sample) {
        return conversationCard(
          { conversationId: sample.conversationId, clusterId: sample.clusterId,
            messages: sample.messages },
          'verdict-',
          'ADOPT'
        );
      })
      .join('');
    return (
      '<section class="gate-section"><h2>검사 요약</h2>' + facts([
        ['데이터셋', dataset.datasetRev],
        ['차단 실패', dataset.blockingFailures],
        ['경고', dataset.warnings]
      ]) +
      '<p class="section-sub">' + esc(joinList(items.notes, ' ')) + '</p>' +
      '<table class="metric-table"><thead><tr><th>클러스터</th><th>대화</th><th>답변</th>' +
      '<th>학습 토큰</th></tr></thead><tbody>' + rows + '</tbody></table>' +
      '<details class="gate-more"><summary>분할 파일</summary>' +
      '<table class="metric-table"><thead><tr><th>분할</th><th>파일</th><th>대화</th></tr>' +
      '</thead><tbody>' + files + '</tbody></table></details></section>' +
      '<section class="gate-section"><h2>무작위 표본 20개</h2>' +
      '<p class="section-sub">대화마다 판정한다. 기본은 ADOPT이고, 고칠 대화만 바꾼다.</p>' +
      samples + '</section>'
    );
  }

  function buildDataset(decision) {
    var verdicts = {};
    var notes = {};
    list(state.items.samples).forEach(function (sample) {
      var pick = q('input[name="verdict-' + sample.conversationId + '"]:checked');
      if (!pick) throw Error(sample.conversationId + '의 판정을 골라 주세요.');
      verdicts[sample.conversationId] = pick.value;
      var note = q('[data-conv-note="' + sample.conversationId + '"]');
      if (pick.value === 'FIX' && note && note.value.trim()) {
        notes[sample.conversationId] = note.value.trim();
      }
    });
    return Object.assign({ decision: decision, verdicts: verdicts, notes: notes }, details());
  }

  // ---------------------------------------------------------------- G8
  function renderEval(items) {
    var report = items.report || {};
    var metrics = list(report.metrics)
      .map(function (metric) {
        return '<tr><td>' + esc(metric.armId) + '</td><td>' + esc(metric.metric) +
          '</td><td class="num">' + esc(metric.value) + '</td></tr>';
      })
      .join('');
    var criteria = list(report.criteriaResults)
      .map(function (result) {
        return '<tr><td>' + esc(result.id) + '</td><td>' + esc(result.armId) +
          '</td><td class="num">' + esc(result.value) + '</td><td>' +
          (result.passed
            ? '<span class="badge-chip is-good">통과</span>'
            : '<span class="badge-chip is-bad">미달</span>') + '</td></tr>';
      })
      .join('');
    var pairs = list(items.pairs)
      .map(function (pair) {
        return (
          '<div class="pair" data-pair="' + esc(pair.pairId) + '">' +
          '<div class="pair-head"><span>' + esc(pair.pairId) + '</span></div>' +
          '<p class="pair-prompt">' + esc(pair.prompt) + '</p>' +
          '<div class="pair-answers">' +
          '<div class="pair-answer" data-answer="A"><b>응답 A</b>' + esc(pair.a) + '</div>' +
          '<div class="pair-answer" data-answer="B"><b>응답 B</b>' + esc(pair.b) + '</div>' +
          '</div><div class="seg" role="group" aria-label="' + esc(pair.pairId) + ' 선택">' +
          '<button type="button" data-pick="A" data-pair-id="' + esc(pair.pairId) +
          '" aria-pressed="false">A가 낫다</button>' +
          '<button type="button" data-pick="B" data-pair-id="' + esc(pair.pairId) +
          '" aria-pressed="false">B가 낫다</button>' +
          '<button type="button" data-pick="TIE" data-pair-id="' + esc(pair.pairId) +
          '" aria-pressed="false">비슷함</button></div></div>'
        );
      })
      .join('');
    var adopt = list(items.adoptOptions)
      .map(function (option) {
        return '<option value="' + esc(option) + '">' + esc(option) + '</option>';
      })
      .join('');
    // 지표에는 조건 이름과 값이 있어 판정을 흔들 수 있다. 블라인드를 다 고른 뒤에 연다.
    var blindOpen =
      !list(items.pairs).length || (state.view && state.view.status !== 'AWAITING_HUMAN');
    return (
      '<section class="gate-section" data-blind-wait' + (blindOpen ? ' hidden' : '') + '>' +
      '<h2>지표</h2><p class="section-sub">조건 이름과 지표 값은 블라인드 ' +
      list(items.pairs).length + '쌍을 모두 고르면 열려요.</p></section>' +
      '<section class="gate-section" data-after-blind' + (blindOpen ? '' : ' hidden') + '>' +
      '<h2>지표</h2>' +
      '<p class="section-sub">블라인드 판정을 마친 뒤 보는 조건별 지표다.</p>' +
      '<table class="metric-table"><thead><tr><th>조건</th><th>지표</th><th>값</th></tr>' +
      '</thead><tbody>' + metrics + '</tbody></table>' +
      '<details class="gate-more"><summary>기준 결과</summary>' +
      '<table class="metric-table"><thead><tr><th>기준</th><th>조건</th><th>값</th><th>결과</th>' +
      '</tr></thead><tbody>' + criteria + '</tbody></table>' +
      '<p class="section-sub">' + esc(report.recommendation || '') + '</p></details></section>' +
      '<section class="gate-section"><h2>블라인드 비교 <span class="blind-count" data-blind-count>' +
      '0 / ' + list(items.pairs).length + '</span></h2>' +
      '<p class="section-sub">어느 쪽이 어떤 조건인지 숨긴다. 더 나은 응답을 고르거나 비슷함을 ' +
      '고른다.</p>' + pairs + '</section>' +
      '<section class="gate-section"><h2>채택 기준</h2>' +
      '<p class="section-sub">블라인드 결과를 본 뒤, 어떤 조건을 채택할지 정한다.</p>' +
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

  // ---------------------------------------------------------------- G9
  // ---------------------------------------------------------------- G8(학습 없이 진행, K-0038)
  function renderPromptOnly(items) {
    var doc = items.decision || {};
    var runs = list(doc.trainingRuns)
      .map(function (run) {
        var usd = run.estimateUsd == null ? '-' : '$' + Number(run.estimateUsd).toFixed(2);
        return '<tr><td>' + esc(run.provider) + '</td><td>' + esc(run.status) + '</td><td>' +
          (run.dryRun ? '계획만(dry run)' : '실행') + '</td><td class="num">' + esc(usd) +
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
      '<p class="section-sub"><b>긴 프롬프트로 진행</b>을 누르면 SFT 평가 없이 패키지를 만들고, ' +
      '패키지에는 긴 프롬프트·짧은 프롬프트·데이터셋(' + esc(doc.datasetRev || '없음') +
      ')과 학습 계획이 들어가요. <b>학습을 기다린다</b>를 누르면 학습 결과가 생길 때까지 ' +
      '평가 단계가 멈춰요.</p></section>'
    );
  }

  function buildPromptOnly(decision) {
    var answer = { decision: decision };
    if (decision === 'SELECT') answer.adopted = list(state.items.adoptOptions)[0] || 'LONG_BASE';
    return Object.assign(answer, details());
  }

  function renderPackage(items) {
    var pkg = items.package || {};
    var profile = pkg.profile || {};
    var profileRows = [
      ['이름', profile.name],
      ['성별·나이', (profile.gender || '') + ' · ' + (profile.age || '')],
      ['직업', profile.job],
      ['한 줄', profile.tagline],
      ['취미', profile.hobby],
      ['좋아함', profile.likes],
      ['싫어함', profile.dislikes],
      ['MBTI', profile.mbti],
      ['태그', joinList(profile.tags, ', ')],
      ['TMI', list(profile.tmiItems).map(function (t) { return t.text; }).join(' / ')]
    ];
    var chapters = list(pkg.chapters)
      .map(function (chapter) {
        return '<tr><td class="num">' + esc(chapter.chapterNo) + '</td><td>' +
          esc(chapter.title) + '</td><td>' + esc(chapter.relationshipStage) + '</td><td>' +
          esc(chapter.intro) + '</td></tr>';
      })
      .join('');
    var gates = list(pkg.gates)
      .map(function (gate) {
        return '<tr><td>' + esc(gate.gate) + '</td><td>' + esc(gate.rev) + '</td><td>' +
          esc(gate.decision) + '</td></tr>';
      })
      .join('');
    var videos = list(pkg.videos)
      .map(function (video) {
        return '<tr><td>' + esc(video.videoId) + '</td><td>' + esc(video.kind) + '</td><td>' +
          esc(video.chapterNo || '-') + '</td><td>' + esc(video.durationS || '-') + '</td><td>' +
          (video.synthetic ? '가짜 공급자' : '실제') + '</td></tr>';
      })
      .join('');
    var sft = pkg.sft || {};
    var verification = items.verification || {};
    return (
      '<section class="gate-section"><h2>프로필 카드</h2><div class="profile-card">' +
      profileRows
        .filter(function (row) { return row[1]; })
        .map(function (row) {
          return '<div><b>' + esc(row[0]) + '</b>' + esc(row[1]) + '</div>';
        })
        .join('') +
      '</div></section>' +
      '<section class="gate-section"><h2>챕터</h2>' +
      '<table class="gate-table"><thead><tr><th>#</th><th>제목</th><th>관계 단계</th>' +
      '<th>소개</th></tr></thead><tbody>' + chapters + '</tbody></table></section>' +
      '<section class="gate-section"><h2>영상</h2>' +
      '<table class="gate-table"><thead><tr><th>ID</th><th>종류</th><th>챕터</th><th>길이</th>' +
      '<th>출처</th></tr></thead><tbody>' + videos + '</tbody></table>' +
      (videos ? '' : '<p class="empty">영상이 아직 없다.</p>') + '</section>' +
      '<section class="gate-section"><h2>페르소나·SFT</h2>' + facts([
        ['persona', (pkg.persona || {}).personaVersion],
        ['데이터셋', sft.datasetRev],
        ['학습 기록', joinList(sft.trainingRuns, ' / ')],
        ['평가 보고서', sft.evalReport ||
          (sft.adoptedBinding === 'LONG_BASE' ? '없음 · 학습 없이 긴 프롬프트로 진행' : '없음')],
        ['채택 모델', sft.adoptedBinding]
      ]) + '</section>' +
      '<section class="gate-section"><h2>관문 기록</h2>' +
      '<table class="gate-table"><thead><tr><th>관문</th><th>rev</th><th>결정</th></tr>' +
      '</thead><tbody>' + gates + '</tbody></table></section>' +
      '<section class="gate-section"><h2>적재 확인</h2>' + facts([
        ['상태', verification.status],
        ['일회용 DB', verification.disposableDb ? '예' : '아니오']
      ]) +
      list(verification.steps)
        .map(function (step) {
          return '<p class="qa-note">' + (step.ok ? '✓ ' : '· ') + esc(step.name) + ' — ' +
            esc(step.detail) + '</p>';
        })
        .join('') + '</section>'
    );
  }

  function buildPackage(decision) {
    return Object.assign({ decision: decision }, details());
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
          '이 관문의 단계 코드가 아직 없다. 화면과 답 형식은 계약(LLD §5.14·§5.15·§5.17)대로 ' +
            '맞췄고, 지금 보이는 자료는 합성 예시다. 결정을 보내면 서버가 501로 답한다.'
        )
      );
    }
    if (view.synthetic) {
      out.push(banner('warn', '합성 예시', '실제 산출물이 아직 없어 계약 모양의 예시를 보여 준다.'));
    }
    list(view.missing).forEach(function (problem) {
      out.push(banner('bad', '자료 확인', problem));
    });
    if (view.record) {
      out.push(
        banner(
          'ok',
          '이미 기록된 결정',
          '결정 ' + view.record.decision + ' · 검토자 ' + (view.record.reviewer || '') +
            ' · 기록 ' + (view.recordRef || '')
        )
      );
    }
    if (view.status === 'AWAITING_HUMAN' && !view.record) {
      out.push(banner('warn', '사람 검토 대기', '이 관문은 사람 결정을 기다리고 있다.'));
    }
    if (view.status === 'PENDING' && view.connected !== false) {
      out.push(
        banner('warn', '아직 차례가 아님', '앞 단계가 끝나야 이 관문이 열린다. 먼저 작업을 돌린다.')
      );
    }
    return out.join('');
  }

  function renderActionsBar(view, meta) {
    var host = q('[data-actions]');
    var locked = view.status === 'APPROVED' || view.status === 'REJECTED';
    host.innerHTML = meta.actions
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
      : '기록 없음';
  }

  function render() {
    var view = state.view;
    var items = state.items;
    var meta = KINDS[state.kind];
    var summary = (state.character && state.character.summary) || {};
    var name = summary.name || state.characterId;
    var back = 'c-glass.html?character=' + encodeURIComponent(state.characterId) +
      '&gate=' + encodeURIComponent(state.gate);
    q('[data-workroom-link]').setAttribute('href', back);
    q('[data-crumbs]').innerHTML =
      '<a href="c-glass.html">작업실</a> › <a href="' + esc(back) + '">' + esc(name) +
      '</a> › <b>' + esc(state.gate + ' ' + (view.title || '')) + '</b>';
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
    q('[data-kicker]').textContent = state.gate + ' · ' + (view.title || '');
    q('[data-title]').textContent = view.title || state.gate;
    q('[data-desc]').textContent = (meta && meta.hint) || '';
    q('[data-meta]').innerHTML =
      '<span>캐릭터 <code>' + esc(state.characterId) + '</code></span>' +
      '<span>revision <code>' + esc(view.rev || '-') + '</code></span>' +
      '<span>상태 ' + esc(STATUS_KO[view.status] || view.status || '-') + '</span>' +
      (view.recordRef ? '<span>기록 <code>' + esc(view.recordRef) + '</code></span>' : '') +
      '<span>' + esc(connectionLabel(view)) + '</span>';
    q('[data-banners]').innerHTML = renderBanners(view, items);
    q('[data-body]').innerHTML = meta
      ? meta.render(items)
      : '<p class="empty">화면 종류를 모른다: ' + esc(state.kind) + '</p>';
    q('[data-side-hint]').textContent = (meta && meta.hint) || '';
    if (meta) renderActionsBar(view, meta);
    renderRaw(view);
    setStatus('');
    bindBody();
  }

  function bindBody() {
    var pick = q('input[name="planPick"]');
    if (pick) renderPlanFields();
    qa('input[name="planPick"]').forEach(function (node) {
      node.addEventListener('change', renderPlanFields);
    });
    var clusterPick = q('[data-cluster-pick]');
    if (clusterPick) {
      renderClusterBody(clusterPick.value);
      clusterPick.addEventListener('change', function () {
        renderClusterBody(clusterPick.value);
      });
    }
  }

  // ---------------------------------------------------------------- 전송
  function currentAnswer(decision) {
    var meta = KINDS[state.kind];
    if (!meta) throw Error('화면 종류를 모른다: ' + state.kind);
    return meta.build(decision);
  }

  function showAnswer(answer) {
    var out = q('[data-answer-json]');
    out.hidden = false;
    out.textContent = JSON.stringify(answer, null, 2);
  }

  function send(decision) {
    if (state.busy) return;
    var answer;
    try {
      answer = currentAnswer(decision);
    } catch (error) {
      setStatus(error.message, 'bad');
      return;
    }
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
        var message = '기록했다: ' + (data.recordRef || '') + ' · 상태 ' + recorded;
        // 다시 그리면 상태 줄이 지워지므로 새로 읽은 뒤에 기록 결과를 보여 준다.
        return load().then(function () {
          setStatus(message, 'ok');
        });
      })
      .catch(function (error) {
        if (error.status === 501) {
          setStatus('아직 연결 전: 이 관문의 결정 경로가 서버에 없다.', 'bad');
          q('[data-banners]').insertAdjacentHTML(
            'afterbegin',
            banner(
              'synthetic',
              '아직 연결 전',
              error.message + ' · 화면과 답 형식은 계약대로 준비돼 있다.'
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
      });
  }

  // ---------------------------------------------------------------- 초기화
  function showEmpty(message) {
    q('[data-title]').textContent = '관문을 열지 못했다';
    q('[data-desc]').textContent = message;
    q('[data-body]').innerHTML = '<p class="empty">' + esc(message) + '</p>';
    setStatus(message, 'bad');
  }

  function load() {
    if (!state.characterId || !state.gate) {
      showEmpty('주소에 character와 gate가 필요하다. 작업실에서 관문 칩을 눌러 연다.');
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
        render();
        document.title = '캐릭터 공장 · ' + state.gate + ' ' + (view.title || '');
      })
      .catch(function (error) {
        showEmpty('관문 자료를 읽지 못했다: ' + error.message);
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
        setStatus('답 JSON을 만들었다. 서버로 보내기 전에 확인한다.');
      } catch (error) {
        setStatus(error.message, 'bad');
      }
      return;
    }
    var pick = event.target.closest('[data-pick]');
    if (pick) {
      var pairId = pick.getAttribute('data-pair-id');
      var choice = pick.getAttribute('data-pick');
      state.pairs[pairId] = choice;
      var group = pick.parentElement;
      Array.prototype.slice.call(group.querySelectorAll('[data-pick]')).forEach(function (node) {
        node.setAttribute('aria-pressed', String(node === pick));
      });
      var pair = pick.closest('.pair');
      if (pair) {
        Array.prototype.slice.call(pair.querySelectorAll('.pair-answer')).forEach(function (box) {
          box.classList.toggle('is-picked', box.getAttribute('data-answer') === choice);
        });
      }
      var total = qa('.pair').length;
      var done = Object.keys(state.pairs).length;
      var counter = q('[data-blind-count]');
      if (counter) counter.textContent = done + ' / ' + total;
      if (total && done >= total) {
        var after = q('[data-after-blind]');
        var wait = q('[data-blind-wait]');
        if (after) after.hidden = false;
        if (wait) wait.hidden = true;
      }
    }
  });

  load().then(watch);
})();
