// Smoke test: start the server, connect a fake client, join, steer, check state arrives.
// Usage: npm test
import { spawn } from 'node:child_process';
import WebSocket from 'ws';

const PORT = 3999;
const srv = spawn(process.execPath, ['server/index.js'], {
  env: { ...process.env, PORT: String(PORT), BOTS: '20' },
  stdio: ['ignore', 'pipe', 'inherit'],
});
const fail = (m) => { console.error('FAIL:', m); srv.kill(); process.exit(1); };
setTimeout(() => fail('timeout'), 15000);

await new Promise((res) => srv.stdout.on('data', (d) => { if (String(d).includes('listening')) res(); }));

const health = await (await fetch(`http://127.0.0.1:${PORT}/healthz`)).json();
if (!health.ok) fail('healthz');
const html = await (await fetch(`http://127.0.0.1:${PORT}/`)).text();
if (!html.includes('mocmoc')) fail('index');
const trav = await fetch(`http://127.0.0.1:${PORT}/..%2f..%2fpackage.json`);
if (trav.status !== 404) fail('path traversal not blocked: ' + trav.status);

const ws = new WebSocket(`ws://127.0.0.1:${PORT}/ws`);
let welcome = null, you = null, states = 0, bytes = 0, maxSnakes = 0, foodAdds = 0, gotLb = false;
ws.on('message', (data, isBinary) => {
  if (!isBinary) {
    const m = JSON.parse(String(data));
    if (m.t === 'welcome') {
      welcome = m;
      const name = Buffer.from('Tester ✓');
      ws.send(Buffer.concat([Buffer.from([1, 3]), name]));
    }
    if (m.t === 'you') you = m;
    if (m.t === 'lb') gotLb = true;
    return;
  }
  states++;
  bytes += data.length;
  const n = data.readUInt16LE(13);
  maxSnakes = Math.max(maxSnakes, n);
  // walk snakes to reach food count
  let o = 15;
  for (let i = 0; i < n; i++) {
    const flags = data[o + 2];
    o += 11;
    if (flags & 2) { const m = data.readUInt16LE(o); o += 2 + m * 4; }
  }
  foodAdds += data.readUInt16LE(o);
});
ws.on('open', () => {
  setInterval(() => {
    const b = Buffer.alloc(8);
    b[0] = 2; b.writeUInt16LE((Date.now() / 10) & 0xffff, 1); b[3] = 0;
    b.writeUInt16LE(900, 4); b.writeUInt16LE(600, 6);
    ws.send(b);
  }, 100);
});

await new Promise((r) => setTimeout(r, 3000));
if (!welcome) fail('no welcome');
if (!you) fail('no join');
if (states < 50) fail('too few states: ' + states);
if (!gotLb) fail('no leaderboard');
if (foodAdds < 10) fail('no food');
const h2 = await (await fetch(`http://127.0.0.1:${PORT}/healthz`)).json();
console.log('OK', { states, avgBytes: Math.round(bytes / states), maxSnakes, foodAdds, health: h2 });
ws.close();
srv.kill();
process.exit(0);
