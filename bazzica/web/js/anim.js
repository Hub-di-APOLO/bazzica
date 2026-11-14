// Animazioni ed effetti speciali (CSS + DOM).
import { el, sleep } from "./util.js";

const layer = () => document.getElementById("fx");
export let VELOCITA = 1; // moltiplicatore delle durate

export function centro(r) { return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; }

/** Fa volare un elemento carta da ``da`` (DOMRect) ad ``a`` (DOMRect). */
export async function vola(cartaEl, da, a, { durata = 450, fiamme = false, ritardo = 0, svanisci = false, ruota = 0 } = {}) {
  durata *= VELOCITA;
  const w = a.width || da.width, h = a.height || da.height;
  const box = el("div", { class: "volante" + (fiamme ? " in-fiamme" : "") });
  box.style.width = da.width + "px";
  box.style.height = da.height + "px";
  box.style.left = da.left + "px";
  box.style.top = da.top + "px";
  box.style.transitionDuration = `${durata}ms, 300ms`;
  if (fiamme) box.append(el("div", { class: "alone-fuoco" }));
  box.append(cartaEl);
  layer().append(box);
  if (ritardo) await sleep(ritardo);
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  const dx = a.left - da.left + (a.width - da.width) / 2;
  const dy = a.top - da.top + (a.height - da.height) / 2;
  const sc = w / da.width;
  box.style.transform = `translate(${dx}px, ${dy}px) scale(${sc}) rotate(${ruota}deg)`;
  if (svanisci) box.style.opacity = "0";
  let timer = null;
  if (fiamme) {
    timer = setInterval(() => {
      const r = box.getBoundingClientRect();
      for (let i = 0; i < 3; i++) fiammella(r.left + Math.random() * r.width, r.top + Math.random() * r.height);
    }, 30);
  }
  await sleep(durata + 30);
  if (timer) clearInterval(timer);
  box.remove();
}

export function fiammella(x, y) {
  const f = el("div", { class: "fiamma" });
  f.style.left = x + "px";
  f.style.top = y + "px";
  f.style.setProperty("--dx", (Math.random() * 30 - 15) + "px");
  const s = 0.7 + Math.random() * 1.2;
  f.style.width = f.style.height = 18 * s + "px";
  layer().append(f);
  setTimeout(() => f.remove(), 750);
}

export function banner(testo, classe = "", sotto = "", durata = 1600) {
  const b = el("div", { class: "banner-fx " + classe }, testo, sotto ? el("small", {}, sotto) : null);
  // i banner brevi (es. il cartello del Turno) completano l'animazione invece di sparire a metà
  if (durata < 1600) b.style.animationDuration = `${durata}ms`;
  document.body.append(b);
  setTimeout(() => b.remove(), durata + 100);
  return sleep(Math.min(durata, 1100) * VELOCITA);
}

export function scintille(x, y, n = 24, colore = null) {
  for (let i = 0; i < n; i++) {
    const s = el("div", { class: "scintilla" });
    const ang = Math.random() * Math.PI * 2, d = 60 + Math.random() * 140;
    s.style.left = x + "px";
    s.style.top = y + "px";
    s.style.setProperty("--dx", Math.cos(ang) * d + "px");
    s.style.setProperty("--dy", Math.sin(ang) * d + "px");
    if (colore) { s.style.background = colore; s.style.boxShadow = `0 0 8px ${colore}`; }
    document.body.append(s);
    setTimeout(() => s.remove(), 1050);
  }
}

export function fumetto(rect, testo, classe = "") {
  const f = el("div", { class: "fumetto" + (classe ? " " + classe : "") }, testo);
  const c = centro(rect);
  if (classe === "commento") {
    // commento di uno spettatore: parte dal contatore a sinistra e non esce mai dallo schermo
    f.style.left = Math.max(8, rect.left) + "px";
    f.style.top = Math.max(70, rect.top - 6) + "px";
  } else {
    f.style.left = Math.min(window.innerWidth - 120, Math.max(120, c.x)) + "px";
    f.style.top = Math.max(70, rect.top - 6) + "px";
  }
  document.body.append(f);
  setTimeout(() => f.remove(), 2500);
}

