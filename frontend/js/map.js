// Concept map tab: prerequisites drawn top to bottom as an SVG, with a detail panel for the selected concept.
// Layers come from the backend (graph.nodes[].layer); this file only positions and draws them.
// Top to bottom keeps long prerequisite chains inside the column and matches the study order.
import { $, h, cap, evidenceItem } from './dom.js';
import { state, on, emit, conceptById } from './state.js';
import { focusSegment } from './reader.js';

const NS = 'http://www.w3.org/2000/svg';
const NODE_W = 184, NODE_H = 60, COL_GAP = 20, LAYER_GAP = 48, PAD = 14;
const DIFFICULTY = { beginner: 1, intermediate: 2, advanced: 3 };

let selected = null;
let nodeEls = new Map();   // concept id -> <g>
let edgeEls = [];          // { el, edge }

function svg(tag, attrs = {}, ...kids) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) el.setAttribute(k, v);
  for (const kid of kids.flat()) if (kid != null) el.append(kid.nodeType ? kid : document.createTextNode(kid));
  return el;
}

function wrap(name, max = 21) {
  const words = name.trim().split(/\s+/);
  let lines = [], line = '';
  for (const w of words) {
    if (line && (line + ' ' + w).length > max) { lines.push(line); line = w; }
    else line = line ? `${line} ${w}` : w;
  }
  if (line) lines.push(line);
  if (lines.length > 2) lines = [lines[0], lines.slice(1).join(' ')];
  return lines.map(l => (l.length > max ? l.slice(0, max - 1) + '…' : l));
}

function layout(graph) {
  const order = new Map(graph.study_order.map((id, i) => [id, i]));
  const layerOf = new Map(graph.nodes.map(n => [n.id, n.layer]));
  const layers = [];
  for (const id of graph.study_order) (layers[layerOf.get(id) ?? 0] ||= []).push(id);

  const preds = new Map(graph.study_order.map(id => [id, []]));
  for (const e of graph.edges) preds.get(e.target)?.push(e.source);

  const step = NODE_W + COL_GAP;
  const widest = Math.max(1, ...layers.map(l => (l ? l.length : 0)));
  const pos = new Map();
  layers.forEach((row, layer) => {
    if (!row) return;
    // Sit each concept under the average position of its prerequisites to keep arrows short.
    const key = id => {
      const ps = preds.get(id).filter(p => pos.has(p));
      return ps.length ? ps.reduce((t, p) => t + pos.get(p).x, 0) / ps.length : PAD + order.get(id) * step;
    };
    const sorted = [...row].sort((a, b) => key(a) - key(b) || order.get(a) - order.get(b));
    const offset = ((widest - sorted.length) * step) / 2;
    sorted.forEach((id, i) =>
      pos.set(id, { x: PAD + offset + i * step, y: PAD + layer * (NODE_H + LAYER_GAP) }));
  });

  return {
    pos,
    width: PAD * 2 + widest * NODE_W + (widest - 1) * COL_GAP,
    height: PAD * 2 + layers.length * NODE_H + (layers.length - 1) * LAYER_GAP,
  };
}

function masteryOf(id) {
  const s = state.scores[id];
  if (!s || !s.total) return null;
  return s.correct === s.total ? 'mastered' : 'shaky';
}

function drawNode(c, p) {
  const mastery = masteryOf(c.id);
  const cls = ['map-node', c.importance === 'core' ? 'core' : '', c.grounded ? '' : 'ungrounded', mastery || '']
    .filter(Boolean).join(' ');
  const status = mastery === 'mastered' ? ', all quiz answers correct'
    : mastery === 'shaky' ? ', needs review' : '';
  const g = svg('g', {
    class: cls, transform: `translate(${p.x},${p.y})`, tabindex: 0, role: 'button',
    'aria-pressed': 'false',
    'aria-label': `${c.name}, ${c.importance} concept, ${c.difficulty}${status}`,
  });
  g.append(svg('rect', { width: NODE_W, height: NODE_H, rx: 6 }));

  const lines = wrap(c.name);
  lines.forEach((line, i) =>
    g.append(svg('text', { x: 12, y: lines.length === 1 ? 26 : 22 + i * 16 }, line)));

  if (mastery) g.append(svg('text', { class: 'badge', x: 12, y: NODE_H - 9 },
    mastery === 'mastered' ? 'Got it' : 'Review'));

  const level = DIFFICULTY[c.difficulty] || 2;
  for (let i = 0; i < 3; i++) {
    g.append(svg('circle', {
      class: i < level ? 'pip on' : 'pip', cx: NODE_W - 12 - (2 - i) * 10, cy: NODE_H - 13, r: 3,
    }));
  }

  g.addEventListener('click', () => select(c.id));
  g.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(c.id); }
  });
  return g;
}

