"""Configurazione tramite variabili d'ambiente."""
import ipaddress
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bazzica.server.app import create_app
from bazzica.server.config import Config, ROOT


def test_predefiniti_uso_in_lan():
    c = Config.da_ambiente({})
    assert c.host == "0.0.0.0" and c.porta == 8000
    assert Path(c.cartella_dati) == ROOT / "data" and Path(c.cartella_log) == ROOT / "logs"
    assert Path(c.db_path) == ROOT / "data" / "storico.db"
    assert c.codice == ""
    assert c.ritardo_bot == (0.8, 1.5)
    assert c.proxy_fidati == ()
    assert c == Config()


def test_lettura_variabili():
    env = {
        "BAZZICA_HOST": "127.0.0.1", "BAZZICA_PORTA": "9001", "BAZZICA_DATI": "/dati", "BAZZICA_LOG": "/log",
        "BAZZICA_CODICE": "  segreto ", "BAZZICA_RITARDO_BOT": "0.1-0.2", "BAZZICA_MAX_TAVOLI": "5",
        "BAZZICA_MAX_TAVOLI_TOKEN": "2", "BAZZICA_MAX_CONN_IP": "0", "BAZZICA_MAX_MESSAGGIO": "1000",
        "BAZZICA_MAX_MSG_SECONDO": "2.5", "BAZZICA_RAFFICA_MSG": "7",
        "BAZZICA_PROXY_FIDATI": "172.16.0.0/12, 10.0.0.1", "BAZZICA_TAVOLO_INATTIVO_MIN": "30",
        "BAZZICA_PAUSA_MAX_ORE": "0",
    }
    c = Config.da_ambiente(env)
    assert (c.host, c.porta, c.cartella_dati, c.cartella_log) == ("127.0.0.1", 9001, "/dati", "/log")
    assert c.codice == "segreto"
    assert c.ritardo_bot == (0.1, 0.2)
    assert (c.max_tavoli, c.max_tavoli_token, c.max_conn_ip, c.max_messaggio) == (5, 2, 0, 1000)
    assert (c.max_msg_secondo, c.raffica_msg) == (2.5, 7)
    assert c.proxy_fidati == (ipaddress.ip_network("172.16.0.0/12"), ipaddress.ip_network("10.0.0.1/32"))
    assert (c.tavolo_inattivo_min, c.pausa_max_ore) == (30, 0)
    assert c.db_path.replace("\\", "/") == "/dati/storico.db"


@pytest.mark.parametrize("nome,valore", [("BAZZICA_PORTA", "abc"), ("BAZZICA_PORTA", "0"),
                                         ("BAZZICA_MAX_TAVOLI", "-1"), ("BAZZICA_PROXY_FIDATI", "boh")])
def test_valori_non_validi(nome, valore):
    with pytest.raises(ValueError):
        Config.da_ambiente({nome: valore})


def test_variabili_vuote_usano_il_predefinito():
    c = Config.da_ambiente({"BAZZICA_PORTA": "", "BAZZICA_DATI": "", "BAZZICA_RITARDO_BOT": "x"})
    assert c.porta == 8000 and Path(c.cartella_dati) == ROOT / "data" and c.ritardo_bot == (0.8, 1.5)


def test_create_app_usa_le_cartelle_configurate(tmp_path):
    cfg = Config(cartella_dati=str(tmp_path / "d"), cartella_log=str(tmp_path / "l"))
    app = create_app(config=cfg)
    with TestClient(app) as c:
        assert c.get("/api/storico").status_code == 200
    assert (tmp_path / "d" / "storico.db").exists() and (tmp_path / "l").is_dir()
    assert app.state.manager.cartella_log == str(tmp_path / "l")


def test_inattivita_da_ambiente():
    from bazzica.server.config import Config
    assert Config.da_ambiente({}).inattivita_min == 5
    assert Config.da_ambiente({"BAZZICA_INATTIVITA_MIN": "0"}).inattivita_min == 0
    assert Config.da_ambiente({"BAZZICA_INATTIVITA_MIN": "2.5"}).inattivita_min == 2.5
