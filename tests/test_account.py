"""Account: registrazione, login, limiti dei tentativi, sessioni, WebSocket con account, comando admin."""
import io
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from bazzica import admin
from bazzica.server import app as app_mod
from bazzica.server.account import (controlla_nome, ErroreAccount, hash_password, verifica_password,
                                    normalizza_nome, LimiteTentativi)
from bazzica.server.app import create_app
from bazzica.server.config import Config
from bazzica.server.tables import Manager

PW = "password-lunga"


@pytest.fixture(autouse=True)
def niente_attese(monkeypatch):
    monkeypatch.setattr(app_mod, "ATTESA_LOGIN_ERRATO", 0)
    monkeypatch.setattr(app_mod, "ATTESA_CODICE_ERRATO", 0)


def nuovo_client(tmp_path, **cfg):
    cfg.setdefault("max_msg_secondo", 0)
    m = Manager(cartella_log=str(tmp_path / "logs"), db_path=str(tmp_path / "s.db"), ritardo_bot=(0, 0),
                pausa_fine_mano=0, config=Config(**cfg))
    c = TestClient(create_app(m))
    c.manager = m
    return c


def registra(c, nome="Paolo", password=PW, **kw):
    return c.post("/api/registrati", json={"nome": nome, "password": password}, **kw)


def ricevi_fino(ws, cond, max_msg=500):
    for _ in range(max_msg):
        msg = ws.receive_json()
        if cond(msg):
            return msg
    raise AssertionError("messaggio atteso non ricevuto")


# --------------------------------------------------------------------------- funzioni di base

def test_hash_con_sale_e_verifica():
    h1, s1 = hash_password("segreto123")
    h2, s2 = hash_password("segreto123")
    assert s1 != s2 and h1 != h2
    assert verifica_password("segreto123", h1, s1)
    assert not verifica_password("segreto124", h1, s1)
    assert "segreto" not in h1 + s1


@pytest.mark.parametrize("nome", ["Bot Nord", "bot", "BOT-ovest", "Bot_Sud", "Paolo (bot)", "ab", "x" * 21,
                                  "Paolo!", "🤖Paolo"])
def test_nomi_non_validi(nome):
    with pytest.raises(ErroreAccount):
        controlla_nome(nome)


def test_nomi_validi_e_normalizzati():
    assert controlla_nome("  Gian   Luca ") == "Gian Luca"
    assert controlla_nome("Niccolò_9") == "Niccolò_9"
    assert normalizza_nome("Gian Luca") == normalizza_nome("gianluca") == normalizza_nome("Gian-Luca")
    assert normalizza_nome("Niccolò") == normalizza_nome("niccolo")


def test_limite_tentativi_blocca_e_sblocca():
    ora = [0.0]
    lim = LimiteTentativi(3, 60, 100, orologio=lambda: ora[0])
    for _ in range(2):
        lim.fallito("x")
    assert not lim.bloccato("x")
    lim.fallito("x")
    assert lim.bloccato("x") and not lim.bloccato("y")
    ora[0] = 99
    assert lim.bloccato("x")
    ora[0] = 101
    assert not lim.bloccato("x")
    # i fallimenti vecchi escono dalla finestra
    lim.fallito("z")
    lim.fallito("z")
    ora[0] = 200
    lim.fallito("z")
    assert not lim.bloccato("z")


# --------------------------------------------------------------------------- HTTP

def test_registrazione_login_io_esci(tmp_path):
    with nuovo_client(tmp_path) as c:
        r = registra(c)
        assert r.status_code == 200
        d = r.json()
        assert d["account"]["nome"] == "Paolo" and d["account"]["ele"] == 1550 and d["account"]["provvisorio"]
        sess1 = d["sessione"]
        # il database contiene solo hash: né la password né il token in chiaro
        raw = (tmp_path / "s.db").read_bytes()
        assert PW.encode() not in raw and sess1.encode() not in raw
        # nome già usato (anche con maiuscole e spazi diversi)
        assert registra(c, "paolo").status_code == 400
        # login da un secondo dispositivo: un'altra sessione, la prima resta valida
        r = c.post("/api/accedi", json={"nome": "PAOLO", "password": PW})
        assert r.status_code == 200
        sess2 = r.json()["sessione"]
        assert sess2 != sess1
        for s in (sess1, sess2):
            io = c.get("/api/io", headers={"Authorization": f"Bearer {s}"})
            assert io.status_code == 200 and io.json()["account"]["nome"] == "Paolo"
            assert "sessione" not in io.json() and "hash" not in json.dumps(io.json())
        # uscita: revoca solo quella sessione
        assert c.post("/api/esci", headers={"Authorization": f"Bearer {sess1}"}).status_code == 200
        assert c.get("/api/io", headers={"Authorization": f"Bearer {sess1}"}).status_code == 401
        assert c.get("/api/io", headers={"Authorization": f"Bearer {sess2}"}).status_code == 200
        assert c.get("/api/io").status_code == 401