export function scuoti(elem) {
  elem.classList.remove("shake");
  void elem.offsetWidth;
  elem.classList.add("shake");
  setTimeout(() => elem.classList.remove("shake"), 500);
}

export function lampeggia(elems, classe = "evidenzia", ms = 500) {
  elems.forEach((e) => e && e.classList.add(classe));
  return sleep(ms * VELOCITA);
}

// ----------------------------------------------------------------- Piccola: velocissima
export function lineeVelocita(x, y) {
  const d = el("div", { class: "linee-velocita" });
  d.style.setProperty("--x", x + "px");
  d.style.setProperty("--y", y + "px");
  document.body.append(d);
  setTimeout(() => d.remove(), 600);
}

export function saetta(da, a) {
  const dx = a.x - da.x, dy = a.y - da.y;
  const s = el("div", { class: "saetta" });
  s.style.left = da.x + "px";
  s.style.top = da.y + "px";
  s.style.width = Math.hypot(dx, dy) + "px";
  s.style.transform = `rotate(${Math.atan2(dy, dx)}rad)`;
  document.body.append(s);
  setTimeout(() => s.remove(), 400);
}

export function sbuffi(x, y, n = 10) {
  for (let i = 0; i < n; i++) {
    const p = el("div", { class: "sbuffo" });
    const ang = Math.random() * Math.PI * 2, d = 40 + Math.random() * 60;
    p.style.left = x + "px";
    p.style.top = y + "px";
    p.style.setProperty("--dx", Math.cos(ang) * d + "px");
    p.style.setProperty("--dy", Math.sin(ang) * d + "px");
    document.body.append(p);
    setTimeout(() => p.remove(), 550);
  }
}

export function bannerZip(testo, sotto = "") {
  const b = el("div", { class: "banner-zip" }, testo, sotto ? el("small", {}, sotto) : null);
  document.body.append(b);
  setTimeout(() => b.remove(), 1100);
  return sleep(900 * VELOCITA);
}

// ----------------------------------------------------------------- Grande: pesantissima
export function vignetta() {
  const v = el("div", { class: "vignetta" });
  document.body.append(v);
  setTimeout(() => v.remove(), 2700);
}

/** Una carta enorme precipita dall'alto e si schianta sul punto ``dst`` (DOMRect). */
export async function macigno(cartaEl, dst, durata = 620) {
  durata *= VELOCITA;
  const c = centro(dst);
  const ombra = el("div", { class: "ombra-impatto" });
  ombra.style.left = c.x + "px";
  ombra.style.top = c.y + dst.height * 0.45 + "px";
  ombra.style.width = dst.width * 2.2 + "px";
  ombra.style.height = dst.width * 0.8 + "px";
  ombra.style.animationDuration = durata + "ms";
  document.body.append(ombra);
  const box = el("div", { class: "macigno" });
  box.style.left = dst.left + "px";
  box.style.top = dst.top + "px";
  box.style.width = dst.width + "px";
  box.style.height = dst.height + "px";
  box.style.transform = `translateY(${-window.innerHeight * 0.75}px) scale(3.2) rotate(-14deg)`;
  box.style.transition = `transform ${durata}ms cubic-bezier(.6,0,1,.6)`;
  box.append(cartaEl);
  document.body.append(box);
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  box.style.transform = "translateY(0) scale(1) rotate(0)";
  await sleep(durata);
  ombra.remove();
  return { box, c };
}

export function crepe(x, y, r = 170) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("class", "crepe");
  svg.setAttribute("width", r * 2);
  svg.setAttribute("height", r * 2);
  svg.style.left = x + "px";
  svg.style.top = y + "px";
  const n = 9;
  for (let i = 0; i < n; i++) {
    let ang = (i / n) * Math.PI * 2 + Math.random() * 0.4;
    let px = r, py = r, d = "M" + px + " " + py;
    const passi = 4 + Math.floor(Math.random() * 3);
    const lung = r * (0.55 + Math.random() * 0.45);
    for (let k = 0; k < passi; k++) {
      ang += (Math.random() - 0.5) * 0.9;
      px += Math.cos(ang) * (lung / passi);
      py += Math.sin(ang) * (lung / passi);
      d += ` L${px.toFixed(1)} ${py.toFixed(1)}`;
    }
    const p = document.createElementNS(ns, "path");
    p.setAttribute("d", d);
    p.style.animationDelay = Math.random() * 120 + "ms";
    p.style.strokeWidth = 3 + Math.random() * 4;
    svg.append(p);
  }
  document.body.append(svg);
  setTimeout(() => svg.remove(), 2900);
}

