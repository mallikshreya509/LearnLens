// Ask tab: grounded Q&A. Answers come from the transcript and carry the quotes they rely on.
import { $, h, evidenceItem } from './dom.js';
import { api } from './api.js';
import { state, on, emit } from './state.js';
import { focusSegment } from './reader.js';

let busy = false;

export function initAsk() {
  $('#panel-ask').append(
    h('p', { class: 'hint',
      text: 'Ask about anything in the video. Answers use only the transcript, and each one shows the lines it relies on.' }),
    h('div', { class: 'chips', id: 'ask-chips' }),
    h('ol', { class: 'thread', id: 'ask-thread', 'aria-live': 'polite' }),
    h('form', { class: 'ask-form', id: 'ask-form',
      onsubmit: e => { e.preventDefault(); submit($('#ask-input').value); } },
      h('label', { class: 'sr', for: 'ask-input', text: 'Your question' }),
      h('input', { type: 'text', id: 'ask-input', maxlength: 500, autocomplete: 'off',
        placeholder: 'Ask a question about the video' }),
      h('button', { class: 'primary', type: 'submit', id: 'ask-send', text: 'Ask' })));

  on('session', () => { busy = false; render(); });
  on('ask-question', q => { emit('showtab', 'ask'); submit(q); });
}

async function submit(question) {
  question = question.trim();
  if (!question || busy || !state.result) return;
  const thread = state.thread;
  const item = { question, status: 'pending' };
  thread.push(item);
  busy = true;
  $('#ask-input').value = '';
  render();

  const history = thread
    .filter(t => t.status === 'done')
    .slice(-3)
    .flatMap(t => [
      { role: 'user', text: t.question },
      { role: 'tutor', text: t.result.answer.slice(0, 4000) },
    ]);

  try {
    item.result = await api.ask(question, state.result.segments, history);
    item.status = 'done';
  } catch (e) {
    item.status = 'error';
    item.error = e.message;
  }
  if (state.thread !== thread) return; // a new analysis replaced this session
  busy = false;
  render();
  emit('asked');
  document.querySelector('#ask-thread .qa:last-child')?.scrollIntoView({ block: 'nearest' });
}

function render() {
  if (!state.result) return;
  const thread = $('#ask-thread');
  thread.replaceChildren(...state.thread.map(item =>
    h('li', { class: 'qa' },
      h('p', { class: 'qa-q', text: item.question }),
      answer(item))));
  renderChips();
  $('#ask-send').disabled = busy;
}

function renderChips() {
  const last = [...state.thread].reverse().find(t => t.status === 'done');
  const suggestions = state.thread.length === 0
    ? state.result.concepts.slice(0, 3).map(c => `What is ${c.name}?`)
    : (last?.result.follow_ups || []);
  $('#ask-chips').replaceChildren(...suggestions.map(q =>
    h('button', { class: 'chip', type: 'button', text: q, disabled: busy, onclick: () => submit(q) })));
}

function answer(item) {
  if (item.status === 'pending') return h('p', { class: 'qa-a pending', text: 'Reading the transcript…' });
  if (item.status === 'error') return h('p', { class: 'qa-a error', role: 'alert', text: item.error });

  const r = item.result;
  if (r.status === 'not_covered') {
    return h('div', {},
      h('div', { class: 'qa-flag' },
        h('strong', { text: 'Not covered in this video' }),
        'No answer was made up from outside the transcript.'),
      h('p', { class: 'qa-a', text: r.answer }));
  }

  const parts = [h('p', { class: 'qa-a', text: r.answer })];
  if (r.status === 'unverified') {
    parts.unshift(h('div', { class: 'qa-flag bad' },
      h('strong', { text: 'Could not be checked against the transcript' }),
      'None of the quotes behind this answer were found in the transcript. Treat it with caution.'));
  } else {
    parts.push(h('ul', { class: 'evidence' }, r.citations.map(c => evidenceItem(c, focusSegment))));
  }
  if (r.unverified_dropped > 0) {
    parts.push(h('p', { class: 'qa-note',
      text: `${r.unverified_dropped} quote${r.unverified_dropped === 1 ? '' : 's'} removed because ${r.unverified_dropped === 1 ? 'it' : 'they'} could not be found in the transcript.` }));
  }
  return h('div', {}, parts);
}
