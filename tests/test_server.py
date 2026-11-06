"""Test del server: lobby, partita via WebSocket, sicurezza informativa, storico, riconnessione."""
import pytest
from fastapi.testclient import TestClient

from bazzica.server.app import create_app
from bazzica.server.tables import Manager


@pytest.fixture
def client(tmp_path):
    m = Manager(cartella_log=str(tmp_path / "logs"), db_path=str(tmp_path / "s.db"), ritardo_bot=(0, 0),
                pausa_fine_mano=0)
    app = create_app(m)
    with TestClient(app) as c:
        c.manager = m
        c.tmp = tmp_path
        yield c


def ricevi_fino(ws, cond, max_msg=5000):
    for _ in range(max_msg):
        msg = ws.receive_json()
        if cond(msg):
            return msg
    raise AssertionError("messaggio atteso non ricevuto")


def crea_con_bot(ws, variante="Vanilla", posto=2):
    ws.send_json({"type": "crea_tavolo", "variante": variante, "nome": "Prova"})
    t = ricevi_fino(ws, lambda m: m["type"] == "tavolo")["tavolo"]
    tid = t["id"]
    ws.send_json({"type": "siedi", "tavolo": tid, "posto": posto, "nome": "Paolo"})
    for p in range(4):
        if p != posto:
            ws.send_json({"type": "bot", "tavolo": tid, "posto": p, "aggiungi": True})
    ricevi_fino(ws, lambda m: m["type"] == "tavolo" and all(m["tavolo"]["posti"]))
    return tid


def test_api_carte_e_index(client):
    r = client.get("/api/carte")
    assert r.status_code == 200
    assert "carte" in r.json()
    assert client.get("/").status_code == 200


@pytest.mark.parametrize("variante", ["Vanilla", "Avogadro"])
def test_partita_completa_un_umano_tre_bot(client, variante):
    with client.websocket_connect("/ws?token=tok1&nome=Paolo") as ws:
        tid = crea_con_bot(ws, variante)
        ws.send_json({"type": "avvia", "tavolo": tid})
        finita = False
        for _ in range(20000):
            msg = ws.receive_json()
            if msg["type"] == "eventi":
                for e in msg["eventi"]:
                    # sicurezza: nessuna carta privata di altri posti
                    if e["tipo"] in ("carte_ricevute",):
                        assert e["seat"] == 2
                    if e["tipo"] == "scambio_carta":
                        assert 2 in (e["seat"], e["a"])
                    if e["tipo"] == "fine_partita":
                        finita = True
            if finita:
                break
            if msg["type"] == "stato":
                obs = msg["obs"]
                for k, o in obs["altri"].items():
                    if k not in obs["bazziche"]:
                        assert o["carte"] is None
                if msg["info"]["attesa_ack"]:
                    ws.send_json({"type": "prosegui", "tavolo": tid})
                    continue
                leg = [a for a in msg["legali"] if a["tipo"] in ("gioca", "passa")]
                if leg and (obs["corrente"] == 2 or obs["fase"] == "scambio"):
                    a = leg[0]
                    ws.send_json({"type": "azione", "tavolo": tid, "posto": 2, "azione": a})
        assert finita
    st = client.get("/api/storico").json()
    assert st and st[0]["esito"] in ("Squadra 1", "Squadra 2", "pari")
    det = client.get(f"/api/storico/{st[0]['id']}").json()
    assert len(det["mani"]) == st[0]["n_mani"] >= 1
    logs = list((client.tmp / "logs").glob("*.txt"))
    testo = logs[0].read_text(encoding="utf-8")
    assert "Riepilogo Mano 1" in testo and "Carte di" in testo


def test_azione_non_valida_rifiutata(client):
    with client.websocket_connect("/ws?token=tok2") as ws:
        tid = crea_con_bot(ws)
        ws.send_json({"type": "azione", "tavolo": tid, "posto": 2, "azione": {"tipo": "gioca"}})
        m = ricevi_fino(ws, lambda m: m["type"] == "errore")
        assert "partita" in m["messaggio"].lower()


def test_pausa_e_riconnessione(client):
    with client.websocket_connect("/ws?token=tok3") as ws:
        tid = crea_con_bot(ws, posto=0)
        ws.send_json({"type": "avvia", "tavolo": tid})
        ricevi_fino(ws, lambda m: m["type"] == "stato")
    tav = client.manager.tavoli[tid]
    assert tav.in_pausa
    with client.websocket_connect("/ws?token=tok3") as ws:
        m = ricevi_fino(ws, lambda m: m["type"] == "stato")
        assert m["posto"] == 0
        assert not tav.in_pausa


