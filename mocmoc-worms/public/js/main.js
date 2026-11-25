import {
  TICK_MS, SPACING, C2S, S2C, FLAG_BOOST, FLAG_FULL, SKINS, FOOD_COLORS,
} from './shared.js';

const TAU = Math.PI * 2;
const INTERP_DELAY = 110; // ms behind server time we render at
const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------- storage
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode etc. */ } },
};

// ---------------------------------------------------------------- state
const S = {
  ws: null,
  connected: false,
  reconnectDelay: 1000,
  R: 3000,
  myId: 0,
  alive: false,
  wantPlay: false,
  score: 0,
  snakes: new Map(),     // id -> snake
  dying: [],             // fading snakes
  meta: new Map(),       // id -> {name, skin}
  food: new Map(),       // id -> food
  eatAnims: [],
  camHist: [],
  offset: null,          // performance.now() - serverTime
  lb: null,
  feed: [],
  ping: 0,
  fps: 0,
};

const view = { w: 0, h: 0, dpr: 1, scale: 1, camX: 0, camY: 0 };
const input = { angle: 0, boost: false, keyBoost: false, mouseBoost: false, touchBoost: false, btnBoost: false,
  keyTurn: 0, lastSent: 0, sentAngle: 99, sentBoost: false, sentHW: 0, sentHH: 0 };

// ---------------------------------------------------------------- canvas & sprites
const canvas = $('game');
const ctx = canvas.getContext('2d', { alpha: false });

function makeCanvas(w, h) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  return c;
}

function shade(hex, f) {
  const n = parseInt(hex.slice(1), 16);
  let r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  if (f >= 0) { r += (255 - r) * f; g += (255 - g) * f; b += (255 - b) * f; }
  else { r *= 1 + f; g *= 1 + f; b *= 1 + f; }
  return `rgb(${r | 0},${g | 0},${b | 0})`;
}

const BODY_SPRITE = 96;
function bodySprite(color) {
  const c = makeCanvas(BODY_SPRITE, BODY_SPRITE), g = c.getContext('2d');
  const m = BODY_SPRITE / 2, r = m - 2;
  const grad = g.createRadialGradient(m - r * 0.35, m - r * 0.35, r * 0.1, m, m, r);
  grad.addColorStop(0, shade(color, 0.45));
  grad.addColorStop(0.55, color);
  grad.addColorStop(1, shade(color, -0.45));
  g.fillStyle = grad;
  g.beginPath(); g.arc(m, m, r, 0, TAU); g.fill();
  return c;
}
const skinSprites = SKINS.map(([a, b]) => [bodySprite(a), bodySprite(b)]);

const glowSprite = (() => {
  const s = 64, c = makeCanvas(s, s), g = c.getContext('2d');
  const grad = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  grad.addColorStop(0, 'rgba(255,255,255,0.55)');
  grad.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grad; g.fillRect(0, 0, s, s);
  return c;
})();

const FOOD_SPRITE = 64; // core radius = 20% of size
const foodSprites = FOOD_COLORS.map((col) => {
  const s = FOOD_SPRITE, c = makeCanvas(s, s), g = c.getContext('2d');
  const grad = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  grad.addColorStop(0, col);
  grad.addColorStop(0.32, col);
  grad.addColorStop(0.42, shade(col, -0.1).replace('rgb', 'rgba').replace(')', ',0.35)'));
  grad.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = grad; g.fillRect(0, 0, s, s);
  g.fillStyle = 'rgba(255,255,255,0.7)';
  g.beginPath(); g.arc(s / 2 - s * 0.06, s / 2 - s * 0.06, s * 0.06, 0, TAU); g.fill();
  return c;
});

