"""Bazziche, 7 bello jolly, crediti, Che Palo!"""
import pytest

from conftest import C, CC, make_state, play
from bazzica.engine import (opzioni_bazzica, puo_dire_che_palo, legal_actions, apply, apply_inplace,
                            Action, preset, observation, IllegalAction)

V = preset("Vanilla")


def tipi(mano, rules=V):
    return [(o["sette"], o["tipo"], o["scope"]) for o in opzioni_bazzica(CC(*mano), rules)]


def test_tipi_base():
    assert tipi(["C1", "S3", "B5"]) == [(None, "diverse", 2)]
    assert tipi(["C1", "S3", "B6"]) == []          # somma 10
    assert tipi(["C2", "S2", "B5"]) == [(None, "coppia", 3)]
    assert tipi(["C2", "S2", "B6"]) == []          # coppia somma 10
    assert tipi(["C9", "S9", "B9"]) == [(None, "tris", 7)]
    assert tipi(["C2", "S2", "B2"]) == [(None, "tris", 7)]  # tris con somma <= 9 vale 7, non si cumula


def test_sette_bello_jolly():
    ops = tipi(["D7", "S1", "B3"])
    d = {o[0]: (o[1], o[2]) for o in ops}
    assert d[5] == ("diverse", 2)
    assert d[1] == ("coppia", 3)
    assert d[3] == ("coppia", 3)
    assert 7 not in d   # 1+3+7 = 11
    ops = tipi(["D7", "S10", "B10"])
    assert ops == [(10, "tris", 7)]
    assert tipi(["D7", "S9", "B10"]) == []


def test_einstein_tris_con_sette_bello_vale_5():
    E = preset("Einstein")
    assert tipi(["D7", "S10", "B10"], E) == [(10, "tris", 5)]
    # tris naturale di 7 con il 7 bello: 5 (scelta dell'utente)
    assert (7, "tris", 5) in tipi(["D7", "S7", "B7"], E)
    assert tipi(["C9", "S9", "B9"], E) == [(None, "tris", 7)]
    d = {o[0]: o[2] for o in tipi(["D7", "S3", "B3"], E)}
    assert d[3] == 5 and d[1] == 3


def _baz_state(rules=V, mano0=("C1", "S3", "B5"), prese0=(), credito=(0, 0), tavola=("D9",)):
    return make_state(rules=rules, mani={0: list(mano0), 1: ["C9", "S9", "B9"], 2: ["D4", "D5", "D6"],
                                         3: ["C10", "S10", "B10"]},
                      tavola=tavola, prese=[list(prese0), []], credito=credito)


def test_bazzica_facoltativa_e_prima_della_prima_carta():
    st = _baz_state()
    acts = legal_actions(st, 0)
    assert any(a.tipo == "bazzica" for a in acts)
    assert any(a.tipo == "gioca" for a in acts)
    apply_inplace(st, [a for a in acts if a.tipo == "gioca"][0])
    # Nel giro successivo non è più possibile
    st.corrente = 0
    st.mani[0].append(C("B2"))
    assert not any(a.tipo == "bazzica" for a in legal_actions(st, 0))


def test_bazzica_gira_carte_e_crea_credito():
    st = _baz_state(prese0=["C2"])
    ev = apply_inplace(st, Action("bazzica", 0))
    assert ev[0]["girate"] == 1 and st.credito[0] == 1
    assert st.prese[0][0][1] is True and st.prese[0][0][2] == "bazzica"


def test_bazzica_mano_visibile_a_tutti():
    st = _baz_state()
    assert observation(st, 1)["altri"]["0"]["carte"] is None
    apply_inplace(st, Action("bazzica", 0))
    assert sorted(observation(st, 1)["altri"]["0"]["carte"]) == sorted(CC("C1", "S3", "B5"))
    # le altre mani restano coperte
    assert observation(st, 1)["altri"]["2"]["carte"] is None


def test_credito_riscosso_con_le_prese():
    st = _baz_state(credito=(0, 0))
    apply_inplace(st, Action("bazzica", 0))  # 2 Scope, nessuna carta: credito 2
    assert st.credito[0] == 2
    st.tavola = [C("D3")]
    apply_inplace(st, play(0, "S3", ["D3"]))  # presa di 2 carte, paga 2 (no scopa: tavolo vuoto? sì scopa)
    # sparecchio: la S3 a faccia in su (scopa) + D3 paga 1 di credito
    assert st.credito[0] == 1
    origini = sorted(e[2] for e in st.prese[0])
    assert origini == ["bazzica", "sparecchio"]


def test_credito_parziale_e_perso_a_fine_mano():
    st = make_state(mani={3: ["C9"]}, tavola=["D3", "S6"], turno=3, corrente=3, giocato=[True] * 4,
                    credito=(0, 5), mazzo=[])
    st2, ev = apply(st, play(3, "C9", ["D3", "S6"]))
    # ultima giocata: niente scopa; 3 carte pagano 3 di credito, ne restano 2 perse
    rie = next(e for e in ev if e["tipo"] == "fine_mano")["riepilogo"]
    assert rie["credito_perso"] == [0, 2]
    assert rie["squadre"][1]["scope_dettaglio"]["bazzica"] == 3


