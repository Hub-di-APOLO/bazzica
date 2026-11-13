"""Test del calcolo eLE (funzione pura) e delle statistiche individuali ricavate dagli eventi."""
import pytest

from bazzica.bots import HeuristicAgent
from bazzica.bots.runner import gioca_partita
from bazzica.engine import preset
from bazzica.server import ele as E


def stat(**kw):
    s = E.statistiche_vuote()
    s.update(kw)
    return s


def giocatori(ele=(1550, 1550, 1550, 1550), partite=(20, 20, 20, 20), stats=None, abbandoni=()):
    stats = stats or [stat() for _ in range(4)]
    return [{"ele": ele[i], "partite": partite[i], "abbandono": i in abbandoni, "stat": stats[i]} for i in range(4)]


def delta(ris):
    return [round(r["delta"], 4) for r in ris]


def test_squadre_pari_30_20_quota_di_squadra_15():
    ris = E.calcola(giocatori(), [30, 20], 0)
    assert delta(ris) == [15, -15, 15, -15]
    assert ris[0]["esito"] == "vittoria" and ris[1]["esito"] == "sconfitta"
    assert ris[0]["dettaglio"]["spettacolo"] == 1.0
    assert ris[0]["dopo"] == 1565


def test_vittoria_40_10_moltiplicatore_spettacolo_025():
    assert E.moltiplicatore_spettacolo(40, 10) == pytest.approx(0.25)
    ris = E.calcola(giocatori(), [40, 10], 0)
    # i vincitori guadagnano un quarto, i perdenti perdono la quota piena
    assert delta(ris) == [3.75, -15, 3.75, -15]
    assert "Poco" not in str(ris)  # il testo scherzoso è dell'interfaccia


@pytest.mark.parametrize("a,b,atteso", [(30, 20, 1.0), (21, 0, 0.25), (35, 15, 0.625), (25, 25, 1.0),
                                        (3, -3, 0.25), (0, 0, 1.0), (60, 40, 1.0)])
def test_moltiplicatore_spettacolo(a, b, atteso):
    assert E.moltiplicatore_spettacolo(a, b) == pytest.approx(atteso)


def test_ripartizione_12_contro_6():
    stats = [stat(scope=12), stat(scope=12), stat(scope=6), stat(scope=6)]
    ris = E.calcola(giocatori(stats=stats), [30, 20], 0)
    # q = 15/24 = 0,625 → vincitore ×1,125, compagno ×0,875; tra i perdenti chi ha fatto di più perde meno
    assert delta(ris) == [16.875, -13.125, 13.125, -16.875]
    assert ris[0]["dettaglio"]["ripartizione"] == pytest.approx(1.125)
    # la squadra nel complesso prende sempre 2·D
    assert ris[0]["delta"] + ris[2]["delta"] == pytest.approx(30)


def test_pareggio_squadre_pari_e_diverse():
    assert delta(E.calcola(giocatori(), [22, 22], "pari")) == [0, 0, 0, 0]
    stats = [stat(scope=8), stat(scope=8), stat(scope=2), stat(scope=2)]
    ris = E.calcola(giocatori(ele=(1650, 1450, 1650, 1450), stats=stats), [22, 22], "pari")
    e_forte = 1 / (1 + 10 ** (-200 / 400))
    d = 30 * (0.5 - e_forte)
    q = 11 / 16
    # squadra favorita: D < 0, si ripartisce come una sconfitta (chi ha fatto di più perde meno)
    assert ris[0]["delta"] == pytest.approx(d * (1 - 0.5 * (2 * q - 1)))
    assert ris[2]["delta"] == pytest.approx(d * (1 + 0.5 * (2 * q - 1)))
    # squadra sfavorita: D > 0, come una vittoria (ma senza moltiplicatore spettacolo)
    assert ris[1]["delta"] == pytest.approx(-d * (1 + 0.5 * (2 * q - 1)))
    assert all(r["esito"] == "pareggio" for r in ris)


def test_giocatore_provvisorio_usa_k_40():
    ris = E.calcola(giocatori(partite=(3, 20, 20, 14)), [30, 20], 0)
    assert delta(ris) == [20, -15, 15, -20]
    assert E.provvisorio(14) and not E.provvisorio(15)
    assert E.k_di(14) == 40 and E.k_di(15) == 30


