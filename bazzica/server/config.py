"""Configurazione del server tramite variabili d'ambiente.

Tutti i valori hanno un predefinito che lascia invariato l'uso in LAN (python run.py):
basta non impostare nulla. Sul NAS (Docker) si impostano nel file YAML.

Variabili (tutte facoltative):
  BAZZICA_HOST                 indirizzo di ascolto                         (0.0.0.0)
  BAZZICA_PORTA                porta TCP                                    (8000)
  BAZZICA_DATI                 cartella dello storico SQLite                (<progetto>/data)
  BAZZICA_LOG                  cartella dei log delle partite               (<progetto>/logs)
  BAZZICA_CODICE               codice d'accesso; vuoto = nessun codice      ("")
  BAZZICA_RITARDO_BOT          pausa dei bot in secondi "min-max"           (0.8-1.5)
  BAZZICA_MAX_TAVOLI           tavoli in totale; 0 = nessun limite          (100)
  BAZZICA_MAX_TAVOLI_TOKEN     tavoli creati da uno stesso browser          (10)
  BAZZICA_MAX_CONN_IP          WebSocket aperte da uno stesso IP            (30)
  BAZZICA_MAX_MESSAGGIO        dimensione massima di un messaggio (byte)    (16384)
  BAZZICA_MAX_MSG_SECONDO      messaggi al secondo per connessione (media)  (20)
  BAZZICA_RAFFICA_MSG          messaggi consentiti di fila prima del limite (60)
  BAZZICA_PROXY_FIDATI         IP o reti (CIDR) dei reverse proxy fidati,
                               separati da virgola; solo da questi si legge
                               X-Forwarded-For                              ("")
  BAZZICA_TAVOLO_INATTIVO_MIN  minuti dopo cui un tavolo non avviato e
                               inattivo viene eliminato; 0 = mai            (180)
  BAZZICA_PAUSA_MAX_ORE        ore dopo cui una partita in pausa senza
                               umani connessi viene terminata; 0 = mai      (12)
  BAZZICA_INATTIVITA_MIN       minuti dopo cui un giocatore inattivo (tocca
                               a lui e non gioca) o disconnesso viene
                               sostituito da un bot; 0 = mai                (5)
  BAZZICA_SESSIONE_GIORNI      giorni dopo l'ultimo uso in cui scade una
                               sessione (login) di un account               (90)
  BAZZICA_LOGIN_MAX_FALLITI    login falliti (per IP e per nome utente)
                               dopo cui si blocca; 0 = nessun blocco        (5)
  BAZZICA_LOGIN_FINESTRA_MIN   minuti in cui si contano i login falliti     (15)
  BAZZICA_LOGIN_BLOCCO_MIN     minuti di blocco dopo troppi login falliti   (15)
  BAZZICA_REGISTRAZIONI_ORA    nuovi account all'ora da uno stesso IP       (5)
Per i limiti numerici 0 significa "nessun limite".
"""
from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _str(env, nome, predefinito=""):
    v = env.get(nome)
    return predefinito if v is None else v.strip()


def _num(env, nome, predefinito, tipo=int, minimo=0):
    v = env.get(nome)
    if v is None or not v.strip():
        return predefinito
    try:
        x = tipo(v.strip())
    except ValueError:
        raise ValueError(f"Valore non valido per {nome}: {v!r}") from None
    if x < minimo:
        raise ValueError(f"{nome} deve essere almeno {minimo}")
    return x


def _ritardo(env):
    v = _str(env, "BAZZICA_RITARDO_BOT", "0.8-1.5")
    try:
        lo, hi = (float(x) for x in v.split("-"))
        return (lo, hi) if 0 <= lo <= hi else (0.8, 1.5)
    except ValueError:
        return 0.8, 1.5


def _reti(testo: str):
    reti = []
    for parte in testo.replace(";", ",").split(","):
        parte = parte.strip()
        if parte:
            try:
                reti.append(ipaddress.ip_network(parte, strict=False))
            except ValueError:
                raise ValueError(f"BAZZICA_PROXY_FIDATI: indirizzo non valido {parte!r}") from None
    return tuple(reti)


@dataclass(frozen=True)
class Config:
    host: str = "0.0.0.0"
    porta: int = 8000
    cartella_dati: str = str(ROOT / "data")
    cartella_log: str = str(ROOT / "logs")
    codice: str = ""
    ritardo_bot: tuple = (0.8, 1.5)
    max_tavoli: int = 100
    max_tavoli_token: int = 10
    max_conn_ip: int = 30
    max_messaggio: int = 16384
    max_msg_secondo: float = 20.0
    raffica_msg: int = 60
    proxy_fidati: tuple = field(default_factory=tuple)
    tavolo_inattivo_min: float = 180.0
    pausa_max_ore: float = 12.0
    inattivita_min: float = 5.0
    sessione_giorni: float = 90.0
    login_max_falliti: int = 5
    login_finestra_min: float = 15.0
    login_blocco_min: float = 15.0
    registrazioni_ora: int = 5

    @classmethod
    def da_ambiente(cls, env=None) -> "Config":
        env = os.environ if env is None else env
        return cls(
            host=_str(env, "BAZZICA_HOST", "0.0.0.0") or "0.0.0.0",
            porta=_num(env, "BAZZICA_PORTA", 8000, minimo=1),
            cartella_dati=_str(env, "BAZZICA_DATI") or str(ROOT / "data"),
            cartella_log=_str(env, "BAZZICA_LOG") or str(ROOT / "logs"),
            codice=_str(env, "BAZZICA_CODICE"),
            ritardo_bot=_ritardo(env),
            max_tavoli=_num(env, "BAZZICA_MAX_TAVOLI", 100),
            max_tavoli_token=_num(env, "BAZZICA_MAX_TAVOLI_TOKEN", 10),
            max_conn_ip=_num(env, "BAZZICA_MAX_CONN_IP", 30),
            max_messaggio=_num(env, "BAZZICA_MAX_MESSAGGIO", 16384),
            max_msg_secondo=_num(env, "BAZZICA_MAX_MSG_SECONDO", 20.0, float),
            raffica_msg=_num(env, "BAZZICA_RAFFICA_MSG", 60),
            proxy_fidati=_reti(_str(env, "BAZZICA_PROXY_FIDATI")),
            tavolo_inattivo_min=_num(env, "BAZZICA_TAVOLO_INATTIVO_MIN", 180.0, float),
            pausa_max_ore=_num(env, "BAZZICA_PAUSA_MAX_ORE", 12.0, float),
            inattivita_min=_num(env, "BAZZICA_INATTIVITA_MIN", 5.0, float),
            sessione_giorni=_num(env, "BAZZICA_SESSIONE_GIORNI", 90.0, float),
            login_max_falliti=_num(env, "BAZZICA_LOGIN_MAX_FALLITI", 5),
            login_finestra_min=_num(env, "BAZZICA_LOGIN_FINESTRA_MIN", 15.0, float),
            login_blocco_min=_num(env, "BAZZICA_LOGIN_BLOCCO_MIN", 15.0, float),
            registrazioni_ora=_num(env, "BAZZICA_REGISTRAZIONI_ORA", 5),
        )

    @property
    def db_path(self) -> str:
        return str(Path(self.cartella_dati) / "storico.db")
