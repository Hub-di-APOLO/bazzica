// Schermata di gioco: rendering del tavolo, interazioni, animazioni degli eventi, hot-seat.
import { el, $, $$, sleep, POSTI, SQUADRE, FRASI, nomeCarta, nomiCarte, val, squadra, toast, testoEle, conSegno } from "./util.js";
import { carta, dorso } from "./cards.js";
import { suona } from "./audio.js";
import * as fx from "./anim.js";
import { noteAttive } from "./account.js";

const NOMI_TIPO = { tris: "Tris", coppia: "Coppia con somma ≤ 9", diverse: "Tre carte diverse con somma ≤ 9" };
const ORIGINI = [["sparecchio", "Scope di sparecchio"], ["bazzica", "Scope da Bazzica"], ["piccola", "Piccole"], ["grande", "Grandi"], ["asso", "Assi (Avogadro)"]];

/**
 * Ritmo della partita (impostazione del tavolo, ms). Una giocata ha tre tempi: posa (la carta resta ferma
 * sul tavolo), evidenza (giocata e carte prese illuminate insieme), raccolta (le carte vanno a chi ha preso).
 * "ferma": quanto resta illuminata una carta che non prende niente. Svelto ≈ i tempi di prima.
 * Le pause dei bot e l'attesa dei "visto" sono sul server (tables.py, RITMI).
 */
export const RITMI = {
  rilassato: { posa: 700, evidenza: 900, raccolta: 650, ferma: 900, cartello: 1200, dopoScambio: 1000 },
  normale: { posa: 450, evidenza: 600, raccolta: 500, ferma: 600, cartello: 800, dopoScambio: 600 },
  svelto: { posa: 0, evidenza: 450, raccolta: 420, ferma: 0, cartello: 0, dopoScambio: 0 },
};

const PALETTE = [["#ffb547", "#ff6fae"], ["#5ad1ff", "#7a4cff"], ["#7be37b", "#1fa3a3"], ["#ff8a5c", "#e8336d"],
  ["#ffd23f", "#ff7a00"], ["#b28dff", "#ff6fd8"], ["#4dd4ac", "#3d7bff"], ["#ff6f61", "#ffb347"]];
function coloriAvatar(nome) {
  let h = 0;
  for (const ch of nome) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[h % PALETTE.length];
}
function iniziali(nome) {
  const p = nome.replace(/^Bot\s+/i, "").trim().split(/\s+/);
  return ((p[0] || "?")[0] + (p[1] ? p[1][0] : "")).toUpperCase();
}

// Reazioni automatiche di chi subisce punti: più punti, più disperazione.
const REAZ = {
  1: { emo: ["😕", "😒", "🙄", "😬"], frasi: ["Uffa", "Mah...", "Vabbè", "Pazienza"] },
  2: { emo: ["😠", "😢", "😤", "😣"], frasi: ["Ma dai!", "Che sfortuna...", "Ancora?!", "Grrr"] },
  3: { emo: ["😡", "😭", "😩", "🤬"], frasi: ["Non è possibile!", "Ma come?!", "Basta!!", "Ingiocabile!"] },
  4: { emo: ["💀", "😱", "🤯", "😵"], frasi: ["È FINITA", "Mi ritiro...", "NOOOOO!", "Chiamo l'avvocato"] },
};
const GIOIA = ["😎", "🥳", "😁", "🤩", "😏"];
const pesca = (a) => a[Math.floor(Math.random() * a.length)];

export class Partita {
  constructor(app) {
    this.app = app;
    this.tid = null;
    this.miei = [];
    this.stati = {};
    this.view = null;
    this.rivelato = true;
    this.coda = [];
    this.inElaborazione = false;
    this.selezione = null;
    this.inviato = false;
    this.ultimoScambioPrivato = {};
    this.modalRiepilogo = false;
    this.ackInviato = false;
    $("#ov-passa").addEventListener("click", () => this.mostraMano());
    window.addEventListener("resize", () => this.adattaTavola());
    // lo spazio centrale cambia anche senza "resize" della finestra (pulsanti Striscia e Chat che
    // compaiono, mano che si riempie, schermata appena mostrata): si ricalcola ogni volta
    if (window.ResizeObserver) new ResizeObserver(() => this.adattaTavola()).observe($("#centro"));
  }

  /** Nomi delle squadre scelti nella stanza (predefiniti: "Squadra 1" e "Squadra 2"). */
  /** Tempi del ritmo scelto nella stanza. */
  tempi() {
    const st = this.stati[this.view];
    return RITMI[st && st.info && st.info.ritmo] || RITMI.rilassato;
  }

  sq() {
    const st = this.stati[this.view];
    return (st && st.info && st.info.squadre) || SQUADRE;
  }

  // ------------------------------------------------------------ ingresso
  apri(tid, miei, spettatore = false) {
    this.spettatore = spettatore;
    if (this.tid !== tid) {
      this.tid = tid;
      this.vistoInviato = -1;
      this.stati = {};
      this.view = null;
      this.coda = [];
      this.selezione = null;
      this.preselezione = null;
      this.modalRiepilogo = false;
      this.modalInterrotta = false;
    }
    this.miei = miei.slice();
  }

  /** Una nuova partita è partita sullo stesso tavolo: si dimentica quella vecchia (e la sua schermata finale). */
  nuovaPartita() {
    const conModalFinale = this.modalFinale || this.modalInterrotta;
    this.stati = {};
    this.view = null;
    this.coda = [];
    this.selezione = null;
    this.preselezione = null;
    this.modalRiepilogo = false;
    this.modalFinale = false;
    this.modalInterrotta = false;
    this.impostaTimer(null);
    if (conModalFinale) this.app.chiudiModal();
  }

  /** True se gli stati in memoria sono di una partita già finita. */
  vecchiaFinita() {
    return Object.values(this.stati).some((st) => st.info && st.info.stato === "finita");
  }

  ricevi(msg) {
    if (msg.tavolo !== this.tid) return;
    if (msg.type === "stato" && msg.info && msg.info.stato === "in_corso" && this.vecchiaFinita()) this.nuovaPartita();
    // le esclamazioni ("Che Palo!" e frasi) compaiono subito, senza aspettare le altre animazioni
    if (msg.type === "eventi" && msg.eventi.length && msg.eventi.every((e) => ["frase", "che_palo", "striscia", "frase_spettatore"].includes(e.tipo))) {
      if (msg.posto === this.view && this.app.schermo === "gioco") msg.eventi.forEach((e) => this.animaEvento(e).catch(() => {}));
      return;
    }
    this.coda.push(msg);
    if (!this.inElaborazione) this.elabora();
  }

  async elabora() {
    this.inElaborazione = true;
    try {
      while (this.coda.length) {
        const msg = this.coda.shift();
        if (msg.type === "eventi") {
          if (this.view === null) this.view = msg.posto;
          if (msg.posto === this.view && this.app.schermo === "gioco") {
            for (const e of msg.eventi) {
              try { await this.animaEvento(e); } catch (err) { console.error(err); }
            }
          }
        } else if (msg.type === "stato") {
          this.stati[msg.posto] = msg;
          if (msg.info && msg.info.versione != null) this.ultimaVersione = msg.info.versione;
          if (!this.miei.includes(msg.posto)) this.miei.push(msg.posto);
          if (this.view === null) this.view = msg.posto;
          // aspetta di avere gli stati più recenti di tutti i posti già in coda
          if (this.coda.length && this.coda[0].type === "stato") continue;
          this.scegliVista();
          this.render();
        }
      }
    } finally {
      this.inElaborazione = false;
      // dice al server che ha finito di vedere le animazioni: i bot aspettano, così si gioca a ritmo umano
      // (giocatori e spettatori delle partite tra soli bot)
      if (!this.coda.length && this.ultimaVersione != null && this.ultimaVersione > (this.vistoInviato ?? -1)) {
        this.vistoInviato = this.ultimaVersione;
        this.app.rete.invia({ type: "visto", tavolo: this.tid, versione: this.ultimaVersione });
      }
    }
  }

  // ------------------------------------------------------------ hot-seat
  posiziona(seat) { return (seat - this.view + 4) % 4; }

  vistaDesiderata() {
    if (this.miei.length <= 1) return this.view;
    const st = this.stati[this.view];
    if (!st) return this.view;
    const obs = st.obs;
    const conAzioni = (s) => this.stati[s] && this.stati[s].legali.some((a) => a.tipo === "passa");
    if (obs.fase === "scambio") {
      if (conAzioni(this.view)) return this.view;
      const ordine = [1, 2, 3, 4].map((i) => (obs.mazziere + i) % 4).filter((s) => this.miei.includes(s));
      return ordine.find(conAzioni) ?? this.view;
    }
    if (obs.fase === "gioco" && this.miei.includes(obs.corrente)) return obs.corrente;
    return this.view;
  }

