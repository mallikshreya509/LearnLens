// Every call to the backend goes through here.
const base = () => (window.LEARNLENS_API || '').replace(/\/$/, '');
const TIMEOUT_MS = 150_000;
const YOUTUBE_TIMEOUT_MS = 270_000;   // Gemini listening to a long video is slow. The server stops at 240 s, Cloud Run at 300 s.

function detail(data, status) {
  const d = data && data.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d.length) {
    return d.map(e => {
      const field = (e.loc || []).filter(x => x !== 'body').join('.');
      return field ? `${field}: ${e.msg}` : e.msg;
    }).join('; ');
  }
  return `The server returned an error (${status}).`;
}

async function request(path, body, timeoutMs = TIMEOUT_MS) {
  const init = { signal: AbortSignal.timeout(timeoutMs) };
  if (body !== undefined) {
    init.method = 'POST';
    init.headers = { 'Content-Type': 'application/json' };
    init.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(base() + path, init);
  } catch (e) {
    if (e && e.name === 'TimeoutError') {
      throw new Error('The request took too long. Try again, or paste the transcript instead.');
    }
    throw new Error(`Could not reach the backend${base() ? ' at ' + base() : ''}. Check that it is running.`);
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(detail(data, res.status));
  return data;
}

export const api = {
  health: () => request('/api/health'),
  sample: () => request('/api/sample'),
  youtube: url => request('/api/youtube', { url }, YOUTUBE_TIMEOUT_MS),
  analyze: (transcript, title) => request('/api/analyze', { transcript, title: title || null }),
  ask: (question, segments, history) => request('/api/ask', { question, segments, history }),
  quiz: (segments, concepts, count, focus) =>
    request('/api/quiz', { segments, concepts, count, focus }),
  tutor: payload => request('/api/tutor/next', payload),
};
