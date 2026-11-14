"""Ritmo della partita: impostazione, attesa dei "visto" dei giocatori, tetto, timer e inattività, pensiero dei bot."""
import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from bazzica.engine import legal_actions, apply_inplace, Action, FASE_GIOCO, FASE_SCAMBIO
from bazzica.server import tables as T
from bazzica.server.app import create_app
from bazzica.server.config import Config
from bazzica.server.tables import Manager, Tavolo, RITMI


class FintoWS:
    def __init__(self):
        self.msgs = []

    async def send_json(self, m):
        self.msgs.append(m)


def manager(tmp_path, attesa=True, ritardo=(0, 0)):
    return Manager(cartella_log=str(tmp_path / "logs"), db_path=str(tmp_path / "s.db"), ritardo_bot=ritardo,
                   pausa_fine_mano=0, config=Config(), attesa_giocatori=attesa)


def tavolo(m, umani=("u1",), variante="Vanilla", posti_umani=None):
    """Tavolo con gli umani indicati (connessi con un finto websocket) e bot negli altri posti."""
    t = Tavolo(m, "t1", "Prova", umani[0], variante, False)
    m.tavoli["t1"] = t
    posti_umani = posti_umani or {tok: [i] for i, tok in enumerate(umani)}
    for tok, posti in posti_umani.items():
        m.conn[tok] = {FintoWS()}
        m.nomi[tok] = tok
        for p in posti:
            t.siedi(tok, p, tok)
    for p in range(4):
        if t.posti[p] is None:
            t.bot(p, True)
    return t


@pytest.fixture
def tetto_breve(monkeypatch):
    nuovi = {k: dict(v, tetto=0.6, finestra=0.0) for k, v in RITMI.items()}
    monkeypatch.setattr(T, "RITMI", nuovi)
    return nuovi


async def avvia(t):
    await t.gestisci_eventi(t.avvia())


def giocate(t):
    return len(t.st.giocate_mano) + 100 * t.st.mano_n


async def vede_tutto(t, g, token="u1", secondi=1.0):
    """Il client conferma ogni nuova versione (un bot può dichiarare la Bazzica prima di giocare) finché il bot
    non gioca o passano ``secondi``."""
    inizio = time.monotonic()
    while giocate(t) == g and time.monotonic() - inizio < secondi:
        await t.visto(token, t.versione)
        await asyncio.sleep(0.02)


async def turno_di_un_bot(t, token="u1"):
    """Porta la partita a un momento in cui deve giocare un bot (gioca l'umano se tocca a lui)."""
    for _ in range(4):
        st = t.st
        p = t.posti[st.corrente]
        if p["tipo"] == "bot":
            return
        a = next(a for a in legal_actions(st, st.corrente) if a.tipo == "gioca")
        await t.azione_umana(p["token"], st.corrente, a.to_dict())
    raise AssertionError("nessun turno di bot")


# --------------------------------------------------------------------------- impostazione

def test_imposta_ritmo_validato(tmp_path):
    m = manager(tmp_path, attesa=False)
    with TestClient(create_app(m)) as c, c.websocket_connect("/ws?token=aaa&nome=Anna") as ws:
        ws.send_json({"type": "crea_tavolo", "variante": "Vanilla"})
        t = None
        while not t:
            msg = ws.receive_json()
            t = msg["tavolo"] if msg["type"] == "tavolo" else None
        assert t["ritmo"] == "rilassato"                        # predefinito
        ws.send_json({"type": "imposta", "tavolo": t["id"], "ritmo": "svelto"})
        ws.send_json({"type": "imposta", "tavolo": t["id"], "ritmo": "turbo"})
        while True:
            msg = ws.receive_json()
            if msg["type"] == "errore":
                assert "Ritmo" in msg["messaggio"]
                break
        assert m.tavoli[t["id"]].ritmo == "svelto"
        tav = m.tavoli[t["id"]]
        ws.send_json({"type": "siedi", "tavolo": t["id"], "posto": 0})
        for p in (1, 2, 3):
            ws.send_json({"type": "bot", "tavolo": t["id"], "posto": p})
        ws.send_json({"type": "avvia", "tavolo": t["id"]})
        while True:
            msg = ws.receive_json()
            if msg["type"] == "stato":
                assert msg["info"]["ritmo"] == "svelto"           # riportato nell'info dello stato
                break
        ws.send_json({"type": "imposta", "tavolo": t["id"], "ritmo": "normale"})
        while ws.receive_json()["type"] != "errore":
            pass
        assert tav.ritmo == "svelto"                             # partita in corso: non si cambia


