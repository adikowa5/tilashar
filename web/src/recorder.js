/* Запись с пре-роллом и обработка дубля — перенесено из прототипа без изменений логики. */

import { audioCtx } from "./audio.js";

const sleep = ms => new Promise(r => setTimeout(r, ms));

/* Всегда держит 0,6 с пре-ролла, поэтому слово, сказанное на самом клике, не обрезается. */
export const Rec = {
  stream: null, src: null, node: null, sink: null, sampleRate: 48000,
  ring: [], ringLen: 0, chunks: [], capLen: 0, capturing: false,
  noise: 0.004, heardSpeech: false, silentFor: 0, onLevel: null, onAuto: null,
  get open(){ return !!this.stream; },
  async start(){
    if (!this.stream){
      const ctx = audioCtx();
      if (!ctx || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw { name: "NotSupportedError" };
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 } });
      this.sampleRate = ctx.sampleRate;
      this.src = ctx.createMediaStreamSource(this.stream);
      this.node = ctx.createScriptProcessor(2048, 1, 1);
      this.sink = ctx.createGain(); this.sink.gain.value = 0;
      this.src.connect(this.node); this.node.connect(this.sink); this.sink.connect(ctx.destination);
      this.node.onaudioprocess = e => this.block(e.inputBuffer.getChannelData(0));
      await sleep(250);                       // даём пре-роллу наполниться до первого дубля
    }
  },
  block(d){
    const c = new Float32Array(d), sr = this.sampleRate;
    let s = 0; for (let i = 0; i < c.length; i++) s += c[i] * c[i];
    const rms = Math.sqrt(s / c.length);
    if (!this.capturing){
      this.noise = this.noise * 0.9 + Math.min(rms, 0.05) * 0.1;
      this.ring.push(c); this.ringLen += c.length;
      while (this.ring.length > 1 && this.ringLen - this.ring[0].length >= 0.6 * sr) this.ringLen -= this.ring.shift().length;
    } else {
      this.chunks.push(c); this.capLen += c.length;
      if (rms > Math.max(0.02, this.noise * 4)){ this.heardSpeech = true; this.silentFor = 0; }
      else if (this.heardSpeech) this.silentFor += c.length / sr;
      if ((this.heardSpeech && this.silentFor > 0.85) || this.capLen / sr > 4.2) this.onAuto && this.onAuto();
    }
    this.onLevel && this.onLevel(rms);
  },
  take(){
    this.chunks = this.ring.slice(); this.capLen = this.ringLen;
    this.heardSpeech = false; this.silentFor = 0; this.capturing = true;
  },
  finish(){
    this.capturing = false;
    const out = new Float32Array(this.capLen); let o = 0;
    for (const c of this.chunks){ out.set(c, o); o += c.length; }
    this.chunks = []; this.capLen = 0;
    return { data: out, sampleRate: this.sampleRate };
  },
  close(){
    this.capturing = false; this.onAuto = null; this.onLevel = null;
    try { this.node && (this.node.onaudioprocess = null); this.src && this.src.disconnect(); this.node && this.node.disconnect(); this.sink && this.sink.disconnect(); } catch {}
    if (this.stream) this.stream.getTracks().forEach(t => t.stop());
    this.stream = this.src = this.node = this.sink = null; this.ring = []; this.ringLen = 0;
  }
};

// Щедро режем тишину (180 мс до первого звука, 280 мс после последнего), нормализуем, 22,05 кГц моно WAV.
export async function processTake(data, sr){
  const win = Math.round(sr * 0.01), n = Math.floor(data.length / win);
  if (n < 10) throw { code: "quiet" };
  const rms = new Float32Array(n); let peak = 0;
  for (let i = 0; i < n; i++){
    let s = 0; for (let j = 0; j < win; j++){ const v = data[i * win + j]; s += v * v; }
    rms[i] = Math.sqrt(s / win); if (rms[i] > peak) peak = rms[i];
  }
  if (peak < 0.012) throw { code: "quiet" };
  const floor = Array.from(rms).sort((a, b) => a - b)[Math.floor(n * 0.2)];
  const th = Math.max(floor * 3, peak * 0.05);
  let a = 0; while (a < n && rms[a] < th) a++;
  let b = n - 1; while (b > a && rms[b] < th) b--;
  let s = Math.max(0, a * win - Math.round(0.18 * sr));
  let e = Math.min(data.length, (b + 1) * win + Math.round(0.28 * sr));
  e = Math.min(e, s + Math.round(3.6 * sr));
  const seg = data.slice(s, e);

  const outSr = 22050;
  const OAC = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  const off = new OAC(1, Math.ceil(seg.length * outSr / sr), outSr);
  const inBuf = off.createBuffer(1, seg.length, sr);
  inBuf.getChannelData(0).set(seg);
  const node = off.createBufferSource(); node.buffer = inBuf; node.connect(off.destination); node.start();
  const y = (await off.startRendering()).getChannelData(0);

  let pk = 0; for (let i = 0; i < y.length; i++) pk = Math.max(pk, Math.abs(y[i]));
  const gain = pk > 0 ? Math.min(6, 0.89 / pk) : 1;
  const lead = Math.round(0.12 * outSr), tail = Math.round(0.08 * outSr);
  const fi = Math.round(0.01 * outSr), fo = Math.round(0.08 * outSr);
  const out = new Float32Array(lead + y.length + tail);
  for (let i = 0; i < y.length; i++){
    let v = y[i] * gain;
    if (i < fi) v *= i / fi;
    if (i > y.length - fo) v *= (y.length - i) / fo;
    out[lead + i] = v;
  }
  return { wav: encodeWav(out, outSr), dur: Math.round(out.length / outSr * 10) / 10 };
}

export function encodeWav(f, sr){
  const n = f.length, buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf);
  const w = (o, str) => { for (let i = 0; i < str.length; i++) v.setUint8(o + i, str.charCodeAt(i)); };
  w(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); w(8, "WAVE"); w(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  w(36, "data"); v.setUint32(40, n * 2, true);
  for (let i = 0; i < n; i++){ const x = Math.max(-1, Math.min(1, f[i])); v.setInt16(44 + i * 2, x < 0 ? x * 0x8000 : x * 0x7fff, true); }
  const bytes = new Uint8Array(buf); let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}
