// Saves study progress in this browser (localStorage) so a learner can come back later.
//
// What is saved per transcript: the analysis, the transcript text, every quiz answer, and the Q&A thread.
// The tutor's plan and an unfinished quiz are not saved; the plan is recomputed from the answers on demand.
// Nothing leaves the browser. Progress does not follow the learner to another browser or device.
import { state, on, emit } from './state.js';

const STORAGE_KEY = 'learnlens.v1';
const VERSION = 1;
const MAX_SESSIONS = 5;

// Small, stable fingerprint of the pasted transcript. Same text, same key.
export function hashText(text) {
  let a = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    a ^= text.charCodeAt(i);
    a = Math.imul(a, 0x01000193) >>> 0;
  }
  return `${a.toString(16)}-${text.length}`;
}

const isObj = v => v && typeof v === 'object' && !Array.isArray(v);

// Anything stored by an older or broken version is dropped rather than risking a half-working page.
function valid(e) {
  const r = e?.result;
  return isObj(e) && typeof e.key === 'string' && typeof e.transcript === 'string'
    && isObj(r) && Array.isArray(r.segments) && Array.isArray(r.concepts)
    && isObj(r.graph) && Array.isArray(r.graph.study_order) && Array.isArray(r.graph.edges)
    && isObj(r.stats) && Array.isArray(r.key_takeaways) && Array.isArray(r.learning_objectives)
    && isObj(e.scores) && Array.isArray(e.attempts) && Array.isArray(e.thread);
}

function read() {
  try {
    const data = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
    if (!isObj(data) || data.v !== VERSION || !Array.isArray(data.sessions)) return [];
    return data.sessions.filter(valid);
  } catch {
    return [];
  }
}

// Returns true when saved. If the browser is full, the oldest transcripts are dropped until it fits.
function write(sessions) {
  let list = sessions.slice(0, MAX_SESSIONS);
  if (list.length === 0) {
    try { localStorage.removeItem(STORAGE_KEY); return true; } catch { return false; }
  }
  while (list.length > 0) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ v: VERSION, sessions: list }));
      return true;
    } catch {
      list = list.slice(0, -1);
    }
  }
  try { localStorage.removeItem(STORAGE_KEY); } catch { /* storage is unavailable */ }
  return false;
}

export const listSessions = () => read();
export const findSession = key => read().find(s => s.key === key) || null;

export function deleteSession(key) {
  write(read().filter(s => s.key !== key));
}

function save() {
  if (!state.result || !state.key) return;
  const entry = {
    key: state.key,
    savedAt: Date.now(),
    title: state.result.title,
    transcript: state.transcript,
    result: state.result,
    scores: state.scores,
    attempts: state.attempts,
    // Only finished answers. A question still waiting on the server cannot be restored.
    thread: state.thread.filter(t => t.status === 'done' && t.result),
  };
  const ok = write([entry, ...read().filter(s => s.key !== entry.key)]);
  emit('save-status', ok);
}

export function initStore() {
  on('session', save);
  on('scores', save);
  on('asked', save);
}