  scegliVista() {
    const d = this.vistaDesiderata();
    if (d !== this.view) {
      this.view = d;
      this.rivelato = false;
      this.selezione = null;
      const st = this.stati[d];
      $("#ov-passa-nome").textContent = st ? st.info.nomi[d] : POSTI[d];
      $("#ov-passa").classList.remove("nascosto");
    }
  }

  mostraMano() {
    this.rivelato = true;
    $("#ov-passa").classList.add("nascosto");
    this.render();
  }

  // ------------------------------------------------------------ rendering
  render() {
    const st = this.stati[this.view];
    if (!st || this.app.schermo !== "gioco") return;
    this.inviato = false;
    const { obs, info } = st;
    const v = this.view;

    // HUD
    $("#hud-variante").textContent = info.variante;
    $("#hud-mano").textContent = obs.regole.margherita_hack ? `${obs.mano_n} / 4` : obs.mano_n;
    $("#hud-turno").textContent = `${obs.turno} / 3`;
    const punti = $("#hud-punti");
    punti.innerHTML = "";
    for (const t of [squadra(v), 1 - squadra(v)]) {
      const nomi = [t, t + 2].map((s) => info.nomi[s]).join(" & ");
      punti.append(el("div", { class: `punti-squadra team${t}` + (t === squadra(v) ? " mia" : "") },
        el("span", { class: "ps-nome" }, this.sq()[t], el("small", {}, nomi)),
        el("span", { class: "ps-n" }, obs.punteggi[t])));
    }

    // posti
    for (let s = 0; s < 4; s++) {
      const p = this.posiziona(s);
      const box = $(`#tappeto .posto.pos-${p}`);
      box.innerHTML = "";
      box.dataset.seat = s;
      box.append(this.targhetta(s, obs, info));
      if (s !== v) box.append(this.manoAltrui(s, obs));
    }

    // tavola
    const tav = $("#tavola");
    tav.innerHTML = "";
    for (const c of obs.tavola) {
      const ce = carta(c);
      if (obs.regole.curie && c === obs.piccola_target) ce.classList.add("target-piccola");
      tav.append(ce);
    }

    this.adattaTavola();
    requestAnimationFrame(() => this.adattaTavola());   // dopo che mano e pulsanti hanno preso posto

    // prese
    this.renderPrese($("#prese-mia"), squadra(v), obs);
    this.renderPrese($("#prese-avv"), 1 - squadra(v), obs);

    // messaggio di turno
    $("#msg-turno").textContent = this.testoTurno(obs, info);

    // mano e azioni
    this.renderMano(st);
    this.renderAzioni(st);
    this.renderPalo(st);
    this.aggiornaPunti(obs);
    this.impostaTimer(info.timer, obs);

    // chi sta guardando la partita
    const spett = info.spettatori || [];
    const badge = $("#spettatori-badge");
    badge.classList.toggle("nascosto", !spett.length);
    badge.textContent = `👀 ${spett.length}`;
    badge.title = `Spettatori: ${spett.join(", ")}`;
    badge.onclick = () => toast(`👀 Guardano: ${spett.join(", ")}`);

    // overlay pausa
    const ovp = $("#ov-pausa");
    if (info.pausa && info.pausa.length && info.stato === "in_corso") {
      $("#ov-pausa-testo").textContent = `In attesa di riconnessione di ${info.pausa.join(", ")}…`;
      ovp.classList.remove("nascosto");
    } else ovp.classList.add("nascosto");

    // attesa di fine mano
    if (obs.fase === "fine_mano" && !this.modalRiepilogo && obs.storico_mani.length) {
      this.mostraRiepilogo(obs.storico_mani[obs.storico_mani.length - 1], info);
    } else if (this.modalRiepilogo && obs.fase === "fine_mano") {
      this.aggiornaAttesaAck(info);
    } else if (this.modalRiepilogo && obs.fase !== "fine_partita") {
      // riepilogo rimasto aperto ma la Mano successiva è già iniziata (es. rientro in partita)
      this.modalRiepilogo = false;
      this.app.chiudiModal();
    }
    if (obs.fase === "fine_partita" && !this.modalFinale) {
      this.mostraFinale(obs, info);
    }
    if (info.stato === "finita" && obs.fase !== "fine_partita" && !this.modalInterrotta) {
      this.mostraInterrotta(info);
    }
  }

  mostraInterrotta(info) {
    this.modalInterrotta = true;
    this.impostaTimer(null);
    const box = el("div", {},
      el("p", { class: "grande-testo" }, "Partita interrotta"),
      el("p", {}, info.terminata_da ? `${info.terminata_da} ha terminato la partita.` : "La partita è stata terminata."),
      el("div", { class: "riga-btn" },
        el("button", { class: "btn primario", onclick: () => { this.app.chiudiModal(); this.app.vaiStanza(this.tid); } }, "Torna al tavolo"),
        el("button", { class: "btn", onclick: () => { this.app.chiudiModal(); this.app.mostra("lobby"); } }, "Lobby")));
    this.app.apriModal(box);
  }

  // ------------------------------------------------------------ timer (durate scelte nella stanza)
  impostaTimer(t, obs) {
    this.timer = t ? { ...t, fine: performance.now() + t.restanti * 1000 } : null;
    this.timerObs = obs || null;
    if (this.timer && !this.timerTicker) this.timerTicker = setInterval(() => this.tickTimer(), 200);
    if (!this.timer && this.timerTicker) { clearInterval(this.timerTicker); this.timerTicker = null; }
    this.ultimoTic = null;
    this.tickTimer();
  }

  tickTimer() {
    const t = this.timer;
    $$(".timer-anello").forEach((x) => x.remove());
    $$(".g-timer").forEach((x) => x.remove());
    const box = $("#msg-timer");
    if (!t || !this.timerObs) { if (box) box.textContent = ""; return; }
    const rest = Math.max(0, (t.fine - performance.now()) / 1000);
    const sec = Math.ceil(rest);
    const p = t.totale ? rest / t.totale : 0;
    const obs = this.timerObs;
    const seats = t.tipo === "giocata" ? [t.seat] : [0, 1, 2, 3].filter((s) => !obs.scambio.passati[s]);
    for (const s of seats) {
      const g = this.avatarDi(s);
      if (!g) continue;
      const av = g.querySelector(".avatar");
      const an = el("span", { class: "timer-anello" + (sec <= 5 ? " urgente" : "") });
      an.style.setProperty("--p", p.toFixed(3));
      av.append(an);
      const nome = g.querySelector(".g-nome");
      if (nome) nome.append(el("span", { class: "g-timer" + (sec <= 5 ? " urgente" : "") }, ` ${sec}s`));
    }
    if (box) box.textContent = `⏱ ${sec}s`;
    box && box.classList.toggle("urgente", sec <= 5);
    // ticchettio negli ultimi 5 secondi se tocca a me
    const tocca = seats.includes(this.view) && this.rivelato;
    if (tocca && sec <= 5 && sec > 0 && this.ultimoTic !== sec) { this.ultimoTic = sec; suona("tic"); }
  }

  /** Sceglie la dimensione delle carte in tavola perché stiano tutte nello spazio centrale. */
  adattaTavola() {
    const t = $("#tavola"), box = $("#centro");
    if (!t || !box) return;
    const n = Math.max(1, t.querySelectorAll(".carta").length);
    const W = box.clientWidth - 12, H = box.clientHeight - 12, gap = 6, R = 1.768;
    // la disposizione che dà le carte più grandi; a parità (quasi) si preferisce quella più "quadrata"
    // (4 carte: 2×2 invece di una fila di 4)
    let best = 30, bestCols = n;
    for (let rows = 1; rows <= 5; rows++) {
      const cols = Math.ceil(n / rows);
      const w = Math.floor(Math.min(112, (W - gap * (cols - 1)) / cols, (H - gap * (rows - 1)) / rows / R));
      const quasiPari = w >= best - 3 && w <= best + 3;
      if (w > best + 3 || (quasiPari && Math.abs(cols - rows) < Math.abs(bestCols - Math.ceil(n / bestCols)))) {
        best = Math.max(30, w);
        bestCols = cols;
      }
    }
    t.style.setProperty("--tcw", best + "px");
    // larghezza della tavola = esattamente `bestCols` carte per riga
    t.style.setProperty("max-width", `${bestCols * best + gap * (bestCols - 1) + 12}px`);
  }

