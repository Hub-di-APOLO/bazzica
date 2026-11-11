"""Pulizia automatica: tavoli abbandonati e partite in pausa senza giocatori connessi."""
import time

from fastapi.testclient import TestClient

from bazzica.server.app import create_app
from bazzica.server.config import Config
from bazzica.server.tables import Manager

ORA = 3600  # secondi


def nuovo_client(tmp_path, **cfg):
    m = Manager(cartella_log=str(tmp_path / "logs"), db_path=str(tmp_path / "s.db"), ritardo_bot=(0, 0),
                pausa_fine_mano=0, config=Config(max_msg_secondo=0, **cfg))
    c = TestClient(create_app(m))
    c.manager = m
    return c


def ricevi_fino(ws, cond, max_msg=500):
    for _ in range(max_msg):
        msg = ws.receive_json()
        if cond(msg):
            return msg
    raise AssertionError("messaggio atteso non ricevuto")


def pulisci(c, dopo_secondi):
    """Esegue la pulizia come se fossero passati `dopo_secondi` secondi."""
    return c.portal.call(c.manager.pulizia, time.monotonic() + dopo_secondi)


def crea_tavolo(ws, siedi=True):
    ws.send_json({"type": "crea_tavolo", "variante": "Heisenberg"})
    tid = ricevi_fino(ws, lambda m: m["type"] == "tavolo")["tavolo"]["id"]
    if siedi:
        ws.send_json({"type": "siedi", "tavolo": tid, "posto": 0, "nome": "Paolo"})
        for p in (1, 2, 3):
            ws.send_json({"type": "bot", "tavolo": tid, "posto": p, "aggiungi": True})
        ricevi_fino(ws, lambda m: m["type"] == "tavolo" and all(m["tavolo"]["posti"]))
    return tid


def test_tavolo_non_avviato_abbandonato_viene_eliminato(tmp_path):
    with nuovo_client(tmp_path, tavolo_inattivo_min=30) as c:
        with c.websocket_connect("/ws?token=aaa") as ws:
            tid = crea_tavolo(ws)
            # finché il creatore è connesso il tavolo resta
            c.manager.tavoli[tid].ultima_attivita -= 10 * ORA
            assert pulisci(c, 0) == ([], [])
        with c.websocket_connect("/ws?token=bbb") as altro:
            ricevi_fino(altro, lambda m: m["type"] == "lobby")
            assert pulisci(c, 20 * 60) == ([], [])          # 20 minuti: ancora presto
            assert tid in c.manager.tavoli
            assert pulisci(c, 31 * 60) == ([tid], [])
            assert tid not in c.manager.tavoli
            lobby = ricevi_fino(altro, lambda m: m["type"] == "lobby" and not m["tavoli"])
            assert lobby["tavoli"] == []


def test_attivita_rinvia_la_pulizia(tmp_path):
    with nuovo_client(tmp_path, tavolo_inattivo_min=30) as c:
        with c.websocket_connect("/ws?token=aaa") as ws:
            tid = crea_tavolo(ws, siedi=False)
        c.manager.tavoli[tid].ultima_attivita = time.monotonic() - 29 * 60
        with c.websocket_connect("/ws?token=bbb") as b:
            ricevi_fino(b, lambda m: m["type"] == "lobby")
            b.send_json({"type": "apri", "tavolo": tid})    # qualcuno guarda il tavolo: attività
            ricevi_fino(b, lambda m: m["type"] == "tavolo")
        assert pulisci(c, 5 * 60) == ([], [])
        assert pulisci(c, 31 * 60) == ([tid], [])


def test_pulizia_disattivata(tmp_path):
    with nuovo_client(tmp_path, tavolo_inattivo_min=0, pausa_max_ore=0) as c:
        with c.websocket_connect("/ws?token=aaa") as ws:
            tid = crea_tavolo(ws)
            ws.send_json({"type": "avvia", "tavolo": tid})
            ricevi_fino(ws, lambda m: m["type"] == "stato")
        assert pulisci(c, 1000 * ORA) == ([], [])
        assert pulisci(c, 2000 * ORA) == ([], [])
        assert c.manager.tavoli[tid].stato == "in_corso"


