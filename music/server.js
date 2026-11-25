// Dailoc Music - self-hosted music upload + streaming server
// Single-user, password protected. Files live in MUSIC_DIR (NAS share), cache in DATA_DIR.

import express from 'express';
import busboy from 'busboy';
import { parseFile, selectCover } from 'music-metadata';
import crypto from 'node:crypto';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const PORT = Number(process.env.PORT || 3000);
const MUSIC_DIR = path.resolve(process.env.MUSIC_DIR || '/music');
const DATA_DIR = path.resolve(process.env.DATA_DIR || '/data');
const UPLOAD_SUBDIR = process.env.UPLOAD_SUBDIR || 'Uploads';
const APP_PASSWORD = process.env.APP_PASSWORD || '';
const MAX_UPLOAD_MB = Number(process.env.MAX_UPLOAD_MB || 500);
const SESSION_DAYS = Number(process.env.SESSION_DAYS || 180);
const RESCAN_MINUTES = Number(process.env.RESCAN_MINUTES || 0); // 0 = no periodic rescan

if (!APP_PASSWORD) {
  console.error('FATAL: APP_PASSWORD is not set. Refusing to start without a password.');
  process.exit(1);
}

const COVER_DIR = path.join(DATA_DIR, 'covers');
const LIBRARY_FILE = path.join(DATA_DIR, 'library.json');
const SECRET_FILE = path.join(DATA_DIR, 'session.secret');
const AUDIO_EXT = new Set(['.mp3', '.m4a', '.aac', '.flac', '.wav', '.ogg', '.oga', '.opus', '.alac', '.aiff', '.aif']);
const MIME = {
  '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4', '.alac': 'audio/mp4', '.aac': 'audio/aac',
  '.flac': 'audio/flac', '.wav': 'audio/wav', '.ogg': 'audio/ogg', '.oga': 'audio/ogg',
  '.opus': 'audio/ogg', '.aiff': 'audio/aiff', '.aif': 'audio/aiff',
};

fs.mkdirSync(COVER_DIR, { recursive: true });
fs.mkdirSync(path.join(MUSIC_DIR, UPLOAD_SUBDIR), { recursive: true });

// ---------- session secret ----------
function loadSecret() {
  if (process.env.SESSION_SECRET) return process.env.SESSION_SECRET;
  try {
    return fs.readFileSync(SECRET_FILE, 'utf8').trim();
  } catch {
    const s = crypto.randomBytes(32).toString('hex');
    fs.writeFileSync(SECRET_FILE, s, { mode: 0o600 });
    return s;
  }
}
const SECRET = loadSecret();
const hmac = (v) => crypto.createHmac('sha256', SECRET).update(v).digest('base64url');

// Track id: HMAC of relative path -> stable across rescans, not guessable from the filename.
const trackId = (rel) => hmac('track:' + rel).slice(0, 22);

// ---------- library ----------
let library = { tracks: [] };
let byId = new Map();
let scanning = null;

function loadLibrary() {
  try {
    library = JSON.parse(fs.readFileSync(LIBRARY_FILE, 'utf8'));
    if (!Array.isArray(library.tracks)) library = { tracks: [] };
  } catch {
    library = { tracks: [] };
  }
  reindex();
}
function reindex() {
  byId = new Map(library.tracks.map((t) => [t.id, t]));
}
async function saveLibrary() {
  const tmp = LIBRARY_FILE + '.tmp';
  await fsp.writeFile(tmp, JSON.stringify(library));
  await fsp.rename(tmp, LIBRARY_FILE);
}

async function* walk(dir) {
  let entries;
  try {
    entries = await fsp.readdir(dir, { withFileTypes: true });
  } catch (e) {
    console.warn('Cannot read dir', dir, e.code);
    return;
  }
  for (const e of entries) {
    if (e.name.startsWith('.') || e.name.startsWith('@') || e.name === '#recycle') continue; // skip hidden + Synology system dirs
    const full = path.join(dir, e.name);
    if (e.isDirectory()) yield* walk(full);
    else if (e.isFile() && AUDIO_EXT.has(path.extname(e.name).toLowerCase())) yield full;
  }
}