  targhetta(s, obs, info) {
    const turno = obs.fase === "gioco" && obs.corrente === s;
    // chi apre il Turno (a sinistra del mazziere) è segnalato da subito, già durante lo scambio
    const primo = (obs.fase === "scambio" || obs.fase === "gioco") && s === (obs.mazziere + 1) % 4;
    const iniziato = obs.giocato_turno && obs.giocato_turno.some(Boolean);
    const g = el("div", { class: `giocatore targhetta team${squadra(s)}` + (turno ? " turno" : "") + (primo && !turno && !iniziato ? " primo" : ""), dataset: { seat: s } });
    const nome = info.nomi[s] || "?";
    const [c1, c2] = coloriAvatar(nome);
    const emoji = (info.avatar && info.avatar[s]) || (info.tipi[s] === "bot" ? "🤖" : null);
    const av = el("div", { class: "avatar" + (emoji ? " emoji" : "") + (info.tipi[s] === "bot" ? " bot" : ""), style: `--c1:${c1};--c2:${c2}` },
      emoji || iniziali(nome));
    if (obs.mazziere === s) av.append(el("span", { class: "ang mazz", title: "Mazziere" }, "M"));
    const badges = el("div", { class: "g-badges" });
    if (primo && !iniziato) badges.append(el("span", { class: "g-badge inizia", title: "Gioca per primo in questo Turno" }, "▶ Inizia"));
    if (obs.bazziche[s]) badges.append(el("span", { class: "g-badge bazzica", title: "Ha chiamato Bazzica" }, `Bazzica ${obs.bazziche[s].scope}`));
    if (obs.fase === "scambio") {
      if (obs.scambio.veloci[s]) badges.append(el("span", { class: "g-badge veloce" }, "Veloce! 🔥"));
      else if (obs.scambio.passati[s]) badges.append(el("span", { class: "g-badge passato" }, "Passato"));
    }
    const ele = info.ele && info.ele[s];
    if (ele) badges.prepend(el("span", { class: "g-badge ele", title: ele.provvisorio ? "eLE provvisorio (prime 15 partite)" : "eLE" }, testoEle(ele)));
    g.append(av, el("div", {}, el("div", { class: "g-nome" }, nome), badges.childNodes.length ? badges : null));
    return g;
  }

  manoAltrui(s, obs) {
    const a = obs.altri[s];
    const box = el("div", { class: "mano-altrui" + (a.carte ? " scoperta" : "") });
    if (a.carte) {
      for (const c of a.carte) {
        const ce = carta(c);
        const b = obs.bazziche[s];
        if (b && c === "denari_07" && b.sette !== null && b.sette !== undefined) ce.append(el("span", { class: "valore-7b" }, b.sette));
        box.append(ce);
      }
    } else for (let i = 0; i < a.n; i++) box.append(dorso());
    return box;
  }

  renderPrese(box, t, obs) {
    box.innerHTML = "";
    box.dataset.team = t;
    const p = obs.prese[t];
    const m = el("div", { class: "mazzetto" });
    if (p.n > 0) m.append(dorso()); else m.append(el("div", { class: "vuoto-mazzo" }));
    const sc = el("div", { class: "scoperte" });
    p.scoperte.slice(-4).forEach(([c, o]) => { const ce = carta(c); ce.title = `${nomeCarta(c)} — ${o}`; sc.append(ce); });
    const info = el("div", { class: "prese-info" },
      el("span", { class: "pi-team" }, this.sq()[t]),
      el("span", {}, `${p.n} carte`),
      el("b", {}, `${p.scoperte.length} Scope`),
      obs.credito[t] > 0 ? el("span", { class: "credito" }, `Credito: ${obs.credito[t]}`) : null);
    box.append(el("div", { class: "pila" }, m, p.scoperte.length ? sc : null), info);
  }

  testoTurno(obs, info) {
    const v = this.view;
    if (obs.fase === "scambio") {
      if (!obs.scambio.passati[v]) {
        const p = obs.compagno;
        const chiInizia = (obs.mazziere + 1) % 4;
        const ini = chiInizia === v ? " · poi inizi tu" : ` · poi inizia ${info.nomi[chiInizia]}`;
        if (obs.scambio.passati[p]) return `${info.nomi[p]} ha già passato${obs.scambio.veloci[p] ? " VELOCE" : ""}: scegli la tua carta${ini}`;
        return `Scegli la carta da passare a ${info.nomi[p]}${ini}`;
      }
      const mancano = [0, 1, 2, 3].filter((s) => !obs.scambio.passati[s]).map((s) => info.nomi[s]);
      if (!obs.scambio.ricevuta) return `Hai passato: aspetti la carta di ${info.nomi[obs.compagno]}`;
      return `Scambio: in attesa di ${mancano.join(", ")}`;
    }
    if (obs.fase === "gioco") {
      if (obs.corrente === v) return "Tocca a te";
      return `Tocca a ${info.nomi[obs.corrente]}`;
    }
    if (obs.fase === "fine_mano") return "Fine della Mano";
    if (obs.fase === "fine_partita") return "Partita terminata";
    return "";
  }

  renderMano(st) {
    const { obs, legali } = st;
    const box = $("#mia-mano");
    box.innerHTML = "";
    if (obs.pubblica && obs.mano_coperte) {
      // spettatore di una partita con giocatori umani: le carte del giocatore in basso sono coperte
      for (let i = 0; i < obs.mano_coperte; i++) box.append(dorso());
      box.classList.remove("attiva");
      return;
    }
    if (!this.rivelato) {
      obs.mano.forEach(() => box.append(dorso()));
      box.classList.remove("attiva");
      return;
    }
    const giocabili = new Set(legali.filter((a) => a.tipo === "gioca" || a.tipo === "passa").map((a) => a.carta));
    // pre-mossa: la carta scelta mentre giocavano gli altri diventa la selezione appena tocca a me
    if (this.preselezione && !obs.mano.includes(this.preselezione)) this.preselezione = null;
    if (this.preselezione && giocabili.has(this.preselezione) && legali.some((a) => a.tipo === "gioca")) {
      this.selezione = this.preselezione;
      this.preselezione = null;
    }
    if (this.selezione && !giocabili.has(this.selezione)) this.selezione = null;
    const puoPremuovere = !this.spettatore && obs.fase === "gioco" && obs.corrente !== this.view && giocabili.size === 0 && obs.mano.length > 0;
    box.classList.toggle("attiva", giocabili.size > 0 || puoPremuovere);
    if (!obs.mano.length) box.append(el("span", { class: "vuota" }, "Nessuna carta in mano"));
    const baz = obs.bazziche[this.view];
    for (const c of obs.mano) {
      const ce = carta(c);
      if (giocabili.has(c)) {
        ce.classList.add("giocabile");
        ce.addEventListener("click", () => this.selezionaCarta(c));
      } else if (puoPremuovere) {
        ce.classList.add("giocabile", "premossa-possibile");
        ce.addEventListener("click", () => this.preseleziona(c));
      }
      if (this.preselezione === c) ce.classList.add("preselezionata");
      if (obs.fase === "scambio" && c === obs.scambio.ricevuta) ce.classList.add("ricevuta", "non-selezionabile");
      if (this.selezione === c) ce.classList.add("selezionata");
      if (baz && c === "denari_07" && baz.sette != null) ce.append(el("span", { class: "valore-7b", title: "Valore assegnato al 7 bello" }, baz.sette));
      box.append(ce);
    }
  }

  renderPalo(st) {
    const f = $("#btn-frasi"), u = $("#btn-ultima"), sx = $("#btn-striscia");
    // gli spettatori hanno le frasi rapide (non "Che Palo!") e possono commentare anche durante lo scambio
    const ok = this.spettatore ? st.info.stato === "in_corso"
      : this.rivelato && st.legali.some((a) => a.tipo === "che_palo");
    f.classList.toggle("nascosto", !ok);
    // niente chat finché lo scambio delle carte non è finito
    const inScambio = st.obs.fase === "scambio" && !this.spettatore;
    f.disabled = inScambio || !!this.inRicarica;
    f.title = inScambio ? "La chat si apre quando tutti hanno scambiato le carte" : "Che Palo! e frasi";
    if (!ok || inScambio) $("#menu-frasi").classList.add("nascosto");
    u.disabled = !this.ultimaPresa(st.obs);
    // "Striscia": solo mentre gioca il giocatore che viene prima di me
    const precedente = (this.view + 3) % 4;
    const puoStrisciare = this.rivelato && st.obs.fase === "gioco" && st.obs.corrente === precedente && st.info.stato === "in_corso";
    sx.classList.toggle("nascosto", this.spettatore || !(st.obs.fase === "gioco" && st.obs.mano.length));
    sx.disabled = !puoStrisciare || !!this.strisciaRicarica;
    sx.title = puoStrisciare ? `Striscia una carta sul tavolo per mettere fretta a ${st.info.nomi[precedente]}` : `Si può strisciare solo mentre gioca ${st.info.nomi[precedente]}`;
    if (!f.dataset.bound) {
      f.dataset.bound = "1";
      sx.addEventListener("click", () => this.striscia());
      f.addEventListener("click", (ev) => { ev.stopPropagation(); if (!f.disabled) this.apriFrasi(); });
      u.addEventListener("click", () => this.mostraUltimaPresa());
      document.addEventListener("click", (ev) => { if (!ev.target.closest(".frasi-box")) $("#menu-frasi").classList.add("nascosto"); });
    }
  }