let bgPattern = null;
function makeBg() {
  const side = 30, h = 52, w = side * 3, k = 2; // tile rendered at 2x for crispness
  const c = makeCanvas(w * k, h * k), g = c.getContext('2d');
  g.scale(k, k);
  g.fillStyle = '#10172b';
  g.fillRect(0, 0, w, h);
  g.strokeStyle = 'rgba(120,140,200,0.10)';
  g.lineWidth = 2;
  const hex = (cx, cy) => {
    g.beginPath();
    for (let i = 0; i < 6; i++) {
      const a = (Math.PI / 3) * i;
      const x = cx + Math.cos(a) * side, y = cy + Math.sin(a) * (h / 2) / Math.sin(Math.PI / 3);
      if (i === 0) g.moveTo(x, y); else g.lineTo(x, y);
    }
    g.closePath(); g.stroke();
  };
  hex(0, 0); hex(0, h); hex(side * 1.5, h / 2); hex(w, 0); hex(w, h);
  bgPattern = ctx.createPattern(c, 'repeat');
  if (bgPattern.setTransform && typeof DOMMatrix !== 'undefined') bgPattern.setTransform(new DOMMatrix().scale(1 / k));
}
makeBg();

function resize() {
  view.dpr = Math.min(2, window.devicePixelRatio || 1);
  view.w = window.innerWidth;
  view.h = window.innerHeight;
  canvas.width = Math.round(view.w * view.dpr);
  canvas.height = Math.round(view.h * view.dpr);
}
window.addEventListener('resize', resize);
resize();

// ---------------------------------------------------------------- networking
function wsUrl() {
  const u = new URL('ws', location.href);
  u.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return u.href;
}

function resetWorld() {
  S.snakes.clear(); S.dying.length = 0; S.food.clear(); S.eatAnims.length = 0;
  S.camHist.length = 0; S.offset = null; S.meta.clear();
  S.alive = false; S.myId = 0;
}

function connect() {
  showConn('Đang kết nối…');
  const ws = new WebSocket(wsUrl());
  ws.binaryType = 'arraybuffer';
  S.ws = ws;
  ws.onopen = () => {
    S.connected = true;
    S.reconnectDelay = 1000;
    hideConn();
    $('play').disabled = false;
    $('play').textContent = 'Chơi';
  };
  ws.onmessage = (ev) => {
    if (typeof ev.data === 'string') onJson(JSON.parse(ev.data));
    else onBinary(new DataView(ev.data));
  };
  ws.onclose = () => {
    S.connected = false;
    S.wantPlay = false;
    $('play').disabled = true;
    $('play').textContent = 'Đang kết nối…';
    const wasAlive = S.alive;
    resetWorld();
    $('hud').hidden = true;
    if (wasAlive) { $('dead').hidden = true; $('menu').hidden = false; }
    showConn('Mất kết nối, đang thử lại…');
    setTimeout(connect, S.reconnectDelay);
    S.reconnectDelay = Math.min(10000, S.reconnectDelay * 2);
  };
  ws.onerror = () => {};
}

function send(buf) {
  if (S.ws && S.ws.readyState === 1) S.ws.send(buf);
}

function sendJoin() {
  const name = $('name').value.trim();
  store.set('mm_name', name);
  store.set('mm_skin', String(selectedSkin));
  const bytes = new TextEncoder().encode(name).slice(0, 60);
  const buf = new Uint8Array(2 + bytes.length);
  buf[0] = C2S.JOIN; buf[1] = selectedSkin;
  buf.set(bytes, 2);
  send(buf);
}

function sendInput(force) {
  const now = performance.now();
  const hw = Math.ceil(view.w / 2 / view.scale), hh = Math.ceil(view.h / 2 / view.scale);
  const boost = input.keyBoost || input.mouseBoost || input.touchBoost || input.btnBoost;
  const changed = Math.abs(input.angle - input.sentAngle) > 0.004 || boost !== input.sentBoost
    || Math.abs(hw - input.sentHW) > 20 || Math.abs(hh - input.sentHH) > 20;
  if (!force && !(changed && now - input.lastSent > 40) && now - input.lastSent < 1000) return;
  const b = new DataView(new ArrayBuffer(8));
  b.setUint8(0, C2S.INPUT);
  let a = (input.angle + Math.PI) / TAU;
  a -= Math.floor(a);
  b.setUint16(1, Math.min(65535, Math.round(a * 65536)), true);
  b.setUint8(3, boost ? 1 : 0);
  b.setUint16(4, Math.min(65535, hw), true);
  b.setUint16(6, Math.min(65535, hh), true);
  send(b.buffer);
  input.lastSent = now; input.sentAngle = input.angle; input.sentBoost = boost;
  input.sentHW = hw; input.sentHH = hh;
}