async function readTrack(full, stat) {
  const rel = path.relative(MUSIC_DIR, full).split(path.sep).join('/');
  const id = trackId(rel);
  const base = path.basename(full, path.extname(full)).replace(/ \(\d+\)$/, ''); // drop " (2)" added on duplicate upload
  const t = {
    id, rel, size: stat.size, mtime: stat.mtimeMs,
    title: base, artist: '', album: '', albumArtist: '', trackNo: 0, discNo: 0, year: 0,
    duration: 0, cover: false, addedAt: Date.now(),
  };
  try {
    const mm = await parseFile(full, { duration: true, skipCovers: false });
    const c = mm.common;
    t.title = c.title || base;
    t.artist = c.artist || (c.artists && c.artists.join(', ')) || '';
    t.album = c.album || '';
    t.albumArtist = c.albumartist || '';
    t.trackNo = c.track?.no || 0;
    t.discNo = c.disk?.no || 0;
    t.year = c.year || 0;
    t.duration = Math.round(mm.format.duration || 0);
    const pic = selectCover(c.picture);
    if (pic && pic.data?.length) {
      const ext = (pic.format || '').includes('png') ? 'png' : 'jpg';
      await fsp.writeFile(path.join(COVER_DIR, `${id}.${ext}`), pic.data);
      t.cover = ext;
    }
  } catch (e) {
    console.warn('Metadata read failed for', rel, '-', e.message);
  }
  // "Artist - Title" filename fallback when tags are missing
  if (!t.artist && t.title === base && base.includes(' - ')) {
    const [a, ...rest] = base.split(' - ');
    t.artist = a.trim();
    t.title = rest.join(' - ').trim();
  }
  return t;
}

async function scan() {
  if (scanning) return scanning;
  scanning = (async () => {
    const started = Date.now();
    const old = new Map(library.tracks.map((t) => [t.rel, t]));
    const next = [];
    let added = 0;
    for await (const full of walk(MUSIC_DIR)) {
      let stat;
      try { stat = await fsp.stat(full); } catch { continue; }
      const rel = path.relative(MUSIC_DIR, full).split(path.sep).join('/');
      const prev = old.get(rel);
      if (prev && prev.size === stat.size && prev.mtime === stat.mtimeMs) {
        next.push(prev);
      } else {
        const t = await readTrack(full, stat);
        if (prev) t.addedAt = prev.addedAt;
        else added++;
        next.push(t);
      }
    }
    const keep = new Set(next.map((t) => t.id));
    const removed = library.tracks.filter((t) => !keep.has(t.id));
    for (const t of removed) if (t.cover) fsp.rm(path.join(COVER_DIR, `${t.id}.${t.cover}`), { force: true }).catch(() => {});
    library = { tracks: next, scannedAt: Date.now() };
    reindex();
    await saveLibrary();
    console.log(`Scan done: ${next.length} tracks (+${added}, -${removed.length}) in ${Date.now() - started} ms`);
    return { total: next.length, added, removed: removed.length };
  })().finally(() => { scanning = null; });
  return scanning;
}

async function addFile(full) {
  const stat = await fsp.stat(full);
  const t = await readTrack(full, stat);
  library.tracks = library.tracks.filter((x) => x.id !== t.id);
  library.tracks.push(t);
  reindex();
  await saveLibrary();
  return t;
}

// ---------- auth ----------
function makeToken() {
  const payload = `v1.${Date.now()}`;
  return `${payload}.${hmac(payload)}`;
}
function validToken(tok) {
  if (!tok) return false;
  const i = tok.lastIndexOf('.');
  if (i < 0) return false;
  const payload = tok.slice(0, i);
  const sig = Buffer.from(tok.slice(i + 1));
  const expect = Buffer.from(hmac(payload));
  if (sig.length !== expect.length || !crypto.timingSafeEqual(sig, expect)) return false;
  const ts = Number(payload.split('.')[1]);
  return Number.isFinite(ts) && Date.now() - ts < SESSION_DAYS * 864e5;
}
function getCookie(req, name) {
  const h = req.headers.cookie || '';
  for (const part of h.split(';')) {
    const [k, ...v] = part.trim().split('=');
    if (k === name) return decodeURIComponent(v.join('='));
  }
  return null;
}
function authed(req) {
  return validToken(getCookie(req, 'sid'));
}
function requireAuth(req, res, next) {
  if (authed(req)) return next();
  res.status(401).json({ error: 'unauthorized' });
}

