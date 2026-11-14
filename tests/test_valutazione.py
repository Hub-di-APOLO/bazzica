"""Partite valutate eLE: quando lo sono, calcolo a fine partita, abbandoni, ricalcolo, migrazione."""
import asyncio
import json
import sqlite3

import pytest

from bazzica.bots import HeuristicAgent
from bazzica.engine import (legal_actions, apply_inplace, observation, required_actors, optional_actors,
                            system_action, FASE_SCAMBIO, compagno)
from bazzica.server import ele as E
from bazzica.server.account import identita
from bazzica.server.config import Config
from bazzica.server.storico import Storico
from bazzica.server.tables import Manager, Tavolo

NOMI = ["Anna", "Bruno", "Carla", "Dario"]


@pytest.fixture
def m(tmp_path):
    return Manager(cartella_log=str(tmp_path / "logs"), db_path=str(tmp_path / "s.db"), ritardo_bot=(0, 0),
                   pausa_fine_mano=0, config=Config())


def tavolo(m, posti, variante="Vanilla", margherita=True):
    """``posti``: per posto "acc:<nome>" (account), "ospite:<nome>" o "bot"."""
    t = Tavolo(m, "t1", "Prova", "proprietario", variante, margherita)
    m.tavoli["t1"] = t
    for s, p in enumerate(posti):
        if p == "bot":
            t.bot(s, True)
            continue
        tipo, nome = p.split(":")
        if tipo == "acc":
            a = m.account.per_nome(nome) or m.account.registra(nome, "password-lunga")
            token = identita(a["id"])
            m.nomi[token] = a["nome"]
        else:
            token = f"ospite{nome}"
            m.nomi[token] = nome
        t.siedi(token, s, nome)
    return t


def tutti_account(m, **kw):
    return tavolo(m, [f"acc:{n}" for n in NOMI], **kw)


async def gioca(t, prima_di_ogni_azione=None, seed=0):
    """Gioca la partita fino alla fine con agenti euristici al posto di tutti (come farebbero gli umani)."""
    agenti = {s: HeuristicAgent(seed=seed + s) for s in range(4)}
    eventi = []
    invia = t.invia_eventi

    async def intercetta(evs):          # gli eventi come li ricevono i client (compreso "ele")
        eventi.extend(evs)
        await invia(evs)
    t.invia_eventi = intercetta
    registra = t.gestisci_eventi
    n = 0
    while t.stato == "in_corso":
        n += 1
        assert n < 20000
        if prima_di_ogni_azione and await prima_di_ogni_azione(t, n):
            continue
        st = t.st
        sa = system_action(st)
        if sa:
            t.ack = set()
            await registra(apply_inplace(st, sa))
            continue
        for s in optional_actors(st) + required_actors(st):
            if st.fase == FASE_SCAMBIO and st.scambio_attesa[s] and st.scambio_passata[compagno(s)] is None:
                continue
            legal = legal_actions(st, s)
            if legal:
                await registra(apply_inplace(st, agenti[s].choose_action(observation(st, s), legal)))
                break
    return eventi


def avvia(t):
    return asyncio.run(_avvia(t))


async def _avvia(t):
    await t.gestisci_eventi(t.avvia())


def partita(t, **kw):
    async def corpo():
        await _avvia(t)
        return await gioca(t, **kw)
    return asyncio.run(corpo())


def evento_ele(eventi):
    return next((e for e in eventi if e["tipo"] == "ele"), None)


def righe(m, sql, *args):
    with sqlite3.connect(m.storico.path) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute(sql, args).fetchall()]


# --------------------------------------------------------------------------- valutata o no