  ricarica() {
    const f = $("#btn-frasi");
    this.inRicarica = true;
    f.disabled = true;
    f.classList.add("ricarica");
    $("#menu-frasi").classList.add("nascosto");
    setTimeout(() => {
      this.inRicarica = false;
      f.classList.remove("ricarica");
      const st = this.stati[this.view];
      f.disabled = !!(st && st.obs.fase === "scambio" && !this.spettatore);
    }, 3000);
  }

  /** Nota scritta in sovraimpressione durante la partita (si può spegnere nelle impostazioni). */
  nota(testo) {
    if (noteAttive(this.app)) toast(testo);
  }

  striscia() {
    const sx = $("#btn-striscia");
    if (sx.disabled) return;
    // la versione che sto guardando: se il turno è appena passato, il server sa che stavo guardando quello
    const st = this.stati[this.view];
    const versione = st && st.info ? st.info.versione : undefined;
    this.app.rete.invia({ type: "striscia", tavolo: this.tid, posto: this.view, versione });
    this.strisciaRicarica = true;
    sx.disabled = true;
    setTimeout(() => { this.strisciaRicarica = false; const st = this.stati[this.view]; if (st) this.renderPalo(st); }, 1000);
  }

  esclamaPalo() {
    if ($("#btn-frasi").disabled) return;
    this.app.rete.invia({ type: "azione", tavolo: this.tid, posto: this.view, azione: { tipo: "che_palo" } });
    this.ricarica();
  }

  apriFrasi() {
    const m = $("#menu-frasi");
    if (!m.classList.contains("nascosto")) { m.classList.add("nascosto"); return; }
    m.innerHTML = "";
    if (!this.spettatore) m.append(el("button", { class: "btn piccolo frase-palo", onclick: () => this.esclamaPalo() }, "Che Palo!"));
    FRASI.forEach((f, i) => m.append(el("button", {
      class: "btn piccolo", onclick: () => {
        if ($("#btn-frasi").disabled) return;
        // lo spettatore non ha un posto: il server riconosce la frase come commento di uno spettatore
        this.app.rete.invia(this.spettatore ? { type: "frase", tavolo: this.tid, indice: i }
          : { type: "frase", tavolo: this.tid, posto: this.view, indice: i });
        this.ricarica();
      },
    }, f)));
    m.classList.remove("nascosto");
  }

  ultimaPresa(obs) {
    const g = [...obs.giocate_mano].reverse().find((x) => x[2] && x[2].length);
    return g || null;
  }

  mostraUltimaPresa() {
    const st = this.stati[this.view];
    if (!st) return;
    const g = this.ultimaPresa(st.obs);
    if (!g) { toast("Nessuna presa in questa Mano"); return; }
    const [seat, c, presa] = g;
    const box = el("div", {},
      el("h3", {}, "Ultima presa"),
      el("p", {}, `${st.info.nomi[seat]} (${this.sq()[squadra(seat)]}) ha giocato ${nomeCarta(c)} e preso ${nomiCarte(presa)}.`),
      el("div", { class: "ultima-presa" },
        el("div", { class: "gruppo" }, carta(c)),
        el("span", { class: "freccia" }, "→"),
        el("div", { class: "gruppo" }, ...presa.map((x) => carta(x)))),
      el("button", { class: "btn primario", onclick: () => this.app.chiudiModal() }, "Chiudi"));
    this.app.apriModal(box, true);
  }

  // ------------------------------------------------------------ reazioni
  avatarDi(seat) { return $(`#tappeto .giocatore[data-seat="${seat}"]`); }

  /** Reazioni dei giocatori: chi subisce ``punti`` si dispera, chi li fa gioisce. */
  reazioni(squadraCheSegna, punti) {
    if (punti <= 0) return;
    const livello = punti >= 7 ? 4 : punti >= 4 ? 3 : punti >= 2 ? 2 : 1;
    const dur = 1800 + livello * 500;
    for (let s = 0; s < 4; s++) {
      const g = this.avatarDi(s);
      if (!g) continue;
      const r = g.querySelector(".avatar").getBoundingClientRect();
      const vittima = squadra(s) !== squadraCheSegna;
      const box = el("div", { class: "reazione", style: `left:${r.left + r.width / 2}px;top:${r.top - 4}px;--dur:${dur}ms;--k:${1 + livello * 0.25}` });
      if (vittima) {
        const pool = REAZ[livello];
        box.append(el("span", { class: "emo" }, pesca(pool.emo)));
        if (livello >= 2 || Math.random() < 0.5) box.append(el("span", { class: "bolla" }, pesca(pool.frasi)));
        const cls = livello >= 4 ? "spazzato" : livello >= 3 ? "arrabbiato" : "triste";
        if (cls === "spazzato") g.style.setProperty("--vx", (Math.random() < 0.5 ? -1 : 1) * 160 + "px");
        g.classList.add(cls);
        setTimeout(() => g.classList.remove(cls), dur);
      } else if (livello >= 2) {
        box.append(el("span", { class: "emo" }, pesca(GIOIA)));
        g.classList.add("felice");
        setTimeout(() => g.classList.remove("felice"), 1600);
      } else continue;
      document.body.append(box);
      setTimeout(() => box.remove(), dur + 100);
    }
    const mia = squadra(this.view);
    if (livello >= 3) suona(squadraCheSegna === mia ? "festa" : "triste");
  }

  /** Effetti di contorno proporzionati ai punti fatti con una giocata. */
  clamore(punti, x, y) {
    if (punti >= 2) fx.coriandoli(20 * punti, 2200);
    if (punti >= 3) { fx.flash("#fff", 300); fx.terremoto(document.getElementById("gioco")); fx.onda(x, y, "#ffd23f", 20); }
    if (punti >= 5) { fx.raggi("rgba(255,210,63,.35)", 2400); fx.fuochi(4); }
  }

  aggiornaPunti(obs) {
    const chiave = obs.punteggi.join("/");
    if (this.ultimiPunti && this.ultimiPunti !== chiave) {
      $$("#hud-punti .ps-n").forEach((n) => { n.classList.remove("pop"); void n.offsetWidth; n.classList.add("pop"); });
    }
    this.ultimiPunti = chiave;
  }

  preseleziona(c) {
    const st = this.stati[this.view];
    if (!st) return;
    this.preselezione = this.preselezione === c ? null : c;
    this.renderMano(st);
    this.renderAzioni(st);
  }

  selezionaCarta(c) {
    const st = this.stati[this.view];
    if (!st || this.inviato) return;
    const opz = st.legali.filter((a) => (a.tipo === "gioca" || a.tipo === "passa") && a.carta === c);
    if (!opz.length) return;
    this.selezione = this.selezione === c ? null : c;
    this.renderMano(st);
    this.renderAzioni(st);
  }

  renderAzioni(st) {
    const { obs, legali } = st;
    const bar = $("#barra-azioni");
    bar.innerHTML = "";
    if (!this.rivelato) return;
    if (this.spettatore) {
      bar.append(el("span", { class: "suggerimento" }, obs.pubblica
        ? "👀 Stai guardando: vedi solo le carte in tavola. Puoi commentare con la Chat"
        : "👀 Stai guardando una partita tra bot: si vedono tutte le carte"));
      return;
    }
    const tipi = new Set(legali.map((a) => a.tipo));

    if (tipi.has("bazzica")) {
      bar.append(el("button", { class: "btn btn-azione btn-bazzica", onclick: () => this.modalBazzica(st) }, "Bazzica!"));
    }

    if (tipi.has("passa")) {
      if (!this.selezione) {
        bar.append(el("span", { class: "suggerimento" }, "Scegli la carta da passare al compagno"));
      } else {
        const n = nomeCarta(this.selezione);
        const normale = legali.find((a) => a.tipo === "passa" && a.carta === this.selezione && !a.veloce);
        const veloce = legali.find((a) => a.tipo === "passa" && a.carta === this.selezione && a.veloce);
        bar.append(el("button", { class: "btn btn-azione primario", onclick: () => this.invia(normale) }, `Passa ${n}`));
        bar.append(el("button", { class: "btn btn-azione btn-veloce", onclick: () => this.invia(veloce) }, "Passa veloce 🔥"));
      }
      return;
    }

    if (!tipi.has("gioca") && obs.fase === "gioco" && obs.corrente !== this.view && obs.mano.length) {
      bar.append(el("span", { class: "suggerimento" }, this.preselezione
        ? `Pronta: ${nomeCarta(this.preselezione)} — al tuo turno premi "Gioca"`
        : "Puoi già scegliere la prossima carta"));
      return;
    }

    if (tipi.has("gioca")) {
      if (!this.selezione) {
        bar.append(el("span", { class: "suggerimento" }, "Scegli una carta da giocare"));
        return;
      }
      const opz = legali.filter((a) => a.tipo === "gioca" && a.carta === this.selezione);
      for (const a of opz) {
        const b = el("button", { class: "btn btn-azione opzione-presa", onclick: () => this.invia(a) }, ...this.etichettaGiocata(a));
        b.addEventListener("mouseenter", () => this.evidenziaTavola(a.presa));
        b.addEventListener("mouseleave", () => this.evidenziaTavola([]));
        b.addEventListener("focus", () => this.evidenziaTavola(a.presa));
        bar.append(b);
      }
      if (opz.length === 1) this.evidenziaTavola(opz[0].presa);
    }
  }