// naive in-memory login rate limit: 10 attempts / 15 min per IP
const attempts = new Map();
function rateLimited(ip) {
  const now = Date.now();
  const a = (attempts.get(ip) || []).filter((t) => now - t < 15 * 60e3);
  attempts.set(ip, a);
  return a.length >= 10;
}

// ---------- app ----------
const app = express();
app.set('trust proxy', process.env.TRUST_PROXY || 'loopback, linklocal, uniquelocal');
app.disable('x-powered-by');
app.use((req, res, next) => {
  res.set('X-Content-Type-Options', 'nosniff');
  res.set('Referrer-Policy', 'same-origin');
  next();
});

app.get('/healthz', (req, res) => res.json({ ok: true, tracks: library.tracks.length }));

app.post('/api/login', express.json({ limit: '4kb' }), (req, res) => {
  const ip = req.ip;
  if (rateLimited(ip)) return res.status(429).json({ error: 'Too many attempts, try again later' });
  const pw = Buffer.from(String(req.body?.password || ''));
  const real = Buffer.from(APP_PASSWORD);
  const ok = pw.length === real.length && crypto.timingSafeEqual(pw, real);
  if (!ok) {
    attempts.get(ip).push(Date.now());
    return res.status(401).json({ error: 'Wrong password' });
  }
  attempts.delete(ip);
  res.cookie('sid', makeToken(), {
    httpOnly: true, sameSite: 'lax', secure: req.secure, maxAge: SESSION_DAYS * 864e5, path: '/',
  });
  res.json({ ok: true });
});

app.post('/api/logout', (req, res) => {
  res.clearCookie('sid', { path: '/' });
  res.json({ ok: true });
});

app.get('/api/me', (req, res) => res.json({ authed: authed(req) }));

app.get('/api/tracks', requireAuth, (req, res) => {
  res.set('Cache-Control', 'no-store');
  res.json({
    scannedAt: library.scannedAt || 0,
    tracks: library.tracks.map(({ mtime, ...t }) => t),
  });
});

app.post('/api/rescan', requireAuth, async (req, res) => {
  try { res.json(await scan()); } catch (e) { res.status(500).json({ error: e.message }); }
});

