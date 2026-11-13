// Scheda del giocatore: carriera, giocate spettacolari, carte prese, compagni e rivali.
import { el, $, apiGet, testoEle } from "./util.js";

let corrente = null;      // nome del giocatore mostrato
let soloValutate = false;

/** Apre la scheda di un giocatore con account. ``indietro``: schermata a cui tornare. */
export function apriScheda(app, nome, indietro = "lobby") {
  corrente = nome;
  app.indietroScheda = indietro;
  app.mostra("giocatore");
  carica();
}

export function initScheda(app) {
  $("#btn-giocatore-esci").addEventListener("click", () => app.mostra(app.indietroScheda || "lobby"));
}

async function carica() {
  const box = $("#giocatore-contenuto");
  box.innerHTML = "Caricamento…";
  let d;
  try {
    d = await apiGet(`/api/giocatore/${encodeURIComponent(corrente)}${soloValutate ? "?valutate=1" : ""}`);
  } catch (e) {
    box.textContent = e.message === "Errore 404" ? "Giocatore inesistente." : e.message;
    return;
  }
  $("#giocatore-titolo").textContent = `Scheda di ${d.nome}`;
  box.innerHTML = "";
  box.append(intestazione(d));
  const c = d.carriera;
  if (!c.partite) {
    box.append(el("p", { class: "vuoto" }, soloValutate
      ? "Nessuna partita valutata eLE, per ora. Servono 4 account al tavolo!"
      : "Ancora nessuna partita: il campo aspetta il suo campione!"));
    return;
  }
  const s = d.spettacolo, k = d.carte, cr = d.compagni_rivali;
  box.append(sezione("🏟️ Carriera", [
    tessera("Partite", c.partite, c.valutate && !soloValutate ? `${c.valutate} valutate eLE` : null),
    tessera("Vittorie", c.vittorie, `${c.percentuale_vittorie}% delle partite`),
    tessera("Pareggi", c.pareggi),
    tessera("Sconfitte", c.sconfitte),
    tessera("Serie di vittorie", c.serie_vittorie, "la più lunga"),
    tessera("Abbandoni", c.abbandoni, c.abbandoni ? "il pubblico non dimentica" : "mai lasciato il campo"),
  ], c.varianti.length ? el("p", { class: "nota" }, "Varianti più giocate: ",
    c.varianti.map((v) => `${v.variante} (${v.partite})`).join(" · ")) : null));
  const tipi = s.bazziche_per_tipo;
  box.append(sezione("✨ Giocate spettacolari", [
    tessera("Scope", s.scope),
    tessera("Piccole", s.piccole),
    tessera("Grandi", s.grandi),
    tessera("Bazziche", s.bazziche, `da 2: ${tipi["2"]} · da 3: ${tipi["3"]} · da 5: ${tipi["5"]} · da 7: ${tipi["7"]}`),
    tessera("Bazziche riscosse per intero", s.bazziche_riscosse_intere),
    tessera("Bazziche fatte fare", s.bazziche_fatte_fare, "con la carta passata al compagno"),
    tessera("Assist", s.assist, "prese spettacolari del compagno con la tua carta"),
    tessera("Con la carta del compagno", s.con_carta_compagno, "le tue prese spettacolari grazie a lui"),
    tessera("Napoleoni", s.napoleoni, s.napoleoni ? "leggenda vivente" : null),
    tessera("Napole", s.napole),
    tessera("\"Che Palo!\"", s.che_palo, "gridati"),
    tessera("Passaggi veloci", s.passaggi_veloci),
  ]));
  box.append(sezione("🃏 Carte prese", [
    tessera("Assi", k.assi),
    tessera("7 bello", k.sette_bello),
    tessera("Re bello", k.re_bello),
    tessera("2 di denari", k.due_denari, k.due_denari ? "la maledizione colpisce ancora" : "intoccabile"),
    tessera("Prese", k.prese),
    tessera("Carte prese", k.carte_prese),
    tessera("Punti individuali", String(k.media_punti_individuali).replace(".", ","), "in media a partita"),
  ]));
  box.append(sezione("🤝 Compagni e rivali", [
    persona("Compagno preferito", cr.compagno_preferito, "insieme"),
    persona("Bestia nera", cr.bestia_nera, "contro"),
    persona("Vittima preferita", cr.vittima_preferita, "contro"),
  ], el("p", { class: "nota" }, `Servono almeno ${cr.minimo_partite} partite insieme (o contro).`),
  bilanci("Con i compagni", cr.compagni), bilanci("Contro gli avversari", cr.avversari)));
}

function intestazione(d) {
  const filtro = el("div", { class: "filtro-scheda" },
    el("button", { class: "chip-legenda" + (soloValutate ? "" : " attiva"), onclick: () => { soloValutate = false; carica(); } }, "Tutte le partite"),
    el("button", { class: "chip-legenda" + (soloValutate ? " attiva" : ""), onclick: () => { soloValutate = true; carica(); } }, "Solo valutate eLE"));
  return el("div", { class: "scheda-testa" },
    el("div", { class: "scheda-avatar" }, d.avatar || "🙂"),
    el("div", {},
      el("div", { class: "scheda-nome" }, d.nome),
      el("div", { class: "scheda-ele" }, `eLE ${testoEle(d)}`, el("small", {}, ` · massimo ${d.ele_massimo}`))),
    filtro);
}

function sezione(titolo, tessere, ...dopo) {
  return el("section", { class: "scheda-sezione" }, el("h3", {}, titolo),
    el("div", { class: "tessere" }, ...tessere), ...dopo);
}

function tessera(etichetta, valore, nota = null) {
  return el("div", { class: "tessera" },
    el("div", { class: "tessera-valore" }, valore ?? 0),
    el("div", { class: "tessera-etichetta" }, etichetta),
    nota ? el("div", { class: "tessera-nota" }, nota) : null);
}

function persona(etichetta, b, parola) {
  if (!b) return tessera(etichetta, "—", "nessuno, per ora");
  return el("div", { class: "tessera" },
    el("div", { class: "tessera-valore piccolo" }, b.nome),
    el("div", { class: "tessera-etichetta" }, etichetta),
    el("div", { class: "tessera-nota" }, `${b.vittorie} V · ${b.pareggi} P · ${b.sconfitte} S ${parola} (${b.percentuale_vittorie}%)`));
}

function bilanci(titolo, lista) {
  if (!lista.length) return null;
  return el("details", { class: "bilanci" }, el("summary", {}, titolo),
    el("table", {}, el("tr", {}, ...["Giocatore", "Partite", "V", "P", "S", "%"].map((h) => el("th", {}, h))),
      ...lista.map((b) => el("tr", {}, el("td", {}, b.nome), el("td", {}, b.partite), el("td", {}, b.vittorie),
        el("td", {}, b.pareggi), el("td", {}, b.sconfitte), el("td", {}, `${b.percentuale_vittorie}%`)))));
}