def test_frasi_e_avatar(client):
    with client.websocket_connect("/ws?token=tokF&nome=Paolo&avatar=🐸") as ws:
        tid = crea_con_bot(ws)
        tav = client.manager.tavoli[tid]
        assert tav.posti[2]["avatar"] == "🐸"
        assert tav.posti[0]["avatar"] == "🤖"
        ws.send_json({"type": "avvia", "tavolo": tid})
        ricevi_fino(ws, lambda m: m["type"] == "stato")
        ws.send_json({"type": "frase", "tavolo": tid, "posto": 2, "indice": 9})
        m = ricevi_fino(ws, lambda m: m["type"] == "eventi" and any(e["tipo"] == "frase" for e in m["eventi"]))
        e = next(e for e in m["eventi"] if e["tipo"] == "frase")
        assert e["testo"] == "CHE CULO" and e["seat"] == 2


# ---------------------------------------------------------------- novità: termina, squadre, timer, striscia, chat

@pytest.fixture
def client_timer(tmp_path):
    m = Manager(cartella_log=str(tmp_path / "logs"), db_path=str(tmp_path / "s.db"), ritardo_bot=(0, 0),
                pausa_fine_mano=0, timer_scambio=0.4, timer_giocata=0.4)
    with TestClient(create_app(m)) as c:
        c.manager = m
        yield c


def test_termina_da_un_giocatore_non_creatore(client):
    with client.websocket_connect("/ws?token=capo&nome=Capo") as ws1, \
            client.websocket_connect("/ws?token=ospite&nome=Ospite") as ws2:
        ws1.send_json({"type": "crea_tavolo", "variante": "Vanilla"})
        tid = ricevi_fino(ws1, lambda m: m["type"] == "tavolo")["tavolo"]["id"]
        ws1.send_json({"type": "siedi", "tavolo": tid, "posto": 0})
        ws2.send_json({"type": "siedi", "tavolo": tid, "posto": 2})
        for p in (1, 3):
            ws1.send_json({"type": "bot", "tavolo": tid, "posto": p, "aggiungi": True})
        ricevi_fino(ws1, lambda m: m["type"] == "tavolo" and all(m["tavolo"]["posti"]))
        client.manager.ritardo_bot = (5, 5)        # i bot aspettano: la partita resta a metà
        ws1.send_json({"type": "avvia", "tavolo": tid})
        ricevi_fino(ws2, lambda m: m["type"] == "stato")
        ws2.send_json({"type": "termina", "tavolo": tid})
        m = ricevi_fino(ws1, lambda m: m["type"] == "stato" and m["info"]["stato"] == "finita")
        assert m["info"]["terminata_da"] == "Ospite"
    st = client.get("/api/storico").json()
    assert st[0]["esito"] == "interrotta"


def test_nomi_squadre_personalizzati(client):
    with client.websocket_connect("/ws?token=tokS&nome=Paolo") as ws:
        tid = crea_con_bot(ws)
        ws.send_json({"type": "imposta", "tavolo": tid, "squadre": ["Elementini", "  "]})
        t = ricevi_fino(ws, lambda m: m["type"] == "tavolo" and m["tavolo"]["squadre"][0] == "Elementini")["tavolo"]
        assert t["squadre"] == ["Elementini", "Squadra 2"]
        ws.send_json({"type": "avvia", "tavolo": tid})
        m = ricevi_fino(ws, lambda m: m["type"] == "stato")
        assert m["info"]["squadre"] == ["Elementini", "Squadra 2"]
    g = client.get("/api/storico").json()[0]["giocatori"]
    assert {x["squadra"] for x in g} == {"Elementini", "Squadra 2"}