setInterval(() => {
  if (S.ws && S.ws.readyState === 1) S.ws.send(JSON.stringify({ t: 'ping', c: performance.now() }));
}, 2000);

function onJson(m) {
  switch (m.t) {
    case 'welcome':
      S.R = m.R;
      for (const [id, name, skin] of m.players) S.meta.set(id, { name, skin });
      if (S.wantPlay) sendJoin();
      break;
    case 'ev':
      for (const e of m.e) {
        if (e[0] === 's') S.meta.set(e[1], { name: e[2], skin: e[3] });
        else if (e[0] === 'd') {
          const who = S.meta.get(e[1]);
          if (e[2] && who) addFeed(e[2], who.name);
          setTimeout(() => S.meta.delete(e[1]), 2000);
        }
      }
      break;
    case 'you':
      S.myId = m.id;
      S.alive = true;
      $('menu').hidden = true;
      $('dead').hidden = true;
      $('hud').hidden = false;
      sendInput(true);
      break;
    case 'dead':
      S.alive = false;
      S.wantPlay = false;
      showDead(m);
      break;
    case 'full':
      S.wantPlay = false;
      $('online').textContent = 'Server đang đầy, thử lại sau một chút.';
      $('menu').hidden = false;
      break;
    case 'lb':
      S.lb = m;
      updateBoard();
      break;
    case 'pong':
      S.ping = Math.round(performance.now() - m.c);
      break;
  }
}

function updateOffset(sample) {
  if (S.offset === null || Math.abs(sample - S.offset) > 1500) S.offset = sample;
  else if (sample < S.offset) S.offset += (sample - S.offset) * 0.2; // arrived earlier: adapt fast
  else S.offset += (sample - S.offset) * 0.02;                       // arrived later: adapt slowly
}

function onBinary(dv) {
  if (dv.getUint8(0) !== S2C.STATE) return;
  let o = 1;
  const tick = dv.getUint32(o, true); o += 4;
  S.score = dv.getUint32(o, true); o += 4;
  const cx = dv.getInt16(o, true), cy = dv.getInt16(o + 2, true); o += 4;
  const t = tick * TICK_MS;
  const now = performance.now();
  updateOffset(now - t);
  S.camHist.push({ t, x: cx, y: cy });
  if (S.camHist.length > 12) S.camHist.shift();

  const n = dv.getUint16(o, true); o += 2;
  const seen = new Set();
  for (let i = 0; i < n; i++) {
    const id = dv.getUint16(o, true);
    const flags = dv.getUint8(o + 2);
    const hx = dv.getInt16(o + 3, true), hy = dv.getInt16(o + 5, true);
    const a = (dv.getUint8(o + 7) / 256) * TAU - Math.PI;
    const r = dv.getUint8(o + 8) / 4;
    const len = dv.getUint16(o + 9, true);
    o += 11;
    let full = null;
    if (flags & FLAG_FULL) {
      const m = dv.getUint16(o, true); o += 2;
      const xs = new Array(m), ys = new Array(m);
      for (let k = 0; k < m; k++) { xs[k] = dv.getInt16(o, true); ys[k] = dv.getInt16(o + 2, true); o += 4; }
      full = { xs, ys }; // newest first
    }
    let s = S.snakes.get(id);
    if (!s) {
      s = { id, hist: [], r, rDraw: r, len, boost: false, px: [], py: [], tail: 0, pending: null, hx, hy, ha: a, lastRealT: 0 };
      S.snakes.set(id, s);
    }
    seen.add(id);
    s.hist.push({ t, x: hx, y: hy, a });
    if (s.hist.length > 12) s.hist.shift();
    s.r = r; s.len = len; s.boost = (flags & FLAG_BOOST) !== 0;
    if (full) s.pending = full;
  }
  for (const [id, s] of S.snakes) {
    if (!seen.has(id)) { s.fadeAt = now; S.dying.push(s); S.snakes.delete(id); }
  }

  const na = dv.getUint16(o, true); o += 2;
  for (let i = 0; i < na; i++) {
    const id = dv.getUint32(o, true);
    S.food.set(id, {
      x: dv.getInt16(o + 4, true), y: dv.getInt16(o + 6, true),
      v: dv.getUint8(o + 8), c: dv.getUint8(o + 9) % FOOD_COLORS.length,
      born: now, ph: (id % 100) * 0.37,
    });
    o += 10;
  }
  const nr = dv.getUint16(o, true); o += 2;
  for (let i = 0; i < nr; i++) {
    const id = dv.getUint32(o, true), eater = dv.getUint16(o + 4, true);
    o += 6;
    const f = S.food.get(id);
    if (!f) continue;
    S.food.delete(id);
    if (eater !== 0xffff && S.snakes.has(eater) && S.eatAnims.length < 300) S.eatAnims.push({ f, eater, t0: now });
  }
}

