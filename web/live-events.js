export class LiveHTTPError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

export async function readSSE(response, onEvent, signal) {
  if (!response.ok) {
    let detail;
    try { detail = (await response.json()).detail; } catch {}
    throw new LiveHTTPError(response.status,
      typeof detail === 'string' ? detail.slice(0, 300) : '실시간 연결을 확인하지 못했습니다.');
  }
  if (!response.body) throw new Error('실시간 응답 본문이 없습니다.');
  const reader = response.body.getReader(), decoder = new TextDecoder();
  let pending = '';
  try {
    while (!signal?.aborted) {
      const { value, done } = await reader.read();
      if (signal?.aborted) return;
      pending += decoder.decode(value, { stream: !done });
      if (pending.length > 6 * 1024 * 1024) throw new Error('실시간 이벤트 크기 제한을 초과했습니다.');
      pending = pending.replace(/\r\n/g, '\n');
      let i;
      while ((i = pending.indexOf('\n\n')) >= 0) {
        const block = pending.slice(0, i); pending = pending.slice(i + 2);
        const lines = block.split('\n');
        const data = lines.filter(s => s.startsWith('data:')).map(s => s.slice(5).trimStart()).join('\n');
        if (data && !signal?.aborted) onEvent({
          type: lines.find(s => s.startsWith('event:'))?.slice(6).trim() || 'message',
          data: JSON.parse(data),
        });
      }
      if (done) return;
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export function connectLive(getToken, onEvent, onStatus, options = {}) {
  const page = options.document || document;
  const request = options.fetch || fetch;
  const setTimer = options.setTimeout || setTimeout;
  const clearTimer = options.clearTimeout || clearTimeout;
  let stopped = false, controller = null, timer = null, delay = 1000, generation = 0;
  const current = serial => !stopped && serial === generation;

  function cancel() {
    generation++;
    if (timer !== null) clearTimer(timer);
    timer = null;
    controller?.abort(); controller = null;
  }
  function stop() {
    if (stopped) return;
    stopped = true; cancel(); page.removeEventListener('visibilitychange', visibility);
  }
  async function open() {
    if (stopped || page.hidden || !getToken() || controller) return;
    const serial = ++generation, active = new AbortController(); controller = active;
    onStatus('실시간 연결 중');
    try {
      const response = await request('/api/ops/events', {
        headers: { Authorization: 'Bearer ' + getToken() }, signal: active.signal, cache: 'no-store',
      });
      if (!current(serial) || active.signal.aborted) return;
      await readSSE(response, event => {
        if (!current(serial) || active.signal.aborted) return;
        delay = 1000; onStatus('실시간 연결됨'); onEvent(event);
      }, active.signal);
      if (current(serial) && !active.signal.aborted) onStatus('연결 종료 · 재연결 대기');
    } catch (error) {
      if (!current(serial) || error.name === 'AbortError') return;
      if ([401, 403].includes(error.status)) {
        stop();
        onStatus('운영 인증이 만료되거나 변경되었습니다. 토큰을 다시 입력하세요.');
        options.onUnauthorized?.();
      } else onStatus('실시간 연결을 확인하지 못했습니다. 재연결을 기다립니다.');
    } finally {
      if (serial === generation) controller = null;
      if (current(serial) && !page.hidden && getToken()) {
        timer = setTimer(() => { timer = null; open(); }, delay);
        delay = Math.min(delay * 2, 15000);
      }
    }
  }
  function visibility() {
    if (page.hidden) cancel();
    else open();
  }
  page.addEventListener('visibilitychange', visibility); open();
  return stop;
}
