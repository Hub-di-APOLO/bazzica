"""Limiti contro gli abusi: tavoli, connessioni per IP, dimensione e frequenza dei messaggi, IP reale."""
import ipaddress

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from bazzica.server.app import create_app
from bazzica.server.config import Config
from bazzica.server.sicurezza import ip_reale, Secchiello, ContaConnessioni
from bazzica.server.tables import Manager


def nuovo_client(tmp_path, **cfg):
    m = Manager(cartella_log=str(tmp_path / "logs"), db_path=str(tmp_path / "s.db"), ritardo_bot=(0, 0),
                pausa_fine_mano=0, config=Config(**cfg))
    return TestClient(create_app(m))


def ricevi_fino(ws, cond, max_msg=200):
    for _ in range(max_msg):
        msg = ws.receive_json()
        if cond(msg):
            return msg
    raise AssertionError("messaggio atteso non ricevuto")


def crea(ws):
    ws.send_json({"type": "crea_tavolo", "variante": "Vanilla"})
    return ricevi_fino(ws, lambda m: m["type"] in ("tavolo", "errore"))


def test_limite_tavoli_per_token_e_totale(tmp_path):
    with nuovo_client(tmp_path, max_tavoli=3, max_tavoli_token=2) as c:
        with c.websocket_connect("/ws?token=aaa") as a, c.websocket_connect("/ws?token=bbb") as b:
            assert crea(a)["type"] == "tavolo"
            assert crea(a)["type"] == "tavolo"
            err = crea(a)
            assert err["type"] == "errore" and "2 tavoli" in err["messaggio"]
            assert crea(b)["type"] == "tavolo"
            err = crea(b)
            assert err["type"] == "errore" and "troppi tavoli" in err["messaggio"]
            # eliminandone uno si libera il posto
            tid = next(iter(c.app.state.manager.tavoli))
            a.send_json({"type": "elimina", "tavolo": tid})
            assert crea(b)["type"] == "tavolo"


def test_limiti_zero_disattivati(tmp_path):
    with nuovo_client(tmp_path, max_tavoli=0, max_tavoli_token=0) as c:
        with c.websocket_connect("/ws?token=aaa") as a:
            for _ in range(15):
                assert crea(a)["type"] == "tavolo"


def test_connessioni_per_ip(tmp_path):
    with nuovo_client(tmp_path, max_conn_ip=2) as c:
        with c.websocket_connect("/ws?token=a1") as a, c.websocket_connect("/ws?token=a2") as b:
            assert a.receive_json()["type"] == "benvenuto" and b.receive_json()["type"] == "benvenuto"
            with c.websocket_connect("/ws?token=a3") as terza:
                assert terza.receive_json()["type"] == "errore"
                with pytest.raises(WebSocketDisconnect) as ex:
                    terza.receive_json()
                assert ex.value.code == 4429
        # chiuse le prime due, si può rientrare
        with c.websocket_connect("/ws?token=a4") as d:
            assert d.receive_json()["type"] == "benvenuto"
        assert c.app.state.connessioni.per_ip == {}


def test_messaggio_troppo_grande(tmp_path):
    with nuovo_client(tmp_path, max_messaggio=200) as c:
        with c.websocket_connect("/ws?token=aaa") as ws:
            ricevi_fino(ws, lambda m: m["type"] == "lobby")
            ws.send_json({"type": "nome", "nome": "x" * 50})       # piccolo: ok
            ws.send_text('{"type": "nome", "nome": "' + "x" * 300 + '"}')
            err = ricevi_fino(ws, lambda m: m["type"] == "errore")
            assert "troppo grande" in err["messaggio"]
            with pytest.raises(WebSocketDisconnect) as ex:
                ricevi_fino(ws, lambda m: False)
            assert ex.value.code == 4413