// ---------------------------------------------------------------- interpolation
function sample(hist, t, out) {
  const n = hist.length;
  if (n === 1 || t <= hist[0].t) { const h = hist[0]; out.x = h.x; out.y = h.y; out.a = h.a; out.real = true; return out; }
  const last = hist[n - 1];
  if (t >= last.t) {
    const prev = hist[n - 2], span = last.t - prev.t || TICK_MS;
    const dt = Math.min(t - last.t, 120);
    out.x = last.x + ((last.x - prev.x) / span) * dt;
    out.y = last.y + ((last.y - prev.y) / span) * dt;
    out.a = last.a; out.real = false;
    return out;
  }
  for (let i = n - 1; i > 0; i--) {
    const a = hist[i - 1];
    if (a.t <= t) {
      const b = hist[i], k = (t - a.t) / (b.t - a.t || 1);
      out.x = a.x + (b.x - a.x) * k;
      out.y = a.y + (b.y - a.y) * k;
      let d = b.a - a.a;
      if (d > Math.PI) d -= TAU; else if (d < -Math.PI) d += TAU;
      out.a = a.a + d * k; out.real = true;
      return out;
    }
  }
  return out;
}

const tmp = { x: 0, y: 0, a: 0, real: true };
let resyncAsked = 0;

function updateSnake(s, rt) {
  sample(s.hist, rt, tmp);
  s.hx = tmp.x; s.hy = tmp.y; s.ha = tmp.a;
  s.rDraw += (s.r - s.rDraw) * 0.15;

  if (s.pending) {
    // server body is newest-first and ends at the *current* server head, which is ahead of
    // where we render. Drop the leading points that are in front of our rendered head.
    const { xs, ys } = s.pending;
    s.pending = null;
    let best = 0, bd = Infinity;
    const lim = Math.min(xs.length, 40);
    for (let k = 0; k < lim; k++) {
      const d = (xs[k] - s.hx) ** 2 + (ys[k] - s.hy) ** 2;
      if (d < bd) { bd = d; best = k; }
    }
    s.px = []; s.py = []; s.tail = 0;
    for (let k = xs.length - 1; k >= best; k--) { s.px.push(xs[k]); s.py.push(ys[k]); }
    if (s.px.length === 0) { s.px.push(s.hx); s.py.push(s.hy); }
  }
  if (!tmp.real) return; // don't bake extrapolated positions into the body
  let n = s.px.length - 1;
  let lx = s.px[n], ly = s.py[n];
  let dx = s.hx - lx, dy = s.hy - ly, d = Math.hypot(dx, dy);
  if (d > 400 && s.id === S.myId && performance.now() - resyncAsked > 2000) {
    // big gap (tab was in background): ask the server for full bodies again
    resyncAsked = performance.now();
    S.food.clear();
    send(new Uint8Array([C2S.RESYNC]));
  }
  while (d >= SPACING) {
    lx += (dx / d) * SPACING; ly += (dy / d) * SPACING;
    s.px.push(lx); s.py.push(ly);
    dx = s.hx - lx; dy = s.hy - ly; d = Math.hypot(dx, dy);
  }
  const maxPts = Math.ceil(s.len / SPACING) + 2;
  if (s.px.length - s.tail > maxPts) s.tail = s.px.length - maxPts;
  if (s.tail > 256) { s.px.splice(0, s.tail); s.py.splice(0, s.tail); s.tail = 0; }
}