export function polvere(x, y, n = 18) {
  for (let i = 0; i < n; i++) {
    const p = el("div", { class: "polvere" });
    const lato = i % 2 ? 1 : -1;
    p.style.left = x + (Math.random() * 40 - 20) + "px";
    p.style.top = y + 20 + "px";
    p.style.setProperty("--dx", lato * (60 + Math.random() * 200) + "px");
    p.style.setProperty("--dy", -(Math.random() * 90) + "px");
    p.style.setProperty("--s", 2 + Math.random() * 3);
    p.style.animationDelay = Math.random() * 120 + "ms";
    document.body.append(p);
    setTimeout(() => p.remove(), 1500);
  }
}

export function terremoto(elem) {
  elem.classList.remove("terremoto");
  void elem.offsetWidth;
  elem.classList.add("terremoto");
  setTimeout(() => elem.classList.remove("terremoto"), 750);
}

export function bannerPesante(testo, sotto = "") {
  const b = el("div", { class: "banner-pesante" }, testo, sotto ? el("small", {}, sotto) : null);
  document.body.append(b);
  setTimeout(() => b.remove(), 2350);
  return b;
}

export function lacrima(rect, simbolo = "😱") {
  const l = el("div", { class: "lacrima" }, simbolo);
  l.style.left = rect.left + rect.width / 2 + "px";
  l.style.top = rect.top - 10 + "px";
  document.body.append(l);
  setTimeout(() => l.remove(), 2300);
}

// ----------------------------------------------------------------- festa e devastazione
const COLORI_FESTA = ["#ff4fa3", "#ffd23f", "#5ad1ff", "#7be37b", "#ff7a00", "#b28dff", "#ffffff"];

export function coriandoli(n = 80, durata = 2600) {
  for (let i = 0; i < n; i++) {
    const c = el("div", { class: "coriandolo" });
    c.style.left = Math.random() * 100 + "vw";
    c.style.background = COLORI_FESTA[i % COLORI_FESTA.length];
    c.style.setProperty("--dx", (Math.random() * 200 - 100) + "px");
    c.style.setProperty("--r", (Math.random() * 1440 - 720) + "deg");
    c.style.setProperty("--t", (durata * (0.6 + Math.random() * 0.6)) + "ms");
    c.style.animationDelay = Math.random() * 600 + "ms";
    if (i % 3 === 0) c.style.borderRadius = "50%";
    document.body.append(c);
    setTimeout(() => c.remove(), durata * 1.3 + 700);
  }
}

export function flash(colore = "#fff", t = 350) {
  const f = el("div", { class: "flash" });
  f.style.setProperty("--col", colore);
  f.style.setProperty("--t", t + "ms");
  document.body.append(f);
  setTimeout(() => f.remove(), t + 50);
}

export function raggi(colore = "rgba(255,79,163,.35)", t = 2600) {
  const r = el("div", { class: "raggi" });
  r.style.setProperty("--col", colore);
  r.style.setProperty("--t", t + "ms");
  document.body.append(r);
  setTimeout(() => r.remove(), t + 50);
}

export function onda(x, y, colore = "#fff", scala = 30) {
  const o = el("div", { class: "onda" });
  o.style.left = x + "px";
  o.style.top = y + "px";
  o.style.setProperty("--col", colore);
  o.style.setProperty("--s", scala);
  document.body.append(o);
  setTimeout(() => o.remove(), 950);
}

export function buio(t = 5000) {
  const b = el("div", { class: "buio" });
  b.style.setProperty("--t", t + "ms");
  document.body.append(b);
  setTimeout(() => b.remove(), t + 50);
}

