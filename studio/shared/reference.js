(function (global) {
  'use strict';
  const text = (v) => v == null ? '' : String(v);
  const E = (v) => text(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const PARALLEL_COPY = '원문 분석·프롬프트 준비와 9:16 기준 사진 생성을 병렬로 진행해요. 이미지를 직접 확인하고 승인하면 준비가 끝나는 대로 영상 6편(대기 1편·동작 4편·시그니처 1편)을 만들어요. 자동 진행·시연 모드에서도 이미지 승인은 생략하지 않아요.';
  function imageUrl(value) {
    const s = text(value).trim();
    if (!s || /[\u0000-\u0020\\]/.test(s)) return '';
    if (/^\/(?!\/)/.test(s)) return s;
    try { const u = new URL(s); return ['http:', 'https:'].includes(u.protocol) && !u.username && !u.password ? s : ''; } catch (_) { return ''; }
  }
  function canConfirm(r) {
    // A generated signature seed is approved together with the master photo, so both must be visible.
    return !!(r && r.enabled && r.status === 'awaiting_confirmation' && r.revision && r.sha256 && imageUrl(r.imageUrl) && (!r.signatureSha256 || imageUrl(r.signatureImageUrl)));
  }
  function keyOf(r) {
    if (!r) return '';
    const base = [r.revision, r.sha256, imageUrl(r.imageUrl)].join('|');
    return r.signatureSha256 ? base + '|' + [r.signatureSha256, imageUrl(r.signatureImageUrl)].join('|') : base;
  }
  function confirmBody(r) {
    const body = { revision: r.revision, sha256: r.sha256 };
    if (r.signatureSha256) body.signatureSha256 = r.signatureSha256;
    return body;
  }
  function canRetry(r) {
    return !!(r && r.enabled && ['not_started', 'awaiting_confirmation', 'failed'].includes(r.status) && !r.activeJobId);
  }
  function canResumeVideo(r) {
    return !!(r && r.enabled && r.status === 'approved' && ['none', 'failed'].includes(r.videoStatus) && !r.activeJobId && r.revision && r.sha256);
  }
  function statusCopy(r) {
    if (!r) return '기준 사진 상태를 불러오는 중이에요.';
    if (r.status === 'approved') {
      if (r.videoStatus === 'ready') return '기준 사진을 승인했고 영상 제작이 완료됐어요. 영상 품질은 결과를 직접 확인해 주세요.';
      if (r.videoStatus === 'failed') return '기준 사진은 승인됐지만 영상 제작에 실패했어요. 진행 화면에서 실패한 단계를 확인하고, 진행 중인 작업이 없으면 아래 버튼으로 다시 시도할 수 있어요.';
      if (r.videoStatus === 'making') return '승인한 기준 사진으로 영상 6편을 만들고 있어요.';
      if (canResumeVideo(r)) return '기준 사진은 승인됐어요. 영상 제작이 아직 시작되지 않았다면 아래 버튼으로 이어서 시작할 수 있어요.';
      return '기준 사진 승인이 접수됐어요. 필요한 작업이 끝나면 영상 6편을 자동으로 만들어요.';
    }
    if (r.status === 'awaiting_confirmation' && r.signatureSha256) return '기준 사진의 얼굴·복장·배경과, 같은 장면에 시그니처 동작만 입힌 중간 프레임을 함께 확인해 주세요. 직접 승인하기 전에는 영상을 만들지 않아요.';
    return ({ not_started: '기준 사진 생성을 기다리고 있어요. 프롬프트 준비는 별도로 진행해요.', generating: '9:16 기준 사진을 만들고 있어요. 시그니처 참고 사진을 올렸다면 중간 프레임도 이어서 만들어요. 프롬프트 준비도 함께 진행해요.', awaiting_confirmation: '얼굴·복장·배경을 확인해 주세요. 직접 승인하기 전에는 영상을 만들지 않아요.', failed: '기준 사진을 만들지 못했어요. 아래 내용을 확인하고 다시 만들어 주세요.' })[r.status] || '기준 사진 상태를 확인하고 있어요.';
  }
  function cardHTML(s) {
    const r = s.reference;
    if (r && r.enabled === false) return '';
    const editable = canRetry(r);
    const url = r && imageUrl(r.imageUrl);
    const sigUrl = r && r.signatureSha256 ? imageUrl(r.signatureImageUrl) : '';
    const key = keyOf(r);
    const validImage = !!url && (!r.signatureSha256 || !!sigUrl) && s.loadedKey === key;
    const disabled = !!(s.busy || s.readError);
    const field = (name, label, value) => '<label for="ref-' + name + '">' + label + ' <span>선택</span></label><textarea id="ref-' + name + '" data-ref-field="' + name + '" rows="2"' + (disabled ? ' disabled' : '') + '>' + E(value) + '</textarea>';
    const img = (src, alt) => '<img data-ref-image data-ref-key="' + E(key) + '" src="' + E(src) + '" alt="' + alt + '">';
    const previews = sigUrl
      ? '<div class="ref-previews"><figure class="ref-shot"><div class="ref-preview">' + img(url, '영상 시작과 끝에 쓰는 9:16 기준 사진') + '</div><figcaption>기준 사진 · 시작과 끝</figcaption></figure>' +
        '<figure class="ref-shot"><div class="ref-preview">' + img(sigUrl, '기준 사진에 시그니처 동작을 입힌 중간 프레임') + '</div><figcaption>시그니처 중간 프레임</figcaption></figure></div>'
      : '<div class="ref-preview">' + (url ? img(url, '영상 제작에 사용할 9:16 기준 사진') : '<span>9:16<br>기준 사진 미리보기</span>') + '</div>';
    return '<section class="ref-card' + (sigUrl ? ' has-signature' : '') + '" aria-labelledby="ref-title" aria-busy="' + !!s.busy + '">' +
      previews +
      '<div class="ref-content"><h2 id="ref-title">영상 제작 전 이미지 확인</h2><p data-ref-status role="status">' + E(statusCopy(r)) + '</p><p class="ref-muted">' + E(PARALLEL_COPY) + '</p>' +
      (r && r.validationStatus === 'unverified' ? '<p class="ref-warning">' + (sigUrl ? '두 이미지가 같은 사람·복장·배경인지, 중간 프레임의 손 모양이 동작과 맞는지 직접 확인해 주세요.' : '얼굴·복장·배경·구도를 직접 확인해 주세요.') + ' 생성 완료는 품질 검증 완료를 뜻하지 않아요.</p>' : '') +
      (r && r.error ? '<p class="ref-error">' + E(r.error) + '</p>' : '') +
      (s.error ? '<p class="ref-error" role="alert">' + E(s.error) + '</p>' : '') +
      (s.notice ? '<p role="status">' + E(s.notice) + '</p>' : '') +
      (s.imageFailed ? '<p class="ref-error">이미지를 불러오지 못했어요. 상태를 새로고침한 뒤 다시 확인해 주세요.</p>' : '') +
      (editable ? '<div class="ref-fields">' + field('wardrobe', '복장', s.edits.wardrobe) + field('background', '배경', s.edits.background) + '<p class="ref-muted">비워 두면 업로드한 사진의 옷과 배경을 유지해요. 바꾼 내용은 다시 만들기를 눌러야 반영돼요.</p></div>' : '') +
      '<div class="ref-actions">' +
      (canConfirm(r) ? '<button type="button" class="btn pri" data-ref-act="confirm"' + (disabled || !validImage ? ' disabled' : '') + '>' + (sigUrl ? '두 이미지로 승인 · 영상 6편 만들기' : '이 이미지로 승인 · 영상 6편 만들기') + '</button>' : '') +
      (canResumeVideo(r) ? '<button type="button" class="btn pri" data-ref-act="resume-video"' + (disabled ? ' disabled' : '') + '>' + (r.videoStatus === 'failed' ? '영상 6편 생성 다시 시도' : '영상 6편 생성 이어서 하기') + '</button>' : '') +
      (editable ? '<button type="button" class="btn" data-ref-act="retry"' + (disabled ? ' disabled' : '') + '>' + (sigUrl ? '두 이미지 다시 만들기' : '기준 사진 다시 만들기') + '</button>' : '') +
      '<button type="button" class="btn ghost" data-ref-act="refresh"' + (s.busy ? ' disabled' : '') + '>상태 새로고침</button></div>' +
      (canResumeVideo(r) ? '<p class="ref-muted">승인한 기준 사진을 그대로 사용해요. 이어서 생성하거나 다시 시도하는 영상에는 모델 사용 비용이 들어요.</p>' : '') +
      (r && r.status === 'awaiting_confirmation' && !validImage ? '<p class="ref-muted">' + (sigUrl ? '두 이미지가 모두 표시된 뒤 승인할 수 있어요.' : '이미지가 표시된 뒤 승인할 수 있어요.') + '</p>' : '') +
      '</div></section>';
  }

  // This controller owns reference requests only. It never starts a persona/video job directly.
  function createController(options) {
    const o = options || {};
    const state = { cid: null, reference: null, busy: false, readError: false, error: '', notice: '', edits: { wardrobe: '', background: '' }, loadedKey: '', imageFailed: false };
    let epoch = 0, seq = 0, reading = false, disposed = false;
    const emit = () => { if (!disposed && o.onChange) o.onChange(state); };
    async function request(method, suffix, body, cid) {
      const res = await o.fetch(text(o.apiBase).replace(/\/$/, '') + '/api/sources/' + encodeURIComponent(cid) + '/reference' + suffix, { method, cache: 'no-store', headers: body ? { 'Content-Type': 'application/json' } : undefined, body: body ? JSON.stringify(body) : undefined });
      const data = await res.json();
      if (!res.ok) throw Object.assign(new Error(typeof data.detail === 'string' ? data.detail : '요청을 처리하지 못했어요.'), { status: res.status });
      return data;
    }
    async function refresh() {
      if (!state.cid || reading || disposed || state.busy) return;
      const cid = state.cid, version = epoch, token = ++seq;
      reading = true;
      try {
        const r = await request('GET', '', null, cid);
        if (disposed || version !== epoch || token !== seq) return;
        const prev = state.reference;
        if (!prev || prev.revision !== r.revision) state.edits = { wardrobe: text(r.wardrobe), background: text(r.background) };
        state.reference = r;
        state.readError = false;
        if (!state.actionError) state.error = '';
        if (r.status === 'approved' && ['making', 'ready', 'failed'].includes(r.videoStatus)) state.notice = '';
      } catch (err) {
        if (disposed || version !== epoch || token !== seq) return;
        if ([404, 405].includes(err.status) && !o.expected) state.reference = { enabled: false };
        else { state.readError = true; state.error = '기준 사진 상태를 읽지 못했어요. 연결을 확인하고 새로고침해 주세요.'; }
      } finally { if (version === epoch) { reading = false; emit(); } }
    }
    function setCharacter(cid) {
      if (disposed || cid === state.cid) return;
      epoch++; seq++; reading = false;
      Object.assign(state, { cid, reference: null, busy: false, readError: false, actionError: false, error: '', notice: '', loadedKey: '', imageFailed: false, edits: { wardrobe: '', background: '' } });
      emit();
      if (cid) return refresh();
    }
    async function act(action) {
      const r = state.reference;
      const key = keyOf(r);
      if (state.busy || state.readError || !state.cid || disposed) return false;
      if (action === 'confirm' ? !canConfirm(r) || state.loadedKey !== key : action === 'resume-video' ? !canResumeVideo(r) : action !== 'retry' || !canRetry(r)) return false;
      const confirming = action === 'confirm' || action === 'resume-video';
      const body = confirming ? confirmBody(r) : { revision: r.revision, wardrobe: state.edits.wardrobe.trim(), background: state.edits.background.trim() };
      const version = epoch, cid = state.cid;
      seq++; state.busy = true; state.error = ''; state.notice = ''; state.actionError = false; emit();
      let ok = false;
      try {
        const result = await request('POST', confirming ? '/confirm' : '/retry', body, cid);
        if (version !== epoch || disposed) return false;
        ok = true;
        if (confirming) {
          state.reference = Object.assign({}, r, { status: 'approved' });
          state.notice = action === 'resume-video' ? '영상 생성 이어하기 요청을 처리했어요. 현재 제작 상태를 확인해 주세요.' : '기준 사진 승인이 접수됐어요.';
          if (result.queued) state.notice = (action === 'resume-video' ? '영상 생성 요청이' : '승인이') + ' 접수됐어요. 진행 중인 작업과 필요한 준비가 끝나면 서버가 영상 제작을 이어서 시작해요.';
        } else {
          state.reference = Object.assign({}, r, { status: 'generating', activeJobId: result.jobId, imageUrl: null, signatureImageUrl: null, signatureSha256: null });
          state.loadedKey = ''; state.notice = '새 기준 사진을 요청했어요. 새 이미지도 직접 확인하고 승인해 주세요.';
        }
      } catch (err) {
        if (version !== epoch || disposed) return false;
        state.error = err.status === 409 ? '이미지가 바뀌었거나 작업이 진행 중이에요. 최신 상태를 다시 읽었어요. 이미지를 확인한 뒤 다시 시도해 주세요.' : '요청을 완료하지 못했어요. 상태를 확인하고 다시 시도해 주세요.';
        // Keep action failures visible after the following GET.
        state.actionError = true;
      } finally {
        if (version === epoch && !disposed) { state.busy = false; emit(); await refresh(); }
      }
      return ok;
    }
    return { state, refresh, setCharacter, act, edit(name, value) { if (['wardrobe', 'background'].includes(name)) state.edits[name] = text(value); }, imageLoaded(key, success) { state.loadedKey = success ? key : ''; state.imageFailed = !success; emit(); }, destroy() { disposed = true; epoch++; } };
  }

  function mount(options) {
    const o = options || {}, host = o.host;
    if (!host) return { setCharacter() {}, destroy() {} };
    const doc = host.ownerDocument;
    let rendered = '';
    const controller = createController(Object.assign({}, o, { fetch: o.fetch || global.fetch.bind(global), onChange: render }));
    function render(s) {
      host.hidden = !s.cid || !!(s.reference && s.reference.enabled === false);
      if (host.hidden) { host.innerHTML = ''; rendered = ''; if (o.onChange) o.onChange(s); return; }
      if (o.onChange) o.onChange(s);
      const html = cardHTML(s);
      if (html === rendered) return;
      const focused = host.contains(doc.activeElement) ? doc.activeElement : null;
      const field = focused && focused.dataset.refField, action = focused && focused.dataset.refAct;
      const caret = field ? [focused.selectionStart, focused.selectionEnd] : null;
      rendered = html; host.innerHTML = html;
      // Approval waits until every shown image (master, and the signature seed if any) has decoded.
      const imgs = Array.from(host.querySelectorAll('[data-ref-image]'));
      if (imgs.length) {
        const key = imgs[0].dataset.refKey;
        const loaded = () => {
          if (!imgs.every((img) => host.contains(img) && img.complete && img.naturalWidth)) return;
          if (controller.state.loadedKey !== key || controller.state.imageFailed) controller.imageLoaded(key, true);
        };
        imgs.forEach((img) => {
          img.onload = loaded;
          img.onerror = () => { if (host.contains(img) && !controller.state.imageFailed) controller.imageLoaded(key, false); };
        });
        loaded();
      }
      const next = field ? host.querySelector('[data-ref-field="' + field + '"]') : action ? host.querySelector('[data-ref-act="' + action + '"]') : null;
      if (next) { next.focus({ preventScroll: true }); if (caret) next.setSelectionRange(...caret); }
    }
    const click = (e) => {
      const el = e.target.closest('[data-ref-act]');
      if (!el || el.disabled) return;
      if (el.dataset.refAct === 'refresh') { controller.state.imageFailed = false; controller.state.loadedKey = ''; rendered = ''; controller.refresh(); }
      else controller.act(el.dataset.refAct);
    };
    const input = (e) => { if (e.target.dataset.refField) controller.edit(e.target.dataset.refField, e.target.value); };
    host.addEventListener('click', click); host.addEventListener('input', input);
    const timer = global.setInterval(() => { if (!doc.hidden) controller.refresh(); }, 4000);
    return { controller, setCharacter: controller.setCharacter, destroy() { global.clearInterval(timer); controller.destroy(); host.removeEventListener('click', click); host.removeEventListener('input', input); } };
  }
  const api = { PARALLEL_COPY, imageUrl, keyOf, confirmBody, canConfirm, canRetry, canResumeVideo, statusCopy, cardHTML, createController, mount };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (global) global.ReferencePreview = api;
})(typeof window !== 'undefined' ? window : null);