// ---------------------------------------------------------------- drawing
const circ = []; // reused buffer: x, y, r, stripe

function drawSnake(s, alpha, isMe) {
  const meta = S.meta.get(s.id);
  const skin = meta ? meta.skin % SKINS.length : 0;
  const sprites = skinSprites[skin];
  const r = s.rDraw;
  const step = Math.max(2.5, r * 0.42);
  const total = s.len;

  // walk from head backwards along [head, newest ... oldest]
  circ.length = 0;
  let ax = s.hx, ay = s.hy, dist = 0, nextAt = 0, k = 0;
  const taperFrom = total * 0.82;
  const pushC = (x, y) => {
    const tr = nextAt > taperFrom ? 1 - ((nextAt - taperFrom) / (total - taperFrom)) * 0.45 : 1;
    circ.push(x, y, r * tr, (k >> 2) & 1);
    k++;
    nextAt += step;
  };
  pushC(ax, ay);
  for (let i = s.px.length - 1; i >= s.tail && nextAt <= total; i--) {
    const bx = s.px[i], by = s.py[i];
    const seg = Math.hypot(bx - ax, by - ay);
    while (seg > 0 && nextAt <= dist + seg && nextAt <= total) {
      const f = (nextAt - dist) / seg;
      pushC(ax + (bx - ax) * f, ay + (by - ay) * f);
    }
    dist += seg; ax = bx; ay = by;
  }

  const vx0 = view.camX - view.w / 2 / view.scale - 60, vx1 = view.camX + view.w / 2 / view.scale + 60;
  const vy0 = view.camY - view.h / 2 / view.scale - 60, vy1 = view.camY + view.h / 2 / view.scale + 60;
  ctx.globalAlpha = alpha;
  if (s.boost) {
    ctx.globalAlpha = alpha * (0.55 + 0.25 * Math.sin(performance.now() / 70));
    for (let i = circ.length - 4; i >= 0; i -= 8) {
      const x = circ[i], y = circ[i + 1], cr = circ[i + 2] * 2.1;
      if (x < vx0 || x > vx1 || y < vy0 || y > vy1) continue;
      ctx.drawImage(glowSprite, x - cr, y - cr, cr * 2, cr * 2);
    }
    ctx.globalAlpha = alpha;
  }
  const sc = BODY_SPRITE / (BODY_SPRITE - 4);
  for (let i = circ.length - 4; i >= 0; i -= 4) {
    const x = circ[i], y = circ[i + 1], cr = circ[i + 2] * sc;
    if (x < vx0 || x > vx1 || y < vy0 || y > vy1) continue;
    ctx.drawImage(sprites[circ[i + 3]], x - cr, y - cr, cr * 2, cr * 2);
  }

  // eyes
  const a = s.ha, ca = Math.cos(a), sa = Math.sin(a);
  let look = a;
  if (isMe) look = input.angle;
  const er = r * 0.34, pr = r * 0.19;
  for (const side of [-1, 1]) {
    const ex = s.hx + ca * r * 0.38 - sa * r * 0.48 * side;
    const ey = s.hy + sa * r * 0.38 + ca * r * 0.48 * side;
    ctx.fillStyle = '#fff';
    ctx.beginPath(); ctx.arc(ex, ey, er, 0, TAU); ctx.fill();
    ctx.fillStyle = '#141824';
    ctx.beginPath(); ctx.arc(ex + Math.cos(look) * er * 0.4, ey + Math.sin(look) * er * 0.4, pr, 0, TAU); ctx.fill();
  }
  ctx.globalAlpha = 1;
}

