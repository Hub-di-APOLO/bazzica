// Rendering delle carte: immagini in assets/cards (o mapping.json) con fallback CSS.
import { el, val, seme, SIMBOLI, nomeCarta } from "./util.js";

let IMMAGINI = {};
const VALORI_BREVI = { 1: "A", 8: "F", 9: "C", 10: "R" };

export async function caricaCarte() {
  try {
    const r = await fetch("/api/carte");
    const d = await r.json();
    IMMAGINI = d.carte || {};
    // precarica
    Object.values(IMMAGINI).forEach((u) => { const i = new Image(); i.src = u; });
    return d;
  } catch (e) {
    IMMAGINI = {};
    return { carte: {}, mancanti: [], suoni: [] };
  }
}

export function carta(c, opts = {}) {
  // c: id carta oppure null/"?" per il dorso
  if (!c || c === "?" || opts.dorso) return dorso(opts);
  const url = IMMAGINI[c];
  const e = el("div", { class: "carta" + (opts.class ? " " + opts.class : ""), title: nomeCarta(c), dataset: { carta: c } });
  if (url) {
    e.classList.add("img");
    e.style.backgroundImage = `url("${url}")`;
  } else {
    const s = seme(c), v = val(c);
    e.classList.add("css", "s-" + s);
    e.append(el("span", { class: "cv" }, VALORI_BREVI[v] || v), el("span", { class: "cs" }, SIMBOLI[s]));
  }
  return e;
}

export function dorso(opts = {}) {
  const url = IMMAGINI["dorso"];
  const e = el("div", { class: "carta dorso" + (opts.class ? " " + opts.class : "") });
  if (url) { e.classList.add("img"); e.style.backgroundImage = `url("${url}")`; }
  else e.classList.add("dorso-css");
  return e;
}