function drawMap() {
  const r = state.result;
  const { pos, width, height } = layout(r.graph);

  const root = svg('svg', { viewBox: `0 0 ${width} ${height}`, width, height, role: 'group', 'aria-label': 'Concept map' });
  const marker = (id, cls) => svg('marker', {
    id, viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 8, markerHeight: 8, orient: 'auto',
  }, svg('path', { class: cls, d: 'M0,0 L10,5 L0,10 z' }));
  root.append(svg('defs', {}, marker('lm-arrow', 'map-arrow'), marker('lm-arrow-on', 'map-arrow-on')));

  edgeEls = [];
  for (const e of r.graph.edges) {
    const a = pos.get(e.source), b = pos.get(e.target);
    if (!a || !b) continue;
    const x1 = a.x + NODE_W / 2, y1 = a.y + NODE_H, x2 = b.x + NODE_W / 2, y2 = b.y;
    const dy = Math.max(20, (y2 - y1) / 2);
    const el = svg('path', {
      class: 'map-edge', 'marker-end': 'url(#lm-arrow)',
      d: `M${x1},${y1} C${x1},${y1 + dy} ${x2},${y2 - dy} ${x2},${y2}`,
    });
    root.append(el);
    edgeEls.push({ el, edge: e });
  }

  nodeEls = new Map();
  for (const id of r.graph.study_order) {
    const c = conceptById(id);
    if (!c || !pos.has(id)) continue;
    const g = drawNode(c, pos.get(id));
    nodeEls.set(id, g);
    root.append(g);
  }
  return root;
}

function applySelection() {
  const edges = state.result.graph.edges;
  const related = new Set();
  if (selected) {
    related.add(selected);
    for (const e of edges) {
      if (e.source === selected) related.add(e.target);
      if (e.target === selected) related.add(e.source);
    }
  }
  for (const [id, el] of nodeEls) {
    el.classList.toggle('sel', id === selected);
    el.classList.toggle('rel', !!selected && id !== selected && related.has(id));
    el.classList.toggle('dim', !!selected && !related.has(id));
    el.setAttribute('aria-pressed', String(id === selected));
  }
  for (const { el, edge } of edgeEls) {
    const active = !!selected && (edge.source === selected || edge.target === selected);
    el.classList.toggle('on', active);
    el.classList.toggle('dim', !!selected && !active);
    el.setAttribute('marker-end', `url(#${active ? 'lm-arrow-on' : 'lm-arrow'})`);
  }
}

function renderDetail() {
  const box = $('#map-detail');
  const c = conceptById(selected);
  if (!c) { box.replaceChildren(); return; }
  const g = state.result.graph;
  const needs = g.edges.filter(e => e.target === c.id).map(e => conceptById(e.source)).filter(Boolean);
  const leads = g.edges.filter(e => e.source === c.id).map(e => conceptById(e.target)).filter(Boolean);
  const links = list => list.length
    ? list.map(x => h('button', { class: 'link', type: 'button', text: x.name, onclick: () => select(x.id, true) }))
    : [h('span', { class: 'muted', text: 'nothing in this video' })];
  const score = state.scores[c.id];

  // replaceChildren() turns undefined into the text "undefined", so drop the empty slots first.
  box.replaceChildren(...[
    h('h3', { text: c.name }),
    h('div', { class: 'tags' },
      h('span', { class: 'tag', text: cap(c.importance) }),
      h('span', { class: 'tag', text: cap(c.difficulty) })),
    h('p', { text: c.definition }),
    h('p', { class: 'rel-line' }, h('span', { class: 'rel-label', text: 'Needs first: ' }), links(needs)),
    h('p', { class: 'rel-line' }, h('span', { class: 'rel-label', text: 'Leads to: ' }), links(leads)),
    score && h('p', { class: 'muted', text: `Quiz so far: ${score.correct} of ${score.total} correct.` }),
    h('ul', { class: 'evidence' }, c.evidence.map(e => evidenceItem(e, focusSegment))),
    h('div', { class: 'actions' },
      h('button', { class: 'link', type: 'button', text: 'Ask about this',
        onclick: () => emit('ask-question', `What is ${c.name}?`) }),
      h('button', { class: 'link', type: 'button', text: 'Quiz me on this',
        onclick: () => emit('quiz-concept', c.name) })),
  ].filter(Boolean));
}

function select(id, scrollTo = false) {
  selected = id;
  applySelection();
  renderDetail();
  if (scrollTo) nodeEls.get(id)?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
}

function build() {
  const r = state.result;
  const root = $('#panel-map');
  if (!r || !r.concepts.length) {
    root.replaceChildren(h('p', { class: 'hint', text: 'No concepts were found, so there is nothing to map.' }));
    return;
  }
  if (!selected || !conceptById(selected)) selected = r.graph.study_order[0];

  const g = r.graph;
  const notes = [
    'Read from top to bottom. Arrows run from a prerequisite to the concept that needs it. A thick outline marks a core concept, and the dots show difficulty.',
    'Select a concept to see what it needs and what builds on it.',
  ];
  if (!g.edges.length) notes.unshift('No prerequisite links were found, so concepts are listed in study order.');
  if (g.ignored_edges > 0) {
    notes.push(`${g.ignored_edges} prerequisite link${g.ignored_edges === 1 ? ' was' : 's were'} left out because ${g.ignored_edges === 1 ? 'it' : 'they'} formed a loop.`);
  }
  if (Object.keys(state.scores).length) {
    notes.push('Green means every quiz answer on that concept was right. Amber means at least one was wrong.');
  }

  root.replaceChildren(
    h('div', { class: 'map-scroll' }, drawMap()),
    h('div', { class: 'map-notes' }, notes.map(n => h('p', { text: n }))),
    h('div', { class: 'detail', id: 'map-detail' }));
  applySelection();
  renderDetail();
}

export function initMap() {
  on('session', () => { selected = null; build(); });
  on('scores', build);
}
