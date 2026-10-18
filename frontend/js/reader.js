// The transcript panel. Other tabs call focusSegment() to show where a quote comes from.
import { $, h, fmt } from './dom.js';

let focusedRow = null;

export function renderReader(segments) {
  focusedRow = null;
  $('#r-segments').replaceChildren(...segments.map(s =>
    h('div', { class: 'seg', 'data-id': s.id },
      h('span', { class: 'time', text: fmt(s.start) || `#${s.id}` }),
      h('span', { class: 'text', 'data-full': s.text, text: s.text }))));
}

function clearFocus() {
  if (!focusedRow) return;
  const t = focusedRow.querySelector('.text');
  t.textContent = t.dataset.full;
  focusedRow.classList.remove('focus');
  focusedRow = null;
}

export function focusSegment(id, quote) {
  clearFocus();
  const row = document.querySelector(`.seg[data-id="${id}"]`);
  if (!row) return;
  const t = row.querySelector('.text');
  const full = t.dataset.full;
  const at = quote ? full.toLowerCase().indexOf(quote.toLowerCase()) : -1;
  t.textContent = '';
  if (at >= 0) {
    t.append(full.slice(0, at), h('mark', { text: full.slice(at, at + quote.length) }), full.slice(at + quote.length));
  } else {
    t.append(h('mark', { text: full })); // wording differs slightly: mark the whole segment
  }
  row.classList.add('focus');
  focusedRow = row;
  row.scrollIntoView({ block: 'center' });
}
