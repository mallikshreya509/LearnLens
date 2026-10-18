// Shared session state plus a tiny event bus so tabs can talk to each other without importing each other.
//
// Events:
//   session        a new analysis is ready, or a saved one was resumed (state has been set)
//   save-status    detail = true when progress was saved in this browser, false when it could not be
//   scores         a quiz answer was recorded
//   asked          the learner asked a question in the Ask tab
//   showtab        detail = tab name
//   ask-question   detail = question text (switches to Ask and sends it)
//   quiz-concept   detail = concept name (switches to Quiz with that concept preselected)
//   quiz-start     detail = { focus: [concept names], count } (switches to Quiz and starts it)
//   tutor-plan     asks the tutor for the next step (switches to the Tutor tab)
export const state = {
  key: null,      // fingerprint of the pasted transcript; progress is saved under it (see store.js)
  transcript: '', // the pasted transcript text, kept so "Edit transcript" works after a resume
  result: null,   // the /api/analyze response
  thread: [],     // Q&A items for the Ask tab
  scores: {},     // concept id -> { correct, total } from quizzes (drives the map colours)
  attempts: [],   // every quiz answer, oldest first: { concept (name), correct, question }
};

const bus = new EventTarget();
export const on = (name, fn) => bus.addEventListener(name, e => fn(e.detail));
export const emit = (name, detail) => bus.dispatchEvent(new CustomEvent(name, { detail }));

// `saved` carries a transcript's key and text, and when resuming also the thread, scores and attempts.
export function startSession(result, saved = {}) {
  state.key = saved.key ?? null;
  state.transcript = saved.transcript ?? '';
  state.result = result;
  state.thread = saved.thread ?? [];
  state.scores = saved.scores ?? {};
  state.attempts = saved.attempts ?? [];
  emit('session', result);
}

export const conceptById = id => state.result?.concepts.find(c => c.id === id);

export function conceptByName(name) {
  const key = (name || '').trim().toLowerCase();
  return state.result?.concepts.find(c => c.name.toLowerCase() === key);
}

export function recordScore(concept, correct, question = '') {
  const s = (state.scores[concept.id] ||= { correct: 0, total: 0 });
  s.total += 1;
  if (correct) s.correct += 1;
  state.attempts.push({ concept: concept.name, correct, question: question.slice(0, 600) });
  emit('scores');
}
