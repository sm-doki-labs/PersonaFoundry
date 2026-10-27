(function STATUS() {
  // 상태 표: 두 화면이 쓰는 상태의 이름과 색을 여기에서만 정한다.
  // [이름, 색 단계]. 색 단계는 glass.css의 .pill.t-* 과 짝이다. 화면 코드는 상태 글자를 직접 쓰지 않고 이 표를 부른다.
  const TABLE = {
    // 작업 요청 하나(신규 생성, 영상 증보 같은 묶음)의 상태
    job: {
      notstarted: ['시작 전', 'muted'], running: ['실행 중', 'active'], paused: ['일시정지', 'muted'],
      gate: ['결재 대기', 'warn'], human: ['사람 필요', 'alert'], done: ['완료', 'ok'],
      cancelled: ['취소됨', 'muted'], queued: ['대기열', 'muted'], next: ['다음 단계 대기', 'muted']
    },
    // 팀과 작업 하나의 상태
    task: {
      working: ['작업 중', 'active'], paused: ['일시정지', 'muted'], gate: ['결재 대기', 'warn'], budget: ['예산 대기', 'warn'],
      retry: ['재시도 중', 'bad'], human: ['사람 필요', 'alert'], done: ['완료', 'ok'], idle: ['대기', 'muted'], cancelled: ['취소됨', 'muted']
    },
    // 작업 안의 시도 한 번
    attempt: { ok: ['성공', 'ok'], fail: ['실패', 'bad'], running: ['진행 중', 'active'], stopped: ['중단', 'muted'] },
    // 관문 결재
    gate: { pending: ['결재 대기', 'warn'], approved: ['결재됨', 'ok'] },
    // 캐릭터 자산 한 종류
    asset: {
      approved: ['승인', 'ok'], pending: ['결재 대기', 'warn'], running: ['만드는 중', 'active'],
      human: ['사람 필요', 'alert'], queued: ['대기열', 'muted'], none: ['아직 없음', 'muted']
    },
    // 캐릭터 단계
    life: { planning: ['기획 중', 'muted'], making: ['제작 중', 'active'], ready: ['출시 준비', 'ok-strong'], released: ['출시됨', 'ok'] }
  };
  const get = (g, k) => {
    const v = TABLE[g] && TABLE[g][k];
    if (!v) throw new Error(`상태 표에 없는 상태: ${g}.${k}`);
    return v;
  };
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  const label = (g, k) => get(g, k)[0];
  const tone = (g, k) => get(g, k)[1];
  // size: 'sm'이면 좁은 칸용 작은 상태 칩
  const cls = (g, k, size) => `pill t-${tone(g, k)} s-${k}${size === 'sm' ? ' pill--sm' : ''}`;
  // text를 주면 표의 이름 대신 쓴다(예: "결재 대기 2", "진행 42%"). 색은 언제나 표를 따른다.
  const pill = (g, k, text, size) => `<span class="${cls(g, k, size)}"><span class="dot"></span><span>${esc(text == null ? label(g, k) : text)}</span></span>`;
  window.FACTORY_STATUS = { table: TABLE, label, tone, cls, pill };
})();