  etichettaGiocata(a) {
    const p = a.anteprima || {};
    const out = [];
    if (!a.presa.length) out.push(`Gioca ${nomeCarta(a.carta)} in tavola`);
    else out.push(`Prendi ${nomiCarte(a.presa)}`);
    const tag = (t, cls = "") => el("span", { class: "tag " + cls }, t);
    if (p.scopa) out.push(tag("SCOPA"));
    if (p.piccola) out.push(tag("PICCOLA"));
    if (p.grande) out.push(tag(`GRANDE da ${a.presa.length + 1}`));
    if (p.assi && p.assi.length) out.push(tag(`+${p.assi.length} asso`));
    if (p.credito_pagato) out.push(tag(`credito −${p.credito_pagato}`));
    if (p.ultima_giocata && a.presa.length) out.push(tag("ultima giocata", "no"));
    return out;
  }

  evidenziaTavola(presa) {
    $$("#tavola .carta").forEach((c) => c.classList.toggle("evidenzia", presa.includes(c.dataset.carta)));
  }

  invia(a) {
    if (!a || this.inviato) return;
    this.inviato = true;
    this.selezione = null;
    const azione = { tipo: a.tipo, carta: a.carta, presa: a.presa, sette: a.sette, veloce: a.veloce };
    this.app.rete.invia({ type: "azione", tavolo: this.tid, posto: this.view, azione });
    $("#barra-azioni").innerHTML = "";
    $("#mia-mano").classList.remove("attiva");
  }

  modalBazzica(st) {
    const opz = st.legali.filter((a) => a.tipo === "bazzica");
    const box = el("div", {},
      el("h3", {}, "Chiama Bazzica"),
      el("p", { class: "nota" }, "Chiamando la Bazzica la tua mano diventa visibile a tutti per il resto del Turno."),
      el("div", { class: "opzioni" }, ...opz.map((a) => el("button", {
        class: "btn", onclick: () => { this.app.chiudiModal(); this.invia(a); },
      }, a.descrizione))),
      el("button", { class: "btn", onclick: () => this.app.chiudiModal() }, "Non chiamare"));
    this.app.apriModal(box);
  }

  // ------------------------------------------------------------ riepilogo e fine
  mostraRiepilogo(rie, info) {
    this.modalRiepilogo = true;
    this.ackInviato = false;
    const v = this.view;
    const ordine = [squadra(v), 1 - squadra(v)];
    const tab = el("table", { class: "riepilogo" });
    tab.append(el("tr", {}, el("th", {}, ""), ...ordine.map((t) => el("th", {}, this.sq()[t]))));
    const punto = (n) => el("span", { class: "punto" + (n ? "" : " zero") }, n);
    const riga = (label, f, cls = "") => tab.append(el("tr", { class: cls }, el("td", {}, label), ...ordine.map((t) => el("td", {}, ...[].concat(f(rie.squadre[t], t))))));
    riga("Carte", (s) => [s.carte, punto(s.punti_mazzo_dettaglio.carte)]);
    riga("Denari", (s) => [s.denari, punto(s.punti_mazzo_dettaglio.denari)]);
    riga("Primiera", (s) => {
      const calc = Object.entries(s.primiera_dettaglio).map(([sm, d]) => d ? `${d.punti}` : `— (${sm})`).join(" + ");
      const tit = s.semi_mancanti.length ? `manca: ${s.semi_mancanti.join(", ")}` : calc;
      return [el("span", {}, s.primiera, el("span", { class: "prim-calc" }, tit)), punto(s.punti_mazzo_dettaglio.primiera)];
    });
    riga("7 bello", (s) => punto(s.punti_mazzo_dettaglio.sette_bello));
    riga("Re bello", (s) => punto(s.punti_mazzo_dettaglio.re_bello));
    riga("Punti di mazzo", (s) => el("b", {}, s.punti_mazzo));
    riga("Scope", (s) => el("b", {}, s.scope));
    for (const [o, lab] of ORIGINI) {
      if (rie.squadre.some((s) => s.scope_dettaglio[o])) riga(lab, (s) => s.scope_dettaglio[o] || 0, "sotto");
    }
    riga("2 di denari", (s) => s.punti_due_denari);
    if (rie.squadre.some((s) => s.napola)) riga("Napola / Napoleone", (s) => s.napola ? el("span", { class: "napola-tag" }, `${s.napola_nome}: ${s.napola}`) : 0);
    if (rie.credito_perso && rie.credito_perso.some((x) => x)) riga("Credito Bazzica perso", (s, t) => rie.credito_perso[t], "sotto");
    riga("Totale Mano", (s) => s.totale, "totale");
    riga("Totale partita", (s, t) => rie.punteggi[t], "partita");

    const attesa = el("p", { class: "nota", id: "attesa-ack" });
    const st = this.stati[this.view];
    const fine = st && st.obs.fase === "fine_partita";
    // il "Continua" serve ai giocatori: lo spettatore di una partita con umani chiude e basta
    const soloChiudi = this.spettatore && st && st.obs.pubblica;
    const btn = soloChiudi
      ? el("button", { class: "btn primario", onclick: () => this.app.chiudiModal() }, "Chiudi")
      : el("button", {
        class: "btn primario", id: "btn-continua", onclick: () => {
          this.ackInviato = true;
          btn.disabled = true;
          btn.textContent = "In attesa degli altri giocatori…";
          this.app.rete.invia({ type: "prosegui", tavolo: this.tid });
        },
      }, "Continua");
    // a partita finita il riepilogo si apre dalla schermata finale: si torna indietro a quella
    const indietro = el("button", { class: "btn primario", onclick: () => this.mostraFinale(st.obs, st.info, false) }, "Indietro");
    // uscire dalla partita: al proprio posto continua un bot (si può riprendere il posto dopo)
    const esci = fine || this.spettatore ? null
      : el("button", { class: "btn", onclick: () => this.confermaEsci(rie, info) }, "Esci dalla partita");
    this.app.apriModal(el("div", {}, el("h3", {}, `Fine della Mano ${rie.mano}`), tab,
      el("div", { class: "riga-btn" }, fine ? indietro : btn, esci), fine ? null : attesa));
    this.aggiornaAttesaAck(info);
  }

  confermaEsci(rie, info) {
    const tid = this.tid;
    const box = el("div", {},
      el("h3", {}, "Uscire dalla partita?"),
      el("p", {}, "Al tuo posto giocherà un bot e la partita continua per gli altri. "
        + "Potrai riprendere il posto dalla lobby o dalla stanza del tavolo."),
      el("div", { class: "riga-btn" },
        el("button", { class: "btn pericolo", onclick: () => {
          this.app.rete.invia({ type: "esci", tavolo: tid });
          this.modalRiepilogo = false;
          this.app.chiudiModal();
          this.app.vaiStanza(tid);
        } }, "Sì, esci"),
        el("button", { class: "btn", onclick: () => { this.modalRiepilogo = false; this.mostraRiepilogo(rie, info); } }, "Annulla")));
    this.app.apriModal(box);
  }

  aggiornaAttesaAck(info) {
    const a = $("#attesa-ack");
    if (a && info.ack && info.ack.length) a.textContent = `Pronti: ${info.ack.join(", ")}`;
  }

  mostraFinale(obs, info, conSuono = true) {
    this.modalFinale = true;
    const vinc = obs.vincitore;
    const mio = squadra(this.view);
    let titolo;
    if (vinc === "pari") titolo = "Pareggio!";
    else titolo = `${this.sq()[vinc]} ha vinto!`;
    if (conSuono) suona("vittoria");
    const ultimo = obs.storico_mani[obs.storico_mani.length - 1];
    const box = el("div", {},
      el("p", { class: "grande-testo" }, titolo),
      el("p", {}, `${this.sq()[0]} ${obs.punteggi[0]} — ${obs.punteggi[1]} ${this.sq()[1]} dopo ${obs.mano_n} Mani`),
      info.esito_ele ? this.riquadroEle(info.esito_ele, conSuono) : null,
      el("div", { class: "riga-btn" },
        ultimo ? el("button", { class: "btn", onclick: () => { this.modalRiepilogo = false; this.mostraRiepilogo(ultimo, info); } }, "Riepilogo ultima Mano") : null,
        el("button", { class: "btn primario", onclick: () => { this.app.chiudiModal(); this.app.vaiStanza(this.tid); } }, "Torna al tavolo"),
        el("button", { class: "btn", onclick: () => { this.app.chiudiModal(); this.app.mostra("lobby"); } }, "Lobby")));
    this.app.apriModal(box);
  }

