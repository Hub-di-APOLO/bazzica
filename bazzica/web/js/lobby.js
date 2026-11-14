// Lobby (elenco tavoli, creazione) e stanza del tavolo (posti, bot, impostazioni).
import { el, $, POSTI, SQUADRE, VARIANTI_DESC, store, AVATAR, testoEle } from "./util.js";

export function riempiVarianti(select, varianti, scelta) {
  select.innerHTML = "";
  for (const v of varianti) select.append(el("option", { value: v, selected: v === scelta }, v));
}

export function renderLobby(app, tavoli) {
  const box = $("#lista-tavoli");
  box.innerHTML = "";
  if (!tavoli.length) {
    box.append(el("p", { class: "vuoto" }, "Nessun tavolo. Creane uno!"));
    return;
  }
  for (const t of tavoli) {
    const occ = t.posti.filter(Boolean).length;
    const stato = { lobby: "In preparazione", in_corso: "Partita in corso", finita: "Partita finita" }[t.stato];
    const giocatori = t.posti.map((p, i) => p ? `${POSTI[i]}: ${p.nome}${p.ele ? ` (${testoEle(p)})` : ""}` : null)
      .filter(Boolean).join(" · ");
    const mio = t.miei && t.miei.length;
    const sostituito = t.stato === "in_corso" && t.sostituiti && t.sostituiti.length;
    box.append(el("div", { class: "tavolo-item" },
      el("div", { class: "ti-info" },
        el("div", { class: "ti-nome" }, t.nome),
        el("div", { class: "ti-dett" }, `${t.variante}${t.margherita ? " + Margherita Hack" : ""} — ${stato} — ${occ}/4`,
          t.valutata && t.valutata.si ? el("span", { class: "tag-ele" }, "eLE") : null),
        giocatori ? el("div", { class: "ti-dett" }, giocatori) : null),
      t.guardabile ? el("button", { class: "btn", onclick: () => app.guarda(t.id) }, "👀 Guarda") : null,
      sostituito ? el("button", { class: "btn primario", onclick: () => app.riprendi(t.id) }, "Riprendi il posto") : null,
      mio && t.stato === "in_corso" ? el("button", { class: "btn primario", onclick: () => app.entraInPartita(t.id) }, "Rientra") : null,
      el("button", { class: "btn", onclick: () => app.vaiStanza(t.id) }, "Apri")));
  }
}

