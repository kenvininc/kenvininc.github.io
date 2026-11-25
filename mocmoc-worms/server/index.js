import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { WebSocketServer } from 'ws';
import { Game } from './game.js';
import { TICK_MS } from '../public/js/shared.js';

const env = (k, d) => (process.env[k] === undefined || process.env[k] === '' ? d : process.env[k]);
const num = (k, d) => {
  const v = Number(env(k, d));
  return Number.isFinite(v) ? v : d;
};

const CFG = {
  port: num('PORT', 3000),
  worldRadius: Math.min(15000, Math.max(1000, num('WORLD_RADIUS', 3000))),
  bots: Math.max(0, num('BOTS', 16)),
  maxPlayers: Math.max(1, num('MAX_PLAYERS', 60)),
  maxConnPerIp: Math.max(1, num('MAX_CONN_PER_IP', 6)),
  foodDensity: Math.max(2000, num('FOOD_DENSITY', 9000)), // world units^2 per natural food
  trustProxy: env('TRUST_PROXY', '0') === '1',
  allowedOrigins: env('ALLOWED_ORIGINS', '').split(',').map((s) => s.trim()).filter(Boolean),
};

const PUBLIC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'public');
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.json': 'application/json',
  '.webmanifest': 'application/manifest+json',
};
const SECURITY_HEADERS = {
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'X-Frame-Options': 'DENY',
  'Content-Security-Policy':
    "default-src 'self'; connect-src 'self' ws: wss:; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'",
};

const game = new Game(CFG);
const startedAt = Date.now();

function clientIp(req) {
  if (CFG.trustProxy) {
    const cf = req.headers['cf-connecting-ip'];
    if (typeof cf === 'string' && cf) return cf.trim();
    const xff = req.headers['x-forwarded-for'];
    if (typeof xff === 'string' && xff) return xff.split(',')[0].trim();
  }
  return req.socket.remoteAddress || '?';
}

function serveStatic(req, res) {
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.writeHead(405, { Allow: 'GET, HEAD' }).end();
    return;
  }
  let pathname;
  try {
    pathname = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  } catch {
    res.writeHead(400).end();
    return;
  }
  if (pathname === '/healthz') {
    const body = JSON.stringify({ ok: true, uptime: Math.round((Date.now() - startedAt) / 1000), ...game.stats() });
    res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }).end(body);
    return;
  }
  if (pathname.endsWith('/')) pathname += 'index.html';
  const file = path.resolve(PUBLIC, '.' + pathname);
  if (!file.startsWith(PUBLIC + path.sep) || file.includes('\0')) {
    res.writeHead(404).end();
    return;
  }
  fs.stat(file, (err, st) => {
    if (err || !st.isFile()) {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8', ...SECURITY_HEADERS }).end('Not found');
      return;
    }
    const lastMod = st.mtime.toUTCString();
    const etag = `W/"${st.size.toString(16)}-${Math.floor(st.mtimeMs).toString(16)}"`;
    const headers = {
      'Content-Type': MIME[path.extname(file).toLowerCase()] || 'application/octet-stream',
      'Cache-Control': 'no-cache',
      'Last-Modified': lastMod,
      ETag: etag,
      ...SECURITY_HEADERS,
    };
    if (req.headers['if-none-match'] === etag) {
      res.writeHead(304, headers).end();
      return;
    }
    headers['Content-Length'] = st.size;
    res.writeHead(200, headers);
    if (req.method === 'HEAD') { res.end(); return; }
    fs.createReadStream(file).pipe(res);
  });
}

const server = http.createServer(serveStatic);
const wss = new WebSocketServer({ noServer: true, maxPayload: 256, perMessageDeflate: false });
const connPerIp = new Map();

function originAllowed(req) {
  const origin = req.headers.origin;
  if (!origin) return true; // non-browser client; per-IP limit still applies
  if (CFG.allowedOrigins.includes('*') || CFG.allowedOrigins.includes(origin)) return true;
  try {
    return new URL(origin).host === req.headers.host; // same origin
  } catch {
    return false;
  }
}

