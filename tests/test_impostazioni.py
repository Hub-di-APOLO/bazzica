"""Impostazioni dell'account (note scritte durante la partita): API, validazione, migrazione del database."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from bazzica.server import app as app_mod
from bazzica.server.account import impostazioni_di, controlla_impostazioni, ErroreAccount
from bazzica.server.app import create_app
from bazzica.server.config import Config
from bazzica.server.storico import Storico
from bazzica.server.tables import Manager

PW = "password-lunga"


@pytest.fixture(autouse=True)
def niente_attese(monkeypatch):
    monkeypatch.setattr(app_mod, "ATTESA_LOGIN_ERRATO", 0)


def nuovo_client(tmp_path):
    m = Manager(cartella_log=str(tmp_path / "logs"), db_path=str(tmp_path / "s.db"), ritardo_bot=(0, 0),
                pausa_fine_mano=0, config=Config(max_msg_secondo=0))
    return TestClient(create_app(m))


def test_impostazioni_predefinite_e_salvate(tmp_path):
    with nuovo_client(tmp_path) as c:
        r = c.post("/api/registrati", json={"nome": "Paolo", "password": PW}).json()
        assert r["account"]["impostazioni"] == {"note": True}          # predefinito: note attive
        h = {"Authorization": f"Bearer {r['sessione']}"}
        assert c.post("/api/impostazioni", json={"note": False}, headers=h).json() == {"impostazioni": {"note": False}}
        # vale su ogni dispositivo: la rileggono /api/io e un nuovo accesso
        assert c.get("/api/io", headers=h).json()["account"]["impostazioni"] == {"note": False}
        r2 = c.post("/api/accedi", json={"nome": "Paolo", "password": PW}).json()
        assert r2["account"]["impostazioni"] == {"note": False}
        # la risposta non contiene mai la password o l'hash
        assert "hash" not in str(r2) and PW not in str(r2)


@pytest.mark.parametrize("corpo", [{}, {"note": "no"}, {"note": 0}, {"note": None}, {"sconosciuta": True},
                                   {"note": True, "altro": 1}, [], "note"])
def test_impostazioni_validate(tmp_path, corpo):
    with nuovo_client(tmp_path) as c:
        s = c.post("/api/registrati", json={"nome": "Paolo", "password": PW}).json()["sessione"]
        r = c.post("/api/impostazioni", json=corpo, headers={"Authorization": f"Bearer {s}"})
        assert r.status_code == 400
        assert c.get("/api/io", headers={"Authorization": f"Bearer {s}"}).json()["account"]["impostazioni"] == {"note": True}


def test_impostazioni_senza_sessione(tmp_path):
    with nuovo_client(tmp_path) as c:
        assert c.post("/api/impostazioni", json={"note": False}).status_code == 401
        assert c.post("/api/impostazioni", json={"note": False},
                      headers={"Authorization": "Bearer inventato"}).status_code == 401


def test_impostazioni_di_tollera_dati_rovinati():
    assert impostazioni_di({}) == {"note": True}
    assert impostazioni_di({"impostazioni": "non json"}) == {"note": True}
    assert impostazioni_di({"impostazioni": '{"note": "x", "vecchia": 1}'}) == {"note": True}
    assert impostazioni_di({"impostazioni": '{"note": false}'}) == {"note": False}
    with pytest.raises(ErroreAccount):
        controlla_impostazioni({"note": 1})


def test_migrazione_dalla_versione_2(tmp_path):
    """Un database della versione 2 (senza impostazioni) riceve la colonna e tiene gli account."""
    path = tmp_path / "v2.db"
    Storico(str(path))
    with sqlite3.connect(path) as c:
        c.executescript("""
            CREATE TABLE account_vecchio AS SELECT id, nome, nome_norm, hash, sale, avatar, creato, ultimo_accesso
                FROM account;
            DROP TABLE account;
            ALTER TABLE account_vecchio RENAME TO account;
            PRAGMA user_version = 2;
            INSERT INTO account (nome, nome_norm, hash, sale, creato) VALUES ('Anna', 'anna', 'h', 's', 'x');
        """)
    Storico(str(path))
    with sqlite3.connect(path) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 3
        assert c.execute("SELECT nome, impostazioni FROM account").fetchone() == ("Anna", None)
    Storico(str(path))      # una seconda apertura non rifà nulla