  /** Variazioni di eLE a fine partita, con il conteggio animato e il dettaglio del calcolo. */
  riquadroEle(variazioni, anima = true) {
    const num = (x) => String(Number(Number(x).toFixed(2))).replace(".", ",");
    const box = el("div", { class: "esito-ele" }, el("h4", {}, "eLE"));
    const poco = variazioni.some((v) => v.esito === "vittoria" && v.dettaglio.spettacolo < 1);
    if (poco) box.append(el("p", { class: "poco-spettacolo" }, "🥱 Poco spettacolo! Il pubblico non gradisce"));
    const ordine = [...variazioni].sort((a, b) => (a.posto % 2) - (b.posto % 2) || a.posto - b.posto);
    for (const v of ordine) {
      const d = v.dettaglio;
      let spiega;
      if (d.abbandono) spiega = `${conSegno(v.delta)}: ha lasciato la partita (sconfitta piena)`;
      else {
        spiega = `${conSegno(v.delta)}: ${conSegno(d.quota_squadra)} squadra, ripartizione ×${num(d.ripartizione)}, spettacolo ×${num(d.spettacolo)}`;
        if (d.bonus) spiega += `, bonus ${conSegno(d.bonus)}`;
        if (d.fattore_k < 1) spiega += " (K dimezzato per un abbandono)";
      }
      const valore = el("span", { class: "ele-valore" }, Math.round(anima ? v.prima : v.dopo) + (v.provvisorio ? "?" : ""));
      const delta = el("span", { class: "ele-delta " + (v.delta > 0 ? "su" : v.delta < 0 ? "giu" : "") + (anima ? " entra" : "") },
        conSegno(v.delta));
      box.append(el("div", { class: `riga-ele team${v.posto % 2}` + (this.miei.includes(v.posto) ? " mia" : "") },
        el("span", { class: "ele-nome" }, v.nome), valore, delta, el("small", { class: "ele-dett" }, spiega)));
      if (anima) contaFino(valore, v.prima, v.dopo, v.provvisorio ? "?" : "");
    }
    return box;
  }

  // ------------------------------------------------------------ animazioni eventi
  rectPosto(seat) {
    if (seat === this.view) {
      const m = $("#mia-mano");
      return m.getBoundingClientRect();
    }
    const p = this.posiziona(seat);
    const box = $(`#tappeto .posto.pos-${p}`);
    const mano = box && box.querySelector(".mano-altrui");
    return (mano || box).getBoundingClientRect();
  }

  rectCartaTavola() {
    const t = $("#tavola").getBoundingClientRect();
    const c = $("#tavola .carta");
    const w = c ? c.getBoundingClientRect().width : 70;
    const h = c ? c.getBoundingClientRect().height : 124;
    return new DOMRect(t.left + t.width / 2 - w / 2 + (Math.random() * 40 - 20), t.top + t.height / 2 - h / 2, w, h);
  }

  rectPrese(team) {
    const box = team === squadra(this.view) ? $("#prese-mia") : $("#prese-avv");
    return box.querySelector(".mazzetto").getBoundingClientRect();
  }

  async animaEvento(e) {
    const st = this.stati[this.view];
    const info = st ? st.info : { nomi: POSTI };
    switch (e.tipo) {
      case "nuova_mano":
        if (this.modalRiepilogo) { this.app.chiudiModal(); this.modalRiepilogo = false; }
        this.modalFinale = false;
        this.nota(`Mano ${e.mano} — mazziere ${info.nomi[e.mazziere]}`);
        break;
      case "distribuzione": {
        suona("distribuzione");
        const da = this.rectPosto(e.mazziere);
        const voli = [];
        const w = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--sw")) || 34;
        for (let i = 0; i < 4; i++) {
          const s = (e.mazziere + 1 + i) % 4;
          const a = this.rectPosto(s);
          const src = new DOMRect(da.left + da.width / 2 - w / 2, da.top + da.height / 2 - w * 0.9, w, w * 1.768);
          const dst = new DOMRect(a.left + a.width / 2 - w / 2, a.top + a.height / 2 - w * 0.9, w, w * 1.768);
          voli.push(fx.vola(dorso(), src, dst, { durata: 380, ritardo: i * 90, svanisci: false }));
        }
        await Promise.all(voli);
        // un attimo di respiro: il cartello con il numero del Turno
        const T = this.tempi();
        if (T.cartello) {
          fx.banner(`Turno ${e.turno}`, "turno", `Mano ${e.mano}`, T.cartello);
          await sleep(T.cartello);
        }
        break;
      }
      case "fine_scambio":
        await sleep(this.tempi().dopoScambio);
        break;
      case "inizio_giocate":
        if (st && this.miei.includes(e.corrente)) suona("turno");
        break;
      case "scambio_carta":
        this.ultimoScambioPrivato[e.seat] = e.carta;
        break;
      case "scambio": {
        const priv = this.ultimoScambioPrivato[e.seat];
        delete this.ultimoScambioPrivato[e.seat];
        const da = this.rectPosto(e.seat), a = this.rectPosto(e.a);
        const w = 56, h = w * 1.768;
        let src = new DOMRect(da.left + da.width / 2 - w / 2, da.top + da.height / 2 - h / 2, w, h);
        const dst = new DOMRect(a.left + a.width / 2 - w / 2, a.top + a.height / 2 - h / 2, w, h);
        const vis = priv && this.rivelato ? carta(priv) : dorso();
        const mia = priv && e.seat === this.view ? $(`#mia-mano .carta[data-carta="${priv}"]`) : null;
        if (mia) { src = mia.getBoundingClientRect(); mia.style.visibility = "hidden"; }
        if (e.veloce) {
          suona("fuoco");
          fx.scuoti($("#gioco"));
          fx.banner("Passa veloce!", "veloce", info.nomi[e.seat], 1300);
          await fx.vola(vis, src, dst, { durata: 650, fiamme: true, ruota: 720 });
        } else {
          suona("passa");
          await fx.vola(vis, src, dst, { durata: 420 });
        }
        break;
      }
      case "scambio_ricevuta": {
        if (e.seat !== this.view || !this.rivelato) break;
        const da = this.rectPosto(e.da);
        const m = $("#mia-mano").getBoundingClientRect();
        const w = 56, h = w * 1.768;
        const src = new DOMRect(da.left + da.width / 2 - w / 2, da.top + da.height / 2 - h / 2, w, h);
        const cw = $("#mia-mano .carta") ? $("#mia-mano .carta").getBoundingClientRect().width : 80;
        const dst = new DOMRect(m.left + m.width / 2 - cw / 2, m.top + 8, cw, cw * 1.768);
        suona("passa");
        await fx.vola(carta(e.carta), src, dst, { durata: 520, ruota: 360 });
        fx.scintille(dst.left + dst.width / 2, dst.top + dst.height / 2, 14, "#5ad1ff");
        this.nota(`${info.nomi[e.da]} ti ha passato: ${nomeCarta(e.carta)}`);
        break;
      }
      case "bazzica":
        await this.animaBazzica(e, info);
        break;
      case "striscia": {
        const r = this.rectPosto(e.verso);
        const cen = fx.centro($("#tavola").getBoundingClientRect());
        const c = fx.centro(r);
        // la carta viene strisciata sul panno tra la mano del giocatore precedente e il centro
        const x = c.x + (cen.x - c.x) * 0.35, y = c.y + (cen.y - c.y) * 0.35;
        suona("striscia");
        fx.cartaStrisciata(dorso(), x, y);
        const g = this.avatarDi(e.seat);
        if (g) fx.fumetto(g.getBoundingClientRect(), "😤");
        // chi la subisce trema; se sono io, il telefono vibra e la mia mano si agita
        const bersaglio = this.avatarDi(e.verso);
        if (bersaglio) fx.trema(bersaglio);
        if (this.miei.includes(e.verso) && !this.spettatore) {
          fx.trema($("#mia-mano"));
          try { if (navigator.vibrate) navigator.vibrate([70, 50, 70, 50, 140]); } catch (err) { /* niente vibrazione */ }
        }
        break;
      }
      case "sostituito":
        this.nota(e.motivo === "uscito" ? `${e.nome} ha lasciato la partita: al suo posto gioca un bot 🤖`
          : `${e.nome} ${e.motivo === "inattivo" ? "non gioca" : "non è connesso"} da qualche minuto: al suo posto gioca un bot 🤖`);
        break;
      case "rientrato":
        this.nota(`${e.nome} ha ripreso il suo posto`);
        break;
      case "tempo_scaduto":
        if (e.fase === "scambio") this.nota("⏱ Tempo scaduto: chi non aveva scambiato ha passato una carta a caso");
        else this.nota(`⏱ Tempo scaduto: per ${info.nomi[e.seat]} gioca il computer`);
        break;
      case "inizio_partita":
        this.modalInterrotta = false;
        this.modalFinale = false;
        break;
      case "frase_spettatore": {
        suona("palo");
        const b = $("#spettatori-badge");
        const r = b && !b.classList.contains("nascosto") ? b.getBoundingClientRect() : $("#tavola").getBoundingClientRect();
        fx.fumetto(r, `👀 ${e.nome}: ${e.testo}`, "commento");
        break;
      }
      case "frase": {
        suona("palo");
        const g = this.avatarDi(e.seat);
        fx.fumetto((g || $("#mia-mano")).getBoundingClientRect(), e.testo);
        await sleep(300);
        break;
      }
      case "che_palo": {
        suona("palo");
        const box = $(`#tappeto .posto.pos-${this.posiziona(e.seat)} .targhetta`) || $("#mia-mano");
        fx.fumetto(box.getBoundingClientRect(), "Che Palo!");
        await sleep(500);
        break;
      }
      case "giocata":
        await this.animaGiocata(e, info);
        break;
      case "carte_residue": {
        const els = $$("#tavola .carta");
        await fx.lampeggia(els, "evidenzia", 400);
        const dst = this.rectPrese(e.squadra);
        await Promise.all(els.map((x, i) => { const r = x.getBoundingClientRect(); x.style.visibility = "hidden"; return fx.vola(carta(x.dataset.carta), r, dst, { durata: 450, ritardo: i * 50 }); }));
        suona("presa");
        await this.carteBuone(e.squadra, e.carte);
        break;
      }
      case "fine_mano": {
        suona("fineMano");
        const rie = e.riepilogo;
        for (let t = 0; t < 2; t++) {
          const sq = rie.squadre[t];
          if (sq.napola_len === 10 && sq.napola) await this.animaNapoleone(t, info);
          else if (sq.napola) await this.animaNapola(t, sq);
        }
        await sleep(300);
        break;
      }
      case "fine_partita":
        break;
      default:
        break;
    }
  }