export function fulmine() {
  const ns = "http://www.w3.org/2000/svg";
  const W = window.innerWidth, H = window.innerHeight;
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("class", "fulmine");
  svg.setAttribute("width", W);
  svg.setAttribute("height", H);
  svg.style.left = "0px";
  svg.style.top = "0px";
  let x = Math.random() * W, y = 0, d = `M${x} ${y}`;
  while (y < H * (0.6 + Math.random() * 0.4)) {
    x += Math.random() * 120 - 60;
    y += 30 + Math.random() * 50;
    d += ` L${x.toFixed(0)} ${y.toFixed(0)}`;
  }
  const p = document.createElementNS(ns, "path");
  p.setAttribute("d", d);
  svg.append(p);
  document.body.append(svg);
  setTimeout(() => svg.remove(), 520);
}

export function carteGiganti(elems, t = 2600, vortice = false) {
  const box = el("div", { class: "carte-giganti" + (vortice ? " vortice" : "") });
  box.style.setProperty("--t", t + "ms");
  elems.forEach((e) => { e.style.setProperty("--t", t + "ms"); box.append(e); });
  document.body.append(box);
  setTimeout(() => box.remove(), t + 400);
}

export function pioggiaCarte(fabbrica, n = 40, durata = 2200) {
  for (let i = 0; i < n; i++) {
    const w = el("div", { class: "pioggia-carta" });
    w.append(fabbrica(i));
    w.style.left = Math.random() * 100 + "vw";
    w.style.setProperty("--dx", (Math.random() * 300 - 150) + "px");
    w.style.setProperty("--r", (Math.random() * 1080 - 540) + "deg");
    w.style.setProperty("--t", durata * (0.7 + Math.random() * 0.5) + "ms");
    w.style.animationDelay = Math.random() * 900 + "ms";
    document.body.append(w);
    setTimeout(() => w.remove(), durata * 1.3 + 1000);
  }
}

export function fuocoArtificio(x, y, n = 36) {
  const col = COLORI_FESTA[Math.floor(Math.random() * COLORI_FESTA.length)];
  for (let i = 0; i < n; i++) {
    const s = el("div", { class: "fuoco-artificio" });
    const ang = (i / n) * Math.PI * 2, d = 80 + Math.random() * 90;
    s.style.left = x + "px";
    s.style.top = y + "px";
    s.style.background = col;
    s.style.boxShadow = `0 0 8px ${col}, 0 0 16px ${col}`;
    s.style.setProperty("--dx", Math.cos(ang) * d + "px");
    s.style.setProperty("--dy", Math.sin(ang) * d + "px");
    document.body.append(s);
    setTimeout(() => s.remove(), 1250);
  }
}

export function fuochi(n = 6, intervallo = 280) {
  for (let i = 0; i < n; i++) {
    setTimeout(() => fuocoArtificio(window.innerWidth * (0.15 + Math.random() * 0.7), window.innerHeight * (0.15 + Math.random() * 0.4)), i * intervallo);
  }
}

/** Parata delle carte di denari: arrivano una alla volta e si dispongono ad arco. */
export async function parataDenari(elemsCarte, passo = 260, onCarta = null) {
  const box = el("div", { class: "parata-denari" });
  document.body.append(box);
  const n = elemsCarte.length;
  const W = box.getBoundingClientRect().width, H = box.getBoundingClientRect().height;
  elemsCarte.forEach((c) => box.append(c));
  await sleep(50);
  for (let i = 0; i < n; i++) {
    const c = elemsCarte[i];
    const t = n === 1 ? 0.5 : i / (n - 1);
    const cw = c.getBoundingClientRect().width || 80;
    const x = t * (W - cw);
    const y = H * 0.55 - Math.sin(t * Math.PI) * H * 0.45;
    const rot = (t - 0.5) * 50;
    c.classList.add("in");
    c.style.transform = `translate(${x}px, ${y}px) rotate(${rot}deg) scale(1)`;
    if (onCarta) onCarta(i);
    await sleep(passo * VELOCITA);
  }
  return box;
}

