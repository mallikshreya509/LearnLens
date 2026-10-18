// Tutor tab. The tutor reads the learner's quiz answers and questions, diagnoses each concept and picks
// one next step. Facts (statuses, gaps, the reason) come from the backend's rules; Gemini only writes lessons.
import { $, h, evidenceItem } from './dom.js';
import { api } from './api.js';
import { state, on, emit } from './state.js';
import { focusSegment } from './reader.js';

const ACTION_LABEL = {
  diagnose: 'Check',
  reteach: 'Re-teach',
  review_prerequisite: 'Back to basics',
  practice: 'Practice',
  check: 'Double-check',
  advance: 'Next concept',
  complete: 'Done',
};
const STATUS_LABEL = {
  unseen: 'Not checked yet',
  exploring: 'Asked about, not quizzed',
  shaky: 'Shaky',
  struggling: 'Struggling',
  solid: 'Solid',
};

let plan = null;
let loading = false;
let error = '';
let stale = false;   // the learner answered or asked something after this plan was made

export function initTutor() {
  on('session', () => { plan = null; loading = false; error = ''; stale = false; render(); });
  on('scores', () => { if (plan) { stale = true; render(); } });
  on('asked', () => { if (plan) { stale = true; render(); } });
  on('tutor-plan', () => { emit('showtab', 'tutor'); run(); });
}

function payload() {
  const r = state.result;
  return {
    segments: r.segments,
    concepts: r.concepts.map(c => ({
      id: c.id, name: c.name, definition: c.definition, prerequisites: c.prerequisites,
    })),
    study_order: r.graph.study_order,
    attempts: state.attempts.slice(-300),
    asked: state.thread.map(t => t.question).slice(-100),
  };
}

async function run() {
  if (loading || !state.result) return;
  const session = state.result;
  loading = true;
  error = '';
  render();
  try {
    const data = await api.tutor(payload());
    if (state.result !== session) return;
    plan = data;
    stale = false;
  } catch (e) {
    if (state.result !== session) return;
    error = e.message;
  }
  loading = false;
  render();
  $('#tutor-step')?.focus();
}

function render() {
  if (!state.result) return;
  $('#panel-tutor').replaceChildren(...[
    h('p', { class: 'hint',
      text: 'The tutor looks at your quiz answers and the questions you asked, finds what is shaky, and picks one next step. It shows the evidence for its choice.' }),
    h('div', { class: 'row' },
      h('button', { class: 'primary', type: 'button', disabled: loading, onclick: run,
        text: loading ? 'Planning…' : plan ? 'Plan again' : 'Plan my next step' }),
      stale && h('span', { class: 'muted', role: 'status',
        text: 'You have answered more since this plan. Plan again to include it.' })),
    error && h('div', { class: 'error', role: 'alert', text: error }),
    plan && h('div', { class: 'tutor-plan' }, stepCard(plan.next_step), standing(plan), gaps(plan.gaps), trace(plan.trace)),
  ].filter(Boolean));
}

function stepCard(step) {
  const lesson = step.lesson;
  const goAsk = () => emit('showtab', 'ask');
  return h('article', { class: 'step', id: 'tutor-step', tabindex: -1 },
    h('span', { class: 'tag', text: ACTION_LABEL[step.action] || step.action }),
    h('h3', { class: 'step-title', text: step.title }),
    h('p', { class: 'step-reason', text: step.reason }),
    lesson && h('div', { class: 'lesson' },
      lesson.status === 'unverified' && h('div', { class: 'qa-flag bad' },
        h('strong', { text: 'Could not be checked against the transcript' }),
        'No quote behind this lesson was found in the transcript. Treat it with caution.'),
      h('p', { class: 'lesson-text', text: lesson.explanation }),
      lesson.key_points.length > 0 && h('ul', { class: 'plain' }, lesson.key_points.map(k => h('li', { text: k }))),
      lesson.citations.length > 0 && h('ul', { class: 'evidence' }, lesson.citations.map(c => evidenceItem(c, focusSegment)))),
    step.lesson_error && h('div', { class: 'error', role: 'alert',
      text: `The lesson could not be written: ${step.lesson_error} You can still take the quiz.` }),
    h('div', { class: 'row' },
      step.quiz
        ? h('button', { class: 'primary', type: 'button', text: step.cta,
            onclick: () => emit('quiz-start', { focus: step.quiz.focus, count: step.quiz.count }) })
        : h('button', { class: 'secondary', type: 'button', text: step.cta, onclick: goAsk }),
      lesson && h('button', { class: 'link', type: 'button', text: 'Ask a follow-up question', onclick: goAsk })));
}

function standing(p) {
  const pr = p.progress;
  return h('section', { class: 'standing' },
    h('h2', { text: 'Where you stand' }),
    h('div', { class: 'grounding' },
      h('span', { class: 'meter', 'aria-hidden': 'true' }, h('span', { style: `width:${pr.percent}%` })),
      h('span', { text: `${pr.solid} of ${pr.total} concepts solid` })),
    h('ul', { class: 'status-list' }, p.concepts.map(c => {
      const detail = c.attempts
        ? `${c.correct} of ${c.attempts} right`
        : c.asked ? `${c.asked} question${c.asked === 1 ? '' : 's'} asked` : '';
      return h('li', {},
        h('span', { class: 'sname', text: c.name }),
        h('span', { class: `pill ${c.status}`, text: STATUS_LABEL[c.status] }),
        detail && h('span', { class: 'muted', text: detail }),
        c.weak_prerequisites.length > 0 && h('span', { class: 'sub',
          text: `Builds on ${c.weak_prerequisites.join(' and ')}, which needs work.` }));
    })));
}

function gaps(list) {
  return h('section', { class: 'gaps' },
    h('h2', { text: 'Gaps' }),
    list.length === 0
      ? h('p', { class: 'muted', text: 'No gaps right now.' })
      : h('ul', { class: 'gap-list' }, list.map(g =>
          h('li', {},
            h('span', { class: 'sname', text: g.concept }),
            h('span', { class: `tag${g.severity === 'high' ? ' urgent' : ''}`,
              text: g.severity === 'high' ? 'High priority' : 'Lower priority' }),
            h('span', { class: 'sub', text: g.detail })))));
}

function trace(lines) {
  return h('details', { class: 'trace' },
    h('summary', { text: 'How the tutor decided' }),
    h('ol', {}, lines.map(l => h('li', { text: l }))));
}