export function renderStanza(app, t) {
  $("#stanza-titolo").textContent = t.nome;
  const stato = { lobby: "In preparazione", in_corso: "Partita in corso", finita: "Partita finita" }[t.stato];
  $("#stanza-stato").textContent = stato + (t.punteggi ? ` — ${t.punteggi[0]} a ${t.punteggi[1]}` : "");
  const modificabile = t.stato !== "in_corso";
  const croce = $("#posti-croce");
  croce.innerHTML = "";
  const aree = ["n", "e", "s", "o"];
  for (let s = 0; s < 4; s++) {
    const p = t.posti[s];
    const mio = t.miei.includes(s);
    const box = el("div", { class: `posto-lobby team${s % 2}`, style: `grid-area:${aree[s]}` },
      el("div", { class: "pl-nome-posto" }, `${POSTI[s]} · ${(t.squadre || SQUADRE)[s % 2]}`));
    if (p) {
      box.append(el("div", { class: "pl-occ" + (mio ? " mio" : "") }, el("span", { class: "pl-av" }, p.avatar || (p.tipo === "bot" ? "🤖" : "🙂")), p.nome,
        p.ele ? el("span", { class: "chip-ele", title: p.provvisorio ? "eLE provvisorio (prime 15 partite)" : "eLE" }, testoEle(p)) : null,
        p.tipo === "umano" && !p.connesso ? el("small", {}, " (disconnesso)") : null));
      if (modificabile && (p.tipo === "bot" || mio || t.owner)) {
        box.append(el("div", { class: "riga-btn" },
          el("button", { class: "btn piccolo", onclick: () => app.rete.invia({ type: p.tipo === "bot" ? "bot" : "alzati", tavolo: t.id, posto: s, aggiungi: false }) },
            p.tipo === "bot" ? "Togli bot" : "Libera")));
      }
    } else {
      box.append(el("div", { class: "pl-occ" }, "libero"));
      if (modificabile) {
        box.append(el("div", { class: "riga-btn" },
          el("button", { class: "btn piccolo primario", onclick: () => siediti(app, t, s) }, "Siediti"),
          el("button", { class: "btn piccolo", onclick: () => app.rete.invia({ type: "bot", tavolo: t.id, posto: s, aggiungi: true }) }, "+ Bot")));
      }
    }
    croce.append(box);
  }
  const sq = t.squadre || SQUADRE;
  const ant = t.anteprima_ele;
  const riga = (i) => el("span", { class: "vs-squadra" }, sq[i],
    ant ? el("small", { class: "vs-ele" }, `eLE ${ant.ele_squadre[i]} · ${Math.round((i ? 1 - ant.probabilita : ant.probabilita) * 100)}%`) : null);
  croce.append(el("div", { class: "centro" }, el("div", { class: "vs" }, riga(0), el("b", {}, "VS"), riga(1))));
  const val = $("#stanza-valutata");
  const v = t.valutata || { si: false, motivo: "" };
  val.className = "valutata " + (v.si ? "si" : "no");
  val.textContent = v.si ? "⭐ Partita valutata eLE" : `Partita non valutata eLE${v.motivo ? ` — ${v.motivo}` : ""}`;

  // impostazioni: le cambia chi ha creato il tavolo o chi è seduto, a partita non in corso
  const puo = t.gestore && modificabile;
  const sel = $("#stanza-variante");
  riempiVarianti(sel, app.varianti, t.variante);
  sel.disabled = !puo;
  $("#stanza-desc").textContent = VARIANTI_DESC[t.variante] || "";
  const mh = $("#stanza-mh");
  mh.checked = t.margherita;
  mh.disabled = !puo;
  const sp = $("#stanza-spett");
  sp.checked = t.spettatori_ammessi !== false;
  sp.disabled = !puo;
  const ritmo = $("#stanza-ritmo");
  if (document.activeElement !== ritmo) ritmo.value = t.ritmo || "rilassato";
  ritmo.disabled = !puo;
  for (const [id, chiave] of [["#stanza-ts", "timer_scambio"], ["#stanza-tg", "timer_giocata"]]) {
    const sel = $(id);
    const v = String(t[chiave] ?? 0);
    if (![...sel.options].some((o) => o.value === v)) sel.append(el("option", { value: v }, `${v} s`));
    if (document.activeElement !== sel) sel.value = v;
    sel.disabled = !puo;
  }
  // nomi delle squadre: non sovrascrivere mentre qualcuno sta scrivendo
  for (const i of [0, 1]) {
    const inp = $(`#stanza-sq${i}`);
    const nome = (t.squadre || SQUADRE)[i];
    if (document.activeElement !== inp) inp.value = nome === SQUADRE[i] ? "" : nome;
    inp.disabled = !puo;
  }
  const pieno = t.posti.every(Boolean);
  const avvia = $("#btn-avvia");
  avvia.disabled = !pieno || !modificabile || !(t.owner || t.miei.length);
  avvia.textContent = t.stato === "finita" ? "Nuova partita" : "Avvia partita";
  avvia.classList.toggle("nascosto", t.stato === "in_corso");
  $("#btn-rientra").classList.toggle("nascosto", !(t.stato !== "lobby" && t.miei.length));
  $("#btn-guarda").classList.toggle("nascosto", !t.guardabile);
  $("#btn-riprendi").classList.toggle("nascosto", !(t.stato === "in_corso" && t.sostituiti && t.sostituiti.length));
  $("#btn-termina").classList.toggle("nascosto", !(t.stato === "in_corso" && t.gestore));
  $("#btn-elimina").classList.toggle("nascosto", !t.puo_eliminare);
  $("#stanza-nota").textContent = t.stato === "in_corso" && t.gestore
    ? "Per cambiare le impostazioni termina prima la partita." : "";
}

