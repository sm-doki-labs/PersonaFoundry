// 시안 화면 위에 실제 공장 값을 얹는 얇은 패널. 프로젝트 목록·갈래별 진행·대기 관문·작업 큐.
// 대기 관문 칩은 관문 상세 화면(gate.html)을 연다. 값은 SSE(state·gate·job)로 갱신한다.
(function () {
  'use strict';
  var api = window.CF_API;
  if (!api) return;
  var roots = Array.prototype.slice.call(document.querySelectorAll('[data-factory-live]'));
  if (!roots.length) return;

  var STATUS_KO = {
    PENDING: '대기',
    RUNNING: '진행 중',
    CHECK_FAILED: '검사 실패',
    AWAITING_HUMAN: '사람 검토',
    APPROVED: '승인',
    REJECTED: '반려',
    SKIPPED: '건너뜀'
  };
  var STAGE_KO = {
    s1: '근거',
    s2: '기준 사진',
    s3: '기획',
    s3r: '참고 자료',
    s4a: '배경',
    s4b: '장면·자세',
    s4: '완성 이미지',
    s5: '소개 영상',
    s6: '동작 영상',
    s7: '특질',
    s8: '프롬프트',
    s9s: '데이터 샘플',
    s9: '데이터셋',
    s10t: '학습',
    s10: '평가',
    s11: '패키지',
    sx: '내보내기'
  };
  var UNTIL_CHOICES = ['G3', 'G4a', 'G4b', 'G4', 'G5', 'G5b', 'G6'];

  var view = {
    data: null,
    details: {},
    mode: 'ops',
    error: '',
    connected: false,
    timer: null,
    source: null
  };
  var refreshTimer = null;

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function modeOf(root) {
    return root.getAttribute('data-factory-live') || 'ops';
  }

  function statusClass(status) {
    return 'is-' + String(status || 'PENDING').toLowerCase();
  }

  function stageChips(character) {
    var stages = (character.stages || []).filter(function (s) {
      return s.implemented;
    });
    if (!stages.length) return '<span class="cf-quiet">단계 기록 없음</span>';
    return (
      '<div class="cf-rail" role="list">' +
      stages
        .map(function (s) {
          var label = STATUS_KO[s.status] || s.status;
          var title = s.id + ' ' + s.name + ' · ' + label;
          if (s.gate && s.gateStatus === 'AWAITING_HUMAN') title += ' · ' + s.gate + ' 대기';
          return (
            '<span class="cf-step ' +
            statusClass(s.status) +
            '" role="listitem" title="' +
            esc(title) +
            '"><b>' +
            esc(s.id.toUpperCase()) +
            '</b><span>' +
            esc(STAGE_KO[s.id] || s.name) +
            '</span></span>'
          );
        })
        .join('') +
      '</div>'
    );
  }

  // 대기 관문은 서버가 정한 대기열 순서(queue)를 그대로 쓴다(LLD §6.10).
  // queue에 없는 대기 관문(옛 기록 등)은 뒤에 붙인다.
  function orderedGates(character) {
    var pending = character.pendingGates || [];
    var queue = character.queue || [];
    var left = {};
    pending.forEach(function (g) {
      left[g.id] = g;
    });
    var out = [];
    queue.forEach(function (q) {
      var g = left[q.gate];
      if (!g) return;
      out.push({ id: g.id, title: g.title, unblocks: q.unblocks });
      delete left[q.gate];
    });
    pending.forEach(function (g) {
      if (left[g.id]) out.push({ id: g.id, title: g.title, unblocks: null });
    });
    return out;
  }

  // 그 관문을 결정하면 풀리는 뒤쪽 단계 수를 짧은 문장으로 쓴다.
  function unblocksLabel(count) {
    if (typeof count !== 'number') return '';
    return count > 0 ? '뒤쪽 ' + count + '단계' : '뒤 단계 없음';
  }

  function gateLinks(character) {
    var gates = orderedGates(character);
    if (!gates.length) return '<span class="cf-quiet">기다리는 관문 없음</span>';
    return gates
      .map(function (g) {
        var href =
          'gate.html?character=' +
          encodeURIComponent(character.id) +
          '&gate=' +
          encodeURIComponent(g.id);
        var json = api.base + '/api/characters/' + encodeURIComponent(character.id) + '/gates/' + encodeURIComponent(g.id);
        var wait = unblocksLabel(g.unblocks);
        var title = g.id + ' ' + (g.title || '') + (wait ? ' · ' + wait : '') + ' 상세 화면을 연다';
        return (
          '<span class="cf-gatewrap"><a class="cf-gate" href="' +
          href +
          '" title="' +
          esc(title) +
          '">' +
          '<b>' +
          esc(g.id) +
          '</b>' +
          esc(g.title || '') +
          (wait ? '<span class="cf-gate-wait">' + esc(wait) + '</span>' : '') +
          ' <em>열기</em></a>' +
          '<a class="cf-gate-json" href="' +
          json +
          '" target="_blank" rel="noopener" aria-label="' +
          esc(g.id + ' 검토 항목 JSON') +
          '">JSON</a></span>'
        );
      })
      .join(' ');
  }

  // 유료 공급자를 쓰는 단계는 사람이 실행을 확인하기 전에는 돌지 않는다(LLD §6.7).
  function heldChips(character) {
    var detail = view.details[character.id];
    var held = (detail && detail.held) || [];
    if (!held.length) return '';
    var items = held
      .map(function (h) {
        var plan = (h.providers || []).join(', ');
        return (
          '<span class="cf-held-item" role="listitem"><b>실행 확인 대기</b>' +
          '<span class="cf-held-stage">' +
          esc(STAGE_KO[h.stage] || h.stage) +
          '</span>' +
          (plan ? '<span class="cf-held-plan">' + esc(plan) + '</span>' : '') +
          '<button type="button" class="cf-btn cf-btn--primary cf-btn--small" data-live-confirm="' +
          esc(character.id) +
          '" data-stage="' +
          esc(h.stage) +
          '">실행</button></span>'
        );
      })
      .join('');
    return '<div class="cf-held" role="list" aria-label="실행 확인 대기">' + items + '</div>';
  }

  function laneBars(character) {
    var lanes = character.lanes || [];
    if (!lanes.length) return '';
    return (
      '<div class="cf-lanes" role="list" aria-label="갈래별 진행">' +
      lanes
        .map(function (lane) {
          var percent = Number(lane.percent || 0);
          var title = lane.label + ' · ' + lane.done + '/' + lane.total;
          if (lane.pendingGates && lane.pendingGates.length) {
            title += ' · 대기 ' + lane.pendingGates.join(', ');
          }
          return (
            '<a class="cf-lane is-' +
            esc(lane.status) +
            '" role="listitem" href="' +
            laneHref(character, lane) +
            '" title="' +
            esc(title) +
            '">' +
            '<span class="cf-lane-name">' +
            esc(lane.label) +
            '</span>' +
            '<span class="cf-lane-bar"><i style="width:' +
            percent +
            '%"></i></span>' +
            '<span class="cf-lane-num">' +
            lane.done +
            '/' +
            lane.total +
            '</span>' +
            (lane.pendingGates && lane.pendingGates.length
              ? '<span class="cf-lane-gate">' + esc(lane.pendingGates.join(' · ')) + '</span>'
              : '') +
            '</a>'
          );
        })
        .join('') +
      '</div>'
    );
  }

  function laneHref(character, lane) {
    var id = encodeURIComponent(character.id);
    if (!lane.pendingGates || !lane.pendingGates.length) {
      return 'c-glass.html?character=' + id;
    }
    return 'gate.html?character=' + id + '&gate=' + encodeURIComponent(lane.pendingGates[0]);
  }

  function jobChip(job) {
    var active = job.status === 'running' || job.status === 'queued';
    var label =
      job.status === 'succeeded'
        ? '완료'
        : job.status === 'failed'
          ? '실패'
          : active
            ? '진행 중'
            : job.status;
    var tail = job.stoppedAt ? ' · ' + job.stoppedAt + ' 멈춤' : '';
    return (
      '<li class="cf-queue-item is-' +
      esc(active ? 'running' : job.status) +
      '"><b>' +
      esc(label) +
      '</b><span>' +
      esc(job.characterId) +
      ' · ' +
      esc(job.until) +
      '까지' +
      esc(tail) +
      '</span><code>' +
      esc(job.jobId) +
      '</code></li>'
    );
  }

  function queueList(data, characterId) {
    var jobs = (data.jobs || []).filter(function (job) {
      return !characterId || job.characterId === characterId;
    });
    var items = jobs.slice(0, 6);
    var running = (data.totals || {}).runningJobs || 0;
    return (
      '<div class="cf-queue"><h3>작업 큐 <span class="cf-quiet">진행 ' +
      running +
      '</span></h3>' +
      (items.length
        ? '<ul>' + items.map(jobChip).join('') + '</ul>'
        : '<p class="cf-quiet">최근 작업이 없다.</p>') +
      '</div>'
    );
  }

  function jobLine(character) {
    var job = character.job || character.lastJob;
    if (!job) return '<span class="cf-quiet">작업 없음</span>';
    var active = job.status === 'running' || job.status === 'queued';
    var label = active ? '작업 중' : job.status === 'succeeded' ? '마지막 작업 완료' : '마지막 작업 실패';
    var result = job.result || {};
    var tail = result.stoppedAt ? ' · ' + result.stoppedAt + '에서 멈춤' : '';
    var reason = job.error ? ' · ' + job.error : '';
    return (
      '<span class="cf-job ' +
      statusClass(active ? 'RUNNING' : job.status === 'succeeded' ? 'APPROVED' : 'CHECK_FAILED') +
      '">' +
      esc(label) +
      ' · ' +
      esc(job.until) +
      '까지' +
      esc(tail + reason) +
      ' · ' +
      esc(job.jobId) +
      '</span>'
    );
  }

  function runControls(character) {
    var options = UNTIL_CHOICES.map(function (gate) {
      return (
        '<option value="' +
        esc(gate) +
        '"' +
        (gate === 'G6' ? ' selected' : '') +
        '>' +
        esc(gate) +
        '</option>'
      );
    }).join('');
    var disabled = character.job ? ' disabled' : '';
    return (
      '<div class="cf-actions">' +
      '<label class="cf-until">여기까지 <select data-live-until="' +
      esc(character.id) +
      '"' +
      disabled +
      '>' +
      options +
      '</select></label>' +
      '<button type="button" class="cf-btn cf-btn--primary" data-live-run="' +
      esc(character.id) +
      '"' +
      disabled +
      '>작업 실행</button>' +
      jobLine(character) +
      '</div>'
    );
  }

  function characterCard(character, compact) {
    var persona = character.persona || {};
    var meta = [persona.age ? persona.age + '세' : '', persona.job || ''].filter(Boolean).join(' · ');
    var progress = character.progress || { done: 0, total: 0, percent: 0 };
    return (
      '<article class="cf-char' +
      (compact ? ' cf-char--compact' : '') +
      '">' +
      '<div class="cf-char-top">' +
      '<b class="cf-name">' +
      esc(character.name || character.id) +
      '</b>' +
      '<code class="cf-id">' +
      esc(character.id) +
      '</code>' +
      (meta ? '<span class="cf-meta">' + esc(meta) + '</span>' : '') +
      '<span class="cf-prog">' +
      progress.done +
      '/' +
      progress.total +
      ' 단계 · ' +
      progress.percent +
      '%</span>' +
      '</div>' +
      '<div class="cf-bar"><i style="width:' +
      Number(progress.percent || 0) +
      '%"></i></div>' +
      stageChips(character) +
      laneBars(character) +
      '<div class="cf-gates">대기 관문 ' + gateLinks(character) + '</div>' +
      heldChips(character) +
      runControls(character) +
      (character.stateError ? '<p class="cf-warn">' + esc(character.stateError) + '</p>' : '') +
      '</article>'
    );
  }

  function briefCard(brief) {
    var marks = [];
    if (brief.hasBrief) marks.push('brief.md');
    if (brief.hasPlan) marks.push('plan.json');
    if (brief.hasProbes) marks.push('probes.txt');
    return (
      '<li class="cf-brief"><code>' +
      esc(brief.id) +
      '</code><span>' +
      (marks.length ? esc(marks.join(' · ')) : '파일 없음') +
      '</span></li>'
    );
  }

  function totalsLine(data) {
    var totals = data.totals || {};
    return (
      '캐릭터 ' +
      (totals.characters || 0) +
      ' · 대기 관문 ' +
      (totals.pendingGates || 0) +
      ' · 브리프 ' +
      (totals.briefs || 0) +
      ' · 작업 중 ' +
      (totals.runningJobs || 0)
    );
  }

  function opsBody(data) {
    var chars = data.characters || [];
    var cards = chars.length
      ? chars.map(function (c) {
          return characterCard(c, false);
        }).join('')
      : '<p class="cf-empty">아직 만든 캐릭터가 없어요. 브리프를 넣고 S1부터 돌리면 여기에 나타납니다.</p>';
    var briefs = data.briefs || [];
    var briefList = briefs.length
      ? '<ul class="cf-briefs">' + briefs.map(briefCard).join('') + '</ul>'
      : '<p class="cf-empty">runs/briefs가 비어 있어요.</p>';
    return (
      '<div class="cf-chars">' + cards + '</div>' +
      queueList(data) +
      '<div class="cf-brief-block"><h3>브리프</h3>' + briefList + '</div>'
    );
  }

  function pickCharacter(data) {
    var params = new URLSearchParams(location.search);
    var wanted = params.get('character');
    var chars = data.characters || [];
    if (wanted) {
      var hit = chars.filter(function (c) {
        return c.id === wanted;
      })[0];
      if (hit) return hit;
    }
    var awaiting = chars.filter(function (c) {
      return c.awaitingHuman;
    })[0];
    return awaiting || chars[0] || null;
  }

  function workroomBody(data) {
    var character = pickCharacter(data);
    if (!character) {
      return '<p class="cf-empty">아직 만든 캐릭터가 없어요. 운영 화면에서 브리프를 확인하세요.</p>';
    }
    var params = new URLSearchParams(location.search);
    var gate = params.get('gate');
    var pending = (character.pendingGates || []).filter(function (g) {
      return !gate || g.id === gate;
    });
    var note = gate
      ? '<p class="cf-note">' +
        esc(gate) +
        ' 상세 화면을 엽니다. 아래 관문 칩을 누르면 고르기·승인·수정 요청을 그 화면에서 합니다.</p>'
      : '<p class="cf-note">대기 관문 칩을 누르면 관문 상세 화면이 열립니다. 갈래 막대를 누르면 그 갈래의 관문으로 갑니다.</p>';
    var jump = pending.length
      ? '<p class="cf-jump"><a class="cf-btn cf-btn--primary" href="gate.html?character=' +
        encodeURIComponent(character.id) +
        '&gate=' +
        encodeURIComponent(pending[0].id) +
        '">' +
        esc(pending[0].id + ' ' + (pending[0].title || '') + ' 열기') +
        '</a></p>'
      : '';
    return characterCard(character, true) + jump + queueList(data, character.id) + note;
  }

  function renderRoot(root) {
    var mode = modeOf(root);
    var status = view.error
      ? '<p class="cf-error">' + esc(view.error) + '</p>'
      : '<p class="cf-live-sub">' + esc(view.data ? totalsLine(view.data) : '불러오는 중…') + '</p>';
    var body = '';
    if (view.data) body = mode === 'workroom' ? workroomBody(view.data) : opsBody(view.data);
    root.innerHTML =
      '<div class="cf-live-head">' +
      '<div><h2>실제 공장 현황</h2>' +
      status +
      '</div>' +
      '<div class="cf-live-actions">' +
      '<span class="cf-conn' +
      (view.connected ? ' is-on' : '') +
      '">' +
      (view.connected ? '실시간 연결' : '새로고침으로 갱신') +
      '</span>' +
      '<button type="button" class="cf-btn" data-live-refresh>새로고침</button>' +
      '</div></div>' +
      body;
  }

  function render() {
    roots.forEach(renderRoot);
  }

  function setError(message) {
    view.error = message || '';
    render();
  }

  function refresh() {
    return api
      .projects()
      .then(function (data) {
        view.data = data;
        view.error = '';
        render();
        return data;
      })
      .catch(function (err) {
        setError('공장 상태를 읽지 못했다: ' + err.message);
        throw err;
      })
      .then(function (data) {
        return loadDetails(data).then(function () {
          return data;
        });
      });
  }

  // 실행 확인 대기(held)와 상세 값은 GET /api/characters/{id}에만 있다.
  function wantedDetails(data) {
    var ids = [];
    (data.characters || []).forEach(function (c) {
      var last = c.lastJob || null;
      if (last && last.held && last.held.length) ids.push(c.id);
    });
    if (view.mode === 'workroom') {
      var picked = pickCharacter(data);
      if (picked) ids.push(picked.id);
    }
    return ids.filter(function (id, i) {
      return ids.indexOf(id) === i;
    });
  }

  function loadDetails(data) {
    var ids = wantedDetails(data);
    if (!ids.length) {
      view.details = {};
      render();
      return Promise.resolve();
    }
    return Promise.all(
      ids.map(function (id) {
        return api.character(id).catch(function () {
          return null;
        });
      })
    ).then(function (list) {
      var next = {};
      list.forEach(function (item) {
        if (item && item.id) next[item.id] = item;
      });
      view.details = next;
      render();
    });
  }

  function startRun(characterId, until) {
    setError('');
    api
      .startRun(characterId, until)
      .then(function () {
        return refresh();
      })
      .catch(function (err) {
        setError('작업을 시작하지 못했다: ' + err.message);
      });
  }

  // "실행" 버튼: 이 단계만 실행을 확인했다고 함께 보낸다(POST /api/jobs confirm).
  // 자동 재개와 같이 끝(sx)까지 돌려 다른 갈래도 이어서 진행한다.
  function confirmRun(characterId, stage) {
    setError('');
    api
      .startRun(characterId, 'sx', [stage])
      .then(function () {
        return refresh();
      })
      .catch(function (err) {
        setError('실행을 시작하지 못했다: ' + err.message);
      });
  }

  function scheduleRefresh() {
    if (refreshTimer) return;
    refreshTimer = setTimeout(function () {
      refreshTimer = null;
      refresh().catch(function () {});
    }, 400);
  }

  function connect() {
    if (view.source || !api.events) return;
    view.source = api.events(function (name, data) {
      if (name === 'hello') {
        view.connected = true;
        render();
        return;
      }
      if (name === 'error') {
        view.connected = false;
        render();
        if (!view.timer) {
          view.timer = setInterval(function () {
            refresh().catch(function () {});
          }, 15000);
        }
        return;
      }
      view.connected = true;
      if (name === 'state' || name === 'job' || name === 'gate') {
        scheduleRefresh();
      }
    });
  }

  document.addEventListener('click', function (event) {
    var refreshButton = event.target.closest('[data-live-refresh]');
    if (refreshButton) {
      refresh().catch(function () {});
      return;
    }
    var runButton = event.target.closest('[data-live-run]');
    if (runButton) {
      var id = runButton.getAttribute('data-live-run');
      var select = document.querySelector('[data-live-until="' + id + '"]');
      startRun(id, select ? select.value : null);
      return;
    }
    var confirmButton = event.target.closest('[data-live-confirm]');
    if (confirmButton) {
      confirmRun(
        confirmButton.getAttribute('data-live-confirm'),
        confirmButton.getAttribute('data-stage')
      );
    }
  });

  view.mode = modeOf(roots[0]);
  refresh().catch(function () {});
  connect();
})();
