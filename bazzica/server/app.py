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
from .config import Config
from .sicurezza import (codice_valido, ip_reale, Secchiello, ContaConnessioni, CHIUSURA_CODICE,
                        CHIUSURA_TROPPE_CONN, CHIUSURA_MESSAGGIO, CHIUSURA_FREQUENZA)
from .tables import Manager

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "bazzica" / "web"
ASSETS = ROOT / "assets"
TOKEN_VALIDO = re.compile(r"[A-Za-z0-9_-]{1,64}")
ATTESA_CODICE_ERRATO = 0.5     # secondi di attesa dopo un codice errato (rallenta i tentativi)


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
        try:
            yield
        finally:
            pulizia.cancel()

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
        nome = ws.query_params.get("nome")
        secchiello = Secchiello(cfg.max_msg_secondo, cfg.raffica_msg)
        scartati = 0
        await m.connetti(token, ws, nome, ws.query_params.get("avatar"))
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
