// Small growable little-endian binary writer, reused between messages.
export class Writer {
  constructor(size = 4096) {
    this.buf = Buffer.allocUnsafe(size);
    this.o = 0;
  }
  reset() { this.o = 0; }
  ensure(n) {
    if (this.o + n <= this.buf.length) return;
    let s = this.buf.length * 2;
    while (s < this.o + n) s *= 2;
    const b = Buffer.allocUnsafe(s);
    this.buf.copy(b, 0, 0, this.o);
    this.buf = b;
  }
  u8(v) { this.ensure(1); this.buf[this.o++] = v & 0xff; }
  u16(v) { this.ensure(2); this.buf.writeUInt16LE(v & 0xffff, this.o); this.o += 2; }
  i16(v) {
    this.ensure(2);
    v = Math.round(v);
    if (v > 32767) v = 32767; else if (v < -32768) v = -32768;
    this.buf.writeInt16LE(v, this.o); this.o += 2;
  }
  u32(v) { this.ensure(4); this.buf.writeUInt32LE(v >>> 0, this.o); this.o += 4; }
  // reserve a u16 and return its position for patching later
  reserve16() { const p = this.o; this.u16(0); return p; }
  patch16(pos, v) { this.buf.writeUInt16LE(v & 0xffff, pos); }
  // copy out (the internal buffer is reused, ws may send asynchronously)
  take() { return Buffer.from(this.buf.subarray(0, this.o)); }
}
