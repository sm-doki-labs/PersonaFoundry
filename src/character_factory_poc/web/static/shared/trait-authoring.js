(function () {
  'use strict';
  const byId = id => document.getElementById(id);
  const fieldNames = ['personality', 'job', 'age', 'gender', 'background', 'notes'];
  const drafts = new Map();
  const state = { id: '', epoch: 0, saving: false, loading: false, catalog: null,
    catalogLoading: false, catalogRequest: 0, seedController: null, resultController: null, resultRequest: 0 };
  let resultItems = [];
  let searchTimer;
  const draft = () => drafts.get(state.id);

  function message(id, text, error = false) {
    byId(id).textContent = text;
    byId(id).dataset.tone = error ? 'error' : '';
  }

  async function request(path, body, signal) {
    const options = { signal, headers: { Accept: 'application/json' } };
    if (body !== undefined) {
      options.method = 'POST';
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(body);
    }
    const response = await fetch((window.CF_API_BASE || '') + path, options);
    if (!response.ok) {
      const error = new Error('HTTP ' + response.status);
      error.status = response.status;
      // Translate only known validation fields; never display raw payloads or paths.
      if ([400, 422].includes(response.status)) {
        try {
          const payload = await response.json();
          error.validationMessage = validationCopy(payload.detail);
        } catch (_) { /* Keep the HTTP failure even when its body is not JSON. */ }
      }
      throw error;
    }
    return response.json();
  }

  function validationCopy(detail) {
    const hints = Array.isArray(detail) ? detail.flatMap(item =>
      item && Array.isArray(item.loc) ? item.loc.filter(value => typeof value === 'string') : []
    ).join(' ') : typeof detail === 'string' ? detail : '';
    const messages = [];
    if (/\bage\b|나이/.test(hints)) messages.push('나이를 18~150세의 정수로 입력해 다시 저장해 주세요.');
    if (/\bgender\b|성별/.test(hints)) messages.push('성별을 여성·남성·기타 중 하나로 선택해 다시 저장해 주세요.');
    if (/\bpersonality\b|성격/.test(hints)) messages.push('성격을 1~5,000자로 입력해 주세요.');
    if (/\bjob\b|직업/.test(hints)) messages.push('직업은 1,000자 이내로 입력해 주세요.');
    if (/\bbackground\b|배경/.test(hints)) messages.push('배경은 5,000자 이내로 입력해 주세요.');
    if (/\bnotes\b|메모/.test(hints)) messages.push('메모는 5,000자 이내로 입력해 주세요.');
    return messages.join(' ');
  }

  function errorCopy(error, action) {
    if (error.status === 409) return '설정이나 특질 목록이 바뀌었거나 작업이 진행 중입니다. 현재 입력은 유지됩니다. 설정을 다시 불러온 뒤 확인해 주세요.';
    if (error.status === 422 || error.status === 400) return error.validationMessage || '입력 내용을 처리할 수 없습니다. 성격, 나이(18~150세), 성별과 선택한 특질을 확인하고 다시 시도해 주세요.';
    if (error.status === 403) return '지금은 이 캐릭터의 설정을 수정할 수 없습니다. 설정을 다시 불러와 상태를 확인해 주세요.';
    if (error.status === 404) return action + '에 필요한 자료를 찾지 못했습니다. 목록이나 설정을 다시 불러와 주세요.';
    if (error.status === 429) return '요청이 많습니다. 잠시 기다렸다가 다시 시도해 주세요.';
    return action + '에 실패했습니다. 연결 상태를 확인하고 다시 시도해 주세요. 현재 입력과 선택은 유지됩니다.';
  }

  function syncControls() {
    const d = draft();
    const locked = state.saving || state.loading || !d || !d.editable || d.stale;
    byId('editor').disabled = locked;
    byId('character').disabled = state.saving || byId('character').options.length < 2;
    ['retry-projects', 'retry-seed', 'retry-catalog'].forEach(id => { byId(id).disabled = state.saving; });
    byId('save').disabled = locked || (d.selected.length > 0 && (!state.catalog || state.catalogLoading));
    ['recommend', 'search-button', 'browse', 'search'].forEach(id => {
      byId(id).disabled = locked || !state.catalog || state.catalogLoading;
    });
    byId('save').textContent = state.saving ? '설정 저장 중…' : '설정 저장';
    byId('authoring-form').setAttribute('aria-busy', String(state.saving || state.loading));
    byId('dirty-status').textContent = state.saving ? '저장 중에는 입력과 캐릭터를 바꿀 수 없습니다.' :
      !d ? '저장할 캐릭터를 선택해 주세요.' : d.dirty ? '아직 저장하지 않은 변경이 있습니다.' : '변경한 내용이 없습니다.';
  }

  function hideSaved() {
    byId('save-result').hidden = true;
    byId('next-link').hidden = true;
    byId('next-link').removeAttribute('href');
  }

  function changed() {
    if (!draft() || state.saving) return;
    draft().dirty = true;
    hideSaved();
    syncControls();
  }

  function cancelResults(text) {
    clearTimeout(searchTimer);
    state.resultRequest++;
    if (state.resultController) state.resultController.abort();
    state.resultController = null;
    resultItems = [];
    byId('results-list').replaceChildren();
    byId('results-region').setAttribute('aria-busy', 'false');
    if (text) message('results-status', text);
  }

  function renderSelected() {
    const selected = draft() ? draft().selected : [];
    const list = byId('selected-list');
    list.replaceChildren();
    byId('selected-count').textContent = selected.length + ' / 5';
    byId('selected-empty').hidden = selected.length > 0;
    selected.forEach((item, index) => {
      const li = document.createElement('li');
      li.className = 'trait-row';
      const text = document.createElement('p');
      text.textContent = item.behavior;
      const actions = document.createElement('div');
      actions.className = 'trait-actions';
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.textContent = '제거';
      remove.setAttribute('aria-label', item.behavior + ' 특질 제거');
      remove.addEventListener('click', () => {
        if (state.saving || !draft().editable || draft().stale) return;
        draft().selected = draft().selected.filter(value => value.traitId !== item.traitId);
        changed();
        const remaining = resultItems.slice();
        cancelResults('선택을 바꿨습니다. 남은 후보를 고르거나 다시 추천받을 수 있습니다.');
        resultItems = remaining;
        renderSelected();
        renderResults();
        const buttons = list.querySelectorAll('button');
        (buttons[Math.min(index, buttons.length - 1)] || byId('recommend')).focus();
      });
      actions.append(remove);
      li.append(text, actions);
      list.append(li);
    });
  }

  const categories = { reinforce: '성격을 선명하게', contrast: '대비되는 성향', explore: '다른 방향 탐색',
    related: '성격과 가까운 행동', strong: '성격과 가까운 행동',
    strongly_related: '성격과 가까운 행동', unexpected: '의외의 면', surprising: '의외의 면',
    alternative: '다른 방향', different: '다른 방향' };

  function renderResults() {
    const list = byId('results-list');
    list.replaceChildren();
    if (!draft()) return;
    resultItems.forEach(item => {
      if (draft().selected.some(value => value.traitId === item.traitId)) return;
      const li = document.createElement('li');
      li.className = 'trait-row';
      const behavior = document.createElement('p');
      behavior.textContent = item.behavior;
      li.append(behavior);
      if (item.reason || categories[item.category]) {
        const reason = document.createElement('p');
        reason.className = 'hint';
        reason.textContent = [categories[item.category], item.reason].filter(Boolean).join(' · ');
        li.append(reason);
      }
      const actions = document.createElement('div');
      actions.className = 'trait-actions';
      const add = document.createElement('button');
      add.type = 'button';
      add.textContent = draft().selected.length >= 5 ? '최대 5개 선택됨' : '추가';
      add.disabled = draft().selected.length >= 5;
      add.setAttribute('aria-label', item.behavior + ' 특질 추가');
      add.addEventListener('click', () => {
        const d = draft();
        if (state.saving || !d.editable || d.stale || d.selected.length >= 5 || d.selected.some(value => value.traitId === item.traitId)) return;
        d.selected.push({ traitId: item.traitId, behavior: item.behavior, presetId: item.presetId,
          sourceField: item.sourceField, catalogSha256: item.catalogSha256 });
        changed();
        const remaining = resultItems.filter(value => value.traitId !== item.traitId);
        cancelResults('특질을 추가했습니다. 남은 후보를 고르거나 현재 선택에서 제거할 수 있습니다.');
        resultItems = remaining;
        renderSelected();
        renderResults();
        byId('selected-list').lastElementChild.querySelector('button').focus();
      });
      const dismiss = document.createElement('button');
      dismiss.type = 'button';
      dismiss.textContent = '이번엔 제외';
      dismiss.setAttribute('aria-label', item.behavior + ' 추천에서 제외');
      dismiss.addEventListener('click', () => {
        if (state.saving) return;
        draft().dismissed.add(item.traitId);
        resultItems = resultItems.filter(value => value.traitId !== item.traitId);
        renderResults();
        message('results-status', resultItems.length ? '남은 후보를 확인하거나 다시 추천받을 수 있습니다.' : '후보를 모두 제외했습니다. 다시 추천받거나 다른 단어로 검색해 주세요.');
        (byId('results-list').querySelector('button') || byId('recommend')).focus();
      });
      actions.append(add, dismiss);
      li.append(actions);
      list.append(li);
    });
  }

  async function getResults(mode) {
    const d = draft();
    if (!d || !d.editable || d.stale || state.loading || state.saving || !state.catalog || state.catalogLoading) return;
    cancelResults();
    const personality = byId('personality').value.trim();
    if (mode === 'recommend' && !personality) {
      message('results-status', '성격을 먼저 적어 주세요. 성격 없이도 직접 검색하거나 둘러볼 수 있습니다.');
      byId('personality').focus();
      return;
    }
    const search = mode === 'search' ? byId('search').value.trim() : '';
    const id = state.id;
    const epoch = state.epoch;
    const serial = state.resultRequest;
    const controller = new AbortController();
    state.resultController = controller;
    byId('results-region').setAttribute('aria-busy', 'true');
    message('results-status', '특질 후보를 찾는 중…');
    try {
      const data = await request('/api/traits/recommend', {
        personality, selectedIds: d.selected.map(item => item.traitId),
        dismissedIds: Array.from(d.dismissed), search, limit: 5
      }, controller.signal);
      if (id !== state.id || epoch !== state.epoch || serial !== state.resultRequest || state.saving) return;
      if (!Array.isArray(data.items)) throw new Error('Invalid recommendations');
      resultItems = data.items.slice(0, 5);
      if (resultItems.some(item => item.catalogSha256 !== state.catalog.catalogSha256)) {
        throw Object.assign(new Error('Catalog changed'), { status: 409 });
      }
      renderResults();
      message('results-status', !resultItems.length ? '찾은 특질이 없습니다. 다른 단어로 검색하거나 특질 없이 저장해 주세요.' :
        data.matchStatus === 'limited' ? '입력과 가까운 후보가 적어 다른 행동도 함께 보여 드립니다. 어울리는 것만 골라 주세요.' :
          resultItems.length + '개의 후보입니다. 원하는 특질만 추가해 주세요.');
    } catch (error) {
      if (error.name === 'AbortError' || id !== state.id || epoch !== state.epoch || serial !== state.resultRequest) return;
      message('results-status', errorCopy(error, '특질 찾기'), true);
      if (error.status === 409) byId('retry-catalog').hidden = false;
    } finally {
      if (id === state.id && epoch === state.epoch && serial === state.resultRequest) {
        byId('results-region').setAttribute('aria-busy', 'false');
        state.resultController = null;
      }
    }
  }

  function fillFields(d) {
    fieldNames.forEach(name => { byId(name).value = d.fields[name] == null ? '' : d.fields[name]; });
    byId('extra-fields').open = fieldNames.slice(1).some(name => String(d.fields[name] ?? '').trim() !== '');
    byId('search').value = d.search || '';
    renderSelected();
  }

  async function loadSeed(id, discard = false) {
    if (state.saving) return;
    const epoch = ++state.epoch;
    if (state.seedController) state.seedController.abort();
    cancelResults('성격을 적고 추천받거나, 원하는 행동을 검색해 보세요.');
    state.id = id;
    byId('extra-fields').open = false;
    hideSaved();
    byId('retry-seed').hidden = true;
    if (!id) {
      state.loading = false;
      fieldNames.forEach(name => { byId(name).value = ''; });
      renderSelected();
      message('page-status', '설정을 입력할 캐릭터를 선택해 주세요.');
      syncControls();
      return;
    }
    const url = new URL(window.location.href);
    url.searchParams.set('character', id);
    window.history.replaceState(null, '', url);
    state.loading = true;
    if (draft()) fillFields(draft());
    else { fieldNames.forEach(name => { byId(name).value = ''; }); renderSelected(); byId('search').value = ''; }
    message('page-status', '캐릭터 설정을 불러오는 중…');
    syncControls();
    const controller = new AbortController();
    state.seedController = controller;
    try {
      const data = await request('/api/characters/' + encodeURIComponent(id) + '/seed', undefined, controller.signal);
      if (id !== state.id || epoch !== state.epoch) return;
      if (typeof data.editable !== 'boolean') throw new Error('Invalid seed response');
      const seed = data.seed;
      const rev = seed ? seed.seedRev : null;
      let d = draft();
      if (!d || !d.dirty || discard) {
        d = { fields: {}, selected: seed && Array.isArray(seed.selectedTraits) ? seed.selectedTraits.slice() : [],
          rev, dirty: false, dismissed: new Set(), search: '', stale: false };
        fieldNames.forEach(name => { d.fields[name] = seed && seed[name] != null ? seed[name] : ''; });
        drafts.set(id, d);
      } else if (d.rev !== rev) d.stale = true;
      d.editable = data.editable;
      fillFields(d);
      message('page-status', d.stale ? '다른 곳에서 설정이 바뀌었습니다. 입력을 보존했으니 확인한 뒤 설정을 다시 불러와 주세요.' :
        !data.editable ? (data.reason || '작업이 진행 중이어서 지금은 수정할 수 없습니다.') :
          d.dirty ? '이 캐릭터에서 작성하던 입력과 선택을 복원했습니다.' : seed ? '저장된 설정을 불러왔습니다.' : '아직 저장된 설정이 없습니다. 기본 성격부터 적어 주세요.', d.stale);
      if (d.stale || !d.editable) byId('retry-seed').hidden = false;
    } catch (error) {
      if (error.name === 'AbortError' || id !== state.id || epoch !== state.epoch) return;
      if (draft()) draft().editable = false;
      message('page-status', errorCopy(error, '설정 불러오기'), true);
      byId('retry-seed').hidden = false;
    } finally {
      if (id === state.id && epoch === state.epoch) { state.loading = false; syncControls(); }
    }
  }

  async function loadCatalog() {
    if (state.saving || state.catalogLoading) return;
    const serial = ++state.catalogRequest;
    state.catalogLoading = true;
    cancelResults('특질 목록을 불러오는 중…');
    byId('retry-catalog').hidden = true;
    syncControls();
    try {
      const data = await request('/api/traits/catalog');
      if (serial !== state.catalogRequest) return;
      if (!data.catalogSha256 || !Array.isArray(data.items)) throw new Error('Invalid catalog');
      state.catalog = data;
      message('results-status', '성격을 적고 추천받거나, 원하는 행동을 검색해 보세요.');
    } catch (error) {
      state.catalog = null;
      message('results-status', '특질 목록을 불러오지 못했습니다. 입력과 선택은 유지됩니다. 목록을 다시 불러와 주세요.', true);
      byId('retry-catalog').hidden = false;
    } finally {
      state.catalogLoading = false;
      syncControls();
    }
  }

  async function loadProjects() {
    if (state.saving) return;
    byId('retry-projects').hidden = true;
    byId('character').disabled = true;
    try {
      const data = await request('/api/projects');
      if (!Array.isArray(data.characters)) throw new Error('Invalid character list');
      const select = byId('character');
      select.replaceChildren();
      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = data.characters.length ? '캐릭터를 선택해 주세요' : '아직 등록된 캐릭터가 없습니다';
      select.append(placeholder);
      data.characters.forEach(character => {
        const option = document.createElement('option');
        option.value = character.id;
        option.textContent = character.name || character.id;
        select.append(option);
      });
      select.disabled = !data.characters.length;
      const requested = new URLSearchParams(window.location.search).get('character');
      if (requested && data.characters.some(character => character.id === requested)) {
        select.value = requested;
        await loadSeed(requested);
      } else {
        await loadSeed('');
        if (requested) message('page-status', '요청한 캐릭터가 목록에 없습니다. 다른 캐릭터를 선택해 주세요.', true);
        if (!data.characters.length) message('page-status', '등록된 캐릭터가 없습니다. 워크숍에서 캐릭터를 준비한 뒤 목록을 다시 불러와 주세요.');
      }
      byId('retry-projects').hidden = data.characters.length > 0;
    } catch (error) {
      message('page-status', errorCopy(error, '캐릭터 목록 불러오기'), true);
      byId('character').disabled = true;
      byId('retry-projects').hidden = false;
    }
  }

  byId('extra-fields').addEventListener('invalid', () => { byId('extra-fields').open = true; }, true);
  byId('character').addEventListener('change', event => { loadSeed(event.target.value); });
  fieldNames.forEach(name => byId(name).addEventListener('input', () => {
    if (!draft() || state.saving) return;
    draft().fields[name] = byId(name).value;
    changed();
    if (name === 'personality') {
      cancelResults('성격이 바뀌었습니다. 다시 추천받으면 새 입력에 맞는 후보를 찾습니다.');
    }
  }));
  byId('recommend').addEventListener('click', () => { getResults('recommend'); });
  byId('search-button').addEventListener('click', () => { getResults('search'); });
  byId('browse').addEventListener('click', () => {
    byId('search').value = '';
    if (draft()) draft().search = '';
    getResults('browse');
  });
  byId('search').addEventListener('input', () => {
    if (draft()) draft().search = byId('search').value;
    cancelResults('검색어를 입력하는 중…');
    searchTimer = setTimeout(() => { getResults('search'); }, 350);
  });
  byId('search').addEventListener('keydown', event => {
    if (event.key === 'Enter') { event.preventDefault(); getResults('search'); }
  });
  byId('retry-projects').addEventListener('click', loadProjects);
  byId('retry-catalog').addEventListener('click', loadCatalog);
  byId('retry-seed').addEventListener('click', () => {
    if (state.saving) return;
    if (draft() && draft().dirty && !window.confirm('현재 캐릭터의 저장하지 않은 입력과 선택을 버리고, 서버에 저장된 설정을 다시 불러올까요?')) return;
    loadSeed(state.id, true);
  });
  byId('authoring-form').addEventListener('keydown', event => {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && event.target.tagName === 'TEXTAREA') {
      event.preventDefault();
      byId('authoring-form').requestSubmit();
    }
  });
  byId('authoring-form').addEventListener('submit', async event => {
    event.preventDefault();
    const d = draft();
    if (!d || state.loading || state.saving || !d.editable || d.stale ||
      (d.selected.length > 0 && (!state.catalog || state.catalogLoading))) return;
    if (!byId('personality').value.trim()) {
      message('page-status', '기본 성격을 입력해 주세요.', true);
      byId('personality').focus();
      return;
    }
    const fields = {};
    fieldNames.forEach(name => { fields[name] = byId(name).value.trim(); });
    fields.age = fields.age === '' ? null : Number(fields.age);
    fields.gender = fields.gender || null;
    if (fields.age !== null && (!Number.isInteger(fields.age) || fields.age < 18)) {
      message('page-status', '나이는 18세 이상의 정수로 입력하거나 비워 주세요.', true);
      byId('extra-fields').open = true;
      byId('age').focus();
      return;
    }
    if (d.selected.some(item => item.catalogSha256 !== state.catalog.catalogSha256)) {
      message('page-status', '특질 목록이 바뀌었습니다. 현재 선택을 확인하고, 제거한 뒤 다시 찾아 추가해 주세요. 입력 내용은 유지됩니다.', true);
      return;
    }
    const id = state.id;
    const epoch = state.epoch;
    const payload = { fields, selectedIds: d.selected.map(item => item.traitId),
      expectedSeedRev: d.rev, catalogSha256: d.selected.length > 0 ? state.catalog.catalogSha256 : null };
    state.saving = true;
    cancelResults('설정을 저장하는 중…');
    hideSaved();
    message('page-status', '설정을 저장하는 중…');
    syncControls();
    try {
      const data = await request('/api/characters/' + encodeURIComponent(id) + '/seed', payload);
      if (id !== state.id || epoch !== state.epoch) return;
      if (!data.seed || !/^sd\d+$/.test(data.seed.seedRev) || data.seed.characterId !== id) throw new Error('Invalid saved seed');
      d.rev = data.seed.seedRev;
      d.fields = fields;
      d.dirty = false;
      fillFields(d);
      message('page-status', '캐릭터 설정을 저장했습니다.');
      message('results-status', '저장했습니다. 성격에 맞는 다른 특질도 찾아볼 수 있습니다.');
      byId('results-region').setAttribute('aria-busy', 'false');
      message('saved-message', '설정 ' + d.rev.replace(/^sd/, '') + '차 저장이 완료되었습니다. 유료 생성은 시작하지 않았습니다.');
      byId('save-result').hidden = false;
      if (typeof data.nextUrl === 'string' && data.nextUrl) {
        try {
          const next = new URL(data.nextUrl, window.location.href);
          if (next.origin === window.location.origin && ['http:', 'https:'].includes(next.protocol)) {
            byId('next-link').href = next.href;
            byId('next-link').hidden = false;
          }
        } catch (_) {
          // A malformed navigation link must not turn a successful save into an error.
        }
      }
    } catch (error) {
      if (id !== state.id || epoch !== state.epoch) return;
      message('page-status', errorCopy(error, '설정 저장'), true);
      if ([403, 404, 409].includes(error.status)) {
        d.stale = true;
        byId('retry-seed').hidden = false;
        byId('retry-catalog').hidden = false;
      }
    } finally {
      state.saving = false;
      syncControls();
    }
  });
  window.addEventListener('beforeunload', event => {
    if (state.saving || Array.from(drafts.values()).some(value => value.dirty)) {
      event.preventDefault();
      event.returnValue = '';
    }
  });
  loadProjects();
  loadCatalog();
})();