function drawFood(now) {
  const vx0 = view.camX - view.w / 2 / view.scale - 30, vx1 = view.camX + view.w / 2 / view.scale + 30;
  const vy0 = view.camY - view.h / 2 / view.scale - 30, vy1 = view.camY + view.h / 2 / view.scale + 30;
  const t = now / 1000;
  for (const f of S.food.values()) {
    if (f.x < vx0 || f.x > vx1 || f.y < vy0 || f.y > vy1) continue;
    const pop = Math.min(1, (now - f.born) / 250);
    const rr = Math.min(22, 4 + Math.sqrt(f.v) * 2.6) * (1 + 0.1 * Math.sin(t * 3 + f.ph)) * pop;
    const d = rr * 5;
    ctx.drawImage(foodSprites[f.c], f.x - d / 2, f.y - d / 2, d, d);
  }
  // food flying into mouths
  for (let i = S.eatAnims.length - 1; i >= 0; i--) {
    const e = S.eatAnims[i];
    const k = (now - e.t0) / 160;
    const s = S.snakes.get(e.eater);
    if (k >= 1 || !s) { S.eatAnims.splice(i, 1); continue; }
    const x = e.f.x + (s.hx - e.f.x) * k, y = e.f.y + (s.hy - e.f.y) * k;
    const rr = Math.min(22, 4 + Math.sqrt(e.f.v) * 2.6) * (1 - k * 0.7), d = rr * 5;
    ctx.drawImage(foodSprites[e.f.c], x - d / 2, y - d / 2, d, d);
  }
}

function drawWorld() {
  const { w, h, dpr, scale } = view;
  const R = S.R;
  ctx.setTransform(dpr * scale, 0, 0, dpr * scale, (w / 2 - view.camX * scale) * dpr, (h / 2 - view.camY * scale) * dpr);
  const x0 = view.camX - w / 2 / scale, y0 = view.camY - h / 2 / scale;
  ctx.fillStyle = bgPattern;
  ctx.fillRect(x0, y0, w / scale, h / scale);
  // outside of the world
  ctx.fillStyle = 'rgba(120, 10, 30, 0.45)';
  ctx.beginPath();
  ctx.rect(x0, y0, w / scale, h / scale);
  ctx.arc(0, 0, R, 0, TAU, true);
  ctx.fill('evenodd');
  ctx.strokeStyle = 'rgba(255, 70, 90, 0.8)';
  ctx.lineWidth = 6;
  ctx.beginPath(); ctx.arc(0, 0, R, 0, TAU); ctx.stroke();
}

function drawNames() {
  const { dpr, scale } = view;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.font = '600 12px system-ui, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  for (const s of S.snakes.values()) {
    if (s.id === S.myId) continue;
    const meta = S.meta.get(s.id);
    if (!meta) continue;
    const sx = (s.hx - view.camX) * scale + view.w / 2;
    const sy = (s.hy - view.camY) * scale + view.h / 2 + s.rDraw * scale + 6;
    if (sx < -100 || sx > view.w + 100 || sy < -50 || sy > view.h + 50) continue;
    ctx.fillStyle = 'rgba(0,0,0,0.5)';
    ctx.fillText(meta.name, sx + 1, sy + 1);
    ctx.fillStyle = 'rgba(255,255,255,0.8)';
    ctx.fillText(meta.name, sx, sy);
  }
}

function drawMinimap() {
  const { dpr, w, h } = view;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const rad = w < 600 ? 44 : 60;
  const cx = w - rad - 14, cy = h - rad - 14;
  ctx.fillStyle = 'rgba(0,0,0,0.35)';
  ctx.beginPath(); ctx.arc(cx, cy, rad, 0, TAU); ctx.fill();
  ctx.strokeStyle = 'rgba(255,255,255,0.25)';
  ctx.lineWidth = 1;
  ctx.stroke();
  if (S.lb && S.lb.mm) {
    const mm = S.lb.mm;
    ctx.fillStyle = 'rgba(255,255,255,0.45)';
    for (let i = 0; i < mm.length; i += 3) {
      const x = cx + (mm[i] / 100 - 1) * rad, y = cy + (mm[i + 1] / 100 - 1) * rad;
      const r = 0.8 + mm[i + 2] * 0.35;
      ctx.fillRect(x - r, y - r, r * 2, r * 2);
    }
  }
  if (S.alive) {
    ctx.fillStyle = '#7dff6b';
    ctx.beginPath();
    ctx.arc(cx + (view.camX / S.R) * rad, cy + (view.camY / S.R) * rad, 3, 0, TAU);
    ctx.fill();
  }
}

// ---------------------------------------------------------------- main loop
let lastFrame = performance.now(), frames = 0, fpsT = 0;

