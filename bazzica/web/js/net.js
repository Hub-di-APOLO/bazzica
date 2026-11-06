// Connessione WebSocket con token persistente e riconnessione automatica.
import { store, $ } from "./util.js";

export class Rete {
  constructor(onMessage) {
    this.onMessage = onMessage;
    this.ws = null;
    this.token = store("bazzica_token") || "";
    this.coda = [];
    this.tentativi = 0;
  }

  connetti() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const nome = store("bazzica_nome") || "";
    const avatar = store("bazzica_avatar") || "";
    const url = `${proto}://${location.host}/ws?token=${encodeURIComponent(this.token)}&nome=${encodeURIComponent(nome)}&avatar=${encodeURIComponent(avatar)}`;
    const ws = new WebSocket(url);
    this.ws = ws;
    ws.onopen = () => {
      this.tentativi = 0;
      $("#ov-connessione").classList.add("nascosto");
      const q = this.coda; this.coda = [];
      q.forEach((m) => this.invia(m));
    };
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "benvenuto" && msg.token) {
        this.token = msg.token;
        store("bazzica_token", msg.token);
      }
      this.onMessage(msg);
    };
    ws.onclose = () => {
      $("#ov-connessione").classList.remove("nascosto");
      const attesa = Math.min(5000, 500 * 2 ** this.tentativi++);
      setTimeout(() => this.connetti(), attesa);
    };
  }

  invia(msg) {
    if (this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify(msg));
    else this.coda.push(msg);
  }
}