def test_partita_in_pausa_senza_umani_viene_terminata(tmp_path):
    with nuovo_client(tmp_path, pausa_max_ore=2, tavolo_inattivo_min=30) as c:
        with c.websocket_connect("/ws?token=aaa") as ws:
            tid = crea_tavolo(ws)
            ws.send_json({"type": "avvia", "tavolo": tid})
            ricevi_fino(ws, lambda m: m["type"] == "stato")
            assert pulisci(c, 10 * ORA) == ([], [])        # connesso: non si tocca
        t = c.manager.tavoli[tid]
        assert t.in_pausa
        assert pulisci(c, 0) == ([], [])                    # inizia a contare
        assert pulisci(c, 1.9 * ORA) == ([], [])
        assert pulisci(c, 2.1 * ORA) == ([], [tid])
        assert t.stato == "finita"
        storico = c.get("/api/storico").json()
        assert storico[0]["esito"] == "interrotta"
        # poi, abbandonato, il tavolo finito viene eliminato come gli altri
        assert pulisci(c, 2.1 * ORA + 31 * 60) == ([tid], [])


def test_rientro_azzera_il_conteggio(tmp_path):
    with nuovo_client(tmp_path, pausa_max_ore=2) as c:
        with c.websocket_connect("/ws?token=aaa") as ws:
            tid = crea_tavolo(ws)
            ws.send_json({"type": "avvia", "tavolo": tid})
            ricevi_fino(ws, lambda m: m["type"] == "stato")
        pulisci(c, 0)
        assert pulisci(c, 1.5 * ORA) == ([], [])
        with c.websocket_connect("/ws?token=aaa") as ws:   # torna il giocatore
            ricevi_fino(ws, lambda m: m["type"] == "stato")
            pulisci(c, 1.6 * ORA)
        assert c.manager.tavoli[tid].senza_umani_da is None
        pulisci(c, 1.7 * ORA)                               # riparte da qui
        assert pulisci(c, 3.0 * ORA) == ([], [])
        assert pulisci(c, 3.8 * ORA) == ([], [tid])


def test_partita_tra_bot_non_viene_toccata(tmp_path):
    with nuovo_client(tmp_path, pausa_max_ore=1, tavolo_inattivo_min=1) as c:
        c.manager.ritardo_bot = (5, 5)        # i bot non finiscono la partita durante il test
        with c.websocket_connect("/ws?token=aaa") as ws:
            ws.send_json({"type": "crea_tavolo", "variante": "Vanilla"})
            tid = ricevi_fino(ws, lambda m: m["type"] == "tavolo")["tavolo"]["id"]
            for p in range(4):
                ws.send_json({"type": "bot", "tavolo": tid, "posto": p, "aggiungi": True})
            ricevi_fino(ws, lambda m: m["type"] == "tavolo" and all(m["tavolo"]["posti"]))
            ws.send_json({"type": "avvia", "tavolo": tid})
            ricevi_fino(ws, lambda m: m["type"] == "lobby" and m["tavoli"][0]["stato"] == "in_corso")
        assert pulisci(c, 100 * ORA) == ([], [])
        c.manager.tavoli[tid].termina()


def test_pulizia_dei_nomi_dei_token_spariti(tmp_path):
    with nuovo_client(tmp_path) as c:
        with c.websocket_connect("/ws?token=aaa&nome=Paolo") as ws:
            ricevi_fino(ws, lambda m: m["type"] == "lobby")
        with c.websocket_connect("/ws?token=bbb&nome=Luca") as ws:
            crea_tavolo(ws)
        pulisci(c, 0)
        assert "aaa" not in c.manager.nomi and c.manager.nomi.get("bbb") == "Luca"
