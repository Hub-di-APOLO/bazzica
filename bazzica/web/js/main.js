// Avvio dell'applicazione, navigazione tra schermate e smistamento dei messaggi.
import { $, $$, el, store, toast, AVATAR } from "./util.js";
import { Rete } from "./net.js";
import { caricaCarte } from "./cards.js";
import { impostaFileSuoni, isMuto, setMuto } from "./audio.js";
import { initLobby, renderLobby, renderStanza } from "./lobby.js";
import { mostraStorico } from "./storico.js";
import { Partita } from "./game.js";

class App {
  constructor() {
    this.schermo = null;
    this.nome = store("bazzica_nome") || "";
    this.avatar = store("bazzica_avatar") || AVATAR[Math.floor(Math.random() * AVATAR.length)];
    this.varianti = ["Vanilla", "Heisenberg", "Einstein", "Fermi", "Pascal", "Curie", "Federico II", "Avogadro"];
    this.tavoli = {};
    this.stanza = null;
    this.uscitoDa = null;
    this.attendiTavoloCreato = false;
    this.partita = new Partita(this);
    this.rete = new Rete((m) => this.messaggio(m));
  }

  async avvia() {
    const d = await caricaCarte();
    impostaFileSuoni(d.suoni);
    initLobby(this);
    this.bind();
    if (!this.nome) this.mostra("nome");
    else { this.mostra("lobby"); this.rete.connetti(); }
  }

  sceltaAvatar(box, scelto, onScelta) {
    box.innerHTML = "";
    for (const a of AVATAR) {
      const b = el("button", { type: "button", class: a === scelto ? "scelto" : "", title: "Scegli questo avatar" }, a);
      b.addEventListener("click", () => {
        box.querySelectorAll("button").forEach((x) => x.classList.remove("scelto"));
        b.classList.add("scelto");
        onScelta(a);
      });
      box.append(b);
    }
  }

  bind() {
    let avatarScelto = this.avatar;
    this.sceltaAvatar($("#scelta-avatar"), this.avatar, (a) => { avatarScelto = a; });
    $("#form-nome").addEventListener("submit", (ev) => {
      ev.preventDefault();
      const n = $("#inp-nome").value.trim();
      if (!n) return;
      const primo = !this.nome;
      this.nome = n;
      this.avatar = avatarScelto;
      store("bazzica_nome", n);
      store("bazzica_avatar", avatarScelto);
      if (primo && !this.rete.ws) this.rete.connetti();
      else this.rete.invia({ type: "nome", nome: n, avatar: avatarScelto });
      this.mostra("lobby");
    });
    $("#btn-cambia-nome").addEventListener("click", () => {
      $("#inp-nome").value = this.nome;
      avatarScelto = this.avatar;
      this.sceltaAvatar($("#scelta-avatar"), this.avatar, (a) => { avatarScelto = a; });
      this.mostra("nome");
    });
    $("#form-codice").addEventListener("submit", (ev) => {
      ev.preventDefault();
      const c = $("#inp-codice").value.trim();
      if (!c) return;
      store("bazzica_codice", c);
      $("#form-codice button").disabled = true;
      this.rete.riconnetti();
    });
    $("#btn-storico").addEventListener("click", () => { this.mostra("storico"); mostraStorico(); });
    $("#btn-storico-esci").addEventListener("click", () => this.mostra("lobby"));
    const muto = $("#btn-muto");
    const aggiornaMuto = () => { muto.innerHTML = isMuto() ? "&#128263;" : "&#128266;"; };
    aggiornaMuto();
    muto.addEventListener("click", () => { setMuto(!isMuto()); aggiornaMuto(); });
    $("#btn-menu").addEventListener("click", () => this.menuGioco());
    $("#ov-modal").addEventListener("click", (ev) => { if (ev.target.id === "ov-modal" && this.modalChiudibile) this.chiudiModal(); });
  }

  mostra(nome) {
    this.schermo = nome;
    document.body.dataset.schermo = nome;
    $$(".screen").forEach((s) => s.classList.remove("attivo"));
    $(`#scr-${nome}`).classList.add("attivo");
    if (nome !== "gioco") {
      $("#ov-passa").classList.add("nascosto");
      $("#ov-pausa").classList.add("nascosto");
      this.chiudiModal();
    }
    if (nome === "lobby") $("#lobby-nome").textContent = `${this.avatar} ${this.nome}`;
  }