  async animaBazzica(e, info) {
    const r = this.rectPosto(e.seat);
    const c = fx.centro(r);
    const chi = info.nomi[e.seat];
    let sotto = `${chi} — ${NOMI_TIPO[e.tipo_bazzica]}, ${e.scope} Scope`;
    if (e.sette != null) sotto += ` (7 bello = ${e.sette})`;
    const carteBaz = () => e.carte.map((x) => {
      const ce = carta(x);
      if (x === "denari_07" && e.sette != null) ce.append(el("span", { class: "valore-7b" }, e.sette));
      return ce;
    });
    const W = window.innerWidth, H = window.innerHeight;
    if (e.scope <= 2) {
      // 2: un bel colpo, niente di più
      suona("bazzica2");
      fx.scintille(c.x, c.y, 30, "#ff8be0");
      this.reazioni(e.squadra, 2);
      await fx.banner("BAZZICA!", "bazzica b2", sotto, 1800);
    } else if (e.scope === 3) {
      // 3: lampo, coriandoli, scossone
      suona("bazzica3");
      fx.flash("#ffd1f0", 350);
      fx.scintille(c.x, c.y, 50, "#ff8be0");
      fx.coriandoli(70, 2400);
      fx.scuoti(document.getElementById("gioco"));
      this.reazioni(e.squadra, 3);
      await fx.banner("BAZZICA!", "bazzica b3", sotto, 2000);
    } else if (e.scope <= 5) {
      // 5: buio, raggi, carte giganti, onda d'urto, terremoto
      suona("bazzica5");
      fx.buio(3200);
      fx.raggi("rgba(255,79,163,.4)", 3000);
      fx.carteGiganti(carteBaz(), 2800);
      await sleep(450);
      fx.onda(W / 2, H / 2, "#ff4fa3", 35);
      fx.terremoto(document.getElementById("gioco"));
      fx.coriandoli(120, 2800);
      this.reazioni(e.squadra, 5);
      await fx.banner("SUPER BAZZICA!", "bazzica b5", sotto, 2400);
      await sleep(600);
    } else {
      // 7: l'apocalisse
      suona("tamburo");
      fx.buio(6800);
      await sleep(1200);
      for (let i = 0; i < 4; i++) setTimeout(() => { fx.fulmine(); fx.flash("#e6dcff", 200); if (i % 2 === 0) suona("tuono"); }, i * 260);
      await sleep(900);
      suona("bazzica7");
      fx.raggi("rgba(255,255,255,.35)", 4500);
      fx.carteGiganti(carteBaz(), 4200, true);
      await sleep(700);
      fx.onda(W / 2, H / 2, "#fff", 45);
      setTimeout(() => fx.onda(W / 2, H / 2, "#ff4fa3", 45), 180);
      setTimeout(() => fx.onda(W / 2, H / 2, "#ffd23f", 45), 360);
      fx.flash("#fff", 500);
      fx.terremoto(document.getElementById("gioco"));
      setTimeout(() => fx.terremoto(document.getElementById("gioco")), 800);
      fx.crepe(W / 2, H / 2, Math.min(W, H) * 0.45);
      fx.pioggiaCarte((i) => (i % 3 ? dorso() : carta(e.carte[i % e.carte.length])), 60, 2600);
      fx.coriandoli(220, 3400);
      fx.fuochi(10, 250);
      this.reazioni(e.squadra, 7);
      fx.banner("BAZZICA DA SETTE!!!", "bazzica b7", sotto, 3200);
      await sleep(3600);
    }
  }

  async animaNapola(t, sq) {
    suona("napola");
    const n = sq.napola_len;
    const carte = Array.from({ length: n }, (_, i) => carta(`denari_${String(i + 1).padStart(2, "0")}`));
    const box = await fx.parataDenari(carte, 180, () => suona("moneta"));
    fx.scintille(window.innerWidth / 2, window.innerHeight / 2, 40, "#ffe066");
    this.reazioni(t, Math.min(6, n));
    await fx.banner(`${sq.napola_nome.toUpperCase()}!`, "napola", `${this.sq()[t]} — ${sq.napola} punti`, 2000);
    box.remove();
  }

  async animaNapoleone(t, info) {
    // 1) tutte le carte di denari sfilano, una a una, ad arco
    fx.buio(9000);
    const carte = Array.from({ length: 10 }, (_, i) => carta(`denari_${String(i + 1).padStart(2, "0")}`));
    const box = await fx.parataDenari(carte, 300, (i) => { suona("moneta"); if (i === 9) fx.flash("#fff3a0", 300); });
    await sleep(400);
    // 2) incoronazione e festa grande
    suona("napoleone");
    const cor = el("div", { class: "corona" }, "👑");
    document.body.append(cor);
    setTimeout(() => cor.remove(), 3600);
    fx.raggi("rgba(255,215,0,.45)", 5000);
    fx.onda(window.innerWidth / 2, window.innerHeight / 2, "#ffd23f", 40);
    fx.banner("NAPOLEONE!", "napola b7", `${this.sq()[t]} prende tutti i denari — 10 punti`, 3400);
    await sleep(700);
    suona("festa");
    fx.coriandoli(260, 3600);
    fx.fuochi(16, 220);
    fx.pioggiaCarte((i) => carta(`denari_${String((i % 10) + 1).padStart(2, "0")}`), 40, 2600);
    this.reazioni(t, 10);
    await sleep(3800);
    box.remove();
  }

