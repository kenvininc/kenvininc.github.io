// Dailoc Music - frontend player
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const audio = $('#audio');

const ICON_PLAY = '<svg viewBox="0 0 24 24"><path d="M8 5.14v13.72a1 1 0 0 0 1.52.85l10.6-6.86a1 1 0 0 0 0-1.7L9.52 4.29A1 1 0 0 0 8 5.14Z"/></svg>';
const ICON_PAUSE = '<svg viewBox="0 0 24 24"><path d="M7 4h3.5v16H7V4Zm6.5 0H17v16h-3.5V4Z"/></svg>';
const ICON_MORE = '<svg viewBox="0 0 24 24"><path d="M12 7a2 2 0 1 1 0-4 2 2 0 0 1 0 4Zm0 7a2 2 0 1 1 0-4 2 2 0 0 1 0 4Zm0 7a2 2 0 1 1 0-4 2 2 0 0 1 0 4Z"/></svg>';
const NO_ART = 'data:image/svg+xml,' + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="#22252f"/>' +
  '<path d="M62 24v38a10 10 0 1 1-6-9.2V34l-20 5v29a10 10 0 1 1-6-9.2V32l32-8Z" fill="#4b5060"/></svg>');

const collator = new Intl.Collator('vi', { sensitivity: 'base', numeric: true });
const norm = (s) => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/gi, 'd').toLowerCase();
const fmt = (s) => {
  if (!Number.isFinite(s) || s < 0) s = 0;
  s = Math.floor(s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`;
};
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const artUrl = (t) => (t && t.cover ? `/cover/${t.id}` : NO_ART);
const artistOf = (t) => t.artist || t.albumArtist || 'Không rõ ca sĩ';

// ---------- state ----------
let tracks = [];
let byId = new Map();
let view = 'songs';
let filter = null; // {type:'album'|'artist', value, label}
let sortMode = 'new';
const st = {
  queue: [],      // track ids in play order
  base: [],       // un-shuffled order (to restore when shuffle off)
  index: -1,
  shuffle: false,
  repeat: 'off',  // off | all | one
  pos: 0,
};
let errorStreak = 0;

function saveState() {
  try {
    localStorage.setItem('player', JSON.stringify({ ...st, pos: audio.currentTime || st.pos }));
  } catch {}
}
function loadState() {
  try {
    const s = JSON.parse(localStorage.getItem('player') || 'null');
    if (s && Array.isArray(s.queue)) Object.assign(st, s);
  } catch {}
}

// ---------- api ----------
async function api(url, opts = {}) {
  const r = await fetch(url, { credentials: 'same-origin', ...opts });
  if (r.status === 401) { showLogin(); throw new Error('unauthorized'); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}

function toast(msg, ms = 2500) {
  const el = $('#toast');
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => { el.hidden = true; }, ms);
}

// ---------- auth ----------
function showLogin() {
  $('#app').hidden = true;
  $('#login').hidden = false;
  audio.pause();
  setTimeout(() => $('#password').focus(), 50);
}
$('#loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  $('#loginErr').textContent = '';
  try {
    const r = await fetch('/api/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: $('#password').value }),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || 'Đăng nhập thất bại');
    $('#password').value = '';
    start();
  } catch (err) {
    $('#loginErr').textContent = err.message;
  }
});

// ---------- library ----------
async function loadTracks() {
  const d = await api('/api/tracks');
  tracks = d.tracks;
  byId = new Map(tracks.map((t) => [t.id, t]));
  // drop ids that no longer exist from the queue
  const cur = st.queue[st.index];
  st.queue = st.queue.filter((id) => byId.has(id));
  st.base = st.base.filter((id) => byId.has(id));
  st.index = cur ? st.queue.indexOf(cur) : -1;
  render();
}

function filtered() {
  const q = norm($('#q').value.trim());
  let list = tracks;
  if (filter?.type === 'album') list = list.filter((t) => albumKey(t) === filter.value);
  if (filter?.type === 'artist') list = list.filter((t) => artistOf(t) === filter.value);
  if (q) list = list.filter((t) => norm(`${t.title} ${t.artist} ${t.album} ${t.albumArtist}`).includes(q));
  list = [...list];
  if (filter?.type === 'album') {
    list.sort((a, b) => (a.discNo - b.discNo) || (a.trackNo - b.trackNo) || collator.compare(a.title, b.title));
  } else if (sortMode === 'az') {
    list.sort((a, b) => collator.compare(a.title, b.title));
  } else {
    list.sort((a, b) => b.addedAt - a.addedAt);
  }
  return list;
}
const albumKey = (t) => `${t.album || '—'}\u0000${t.albumArtist || t.artist || ''}`;

function songRow(t, { queueIdx } = {}) {
  const playing = st.queue[st.index] === t.id;
  return `<li data-id="${t.id}" ${queueIdx != null ? `data-qi="${queueIdx}"` : ''} class="${playing ? 'playing' : ''}">
    <img class="art" loading="lazy" src="${artUrl(t)}" alt="">
    <div class="meta"><b>${esc(t.title)}</b><span>${esc(artistOf(t))}${t.album ? ' · ' + esc(t.album) : ''}</span></div>
    <span class="dur">${t.duration ? fmt(t.duration) : ''}</span>
    <button class="icon-btn more" aria-label="Tuỳ chọn">${ICON_MORE}</button>
  </li>`;
}

function render() {
  $$('[data-view]').forEach((s) => { s.hidden = s.dataset.view !== view; });
  $$('.tabs button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === view)));
  $('#filterBar').hidden = !filter || view !== 'songs';
  if (filter) $('#filterLabel').textContent = filter.label;

  if (view === 'songs') {
    const list = filtered();
    $('#songList').innerHTML = list.map((t) => songRow(t)).join('');
    $('#count').textContent = `${list.length} bài`;
    $('#empty').hidden = tracks.length > 0;
    $('#sortBtn').textContent = sortMode === 'az' ? 'A–Z' : 'Mới nhất';
    $('#sortBtn').hidden = !!filter;
  } else if (view === 'albums') {
    const q = norm($('#q').value.trim());
    const albums = new Map();
    for (const t of tracks) {
      const k = albumKey(t);
      if (!albums.has(k)) albums.set(k, { key: k, name: t.album || 'Không rõ album', artist: t.albumArtist || t.artist || '', cover: null, n: 0 });
      const a = albums.get(k);
      a.n++;
      if (!a.cover && t.cover) a.cover = t;
    }
    const list = [...albums.values()]
      .filter((a) => !q || norm(a.name + ' ' + a.artist).includes(q))
      .sort((a, b) => collator.compare(a.name, b.name));
    $('#albumGrid').innerHTML = list.map((a) => `<button class="album" data-key="${esc(a.key)}" data-label="${esc(a.name)}">
      <img loading="lazy" src="${artUrl(a.cover)}" alt=""><b>${esc(a.name)}</b><span>${esc(a.artist)} · ${a.n} bài</span></button>`).join('')
      || '<p class="empty">Không có album.</p>';
  } else if (view === 'artists') {
    const q = norm($('#q').value.trim());
    const counts = new Map();
    for (const t of tracks) counts.set(artistOf(t), (counts.get(artistOf(t)) || 0) + 1);
    const list = [...counts.entries()].filter(([a]) => !q || norm(a).includes(q)).sort((a, b) => collator.compare(a[0], b[0]));
    $('#artistList').innerHTML = list.map(([a, n]) => `<li><button data-artist="${esc(a)}"><span>${esc(a)}</span><span class="muted">${n}</span></button></li>`).join('')
      || '<p class="empty">Không có ca sĩ.</p>';
  }
  renderQueue();
  renderNow();
}

function renderQueue() {
  if ($('#player').hidden) return;
  const html = st.queue.slice(st.index, st.index + 100)
    .map((id, i) => byId.get(id) && songRow(byId.get(id), { queueIdx: st.index + i }))
    .filter(Boolean).join('');
  $('#queueList').innerHTML = html;
}

// ---------- tabs / filters ----------
$('.tabs').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-tab]');
  if (!b) return;
  view = b.dataset.tab;
  if (view !== 'songs') filter = null;
  render();
  window.scrollTo(0, 0);
});
$('#q').addEventListener('input', () => {
  if (view === 'upload') view = 'songs';
  render();
});
$('#clearFilter').addEventListener('click', () => { filter = null; render(); });
$('#albumGrid').addEventListener('click', (e) => {
  const b = e.target.closest('.album');
  if (!b) return;
  filter = { type: 'album', value: b.dataset.key, label: '💿 ' + b.dataset.label };
  $('#q').value = '';
  view = 'songs';
  render();
  window.scrollTo(0, 0);
});
$('#artistList').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-artist]');
  if (!b) return;
  filter = { type: 'artist', value: b.dataset.artist, label: '🎤 ' + b.dataset.artist };
  $('#q').value = '';
  view = 'songs';
  render();
  window.scrollTo(0, 0);
});

// sort toggle button (injected into list actions)
{
  const b = document.createElement('button');
  b.id = 'sortBtn';
  b.className = 'chip';
  b.addEventListener('click', () => { sortMode = sortMode === 'az' ? 'new' : 'az'; render(); });
  $('.list-actions').insertBefore(b, $('#count'));
}

$('#songList').addEventListener('click', (e) => {
  const li = e.target.closest('li[data-id]');
  if (!li) return;
  if (e.target.closest('.more')) return openTrackMenu(li.dataset.id, null);
  const list = filtered().map((t) => t.id);
  setQueue(list, list.indexOf(li.dataset.id));
});
$('#queueList').addEventListener('click', (e) => {
  const li = e.target.closest('li[data-id]');
  if (!li) return;
  const qi = Number(li.dataset.qi);
  if (e.target.closest('.more')) return openTrackMenu(li.dataset.id, qi);
  playIndex(qi);
});
$('#playAll').addEventListener('click', () => {
  const list = filtered().map((t) => t.id);
  if (!list.length) return;
  st.shuffle = false;
  setQueue(list, 0);
});
$('#shuffleAll').addEventListener('click', () => {
  const list = filtered().map((t) => t.id);
  if (!list.length) return;
  st.shuffle = true;
  setQueue(list, Math.floor(Math.random() * list.length));
});

// ---------- track action sheet ----------
function openTrackMenu(id, queueIdx) {
  const t = byId.get(id);
  if (!t) return;
  const sheet = document.createElement('div');
  sheet.className = 'menu';
  sheet.style.cssText = 'position:fixed;left:8px;right:8px;top:auto;bottom:calc(8px + env(safe-area-inset-bottom,0px));z-index:40;min-width:0';
  const items = [
    ['next', 'Phát tiếp theo'],
    ['add', 'Thêm vào cuối danh sách chờ'],
    ...(queueIdx != null && queueIdx !== st.index ? [['unqueue', 'Bỏ khỏi danh sách chờ']] : []),
    ['delete', '🗑 Xoá file khỏi NAS'],
    ['cancel', 'Huỷ'],
  ];
  sheet.innerHTML = `<div style="padding:12px 16px;color:var(--muted);font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(t.title)}</div>` +
    items.map(([k, l]) => `<button data-k="${k}" ${k === 'delete' ? 'style="color:var(--danger)"' : ''}>${l}</button>`).join('');
  const backdrop = document.createElement('div');
  backdrop.style.cssText = 'position:fixed;inset:0;background:#0007;z-index:39';
  const close = () => { sheet.remove(); backdrop.remove(); };
  backdrop.addEventListener('click', close);
  sheet.addEventListener('click', async (e) => {
    const k = e.target.closest('button')?.dataset.k;
    if (!k) return;
    close();
    if (k === 'next') insertNext(id);
    if (k === 'add') { st.queue.push(id); st.base.push(id); if (st.index < 0) playIndex(0); saveState(); toast('Đã thêm vào danh sách chờ'); renderQueue(); }
    if (k === 'unqueue') { st.queue.splice(queueIdx, 1); if (queueIdx < st.index) st.index--; saveState(); renderQueue(); }
    if (k === 'delete') {
      if (!confirm(`Xoá hẳn file "${t.title}" khỏi NAS?\nKhông khôi phục được từ web (trừ khi NAS có Recycle Bin / snapshot).`)) return;
      try {
        await api(`/api/tracks/${id}`, { method: 'DELETE' });
        const wasCurrent = st.queue[st.index] === id;
        const qi = st.queue.indexOf(id);
        if (qi >= 0) { st.queue.splice(qi, 1); if (qi < st.index) st.index--; }
        st.base = st.base.filter((x) => x !== id);
        if (wasCurrent) { audio.pause(); audio.removeAttribute('src'); st.index = Math.min(st.index, st.queue.length - 1); }
        await loadTracks();
        toast('Đã xoá');
      } catch (err) { toast('Lỗi: ' + err.message); }
    }
  });
  document.body.append(backdrop, sheet);
}

function insertNext(id) {
  if (st.index < 0) { setQueue([id], 0); return; }
  st.queue.splice(st.index + 1, 0, id);
  st.base.push(id);
  saveState();
  renderQueue();
  toast('Sẽ phát tiếp theo');
}

// ---------- playback ----------
function shuffled(arr, firstId) {
  const a = arr.filter((x) => x !== firstId);
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return firstId ? [firstId, ...a] : a;
}

function setQueue(ids, startIdx) {
  if (!ids.length) return;
  startIdx = Math.max(0, startIdx);
  st.base = [...ids];
  if (st.shuffle) {
    st.queue = shuffled(ids, ids[startIdx]);
    startIdx = 0;
  } else {
    st.queue = [...ids];
  }
  playIndex(startIdx);
}

function current() { return byId.get(st.queue[st.index]); }

function playIndex(i, { autoplay = true, at = 0 } = {}) {
  if (i < 0 || i >= st.queue.length) return;
  st.index = i;
  const t = current();
  if (!t) return;
  audio.src = `/stream/${t.id}`;
  if (at) {
    const seekOnce = () => { audio.currentTime = at; audio.removeEventListener('loadedmetadata', seekOnce); };
    audio.addEventListener('loadedmetadata', seekOnce);
  }
  if (autoplay) {
    audio.play().catch((err) => {
      if (err.name === 'NotAllowedError') toast('Bấm ▶ để phát');
    });
  } else {
    audio.load();
  }
  updateMediaSession();
  saveState();
  renderNow();
  renderQueue();
}

function next(auto = false) {
  if (!st.queue.length) return;
  if (auto && st.repeat === 'one') { audio.currentTime = 0; audio.play(); return; }
  let n = st.index + 1;
  if (n >= st.queue.length) {
    if (st.repeat === 'all' || !auto) n = 0;
    else { audio.pause(); audio.currentTime = 0; renderNow(); return; }
  }
  playIndex(n);
}
function prev() {
  if (!st.queue.length) return;
  if (audio.currentTime > 3) { audio.currentTime = 0; return; }
  playIndex(st.index > 0 ? st.index - 1 : (st.repeat === 'all' ? st.queue.length - 1 : 0));
}
function togglePlay() {
  if (!current()) {
    const list = filtered().map((t) => t.id);
    if (list.length) setQueue(list, 0);
    return;
  }
  if (!audio.src) playIndex(st.index, { at: st.pos });
  else if (audio.paused) audio.play().catch(() => {});
  else audio.pause();
}

audio.addEventListener('ended', () => next(true));
audio.addEventListener('playing', () => { errorStreak = 0; });
audio.addEventListener('error', () => {
  const t = current();
  if (!t || !audio.src) return;
  errorStreak++;
  const code = audio.error?.code;
  toast(code === 4 ? `Không phát được "${t.title}" (định dạng không hỗ trợ hoặc phiên đăng nhập hết hạn)` : `Lỗi phát "${t.title}"`, 4000);
  // auto-skip, but stop if every track in the queue is failing
  if (errorStreak < st.queue.length && errorStreak < 5) setTimeout(() => next(true), 1500);
  else fetch('/api/me').then((r) => r.json()).then((d) => { if (!d.authed) showLogin(); });
});

['play', 'pause', 'playing', 'waiting'].forEach((ev) => audio.addEventListener(ev, () => { renderNow(); updatePositionState(); }));
audio.addEventListener('loadedmetadata', updatePositionState);
audio.addEventListener('pause', saveState);

let lastSave = 0;
audio.addEventListener('timeupdate', () => {
  const d = audio.duration || current()?.duration || 0;
  const p = d ? audio.currentTime / d : 0;
  $('#miniBar').style.width = `${p * 100}%`;
  if (!seeking) $('#seek').value = String(Math.round(p * 1000));
  $('#tCur').textContent = fmt(audio.currentTime);
  $('#tDur').textContent = fmt(d);
  if (Date.now() - lastSave > 5000) { lastSave = Date.now(); saveState(); }
});

let seeking = false;
$('#seek').addEventListener('input', () => {
  seeking = true;
  const d = audio.duration || 0;
  $('#tCur').textContent = fmt((Number($('#seek').value) / 1000) * d);
});
$('#seek').addEventListener('change', () => {
  const d = audio.duration || 0;
  if (d) audio.currentTime = (Number($('#seek').value) / 1000) * d;
  seeking = false;
  updatePositionState();
});

function renderNow() {
  const t = current();
  $('#mini').hidden = !t;
  const icon = audio.paused ? ICON_PLAY : ICON_PAUSE;
  $('#miniPlay').innerHTML = icon;
  $('#btnPlay').innerHTML = icon;
  $('#btnShuffle').classList.toggle('on', st.shuffle);
  $('#btnRepeat').classList.toggle('on', st.repeat !== 'off');
  $('#repeatOne').hidden = st.repeat !== 'one';
  if (!t) return;
  if (renderNow.id !== t.id) {
    renderNow.id = t.id;
    $('#miniArt').src = $('#bigArt').src = artUrl(t);
    $('#miniTitle').textContent = $('#bigTitle').textContent = t.title;
    $('#miniArtist').textContent = $('#bigArtist').textContent = artistOf(t);
    document.title = `${t.title} · ${artistOf(t)}`;
    $$('.songs li.playing').forEach((li) => li.classList.remove('playing'));
    $$(`.songs li[data-id="${t.id}"]`).forEach((li) => li.classList.add('playing'));
  }
}

$('#miniPlay').addEventListener('click', togglePlay);
$('#btnPlay').addEventListener('click', togglePlay);
$('#miniNext').addEventListener('click', () => next());
$('#btnNext').addEventListener('click', () => next());
$('#btnPrev').addEventListener('click', prev);
$('#btnShuffle').addEventListener('click', () => {
  st.shuffle = !st.shuffle;
  const cur = st.queue[st.index];
  if (st.shuffle) {
    st.base = [...st.queue];
    st.queue = shuffled(st.queue, cur);
    st.index = cur ? 0 : -1;
  } else if (st.base.length) {
    st.queue = [...st.base];
    st.index = cur ? st.queue.indexOf(cur) : -1;
  }
  saveState();
  renderNow();
  renderQueue();
  toast(st.shuffle ? 'Trộn bài: bật' : 'Trộn bài: tắt', 1200);
});
$('#btnRepeat').addEventListener('click', () => {
  st.repeat = { off: 'all', all: 'one', one: 'off' }[st.repeat];
  saveState();
  renderNow();
  toast({ off: 'Lặp: tắt', all: 'Lặp: tất cả', one: 'Lặp: 1 bài' }[st.repeat], 1200);
});
$('#miniOpen').addEventListener('click', () => { $('#player').hidden = false; document.body.style.overflow = 'hidden'; renderQueue(); });
$('#playerClose').addEventListener('click', () => { $('#player').hidden = true; document.body.style.overflow = ''; });

// ---------- Media Session: lock screen, Control Center, CarPlay Now Playing, steering wheel buttons ----------
function updateMediaSession() {
  if (!('mediaSession' in navigator)) return;
  const t = current();
  if (!t) return;
  const art = t.cover
    ? [{ src: new URL(`/cover/${t.id}`, location.href).href, sizes: '512x512', type: t.cover === 'png' ? 'image/png' : 'image/jpeg' }]
    : [{ src: new URL('/icons/icon-512.png', location.href).href, sizes: '512x512', type: 'image/png' }];
  navigator.mediaSession.metadata = new MediaMetadata({
    title: t.title, artist: artistOf(t), album: t.album || '', artwork: art,
  });
}
function updatePositionState() {
  if (!('mediaSession' in navigator)) return;
  navigator.mediaSession.playbackState = audio.paused ? 'paused' : 'playing';
  const d = audio.duration;
  if (navigator.mediaSession.setPositionState && Number.isFinite(d) && d > 0) {
    try {
      navigator.mediaSession.setPositionState({ duration: d, position: Math.min(audio.currentTime, d), playbackRate: audio.playbackRate || 1 });
    } catch {}
  }
}
if ('mediaSession' in navigator) {
  const set = (a, fn) => { try { navigator.mediaSession.setActionHandler(a, fn); } catch {} };
  set('play', () => { if (!audio.src) togglePlay(); else audio.play(); });
  set('pause', () => audio.pause());
  set('stop', () => audio.pause());
  set('previoustrack', prev);
  set('nexttrack', () => next());
  set('seekto', (d) => { if (d.seekTime != null) { audio.currentTime = d.seekTime; updatePositionState(); } });
  // Deliberately NOT registering seekbackward/seekforward: on iOS that replaces the
  // next/previous buttons (lock screen, CarPlay, steering wheel) with ±10s skip.
  set('seekbackward', null);
  set('seekforward', null);
}

// ---------- menu ----------
$('#menuBtn').addEventListener('click', (e) => { e.stopPropagation(); $('#menu').hidden = !$('#menu').hidden; });
document.addEventListener('click', () => { $('#menu').hidden = true; });
$('#menu').addEventListener('click', async (e) => {
  const act = e.target.closest('button')?.dataset.act;
  if (act === 'logout') {
    await fetch('/api/logout', { method: 'POST' });
    showLogin();
  }
  if (act === 'rescan') {
    toast('Đang quét thư viện...', 10000);
    try {
      const r = await api('/api/rescan', { method: 'POST' });
      await loadTracks();
      toast(`Xong: ${r.total} bài (+${r.added} / -${r.removed})`);
    } catch (err) { toast('Lỗi: ' + err.message); }
  }
});

// ---------- upload ----------
const drop = $('#drop');
$('#fileInput').addEventListener('change', (e) => { uploadFiles([...e.target.files]); e.target.value = ''; });
['dragenter', 'dragover'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('over'); }));
['dragleave', 'drop'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove('over'); }));
drop.addEventListener('drop', (e) => uploadFiles([...e.dataTransfer.files]));

