// Utilità comuni: nomi delle carte, dei posti, helper DOM.

export const POSTI = ["Nord", "Est", "Sud", "Ovest"];
export const SQUADRE = ["Squadra 1", "Squadra 2"];   // nomi predefiniti, il tavolo può cambiarli
export const AVATAR = ["🦊", "🐻", "🐸", "🦁", "🐼", "🐵", "🦉", "🐙", "🐱", "🐲", "🐢", "🦭"];
export const FRASI = ["Veloce?!?", "Di#p?@co", "Praticamente pari", "Che culo...", "Aperta come...",
  "Faccio una giocata un po' particolare", "Stai giocando con paura", "Sei MATTO?!", "Ma hai tutti gli assi??", "CHE CULO"];
export const SEMI = ["denari", "coppe", "spade", "bastoni"];
const NOMI_VALORE = { 1: "Asso", 2: "Due", 3: "Tre", 4: "Quattro", 5: "Cinque", 6: "Sei", 7: "Sette", 8: "Fante", 9: "Cavallo", 10: "Re" };
export const SIMBOLI = { denari: "◆", coppe: "♥", spade: "♠", bastoni: "♣" };

export const VARIANTI_DESC = {
  "Vanilla": "Regole base: prese, Scope, punti di mazzo, 2 di denari a −5, Bazziche e \"Che Palo!\".",
  "Heisenberg": "Come Vanilla + scambio segreto di una carta col compagno a ogni Turno, con \"Passa veloce\".",
  "Einstein": "Come Heisenberg + un tris col 7 bello vale 5 Scope invece di 7.",
  "Fermi": "Come Einstein + il 2 di denari vale −5 + punti di mazzo; Napoleone (tutti i denari) vale 10.",
  "Pascal": "Come Fermi + gli assi di chi ha chiamato Bazzica non pigliano tutto (valgono 1).",
  "Curie": "Come Pascal + Piccola (prendi la carta appena calata) e Grande (presa tutta dello stesso seme).",
  "Federico II": "Come Curie + Napola: Asso-2-3 di denari e seguenti valgono 1 punto ciascuno.",
  "Avogadro": "Come Federico II + ogni asso preso vale una Scopa.",
};

export const val = (c) => parseInt(c.slice(-2), 10);
export const seme = (c) => c.split("_")[0];
export const squadra = (s) => s % 2;

export function nomeCarta(c) {
  if (c === "denari_07") return "Sette bello";
  if (c === "denari_10") return "Re bello";
  return `${NOMI_VALORE[val(c)]} di ${seme(c)}`;
}
export const nomiCarte = (cs) => (cs && cs.length ? cs.map(nomeCarta).join(", ") : "nessuna");

export function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "html") e.innerHTML = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(e.dataset, v);
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const ch of children.flat()) {
    if (ch === null || ch === undefined || ch === false) continue;
    e.append(ch instanceof Node ? ch : document.createTextNode(String(ch)));
  }
  return e;
}

export const $ = (s, r = document) => r.querySelector(s);
export const $$ = (s, r = document) => [...r.querySelectorAll(s)];
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let toastTimer = null;
export function toast(msg, ms = 2800) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.remove("nascosto");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("nascosto"), ms);
}

export function store(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(key);
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch (e) { /* storage non disponibile */ }
  return null;
}
