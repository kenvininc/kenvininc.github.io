import {
  TICK_RATE, SUBSTEPS, SPACING, MAX_NAME, MAX_RADIUS,
  C2S, S2C, FLAG_BOOST, FLAG_FULL, SKINS, FOOD_COLORS,
  radiusForMass, lengthForMass, turnRate,
} from '../public/js/shared.js';
import { Writer } from './writer.js';

const BASE_SPEED = 190;          // units/s
const BOOST_SPEED = 440;
const START_MASS = 10;
const MIN_BOOST_MASS = 15;
const SCELL = 64;                // body-point grid cell
const FCELL = 128;               // food grid cell
const EAT_PAD = 14;
const HEAD_HIT = 0.8;            // head collision radius factor (a bit forgiving)
const DROP_TTL = 75 * TICK_RATE; // dropped food lifetime in ticks
const MAX_FOOD_FACTOR = 2.5;     // total food cap = natural target * this
const VIEW_MARGIN = 120;
const MAX_HALF_VIEW = 2600;
const TAU = Math.PI * 2;

const BOT_NAMES = [
  'Bún Chả', 'Mèo Mốc', 'Cà Phê Sữa', 'Bánh Mì', 'Trà Đá', 'Gỏi Cuốn', 'Phở Bò',
  'Chè Ba Màu', 'Xôi Gà', 'Bánh Xèo', 'Nem Rán', 'Hủ Tiếu', 'Cơm Tấm', 'Bò Bía',
  'Sữa Chua', 'Bánh Bao', 'Kem Bơ', 'Ốc Len', 'Mít Tố Nữ', 'Chuối Chiên',
  'Bánh Flan', 'Cá Viên', 'Trứng Vịt Lộn', 'Rau Má', 'Nước Mía',
];

const rand = (a, b) => a + Math.random() * (b - a);
function wrapAngle(a) {
  while (a > Math.PI) a -= TAU;
  while (a < -Math.PI) a += TAU;
  return a;
}