server.on('upgrade', (req, socket, head) => {
  let pathname = '';
  try { pathname = new URL(req.url, 'http://x').pathname; } catch { /* ignore */ }
  if (!pathname.endsWith('/ws')) { socket.destroy(); return; }
  if (!originAllowed(req)) {
    socket.write('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n');
    socket.destroy();
    return;
  }
  const ip = clientIp(req);
  if ((connPerIp.get(ip) || 0) >= CFG.maxConnPerIp) {
    socket.write('HTTP/1.1 429 Too Many Requests\r\nConnection: close\r\n\r\n');
    socket.destroy();
    return;
  }
  wss.handleUpgrade(req, socket, head, (ws) => onConnection(ws, ip));
});

function onConnection(ws, ip) {
  connPerIp.set(ip, (connPerIp.get(ip) || 0) + 1);
  let tokens = 60, lastRefill = Date.now();
  let alive = true;

  const client = {
    ip,
    sendJson(obj) { if (ws.readyState === ws.OPEN) ws.send(JSON.stringify(obj)); },
    sendText(str) { if (ws.readyState === ws.OPEN) ws.send(str); },
    sendBinary(buf) { if (ws.readyState === ws.OPEN) ws.send(buf, { binary: true }); },
    canSend() {
      if (ws.readyState !== ws.OPEN) return false;
      if (ws.bufferedAmount > 4 * 1024 * 1024) { ws.terminate(); return false; }
      return ws.bufferedAmount < 512 * 1024;
    },
  };
  game.addClient(client);

  ws.on('pong', () => { alive = true; });
  ws.on('message', (data, isBinary) => {
    const now = Date.now();
    tokens = Math.min(80, tokens + ((now - lastRefill) / 1000) * 40);
    lastRefill = now;
    if (--tokens < 0) { ws.close(1008, 'rate limit'); return; }
    if (isBinary) {
      game.onMessage(client, Buffer.isBuffer(data) ? data : Buffer.concat(data));
      return;
    }
    let msg;
    try { msg = JSON.parse(data.toString()); } catch { return; }
    if (msg && msg.t === 'ping' && typeof msg.c === 'number') client.sendJson({ t: 'pong', c: msg.c });
  });
  ws.on('close', () => {
    game.removeClient(client);
    const n = (connPerIp.get(ip) || 1) - 1;
    if (n <= 0) connPerIp.delete(ip); else connPerIp.set(ip, n);
    clearInterval(hb);
  });
  ws.on('error', () => {});
  const hb = setInterval(() => {
    if (!alive) { ws.terminate(); return; }
    alive = false;
    ws.ping();
  }, 20000);
}

// fixed-rate game loop with catch-up (max 5 ticks) and drift correction
let next = performance.now();
let slowTicks = 0;
function loop() {
  const now = performance.now();
  let n = 0;
  while (now >= next && n < 5) {
    const t0 = performance.now();
    game.update();
    if (performance.now() - t0 > TICK_MS) slowTicks++;
    next += TICK_MS;
    n++;
  }
  if (now - next > 1000) next = now; // fell far behind (e.g. host suspended): resync
  setTimeout(loop, Math.max(0, next - performance.now()));
}
loop();

setInterval(() => {
  const s = game.stats();
  if (slowTicks > 0) console.warn(`[perf] ${slowTicks} slow ticks in last 60s`, s);
  slowTicks = 0;
}, 60000).unref();

server.listen(CFG.port, () => {
  console.log(`mocmoc-worms listening on :${CFG.port}`, {
    worldRadius: CFG.worldRadius, bots: CFG.bots, maxPlayers: CFG.maxPlayers,
    trustProxy: CFG.trustProxy, allowedOrigins: CFG.allowedOrigins,
  });
});

function shutdown() {
  console.log('shutting down');
  for (const ws of wss.clients) ws.close(1001, 'server restart');
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 2000).unref();
}
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
