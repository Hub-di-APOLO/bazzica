// Connessione WebSocket con token persistente e riconnessione automatica.
import { store, $ } from "./util.js";

/**
 * Indirizzo della WebSocket a partire da quello della pagina: wss:// se la pagina è in https://
 * (es. dietro il reverse proxy), ws:// altrimenti; stesso host e porta della pagina.
 * I parametri vuoti non vengono inviati (tranne token e nome, attesi dal server).
 */
export function urlWebSocket(loc, parametri) {
  const proto = loc.protocol === "https:" ? "wss:" : "ws:";
  const q = Object.entries(parametri)
    .filter(([k, v]) => v || k === "token" || k === "nome")
    .map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");
  return `${proto}//${loc.host}/ws?${q}`;
}

export class Rete {
  constructor(onMessage) {
    this.onMessage = onMessage;
    this.ws = null;
    this.token = store("bazzica_token") || "";
    this.coda = [];
    this.tentativi = 0;
  }

  connetti() {
    // con un account il token di sessione si manda come primo messaggio, mai nell'indirizzo
    const sessione = store("bazzica_sessione") || "";
    const url = urlWebSocket(location, {
      token: this.token, nome: store("bazzica_nome") || "", avatar: store("bazzica_avatar") || "",
      codice: store("bazzica_codice") || "", auth: sessione ? "1" : "",
    });
    clearTimeout(this.timerRiconnessione);
    this.bloccato = false;
    const ws = new WebSocket(url);
    this.ws = ws;
    ws.onopen = () => {
      if (sessione) ws.send(JSON.stringify({ type: "sessione", sessione }));
      this.tentativi = 0;
      $("#ov-connessione").classList.add("nascosto");
      const q = this.coda; this.coda = [];
      q.forEach((m) => this.invia(m));
    };
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      // codice d'accesso mancante o errato: niente riconnessioni finché non lo si inserisce
      if (msg.type === "codice_richiesto") this.bloccato = true;
      if (msg.type === "benvenuto" && msg.token) {
        this.token = msg.token;
        store("bazzica_token", msg.token);
      }
      this.onMessage(msg);
    };
    ws.onclose = (ev) => {
      if (ws !== this.ws) return;               // vecchia connessione già sostituita
      if (this.bloccato || ev.code === 4401) { this.bloccato = true; return; }
      $("#ov-connessione").classList.remove("nascosto");
      const attesa = Math.min(5000, 500 * 2 ** this.tentativi++);
      this.timerRiconnessione = setTimeout(() => this.connetti(), attesa);
    };
  }

  /** Riprova subito (es. dopo aver inserito il codice d'accesso). */
  riconnetti() {
    const vecchia = this.ws;
    this.ws = null;
    if (vecchia && vecchia.readyState <= 1) vecchia.close();
    this.tentativi = 0;
    this.connetti();
  }

  invia(msg) {
    if (this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify(msg));
    else this.coda.push(msg);
  }
}