  apriModal(contenuto, chiudibile = false) {
    const box = $("#ov-modal-box");
    box.innerHTML = "";
    box.append(contenuto);
    this.modalChiudibile = chiudibile;
    $("#ov-modal").classList.remove("nascosto");
  }
  chiudiModal() { $("#ov-modal").classList.add("nascosto"); }

  vaiStanza(tid) {
    const t = this.tavoli[tid];
    if (!t) { toast("Il tavolo non esiste più"); this.mostra("lobby"); return; }
    this.stanza = tid;
    // aprendo la stanza di una partita in corso si resta nella stanza (per terminarla o eliminare il
    // tavolo): in partita si entra con "Rientra"
    if (t.stato === "in_corso") this.uscitoDa = tid;
    this.mostra("stanza");
    if (t) renderStanza(this, t);
    this.rete.invia({ type: "apri", tavolo: tid });
  }

  /** Riprende il posto che nel frattempo era di un bot, poi entra in partita. */
  riprendi(tid) {
    this.attendiRientro = tid;
    if (this.partita.tid === tid) this.partita.tid = null;   // si riparte dagli stati nuovi (niente riepiloghi vecchi)
    this.rete.invia({ type: "riprendi", tavolo: tid });
  }

  /** Il server ci ha sostituito con un bot (uscita volontaria, inattività o disconnessione). */
  sostituito(m) {
    this.partita.miei = [];
    if (m.motivo === "uscito") return;               // la stanza è già aperta da chi è uscito
    const tid = m.tavolo;
    this.uscitoDa = tid;
    if (m.interrotta) {
      toast("La partita è stata chiusa: non c'erano altri giocatori");
      if (this.schermo === "gioco") this.mostra("lobby");
      return;
    }
    const perche = m.motivo === "inattivo"
      ? "Non hai giocato per qualche minuto mentre gli altri ti aspettavano."
      : "Sei rimasto disconnesso per qualche minuto.";
    const box = el("div", {},
      el("p", { class: "grande-testo" }, "Al tuo posto gioca un bot"),
      el("p", {}, `${perche} La partita è andata avanti con un bot al tuo posto: puoi riprenderlo quando vuoi.`),
      el("div", { class: "riga-btn" },
        el("button", { class: "btn primario", onclick: () => { this.chiudiModal(); this.riprendi(tid); } }, "Riprendi il posto"),
        el("button", { class: "btn", onclick: () => { this.chiudiModal(); this.mostra("lobby"); } }, "Lobby")));
    if (this.schermo !== "gioco") this.mostra("lobby");
    this.apriModal(box);
  }

  /** Guarda una partita tra soli bot (si vedono tutte le carte, a ritmo umano). */
  guarda(tid) {
    this.guardando = tid;
    this.uscitoDa = null;
    this.rete.invia({ type: "guarda", tavolo: tid });
  }

  smettiDiGuardare() {
    if (this.guardando) this.rete.invia({ type: "smetti", tavolo: this.guardando });
    this.guardando = null;
  }

  entraInPartita(tid) {
    const t = this.tavoli[tid];
    this.uscitoDa = null;
    this.stanza = tid;
    this.partita.apri(tid, t ? t.miei : [], this.guardando === tid);
    if (this.partita.vecchiaFinita() && t && t.stato === "in_corso") this.partita.nuovaPartita();
    this.mostra("gioco");
    this.partita.modalRiepilogo = false;
    this.partita.modalFinale = false;
    this.partita.render();
    this.rete.invia({ type: "apri", tavolo: tid });
  }

  menuGioco() {
    const t = this.tavoli[this.partita.tid];
    const tid = this.partita.tid;
    const spettatore = this.partita.spettatore;
    const box = el("div", {},
      el("h3", {}, spettatore ? "Stai guardando" : "Menu"),
      el("div", { class: "opzioni" },
        el("button", { class: "btn", onclick: () => { this.chiudiModal(); } }, spettatore ? "Continua a guardare" : "Riprendi"),
        spettatore
          ? el("button", { class: "btn", onclick: () => { this.smettiDiGuardare(); this.uscitoDa = tid; this.mostra("lobby"); } }, "Smetti di guardare")
          : el("button", { class: "btn", onclick: () => { this.uscitoDa = tid; this.mostra("lobby"); } }, "Torna alla lobby (la partita continua)"),
        t && (t.owner || (t.miei && t.miei.length)) ? el("button", {
          class: "btn pericolo", onclick: () => this.confermaTermina(tid),
        }, "Termina la partita") : null));
    this.apriModal(box, true);
  }

