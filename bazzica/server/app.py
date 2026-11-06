"""Applicazione FastAPI: file statici, API dello storico e WebSocket di gioco."""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..engine import MAZZO
from .tables import Manager

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "bazzica" / "web"
ASSETS = ROOT / "assets"


def _ritardo():
    v = os.environ.get("BAZZICA_RITARDO_BOT", "0.8-1.5")
    try:
        lo, hi = (float(x) for x in v.split("-"))
        return lo, hi
    except ValueError:
        return 0.8, 1.5


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


def create_app(manager: Manager | None = None) -> FastAPI:
    app = FastAPI(title="Bazzica")
    os.makedirs(ROOT / "logs", exist_ok=True)
    os.makedirs(ROOT / "data", exist_ok=True)
    m = manager or Manager(cartella_log=str(ROOT / "logs"), db_path=str(ROOT / "data" / "storico.db"),
                           ritardo_bot=_ritardo())
    app.state.manager = m

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

    @app.get("/api/carte")
    async def api_carte():
        return carte_disponibili()

    @app.get("/api/storico")
    async def api_storico():
        return m.storico.elenco()

    @app.get("/api/storico/{pid}")
    async def api_storico_dettaglio(pid: int):
        d = m.storico.dettaglio(pid)
        if not d:
            raise HTTPException(404, "Partita non trovata")
        return d

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        token = ws.query_params.get("token") or m.nuovo_token()
        if len(token) > 64:
            token = m.nuovo_token()
        nome = ws.query_params.get("nome")
        await m.connetti(token, ws, nome, ws.query_params.get("avatar"))
        try:
            while True:
                msg = await ws.receive_json()
                try:
                    await m.comando(token, msg)
                except (ValueError, KeyError, TypeError) as ex:
                    await ws.send_json({"type": "errore", "messaggio": str(ex)})
        except WebSocketDisconnect:
            pass
        finally:
            await m.disconnetti(token, ws)

    return app