// ----------------------------------------------------------------- Scopa: la spazzola
/** Una spazzola attraversa il tavolo da sinistra a destra lasciando polvere e scintille. */
export async function spazzola(rect, durata = 900) {
  durata *= VELOCITA;
  const s = el("div", { class: "spazzola" }, "🧹");
  const y = rect.top + rect.height / 2;
  s.style.top = y + "px";
  s.style.left = rect.left - 40 + "px";
  s.style.setProperty("--dist", rect.width + 80 + "px");
  s.style.animationDuration = durata + "ms";
  document.body.append(s);
  const t0 = performance.now();
  const timer = setInterval(() => {
    const k = Math.min(1, (performance.now() - t0) / durata);
    const x = rect.left - 40 + k * (rect.width + 80);
    for (let i = 0; i < 2; i++) {
      const p = el("div", { class: "polverina" });
      p.style.left = x - 10 + Math.random() * 20 + "px";
      p.style.top = y + 10 + Math.random() * 30 + "px";
      p.style.setProperty("--dx", 30 + Math.random() * 40 + "px");
      p.style.setProperty("--dy", -(10 + Math.random() * 40) + "px");
      document.body.append(p);
      setTimeout(() => p.remove(), 700);
    }
  }, 35);
  await sleep(durata);
  clearInterval(timer);
  s.remove();
}

/** Banner con le lettere che cadono una alla volta e rimbalzano. */
export function bannerLettere(testo, sotto = "", classe = "") {
  const b = el("div", { class: "banner-lettere " + classe });
  [...testo].forEach((ch, i) => {
    const l = el("span", { class: "lettera" }, ch);
    l.style.animationDelay = i * 70 + "ms";
    l.style.setProperty("--rot", (Math.random() * 24 - 12) + "deg");
    b.append(l);
  });
  if (sotto) b.append(el("small", {}, sotto));
  document.body.append(b);
  setTimeout(() => b.remove(), 1900);
  return sleep(1300 * VELOCITA);
}

// ----------------------------------------------------------------- prese buone
/** La carta presa sale al centro, brilla con la sua scritta e poi vola nel mazzo delle prese. */
export async function cartaDiGloria(cartaEl, testo, stile, dest, durata = 1100) {
  durata *= VELOCITA;
  const box = el("div", { class: "gloria " + stile });
  const alone = el("div", { class: "gloria-alone" });
  box.append(alone, cartaEl);
  if (stile === "re") box.append(el("div", { class: "gloria-corona" }, "👑"));
  box.append(el("div", { class: "gloria-testo" }, testo));
  box.style.setProperty("--durata", durata + "ms");
  document.body.append(box);
  const r = box.getBoundingClientRect();
  scintille(r.left + r.width / 2, r.top + r.height * 0.4, stile === "primiera" ? 12 : 26,
    stile === "primiera" ? "#ff8a5c" : "#ffd23f");
  await sleep(durata * 0.75);
  // vola nel mazzo delle prese
  const c = fx_centro(dest), cr = fx_centro(cartaEl.getBoundingClientRect());
  box.style.animation = "none";                       // l'animazione d'ingresso non deve bloccare il transform
  box.style.transform = "translate(-50%, -50%)";
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  box.style.transition = `transform ${durata * 0.25}ms ease-in, opacity ${durata * 0.25}ms ease-in`;
  box.style.transform = `translate(calc(-50% + ${c.x - cr.x}px), calc(-50% + ${c.y - cr.y}px)) scale(.25)`;
  box.style.opacity = "0.2";
  await sleep(durata * 0.25);
  box.remove();
}
function fx_centro(r) { return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; }

// ----------------------------------------------------------------- "Striscia"
/** Un dorso di carta strisciato avanti e indietro sul panno, per mettere fretta. */
export function cartaStrisciata(cartaEl, x, y) {
  const w = el("div", { class: "carta-strisciata" });
  w.append(cartaEl);
  w.style.left = x + "px";
  w.style.top = y + "px";
  document.body.append(w);
  setTimeout(() => w.remove(), 1700);
}

/** L'elemento trema per un attimo (chi subisce la Striscia). */
export function trema(elemento, durata = 900) {
  if (!elemento) return;
  elemento.classList.remove("trema");
  void elemento.offsetWidth;            // riparte anche se stava già tremando
  elemento.classList.add("trema");
  setTimeout(() => elemento.classList.remove("trema"), durata);
}