def test_visto_validato(tmp_path):
    m = manager(tmp_path)

    async def corpo():
        t = tavolo(m)
        await avvia(t)
        for cattivo in ("3", 1.5, True, -1, t.versione + 1, None):
            with pytest.raises(ValueError):
                await t.visto("u1", cattivo)
        await t.visto("u1", t.versione)
        assert t.visti["u1"] == t.versione
        await t.visto("u1", 0)                                   # una versione vecchia non torna indietro
        assert t.visti["u1"] == t.versione
        await t.visto("estraneo", t.versione)                    # né seduto né spettatore: ignorato
        assert "estraneo" not in t.visti
    asyncio.run(corpo())


# --------------------------------------------------------------------------- attesa dei bot

def test_il_bot_aspetta_il_visto(tmp_path, tetto_breve):
    m = manager(tmp_path)
    tetto_breve["rilassato"]["tetto"] = 5.0

    async def corpo():
        t = tavolo(m)
        await avvia(t)
        await turno_di_un_bot(t)
        g = giocate(t)
        t.sveglia()
        await asyncio.sleep(0.4)
        assert giocate(t) == g                                   # il bot aspetta che l'umano abbia visto
        await vede_tutto(t, g)
        assert giocate(t) > g                                    # visto: il bot gioca
        t.task.cancel()
    asyncio.run(corpo())


def test_tetto_massimo(tmp_path, tetto_breve):
    m = manager(tmp_path)

    async def corpo():
        t = tavolo(m)
        await avvia(t)
        await turno_di_un_bot(t)
        g = giocate(t)
        inizio = time.monotonic()
        t.sveglia()
        while giocate(t) == g and time.monotonic() - inizio < 3:
            await asyncio.sleep(0.05)
        attesa = time.monotonic() - inizio
        assert giocate(t) > g and 0.4 <= attesa < 1.5            # un client muto non blocca oltre il tetto
        t.task.cancel()
    asyncio.run(corpo())


def test_disconnessi_e_hot_seat(tmp_path):
    m = manager(tmp_path)

    async def corpo():
        t = tavolo(m, posti_umani={"u1": [0, 2], "u2": [1]})
        await avvia(t)
        assert t.da_aspettare() == {"u1", "u2"}
        await t.visto("u1", t.versione)                          # hot-seat: basta la conferma di quel client
        assert t.da_aspettare() == {"u2"}
        m.conn.pop("u2")                                         # disconnesso: non si aspetta
        assert t.da_aspettare() == set()
    asyncio.run(corpo())


def test_spettatori_non_aspettati_con_giocatori_umani(tmp_path, tetto_breve):
    m = manager(tmp_path)
    tetto_breve["rilassato"]["tetto"] = 5.0

    async def corpo():
        t = tavolo(m)
        await avvia(t)
        m.conn["spett"] = {FintoWS()}
        t.guarda("spett")                                        # non manda mai "visto"
        await turno_di_un_bot(t)
        g = giocate(t)
        t.sveglia()
        await vede_tutto(t, g)
        assert giocate(t) > g
        t.task.cancel()
    asyncio.run(corpo())