function frame(now) {
  requestAnimationFrame(frame);
  const dt = Math.min(0.1, (now - lastFrame) / 1000);
  lastFrame = now;
  frames++;
  if (now - fpsT > 1000) { S.fps = frames; frames = 0; fpsT = now; updateNet(); }

  const rt = S.offset === null ? 0 : now - S.offset - INTERP_DELAY;
  for (const s of S.snakes.values()) updateSnake(s, rt);

  const me = S.alive ? S.snakes.get(S.myId) : null;
  if (me) { view.camX = me.hx; view.camY = me.hy; }
  else if (S.camHist.length) { sample(S.camHist, rt, tmp); view.camX = tmp.x; view.camY = tmp.y; }

  // zoom: screen size and own radius
  const base = Math.hypot(view.w, view.h) / 2000;
  const r = me ? me.rDraw : 14;
  const z = Math.max(0.45, Math.min(1, Math.pow(14 / r, 0.55)));
  const target = base * (me ? z : 0.85);
  view.scale += (target - view.scale) * Math.min(1, dt * 3);

  if (input.keyTurn) input.angle = wrap(input.angle + input.keyTurn * 3.6 * dt);
  if (S.alive) sendInput(false);

  ctx.setTransform(1, 0, 0, 1, 0, 0);
  drawWorld();
  drawFood(now);
  for (let i = S.dying.length - 1; i >= 0; i--) {
    const s = S.dying[i], k = (now - s.fadeAt) / 300;
    if (k >= 1) { S.dying.splice(i, 1); continue; }
    drawSnake(s, 1 - k, false);
  }
  for (const s of S.snakes.values()) if (s !== me) drawSnake(s, 1, false);
  if (me) drawSnake(me, 1, true);
  drawNames();
  drawMinimap();
  if (S.alive) {
    $('score').textContent = S.score.toLocaleString('vi-VN');
  }
}
requestAnimationFrame(frame);

function wrap(a) {
  while (a > Math.PI) a -= TAU;
  while (a < -Math.PI) a += TAU;
  return a;
}

// ---------------------------------------------------------------- UI
let selectedSkin = Math.min(SKINS.length - 1, Math.max(0, parseInt(store.get('mm_skin', String((Math.random() * SKINS.length) | 0)), 10) || 0));
$('name').value = store.get('mm_name', '');

const skinsEl = $('skins');
SKINS.forEach(([a, b], i) => {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'skin';
  btn.setAttribute('role', 'radio');
  btn.setAttribute('aria-label', `Màu ${i + 1}`);
  btn.style.background = `repeating-linear-gradient(135deg, ${a} 0 8px, ${b} 8px 14px)`;
  btn.addEventListener('click', () => { selectedSkin = i; renderSkins(); });
  skinsEl.appendChild(btn);
});
function renderSkins() {
  [...skinsEl.children].forEach((el, i) => el.setAttribute('aria-checked', String(i === selectedSkin)));
}
renderSkins();

function play() {
  if (!S.connected) return;
  S.wantPlay = true;
  sendJoin();
}
$('play').addEventListener('click', play);
$('name').addEventListener('keydown', (e) => { if (e.key === 'Enter') play(); });
$('again').addEventListener('click', play);
$('to-menu').addEventListener('click', () => { $('dead').hidden = true; $('menu').hidden = false; });

function showDead(m) {
  $('hud').hidden = true;
  let msg;
  if (m.reason === 'wall') msg = 'Bạn lao ra khỏi bản đồ.';
  else if (m.by) msg = `Bạn đâm vào ${m.by}.`;
  else msg = 'Bạn đã bị loại.';
  $('dead-msg').textContent = msg;
  $('dead-score').textContent = m.score.toLocaleString('vi-VN');
  const mins = Math.floor(m.secs / 60), secs = m.secs % 60;
  $('dead-extra').textContent = `Hạ gục ${m.kills} · sống ${mins ? `${mins} phút ` : ''}${secs} giây`;
  setTimeout(() => { if (!S.alive) $('dead').hidden = false; }, 900);
}

