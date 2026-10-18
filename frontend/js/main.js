// Entry point: intake form, tabs and wiring between modules.
import { $, h } from './dom.js';
import { api } from './api.js';
import { state, startSession, on } from './state.js';
import { initStore, hashText, listSessions, findSession, deleteSession } from './store.js';
import { renderReader } from './reader.js';
import { renderOverview } from './overview.js';
import { initMap } from './map.js';
import { initAsk } from './ask.js';
import { initQuiz } from './quiz.js';
import { initTutor } from './tutor.js';

const TABS = ['overview', 'map', 'ask', 'quiz', 'tutor'];
const transcriptEl = $('#transcript');

/* ---------- server status ---------- */
async function loadStatus() {
  const dot = $('#status-dot'), text = $('#status-text');
  try {
    const j = await api.health();
    if (j.mode === 'gemini') {
      dot.className = 'dot live';
      text.textContent = `Gemini (${j.model})`;
    } else {
      dot.className = 'dot mock';
      text.textContent = 'Offline demo mode';
      $('#mock-notice').hidden = false;
    }
  } catch (e) {
    dot.className = 'dot off';
    text.textContent = 'Backend not reachable';
    showError(e.message);
  }
}

/* ---------- intake ---------- */
function updateCount() {
  $('#count').textContent = `${transcriptEl.value.length.toLocaleString()} characters`;
}
function showError(msg) { const e = $('#error'); e.textContent = msg; e.hidden = false; }
function hideError() { $('#error').hidden = true; }
function setBusy(busy) {
  $('#analyze').disabled = busy;
  $('#analyze').textContent = busy ? 'Analyzing…' : 'Analyze transcript';
  $('#busy').hidden = !busy;
}

transcriptEl.addEventListener('input', updateCount);

$('#load-sample').addEventListener('click', async () => {
  try {
    const j = await api.sample();
    transcriptEl.value = j.transcript;
    $('#video-title').value = j.title;
    updateCount();
    hideError();
  } catch (e) {
    showError(e.message);
  }
});

function openWorkspace(data, saved) {
  renderReader(data.segments);
  renderOverview(data);
  startSession(data, saved);
  $('#intake').hidden = true;
  $('#workspace').hidden = false;
  showTab('overview');
  window.scrollTo({ top: 0 });
}

// `force` skips a saved copy of the same transcript and runs a fresh analysis, which clears its progress.
/* ---------- YouTube link ---------- */
const YT_DEFAULT_NOTE = $('#yt-note').textContent;
const YT_LINK = /^(https?:\/\/)?((www|m|music)\.)?(youtube\.com|youtube-nocookie\.com|youtu\.be)\/\S+$/i;
let titleFromVideo = '';   // so a title we filled in can be replaced, but one the learner typed is kept

// Puts the video's captions into the transcript box for review. Returns true when it worked.
async function fetchYoutube(url) {
  hideError();
  const btn = $('#yt-fetch'), note = $('#yt-note');
  btn.disabled = true;
  btn.textContent = 'Fetching…';
  note.textContent = 'Reading the video’s captions. If they cannot be read, Gemini listens to the video instead, which can take a minute or two.';
  try {
    const j = await api.youtube(url);
    transcriptEl.value = j.transcript;
    const titleEl = $('#video-title');
    if (j.title && (!titleEl.value.trim() || titleEl.value === titleFromVideo)) {
      titleEl.value = j.title;
      titleFromVideo = j.title;
    }
    updateCount();
    note.textContent = j.source === 'gemini'
      ? 'Transcribed by Gemini from the video’s audio, because its captions could not be read. It can contain mistakes, '
        + 'and the quotes in your study guide are checked against this text. Review it below, then analyze.'
      : `Got ${j.generated ? 'automatic' : 'uploader-written'} captions (${j.language}). `
        + (j.generated ? 'Automatic captions can contain mistakes. ' : '') + 'Review them below, then analyze.';
    return true;
  } catch (e) {
    note.textContent = YT_DEFAULT_NOTE;
    showError(e.message);
    return false;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Get transcript';
  }
}

$('#yt-fetch').addEventListener('click', () => {
  const url = $('#yt-url').value.trim();
  if (!url) { showError('Paste a YouTube link first.'); return; }
  fetchYoutube(url);
});
$('#yt-url').addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); $('#yt-fetch').click(); }
});