let uploading = Promise.resolve();
function uploadFiles(files) {
  for (const f of files) {
    const li = document.createElement('li');
    li.innerHTML = `<div class="name"><span>${esc(f.name)}</span><span class="pct muted">chờ...</span></div><div class="bar"><div></div></div>`;
    $('#uploadList').prepend(li);
    // one file per request, sequential: keeps each request under proxy body limits (e.g. Cloudflare 100 MB)
    uploading = uploading.then(() => uploadOne(f, li)).catch(() => {});
  }
  uploading.then(() => loadTracks().catch(() => {}));
}
function uploadOne(file, li) {
  return new Promise((resolve) => {
    const fd = new FormData();
    fd.append('file', file, file.name);
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload');
    xhr.upload.onprogress = (e) => {
      if (!e.lengthComputable) return;
      const p = Math.round((e.loaded / e.total) * 100);
      $('.bar div', li).style.width = p + '%';
      $('.pct', li).textContent = p < 100 ? `${p}%` : 'đang xử lý...';
    };
    xhr.onload = () => {
      let d = {};
      try { d = JSON.parse(xhr.responseText); } catch {}
      const r = d.results?.[0];
      if (xhr.status === 401) { li.classList.add('fail'); $('.pct', li).textContent = 'chưa đăng nhập'; showLogin(); }
      else if (xhr.status === 413) { li.classList.add('fail'); $('.pct', li).textContent = 'file quá lớn (proxy chặn)'; }
      else if (xhr.status >= 400 || r?.error) { li.classList.add('fail'); $('.pct', li).textContent = r?.error || d.error || `lỗi ${xhr.status}`; }
      else { li.classList.add('ok'); $('.bar div', li).style.width = '100%'; $('.pct', li).textContent = '✓ xong'; }
      resolve();
    };
    xhr.onerror = () => { li.classList.add('fail'); $('.pct', li).textContent = 'lỗi mạng'; resolve(); };
    xhr.send(fd);
  });
}

// ---------- boot ----------
async function start() {
  $('#login').hidden = true;
  $('#app').hidden = false;
  loadState();
  try {
    await loadTracks();
  } catch (e) {
    if (e.message !== 'unauthorized') toast('Không tải được thư viện: ' + e.message);
    return;
  }
  // restore last track (paused) so one tap on play resumes where you left off
  if (current() && !audio.src) {
    playIndex(st.index, { autoplay: false, at: st.pos || 0 });
  }
}

window.addEventListener('pagehide', saveState);
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') saveState();
  else if (document.visibilityState === 'visible') updatePositionState();
});

fetch('/api/me').then((r) => r.json()).then((d) => (d.authed ? start() : showLogin())).catch(() => showLogin());
