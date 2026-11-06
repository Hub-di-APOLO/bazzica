// Suoni sintetizzati con Web Audio API; se in assets/sounds/ esiste un file con lo
// stesso nome (es. scopa.mp3) viene usato quello.
import { store } from "./util.js";

let ctx = null;
let muto = store("bazzica_muto") === "1";
const FILE = {};

const PRECARICATI = {};

export function impostaFileSuoni(nomi) {
  for (const n of nomi || []) {
    const base = n.replace(/\.[^.]+$/, "");
    FILE[base] = "/assets/sounds/" + n;
    // precarica, così il suono parte senza ritardo la prima volta
    try { const el = new Audio(FILE[base]); el.preload = "auto"; el.load(); PRECARICATI[base] = el; } catch (e) { /* niente audio */ }
  }
}

export const isMuto = () => muto;
export function setMuto(v) { muto = v; store("bazzica_muto", v ? "1" : "0"); }

function ac() {
  if (!ctx) {
    const C = window.AudioContext || window.webkitAudioContext;
    if (!C) return null;
    ctx = new C();
  }
  if (ctx.state === "suspended") ctx.resume();
  return ctx;
}
// uscita comune con compressore: le folle sommano molte voci e non devono distorcere
let master = null;
function uscita() {
  const a = ac(); if (!a) return null;
  if (!master) {
    master = a.createDynamicsCompressor();
    master.threshold.value = -14; master.knee.value = 12; master.ratio.value = 6;
    master.attack.value = 0.005; master.release.value = 0.25;
    master.connect(a.destination);
  }
  return master;
}
// sblocca l'audio al primo gesto
window.addEventListener("pointerdown", () => ac(), { once: true });

function tono(freq, t0, dur, { tipo = "sine", vol = 0.2, slide = 0 } = {}) {
  const a = ac(); if (!a) return;
  const o = a.createOscillator(), g = a.createGain();
  o.type = tipo;
  o.frequency.setValueAtTime(freq, a.currentTime + t0);
  if (slide) o.frequency.exponentialRampToValueAtTime(Math.max(30, freq * slide), a.currentTime + t0 + dur);
  g.gain.setValueAtTime(0.0001, a.currentTime + t0);
  g.gain.exponentialRampToValueAtTime(vol, a.currentTime + t0 + 0.012);
  g.gain.exponentialRampToValueAtTime(0.0001, a.currentTime + t0 + dur);
  o.connect(g).connect(uscita());
  o.start(a.currentTime + t0);
  o.stop(a.currentTime + t0 + dur + 0.05);
}

function rumore(t0, dur, { vol = 0.25, freq = 2000, q = 1, tipo = "bandpass", sweep = 0 } = {}) {
  const a = ac(); if (!a) return;
  const n = Math.floor(a.sampleRate * dur);
  const buf = a.createBuffer(1, n, a.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n);
  const s = a.createBufferSource(); s.buffer = buf;
  const f = a.createBiquadFilter(); f.type = tipo; f.Q.value = q;
  f.frequency.setValueAtTime(freq, a.currentTime + t0);
  if (sweep) f.frequency.exponentialRampToValueAtTime(freq * sweep, a.currentTime + t0 + dur);
  const g = a.createGain(); g.gain.value = vol;
  s.connect(f).connect(g).connect(uscita());
  s.start(a.currentTime + t0);
}

// ----------------------------------------------------------------- folla da stadio
// Formanti (F1, F2) delle vocali cantate.
const VOCALI = { a: [730, 1090], e: [530, 1840], i: [300, 2200], o: [470, 820], u: [320, 800] };

