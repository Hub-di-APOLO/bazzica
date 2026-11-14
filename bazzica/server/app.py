"""Applicazione FastAPI: file statici, API dello storico e WebSocket di gioco."""
from __future__ import annotations

import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..engine import MAZZO
from .account import ErroreAccount, LimiteTentativi, identita, impostazioni_di, normalizza_nome
from .config import Config
from .sicurezza import (codice_valido, ip_reale, Secchiello, ContaConnessioni, CHIUSURA_CODICE,
                        CHIUSURA_TROPPE_CONN, CHIUSURA_MESSAGGIO, CHIUSURA_FREQUENZA)
from .tables import Manager

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "bazzica" / "web"
ASSETS = ROOT / "assets"
TOKEN_VALIDO = re.compile(r"[A-Za-z0-9_-]{1,64}")
ATTESA_CODICE_ERRATO = 0.5     # secondi di attesa dopo un codice errato (rallenta i tentativi)
ATTESA_LOGIN_ERRATO = 0.5      # secondi di attesa dopo un login errato
ATTESA_SESSIONE_WS = 5.0       # secondi entro cui il client manda il token di sessione sulla WebSocket
MAX_CORPO_ACCOUNT = 2048       # byte massimi del corpo delle richieste di registrazione e login


def carte_disponibili() -> dict:
    """Associa ogni carta al file immagine (convenzione o assets/cards/mapping.json)."""
    cards = ASSETS / "cards"
    mapping = {}
    mp = cards / "mapping.json"
    if mp.exists():
        try:
            mapping = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            mapping = {}
    out, mancanti = {}, []
    for c in list(MAZZO) + ["dorso"]:
        f = mapping.get(c, f"{c}.png")
        if (cards / f).exists():
            out[c] = f"/assets/cards/{f}"
        else:
            mancanti.append(c)
    suoni = sorted(p.name for p in (ASSETS / "sounds").glob("*") if p.suffix.lower() in (".mp3", ".ogg", ".wav")) \
        if (ASSETS / "sounds").exists() else []
    return {"carte": out, "mancanti": mancanti, "suoni": suoni}