  async animaGiocata(e, info) {
    let src;
    let cardEl = null;
    if (e.seat === this.view) {
      cardEl = $(`#mia-mano .carta[data-carta="${e.carta}"]`);
    } else {
      const box = $(`#tappeto .posto.pos-${this.posiziona(e.seat)} .mano-altrui`);
      if (box) cardEl = box.querySelector(`.carta[data-carta="${e.carta}"]`) || box.querySelector(".carta:last-child");
    }
    if (cardEl) { src = cardEl.getBoundingClientRect(); cardEl.style.visibility = "hidden"; }
    else src = this.rectPosto(e.seat);
    if (!src.width) src = this.rectPosto(e.seat);
    const dst = this.rectCartaTavola();
    const chi = info.nomi[e.seat];
    const tav = $("#tavola");

    // ---------------- GRANDE: la carta precipita come un macigno
    if (e.grande) {
      await this.animaGrande(e, chi, dst);
      return;
    }

    // ---------------- PICCOLA: tutto velocissimo
    if (e.piccola) {
      await this.animaPiccola(e, chi, src, dst);
      return;
    }

    // 1) posa: la carta arriva sul tavolo e resta ferma, ben visibile
    const T = this.tempi();
    suona("carta");
    await fx.vola(carta(e.carta), src, dst, { durata: 420 });
    const giocata = carta(e.carta);
    tav.append(giocata);
    this.adattaTavola();
    if (T.posa) await sleep(T.posa);
    if (!e.presa.length) {
      // non prende niente: resta un momento in evidenza prima che il gioco passi al successivo
      if (T.ferma) {
        giocata.classList.add("in-evidenza");
        await sleep(T.ferma);
        giocata.classList.remove("in-evidenza");
      }
      return;
    }

    const prese = e.presa.map((c) => $(`#tavola .carta[data-carta="${c}"]`)).filter(Boolean);
    if (!e.scopa) {
      // 2) evidenza: la giocata e le carte che prende si illuminano insieme (il resto del tavolo resta com'è)
      const insieme = [giocata, ...prese];
      insieme.forEach((x) => x.classList.add("in-evidenza"));
      await sleep(T.evidenza);
      // 3) raccolta: le carte scivolano verso chi ha preso
      await this.volaAlleTavole(insieme, e.squadra, T.raccolta);
      const punti = (e.girate || []).length;
      if (punti) {
        const c = fx.centro(tav.getBoundingClientRect());
        this.clamore(punti, c.x, c.y);
        this.reazioni(e.squadra, punti);
      }
      await this.effettiFinali(e);
      return;
    }
    // Scopa: dopo la posa, l'animazione speciale di sempre
    await fx.lampeggia([giocata, ...prese], "evidenzia", 450);
    const c = fx.centro(tav.getBoundingClientRect());
    const punti = (e.girate || []).length;
    if (e.scopa) {
      // la spazzola passa sul tavolo e "spazza" le carte nel mazzo delle prese
      suona("scopa");
      const spazza = fx.spazzola(tav.getBoundingClientRect(), 900);
      await sleep(250);
      await this.volaAlleTavole([giocata, ...prese], e.squadra, 480);
      await spazza;
      fx.scintille(c.x, c.y, 30 + punti * 10);
      this.clamore(punti, c.x, c.y);
      this.reazioni(e.squadra, punti);
      await fx.bannerLettere("SCOPA!", punti > 1 ? `${chi} — ${punti} Scope!` : chi, punti >= 3 ? "grossa" : "");
      await this.effettiFinali(e);
    }
  }

  async volaAlleTavole(elems, squadraT, durata) {
    const dest = this.rectPrese(squadraT);
    const voli = elems.map((x, i) => {
      const r = x.getBoundingClientRect();
      x.style.visibility = "hidden";
      return fx.vola(carta(x.dataset.carta), r, dest, { durata, ritardo: i * Math.min(45, durata / 8) });
    });
    suona("presa");
    await Promise.all(voli);
    elems.forEach((x) => x.remove());
  }

  /** Prese "buone": sette bello, re bello e i sette (primiera) hanno un piccolo momento di gloria. */
  async carteBuone(squadraT, carte) {
    const buone = [];
    if (carte.includes("denari_07")) buone.push(["denari_07", "SETTE BELLO!", "settebello", "oro"]);
    if (carte.includes("denari_10")) buone.push(["denari_10", "RE BELLO!", "rebello", "re"]);
    for (const c of carte) if (val(c) === 7 && c !== "denari_07") buone.push([c, "UN SETTE!", "sette", "primiera"]);
    if (!buone.length) return;
    const dest = this.rectPrese(squadraT);
    for (const [c, testo, suono, stile] of buone.slice(0, 3)) {
      suona(suono);
      await fx.cartaDiGloria(carta(c), testo, stile, dest, buone.length > 1 ? 850 : 1150);
    }
    if (buone.some((b) => b[3] !== "primiera")) this.reazioni(squadraT, 1);
  }

  async effettiFinali(e) {
    if (e.presa && e.presa.length) await this.carteBuone(e.squadra, [e.carta, ...e.presa]);
    if (e.assi && e.assi.length) {
      suona("asso");
      await fx.banner(e.assi.length > 1 ? `${e.assi.length} ASSI!` : "ASSO!", "asso", "Scopa (Avogadro)", 1200);
    }
    if (e.credito_pagato) this.nota(`${this.sq()[e.squadra]}: riscossi ${e.credito_pagato} di credito Bazzica`);
    if (e.girate && e.girate.length) {
      const r = this.rectPrese(e.squadra);
      fx.scintille(r.left + r.width / 2, r.top + r.height / 2, 10);
    }
  }

  async animaPiccola(e, chi, src, dst) {
    const tav = $("#tavola");
    const target = $(`#tavola .carta[data-carta="${e.presa[0]}"]`);
    const tr = target ? target.getBoundingClientRect() : dst;
    const c = fx.centro(tr);
    // 1) arrivo a lampo sulla carta appena calata
    suona("piccola");
    fx.lineeVelocita(c.x, c.y);
    fx.saetta(fx.centro(src), c);
    await fx.vola(carta(e.carta), src, tr, { durata: 160 });
    fx.sbuffi(c.x, c.y, 12);
    const giocata = carta(e.carta);
    tav.append(giocata);
    this.adattaTavola();
    const elems = [giocata, target].filter(Boolean);
    // 2) "PICCOLA!" passa veloce (il banner copre il centro del tavolo)...
    this.reazioni(e.squadra, (e.girate || []).length);
    await fx.bannerZip("PICCOLA!", `${chi} — lampo!`);
    // 3) ...poi si vedono bene le due carte prese: illuminate, il resto del tavolo in ombra
    tav.classList.add("in-ombra");
    elems.forEach((x) => x.classList.add("presa-piccola"));
    await sleep(1100);
    tav.classList.remove("in-ombra");
    // 4) e volano nel mazzo delle prese
    const dest = this.rectPrese(e.squadra);
    fx.saetta(fx.centro(giocata.getBoundingClientRect()), fx.centro(dest));
    await this.volaAlleTavole(elems, e.squadra, 380);
    await this.effettiFinali(e);
  }

  async animaGrande(e, chi, dst) {
    const tav = $("#tavola");
    const prese = e.presa.map((c) => $(`#tavola .carta[data-carta="${c}"]`)).filter(Boolean);
    // punto d'impatto: sopra le carte prese, se ci sono
    let bersaglio = dst;
    if (prese.length) {
      const r = prese[0].getBoundingClientRect();
      bersaglio = new DOMRect(r.left, r.top, r.width, r.height);
    }
    fx.vignetta();
    suona("grandeCaduta");
    prese.forEach((x) => x.classList.add("evidenzia"));
    const { box, c } = await fx.macigno(carta(e.carta), bersaglio, 620);
    // IMPATTO
    suona("grande");
    fx.terremoto(document.getElementById("gioco"));
    fx.crepe(c.x, c.y, Math.max(140, bersaglio.width * 2.2));
    fx.polvere(c.x, c.y + bersaglio.height * 0.35, 22);
    fx.scintille(c.x, c.y, 26, "#ffcc33");
    prese.forEach((x, i) => { x.style.transition = "transform .25s"; x.style.transform = `translateY(10px) rotate(${i % 2 ? 7 : -7}deg) scale(.92)`; });
    fx.bannerPesante("GRANDE!", `${chi} — ${e.presa.length + 1} Scope`);
    // gli avversari accusano il colpo (più è grande, più si disperano)
    const punti = (e.girate || []).length;
    for (const sx of [0, 1, 2, 3].filter((x) => squadra(x) !== e.squadra)) {
      const g = this.avatarDi(sx);
      if (g) { g.classList.add("abbattuto"); setTimeout(() => g.classList.remove("abbattuto"), 2600); }
    }
    this.reazioni(e.squadra, punti + 1);
    if (punti >= 3) { setTimeout(() => fx.terremoto(document.getElementById("gioco")), 350); fx.onda(c.x, c.y, "#3a1d0b", 25); }
    if (punti >= 4) { fx.pioggiaCarte(() => dorso(), 8 * punti, 1600); setTimeout(() => suona("tuono"), 300); }
    await sleep(1100);
    // la carta-macigno e il bottino scivolano lentamente, pesanti, nel mazzo delle prese
    const giocata = carta(e.carta);
    const gr = box.getBoundingClientRect();
    box.remove();
    giocata.style.position = "fixed";
    giocata.style.left = gr.left + "px";
    giocata.style.top = gr.top + "px";
    giocata.style.width = gr.width + "px";
    giocata.style.height = gr.height + "px";
    document.body.append(giocata);
    await this.volaAlleTavole([giocata, ...prese], e.squadra, 700);
    await sleep(500);
    await this.effettiFinali(e);
  }
}

/** Fa scorrere un numero da ``da`` ad ``a`` (eLE a fine partita). */
function contaFino(nodo, da, a, suffisso = "", durata = 1400) {
  const inizio = performance.now() + 400;
  const passo = (ora) => {
    const t = Math.min(1, Math.max(0, (ora - inizio) / durata));
    const k = 1 - (1 - t) ** 3;
    nodo.textContent = Math.round(da + (a - da) * k) + suffisso;
    if (t < 1) requestAnimationFrame(passo);
  };
  requestAnimationFrame(passo);
}
