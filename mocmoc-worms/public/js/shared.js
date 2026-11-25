// Shared between server (Node) and client (browser). Keep this file dependency-free.

export const TICK_RATE = 25;            // server ticks per second (= snapshots per second)
export const TICK_MS = 1000 / TICK_RATE;
export const SUBSTEPS = 2;              // physics substeps per tick (avoids tunnelling when boosting)
export const SPACING = 8;               // distance between stored body points (world units)
export const MAX_NAME = 16;             // max name length in code points
export const MAX_RADIUS = 52;

// client -> server (binary, first byte)
export const C2S = { JOIN: 1, INPUT: 2, RESYNC: 3 };
// server -> client (binary, first byte). Text frames are JSON.
export const S2C = { STATE: 0x11 };

export const FLAG_BOOST = 1;
export const FLAG_FULL = 2;

// [base, stripe]
export const SKINS = [
  ['#ff6b6b', '#ffd93d'],
  ['#4dabf7', '#e7f5ff'],
  ['#69db7c', '#2b8a3e'],
  ['#b197fc', '#5f3dc4'],
  ['#ffa94d', '#d9480f'],
  ['#f783ac', '#fff0f6'],
  ['#3bc9db', '#0b7285'],
  ['#ffe066', '#5c940d'],
  ['#e9ecef', '#495057'],
  ['#ff8787', '#862e9c'],
  ['#63e6be', '#f08c00'],
  ['#748ffc', '#ff922b'],
];

export const FOOD_COLORS = [
  '#ff5c5c', '#ffb347', '#ffe75c', '#7dff6b', '#4dfff3',
  '#5ca8ff', '#b77dff', '#ff6bd6', '#ffffff',
];

export function radiusForMass(m) {
  return Math.min(MAX_RADIUS, 9 + 2.2 * Math.cbrt(m));
}

export function lengthForMass(m) {
  return 90 + 28 * Math.pow(m, 0.6);
}

// radians per second; big worms turn slower
export function turnRate(r) {
  return 4.6 * Math.pow(14 / r, 0.45);
}