def test_abbandono_sconfitta_piena_e_k_dimezzato_per_gli_altri():
    stats = [stat(scope=4), stat(scope=5), stat(scope=4), stat(scope=1)]
    ris = E.calcola(giocatori(stats=stats, abbandoni=(1,)), [30, 20], 1)
    # chi abbandona: K·(0 - E), anche se la sua squadra vince
    assert ris[1]["delta"] == pytest.approx(-15)
    assert ris[1]["esito"] == "sconfitta"
    # il compagno vince con K dimezzato: D = 15·(1 - 0,5) = 7,5, ripartito con i punti del posto 1
    q = (1 + 3) / (1 + 5 + 6)
    assert ris[3]["delta"] == pytest.approx(7.5 * (1 + 0.5 * (2 * q - 1)))
    assert ris[3]["k"] == 15 and ris[3]["esito"] == "vittoria"
    assert ris[0]["delta"] == pytest.approx(-7.5) and ris[2]["delta"] == pytest.approx(-7.5)


def test_bonus_spettacolo():
    stats = [stat(napoleoni=1), stat(), stat(napoleoni=1, bazziche=[{"scope": 7, "riscosse": 7}]),
             stat(bazziche=[{"scope": 7, "riscosse": 5}])]
    ris = E.calcola(giocatori(stats=stats), [30, 20], 0)
    q0 = 3 / 13   # il posto 2 ha 7 punti (la Bazzica riscossa), il posto 0 nessuno
    assert ris[0]["delta"] == pytest.approx(15 * (1 + 0.5 * (2 * q0 - 1)) + 3)
    assert ris[2]["delta"] == pytest.approx(15 * (1 - 0.5 * (2 * q0 - 1)) + 4)
    # Bazzica da 7 non riscossa per intero: niente bonus (ma le 5 Scope riscosse contano come punti)
    assert ris[3]["dettaglio"]["bonus"] == 0 and ris[3]["dettaglio"]["punti"] == 5
    # il fattore dei bonus dipende dall'atteso: sfavoriti ×1,5 al massimo, favoriti ×0,5 al minimo
    ris = E.calcola(giocatori(ele=(1300, 1800, 1300, 1800), stats=[stat(napoleoni=1)] * 4), [30, 20], 0)
    assert ris[0]["dettaglio"]["fattore_bonus"] == 1.5 and ris[1]["dettaglio"]["fattore_bonus"] == 0.5


def test_raccoglitore_credito_bazzica_riscosso_in_ordine():
    r = E.Raccoglitore()
    # Nord chiama una Bazzica da 3 e ne gira subito 1; Sud una da 2 senza girarne
    r.evento({"tipo": "bazzica", "seat": 0, "scope": 3, "girate": 1, "squadra": 0})
    r.evento({"tipo": "bazzica", "seat": 2, "scope": 2, "girate": 0, "squadra": 0})
    # Sud fa Scopa e con la stessa presa paga 2 carte di credito: vanno alla Bazzica di Nord
    r.evento({"tipo": "giocata", "seat": 2, "squadra": 0, "presa": ["x"], "scopa": True, "credito_pagato": 2,
              "girate": [["a", "sparecchio"], ["b", "bazzica"], ["c", "bazzica"]], "assi": []})
    # carte residue: 1 di credito, alla Bazzica di Sud; l'altra si perde a fine Mano
    r.evento({"tipo": "carte_residue", "squadra": 0, "credito_pagato": 1})
    r.evento({"tipo": "fine_mano", "riepilogo": {"squadre": [{"napola_nome": None}, {"napola_nome": None}]}})
    assert r.posti[0]["bazziche"] == [{"scope": 3, "riscosse": 3}]
    assert r.posti[2]["bazziche"] == [{"scope": 2, "riscosse": 1}]
    assert E.punti_individuali(r.posti[0]) == 3
    assert E.punti_individuali(r.posti[2]) == 2       # la Scopa + 1 Scopa della sua Bazzica
    # il credito non passa alla Mano successiva
    r.evento({"tipo": "giocata", "seat": 0, "squadra": 0, "presa": ["y"], "credito_pagato": 0, "girate": []})
    assert r.posti[2]["bazziche"][0]["riscosse"] == 1


