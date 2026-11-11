// Pagina "Storico": elenco partite e dettaglio Mano per Mano.
import { el, $, SQUADRE, apiGet } from "./util.js";

const ORIGINI = { sparecchio: "sparecchio", bazzica: "Bazzica", piccola: "Piccola", grande: "Grande", asso: "assi" };

function data(s) {
  if (!s) return "—";
  const d = new Date(s);
  return d.toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" });
}

export async function mostraStorico() {
  const box = $("#storico-contenuto");
  box.innerHTML = "Caricamento…";
  let lista;
  try { lista = await apiGet("/api/storico"); } catch (e) { box.textContent = e.message; return; }
  box.innerHTML = "";
  if (!lista.length) { box.append(el("p", { class: "vuoto" }, "Nessuna partita giocata finora.")); return; }
  const tab = el("table", {}, el("tr", {}, ...["Data", "Tavolo", "Variante", "Nord–Sud", "Est–Ovest", "Punteggio", "Mani", "Esito"].map((h) => el("th", {}, h))));
  for (const p of lista) {
    const squadra = (posti) => {
      const gs = p.giocatori.filter((g) => posti.includes(g.posto));
      const nome = gs.length && gs[0].squadra ? `${gs[0].squadra}: ` : "";
      return nome + gs.map((g) => g.nome).join(" & ");
    };
    const ns = squadra(["Nord", "Sud"]);
    const eo = squadra(["Est", "Ovest"]);
    const esito = p.esito ? (p.esito === "pari" ? "Pareggio" : p.esito === "interrotta" ? "Interrotta" : `Vince ${p.esito}`) : "In corso / non conclusa";
    tab.append(el("tr", { class: "cliccabile", onclick: () => dettaglio(p.id) },
      el("td", {}, data(p.inizio)), el("td", {}, p.tavolo), el("td", {}, p.variante + (p.margherita ? " + M. Hack" : "")),
      el("td", {}, ns), el("td", {}, eo), el("td", {}, `${p.punti_ns} – ${p.punti_eo}`), el("td", {}, p.n_mani),
      el("td", { class: "esito" }, esito)));
  }
  box.append(tab);
}

function sqN(p, t) {
  const g = p.giocatori.find((x) => (t === 0 ? ["Nord", "Sud"] : ["Est", "Ovest"]).includes(x.posto));
  return (g && g.squadra) || (t === 0 ? "Nord–Sud" : "Est–Ovest");
}

async function dettaglio(id) {
  const box = $("#storico-contenuto");
  const p = await apiGet(`/api/storico/${id}`);
  box.innerHTML = "";
  box.append(el("button", { class: "btn", onclick: mostraStorico }, "← Elenco"));
  box.append(el("h3", { style: "margin-top:12px" }, `${p.tavolo} — ${p.variante}${p.margherita ? " + Margherita Hack" : ""}`));
  box.append(el("p", { class: "nota" }, `Iniziata ${data(p.inizio)} · terminata ${data(p.fine)} · ` +
    p.giocatori.map((g) => `${g.posto}: ${g.nome}${g.bot ? " (bot)" : ""}`).join(", ")));
  const tab = el("table", {}, el("tr", {}, ...["Mano", "Mazziere", "Punti mazzo", "Scope", "2 denari", "Napola", `Mano ${sqN(p, 0)}`, `Mano ${sqN(p, 1)}`, `Totale ${sqN(p, 0)}`, `Totale ${sqN(p, 1)}`].map((h) => el("th", {}, h))));
  const POSTI = ["Nord", "Est", "Sud", "Ovest"];
  for (const m of p.mani) {
    const r = m.riepilogo;
    const [a, b] = r.squadre;
    const scope = (s) => `${s.scope}` + (s.scope ? ` (${Object.entries(s.scope_dettaglio).filter(([, n]) => n).map(([o, n]) => `${n} ${ORIGINI[o]}`).join(", ")})` : "");
    tab.append(el("tr", {},
      el("td", {}, m.numero), el("td", {}, POSTI[m.mazziere]),
      el("td", {}, `${a.punti_mazzo} – ${b.punti_mazzo}`), el("td", {}, `${scope(a)} – ${scope(b)}`),
      el("td", {}, `${a.punti_due_denari} – ${b.punti_due_denari}`), el("td", {}, `${a.napola} – ${b.napola}`),
      el("td", {}, m.punti_ns), el("td", {}, m.punti_eo), el("td", {}, el("b", {}, m.totale_ns)), el("td", {}, el("b", {}, m.totale_eo))));
  }
  box.append(tab);
  if (p.esito) box.append(el("p", { class: "esito" }, p.esito === "pari" ? "Pareggio" : p.esito === "interrotta" ? "Partita interrotta" : `Vince ${p.esito}`));
}