// Strip control / bidi / zero-width characters, trim, limit length.
export function sanitizeName(raw) {
  let s = String(raw || '')
    .replace(/[\u0000-\u001f\u007f-\u009f\u200b-\u200f\u2028-\u202e\u2060-\u2069\ufeff]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  s = Array.from(s).slice(0, MAX_NAME).join('').trim();
  return s || 'Giun vô danh';
}

class Snake {
  constructor(id, name, skin, bot, x, y, angle) {
    this.id = id;
    this.name = name;
    this.skin = skin;
    this.bot = bot;
    this.mass = START_MASS;
    this.r = radiusForMass(this.mass);
    this.len = lengthForMass(this.mass);
    this.hx = x; this.hy = y;
    this.angle = angle; this.target = angle;
    this.wantBoost = false; this.boosting = false;
    this.alive = true;
    // body points, oldest (tail) -> newest; live range is [tail, px.length)
    this.px = []; this.py = []; this.tail = 0;
    this.dropAcc = 0; this.dropTimer = 0;
    this.client = null;
    this.idx = -1;
    this.minX = x; this.maxX = x; this.minY = y; this.maxY = y;
    this.kills = 0;
    this.bornTick = 0;
    // bot state
    this.goalX = x; this.goalY = y; this.goalTimer = 0;
    this.hunter = bot && Math.random() < 0.35;
    this.prey = null;
    const n = Math.ceil(this.len / SPACING);
    const c = Math.cos(angle), s = Math.sin(angle);
    for (let i = n; i >= 1; i--) {
      this.px.push(x - c * i * SPACING);
      this.py.push(y - s * i * SPACING);
    }
  }
  get count() { return this.px.length - this.tail; }
}

export class Game {
  constructor(opts) {
    this.R = opts.worldRadius;
    this.botTarget = opts.bots;
    this.maxPlayers = opts.maxPlayers;
    this.tick = 0;
    this.snakes = new Map();
    this.nextSnakeId = 1;
    this.clients = new Set();
    this.food = new Map();
    this.nextFoodId = 1;
    this.naturalTarget = Math.round((Math.PI * this.R * this.R) / opts.foodDensity);
    this.naturalCount = 0;
    this.eaten = new Map();   // foodId -> eater snake id, this tick only
    this.events = [];         // broadcast JSON events, this tick only
    this.alive = [];          // alive snakes in grid order (idx)
    this.leaderboard = [];
    this.w = new Writer(16384);

    const size = this.R * 2 + SCELL * 2;
    this.sCols = Math.ceil(size / SCELL);
    this.sCells = Array.from({ length: this.sCols * this.sCols }, () => []);
    this.sTouched = [];
    this.fCols = Math.ceil((this.R * 2 + FCELL * 2) / FCELL);
    this.fCells = Array.from({ length: this.fCols * this.fCols }, () => []);

    while (this.naturalCount < this.naturalTarget) this.spawnNaturalFood();
    for (let i = 0; i < this.botTarget; i++) this.spawnBot();
  }

  // ---------- grid helpers ----------
  sCell(v) {
    let c = Math.floor((v + this.R + SCELL) / SCELL);
    return c < 0 ? 0 : c >= this.sCols ? this.sCols - 1 : c;
  }
  fCell(v) {
    let c = Math.floor((v + this.R + FCELL) / FCELL);
    return c < 0 ? 0 : c >= this.fCols ? this.fCols - 1 : c;
  }

  // ---------- food ----------
  addFood(x, y, v, c, ttl) {
    const d = Math.hypot(x, y), lim = this.R - 20;
    if (d > lim) { x *= lim / d; y *= lim / d; }
    const f = { id: this.nextFoodId++, x, y, v, c, exp: ttl ? this.tick + ttl : 0, cell: 0, k: 0 };
    if (this.nextFoodId > 0xfffffff0) this.nextFoodId = 1;
    f.cell = this.fCell(y) * this.fCols + this.fCell(x);
    const arr = this.fCells[f.cell];
    f.k = arr.length;
    arr.push(f);
    this.food.set(f.id, f);
    if (!ttl) this.naturalCount++;
    return f;
  }
  removeFood(f, eaterId) {
    const arr = this.fCells[f.cell];
    const last = arr.pop();
    if (last !== f) { arr[f.k] = last; last.k = f.k; }
    this.food.delete(f.id);
    if (!f.exp) this.naturalCount--;
    if (eaterId) this.eaten.set(f.id, eaterId);
  }
  spawnNaturalFood() {
    const a = Math.random() * TAU, d = (this.R - 40) * Math.sqrt(Math.random());
    const r = Math.random();
    const v = r < 0.7 ? 1 : r < 0.93 ? 2 : 3;
    this.addFood(Math.cos(a) * d, Math.sin(a) * d, v, (Math.random() * FOOD_COLORS.length) | 0, 0);
  }
  dropFood(x, y, v, c) {
    if (this.food.size >= this.naturalTarget * MAX_FOOD_FACTOR) return;
    this.addFood(x, y, v, c, DROP_TTL + ((Math.random() * 10 * TICK_RATE) | 0));
  }

  // ---------- snakes ----------
  newSnakeId() {
    for (let i = 0; i < 65535; i++) {
      const id = this.nextSnakeId;
      this.nextSnakeId = this.nextSnakeId >= 65534 ? 1 : this.nextSnakeId + 1;
      if (!this.snakes.has(id)) return id;
    }
    return 0;
  }
  findSpawn() {
    let best = null, bestD = -1;
    for (let t = 0; t < 24; t++) {
      const a = Math.random() * TAU, d = this.R * 0.75 * Math.sqrt(Math.random());
      const x = Math.cos(a) * d, y = Math.sin(a) * d;
      let nearest = Infinity;
      for (const s of this.snakes.values()) {
        const dd = Math.hypot(s.hx - x, s.hy - y) - s.len * 0.5;
        if (dd < nearest) nearest = dd;
      }
      if (nearest > 400) return { x, y };
      if (nearest > bestD) { bestD = nearest; best = { x, y }; }
    }
    return best;
  }
  spawnSnake(name, skin, bot) {
    const id = this.newSnakeId();
    if (!id) return null;
    const p = this.findSpawn();
    const angle = Math.atan2(-p.y, -p.x) + rand(-1, 1);
    const s = new Snake(id, name, skin, bot, p.x, p.y, angle);
    s.bornTick = this.tick;
    this.snakes.set(id, s);
    this.events.push(['s', id, name, skin]);
    return s;
  }
  spawnBot() {
    const name = BOT_NAMES[(Math.random() * BOT_NAMES.length) | 0];
    const s = this.spawnSnake(name, (Math.random() * SKINS.length) | 0, true);
    if (s) s.mass = START_MASS + Math.random() * 60;
  }
  killSnake(s, killer, reason) {
    if (!s.alive) return;
    s.alive = false;
    this.snakes.delete(s.id);
    // turn the body into food
    const total = Math.max(6, s.mass * 0.75);
    const n = Math.max(4, Math.min(220, Math.round(total / 5)));
    const v = total / n;
    const cnt = s.count;
    for (let k = 0; k < n; k++) {
      const i = s.tail + Math.floor((k * cnt) / n);
      const j = s.r * 0.7;
      this.dropFood(s.px[i] + rand(-j, j), s.py[i] + rand(-j, j), v, s.skin % FOOD_COLORS.length);
    }
    if (killer) killer.kills++;
    this.events.push(['d', s.id, killer ? killer.name : '', reason]);
    const c = s.client;
    if (c) {
      c.snake = null;
      c.deadTick = this.tick;
      c.specX = s.hx; c.specY = s.hy;
      c.sendJson({
        t: 'dead',
        score: Math.floor(s.mass),
        by: killer ? killer.name : null,
        reason,
        kills: s.kills,
        secs: Math.round((this.tick - s.bornTick) / TICK_RATE),
      });
    }
  }

  // ---------- simulation ----------
  update() {
    this.tick++;
    const dt = 1 / TICK_RATE / SUBSTEPS;
    for (let sub = 0; sub < SUBSTEPS; sub++) {
      this.moveSnakes(dt);
      this.buildGrid();
      this.collide();
      for (const s of this.alive) if (s.alive) this.eat(s);
    }
    for (const s of this.alive) {
      if (s.alive && s.bot && ((this.tick + s.id) & 1) === 0) this.botThink(s);
    }
    // food upkeep
    for (let k = 0; k < 40 && this.naturalCount < this.naturalTarget; k++) this.spawnNaturalFood();
    if (this.tick % TICK_RATE === 0) {
      for (const f of this.food.values()) if (f.exp && f.exp <= this.tick) this.removeFood(f, 0);
    }
    // bots
    if (this.tick % 10 === 0 && this.snakes.size < this.botTarget) this.spawnBot();

    this.broadcast();
    if (this.tick % TICK_RATE === 0) this.sendLeaderboard();
    this.eaten.clear();
    this.events.length = 0;
  }

  moveSnakes(dt) {
    const R = this.R;
    for (const s of this.snakes.values()) {
      const diff = wrapAngle(s.target - s.angle);
      const mt = turnRate(s.r) * dt;
      s.angle = wrapAngle(s.angle + (diff > mt ? mt : diff < -mt ? -mt : diff));
      s.boosting = s.wantBoost && s.mass > MIN_BOOST_MASS;
      const sp = s.boosting ? BOOST_SPEED : BASE_SPEED;
      s.hx += Math.cos(s.angle) * sp * dt;
      s.hy += Math.sin(s.angle) * sp * dt;

      if (s.boosting) {
        const drain = (3 + s.mass * 0.0045) * dt;
        s.mass -= drain;
        s.dropAcc += drain;
        s.dropTimer += dt;
        if (s.dropTimer >= 0.1) {
          s.dropTimer = 0;
          if (s.dropAcc > 0.4) {
            const t = s.tail;
            this.dropFood(s.px[t] + rand(-4, 4), s.py[t] + rand(-4, 4), s.dropAcc * 0.8, s.skin % FOOD_COLORS.length);
            s.dropAcc = 0;
          }
        }
      }
      s.r = radiusForMass(s.mass);
      s.len = lengthForMass(s.mass);

      // extend trail
      let n = s.px.length - 1;
      let lx = s.px[n], ly = s.py[n];
      let dx = s.hx - lx, dy = s.hy - ly, d = Math.hypot(dx, dy);
      while (d >= SPACING) {
        lx += (dx / d) * SPACING; ly += (dy / d) * SPACING;
        s.px.push(lx); s.py.push(ly);
        dx = s.hx - lx; dy = s.hy - ly; d = Math.hypot(dx, dy);
      }
      // trim tail
      const maxPts = Math.max(2, Math.ceil(s.len / SPACING));
      if (s.count > maxPts) s.tail = s.px.length - maxPts;
      if (s.tail > 256) { s.px.splice(0, s.tail); s.py.splice(0, s.tail); s.tail = 0; }

      if (Math.hypot(s.hx, s.hy) + s.r * 0.5 > R) s.hitWall = true;
    }
  }

  buildGrid() {
    const cells = this.sCells, cols = this.sCols;
    for (const ci of this.sTouched) cells[ci].length = 0;
    this.sTouched.length = 0;
    this.alive.length = 0;
    let idx = 0;
    for (const s of this.snakes.values()) {
      s.idx = idx++;
      this.alive.push(s);
      let minX = s.hx, maxX = s.hx, minY = s.hy, maxY = s.hy;
      this.gridInsert(cells, cols, s.idx, s.hx, s.hy);
      const px = s.px, py = s.py;
      for (let i = s.tail; i < px.length; i++) {
        const x = px[i], y = py[i];
        if (x < minX) minX = x; else if (x > maxX) maxX = x;
        if (y < minY) minY = y; else if (y > maxY) maxY = y;
        this.gridInsert(cells, cols, s.idx, x, y);
      }
      s.minX = minX - s.r; s.maxX = maxX + s.r; s.minY = minY - s.r; s.maxY = maxY + s.r;
    }
  }
  gridInsert(cells, cols, idx, x, y) {
    const ci = this.sCell(y) * cols + this.sCell(x);
    const arr = cells[ci];
    if (arr.length === 0) this.sTouched.push(ci);
    arr.push(idx, x, y);
  }

  collide() {
    const dead = [];
    const cells = this.sCells, cols = this.sCols, alive = this.alive;
    for (const s of alive) {
      if (s.hitWall) { dead.push([s, null, 'wall']); continue; }
      const hr = s.r * HEAD_HIT;
      const reach = hr + MAX_RADIUS;
      const x0 = this.sCell(s.hx - reach), x1 = this.sCell(s.hx + reach);
      const y0 = this.sCell(s.hy - reach), y1 = this.sCell(s.hy + reach);
      let killer = null;
      outer:
      for (let cy = y0; cy <= y1; cy++) {
        for (let cx = x0; cx <= x1; cx++) {
          const arr = cells[cy * cols + cx];
          for (let i = 0; i < arr.length; i += 3) {
            const j = arr[i];
            if (j === s.idx) continue;
            const o = alive[j];
            const dx = arr[i + 1] - s.hx, dy = arr[i + 2] - s.hy, rr = hr + o.r;
            if (dx * dx + dy * dy < rr * rr) { killer = o; break outer; }
          }
        }
      }
      if (killer) dead.push([s, killer, 'snake']);
    }
    for (const [s, k, why] of dead) this.killSnake(s, k, why);
  }

  eat(s) {
    const er = s.r + EAT_PAD, er2 = er * er;
    const x0 = this.fCell(s.hx - er), x1 = this.fCell(s.hx + er);
    const y0 = this.fCell(s.hy - er), y1 = this.fCell(s.hy + er);
    for (let cy = y0; cy <= y1; cy++) {
      for (let cx = x0; cx <= x1; cx++) {
        const arr = this.fCells[cy * this.fCols + cx];
        for (let i = arr.length - 1; i >= 0; i--) {
          const f = arr[i];
          const dx = f.x - s.hx, dy = f.y - s.hy;
          if (dx * dx + dy * dy < er2) {
            s.mass += f.v;
            this.removeFood(f, s.id);
          }
        }
      }
    }
  }

  // ---------- bots ----------
  danger(s, ang, look) {
    const c = Math.cos(ang), sn = Math.sin(ang);
    const lim = this.R - s.r - 30;
    const cells = this.sCells, cols = this.sCols, alive = this.alive;
    for (const f of [0.35, 0.7, 1]) {
      const x = s.hx + c * look * f, y = s.hy + sn * look * f;
      if (x * x + y * y > lim * lim) return true;
      const reach = s.r + MAX_RADIUS + 8;
      const x0 = this.sCell(x - reach), x1 = this.sCell(x + reach);
      const y0 = this.sCell(y - reach), y1 = this.sCell(y + reach);
      for (let cy = y0; cy <= y1; cy++) {
        for (let cx = x0; cx <= x1; cx++) {
          const arr = cells[cy * cols + cx];
          for (let i = 0; i < arr.length; i += 3) {
            const j = arr[i];
            if (j === s.idx) continue;
            const o = alive[j];
            const dx = arr[i + 1] - x, dy = arr[i + 2] - y, rr = s.r + o.r + 8;
            if (dx * dx + dy * dy < rr * rr) return true;
          }
        }
      }
    }
    return false;
  }

  botChooseGoal(s) {
    s.goalTimer = 10 + ((Math.random() * 20) | 0);
    s.prey = null;
    if (s.hunter && s.mass > 40) {
      let best = null, bd = 420;
      for (const o of this.alive) {
        if (o === s || !o.alive || o.mass > s.mass * 1.2) continue;
        const d = Math.hypot(o.hx - s.hx, o.hy - s.hy);
        if (d < bd) { bd = d; best = o; }
      }
      if (best) { s.prey = best; return; }
    }
    // best food nearby
    const range = 360;
    const x0 = this.fCell(s.hx - range), x1 = this.fCell(s.hx + range);
    const y0 = this.fCell(s.hy - range), y1 = this.fCell(s.hy + range);
    let best = null, bs = 0;
    for (let cy = y0; cy <= y1; cy++) {
      for (let cx = x0; cx <= x1; cx++) {
        for (const f of this.fCells[cy * this.fCols + cx]) {
          const d = Math.hypot(f.x - s.hx, f.y - s.hy);
          const sc = f.v / (d + 60);
          if (sc > bs) { bs = sc; best = f; }
        }
      }
    }
    if (best) { s.goalX = best.x; s.goalY = best.y; return; }
    const a = Math.random() * TAU, d = this.R * 0.7 * Math.sqrt(Math.random());
    s.goalX = Math.cos(a) * d; s.goalY = Math.sin(a) * d;
    s.goalTimer = 40;
  }

  botThink(s) {
    if (--s.goalTimer <= 0 || Math.hypot(s.goalX - s.hx, s.goalY - s.hy) < s.r + 10) this.botChooseGoal(s);
    let gx = s.goalX, gy = s.goalY, wantBoost = false;
    if (s.prey) {
      if (!s.prey.alive) { this.botChooseGoal(s); return; }
      gx = s.prey.hx + Math.cos(s.prey.angle) * (s.prey.r * 4 + 60);
      gy = s.prey.hy + Math.sin(s.prey.angle) * (s.prey.r * 4 + 60);
      wantBoost = Math.hypot(gx - s.hx, gy - s.hy) < 260 && Math.random() < 0.6;
    }
    const desired = Math.atan2(gy - s.hy, gx - s.hx);
    const look = s.r * 2.5 + (s.boosting ? 170 : 95);
    if (this.danger(s, s.angle, look) || this.danger(s, desired, look)) {
      const offs = [0.45, -0.45, 0.9, -0.9, 1.35, -1.35, 1.8, -1.8, 2.3, -2.3, 2.8, -2.8, Math.PI];
      const flip = Math.random() < 0.5 ? 1 : -1;
      let chosen = null;
      for (const o of offs) {
        const a = s.angle + o * flip;
        if (!this.danger(s, a, look)) { chosen = a; break; }
      }
      s.target = wrapAngle(chosen ?? s.angle + Math.PI * flip);
      s.wantBoost = false;
      s.goalTimer = Math.min(s.goalTimer, 4);
      return;
    }
    s.target = desired;
    s.wantBoost = wantBoost && s.mass > 40;
  }

  // ---------- clients ----------
  addClient(client) {
    client.snake = null;
    client.knownSnakes = new Set();
    client.knownFood = new Set();
    client.halfW = 900; client.halfH = 600;
    client.specX = 0; client.specY = 0; client.deadTick = -1e9;
    client.lastJoinTick = -1e9;
    this.clients.add(client);
    client.sendJson({
      t: 'welcome',
      R: this.R,
      players: [...this.snakes.values()].map((s) => [s.id, s.name, s.skin]),
    });
  }
  removeClient(client) {
    this.clients.delete(client);
    const s = client.snake;
    if (s) { s.client = null; this.killSnake(s, null, 'left'); }
    client.snake = null;
  }
  humansAlive() {
    let n = 0;
    for (const c of this.clients) if (c.snake) n++;
    return n;
  }
  onMessage(client, data) {
    const len = data.length;
    if (len < 1) return;
    const type = data[0];
    if (type === C2S.INPUT && len >= 8) {
      const s = client.snake;
      const angle = (data.readUInt16LE(1) / 65536) * TAU - Math.PI;
      client.halfW = Math.min(MAX_HALF_VIEW, Math.max(200, data.readUInt16LE(4)));
      client.halfH = Math.min(MAX_HALF_VIEW, Math.max(200, data.readUInt16LE(6)));
      if (s) { s.target = angle; s.wantBoost = (data[3] & 1) === 1; }
    } else if (type === C2S.JOIN && len >= 2) {
      if (client.snake) return;
      if (this.tick - client.lastJoinTick < TICK_RATE) return; // 1 join / second
      if (this.humansAlive() >= this.maxPlayers) { client.sendJson({ t: 'full' }); return; }
      client.lastJoinTick = this.tick;
      const skin = data[1] % SKINS.length;
      const name = sanitizeName(data.subarray(2, Math.min(len, 2 + 64)).toString('utf8'));
      const s = this.spawnSnake(name, skin, false);
      if (!s) return;
      s.client = client;
      client.snake = s;
      client.sendJson({ t: 'you', id: s.id });
    } else if (type === C2S.RESYNC) {
      client.knownSnakes.clear();
      client.knownFood.clear();
    }
  }

  broadcast() {
    if (this.events.length) {
      const msg = JSON.stringify({ t: 'ev', e: this.events });
      for (const c of this.clients) c.sendText(msg);
    }
    const w = this.w;
    for (const c of this.clients) {
      if (!c.canSend()) continue; // backpressure: skip this tick, state stays consistent
      const me = c.snake;
      let cx, cy;
      if (me) { cx = me.hx; cy = me.hy; }
      else {
        if (this.tick - c.deadTick > 3 * TICK_RATE) {
          const lead = this.leaderboard[0] && this.snakes.get(this.leaderboard[0][0]);
          if (lead) { c.specX += (lead.hx - c.specX) * 0.08; c.specY += (lead.hy - c.specY) * 0.08; }
        }
        cx = c.specX; cy = c.specY;
      }
      const hw = c.halfW + VIEW_MARGIN, hh = c.halfH + VIEW_MARGIN;
      const vx0 = cx - hw, vx1 = cx + hw, vy0 = cy - hh, vy1 = cy + hh;

      w.reset();
      w.u8(S2C.STATE);
      w.u32(this.tick);
      w.u32(me ? Math.floor(me.mass) : 0);
      w.i16(cx); w.i16(cy);
      const pCount = w.reserve16();
      let n = 0;
      const known = c.knownSnakes, nowKnown = new Set();
      for (const s of this.snakes.values()) {
        if (s.maxX < vx0 || s.minX > vx1 || s.maxY < vy0 || s.minY > vy1) continue;
        const full = !known.has(s.id);
        nowKnown.add(s.id);
        n++;
        w.u16(s.id);
        w.u8((s.boosting ? FLAG_BOOST : 0) | (full ? FLAG_FULL : 0));
        w.i16(s.hx); w.i16(s.hy);
        w.u8(Math.round(((s.angle + Math.PI) / TAU) * 256) & 255);
        w.u8(Math.round(s.r * 4));
        w.u16(Math.min(65535, Math.round(s.len)));
        if (full) {
          const cnt = s.count;
          w.u16(cnt);
          for (let i = s.px.length - 1; i >= s.tail; i--) { w.i16(s.px[i]); w.i16(s.py[i]); }
        }
      }
      w.patch16(pCount, n);
      c.knownSnakes = nowKnown;

      // food: diff against what this client already has
      const kf = c.knownFood, cur = new Set();
      const fAdd = w.reserve16();
      let na = 0;
      const fx0 = this.fCell(vx0), fx1 = this.fCell(vx1), fy0 = this.fCell(vy0), fy1 = this.fCell(vy1);
      for (let fy = fy0; fy <= fy1; fy++) {
        for (let fx = fx0; fx <= fx1; fx++) {
          for (const f of this.fCells[fy * this.fCols + fx]) {
            if (f.x < vx0 || f.x > vx1 || f.y < vy0 || f.y > vy1) continue;
            cur.add(f.id);
            if (kf.has(f.id) || na >= 4000) continue;
            na++;
            w.u32(f.id); w.i16(f.x); w.i16(f.y);
            w.u8(Math.max(1, Math.min(255, Math.round(f.v)))); w.u8(f.c);
          }
        }
      }
      w.patch16(fAdd, na);
      const fRem = w.reserve16();
      let nr = 0;
      for (const id of kf) {
        if (cur.has(id)) continue;
        if (nr >= 60000) { cur.add(id); continue; }
        nr++;
        w.u32(id);
        w.u16(this.eaten.get(id) || 0xffff);
      }
      w.patch16(fRem, nr);
      // anything over the add cap stays unknown and is sent next tick
      if (na >= 4000) for (const id of cur) if (!kf.has(id)) cur.delete(id);
      c.knownFood = cur;
      c.sendBinary(w.take());
    }
  }

  sendLeaderboard() {
    const sorted = [...this.snakes.values()].sort((a, b) => b.mass - a.mass);
    this.leaderboard = sorted.slice(0, 10).map((s) => [s.id, s.name, Math.floor(s.mass)]);
    const q = (v) => Math.max(0, Math.min(200, Math.round(((v + this.R) / (2 * this.R)) * 200)));
    const mm = [];
    for (const s of sorted.slice(0, 150)) mm.push(q(s.hx), q(s.hy), Math.min(9, Math.round(s.r / 6)));
    const rank = new Map();
    sorted.forEach((s, i) => rank.set(s, i + 1));
    const base = JSON.stringify({ t: 'lb', top: this.leaderboard, n: sorted.length, mm }).slice(0, -1);
    for (const c of this.clients) {
      const r = c.snake ? rank.get(c.snake) || 0 : 0;
      c.sendText(`${base},"rank":${r}}`);
    }
  }

  stats() {
    let bots = 0;
    for (const s of this.snakes.values()) if (s.bot) bots++;
    return {
      clients: this.clients.size,
      playing: this.humansAlive(),
      bots,
      snakes: this.snakes.size,
      food: this.food.size,
      tick: this.tick,
    };
  }
}