async function analyze(force = false) {
  hideError();
  let transcript = transcriptEl.value.trim();
  // A link pasted into the transcript box instead of the link box: fetch it, then carry on.
  if (YT_LINK.test(transcript)) {
    if (!(await fetchYoutube(transcript))) return;
    transcript = transcriptEl.value.trim();
  }
  if (transcript.length < 50) {
    showError('Paste at least 50 characters of transcript.');
    return;
  }
  const key = hashText(transcript);
  const saved = force ? null : findSession(key);
  if (saved) {   // same transcript as a saved one: no need to pay for the analysis again
    resume(saved);
    return;
  }
  setBusy(true);
  try {
    const data = await api.analyze(transcript, $('#video-title').value.trim());
    openWorkspace(data, { key, transcript });
  } catch (e) {
    showError(e.message);
  } finally {
    setBusy(false);
  }
}

function resume(saved) {
  transcriptEl.value = saved.transcript;
  $('#video-title').value = saved.title || '';
  updateCount();
  hideError();
  openWorkspace(saved.result, saved);
}

$('#analyze').addEventListener('click', () => analyze());

// Analyzing again replaces the saved copy, so ask once before throwing away answers.
let confirmTimer = null;
const againBtn = $('#again');
function resetAgain() { clearTimeout(confirmTimer); againBtn.textContent = 'Analyze again'; againBtn.dataset.confirm = ''; }
againBtn.addEventListener('click', () => {
  const hasProgress = state.attempts.length > 0 || state.thread.length > 0;
  if (hasProgress && !againBtn.dataset.confirm) {
    againBtn.textContent = 'Clear my progress and analyze again?';
    againBtn.dataset.confirm = '1';
    confirmTimer = setTimeout(resetAgain, 6000);
    return;
  }
  resetAgain();
  $('#workspace').hidden = true;
  $('#intake').hidden = false;
  renderResume();
  analyze(true);
});
$('#edit').addEventListener('click', () => {
  $('#workspace').hidden = true;
  $('#intake').hidden = false;
  renderResume();
  transcriptEl.focus();
});

/* ---------- saved progress ---------- */
function ago(ms) {
  const s = Math.round((ms - Date.now()) / 1000);
  const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });
  for (const [unit, size] of [['day', 86400], ['hour', 3600], ['minute', 60]]) {
    if (Math.abs(s) >= size) return rtf.format(Math.round(s / size), unit);
  }
  return 'just now';
}
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

function renderResume() {
  const sessions = listSessions();
  $('#resume').hidden = sessions.length === 0;
  $('#resume-list').replaceChildren(...sessions.map(s => {
    const del = h('button', { class: 'link', type: 'button', text: 'Delete' });
    del.addEventListener('click', () => {
      if (!del.dataset.confirm) {
        del.textContent = 'Delete this?';
        del.dataset.confirm = '1';
        setTimeout(() => { del.textContent = 'Delete'; del.dataset.confirm = ''; }, 5000);
        return;
      }
      deleteSession(s.key);
      renderResume();
    });
    return h('li', {},
      h('div', { class: 'resume-info' },
        h('strong', { text: s.title || 'Untitled video' }),
        h('span', { class: 'muted',
          text: `${plural(s.attempts.length, 'quiz answer')} · ${plural(s.thread.length, 'question')} asked · saved ${ago(s.savedAt)}` })),
      h('div', { class: 'row' },
        h('button', { class: 'primary', type: 'button', text: 'Resume', onclick: () => resume(s) }),
        del));
  }));
}

on('save-status', ok => {
  const el = $('#save-status');
  el.textContent = ok ? 'Progress saved in this browser' : 'Not saved: this browser has storage turned off or full';
  el.classList.toggle('bad', !ok);
});

/* ---------- tabs ---------- */
function showTab(name, focus = false) {
  for (const t of TABS) {
    const selected = t === name;
    const tab = $(`#tab-${t}`);
    tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected ? 0 : -1;
    $(`#panel-${t}`).hidden = !selected;
  }
  if (focus) $(`#tab-${name}`).focus();
}

$('.tabs').addEventListener('click', e => {
  const tab = e.target.closest('[role=tab]');
  if (tab) showTab(tab.dataset.tab);
});
$('.tabs').addEventListener('keydown', e => {
  const i = TABS.findIndex(t => $(`#tab-${t}`).getAttribute('aria-selected') === 'true');
  const target = { ArrowRight: (i + 1) % TABS.length, ArrowLeft: (i + TABS.length - 1) % TABS.length, Home: 0, End: TABS.length - 1 }[e.key];
  if (target === undefined) return;
  e.preventDefault();
  showTab(TABS[target], true);
});

on('showtab', name => {
  showTab(name);
  $('#workspace').scrollIntoView({ block: 'start' });
});

/* ---------- start ---------- */
initStore();
initMap();
initAsk();
initQuiz();
initTutor();
loadStatus();
updateCount();
renderResume();