app.delete('/api/tracks/:id', requireAuth, async (req, res) => {
  const t = byId.get(req.params.id);
  if (!t) return res.status(404).json({ error: 'not found' });
  const full = path.join(MUSIC_DIR, t.rel);
  if (!full.startsWith(MUSIC_DIR + path.sep)) return res.status(400).json({ error: 'bad path' });
  try {
    await fsp.rm(full, { force: true });
    if (t.cover) await fsp.rm(path.join(COVER_DIR, `${t.id}.${t.cover}`), { force: true });
    library.tracks = library.tracks.filter((x) => x.id !== t.id);
    reindex();
    await saveLibrary();
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

function safeName(name) {
  let n = path.basename(String(name || '')).normalize('NFC');
  n = n.replace(/[\u0000-\u001f\u007f<>:"/\\|?*]/g, '_').replace(/^\.+/, '').trim();
  if (n.length > 200) {
    const ext = path.extname(n);
    n = n.slice(0, 200 - ext.length) + ext;
  }
  return n || 'track';
}
async function uniquePath(dir, name) {
  const ext = path.extname(name);
  const stem = name.slice(0, name.length - ext.length);
  let candidate = path.join(dir, name);
  for (let i = 2; ; i++) {
    try { await fsp.access(candidate); } catch { return candidate; }
    candidate = path.join(dir, `${stem} (${i})${ext}`);
  }
}

app.post('/api/upload', requireAuth, (req, res) => {
  let bb;
  try {
    bb = busboy({
      headers: req.headers,
      defParamCharset: 'utf8',
      limits: { fileSize: MAX_UPLOAD_MB * 1024 * 1024, files: 20 },
    });
  } catch {
    return res.status(400).json({ error: 'Expected multipart/form-data' });
  }
  const dir = path.join(MUSIC_DIR, UPLOAD_SUBDIR);
  const jobs = [];
  const results = [];
  bb.on('file', (field, stream, info) => {
    const name = safeName(info.filename);
    const ext = path.extname(name).toLowerCase();
    if (!AUDIO_EXT.has(ext)) {
      stream.resume();
      results.push({ name, error: 'Unsupported file type' });
      return;
    }
    jobs.push((async () => {
      const tmp = path.join(dir, `.upload-${crypto.randomBytes(6).toString('hex')}`);
      try {
        await new Promise((resolve, reject) => {
          const out = fs.createWriteStream(tmp);
          stream.on('limit', () => { out.destroy(); reject(new Error(`File larger than ${MAX_UPLOAD_MB} MB`)); });
          stream.on('error', reject);
          out.on('error', reject);
          out.on('finish', resolve);
          stream.pipe(out);
        });
        if (stream.truncated) throw new Error(`File larger than ${MAX_UPLOAD_MB} MB`);
        const final = await uniquePath(dir, name);
        await fsp.rename(tmp, final);
        const t = await addFile(final);
        results.push({ name, id: t.id, title: t.title, artist: t.artist });
      } catch (e) {
        stream.resume();
        await fsp.rm(tmp, { force: true }).catch(() => {});
        results.push({ name, error: e.message });
      }
    })());
  });
  bb.on('error', (e) => {
    if (!res.headersSent) res.status(400).json({ error: e.message });
  });
  bb.on('close', async () => {
    await Promise.all(jobs);
    if (res.headersSent) return;
    const failed = results.filter((r) => r.error);
    res.status(failed.length && failed.length === results.length ? 400 : 200).json({ results });
  });
  req.on('aborted', () => bb.destroy?.());
  req.pipe(bb);
});

// Audio streaming with HTTP Range (sendFile handles 206 / Accept-Ranges).
app.get('/stream/:id', requireAuth, (req, res) => {
  const t = byId.get(req.params.id);
  if (!t) return res.sendStatus(404);
  const full = path.join(MUSIC_DIR, t.rel);
  const type = MIME[path.extname(full).toLowerCase()] || 'application/octet-stream';
  res.sendFile(full, {
    headers: { 'Content-Type': type, 'Cache-Control': 'private, max-age=86400' },
    acceptRanges: true,
    dotfiles: 'allow',
  }, (err) => {
    if (err && !res.headersSent) res.sendStatus(err.status || 500);
  });
});

// Covers are served without the cookie check on purpose: iOS fetches Now Playing / CarPlay
// artwork outside the page context, and the id is an HMAC so it can't be guessed.
app.get('/cover/:id', (req, res) => {
  const t = byId.get(req.params.id);
  if (!t || !t.cover) return res.sendStatus(404);
  res.sendFile(path.join(COVER_DIR, `${t.id}.${t.cover}`), {
    headers: { 'Cache-Control': 'public, max-age=604800' },
  });
});

app.use(express.static(path.join(__dirname, 'public'), {
  setHeaders(res, file) {
    if (file.endsWith('.html') || file.endsWith('.webmanifest') || file.endsWith('sw.js')) {
      res.set('Cache-Control', 'no-cache');
    }
  },
}));

loadLibrary();
app.listen(PORT, () => {
  console.log(`Dailoc Music listening on :${PORT} | music=${MUSIC_DIR} data=${DATA_DIR}`);
  scan().catch((e) => console.error('Initial scan failed', e));
  if (RESCAN_MINUTES > 0) setInterval(() => scan().catch(() => {}), RESCAN_MINUTES * 60e3);
});