def test_quattro_account_partita_valutata(m):
    t = tutti_account(m)
    assert t.info()["valutata"] == {"si": True, "motivo": ""}
    ant = t.info()["anteprima_ele"]
    assert ant == {"ele_squadre": [1550, 1550], "probabilita": 0.5}
    eventi = partita(t)
    ev = evento_ele(eventi)
    assert ev is not None and ev["visibile"] is None and len(ev["variazioni"]) == 4
    # l'evento eLE arriva subito dopo la fine della partita
    tipi = [e["tipo"] for e in eventi]
    assert tipi.index("ele") == tipi.index("fine_partita") + 1
    fine = next(e for e in eventi if e["tipo"] == "fine_partita")
    for v in ev["variazioni"]:
        vinto = fine["vincitore"] == v["posto"] % 2
        assert (v["delta"] > 0) == vinto if fine["vincitore"] != "pari" else True
        assert v["nome"] == NOMI[v["posto"]] and v["provvisorio"]
    db = righe(m, "SELECT * FROM ele_partite ORDER BY posto")
    assert [r["posto"] for r in db] == [0, 1, 2, 3]
    assert righe(m, "SELECT valutata FROM partite")[0]["valutata"] == 1
    assert all(r["partite"] == 1 for r in righe(m, "SELECT * FROM ele"))
    # l'eLE mostrato ai tavoli è già quello nuovo
    assert t.info()["posti"][0]["ele"] == round(db[0]["ele_dopo"])
    # statistiche grezze salvate per il ricalcolo
    val = righe(m, "SELECT * FROM valutazioni")
    posti = json.loads(val[0]["posti"])
    assert len(posti) == 4 and set(posti[0]["stat"]) >= {"scope", "piccole", "bazziche", "napoleoni"}


@pytest.mark.parametrize("posti,motivo", [
    (["acc:Anna", "bot", "acc:Carla", "acc:Dario"], "C'è un bot (Est)"),
    (["acc:Anna", "ospite:Bea", "acc:Carla", "acc:Dario"], "Bea gioca come ospite"),
])
def test_partite_non_valutate(m, posti, motivo):
    t = tavolo(m, posti)
    assert t.info()["valutata"] == {"si": False, "motivo": motivo}
    assert t.info()["anteprima_ele"] is None
    eventi = partita(t)
    assert evento_ele(eventi) is None
    assert righe(m, "SELECT * FROM ele_partite") == []
    assert righe(m, "SELECT valutata FROM partite")[0]["valutata"] == 0


def test_posto_libero_non_valutata(m):
    t = tavolo(m, ["acc:Anna", "acc:Bruno", "acc:Carla", "bot"])
    t.bot(3, False)
    assert t.info()["valutata"] == {"si": False, "motivo": "Servono 4 giocatori con account"}


def test_hot_seat_non_valutata(m):
    t = tavolo(m, ["acc:Anna", "acc:Bruno", "acc:Carla", "bot"])
    t.bot(3, False)
    token_anna = t.posti[0]["token"]
    t.siedi(token_anna, 3, "Zio")            # un secondo posto dallo stesso giocatore (stesso PC)
    assert t.posti[3]["nome"] == "Zio" and not t.posti[3].get("account_id")
    assert t.info()["valutata"]["si"] is False


def test_partita_interrotta_non_valutata(m):
    t = tutti_account(m)

    async def termina_presto(tav, n):
        if n == 30:
            tav.termina(da="Anna")
        return False
    eventi = partita(t, prima_di_ogni_azione=termina_presto)
    assert evento_ele(eventi) is None
    assert righe(m, "SELECT * FROM valutazioni") == []
    assert all(r["partite"] == 0 for r in righe(m, "SELECT * FROM ele"))


def test_abbandono_sconfitta_piena_e_k_dimezzato(m):
    t = tutti_account(m)
    token_bruno = t.posti[1]["token"]

    async def esce(tav, n):
        if n == 20:
            tav.sostituisci(token_bruno, "uscito")
            return True
        return False
    eventi = partita(t, prima_di_ogni_azione=esce)
    ev = evento_ele(eventi)
    assert ev is not None
    var = {v["posto"]: v for v in ev["variazioni"]}
    assert var[1]["nome"] == "Bruno" and var[1]["esito"] == "sconfitta" and var[1]["dettaglio"]["abbandono"]
    assert var[1]["delta"] == pytest.approx(-20)          # K 40 (provvisorio) · (0 - 0,5)
    for s in (0, 2, 3):
        assert var[s]["dettaglio"]["k"] == 20             # K dimezzato
    db = {r["posto"]: r for r in righe(m, "SELECT * FROM ele_partite")}
    assert db[1]["esito"] == "sconfitta"


def test_rientro_prima_della_fine_conta_come_mai_uscito(m):
    t = tutti_account(m)
    token_bruno = t.posti[1]["token"]

    async def esce_e_rientra(tav, n):
        if n == 20:
            tav.sostituisci(token_bruno, "uscito")
            return True
        if n == 40:
            await tav.riprendi(token_bruno)
            return True
        return False
    eventi = partita(t, prima_di_ogni_azione=esce_e_rientra)
    ev = evento_ele(eventi)
    assert all(not v["dettaglio"]["abbandono"] and v["dettaglio"]["k"] == 40 for v in ev["variazioni"])