def create_app(manager: Manager | None = None, config: Config | None = None) -> FastAPI:
    """Crea l'applicazione. Senza argomenti legge la configurazione dalle variabili d'ambiente."""
    if manager is not None:
        cfg = config or manager.config
        manager.config = cfg
        m = manager
    else:
        cfg = config or Config.da_ambiente()
        os.makedirs(cfg.cartella_log, exist_ok=True)
        os.makedirs(cfg.cartella_dati, exist_ok=True)
        m = Manager(cartella_log=cfg.cartella_log, db_path=cfg.db_path, ritardo_bot=cfg.ritardo_bot, config=cfg)

    @asynccontextmanager
    async def ciclo_vita(_app):
        pulizia = asyncio.create_task(m.ciclo_pulizia())
        inattivita = asyncio.create_task(m.ciclo_inattivita())
        try:
            yield
        finally:
            pulizia.cancel()
            inattivita.cancel()

    app = FastAPI(title="Bazzica", lifespan=ciclo_vita)
    app.state.manager = m
    app.state.config = cfg

    @app.middleware("http")
    async def niente_cache_frontend(request, call_next):
        # il frontend cambia spesso: il browser deve sempre ricontrollare i file (niente versioni vecchie)
        risposta = await call_next(request)
        if request.url.path.startswith("/web/"):
            risposta.headers["Cache-Control"] = "no-cache"
        return risposta
    app.mount("/web", StaticFiles(directory=WEB), name="web")
    if ASSETS.exists():
        app.mount("/assets", StaticFiles(directory=ASSETS), name="assets")

    @app.get("/")
    async def index():
        return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/api/salute")
    async def api_salute():
        """Controllo leggero per l'healthcheck del container (niente codice d'accesso)."""
        try:
            m.storico.controlla()
        except Exception:
            return JSONResponse({"stato": "errore", "dettaglio": "storico non accessibile"}, status_code=503)
        return {"stato": "ok", "versione": os.environ.get("BAZZICA_VERSIONE", "sviluppo"), "tavoli": len(m.tavoli),
                "partite_in_corso": sum(t.stato == "in_corso" for t in m.tavoli.values()),
                "connessioni": sum(len(v) for v in m.conn.values())}

    @app.get("/api/carte")
    async def api_carte():
        return carte_disponibili()

    def verifica_codice(request: Request):
        """Lo storico contiene i nomi dei giocatori: con il codice attivo serve anche qui."""
        fornito = request.headers.get("x-bazzica-codice") or request.query_params.get("codice")
        if not codice_valido(cfg.codice, fornito):
            raise HTTPException(401, "Codice d'accesso richiesto")

    # ------------------------------------------------------------------ account
    # Limiti: secchiello per IP su tutte le richieste degli account, blocco dopo troppi login falliti
    # (per IP e per nome utente), numero massimo di registrazioni all'ora per IP.
    secchielli_ip: dict[str, Secchiello] = {}
    login_falliti = LimiteTentativi(cfg.login_max_falliti, cfg.login_finestra_min * 60, cfg.login_blocco_min * 60)
    registrazioni = LimiteTentativi(cfg.registrazioni_ora, 3600, 3600)
    app.state.login_falliti = login_falliti

    def ip_richiesta(request: Request) -> str:
        return ip_reale(request.client.host if request.client else None, request.headers.get("x-forwarded-for"),
                        cfg.proxy_fidati)

    async def richiesta_account(request: Request):
        """Controlli comuni: codice d'accesso, frequenza per IP, corpo JSON piccolo. Restituisce (ip, dati)."""
        verifica_codice(request)
        ip = ip_richiesta(request)
        sec = secchielli_ip.get(ip)
        if sec is None:
            if len(secchielli_ip) > 10000:
                secchielli_ip.clear()
            sec = secchielli_ip[ip] = Secchiello(1.0, 10)
        if not sec.consenti():
            raise HTTPException(429, "Troppe richieste, riprova tra poco")
        corpo = await request.body()
        if len(corpo) > MAX_CORPO_ACCOUNT:
            raise HTTPException(413, "Richiesta troppo grande")
        try:
            dati = json.loads(corpo or b"{}")
        except ValueError:
            raise HTTPException(400, "Richiesta non valida") from None
        if not isinstance(dati, dict):
            raise HTTPException(400, "Richiesta non valida")
        return ip, dati

    def token_sessione(request: Request) -> str:
        h = request.headers.get("authorization") or ""
        return h[7:].strip() if h.lower().startswith("bearer ") else ""

    def risposta_account(a: dict, sessione: str | None = None):
        out = {"account": {"nome": a["nome"], "avatar": a.get("avatar"), **m.ele_pubblico(a["id"]),
                           "partite": m.ele_cache_di(a["id"])["partite"],
                           "impostazioni": impostazioni_di(a)}}
        if sessione:
            out["sessione"] = sessione
        return out

    @app.post("/api/registrati")
    async def api_registrati(request: Request):
        ip, dati = await richiesta_account(request)
        if registrazioni.bloccato(ip):
            raise HTTPException(429, "Troppi account creati da questo indirizzo: riprova più tardi")
        nome, password = dati.get("nome"), dati.get("password")
        if not isinstance(nome, str) or not isinstance(password, str):
            raise HTTPException(400, "Servono nome utente e password")
        try:
            a = await asyncio.to_thread(m.account.registra, nome, password)
        except ErroreAccount as ex:
            raise HTTPException(400, str(ex)) from None
        registrazioni.fallito(ip)          # conta le registrazioni riuscite di questo IP
        sessione = await asyncio.to_thread(m.account.nuova_sessione, a["id"])
        return risposta_account(a, sessione)

    @app.post("/api/accedi")
    async def api_accedi(request: Request):
        ip, dati = await richiesta_account(request)
        nome, password = dati.get("nome"), dati.get("password")
        if not isinstance(nome, str) or not isinstance(password, str) or len(password) > 200:
            raise HTTPException(400, "Servono nome utente e password")
        chiave_nome = "nome:" + normalizza_nome(nome)[:40]
        if login_falliti.bloccato("ip:" + ip) or login_falliti.bloccato(chiave_nome):
            raise HTTPException(429, f"Troppi tentativi sbagliati: riprova tra {cfg.login_blocco_min:g} minuti")
        a = await asyncio.to_thread(m.account.verifica, nome, password)
        if a is None:
            login_falliti.fallito("ip:" + ip)
            login_falliti.fallito(chiave_nome)
            await asyncio.sleep(ATTESA_LOGIN_ERRATO)
            raise HTTPException(401, "Nome utente o password errati")
        login_falliti.riuscito(chiave_nome)
        sessione = await asyncio.to_thread(m.account.nuova_sessione, a["id"])
        return risposta_account(a, sessione)

    @app.post("/api/esci")
    async def api_esci(request: Request):
        await richiesta_account(request)
        tok = token_sessione(request)
        if tok:
            await asyncio.to_thread(m.account.revoca_sessione, tok)
        return {"ok": True}

    @app.get("/api/io")
    async def api_io(request: Request):
        verifica_codice(request)
        a = await asyncio.to_thread(m.account.da_sessione, token_sessione(request))
        if not a:
            raise HTTPException(401, "Sessione non valida o scaduta")
        return risposta_account(a)

    @app.post("/api/impostazioni")
    async def api_impostazioni(request: Request):
        """Cambia le impostazioni dell'account (es. {"note": false}); vale su tutti i suoi dispositivi."""
        _, dati = await richiesta_account(request)
        a = await asyncio.to_thread(m.account.da_sessione, token_sessione(request))
        if not a:
            raise HTTPException(401, "Sessione non valida o scaduta")
        try:
            tutte = await asyncio.to_thread(m.account.imposta_impostazioni, a["id"], dati)
        except ErroreAccount as ex:
            raise HTTPException(400, str(ex)) from None
        return {"impostazioni": tutte}

    @app.get("/api/classifica")
    async def api_classifica(request: Request):
        verifica_codice(request)
        return m.storico.classifica()

    @app.get("/api/giocatore/{nome}")
    async def api_giocatore(nome: str, request: Request):
        """Scheda pubblica di un giocatore con account (statistiche di tutte le partite o solo valutate)."""
        verifica_codice(request)
        solo = request.query_params.get("valutate") in ("1", "true", "si")
        d = await asyncio.to_thread(m.storico.scheda, normalizza_nome(nome)[:40], solo)
        if not d:
            raise HTTPException(404, "Giocatore inesistente")
        return d

    @app.get("/api/storico")
    async def api_storico(request: Request):
        verifica_codice(request)
        return m.storico.elenco()

    @app.get("/api/storico/{pid}")
    async def api_storico_dettaglio(pid: int, request: Request):
        verifica_codice(request)
        d = m.storico.dettaglio(pid)
        if not d:
            raise HTTPException(404, "Partita non trovata")
        return d

    connessioni = ContaConnessioni()
    app.state.connessioni = connessioni

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        ip = ip_reale(ws.client.host if ws.client else None, ws.headers.get("x-forwarded-for"), cfg.proxy_fidati)
        if not connessioni.apri(ip, cfg.max_conn_ip):
            await ws.send_json({"type": "errore", "messaggio": "Troppe connessioni da questo indirizzo"})
            await ws.close(code=CHIUSURA_TROPPE_CONN)
            return
        try:
            await sessione(ws)
        finally:
            connessioni.chiudi(ip)

    async def sessione(ws: WebSocket):
        if not codice_valido(cfg.codice, ws.query_params.get("codice")):
            errato = bool(ws.query_params.get("codice"))
            if errato:
                await asyncio.sleep(ATTESA_CODICE_ERRATO)
            await ws.send_json({"type": "codice_richiesto", "errato": errato})
            await ws.close(code=CHIUSURA_CODICE)
            return
        token = ws.query_params.get("token") or ""
        if not TOKEN_VALIDO.fullmatch(token):
            token = m.nuovo_token()
        account = None
        if ws.query_params.get("auth"):
            # il token di sessione arriva nel primo messaggio, mai nell'indirizzo (che finisce nei log)
            try:
                primo = json.loads(await asyncio.wait_for(ws.receive_text(), ATTESA_SESSIONE_WS))
                sessione = primo.get("sessione") if isinstance(primo, dict) and primo.get("type") == "sessione" else None
            except (asyncio.TimeoutError, ValueError):
                sessione = None
            except WebSocketDisconnect:
                return
            account = await asyncio.to_thread(m.account.da_sessione, sessione) if isinstance(sessione, str) else None
            if account is None:
                await ws.send_json({"type": "sessione_non_valida"})
            else:
                token = identita(account["id"])
        nome = ws.query_params.get("nome")
        secchiello = Secchiello(cfg.max_msg_secondo, cfg.raffica_msg)
        scartati = 0
        await m.connetti(token, ws, nome, ws.query_params.get("avatar"), account=account)
        try:
            while True:
                testo = await ws.receive_text()
                if cfg.max_messaggio and len(testo.encode("utf-8")) > cfg.max_messaggio:
                    await ws.send_json({"type": "errore", "messaggio": "Messaggio troppo grande"})
                    await ws.close(code=CHIUSURA_MESSAGGIO)
                    break
                if not secchiello.consenti():
                    # troppi messaggi: si scartano; se si insiste, si chiude la connessione
                    scartati += 1
                    if scartati == 1:
                        await ws.send_json({"type": "errore", "messaggio": "Troppi messaggi, rallenta"})
                    if scartati > cfg.raffica_msg:
                        await ws.close(code=CHIUSURA_FREQUENZA)
                        break
                    continue
                scartati = 0
                try:
                    msg = json.loads(testo)
                    if not isinstance(msg, dict):
                        raise ValueError("Messaggio non valido")
                    await m.comando(token, msg)
                except (ValueError, KeyError, TypeError, IndexError) as ex:
                    await ws.send_json({"type": "errore", "messaggio": str(ex) or "Messaggio non valido"})
        except WebSocketDisconnect:
            pass
        finally:
            await m.disconnetti(token, ws)

    return app
