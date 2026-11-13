"""Scheda del giocatore: raccolta delle statistiche, salvataggio a fine partita, API e calcoli."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from bazzica.engine import preset
from bazzica.server import ele as E
from bazzica.server.app import create_app
from bazzica.server.config import Config
from bazzica.server.storico import Storico, MIN_PARTITE_CONFRONTO
from bazzica.server.tables import Manager
from test_valutazione import tavolo, tutti_account, partita, NOMI  # noqa: F401 (riuso degli aiuti)


@pytest.fixture
def m(tmp_path):
    return Manager(cartella_log=str(tmp_path / "logs"), db_path=str(tmp_path / "s.db"), ritardo_bot=(0, 0),
                   pausa_fine_mano=0, config=Config())


def righe(m):
    with sqlite3.connect(m.storico.path) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute("SELECT * FROM statistiche_partite ORDER BY posto")]


# --------------------------------------------------------------------------- raccolta dagli eventi

def test_contatori_della_scheda():
    r = E.Raccoglitore(preset("Avogadro"))
    r.evento({"tipo": "carte_ricevute", "seat": 0, "carte": ["coppe_02", "spade_03", "bastoni_10"]})
    r.evento({"tipo": "scambio", "seat": 2, "a": 0, "veloce": True})
    r.evento({"tipo": "scambio_ricevuta", "seat": 0, "da": 2, "carta": "coppe_04"})
    r.evento({"tipo": "che_palo", "seat": 1})
    # Bazzica da 2 resa possibile dalla carta del compagno: Sud l'ha "fatta fare"
    r.evento({"tipo": "bazzica", "seat": 0, "scope": 2, "girate": 0, "squadra": 0})
    # Scopa con la carta ricevuta: assist per Sud; prende anche il 7 bello e un asso
    r.evento({"tipo": "giocata", "seat": 0, "squadra": 0, "carta": "coppe_04", "presa": ["denari_07", "spade_01"],
              "scopa": True, "assi": ["spade_01"], "girate": []})
    # presa normale con il 2 di denari
    r.evento({"tipo": "giocata", "seat": 1, "squadra": 1, "carta": "bastoni_02", "presa": ["denari_02"],
              "girate": []})
    r.evento({"tipo": "fine_mano", "riepilogo": {"squadre": [{"napola_nome": "Napola al 4"},
                                                             {"napola_nome": None}]}})
    nord, est, sud = r.posti[0], r.posti[1], r.posti[2]
    assert nord["bazziche_per_tipo"] == {"2": 1} and sud["bazziche_fatte_fare"] == 1
    assert (nord["n_scope"], nord["con_carta_compagno"], sud["assist"]) == (1, 1, 1)
    assert (nord["n_prese"], nord["n_carte_prese"], nord["n_sette_bello"], nord["n_assi_presi"]) == (1, 3, 1, 1)
    assert (est["n_due_denari"], est["che_palo"], sud["passaggi_veloci"]) == (1, 1, 1)
    assert (nord["napole"], sud["napole"], est["napole"]) == (1, 1, 0)
    # i campi dell'eLE non cambiano: la Scopa con la carta del compagno resta divisa a metà
    assert (nord["scope"], sud["scope"]) == (0.5, 0.5)


# --------------------------------------------------------------------------- salvataggio a fine partita

def test_statistiche_salvate_anche_senza_valutazione(m):
    t = tavolo(m, ["acc:Anna", "bot", "ospite:Bea", "bot"])
    assert not t.info()["valutata"]["si"]
    partita(t)
    r = righe(m)
    assert len(r) == 1                         # solo l'account: niente bot né ospiti
    assert r[0]["posto"] == 0 and r[0]["valutata"] == 0 and r[0]["compagno_id"] is None
    assert r[0]["esito"] in ("vittoria", "sconfitta", "pareggio") and r[0]["variante"] == "Vanilla"


def test_statistiche_partita_valutata_con_compagni_e_avversari(m):
    t = tutti_account(m)
    partita(t)
    r = righe(m)
    ids = {n: m.account.per_nome(n)["id"] for n in NOMI}
    assert [x["account_id"] for x in r] == [ids[n] for n in NOMI]
    anna = r[0]
    assert anna["valutata"] == 1 and anna["compagno_id"] == ids["Carla"]
    assert sorted(__import__("json").loads(anna["avversari"])) == sorted([ids["Bruno"], ids["Dario"]])
    assert r[0]["esito"] == r[2]["esito"] and r[0]["punti_squadra"] == r[1]["punti_avversari"]


def test_partita_interrotta_senza_statistiche(m):
    t = tutti_account(m)

    async def termina(tav, n):
        if n == 15:
            tav.termina(da="Anna")
        return False
    partita(t, prima_di_ogni_azione=termina)
    assert righe(m) == []


def test_abbandono_conta_come_sconfitta(m):
    t = tavolo(m, ["acc:Anna", "bot", "acc:Carla", "bot"])
    token = t.posti[0]["token"]

    async def esce(tav, n):
        if n == 10:
            tav.sostituisci(token, "uscito")
            return True
        return False
    partita(t, prima_di_ogni_azione=esce)
    anna = next(x for x in righe(m) if x["posto"] == 0)
    assert anna["abbandono"] == 1 and anna["esito"] == "sconfitta"


# --------------------------------------------------------------------------- scheda e API

def riga(aid, esito, compagno=None, avversari=(), valutata=0, **stat):
    base = E.statistiche_vuote()
    base.update(stat)
    return {"account_id": aid, "posto": 0, "esito": esito, "abbandono": False, "punti_squadra": 30,
            "punti_avversari": 20, "punti_individuali": 4, "compagno_id": compagno, "avversari": list(avversari),
            "stat": base}


def test_scheda_carriera_spettacolo_rivali(tmp_path):
    s = Storico(str(tmp_path / "s.db"))
    with s._conn() as c:
        for i, n in enumerate(["Anna", "Bruno", "Carla", "Dario"], 1):
            c.execute("INSERT INTO account (id, nome, nome_norm, hash, sale, creato) VALUES (?,?,?,?,?,?)",
                      (i, n, n.lower(), "h", "s", "x"))
            c.execute("INSERT INTO ele (account_id, ele) VALUES (?, 1550)", (i,))
    esiti = ["vittoria", "vittoria", "vittoria", "sconfitta", "vittoria", "pareggio"]
    for pid, esito in enumerate(esiti, 1):
        with s._conn() as c:
            c.execute("INSERT INTO partite (id, inizio, variante, margherita, valutata) VALUES (?,?,?,?,?)",
                      (pid, "x", "Curie" if pid % 2 else "Vanilla", 0, int(pid <= 3)))
        # Bruno è sempre avversario (Anna ci vince 4 volte su 6); Dario solo 3 volte, tutte sconfitte di Anna
        avv = [2, 4] if pid >= 4 else [2]
        e = esito if pid < 4 else "sconfitta"
        s.registra_statistiche(pid, [riga(1, e, compagno=3, avversari=avv, n_scope=2, n_piccole=1,
                                          bazziche_per_tipo={"3": 1}, bazziche=[{"scope": 3, "riscosse": 3}],
                                          n_assi_presi=1, n_due_denari=1, che_palo=1)])
    d = s.scheda("anna")
    car = d["carriera"]
    assert (car["partite"], car["vittorie"], car["sconfitte"], car["serie_vittorie"]) == (6, 3, 3, 3)
    assert car["percentuale_vittorie"] == 50 and car["valutate"] == 3
    assert d["spettacolo"]["scope"] == 12 and d["spettacolo"]["bazziche_per_tipo"]["3"] == 6
    assert d["spettacolo"]["bazziche_riscosse_intere"] == 6 and d["carte"]["due_denari"] == 6
    assert d["carte"]["media_punti_individuali"] == 4
    cr = d["compagni_rivali"]
    assert cr["compagno_preferito"]["nome"] == "Carla" and cr["compagno_preferito"]["partite"] == 6
    assert cr["bestia_nera"]["nome"] == "Dario" and cr["bestia_nera"]["percentuale_vittorie"] == 0
    assert cr["vittima_preferita"] is None          # contro Bruno è 50%: né vittima né bestia nera
    assert MIN_PARTITE_CONFRONTO == 3
    # solo le valutate
    v = s.scheda("anna", solo_valutate=True)
    assert v["carriera"]["partite"] == 3 and v["carriera"]["vittorie"] == 3
    assert v["compagni_rivali"]["bestia_nera"] is None
    assert s.scheda("nessuno") is None


def test_api_giocatore(tmp_path):
    m = Manager(cartella_log=str(tmp_path / "logs"), db_path=str(tmp_path / "s.db"), ritardo_bot=(0, 0),
                pausa_fine_mano=0, config=Config(max_msg_secondo=0, codice="segreto"))
    with TestClient(create_app(m)) as c:
        m.account.registra("Gian Luca", "password-lunga")
        h = {"X-Bazzica-Codice": "segreto"}
        assert c.get("/api/giocatore/gianluca").status_code == 401
        d = c.get("/api/giocatore/gianluca", headers=h).json()
        assert d["nome"] == "Gian Luca" and d["carriera"]["partite"] == 0 and d["ele"] == 1550
        assert "hash" not in str(d) and "sale" not in str(d)
        assert c.get("/api/giocatore/gianluca?valutate=1", headers=h).json()["solo_valutate"] is True
        assert c.get("/api/giocatore/nessuno", headers=h).status_code == 404
