"""Variante Heisenberg: scambio carte, passa veloce, segretezza."""
import pytest

from conftest import C, CC, make_state
from bazzica.engine import (legal_actions, apply_inplace, Action, preset, observation, IllegalAction,
                            new_game, required_actors)

H = preset("Heisenberg")


def _st():
    return make_state(rules=H, fase="scambio",
                      mani={0: ["C1", "C2", "C3"], 1: ["S1", "S2", "S3"], 2: ["B1", "B2", "B3"],
                            3: ["D4", "D5", "D6"]}, tavola=["C9"])


def passabili(st, seat):
    return sorted({a.carta for a in legal_actions(st, seat) if a.tipo == "passa"})


def test_fase_scambio_dopo_distribuzione():
    st, ev = new_game(H, seed=3)
    assert st.fase == "scambio"
    assert sorted(required_actors(st)) == [0, 1, 2, 3]


def test_carta_del_compagno_invisibile_finche_non_passo():
    st = _st()
    apply_inplace(st, Action("passa", 0, carta=C("C1")))
    # 2 non vede la carta di 0 finché non ha passato la sua
    assert C("C1") not in st.mani[2]
    o2 = observation(st, 2)
    assert C("C1") not in o2["mano"] and o2["scambio"]["ricevuta"] is None
    assert C("C1") not in str(o2)
    assert o2["scambio"]["passati"][0] is True
    # e non può passarla
    assert passabili(st, 2) == sorted(CC("B1", "B2", "B3"))
    with pytest.raises(IllegalAction):
        apply_inplace(st, Action("passa", 2, carta=C("C1")))
    ev = apply_inplace(st, Action("passa", 2, carta=C("B2")))
    ric = [e for e in ev if e["tipo"] == "scambio_ricevuta"]
    assert {(e["seat"], e["carta"]) for e in ric} == {(2, C("C1")), (0, C("B2"))}
    assert all(e["visibile"] == [e["seat"]] for e in ric)
    assert sorted(st.mani[2]) == sorted(CC("B1", "B3", "C1"))
    assert sorted(st.mani[0]) == sorted(CC("C2", "C3", "B2"))
    assert observation(st, 2)["scambio"]["ricevuta"] == C("C1")


def test_carta_ricevuta_non_ripassabile():
    st = _st()
    apply_inplace(st, Action("passa", 2, carta=C("B2")))
    apply_inplace(st, Action("passa", 0, carta=C("C3")))
    assert not [a for a in legal_actions(st, 0) if a.tipo == "passa"]
    assert not [a for a in legal_actions(st, 2) if a.tipo == "passa"]


def test_passa_veloce_pubblico_ma_carta_segreta():
    st = _st()
    ev = apply_inplace(st, Action("passa", 1, carta=C("S1"), veloce=True))
    priv = next(e for e in ev if e["tipo"] == "scambio_carta")
    pub = next(e for e in ev if e["tipo"] == "scambio")
    assert priv["visibile"] == [1] and priv["carta"] == C("S1")
    assert pub["visibile"] is None and pub["veloce"] and "carta" not in pub
    for s in (0, 2, 3):
        o = observation(st, s)
        assert o["scambio"]["veloci"][1] is True
        assert C("S1") not in str(o)


def test_giocate_iniziano_dopo_tutti_gli_scambi():
    st = _st()
    for s, c in [(0, "C1"), (1, "S1"), (2, "B1")]:
        apply_inplace(st, Action("passa", s, carta=C(c)))
        assert st.fase == "scambio"
    apply_inplace(st, Action("passa", 3, carta=C("D4")))
    assert st.fase == "gioco" and st.corrente == 0


def test_attendi_non_crea_stallo():
    st = _st()
    apply_inplace(st, Action("attendi", 0))
    assert not any(a.tipo == "attendi" for a in legal_actions(st, 2))
    assert not any(a.tipo == "attendi" for a in legal_actions(st, 0))


def test_bazzica_con_la_mano_dopo_lo_scambio():
    st = _st()
    # 0 riceve B1, B2? no: 2 passa B1 a 0; 0 passa C3
    apply_inplace(st, Action("passa", 2, carta=C("B1")))
    apply_inplace(st, Action("passa", 0, carta=C("C3")))
    apply_inplace(st, Action("passa", 1, carta=C("S3")))
    apply_inplace(st, Action("passa", 3, carta=C("D6")))
    # mano di 0: C1, C2, B1 -> coppia di assi, somma 4 -> 3 Scope
    baz = [a for a in legal_actions(st, 0) if a.tipo == "bazzica"]
    assert len(baz) == 1
    ev = apply_inplace(st, baz[0])
    assert ev[0]["scope"] == 3
