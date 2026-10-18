// Small DOM helpers. Everything is built with textContent, so model output is never parsed as HTML.
export const $ = (sel, root = document) => root.querySelector(sel);

export function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'text') el.textContent = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

export function fmt(seconds) {
  if (seconds == null) return '';
  const s = Math.floor(seconds);
  const hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = s % 60;
  const p = n => String(n).padStart(2, '0');
  return hh ? `${hh}:${p(mm)}:${p(ss)}` : `${p(mm)}:${p(ss)}`;
}

export const cap = s => s.charAt(0).toUpperCase() + s.slice(1);

export const STATE_LABEL = {
  exact: 'Verified in transcript',
  approximate: 'Close match, wording differs slightly',
  unverified: 'Not found in transcript',
};

// One clickable quote. `onOpen(segmentId, quote)` is normally reader.focusSegment.
export function evidenceItem(ev, onOpen) {
  const locatable = ev.match !== 'unverified' && ev.segment_id != null;
  const where = ev.timestamp || (ev.segment_id != null ? `#${ev.segment_id}` : '');
  return h('li', {},
    h('button', {
      class: 'ev', type: 'button', disabled: !locatable,
      onclick: () => onOpen(ev.segment_id, ev.quote),
    },
      h('span', { class: 'time', text: where }),
      h('span', { class: 'quote', text: `“${ev.quote}”` }),
      h('span', { class: `state ${ev.match}`, text: STATE_LABEL[ev.match] || ev.match })));
}
