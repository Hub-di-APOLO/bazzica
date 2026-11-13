// Account: accesso, registrazione, gioco come ospite e uscita dall'account.
import { $, store, apiPost, apiGet, toast, testoEle } from "./util.js";

let modo = "accedi";

function impostaModo(nuovo) {
  modo = nuovo;
  const reg = modo === "registrati";
  $("#tab-accedi").classList.toggle("attiva", !reg);
  $("#tab-registrati").classList.toggle("attiva", reg);
  $("#acc-ripeti-label").classList.toggle("nascosto", !reg);
  $("#acc-regole").classList.toggle("nascosto", !reg);
  $("#acc-ripeti").required = reg;
  $("#acc-password").autocomplete = reg ? "new-password" : "current-password";
  $("#acc-invia").textContent = reg ? "Crea l'account" : "Accedi";
  $("#acc-errore").classList.add("nascosto");
}

function errore(msg) {
  const e = $("#acc-errore");
  e.textContent = msg;
  e.classList.remove("nascosto");
}

export function initAccesso(app) {
  $("#tab-accedi").addEventListener("click", () => impostaModo("accedi"));
  $("#tab-registrati").addEventListener("click", () => impostaModo("registrati"));
  $("#form-accesso").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const nome = $("#acc-nome").value.trim();
    const password = $("#acc-password").value;
    if (modo === "registrati" && password !== $("#acc-ripeti").value) { errore("Le due password non coincidono"); return; }
    const btn = $("#acc-invia");
    btn.disabled = true;
    try {
      const d = await apiPost(modo === "registrati" ? "/api/registrati" : "/api/accedi", { nome, password });
      store("bazzica_sessione", d.sessione);
      store("bazzica_ospite", null);
      app.account = d.account;
      $("#acc-password").value = "";
      $("#acc-ripeti").value = "";
      $("#acc-errore").classList.add("nascosto");
      app.rete.riconnetti();          // la WebSocket riparte con l'account
      app.mostra("lobby");
    } catch (e) {
      if (e.message === "Codice d'accesso richiesto") { store("bazzica_codice", null); app.rete.riconnetti(); }
      else errore(e.message);
    } finally {
      btn.disabled = false;
    }
  });
  $("#btn-ospite").addEventListener("click", () => {
    store("bazzica_ospite", "1");
    app.account = null;
    app.mostra(app.nome ? "lobby" : "nome");
  });
  $("#btn-account").addEventListener("click", () => {
    if (app.account) esci(app);
    else app.mostra("accesso");
  });
}

/** Esce dall'account su questo dispositivo (gli altri dispositivi restano collegati). */
export async function esci(app) {
  try { await apiPost("/api/esci"); } catch (e) { /* la sessione resta comunque dimenticata qui */ }
  store("bazzica_sessione", null);
  app.account = null;
  app.rete.riconnetti();
  app.mostra("accesso");
  toast("Sei uscito dall'account");
}

/** Aggiorna l'eLE del proprio account (es. tornando in lobby dopo una partita). */
export async function aggiornaAccount(app) {
  if (!store("bazzica_sessione")) return;
  try {
    const d = await apiGet("/api/io");
    app.account = d.account;
    aggiornaBarra(app);
  } catch (e) { /* si riprova al prossimo giro */ }
}

/** Nome, eLE e pulsanti nella barra della lobby. */
export function aggiornaBarra(app) {
  const a = app.account;
  const chip = $("#lobby-nome");
  chip.textContent = a ? `${app.avatar} ${a.nome} · eLE ${testoEle(a)} ›` : `${app.avatar} ${app.nome} (ospite)`;
  chip.classList.toggle("cliccabile", !!a);
  chip.title = a ? "Apri la tua scheda" : "";
  $("#btn-account").textContent = a ? "Esci" : "Accedi";
  $("#btn-cambia-nome").textContent = a ? "Avatar" : "Cambia nome";
}

export { impostaModo };