def test_raccoglitore_piccola_grande_assi_napoleone():
    r = E.Raccoglitore()
    r.evento({"tipo": "giocata", "seat": 1, "squadra": 1, "presa": ["p"], "piccola": True, "girate": [["q", "piccola"]]})
    r.evento({"tipo": "giocata", "seat": 3, "squadra": 1, "presa": ["a", "b"], "grande": True, "scopa": False,
              "girate": [["g", "grande"], ["a", "grande"], ["b", "grande"]], "assi": []})
    r.evento({"tipo": "giocata", "seat": 3, "squadra": 1, "presa": ["c"], "assi": ["spade_01"],
              "girate": [["spade_01", "asso"]]})
    r.evento({"tipo": "giocata", "seat": 0, "squadra": 0, "presa": [], "scopa": False})   # nessuna presa
    r.evento({"tipo": "fine_mano", "riepilogo": {"squadre": [{"napola_nome": "Napola al 5"},
                                                             {"napola_nome": "Napoleone"}]}})
    assert r.posti[1]["piccole"] == 1 and E.punti_individuali(r.posti[1]) == 1
    assert r.posti[3]["grandi"] == 1 and r.posti[3]["carte_grande"] == 3 and r.posti[3]["assi"] == 1
    assert E.punti_individuali(r.posti[3]) == 4
    assert [p["napoleoni"] for p in r.posti] == [0, 1, 0, 1]


@pytest.mark.parametrize("variante", ["Vanilla", "Heisenberg", "Curie", "Avogadro"])
def test_punti_individuali_coerenti_con_le_scope_del_motore(variante):
    """Su partite vere: la somma dei punti individuali di una squadra è uguale alle Scope segnate dal
    motore (il credito di Bazzica perso non si segna), anche con le quote divise per la carta passata."""
    condivise = 0
    for seed in range(8):
        r = E.Raccoglitore(preset(variante))
        mani = []

        def on_events(_st, events):
            for e in events:
                r.evento(e)
                if e["tipo"] == "fine_mano":
                    mani.append(e["riepilogo"])
        agents = [HeuristicAgent(seed=seed * 10 + i) for i in range(4)]
        gioca_partita(preset(variante), agents, seed=seed, on_events=on_events)
        for t in (0, 1):
            scope_motore = sum(m["squadre"][t]["scope"] for m in mani)
            a, b = r.posti[t], r.posti[t + 2]
            assert E.punti_individuali(a, b) + E.punti_individuali(b, a) == pytest.approx(scope_motore)
        condivise += sum(1 for p in r.posti for x in ("scope", "piccole", "carte_grande", "assi")
                         if p[x] != int(p[x]))
    if variante == "Vanilla":
        assert condivise == 0          # senza scambio non c'è mai una carta passata


def scambio(r, seat, distribuite, ricevuta):
    """Simula distribuzione e scambio del Turno per ``seat``."""
    r.evento({"tipo": "carte_ricevute", "seat": seat, "carte": distribuite})
    r.evento({"tipo": "scambio_ricevuta", "seat": seat, "da": (seat + 2) % 4, "carta": ricevuta})