def test_chat_bloccata_durante_lo_scambio_e_striscia(client):
    with client.websocket_connect("/ws?token=tokC&nome=Paolo") as ws:
        tid = crea_con_bot(ws, variante="Heisenberg", posto=2)
        client.manager.ritardo_bot = (5, 5)
        ws.send_json({"type": "avvia", "tavolo": tid})
        ricevi_fino(ws, lambda m: m["type"] == "stato" and m["obs"]["fase"] == "scambio")
        ws.send_json({"type": "frase", "tavolo": tid, "posto": 2, "indice": 0})
        assert "scambio" in ricevi_fino(ws, lambda m: m["type"] == "errore")["messaggio"]
        ws.send_json({"type": "azione", "tavolo": tid, "posto": 2, "azione": {"tipo": "che_palo"}})
        assert "scambio" in ricevi_fino(ws, lambda m: m["type"] == "errore")["messaggio"]
        # striscia: consentita solo mentre gioca il giocatore precedente (posto 1 per il posto 2)
        tav = client.manager.tavoli[tid]
        tav.st.fase = "gioco"
        tav.st.corrente = 0
        ws.send_json({"type": "striscia", "tavolo": tid, "posto": 2})   # non è il turno del precedente: ignorata
        tav.st.corrente = 1
        ws.send_json({"type": "striscia", "tavolo": tid, "posto": 2})
        m = ricevi_fino(ws, lambda m: m["type"] == "eventi" and m["eventi"][0]["tipo"] == "striscia")
        assert m["eventi"][0] == {"tipo": "striscia", "seat": 2, "verso": 1, "visibile": None}


def test_timer_scambio_e_giocata(client_timer):
    c = client_timer
    with c.websocket_connect("/ws?token=tokT&nome=Paolo") as ws:
        tid = crea_con_bot(ws, variante="Heisenberg", posto=2)
        ws.send_json({"type": "avvia", "tavolo": tid})
        m = ricevi_fino(ws, lambda m: m["type"] == "stato" and m["info"]["timer"])
        assert m["info"]["timer"]["tipo"] == "scambio" and m["info"]["timer"]["totale"] == 0.4
        # non passo: allo scadere passa una carta a caso per me
        ev = ricevi_fino(ws, lambda m: m["type"] == "eventi" and any(e["tipo"] == "tempo_scaduto" for e in m["eventi"]))
        assert any(e["tipo"] == "scambio_carta" and e["seat"] == 2 for e in ev["eventi"])
        # poi, quando tocca a me giocare, allo scadere gioca il bot al posto mio
        ev = ricevi_fino(ws, lambda m: m["type"] == "eventi" and any(
            e["tipo"] == "tempo_scaduto" and e["fase"] == "giocata" for e in m["eventi"]))
        assert any(e["tipo"] == "giocata" and e["seat"] == 2 for e in ev["eventi"])


def test_durate_timer_impostabili(client):
    with client.websocket_connect("/ws?token=tokD&nome=Paolo") as ws:
        tid = crea_con_bot(ws, variante="Heisenberg")
        ws.send_json({"type": "imposta", "tavolo": tid, "timer_scambio": 45, "timer_giocata": 0})
        t = ricevi_fino(ws, lambda m: m["type"] == "tavolo" and m["tavolo"]["timer_scambio"] == 45)["tavolo"]
        assert t["timer_giocata"] == 0
        ws.send_json({"type": "imposta", "tavolo": tid, "timer_scambio": 999})
        assert "timer" in ricevi_fino(ws, lambda m: m["type"] == "errore")["messaggio"]
        ws.send_json({"type": "avvia", "tavolo": tid})
        m = ricevi_fino(ws, lambda m: m["type"] == "stato" and m["info"]["timer"])
        assert m["info"]["timer"]["totale"] == 45


def test_spettatore_partita_tra_bot(client):
    with client.websocket_connect("/ws?token=tokV&nome=Paolo") as ws:
        ws.send_json({"type": "crea_tavolo", "variante": "Vanilla"})
        tid = ricevi_fino(ws, lambda m: m["type"] == "tavolo")["tavolo"]["id"]
        for p in range(4):
            ws.send_json({"type": "bot", "tavolo": tid, "posto": p, "aggiungi": True})
        ricevi_fino(ws, lambda m: m["type"] == "tavolo" and all(m["tavolo"]["posti"]))
        ws.send_json({"type": "avvia", "tavolo": tid})
        ricevi_fino(ws, lambda m: m["type"] == "lobby" and any(t["guardabile"] for t in m["tavoli"]))
        ws.send_json({"type": "guarda", "tavolo": tid})
        m = ricevi_fino(ws, lambda m: m["type"] == "stato")
        assert m["spettatore"] and m["info"]["spettatore"]
        assert all(o["carte"] is not None for o in m["obs"]["altri"].values())   # vede tutte le mani
        # finché non segnala di aver visto, i bot aspettano (ritmo umano); poi la partita prosegue
        ws.send_json({"type": "visto", "tavolo": tid, "versione": 10 ** 9})
        m = ricevi_fino(ws, lambda m: m["type"] == "eventi" and any(e["tipo"] == "giocata" for e in m["eventi"]))
        assert m["spettatore"]
        ws.send_json({"type": "smetti", "tavolo": tid})
    assert not client.manager.tavoli[tid].spettatori