def test_frequenza_dei_messaggi(tmp_path):
    with nuovo_client(tmp_path, max_msg_secondo=0.001, raffica_msg=5) as c:
        with c.websocket_connect("/ws?token=aaa") as ws:
            ricevi_fino(ws, lambda m: m["type"] == "lobby")
            for _ in range(5):
                ws.send_json({"type": "lista"})
            ws.send_json({"type": "lista"})                        # sesto: scartato con avviso
            assert "rallenta" in ricevi_fino(ws, lambda m: m["type"] == "errore")["messaggio"]
            for _ in range(5):                                     # scartati in silenzio
                ws.send_json({"type": "lista"})
            ws.send_json({"type": "lista"})                        # oltre: chiusura
            with pytest.raises(WebSocketDisconnect) as ex:
                ricevi_fino(ws, lambda m: False)
            assert ex.value.code == 4408



@pytest.mark.parametrize("testo", ["non json", "[1, 2]", '{"type": "azione", "tavolo": null}', "{}"])
def test_json_non_valido_da_errore(tmp_path, testo):
    with nuovo_client(tmp_path) as c:
        with c.websocket_connect("/ws?token=aaa") as ws:
            ricevi_fino(ws, lambda m: m["type"] == "lobby")
            ws.send_text(testo)
            assert ricevi_fino(ws, lambda m: m["type"] == "errore")
            ws.send_json({"type": "lista"})
            assert ricevi_fino(ws, lambda m: m["type"] == "lobby")    # la connessione resta aperta


def test_token_non_valido_viene_sostituito(tmp_path):
    with nuovo_client(tmp_path) as c:
        with c.websocket_connect("/ws?token=" + "x" * 80) as ws:
            t = ws.receive_json()["token"]
            assert len(t) == 32
        with c.websocket_connect("/ws?token=a%3Cb") as ws:
            assert ws.receive_json()["token"] != "a<b"


# ---------------------------------------------------------------- funzioni pure
FIDATI = (ipaddress.ip_network("172.16.0.0/12"),)


@pytest.mark.parametrize("peer,xff,fidati,atteso", [
    ("203.0.113.5", None, FIDATI, "203.0.113.5"),                       # nessun header
    ("203.0.113.5", "1.2.3.4", FIDATI, "203.0.113.5"),                  # peer non fidato: header ignorato
    ("172.18.0.2", "1.2.3.4", (), "172.18.0.2"),                        # nessun proxy configurato
    ("172.18.0.2", "1.2.3.4", FIDATI, "1.2.3.4"),                       # dal proxy fidato
    ("172.18.0.2", "6.6.6.6, 1.2.3.4", FIDATI, "1.2.3.4"),              # catena falsificata dal client
    ("172.18.0.2", "1.2.3.4, 172.20.0.9", FIDATI, "1.2.3.4"),           # due proxy fidati
    ("172.18.0.2", "172.20.0.9", FIDATI, "172.20.0.9"),                 # client nella rete fidata
    ("172.18.0.2", "boh, 1.2.3.4", FIDATI, "1.2.3.4"),
    ("172.18.0.2", "1.2.3.4, boh", FIDATI, "172.18.0.2"),               # voce illeggibile: ci si ferma
    ("testclient", "1.2.3.4", FIDATI, "testclient"),
    ("::ffff:172.18.0.2", "1.2.3.4", FIDATI, "::ffff:172.18.0.2"),
])
def test_ip_reale(peer, xff, fidati, atteso):
    assert ip_reale(peer, xff, fidati) == atteso


def test_secchiello():
    t = [0.0]
    s = Secchiello(2, 3, orologio=lambda: t[0])
    assert [s.consenti() for _ in range(4)] == [True, True, True, False]
    t[0] = 0.5                       # +1 gettone
    assert s.consenti() and not s.consenti()
    t[0] = 100                       # non supera la raffica
    assert sum(s.consenti() for _ in range(10)) == 3
    assert all(Secchiello(0, 1).consenti() for _ in range(100))      # 0 = nessun limite


def test_conta_connessioni():
    c = ContaConnessioni()
    assert c.apri("a", 2) and c.apri("a", 2) and not c.apri("a", 2)
    assert c.apri("b", 2)
    c.chiudi("a")
    assert c.apri("a", 2)
    assert all(c.apri("z", 0) for _ in range(50))