/** Una voce cantata: dente di sega con vibrato e leggero glissando, filtrata da due formanti. */
function voce(t0, durata, freq, vocale, { vol = 0.05, glide = 1, attacco = 0.06 } = {}) {
  const a = ac(); if (!a) return;
  const T = a.currentTime + t0;
  const o = a.createOscillator(); o.type = "sawtooth";
  o.frequency.setValueAtTime(freq, T);
  if (glide !== 1) o.frequency.exponentialRampToValueAtTime(freq * glide, T + durata);
  const lfo = a.createOscillator(), lg = a.createGain();
  lfo.frequency.value = 4.5 + Math.random() * 2; lg.gain.value = freq * 0.012;
  lfo.connect(lg).connect(o.frequency);
  const g = a.createGain();
  g.gain.setValueAtTime(0.0001, T);
  g.gain.linearRampToValueAtTime(vol, T + attacco + Math.random() * 0.05);
  g.gain.setValueAtTime(vol, T + Math.max(attacco, durata - 0.12));
  g.gain.linearRampToValueAtTime(0.0001, T + durata);
  const [f1, f2] = VOCALI[vocale];
  for (const [f, q, k] of [[f1, 6, 1], [f2, 8, 0.6]]) {
    const bp = a.createBiquadFilter(); bp.type = "bandpass"; bp.frequency.value = f; bp.Q.value = q;
    const kg = a.createGain(); kg.gain.value = k;
    o.connect(bp).connect(kg).connect(g);
  }
  g.connect(uscita());
  o.start(T); lfo.start(T);
  o.stop(T + durata + 0.05); lfo.stop(T + durata + 0.05);
}

/** Un coro di tante voci leggermente stonate e sfasate, come una curva di stadio. */
function coro(t0, durata, freq, vocale, { voci = 16, vol = 0.13, glide = 1, sparpaglia = 0.08 } = {}) {
  for (let i = 0; i < voci; i++) {
    const ottava = i % 5 === 0 ? 0.5 : 1;                       // qualche voce più grave
    const stonato = freq * ottava * (1 + (Math.random() - 0.5) * 0.035);
    voce(t0 + Math.random() * sparpaglia, durata * (0.9 + Math.random() * 0.2), stonato, vocale, { vol, glide: glide * (1 + (Math.random() - 0.5) * 0.04) });
  }
}

/** Brusio/boato di folla: rumore con modulazioni lente e casuali (tante bocche insieme). */
function boato(t0, durata, { vol = 0.6, picco = 0.25, freq = 1000 } = {}) {
  const a = ac(); if (!a) return;
  const n = Math.floor(a.sampleRate * durata);
  const buf = a.createBuffer(2, n, a.sampleRate);
  for (let ch = 0; ch < 2; ch++) {
    const d = buf.getChannelData(ch);
    let mod = 0.6, obiettivo = 0.6;
    for (let i = 0; i < n; i++) {
      if (i % 2200 === 0) obiettivo = 0.35 + Math.random() * 0.65;
      mod += (obiettivo - mod) * 0.0008;
      const t = i / n;
      const inv = t < picco ? t / picco : 1 - (t - picco) / (1 - picco);
      d[i] = (Math.random() * 2 - 1) * mod * Math.pow(Math.max(inv, 0), 1.3);
    }
  }
  const src = a.createBufferSource(); src.buffer = buf;
  const bp = a.createBiquadFilter(); bp.type = "bandpass"; bp.frequency.value = freq; bp.Q.value = 0.6;
  const ls = a.createBiquadFilter(); ls.type = "lowshelf"; ls.frequency.value = 300; ls.gain.value = 6;
  const g = a.createGain(); g.gain.value = vol;
  src.connect(bp).connect(ls).connect(g).connect(uscita());
  src.start(a.currentTime + t0);
}

/** "Ooooh!" di stupore: tante voci che salgono e poi scendono sulla vocale O. */
function ooh(t0, durata = 1.6, vol = 0.16, voci = 18) {
  for (let i = 0; i < voci; i++) {
    const f = 170 + Math.random() * 190;
    const T = t0 + Math.random() * 0.12;
    voce(T, durata * 0.4, f, "o", { vol, glide: 1.18 });
    voce(T + durata * 0.38, durata * 0.62, f * 1.18, "o", { vol, glide: 0.62 });
  }
  boato(t0, durata, { vol: 0.1, picco: 0.35, freq: 700 });
}

/** Applausi: molti battiti di mani brevi e casuali. */
function applausi(t0, durata, densita = 60, vol = 0.22) {
  const n = Math.floor(durata * densita);
  for (let i = 0; i < n; i++) {
    const t = t0 + Math.random() * durata;
    const sfuma = 1 - (t - t0) / durata * 0.6;
    rumore(t, 0.025 + Math.random() * 0.02, { vol: vol * sfuma * (0.5 + Math.random() * 0.5), freq: 1200 + Math.random() * 1800, q: 1.5 });
  }
}