def test_credito_riscosso_con_carte_residue():
    st = make_state(mani={3: ["C9"]}, tavola=["D3", "S5"], turno=3, corrente=3, giocato=[True] * 4,
                    credito=(2, 0), mazzo=[])
    st.ultima_presa_squadra = 0
    st2, ev = apply(st, play(3, "C9"))
    rie = next(e for e in ev if e["tipo"] == "fine_mano")["riepilogo"]
    assert rie["squadre"][0]["scope_dettaglio"]["bazzica"] == 2
    assert rie["credito_perso"] == [0, 0]


def test_sette_bello_prende_con_valore_assegnato():
    st = _baz_state(mano0=("D7", "S1", "B3"), tavola=("C5", "S2", "C3"))
    apply_inplace(st, Action("bazzica", 0, sette=5))
    acts = [a for a in legal_actions(st, 0) if a.tipo == "gioca" and a.carta == C("D7")]
    assert [a.presa for a in acts] == [(C("C5"),)]  # presa singola obbligatoria del 5


def test_sette_bello_combinazione_con_valore_assegnato():
    st = _baz_state(mano0=("D7", "S1", "B3"), tavola=("C2", "S3"))
    apply_inplace(st, Action("bazzica", 0, sette=5))
    acts = [a for a in legal_actions(st, 0) if a.tipo == "gioca" and a.carta == C("D7")]
    assert [tuple(sorted(a.presa)) for a in acts] == [tuple(sorted(CC("C2", "S3")))]


def test_sette_bello_torna_7_se_non_prende():
    st = _baz_state(mano0=("D7", "S1", "B3"), tavola=("C9",))
    apply_inplace(st, Action("bazzica", 0, sette=5))
    apply_inplace(st, play(0, "D7"))
    assert C("D7") in st.tavola
    # il giocatore successivo prende il 7 bello con un 7 (vale 7, non 5)
    st.mani[1] = CC("C7", "S9", "B9")
    acts = [a for a in legal_actions(st, 1) if a.tipo == "gioca" and a.carta == C("C7")]
    assert [a.presa for a in acts] == [(C("D7"),)]


def test_sette_bello_valore_1_non_piglia_tutto():
    # Vanilla: 7 bello a cui si assegna 1 vale solo 1 (scelta dell'utente)
    st = _baz_state(mano0=("D7", "S1", "B3"), tavola=("C5", "S2"))
    apply_inplace(st, Action("bazzica", 0, sette=1))
    acts = [a for a in legal_actions(st, 0) if a.tipo == "gioca" and a.carta == C("D7")]
    assert [a.presa for a in acts] == [()]
    st = _baz_state(mano0=("D7", "S1", "B3"), tavola=("C5", "B1"))
    apply_inplace(st, Action("bazzica", 0, sette=1))
    acts = [a for a in legal_actions(st, 0) if a.tipo == "gioca" and a.carta == C("D7")]
    assert [a.presa for a in acts] == [(C("B1"),)]


def test_asso_in_bazzica_vanilla_piglia_tutto():
    st = _baz_state(mano0=("C1", "S3", "B5"), tavola=("C5", "S2"))
    apply_inplace(st, Action("bazzica", 0))
    acts = [a for a in legal_actions(st, 0) if a.tipo == "gioca" and a.carta == C("C1")]
    assert [tuple(sorted(a.presa)) for a in acts] == [tuple(sorted(CC("C5", "S2")))]


# ---------------------------------------------------------------- Che Palo!

def test_che_palo_condizioni():
    assert puo_dire_che_palo(CC("C5", "S5", "B6"), V)       # esempio del regolamento
    assert not puo_dire_che_palo(CC("C1", "S3", "B5"), V)   # ha già una Bazzica
    assert not puo_dire_che_palo(CC("C8", "S9", "B10"), V)
    assert puo_dire_che_palo(CC("D7", "S9", "B10"), V)      # 9 -> 10 farebbe tris col 7 bello


def test_che_palo_sempre_disponibile():
    st = make_state(mani={0: ["C8", "S9", "B10"], 1: ["C5", "S5", "B6"], 2: ["D8", "D9", "C10"],
                          3: ["S8", "B8", "B9"]}, tavola=["D1"])
    assert st.corrente == 0
    # fuori turno, con un palo sensato: il bot viene interpellato (attendi = non esclamare)
    assert {a.tipo for a in legal_actions(st, 1)} == {"che_palo", "attendi"}
    ev = apply_inplace(st, Action("che_palo", 1))
    assert ev[0]["tipo"] == "che_palo" and ev[0]["visibile"] is None
    # il pulsante resta disponibile quando si vuole, anche più volte
    assert [a.tipo for a in legal_actions(st, 1)] == ["che_palo"]
    apply_inplace(st, Action("che_palo", 1))
    # anche con una mano lontana da una Bazzica e dopo aver giocato
    assert any(a.tipo == "che_palo" for a in legal_actions(st, 0))
    apply_inplace(st, play(0, "C8"))
    assert any(a.tipo == "che_palo" for a in legal_actions(st, 0))


def test_che_palo_durante_lo_scambio():
    st = make_state(rules=preset("Heisenberg"), fase="scambio", mani={0: ["C8", "S9", "B10"]})
    assert any(a.tipo == "che_palo" for a in legal_actions(st, 0))


def test_bot_offerta_palo_solo_se_sensato():
    from bazzica.engine import optional_actors
    st = make_state(mani={0: ["C8", "S9", "B10"], 1: ["C5", "S5", "B6"], 2: ["D8", "D9", "C10"]},
                    tavola=["D1"])
    assert optional_actors(st) == [1]
