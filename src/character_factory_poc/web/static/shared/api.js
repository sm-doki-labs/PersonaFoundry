// 실제 공장 API를 부르는 얇은 어댑터. 시안의 가짜 데이터(shared/data.js) 대신 서버 값을 쓴다.
// 경로는 LLD §6.5 워크숍 API 표와 같다. 화면 코드는 이 파일만 거쳐 서버를 부른다.
(function () {
  'use strict';
  var BASE = window.CF_API_BASE || '';

  function request(path, options) {
    var opts = options || {};
    var headers = Object.assign({ Accept: 'application/json' }, opts.headers || {});
    var init = Object.assign({}, opts, { headers: headers });
    return fetch(BASE + path, init).then(function (res) {
      return res.text().then(function (text) {
        var body = null;
        if (text) {
          try {
            body = JSON.parse(text);
          } catch (e) {
            body = { detail: text };
          }
        }
        if (!res.ok) {
          var detail = body && body.detail ? body.detail : res.status + ' ' + res.statusText;
          var err = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
          err.status = res.status;
          err.body = body;
          throw err;
        }
        return body;
      });
    });
  }

  function enc(value) {
    return encodeURIComponent(String(value));
  }

  function filePath(id, path) {
    return '/api/files/' + enc(id) + '/' + String(path).split('/').map(enc).join('/');
  }

  var api = {
    base: BASE,
    request: request,
    health: function () {
      return request('/api/health');
    },
    projects: function () {
      return request('/api/projects');
    },
    character: function (id) {
      return request('/api/characters/' + enc(id));
    },
    gate: function (id, gate) {
      return request('/api/characters/' + enc(id) + '/gates/' + enc(gate));
    },
    fileUrl: function (id, path) {
      return BASE + filePath(id, path);
    },
    decide: function (id, gate, answer) {
      return request('/api/characters/' + enc(id) + '/gates/' + enc(gate) + '/decision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(answer)
      });
    },
    startRun: function (id, until, confirm) {
      var body = { characterId: id, action: 'run' };
      if (until) body.until = until;
      if (confirm && confirm.length) body.confirm = confirm.slice();
      return request('/api/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
    },
    job: function (jobId) {
      return request('/api/jobs/' + enc(jobId));
    },
    jobs: function (characterId) {
      return request('/api/jobs' + (characterId ? '?characterId=' + enc(characterId) : ''));
    },
    events: function (onEvent, options) {
      var opts = options || {};
      var qs = [];
      if (opts.characterId) qs.push('characterId=' + enc(opts.characterId));
      if (!window.EventSource) {
        return { close: function () {} };
      }
      var source = new EventSource(BASE + '/api/events' + (qs.length ? '?' + qs.join('&') : ''));
      ['hello', 'job', 'state', 'gate'].forEach(function (name) {
        source.addEventListener(name, function (event) {
          var data = null;
          try {
            data = JSON.parse(event.data);
          } catch (e) {
            data = { type: name, raw: event.data };
          }
          onEvent(name, data);
        });
      });
      source.onerror = function () {
        onEvent('error', { type: 'error' });
      };
      return source;
    }
  };

  window.CF_API = api;
})();
