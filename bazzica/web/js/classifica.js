// Pagina "Classifica": eLE dei giocatori con account e grafico dell'andamento (SVG, senza librerie).
import { el, $, apiGet, testoEle } from "./util.js";

const COLORI = ["#e4572e", "#2e86ab", "#3bb273", "#f3a712", "#8e44ad", "#d81e5b", "#16a085", "#7f8c8d",
  "#c0392b", "#2c3e50", "#a3cb38", "#fd7272"];
const SVG = "http://www.w3.org/2000/svg";

function svg(tag, attrs = {}, ...figli) {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  for (const f of figli) e.append(f);
  return e;
}

function coloreDi(nome) {
  let h = 0;
  for (const c of nome.toLowerCase()) h = (h * 31 + c.codePointAt(0)) >>> 0;
  return COLORI[h % COLORI.length];
}

export async function mostraClassifica() {
  const box = $("#classifica-contenuto");
  box.innerHTML = "Caricamento…";
  let d;
  try { d = await apiGet("/api/classifica"); } catch (e) { box.textContent = e.message; return; }
  box.innerHTML = "";
  const giocatori = d.giocatori;
  if (!giocatori.length) {
    box.append(el("p", { class: "vuoto" }, "Nessun account ancora. Crea il tuo dalla lobby con \"Accedi\"."));
    return;
  }
  // colore fisso per giocatore (non cambia quando cambia la classifica)
  const colore = new Map(giocatori.map((g) => [g.nome, coloreDi(g.nome)]));
  const tab = el("table", { class: "tab-classifica" },
    el("tr", {}, ...["#", "Giocatore", "eLE", "Partite", "V", "P", "S"].map((h) => el("th", {}, h))));
  let pos = 0;
  for (const g of giocatori) {
    const haGiocato = g.partite > 0;
    if (haGiocato) pos += 1;
    tab.append(el("tr", { class: haGiocato ? "" : "senza-partite" },
      el("td", {}, haGiocato ? pos : "–"),
      el("td", { class: "cl-nome" }, el("span", { class: "pallino", style: `background:${colore.get(g.nome)}` }), `${g.avatar || "🙂"} ${g.nome}`),
      el("td", { class: "cl-ele" }, testoEle(g)),
      el("td", {}, g.partite), el("td", {}, g.vittorie), el("td", {}, g.pareggi), el("td", {}, g.sconfitte)));
  }
  box.append(tab);
  box.append(el("p", { class: "nota" }, "Il \"?\" indica i giocatori nelle prime 15 partite valutate (eLE provvisorio). " +
    "V/P/S = vittorie, pareggi, sconfitte. Regole complete dell'eLE nel regolamento."));
  const conPartite = giocatori.filter((g) => g.andamento.length);
  if (conPartite.length) {
    box.append(el("h3", {}, "Andamento"));
    box.append(grafico(conPartite, colore, d.iniziale));
  }
}

/** Grafico a linee: in orizzontale le partite valutate in ordine di tempo, in verticale l'eLE. */
function grafico(giocatori, colore, iniziale) {
  const partite = [...new Set(giocatori.flatMap((g) => g.andamento.map((a) => a.partita)))];
  const ordine = new Map();
  giocatori.flatMap((g) => g.andamento).sort((a, b) => (a.fine < b.fine ? -1 : a.fine > b.fine ? 1 : a.partita - b.partita))
    .forEach((a) => { if (!ordine.has(a.partita)) ordine.set(a.partita, ordine.size + 1); });
  const n = Math.max(1, partite.length);
  const serie = giocatori.map((g) => {
    const primo = ordine.get(g.andamento[0].partita);
    return { g, punti: [[primo - 1, iniziale], ...g.andamento.map((a) => [ordine.get(a.partita), a.ele])] };
  });
  const valori = serie.flatMap((s) => s.punti.map((p) => p[1]));
  let min = Math.min(...valori), max = Math.max(...valori);
  if (max - min < 40) { const c = (max + min) / 2; min = c - 20; max = c + 20; }
  min = Math.floor((min - 5) / 10) * 10; max = Math.ceil((max + 5) / 10) * 10;
  // sul telefono un disegno più stretto: le scritte restano leggibili
  const stretto = window.innerWidth < 600;
  const W = stretto ? 360 : 640, H = stretto ? 240 : 300, sx = 40, dx = 12, sy = 14, gy = 26;
  const X = (i) => sx + (i / n) * (W - sx - dx);
  const Y = (v) => sy + (1 - (v - min) / (max - min)) * (H - sy - gy);
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "grafico-ele", role: "img", "aria-label": "Andamento dell'eLE" });
  const passo = Math.max(10, Math.ceil((max - min) / 5 / 10) * 10);
  for (let v = Math.ceil(min / passo) * passo; v <= max; v += passo) {
    s.append(svg("line", { x1: sx, x2: W - dx, y1: Y(v), y2: Y(v), class: "griglia" }));
    const t = svg("text", { x: sx - 6, y: Y(v) + 4, class: "asse", "text-anchor": "end" });
    t.textContent = v;
    s.append(t);
  }
  const passoX = Math.max(1, Math.ceil(n / 8));
  for (let i = 0; i <= n; i += passoX) {
    const t = svg("text", { x: X(i), y: H - 8, class: "asse", "text-anchor": "middle" });
    t.textContent = i;
    s.append(t);
  }
  const linee = new Map();
  for (const { g, punti } of serie) {
    const gruppo = svg("g", { class: "serie", style: `--c:${colore.get(g.nome)}` });
    gruppo.append(svg("polyline", { points: punti.map(([i, v]) => `${X(i)},${Y(v)}`).join(" ") }));
    for (const [i, v] of punti.slice(1)) {
      const c = svg("circle", { cx: X(i), cy: Y(v), r: 3.5 });
      const tt = svg("title");
      tt.textContent = `${g.nome}: ${Math.round(v)} dopo la partita ${i}`;
      c.append(tt);
      gruppo.append(c);
    }
    s.append(gruppo);
    linee.set(g.nome, gruppo);
  }
  // legenda: toccando un nome si evidenzia la sua linea (comodo sul telefono)
  let evidenziato = null;
  const legenda = el("div", { class: "legenda" });
  for (const { g } of serie) {
    const b = el("button", { class: "chip-legenda", style: `--c:${colore.get(g.nome)}` }, el("span", { class: "pallino" }), g.nome);
    b.addEventListener("click", () => {
      evidenziato = evidenziato === g.nome ? null : g.nome;
      for (const [nome, gr] of linee) gr.classList.toggle("spenta", !!evidenziato && nome !== evidenziato);
      legenda.querySelectorAll(".chip-legenda").forEach((x) => x.classList.toggle("attiva", x === b && !!evidenziato));
      if (evidenziato) s.append(linee.get(evidenziato));     // in primo piano
    });
    legenda.append(b);
  }
  return el("div", { class: "box-grafico" }, s, el("div", { class: "nota" }, "Partite valutate"), legenda);
}
