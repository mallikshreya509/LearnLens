// Quiz tab: questions are written from the transcript, each with the line that proves the answer.
// Results are recorded per concept (state.scores) so the map can show what needs review.
import { $, h, evidenceItem } from './dom.js';
import { api } from './api.js';
import { state, on, emit, conceptByName, recordScore } from './state.js';
import { focusSegment } from './reader.js';

const LETTERS = 'ABCDE';
let phase = 'setup';            // setup | loading | running | done
let quiz = null;                // { questions, dropped, index, answers: [{ choice, correct }] }
let settings = { count: 5, focus: '' };
let error = '';

export function initQuiz() {
  on('session', () => { phase = 'setup'; quiz = null; settings = { count: 5, focus: '' }; error = ''; render(); });
  on('quiz-concept', name => {
    settings.focus = name;
    phase = 'setup';
    error = '';
    render();
    emit('showtab', 'quiz');
  });
  // The tutor starts a quiz for the learner: focus on the concepts it chose, no setup screen.
  on('quiz-start', ({ focus, count }) => {
    settings.count = count;
    settings.focus = focus.length === 1 ? focus[0] : '';
    emit('showtab', 'quiz');
    start(focus);
  });
}

async function start(focusNames) {
  const session = state.result;
  phase = 'loading';
  error = '';
  render();
  try {
    const data = await api.quiz(
      session.segments,
      session.concepts.map(c => ({ name: c.name, definition: c.definition })),
      settings.count,
      focusNames,
    );
    if (state.result !== session) return;
    quiz = { questions: data.questions, dropped: data.dropped, index: 0, answers: [] };
    phase = 'running';
  } catch (e) {
    if (state.result !== session) return;
    error = e.message;
    phase = 'setup';
  }
  render();
}

function choose(i) {
  const q = quiz.questions[quiz.index];
  if (quiz.answers[quiz.index]) return;
  const correct = i === q.correct_index;
  quiz.answers[quiz.index] = { choice: i, correct };
  const concept = conceptByName(q.concept);
  if (concept) recordScore(concept, correct, q.question);
  render();
  $('#quiz-feedback')?.focus();
}

function next() {
  if (quiz.index + 1 < quiz.questions.length) quiz.index += 1;
  else phase = 'done';
  render();
}

function render() {
  const root = $('#panel-quiz');
  if (!state.result) return;
  const view = { setup: setupView, loading: loadingView, running: runningView, done: doneView }[phase]();
  root.replaceChildren(view);
}

function setupView() {
  const count = h('select', { id: 'quiz-count', onchange: e => { settings.count = Number(e.target.value); } },
    [...new Set([2, 3, 5, 8, settings.count])].sort((a, b) => a - b)
      .map(n => h('option', { value: n, text: `${n} questions` })));
  count.value = String(settings.count);

  const focus = h('select', { id: 'quiz-focus', onchange: e => { settings.focus = e.target.value; } },
    h('option', { value: '', text: 'Spread across all concepts' }),
    state.result.concepts.map(c => h('option', { value: c.name, text: c.name })));
  focus.value = settings.focus;

  return h('div', { class: 'quiz-setup' },
    h('p', { class: 'hint',
      text: 'Questions are written from the transcript. After each answer you see why it is right and the line in the video that shows it.' }),
    h('div', { class: 'field' }, h('label', { for: 'quiz-count', text: 'Length' }), count),
    h('div', { class: 'field' }, h('label', { for: 'quiz-focus', text: 'Topic' }), focus),
    error && h('div', { class: 'error', role: 'alert', text: error }),
    h('div', { class: 'row' },
      h('button', { class: 'primary', type: 'button', text: 'Start quiz',
        onclick: () => start(settings.focus ? [settings.focus] : []) })));
}

function loadingView() {
  return h('p', { class: 'busy', role: 'status', text: 'Writing questions from the transcript…' });
}