/** Battimani ritmati della curva: clap-clap, clap-clap-clap. */
function battimani(t0, ripetizioni = 1, vol = 0.5) {
  const schema = [0, 0.28, 0.75, 1.0, 1.25];
  for (let r = 0; r < ripetizioni; r++) {
    for (const s0 of schema) {
      for (let k = 0; k < 18; k++) rumore(t0 + r * 1.7 + s0 + Math.random() * 0.03, 0.04, { vol: vol / 6, freq: 1500 + Math.random() * 1200, q: 1.2 });
    }
  }
}

/** Coro "Baz-zi-caaa!" della curva (melodia originale: tre note, l'ultima tenuta). */
function coroBazzica(t0, volte = 1, voci = 20) {
  const nota = [392, 392, 523.25];
  for (let k = 0; k < volte; k++) {
    const t = t0 + k * 1.7;
    coro(t, 0.24, nota[0], "a", { voci });
    coro(t + 0.28, 0.24, nota[1], "i", { voci });
    coro(t + 0.56, 0.9, nota[2], "a", { voci, glide: 1.03 });
  }
}

/** Trombetta da stadio. */
function trombetta(t0, durata = 0.8, vol = 0.12) {
  [466, 554, 698].forEach((f) => tono(f, t0, durata, { tipo: "sawtooth", vol: vol / 3 }));
}

// ----------------------------------------------------------------- spazzola, campana, ottoni
/** Un colpo di spazzola sul panno: rumore che passa da grave ad acuto, con le setole che crepitano. */
function spazzolata(t0, durata, forza = 1) {
  const a = ac(); if (!a) return;
  const T = a.currentTime + t0;
  const n = Math.floor(a.sampleRate * durata);
  const buf = a.createBuffer(1, n, a.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < n; i++) {
    const k = i / n;
    const inv = Math.sin(Math.PI * Math.min(1, k * 1.15)) ** 0.7;           // sale e scende
    const setole = Math.random() < 0.012 ? (Math.random() * 2 - 1) * 2.5 : 0; // crepitio
    d[i] = ((Math.random() * 2 - 1) + setole) * inv;
  }
  const s = a.createBufferSource(); s.buffer = buf;
  const bp = a.createBiquadFilter(); bp.type = "bandpass"; bp.Q.value = 0.9;
  bp.frequency.setValueAtTime(1800, T); bp.frequency.exponentialRampToValueAtTime(5200, T + durata);
  const hp = a.createBiquadFilter(); hp.type = "highpass"; hp.frequency.value = 700;
  const g = a.createGain(); g.gain.value = 0.55 * forza;
  s.connect(bp).connect(hp).connect(g).connect(uscita());
  s.start(T);
}

/** Campana/campanello: parziali inarmoniche che si spengono lentamente. */
function campana(t0, f, vol = 0.2) {
  [[1, 1], [2.76, 0.5], [5.4, 0.25], [8.9, 0.12]].forEach(([k, v]) => tono(f * k, t0, 1.4 / Math.sqrt(k), { vol: vol * v }));
}

/** Nota di ottone (tromba): dente di sega filtrato con apertura del filtro. */
function ottone(f, t0, durata, vol = 0.12) {
  const a = ac(); if (!a) return;
  const T = a.currentTime + t0;
  const o = a.createOscillator(); o.type = "sawtooth"; o.frequency.value = f;
  const lp = a.createBiquadFilter(); lp.type = "lowpass"; lp.Q.value = 2;
  lp.frequency.setValueAtTime(600, T); lp.frequency.linearRampToValueAtTime(3200, T + 0.06); lp.frequency.linearRampToValueAtTime(1800, T + durata);
  const g = a.createGain();
  g.gain.setValueAtTime(0.0001, T); g.gain.linearRampToValueAtTime(vol, T + 0.03);
  g.gain.setValueAtTime(vol, T + durata - 0.05); g.gain.linearRampToValueAtTime(0.0001, T + durata);
  o.connect(lp).connect(g).connect(uscita());
  o.start(T); o.stop(T + durata + 0.05);
}