def test_registrazione_valida_i_dati(tmp_path):
    with nuovo_client(tmp_path) as c:
        assert registra(c, "Bot Nord").status_code == 400
        assert registra(c, "Mario", "corta").status_code == 400
        assert c.post("/api/registrati", content=b"non json").status_code == 400
        assert c.post("/api/registrati", json={"nome": "Mario"}).status_code == 400
        assert c.post("/api/registrati", content=b"{" + b" " * 5000 + b"}").status_code == 413


def test_login_errato(tmp_path):
    with nuovo_client(tmp_path) as c:
        registra(c)
        r = c.post("/api/accedi", json={"nome": "Paolo", "password": "sbagliata!!"})
        assert r.status_code == 401
        assert c.post("/api/accedi", json={"nome": "Nessuno", "password": PW}).status_code == 401
        # stesso messaggio per nome inesistente e password sbagliata
        assert r.json()["detail"] == "Nome utente o password errati"


def test_limite_tentativi_login(tmp_path):
    with nuovo_client(tmp_path, login_max_falliti=3) as c:
        registra(c)
        for _ in range(3):
            assert c.post("/api/accedi", json={"nome": "Paolo", "password": "sbagliata!!"}).status_code == 401
        # bloccato anche con la password giusta
        r = c.post("/api/accedi", json={"nome": "Paolo", "password": PW})
        assert r.status_code == 429
        assert c.post("/api/accedi", json={"nome": "Altro", "password": PW}).status_code == 429   # stesso IP


def test_limite_registrazioni_per_ip(tmp_path):
    with nuovo_client(tmp_path, registrazioni_ora=2) as c:
        assert registra(c, "Uno").status_code == 200
        assert registra(c, "Due").status_code == 200
        assert registra(c, "Tre").status_code == 429


def test_endpoint_account_protetti_dal_codice(tmp_path):
    with nuovo_client(tmp_path, codice="segreto") as c:
        assert registra(c).status_code == 401
        assert c.get("/api/classifica").status_code == 401
        assert registra(c, headers={"X-Bazzica-Codice": "segreto"}).status_code == 200
        assert c.get("/api/classifica", headers={"X-Bazzica-Codice": "segreto"}).status_code == 200


def test_sessione_scaduta_o_revocata(tmp_path):
    with nuovo_client(tmp_path) as c:
        s = registra(c).json()["sessione"]
        with sqlite3.connect(tmp_path / "s.db") as db:
            db.execute("UPDATE sessioni SET scadenza='2000-01-01T00:00:00'")
        assert c.get("/api/io", headers={"Authorization": f"Bearer {s}"}).status_code == 401
        s2 = c.post("/api/accedi", json={"nome": "Paolo", "password": PW}).json()["sessione"]
        c.manager.account.revoca_tutte("Paolo")
        assert c.get("/api/io", headers={"Authorization": f"Bearer {s2}"}).status_code == 401


# --------------------------------------------------------------------------- WebSocket

def test_websocket_con_sessione_usa_il_nome_dell_account(tmp_path):
    with nuovo_client(tmp_path) as c:
        s = registra(c).json()["sessione"]
        # il token di sessione non va nell'indirizzo: arriva come primo messaggio
        with c.websocket_connect("/ws?token=browser1&nome=Altro&auth=1") as ws:
            ws.send_json({"type": "sessione", "sessione": s})
            b = ricevi_fino(ws, lambda m: m["type"] == "benvenuto")
            assert b["account"]["nome"] == "Paolo" and b["nome"] == "Paolo"
            assert b["token"] is None            # l'identità interna dell'account non si manda al client
            ws.send_json({"type": "crea_tavolo", "variante": "Vanilla"})
            t = ricevi_fino(ws, lambda m: m["type"] == "tavolo")["tavolo"]
            ws.send_json({"type": "siedi", "tavolo": t["id"], "posto": 0, "nome": "Finto"})
            t = ricevi_fino(ws, lambda m: m["type"] == "tavolo" and m["tavolo"]["posti"][0])["tavolo"]
            assert t["posti"][0]["nome"] == "Paolo" and t["posti"][0]["ele"] == 1550
            assert t["posti"][0]["provvisorio"] is True
            assert t["valutata"] == {"si": False, "motivo": "Servono 4 giocatori con account"}


def test_websocket_sessione_non_valida_resta_ospite(tmp_path):
    with nuovo_client(tmp_path) as c:
        with c.websocket_connect("/ws?token=browser1&nome=Gigi&auth=1") as ws:
            ws.send_json({"type": "sessione", "sessione": "inventata"})
            assert ws.receive_json()["type"] == "sessione_non_valida"
            b = ricevi_fino(ws, lambda m: m["type"] == "benvenuto")
            assert b["account"] is None and b["token"] == "browser1" and b["nome"] == "Gigi"