def test_carta_passata_divide_scopa_piccola_grande_assi():
    r = E.Raccoglitore(preset("Avogadro"))
    scambio(r, 0, ["coppe_05", "spade_03", "bastoni_09"], "denari_07")
    # Scopa con la carta ricevuta: metà a chi gioca, metà al compagno
    r.evento({"tipo": "giocata", "seat": 0, "squadra": 0, "carta": "denari_07", "presa": ["x"], "scopa": True,
              "girate": [["denari_07", "sparecchio"]]})
    # Scopa con una carta propria: tutta sua
    r.evento({"tipo": "giocata", "seat": 0, "squadra": 0, "carta": "coppe_05", "presa": ["y"], "scopa": True,
              "girate": [["coppe_05", "sparecchio"]]})
    assert (r.posti[0]["scope"], r.posti[2]["scope"]) == (1.5, 0.5)
    scambio(r, 1, ["coppe_01", "spade_02", "bastoni_10"], "spade_01")
    # Grande di 3 carte e un asso Avogadro preso con la carta ricevuta
    r.evento({"tipo": "giocata", "seat": 1, "squadra": 1, "carta": "spade_01", "presa": ["a", "b"], "grande": True,
              "girate": [["spade_01", "grande"], ["a", "grande"], ["b", "grande"]], "assi": []})
    r.evento({"tipo": "giocata", "seat": 1, "squadra": 1, "carta": "spade_01", "presa": ["c"],
              "assi": ["bastoni_01", "coppe_01"], "girate": []})
    assert (r.posti[1]["carte_grande"], r.posti[3]["carte_grande"]) == (1.5, 1.5)
    assert (r.posti[1]["grandi"], r.posti[3]["grandi"]) == (0.5, 0.5)
    assert (r.posti[1]["assi"], r.posti[3]["assi"]) == (1, 1)
    # nuovo Turno: la carta ricevuta prima non conta più
    r.evento({"tipo": "carte_ricevute", "seat": 2, "carte": ["coppe_07", "spade_07", "denari_02"]})
    r.evento({"tipo": "giocata", "seat": 2, "squadra": 0, "carta": "coppe_07", "presa": ["z"], "piccola": True,
              "girate": [["coppe_07", "piccola"]]})
    assert (r.posti[2]["piccole"], r.posti[0]["piccole"]) == (1, 0)


def test_bazzica_condivisa_solo_se_la_carta_ricevuta_e_decisiva():
    r = E.Raccoglitore(preset("Heisenberg"))
    # prima dello scambio 2-3-10: nessuna Bazzica; con il 4 ricevuto 2-3-4 è una Bazzica da 2
    scambio(r, 0, ["coppe_02", "spade_03", "bastoni_10"], "coppe_04")
    r.evento({"tipo": "bazzica", "seat": 0, "scope": 2, "girate": 2, "squadra": 0})
    # prima dello scambio 1-2-3: c'era già la stessa Bazzica, la carta ricevuta non è decisiva
    scambio(r, 1, ["coppe_01", "spade_02", "bastoni_03"], "denari_06")
    r.evento({"tipo": "bazzica", "seat": 1, "scope": 2, "girate": 2, "squadra": 1})
    assert r.posti[0]["bazziche"] == [{"scope": 2, "riscosse": 2, "condivisa": True}]
    assert r.posti[1]["bazziche"] == [{"scope": 2, "riscosse": 2}]
    a, b = r.posti[0], r.posti[2]
    assert (E.punti_individuali(a, b), E.punti_individuali(b, a)) == (1, 1)
    assert (E.punti_individuali(r.posti[1], r.posti[3]), E.punti_individuali(r.posti[3], r.posti[1])) == (2, 0)
    # in Vanilla non c'è scambio: mai condivisa
    v = E.Raccoglitore(preset("Vanilla"))
    v.evento({"tipo": "carte_ricevute", "seat": 0, "carte": ["coppe_02", "spade_03", "bastoni_04"]})
    v.evento({"tipo": "bazzica", "seat": 0, "scope": 2, "girate": 0, "squadra": 0})
    assert "condivisa" not in v.posti[0]["bazziche"][0]


def test_bazzica_da_7_condivisa_divide_il_bonus():
    stats = [stat(bazziche=[{"scope": 7, "riscosse": 7, "condivisa": True}]), stat(), stat(), stat()]
    ris = E.calcola(giocatori(stats=stats), [30, 20], 0)
    assert ris[0]["dettaglio"]["bazziche_7"] == 0.5 and ris[2]["dettaglio"]["bazziche_7"] == 0.5
    assert ris[0]["dettaglio"]["bonus"] == pytest.approx(0.5) and ris[2]["dettaglio"]["bonus"] == pytest.approx(0.5)
    # le 7 Scope riscosse si dividono: q = 6,5 / 13 = 0,5 per entrambi, ripartizione neutra
    assert ris[0]["dettaglio"]["punti"] == 3.5 and ris[2]["dettaglio"]["ripartizione"] == pytest.approx(1)