def test_senza_attesa_con_bot_istantanei(tmp_path):
    # BAZZICA_RITARDO_BOT=0-0 (prove): nessuna attesa dei giocatori
    assert manager(tmp_path, attesa=None, ritardo=(0, 0)).attesa_giocatori is False
    assert manager(tmp_path, attesa=None, ritardo=(0.8, 1.5)).attesa_giocatori is True


# --------------------------------------------------------------------------- timer e inattività

def test_timer_e_inattivita_partono_dopo_il_visto(tmp_path, tetto_breve):
    m = manager(tmp_path)
    tetto_breve["rilassato"]["tetto"] = 5.0

    async def corpo():
        t = tavolo(m)
        t.durata_giocata = 30
        await avvia(t)
        # porta il turno all'umano facendo giocare i bot (con il suo "visto" a ogni passo)
        for _ in range(8):
            if t.st.fase == FASE_GIOCO and t.posti[t.st.corrente]["tipo"] == "umano":
                break
            s = t.st.corrente
            a = next(a for a in legal_actions(t.st, s) if a.tipo == "gioca")
            await t.visto("u1", t.versione)
            await t.gestisci_eventi(apply_inplace(t.st, a))
        assert t.posti[t.st.corrente]["token"] == "u1"
        # le animazioni dell'ultima giocata sono ancora in corso: niente timer, niente inattività
        assert t.timer_chiave is None
        assert "u1" not in t.tokens_attesi()
        t.ultimo_controllo = None
        t.da_sostituire(100.0, 300)
        t.da_sostituire(160.0, 300)
        assert t.attesa.get("u1", 0) == 0
        # visto: parte il timer e l'inattività si conta
        await t.visto("u1", t.versione)
        assert t.timer_chiave and t.timer_chiave[0] == "giocata" and t.timer_totale == 30
        assert "u1" in t.tokens_attesi()
        t.da_sostituire(220.0, 300)
        assert t.attesa["u1"] == pytest.approx(30.0)              # dt limitato a 30 s per controllo
        t.ferma_timer()
    asyncio.run(corpo())


def test_timer_parte_al_tetto_senza_visto(tmp_path, tetto_breve):
    m = manager(tmp_path)

    async def corpo():
        t = tavolo(m)
        t.durata_scambio = 30
        t.variante = "Heisenberg"
        await avvia(t)
        assert t.st.fase == FASE_SCAMBIO and t.timer_chiave is None
        await asyncio.sleep(0.8)                                  # tetto 0,6 s scaduto
        assert t.timer_chiave and t.timer_chiave[0] == "scambio"
        t.ferma_timer()
    asyncio.run(corpo())


# --------------------------------------------------------------------------- pensiero dei bot

def test_pensiero_dentro_i_limiti_del_ritmo(tmp_path):
    m = manager(tmp_path, ritardo=(0.8, 1.5))

    async def corpo():
        t = tavolo(m, variante="Heisenberg")
        await avvia(t)
        st = t.st
        for ritmo, (lo, hi) in {"rilassato": (1.28, 2.4), "normale": (1.0, 1.875), "svelto": (0.8, 1.5)}.items():
            t.ritmo = ritmo
            valori = [t.pensiero(st, legal_actions(st, 1)) for _ in range(200)]   # scambio: scelta impegnativa
            assert lo - 1e-9 <= min(valori) and max(valori) <= hi + 1e-9
            assert sum(valori) / len(valori) > lo + 0.5 * (hi - lo)
        # una sola carta giocabile: pensiero breve (al minimo, salvo un piccolo margine casuale)
        t.ritmo = "rilassato"
        una = [Action("gioca", 1, carta="coppe_05", presa=())]
        gioco = _fase_gioco(st)
        assert all(t.pensiero(gioco, una) <= 1.28 + 0.1 * (2.4 - 1.28) + 1e-9 for _ in range(50))
    asyncio.run(corpo())


def _fase_gioco(st):
    c = st.copy()
    c.fase = FASE_GIOCO
    return c
