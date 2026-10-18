// Overview tab: summary, takeaways and the concept list with evidence.
import { $, h, cap, evidenceItem } from './dom.js';
import { emit } from './state.js';
import { focusSegment } from './reader.js';

export function renderOverview(r) {
  $('#r-title').textContent = r.title;
  $('#r-one-line').textContent = r.one_sentence_summary;
  $('#r-summary').textContent = r.summary;
  $('#r-takeaways').replaceChildren(...r.key_takeaways.map(t => h('li', { text: t })));
  $('#r-objectives').replaceChildren(...r.learning_objectives.map(t => h('li', { text: t })));

  const { evidence_total: total, evidence_verified: ok } = r.stats;
  $('#r-meter').style.width = `${total ? Math.round((ok / total) * 100) : 0}%`;
  $('#r-grounding').textContent = total
    ? `${ok} of ${total} quotes found in the transcript`
    : 'No quotes to check';

  const idByName = Object.fromEntries(r.concepts.map(c => [c.name, c.id]));
  $('#r-concepts').replaceChildren(...r.concepts.map((c, i) => conceptItem(c, i, idByName)));
}

function conceptItem(c, i, idByName) {
  const prereqs = c.prerequisites.filter(name => idByName[name]);
  return h('li', { class: 'concept', id: 'c-' + c.id },
    h('span', { class: 'num', text: i + 1 }),
    h('div', {},
      h('h3', { text: c.name }),
      h('div', { class: 'tags' },
        h('span', { class: 'tag', text: cap(c.importance) }),
        h('span', { class: 'tag', text: cap(c.difficulty) })),
      h('p', { text: c.definition }),
      prereqs.length > 0 && h('p', { class: 'prereq' }, 'Learn first: ',
        prereqs.map(name => h('button', {
          class: 'link', type: 'button', text: name,
          onclick: () => document.getElementById('c-' + idByName[name])?.scrollIntoView({ block: 'start' }),
        }))),
      !c.grounded && h('p', { class: 'caution',
        text: 'None of this concept’s quotes could be found in the transcript. Treat it with caution.' }),
      h('ul', { class: 'evidence' }, c.evidence.map(e => evidenceItem(e, focusSegment))),
      h('div', { class: 'actions' },
        h('button', { class: 'link', type: 'button', text: 'Ask about this',
          onclick: () => emit('ask-question', `What is ${c.name}?`) }),
        h('button', { class: 'link', type: 'button', text: 'Quiz me on this',
          onclick: () => emit('quiz-concept', c.name) }))));
}
