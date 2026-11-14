// Avvio dell'applicazione, navigazione tra schermate e smistamento dei messaggi.
import { $, $$, el, store, toast, AVATAR } from "./util.js";
import { Rete } from "./net.js";
import { caricaCarte } from "./cards.js";
import { impostaFileSuoni, isMuto, setMuto } from "./audio.js";
import { initLobby, renderLobby, renderStanza } from "./lobby.js";
import { mostraStorico } from "./storico.js";
import { mostraClassifica } from "./classifica.js";
import { initAccesso, aggiornaAccount, aggiornaBarra, esci, noteAttive, impostaNote } from "./account.js";
import { initScheda, apriScheda } from "./giocatore.js";
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
    this.account = null;                 // {nome, ele, provvisorio, partite} se si è entrati con un account
    this.partita = new Partita(this);
    this.rete = new Rete((m) => this.messaggio(m));
  }

  async avvia() {
    const d = await caricaCarte();
    impostaFileSuoni(d.suoni);
    initLobby(this);
    initAccesso(this);
    initScheda(this);
    this.bind();
    // si entra con l'account salvato, come ospite (se scelto) oppure dalla schermata di accesso;
    // la connessione parte subito, così il codice d'accesso si chiede per primo
    if (store("bazzica_sessione")) this.mostra("lobby");
    else if (store("bazzica_ospite") && this.nome) this.mostra("lobby");
    else this.mostra("accesso");
    this.rete.connetti();
  }

  /** Schermata giusta dopo il codice d'accesso o il login. */
  schermataIniziale() {
    if (this.account || (store("bazzica_ospite") && this.nome)) return "lobby";
    return store("bazzica_ospite") ? "nome" : "accesso";
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
      if (this.account) {
        // con un account il nome è quello dell'account: si cambia solo l'avatar
        this.avatar = avatarScelto;
        store("bazzica_avatar", avatarScelto);
        this.rete.invia({ type: "nome", avatar: avatarScelto });
        this.mostra("lobby");
        return;
      }
      const n = $("#inp-nome").value.trim();
      if (!n) return;
      this.nome = n;
      this.avatar = avatarScelto;
      store("bazzica_nome", n);
      store("bazzica_avatar", avatarScelto);
      this.rete.invia({ type: "nome", nome: n, avatar: avatarScelto });
      this.mostra("lobby");
    });
    $("#btn-cambia-nome").addEventListener("click", () => {
      $("#inp-nome").value = this.nome;
      $("#label-nome").classList.toggle("nascosto", !!this.account);
      $("#inp-nome").required = !this.account;
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
    $("#btn-classifica").addEventListener("click", () => { this.mostra("classifica"); mostraClassifica(this); });
    // toccando il proprio nome nella lobby si apre la propria scheda
    $("#lobby-nome").addEventListener("click", () => { if (this.account) apriScheda(this, this.account.nome, "lobby"); });
    $("#btn-classifica-esci").addEventListener("click", () => this.mostra("lobby"));
    const muto = $("#btn-muto");
    const aggiornaMuto = () => { muto.innerHTML = isMuto() ? "&#128263;" : "&#128266;"; };
    aggiornaMuto();
    muto.addEventListener("click", () => { setMuto(!isMuto()); aggiornaMuto(); });
    $("#btn-menu").addEventListener("click", () => this.menuGioco());
    $("#btn-menu-pausa").addEventListener("click", () => this.menuGioco());
    $("#btn-impostazioni").addEventListener("click", () => this.menuImpostazioni());
    $("#ov-menu").addEventListener("click", (ev) => { if (ev.target.id === "ov-menu") this.chiudiMenu(); });
    $("#ov-modal").addEventListener("click", (ev) => { if (ev.target.id === "ov-modal" && this.modalChiudibile) this.chiudiModal(); });
  }

  mostra(nome) {
    this.schermo = nome;
    document.body.dataset.schermo = nome;
    $$(".screen").forEach((s) => s.classList.remove("attivo"));
    $(`#scr-${nome}`).classList.add("attivo");
    this.chiudiMenu();
    if (nome !== "gioco") {
      $("#ov-passa").classList.add("nascosto");
      $("#ov-pausa").classList.add("nascosto");
      this.chiudiModal();
    }
    if (nome === "lobby") {
      aggiornaBarra(this);
      if (this.account) aggiornaAccount(this);
    }
    if (nome === "nome") {
      $("#label-nome").classList.toggle("nascosto", !!this.account);
      $("#inp-nome").required = !this.account;
    }
  }

  apriModal(contenuto, chiudibile = false) {
    const box = $("#ov-modal-box");
    box.innerHTML = "";
    // in partita ogni finestra ha il ☰: c'è sempre una via d'uscita (tavolo, lobby, account)
    const conMenu = this.schermo === "gioco";
    box.classList.toggle("con-menu", conMenu);
    if (conMenu) box.append(el("button", { class: "btn icona btn-menu-modal", title: "Menu", onclick: () => this.menuGioco() }, "☰"));
    box.append(contenuto);
    this.modalChiudibile = chiudibile;
    $("#ov-modal").classList.remove("nascosto");
  }
  chiudiModal() { $("#ov-modal").classList.add("nascosto"); }

  /** Il menu sta sopra a ogni altra finestra e, chiuso, la lascia com'era. */
  apriMenu(contenuto) {
    const box = $("#ov-menu-box");
    box.innerHTML = "";
    box.append(contenuto);
    $("#ov-menu").classList.remove("nascosto");
  }
  chiudiMenu() { $("#ov-menu").classList.add("nascosto"); }

  /** Interruttore delle note scritte in sovraimpressione (impostazione dell'account o, da ospite, del dispositivo). */
  interruttoreNote() {
    const casella = el("input", { type: "checkbox", id: "imp-note" });
    casella.checked = noteAttive(this);
    casella.addEventListener("change", async () => {
      const v = casella.checked;
      casella.disabled = true;
      try { await impostaNote(this, v); } catch (e) { casella.checked = !v; toast(e.message || "Impostazione non salvata"); }
      casella.disabled = false;
    });
    return el("label", { class: "menu-impostazioni", for: "imp-note" },
      el("span", {}, "Note scritte durante la partita",
        el("small", {}, this.account ? "Carte passate, inizio Mano, crediti e avvisi in sovraimpressione. Vale per il tuo account su ogni dispositivo."
          : "Carte passate, inizio Mano, crediti e avvisi in sovraimpressione. Da ospite vale solo su questo dispositivo.")),
      casella);
  }

  bottoneAccount() {
    return this.account
      ? el("button", { class: "btn", onclick: () => { this.chiudiMenu(); this.chiudiModal(); this.smettiDiGuardare(); esci(this); } }, "Esci dall'account")
      : el("button", { class: "btn", onclick: () => { this.chiudiMenu(); this.chiudiModal(); this.smettiDiGuardare(); store("bazzica_ospite", null); this.mostra("accesso"); } }, "Schermata di accesso");
  }

  menuImpostazioni() {
    this.apriMenu(el("div", {},
      el("h3", {}, "Impostazioni"),
      this.interruttoreNote(),
      el("div", { class: "opzioni" },
        el("button", { class: "btn primario", onclick: () => this.chiudiMenu() }, "Fatto"),
        this.bottoneAccount())));
  }

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
    const inCorso = t && t.stato === "in_corso";
    // si lascia la partita (che continua) per andare altrove: niente rientro automatico
    const lascia = (dove) => {
      this.chiudiMenu();
      this.chiudiModal();
      if (spettatore) this.smettiDiGuardare();
      this.uscitoDa = tid;
      if (dove === "tavolo" && t) this.vaiStanza(tid);
      else this.mostra("lobby");
    };
    const box = el("div", {},
      el("h3", {}, spettatore ? "Stai guardando" : "Menu"),
      el("div", { class: "opzioni" },
        el("button", { class: "btn primario", onclick: () => this.chiudiMenu() }, spettatore ? "Continua a guardare" : "Torna alla partita"),
        t ? el("button", { class: "btn", onclick: () => lascia("tavolo") },
          spettatore ? "Smetti di guardare e vai al tavolo" : inCorso ? "Vai alla stanza del tavolo (la partita continua)" : "Torna al tavolo") : null,
        el("button", { class: "btn", onclick: () => lascia("lobby") },
          spettatore ? "Smetti di guardare e vai alla lobby" : inCorso ? "Torna alla lobby (la partita continua)" : "Torna alla lobby"),
        inCorso && (t.owner || (t.miei && t.miei.length)) ? el("button", {
          class: "btn pericolo", onclick: () => this.confermaTermina(tid),
        }, "Termina la partita") : null),
      this.interruttoreNote(),
      el("div", { class: "opzioni" }, this.bottoneAccount()));
    this.apriMenu(box);
  }

  /** Conferma dentro il gioco (niente finestra del browser). */
  confermaTermina(tid, dalGioco = true) {
    const box = el("div", {},
      el("h3", {}, "Terminare la partita?"),
      el("p", {}, "La partita finisce per tutti i giocatori e nello storico risulterà interrotta."),
      el("div", { class: "riga-btn" },
        el("button", { class: "btn pericolo", onclick: () => {
          this.rete.invia({ type: "termina", tavolo: tid });
          if (dalGioco) this.chiudiMenu(); else this.chiudiModal();
          toast("Partita terminata");
        } }, "Sì, termina"),
        el("button", { class: "btn", onclick: () => (dalGioco ? this.menuGioco() : this.chiudiModal()) }, "Annulla")));
    if (dalGioco) this.apriMenu(box);
    else this.apriModal(box, true);
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
        this.account = m.account || null;
        if (this.account) {
          if (m.avatar) { this.avatar = m.avatar; store("bazzica_avatar", m.avatar); }
          else this.rete.invia({ type: "nome", avatar: this.avatar });
        } else if (this.nome && (!m.nome || m.nome !== this.nome || m.avatar !== this.avatar)) {
          this.rete.invia({ type: "nome", nome: this.nome, avatar: this.avatar });
        }
        if (["codice", "accesso"].includes(this.schermo) || (this.schermo === "lobby" && this.schermataIniziale() !== "lobby")) {
          this.mostra(this.schermataIniziale());
        } else if (this.schermo === "lobby") aggiornaBarra(this);
        break;
      case "sessione_non_valida":
        store("bazzica_sessione", null);
        this.account = null;
        toast("La sessione è scaduta: accedi di nuovo");
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
        if (!this.account && /appartiene a un account/.test(m.messaggio) && this.schermo === "lobby") {
          // nome già registrato da un altro giocatore: se ne sceglie un altro
          this.nome = "";
          store("bazzica_nome", null);
          $("#inp-nome").value = "";
          this.mostra("nome");
        }
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