function siediti(app, t, s) {
  if (!t.miei.length) {
    app.rete.invia({ type: "siedi", tavolo: t.id, posto: s, nome: app.nome, avatar: app.avatar });
    return;
  }
  // modalità locale: un altro giocatore sullo stesso PC sceglie nome e avatar
  const usati = new Set(t.posti.filter(Boolean).map((p) => p.avatar));
  let scelto = AVATAR.find((a) => !usati.has(a)) || AVATAR[0];
  const inp = el("input", { maxlength: 24, value: `Giocatore ${s + 1}` });
  const griglia = el("div", { class: "scelta-avatar" });
  app.sceltaAvatar(griglia, scelto, (a) => { scelto = a; });
  const box = el("div", {},
    el("h3", {}, `Nuovo giocatore — posto ${POSTI[s]} (${(t.squadre || SQUADRE)[s % 2]})`),
    el("label", {}, "Nome", inp),
    el("div", { class: "etichetta" }, "Avatar"), griglia,
    el("div", { class: "riga-btn" },
      el("button", { class: "btn primario", onclick: () => {
        const nome = inp.value.trim();
        if (!nome) return;
        app.chiudiModal();
        app.rete.invia({ type: "siedi", tavolo: t.id, posto: s, nome, avatar: scelto });
      } }, "Siediti"),
      el("button", { class: "btn", onclick: () => app.chiudiModal() }, "Annulla")));
  app.apriModal(box, true);
  setTimeout(() => inp.select(), 50);
}

export function initLobby(app) {
  riempiVarianti($("#crea-variante"), app.varianti, store("bazzica_variante") || "Vanilla");
  const aggiornaDesc = () => { $("#crea-desc").textContent = VARIANTI_DESC[$("#crea-variante").value] || ""; };
  $("#crea-variante").addEventListener("change", aggiornaDesc);
  aggiornaDesc();
  $("#form-crea").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const variante = $("#crea-variante").value;
    store("bazzica_variante", variante);
    app.attendiTavoloCreato = true;
    app.rete.invia({ type: "crea_tavolo", nome: $("#crea-nome").value.trim(), variante, margherita: $("#crea-mh").checked });
  });
  $("#stanza-variante").addEventListener("change", (ev) => {
    $("#stanza-desc").textContent = VARIANTI_DESC[ev.target.value] || "";
    app.rete.invia({ type: "imposta", tavolo: app.stanza, variante: ev.target.value });
  });
  $("#stanza-mh").addEventListener("change", (ev) => app.rete.invia({ type: "imposta", tavolo: app.stanza, margherita: ev.target.checked }));
  $("#stanza-spett").addEventListener("change", (ev) => app.rete.invia({ type: "imposta", tavolo: app.stanza, spettatori: ev.target.checked }));
  $("#stanza-ts").addEventListener("change", (ev) => app.rete.invia({ type: "imposta", tavolo: app.stanza, timer_scambio: Number(ev.target.value) }));
  $("#stanza-tg").addEventListener("change", (ev) => app.rete.invia({ type: "imposta", tavolo: app.stanza, timer_giocata: Number(ev.target.value) }));
  $("#stanza-ritmo").addEventListener("change", (ev) => app.rete.invia({ type: "imposta", tavolo: app.stanza, ritmo: ev.target.value }));
  $("#btn-guarda").addEventListener("click", () => app.guarda(app.stanza));
  const inviaSquadre = () => app.rete.invia({ type: "imposta", tavolo: app.stanza, squadre: [$("#stanza-sq0").value, $("#stanza-sq1").value] });
  for (const i of [0, 1]) {
    const inp = $(`#stanza-sq${i}`);
    inp.addEventListener("change", inviaSquadre);
    inp.addEventListener("keydown", (ev) => { if (ev.key === "Enter") inp.blur(); });
  }
  $("#btn-avvia").addEventListener("click", () => app.rete.invia({ type: "avvia", tavolo: app.stanza }));
  $("#btn-rientra").addEventListener("click", () => app.entraInPartita(app.stanza));
  $("#btn-riprendi").addEventListener("click", () => app.riprendi(app.stanza));
  $("#btn-termina").addEventListener("click", () => app.confermaTermina(app.stanza, false));
  $("#btn-elimina").addEventListener("click", () => {
    const t = app.tavoli[app.stanza];
    const tid = app.stanza;
    app.apriModal(el("div", {},
      el("h3", {}, "Eliminare il tavolo?"),
      el("p", {}, t && t.stato === "in_corso"
        ? "La partita in corso finisce per tutti e nello storico risulterà interrotta."
        : "Il tavolo sparisce dalla lobby."),
      el("div", { class: "riga-btn" },
        el("button", { class: "btn pericolo", onclick: () => {
          app.rete.invia({ type: "elimina", tavolo: tid });
          app.chiudiModal();
          app.mostra("lobby");
        } }, "Sì, elimina"),
        el("button", { class: "btn", onclick: () => app.chiudiModal() }, "Annulla"))), true);
  });
  $("#btn-stanza-esci").addEventListener("click", () => app.mostra("lobby"));
}