  /** Conferma dentro il gioco (niente finestra del browser). */
  confermaTermina(tid, dalGioco = true) {
    const box = el("div", {},
      el("h3", {}, "Terminare la partita?"),
      el("p", {}, "La partita finisce per tutti i giocatori e nello storico risulterà interrotta."),
      el("div", { class: "riga-btn" },
        el("button", { class: "btn pericolo", onclick: () => {
          this.rete.invia({ type: "termina", tavolo: tid });
          this.chiudiModal();
          toast("Partita terminata");
        } }, "Sì, termina"),
        el("button", { class: "btn", onclick: () => (dalGioco ? this.menuGioco() : this.chiudiModal()) }, "Annulla")));
    this.apriModal(box, true);
  }

  messaggio(m) {
    switch (m.type) {
      case "codice_richiesto":
        $("#codice-errato").classList.toggle("nascosto", !m.errato);
        $("#form-codice button").disabled = false;
        $("#ov-connessione").classList.add("nascosto");
        if (m.errato) store("bazzica_codice", null);
        this.mostra("codice");
        setTimeout(() => { const i = $("#inp-codice"); i.value = ""; i.focus(); }, 50);
        break;
      case "benvenuto":
        if (this.schermo === "codice") this.mostra(this.nome ? "lobby" : "nome");
        if (this.nome && (!m.nome || m.avatar !== this.avatar)) this.rete.invia({ type: "nome", nome: this.nome, avatar: this.avatar });
        break;
      case "lobby":
        if (m.varianti) this.varianti = m.varianti;
        for (const t of m.tavoli) this.aggiornaTavolo(t);
        for (const id of Object.keys(this.tavoli)) if (!m.tavoli.some((t) => t.id === id)) delete this.tavoli[id];
        renderLobby(this, m.tavoli);
        if (this.schermo === "stanza" && this.stanza && !this.tavoli[this.stanza]) { toast("Il tavolo è stato eliminato"); this.mostra("lobby"); }
        break;
      case "tavolo":
        this.aggiornaTavolo(m.tavolo);
        if (this.attendiTavoloCreato) { this.attendiTavoloCreato = false; this.vaiStanza(m.tavolo.id); }
        break;
      case "stato":
      case "eventi": {
        const t = this.tavoli[m.tavolo];
        if (m.spettatore) {
          // partita tra bot guardata da qui
          if (this.guardando !== m.tavolo) break;
          if (!(this.schermo === "gioco" && this.partita.tid === m.tavolo)) this.entraInPartita(m.tavolo);
          this.partita.ricevi(m);
          break;
        }
        const giocoAttivo = this.schermo === "gioco" && this.partita.tid === m.tavolo;
        if (!giocoAttivo && t && t.miei.length && this.uscitoDa !== m.tavolo && ["lobby", "stanza"].includes(this.schermo)
            && (this.schermo === "lobby" || this.stanza === m.tavolo) && t.stato === "in_corso") {
          this.entraInPartita(m.tavolo);
        }
        if (this.partita.tid !== m.tavolo && t && t.miei.length) this.partita.apri(m.tavolo, t.miei);
        this.partita.ricevi(m);
        break;
      }
      case "sostituito":
        this.sostituito(m);
        break;
      case "errore":
        if (this.attendiRientro) this.attendiRientro = null;
        toast(m.messaggio);
        this.partita.inviato = false;
        if (this.schermo === "gioco") this.partita.render();
        break;
      default:
        break;
    }
  }

  aggiornaTavolo(t) {
    const prima = this.tavoli[t.id];
    // "miei" e "owner" arrivano personalizzati per questo token
    this.tavoli[t.id] = t;
    if (this.schermo === "stanza" && this.stanza === t.id) renderStanza(this, t);
    if (this.attendiRientro === t.id && t.miei.length && t.stato === "in_corso") {
      this.attendiRientro = null;
      this.entraInPartita(t.id);
      return;
    }
    if (prima && prima.stato !== "in_corso" && t.stato === "in_corso" && t.miei.length && this.stanza === t.id) {
      this.entraInPartita(t.id);
    }
    // 4 bot avviati da qui: si entra a guardare
    if (prima && prima.stato !== "in_corso" && t.stato === "in_corso" && !t.miei.length && t.guardabile
        && this.stanza === t.id && this.schermo === "stanza") {
      this.guarda(t.id);
    }
  }
}

const app = new App();
window.bazzica = app;
app.avvia();