function runningView() {
  const q = quiz.questions[quiz.index];
  const a = quiz.answers[quiz.index];
  const total = quiz.questions.length;

  const options = q.options.map((text, i) => {
    let cls = 'opt', tag = null;
    if (a) {
      if (i === q.correct_index) {
        cls += ' right';
        tag = a.choice === i ? 'Your answer, correct' : 'Correct answer';
      } else if (i === a.choice) {
        cls += ' wrong';
        tag = 'Your answer';
      }
    }
    return h('li', {},
      h('button', { class: cls, type: 'button', disabled: !!a, onclick: () => choose(i) },
        h('span', { class: 'letter', text: LETTERS[i] }),
        h('span', { text }),
        tag && h('span', { class: 'opt-tag', text: tag })));
  });

  const canOpen = q.evidence && q.evidence.match !== 'unverified' && q.evidence.segment_id != null;
  const feedback = a && h('div', { class: `feedback${a.correct ? '' : ' bad'}`, id: 'quiz-feedback', tabindex: -1, role: 'status' },
    h('p', { class: 'verdict', text: a.correct ? 'Correct.' : 'Not quite.' }),
    h('p', { text: q.explanation }),
    canOpen && h('ul', { class: 'evidence' }, evidenceItem(q.evidence, focusSegment)),
    h('div', { class: 'row' },
      h('button', { class: 'primary', type: 'button',
        text: quiz.index + 1 < total ? 'Next question' : 'See results', onclick: next })));

  return h('div', { class: 'quiz-run' },
    h('div', { class: 'progress' },
      h('span', { text: `Question ${quiz.index + 1} of ${total}` }),
      h('span', { class: 'meter', 'aria-hidden': 'true' },
        h('span', { style: `width:${Math.round((quiz.index / total) * 100)}%` })),
      q.concept && h('span', { text: q.concept })),
    h('p', { class: 'q-text', text: q.question }),
    h('ul', { class: 'options' }, options),
    feedback,
    quiz.index === 0 && quiz.dropped > 0 && h('p', { class: 'qa-note',
      text: `${quiz.dropped} generated question${quiz.dropped === 1 ? ' was' : 's were'} discarded because ${quiz.dropped === 1 ? 'its' : 'their'} evidence could not be found in the transcript.` }));
}

function doneView() {
  const { questions, answers } = quiz;
  const right = answers.filter(a => a.correct).length;

  const byConcept = new Map();
  questions.forEach((q, i) => {
    const key = q.concept || 'Other';
    const row = byConcept.get(key) || { right: 0, total: 0 };
    row.total += 1;
    if (answers[i].correct) row.right += 1;
    byConcept.set(key, row);
  });
  const weak = [...byConcept].filter(([name, r]) => r.right < r.total && name !== 'Other').map(([name]) => name);
  const missed = questions.map((q, i) => ({ q, a: answers[i] })).filter(x => !x.a.correct);

  return h('div', { class: 'quiz-done' },
    h('p', { class: 'score', text: `${right} of ${questions.length} correct` }),
    h('p', { class: 'muted', text: weak.length
      ? 'The concept map now marks the concepts you missed.'
      : 'Every answer was right. The concept map now marks these concepts as done.' }),
    h('ul', { class: 'breakdown' }, [...byConcept].map(([name, r]) =>
      h('li', {}, h('span', { text: name }), h('span', { class: 'muted', text: `${r.right} of ${r.total}` })))),
    h('div', { class: 'row' },
      h('button', { class: 'primary', type: 'button', text: 'What should I study next?',
        onclick: () => emit('tutor-plan') }),
      weak.length > 0 && h('button', { class: 'secondary', type: 'button', text: 'Practice the ones I missed',
        onclick: () => start(weak) }),
      h('button', { class: 'secondary', type: 'button', text: 'New quiz',
        onclick: () => { phase = 'setup'; quiz = null; render(); } })),
    missed.length > 0 && h('ul', { class: 'missed' }, missed.map(({ q, a }) =>
      h('li', {},
        h('p', { class: 'q', text: q.question }),
        h('p', { class: 'muted', text: `You chose: ${q.options[a.choice]}` }),
        h('p', { text: `Answer: ${q.options[q.correct_index]}` }),
        h('p', { text: q.explanation }),
        q.evidence.match !== 'unverified' && q.evidence.segment_id != null
          && h('ul', { class: 'evidence' }, evidenceItem(q.evidence, focusSegment))))));
}
