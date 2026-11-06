"""Comportamenti del bot euristico."""
from conftest import C, CC, make_state
from bazzica.bots import HeuristicAgent, testo_osservazione
from bazzica.engine import legal_actions, apply_inplace, Action, observation, preset

H = preset("Heisenberg")


def scegli(st, seat):
    return HeuristicAgent(seed=1).choose_action(observation(st, seat), legal_actions(st, seat))


def test_bot_chiama_bazzica():
    st = make_state(mani={0: ["C9", "S9", "B9"]}, tavola=["D4"])
    assert scegli(st, 0).tipo == "bazzica"


def test_bot_sceglie_valore_7_bello_migliore():
    st = make_state(mani={0: ["D7", "S10", "B10"]}, tavola=["C4"])
    a = scegli(st, 0)
    assert a.tipo == "bazzica" and a.sette == 10


def test_bot_prende_la_scopa():
    st = make_state(mani={0: ["C7", "S9", "B10"]}, tavola=["D3", "S4"])
    a = scegli(st, 0)
    assert a.tipo == "gioca" and a.carta == C("C7")


def test_bot_evita_due_di_denari():
    st = make_state(mani={0: ["C2", "S8", "B10"]}, tavola=["D2", "S5", "S1"])
    a = scegli(st, 0)
    assert a.carta != C("C2")


def test_bot_che_palo():
    st = make_state(mani={0: ["C5", "S5", "B6"]}, tavola=["D9"])
    assert scegli(st, 0).tipo == "che_palo"


def test_bot_passa_veloce_con_coppia():
    st = make_state(rules=H, fase="scambio", mani={0: ["C9", "S9", "B4"], 2: ["D1", "D2", "D3"]})
    a = scegli(st, 0)
    assert a.tipo == "passa" and a.veloce and a.carta == C("B4")


def test_bot_risponde_al_passa_veloce_col_7_bello():
    st = make_state(rules=H, fase="scambio", mani={0: ["C9", "S9", "B4"], 2: ["D7", "S10", "C8"]})
    apply_inplace(st, Action("passa", 0, carta=C("B4"), veloce=True))
    a = scegli(st, 2)
    assert a.tipo == "passa" and a.carta == C("D7")


def test_testo_osservazione():
    st = make_state(mani={0: ["C5", "S5", "B6"]}, tavola=["D9"])
    t = testo_osservazione(observation(st, 0))
    assert "Sei Nord" in t and "Cavallo di denari" in t