def test_stesso_account_su_due_dispositivi(tmp_path):
    with nuovo_client(tmp_path) as c:
        s1 = registra(c).json()["sessione"]
        s2 = c.post("/api/accedi", json={"nome": "Paolo", "password": PW}).json()["sessione"]
        with c.websocket_connect("/ws?token=pc&auth=1") as pc, c.websocket_connect("/ws?token=tel&auth=1") as tel:
            pc.send_json({"type": "sessione", "sessione": s1})
            tel.send_json({"type": "sessione", "sessione": s2})
            ricevi_fino(pc, lambda m: m["type"] == "benvenuto")
            ricevi_fino(tel, lambda m: m["type"] == "benvenuto")
            pc.send_json({"type": "crea_tavolo", "variante": "Vanilla"})
            tid = ricevi_fino(pc, lambda m: m["type"] == "tavolo")["tavolo"]["id"]
            pc.send_json({"type": "siedi", "tavolo": tid, "posto": 0})
            # il telefono vede il posto come suo
            t = ricevi_fino(tel, lambda m: m["type"] == "lobby" and m["tavoli"] and m["tavoli"][0]["miei"])
            assert t["tavoli"][0]["miei"] == [0]


def test_ospite_non_puo_usare_il_nome_di_un_account(tmp_path):
    with nuovo_client(tmp_path) as c:
        registra(c)
        with c.websocket_connect("/ws?token=ospite1&nome=paolo") as ws:
            b = ricevi_fino(ws, lambda m: m["type"] == "benvenuto")
            assert b["nome"] == "paolo (ospite)"
            ws.send_json({"type": "nome", "nome": "Paolo"})
            assert "account" in ricevi_fino(ws, lambda m: m["type"] == "errore")["messaggio"]
            ws.send_json({"type": "crea_tavolo", "variante": "Vanilla"})
            tid = ricevi_fino(ws, lambda m: m["type"] == "tavolo")["tavolo"]["id"]
            ws.send_json({"type": "siedi", "tavolo": tid, "posto": 1, "nome": "PAOLO"})
            assert "account" in ricevi_fino(ws, lambda m: m["type"] == "errore")["messaggio"]


def test_token_di_sessione_mai_agli_altri_client(tmp_path):
    with nuovo_client(tmp_path) as c:
        s = registra(c).json()["sessione"]
        with c.websocket_connect("/ws?token=altro&nome=Gigi") as altro, \
                c.websocket_connect("/ws?token=pc&auth=1") as ws:
            ws.send_json({"type": "sessione", "sessione": s})
            ricevi_fino(ws, lambda m: m["type"] == "benvenuto")
            ws.send_json({"type": "crea_tavolo", "variante": "Vanilla"})
            tid = ricevi_fino(ws, lambda m: m["type"] == "tavolo")["tavolo"]["id"]
            ws.send_json({"type": "siedi", "tavolo": tid, "posto": 0})
            for p in (1, 2, 3):
                ws.send_json({"type": "bot", "tavolo": tid, "posto": p})
            ws.send_json({"type": "avvia", "tavolo": tid})
            ricevi_fino(ws, lambda m: m["type"] == "stato")       # partita avviata, poi si guarda
            altro.send_json({"type": "guarda", "tavolo": tid})
            visti = []
            for _ in range(200):
                msg = altro.receive_json()
                visti.append(json.dumps(msg))
                if msg["type"] == "stato":
                    break
            testo = "".join(visti)
            assert '"type": "stato"' in testo
            assert s not in testo and "acc:" not in testo and "browser" not in testo


# --------------------------------------------------------------------------- amministrazione

def test_admin_password_elenco_revoca(tmp_path):
    db = str(tmp_path / "s.db")
    with nuovo_client(tmp_path) as c:
        s = registra(c).json()["sessione"]
        out = io.StringIO()
        risposte = iter(["nuova-password-1", "nuova-password-1"])
        assert admin.main(["--db", db, "password", "paolo"], leggi_password=lambda _: next(risposte), out=out) == 0
        assert c.get("/api/io", headers={"Authorization": f"Bearer {s}"}).status_code == 401
        assert c.post("/api/accedi", json={"nome": "Paolo", "password": PW}).status_code == 401
        assert c.post("/api/accedi", json={"nome": "Paolo", "password": "nuova-password-1"}).status_code == 200
        out = io.StringIO()
        assert admin.main(["--db", db, "elenco"], out=out) == 0
        assert "Paolo" in out.getvalue() and "1550?" in out.getvalue() and "nuova-password" not in out.getvalue()
        out = io.StringIO()
        assert admin.main(["--db", db, "revoca", "Paolo"], out=out) == 0
        assert "Sessioni chiuse: 1" in out.getvalue()
        risposte = iter(["aaaaaaaaa", "bbbbbbbbb"])
        out = io.StringIO()
        assert admin.main(["--db", db, "password", "Paolo"], leggi_password=lambda _: next(risposte), out=out) == 1
        assert admin.main(["--db", db, "password", "Nessuno"], out=io.StringIO()) == 1