const SINTESI = {
  carta: () => rumore(0, 0.09, { vol: 0.35, freq: 2600, q: 0.8 }),
  distribuzione: () => { for (let i = 0; i < 6; i++) rumore(i * 0.07, 0.06, { vol: 0.25, freq: 3000 }); },
  presa: () => { rumore(0, 0.16, { vol: 0.3, freq: 1500, sweep: 0.5 }); },
  // Scopa: tre colpi di spazzola sul panno e un tintinnio finale
  scopa: () => { spazzolata(0, 0.32, 0.9); spazzolata(0.3, 0.3, 0.8); spazzolata(0.58, 0.5, 1.0); [2093, 2637, 3136].forEach((f, i) => tono(f, 1.05 + i * 0.06, 0.25, { vol: 0.05 })); },
  // carta strisciata sul panno: tre sfregamenti secchi
  striscia: () => { [0, 0.26, 0.52, 0.78].forEach((t, i) => rumore(t, 0.2, { vol: 0.35, freq: i % 2 ? 2600 : 1900, q: 1.4, sweep: i % 2 ? 0.7 : 1.4 })); },
  // ticchettio del timer
  tic: () => { tono(1800, 0, 0.05, { tipo: "square", vol: 0.06 }); },
  // prese buone
  settebello: () => { campana(0, 1568, 0.22); campana(0.14, 2093, 0.2); campana(0.28, 3136, 0.16); },
  rebello: () => { [392, 523.25, 659.25].forEach((f, i) => ottone(f, i * 0.13, i === 2 ? 0.7 : 0.14)); ottone(784, 0.39, 0.7); },
  sette: () => { tono(1318.5, 0, 0.16, { tipo: "triangle", vol: 0.3 }); tono(1975.5, 0.09, 0.35, { tipo: "triangle", vol: 0.26 }); },
  bazzica: () => { [392, 523, 659, 784, 659, 1047].forEach((f, i) => tono(f, i * 0.1, 0.32, { tipo: "square", vol: 0.08 })); tono(131, 0, 0.8, { tipo: "sawtooth", vol: 0.05 }); },
  // Piccola: "zip" fulmineo verso l'alto + due blip rapidissimi
  piccola: () => { tono(400, 0, 0.16, { tipo: "sawtooth", vol: 0.08, slide: 6 }); rumore(0, 0.18, { vol: 0.35, freq: 1500, sweep: 6, q: 3 }); tono(1760, 0.16, 0.05, { vol: 0.15 }); tono(2350, 0.22, 0.06, { vol: 0.15 }); },
  // Grande: caduta (sibilo che scende), poi botto profondo e rimbombo
  grandeCaduta: () => { tono(1400, 0, 0.6, { tipo: "sine", vol: 0.08, slide: 0.2 }); rumore(0, 0.6, { vol: 0.15, freq: 3000, sweep: 0.15, q: 2 }); },
  grande: () => { tono(110, 0, 1.2, { tipo: "sine", vol: 0.6, slide: 0.3 }); tono(55, 0, 1.6, { tipo: "triangle", vol: 0.5, slide: 0.6 }); rumore(0, 0.9, { vol: 0.9, freq: 300, tipo: "lowpass", sweep: 0.3, q: 1 }); rumore(0.05, 1.4, { vol: 0.4, freq: 120, tipo: "lowpass", q: 0.5 }); for (let i = 0; i < 6; i++) rumore(0.15 + i * 0.12, 0.08, { vol: 0.25, freq: 900 + Math.random() * 1500 }); [196, 185, 175, 165].forEach((f, i) => tono(f, 1.0 + i * 0.28, 0.4, { tipo: "triangle", vol: 0.1 })); },
  asso: () => { tono(660, 0, 0.15, { tipo: "triangle", vol: 0.18 }); tono(990, 0.08, 0.25, { tipo: "triangle", vol: 0.18 }); },
  napola: () => { [523, 659, 784, 1047, 1319, 1568].forEach((f, i) => tono(f, i * 0.09, 0.6, { tipo: "triangle", vol: 0.13 })); },
  // Bazziche: sempre più grosse
  // Bazziche: folla dello stadio, sempre più scatenata
  bazzica2: () => { ooh(0, 1.6); applausi(1.0, 1.2, 35, 0.08); },
  bazzica3: () => { ooh(0, 1.4); boato(1.0, 2.6, { vol: 0.35, picco: 0.2 }); applausi(1.1, 2.2, 60, 0.1); },
  bazzica5: () => { ooh(0, 1.2, 0.17, 22); boato(0.9, 4.2, { vol: 0.35, picco: 0.15 }); trombetta(1.0, 0.7); applausi(1.0, 3, 70, 0.1); coroBazzica(1.8, 1, 18); battimani(1.8, 1, 0.45); },
  tamburo: () => { for (let i = 0; i < 26; i++) rumore(i * 0.045, 0.05, { vol: 0.15 + i * 0.012, freq: 180, tipo: "lowpass", q: 2 }); boato(0, 1.4, { vol: 0.25, picco: 0.95, freq: 600 }); },
  bazzica7: () => {
    // boato esplosivo, trombette, poi la curva intera canta "Baz-zi-caaa!" due volte con i battimani
    boato(0, 6.5, { vol: 0.45, picco: 0.08, freq: 1100 });
    boato(0, 6.5, { vol: 0.25, picco: 0.1, freq: 450 });
    tono(45, 0, 1.6, { tipo: "sine", vol: 0.5, slide: 0.6 });
    trombetta(0.15, 0.6, 0.16); trombetta(0.85, 0.9, 0.16);
    applausi(0.2, 6, 100, 0.1);
    coroBazzica(1.6, 2, 26);
    battimani(1.6, 2, 0.6);
    trombetta(5.0, 1.2, 0.14);
  },
  tuono: () => { rumore(0, 1.4, { vol: 0.9, freq: 120, tipo: "lowpass", sweep: 0.5, q: 0.7 }); rumore(0, 0.15, { vol: 0.7, freq: 2500, tipo: "highpass" }); },
  moneta: () => { tono(1568, 0, 0.08, { tipo: "square", vol: 0.07 }); tono(2093, 0.07, 0.25, { tipo: "square", vol: 0.07 }); },
  napoleone: () => { [392, 392, 392, 523, 659, 784, 1047].forEach((f, i) => tono(f, i * 0.16, i === 6 ? 1.2 : 0.18, { tipo: "square", vol: 0.09 })); [523, 659, 784].forEach((f) => tono(f, 1.1, 1.5, { tipo: "triangle", vol: 0.12 })); },
  festa: () => { for (let i = 0; i < 8; i++) { rumore(i * 0.3, 0.25, { vol: 0.4, freq: 900, sweep: 4 }); rumore(i * 0.3 + 0.25, 0.4, { vol: 0.5, freq: 2500, tipo: "highpass" }); } },
  triste: () => { [392, 370, 349, 330].forEach((f, i) => tono(f, i * 0.35, i === 3 ? 0.9 : 0.35, { tipo: "sawtooth", vol: 0.07, slide: i === 3 ? 0.94 : 1 })); },
  palo: () => { tono(300, 0, 0.35, { tipo: "sine", vol: 0.3, slide: 2.2 }); tono(660, 0.3, 0.25, { tipo: "sine", vol: 0.2, slide: 0.6 }); },
  fuoco: () => { rumore(0, 0.9, { vol: 0.5, freq: 400, tipo: "lowpass", sweep: 5, q: 2 }); for (let i = 0; i < 10; i++) rumore(0.05 + Math.random() * 0.7, 0.03, { vol: 0.3, freq: 5000 }); tono(90, 0, 0.5, { tipo: "sawtooth", vol: 0.08, slide: 0.5 }); },
  passa: () => rumore(0, 0.18, { vol: 0.25, freq: 1800, sweep: 2 }),
  turno: () => tono(740, 0, 0.12, { tipo: "sine", vol: 0.12 }),
  fineMano: () => { [392, 494, 587].forEach((f) => tono(f, 0, 0.9, { tipo: "triangle", vol: 0.1 })); },
  vittoria: () => { [523, 523, 523, 659, 587, 659, 784].forEach((f, i) => tono(f, i * 0.14, 0.3, { tipo: "square", vol: 0.08 })); },
};

export function suona(nome) {
  if (muto) return;
  if (FILE[nome]) {
    try {
      const base = PRECARICATI[nome];
      const a = base ? base.cloneNode(true) : new Audio(FILE[nome]);
      a.volume = 0.9;
      a.play().catch(() => {});
      return;
    } catch (e) { /* fallback alla sintesi */ }
  }
  try { SINTESI[nome] && SINTESI[nome](); } catch (e) { /* audio non disponibile */ }
}