function updateBoard() {
  const lb = S.lb;
  const list = $('board-list');
  list.textContent = '';
  for (const [id, name, score] of lb.top) {
    const li = document.createElement('li');
    if (id === S.myId && S.alive) li.className = 'me';
    const n = document.createElement('span'); n.className = 'n'; n.textContent = name;
    const s = document.createElement('span'); s.className = 's'; s.textContent = score.toLocaleString('vi-VN');
    li.append(n, s);
    list.appendChild(li);
  }
  $('rank').textContent = lb.rank ? `${lb.rank} / ${lb.n}` : '-';
  $('online').textContent = `${lb.n} con giun đang bò`;
}

function addFeed(killer, victim) {
  const feed = $('feed');
  const div = document.createElement('div');
  const a = document.createElement('b'); a.textContent = killer;
  const b = document.createElement('b'); b.textContent = victim;
  div.append(a, ' hạ gục ', b);
  feed.prepend(div);
  while (feed.children.length > 4) feed.lastChild.remove();
  setTimeout(() => { div.style.opacity = '0'; }, 4500);
  setTimeout(() => div.remove(), 5200);
}

function updateNet() {
  $('net').textContent = S.connected ? `${S.ping} ms · ${S.fps} fps` : '';
}

function showConn(text) { $('conn-msg').textContent = text; $('conn').hidden = false; }
function hideConn() { $('conn').hidden = true; }

// ---------------------------------------------------------------- input
function aimAt(clientX, clientY) {
  input.angle = Math.atan2(clientY - view.h / 2, clientX - view.w / 2);
  input.keyTurn = 0;
}

const touches = new Map();
canvas.addEventListener('pointerdown', (e) => {
  if (e.pointerType === 'mouse') {
    if (e.button === 0) input.mouseBoost = true;
    aimAt(e.clientX, e.clientY);
    return;
  }
  touches.set(e.pointerId, true);
  if (touches.size === 1) aimAt(e.clientX, e.clientY);
  else input.touchBoost = true; // second finger = boost
});
canvas.addEventListener('pointermove', (e) => {
  if (e.pointerType === 'mouse') { aimAt(e.clientX, e.clientY); return; }
  if (touches.size >= 1 && [...touches.keys()][0] === e.pointerId) aimAt(e.clientX, e.clientY);
});
const endTouch = (e) => {
  if (e.pointerType === 'mouse') { input.mouseBoost = false; return; }
  touches.delete(e.pointerId);
  if (touches.size < 2) input.touchBoost = false;
};
canvas.addEventListener('pointerup', endTouch);
canvas.addEventListener('pointercancel', endTouch);
canvas.addEventListener('contextmenu', (e) => e.preventDefault());
window.addEventListener('blur', () => {
  input.mouseBoost = input.keyBoost = input.touchBoost = input.btnBoost = false;
  input.keyTurn = 0; touches.clear();
});

const boostBtn = $('boost-btn');
const setBtn = (on) => { input.btnBoost = on; boostBtn.classList.toggle('on', on); };
boostBtn.addEventListener('pointerdown', (e) => { e.preventDefault(); setBtn(true); });
boostBtn.addEventListener('pointerup', () => setBtn(false));
boostBtn.addEventListener('pointercancel', () => setBtn(false));
boostBtn.addEventListener('pointerleave', () => setBtn(false));

window.addEventListener('keydown', (e) => {
  if (e.target instanceof HTMLInputElement) return;
  if (e.code === 'Space' || e.code === 'ArrowUp' || e.code === 'KeyW') { input.keyBoost = true; e.preventDefault(); }
  if (e.code === 'ArrowLeft' || e.code === 'KeyA') input.keyTurn = -1;
  if (e.code === 'ArrowRight' || e.code === 'KeyD') input.keyTurn = 1;
});
window.addEventListener('keyup', (e) => {
  if (e.code === 'Space' || e.code === 'ArrowUp' || e.code === 'KeyW') input.keyBoost = false;
  if ((e.code === 'ArrowLeft' || e.code === 'KeyA') && input.keyTurn < 0) input.keyTurn = 0;
  if ((e.code === 'ArrowRight' || e.code === 'KeyD') && input.keyTurn > 0) input.keyTurn = 0;
});

connect();