def test_partita_senza_umani_rimasti_interrotta(m):
    t = tutti_account(m)

    async def escono_tutti(tav, n):
        if n == 10:
            for p in list(tav.posti):
                if p.get("token"):
                    await tav.applica_sostituzione(p["token"], "uscito")
            return True
        return False
    eventi = partita(t, prima_di_ogni_azione=escono_tutti)
    assert evento_ele(eventi) is None
    assert righe(m, "SELECT esito FROM partite")[0]["esito"] == "interrotta"


# --------------------------------------------------------------------------- ricalcolo e migrazione

def test_ricalcolo_dallo_storico(m, monkeypatch):
    for seed in range(3):
        t = tutti_account(m)
        partita(t, seed=seed)
        del m.tavoli["t1"]
    prima = {r["account_id"]: r for r in righe(m, "SELECT * FROM ele")}
    assert all(r["partite"] == 3 for r in prima.values())
    # stesso risultato rifacendo tutto da zero
    assert m.storico.ricalcola() == 3
    dopo = {r["account_id"]: r for r in righe(m, "SELECT * FROM ele")}
    for a in prima:
        assert dopo[a]["ele"] == pytest.approx(prima[a]["ele"])
        assert dopo[a]["partite"] == 3
        assert (dopo[a]["vittorie"], dopo[a]["sconfitte"], dopo[a]["pareggi"]) == \
            (prima[a]["vittorie"], prima[a]["sconfitte"], prima[a]["pareggi"])
    # con parametri diversi la classifica cambia
    monkeypatch.setattr(E, "K_PROVVISORIO", 80.0)
    m.storico.ricalcola()
    cambiati = {r["account_id"]: r["ele"] for r in righe(m, "SELECT * FROM ele")}
    assert any(abs(cambiati[a] - prima[a]["ele"]) > 0.01 for a in prima)
    cl = m.storico.classifica()
    assert len(cl["giocatori"]) == 4 and len(cl["giocatori"][0]["andamento"]) == 3


def test_migrazione_database_vecchio(tmp_path):
    path = tmp_path / "vecchio.db"
    with sqlite3.connect(path) as c:
        c.executescript("""
            CREATE TABLE partite (id INTEGER PRIMARY KEY AUTOINCREMENT, inizio TEXT NOT NULL, fine TEXT, tavolo TEXT,
                variante TEXT, margherita INTEGER, giocatori TEXT, punti_ns INTEGER DEFAULT 0,
                punti_eo INTEGER DEFAULT 0, esito TEXT, log TEXT);
            CREATE TABLE mani (id INTEGER PRIMARY KEY AUTOINCREMENT, partita_id INTEGER NOT NULL, numero INTEGER,
                mazziere INTEGER, punti_ns INTEGER, punti_eo INTEGER, totale_ns INTEGER, totale_eo INTEGER,
                riepilogo TEXT);
            INSERT INTO partite (inizio, fine, tavolo, variante, margherita, giocatori, punti_ns, punti_eo, esito)
                VALUES ('2026-11-01T20:00:00', '2026-11-01T21:00:00', 'Vecchio', 'Vanilla', 0, '[]', 22, 15, 'Squadra 1');
        """)
    s = Storico(str(path))
    vecchie = s.elenco()
    assert len(vecchie) == 1 and vecchie[0]["tavolo"] == "Vecchio" and vecchie[0]["valutata"] == 0
    with sqlite3.connect(path) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 3
        tabelle = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"account", "sessioni", "ele", "valutazioni", "ele_partite", "statistiche_partite"} <= tabelle
    Storico(str(path))      # una seconda apertura non rifà nulla
    assert len(Storico(str(path)).elenco()) == 1


def test_migrazione_dalla_versione_1(tmp_path):
    """Un database con l'eLE ma senza statistiche dei giocatori riceve solo la tabella nuova."""
    path = tmp_path / "v1.db"
    s = Storico(str(path))
    with sqlite3.connect(path) as c:
        c.execute("DROP TABLE statistiche_partite")
        c.execute("PRAGMA user_version = 1")
        c.execute("INSERT INTO account (nome, nome_norm, hash, sale, creato) VALUES ('Anna','anna','h','s','x')")
    Storico(str(path))
    with sqlite3.connect(path) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 3
        assert c.execute("SELECT COUNT(*) FROM statistiche_partite").fetchone()[0] == 0
        assert c.execute("SELECT nome FROM account").fetchone()[0] == "Anna"
    del s
