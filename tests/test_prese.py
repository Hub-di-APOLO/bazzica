"""Prese, asso piglia tutto, Scope, ultima giocata, carte residue."""
import pytest

from conftest import C, CC, make_state, play
from bazzica.engine import legal_actions, apply, apply_inplace, opzioni_presa, IllegalAction, preset


def plays_of(st, seat, carta):
    return sorted(tuple(sorted(a.presa)) for a in legal_actions(st, seat)
                  if a.tipo == "gioca" and a.carta == C(carta))


def test_presa_singola_obbligatoria():
    st = make_state(mani={0: ["C5", "S9", "B10"]}, tavola=["D5", "S2", "S3"])
    assert plays_of(st, 0, "C5") == [(C("D5"),)]
    with pytest.raises(IllegalAction):
        apply(st, play(0, "C5", ["S2", "S3"]))


def test_presa_singola_scelta_tra_piu_uguali():
    st = make_state(mani={0: ["C5", "S9", "B10"]}, tavola=["D5", "S5", "S3"])
    assert plays_of(st, 0, "C5") == sorted([(C("D5"),), (C("S5"),)])


def test_combinazioni_a_scelta():
    st = make_state(mani={0: ["C7", "S9", "B10"]}, tavola=["D2", "S5", "S3", "B4"])
    opts = plays_of(st, 0, "C7")
    assert tuple(sorted(CC("D2", "S5"))) in opts
    assert tuple(sorted(CC("S3", "B4"))) in opts
    assert len(opts) == 2


def test_carta_che_non_prende_resta_in_tavola():
    st = make_state(mani={0: ["C9", "S9", "B10"]}, tavola=["D2", "S5"])
    assert plays_of(st, 0, "C9") == [()]
    st2, ev = apply(st, play(0, "C9"))
    assert C("C9") in st2.tavola
    assert st2.piccola_target == C("C9")


def test_asso_piglia_tutto_e_scopa():
    st = make_state(mani={0: ["C1", "S9", "B10"]}, tavola=["D2", "S5", "B7"])
    assert plays_of(st, 0, "C1") == [tuple(sorted(CC("D2", "S5", "B7")))]
    st2, ev = apply(st, play(0, "C1", ["D2", "S5", "B7"]))
    assert st2.tavola == []
    assert st2.prese[0][0] == [C("C1"), True, "sparecchio"]
    assert ev[0]["scopa"]


def test_asso_con_asso_in_tavola_prende_solo_asso():
    st = make_state(mani={0: ["C1", "S9", "B10"]}, tavola=["D1", "S5", "B1"])
    assert plays_of(st, 0, "C1") == sorted([(C("D1"),), (C("B1"),)])
    st2, ev = apply(st, play(0, "C1", ["D1"]))
    assert not ev[0]["scopa"]
    assert sorted(st2.tavola) == sorted(CC("S5", "B1"))


def test_asso_che_prende_unico_asso_sparecchia_e_fa_scopa():
    st = make_state(mani={0: ["C1", "S9", "B10"]}, tavola=["D1"])
    st2, ev = apply(st, play(0, "C1", ["D1"]))
    assert ev[0]["scopa"]


def test_asso_su_tavolo_vuoto_resta_e_non_fa_scopa():
    st = make_state(mani={0: ["C1", "S9", "B10"]}, tavola=[])
    assert plays_of(st, 0, "C1") == [()]
    st2, ev = apply(st, play(0, "C1"))
    assert st2.tavola == [C("C1")]
    assert not ev[0]["scopa"] and st2.prese[0] == []


def test_scopa_normale():
    st = make_state(mani={0: ["C7", "S9", "B10"]}, tavola=["D3", "S4"])
    st2, ev = apply(st, play(0, "C7", ["D3", "S4"]))
    assert ev[0]["scopa"]
    assert sum(1 for e in st2.prese[0] if e[1]) == 1


def _ultima(rules=None, tavola=("D3", "S4"), carta="C7", prese=None, credito=(0, 0)):
    # turno 3, mazziere 3 (Ovest) con l'ultima carta della Mano
    return make_state(rules=rules, mani={3: [carta]}, tavola=tavola, turno=3, corrente=3,
                      giocato=[True] * 4, prese=prese, credito=credito, mazzo=[])


def test_ultima_giocata_non_fa_scopa():
    st = _ultima()
    st2, ev = apply(st, play(3, "C7", ["D3", "S4"]))
    g = next(e for e in ev if e["tipo"] == "giocata")
    assert g["ultima_giocata"] and not g["scopa"]
    assert all(not e[1] for e in st2.prese[1])


def test_ultima_del_primo_turno_fa_scopa():
    st = make_state(mani={3: ["C7"]}, tavola=["D3", "S4"], turno=1, corrente=3, giocato=[True] * 4)
    st2, ev = apply(st, play(3, "C7", ["D3", "S4"]))
    g = next(e for e in ev if e["tipo"] == "giocata")
    assert g["scopa"] and not g["ultima_giocata"]
    assert st2.turno == 2


def test_carte_residue_alla_squadra_dell_ultima_presa():
    # ultima presa fatta da Nord-Sud (squadra 0); l'ultima carta non prende
    st = _ultima(tavola=("D3", "S5"), carta="C9")
    st.ultima_presa_squadra = 0
    st2, ev = apply(st, play(3, "C9"))
    res = next(e for e in ev if e["tipo"] == "carte_residue")
    assert res["squadra"] == 0
    assert sorted(e[0] for e in st2.prese[0]) == sorted(CC("D3", "S5", "C9"))
    assert all(not e[1] for e in st2.prese[0])


def test_gioco_in_senso_orario_e_mazziere_ultimo():
    st = make_state(mani={0: ["C9"], 1: ["S9"], 2: ["B9"], 3: ["D9"]}, mazziere=3, tavola=["D1"])
    assert st.corrente == 0
    order = []
    for s in (0, 1, 2, 3):
        assert st.corrente == s
        order.append(s)
        a = [x for x in legal_actions(st, s) if x.tipo == "gioca"][0]
        apply_inplace(st, a)
    assert order == [0, 1, 2, 3]


def test_nuova_mano_ruota_il_mazziere():
    from bazzica.engine import new_game, system_action
    st, _ = new_game(preset("Vanilla"), seed=1, mazziere=2)
    st.fase = "fine_mano"
    apply_inplace(st, system_action(st))
    assert st.mazziere == 3 and st.corrente == 0 and len(st.tavola) == 4
