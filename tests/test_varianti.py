"""Pascal, Curie (Piccola e Grande), Avogadro, fine partita e Margherita Hack."""
from conftest import C, CC, make_state, play
from bazzica.engine import (legal_actions, apply_inplace, apply, Action, preset, with_flags, new_game,
                            system_action, required_actors)

PA = preset("Pascal")
CU = preset("Curie")
AV = preset("Avogadro")


def presa_opts(st, seat, carta):
    return sorted(tuple(sorted(a.presa)) for a in legal_actions(st, seat)
                  if a.tipo == "gioca" and a.carta == C(carta))


def giocata(ev):
    return next(e for e in ev if e["tipo"] == "giocata")


# ------------------------------------------------------------------ Pascal

def test_pascal_asso_di_bazzica_vale_1():
    st = make_state(rules=PA, mani={0: ["C1", "S3", "B5"]}, tavola=["D5", "S2"])
    apply_inplace(st, Action("bazzica", 0))
    assert presa_opts(st, 0, "C1") == [()]
    st = make_state(rules=PA, mani={0: ["C1", "S3", "B5"]}, tavola=["D5", "S1"])
    apply_inplace(st, Action("bazzica", 0))
    assert presa_opts(st, 0, "C1") == [(C("S1"),)]


def test_pascal_asso_senza_bazzica_piglia_tutto():
    st = make_state(rules=PA, mani={0: ["C1", "S3", "B5"]}, tavola=["D5", "S2"])
    assert presa_opts(st, 0, "C1") == [tuple(sorted(CC("D5", "S2")))]


# ------------------------------------------------------------------ Curie: Piccola

def _piccola_state(rules=CU, tavola=("D9",), mani1=("S4", "S9", "B10")):
    st = make_state(rules=rules, mani={0: ["C4", "C8", "B2"], 1: list(mani1)}, tavola=list(tavola))
    apply_inplace(st, play(0, "C4"))   # il 4 resta in tavola
    return st


def test_piccola():
    st = _piccola_state()
    ev = apply_inplace(st, play(1, "S4", ["C4"]))
    g = giocata(ev)
    assert g["piccola"] and not g["scopa"]
    assert [e[2] for e in st.prese[1] if e[1]] == ["piccola"]


def test_piccola_che_sparecchia_vale_una_sola_scopa():
    st = _piccola_state(tavola=())
    ev = apply_inplace(st, play(1, "S4", ["C4"]))
    g = giocata(ev)
    assert g["piccola"] and not g["scopa"] and g["sparecchio"]
    assert sum(1 for e in st.prese[1] if e[1]) == 1


def test_niente_piccola_senza_curie():
    st = _piccola_state(rules=preset("Pascal"))
    g = giocata(apply_inplace(st, play(1, "S4", ["C4"])))
    assert not g["piccola"]


def test_piccola_solo_carta_del_giocatore_precedente():
    st = make_state(rules=CU, mani={0: ["C4", "C8", "B2"], 1: ["S9"], 2: ["S4", "B9", "B8"]},
                    tavola=["D10"])
    apply_inplace(st, play(0, "C4"))
    apply_inplace(st, play(1, "S9"))
    g = giocata(apply_inplace(st, play(2, "S4", ["C4"])))
    assert not g["piccola"]


def test_primo_giocatore_del_turno_non_fa_piccola():
    # ultima giocata del turno 1 lascia un 4; il primo del turno 2 lo prende
    st = make_state(rules=with_flags(CU, scambio=False), mani={3: ["C4"]}, tavola=["D9"], turno=1,
                    corrente=3, giocato=[True] * 4)
    apply_inplace(st, play(3, "C4"))
    assert st.turno == 2 and st.corrente == 0
    st.mani[0] = CC("S4", "B9", "B8")
    g = giocata(apply_inplace(st, play(0, "S4", ["C4"])))
    assert not g["piccola"]


def test_piccola_con_sette_bello_di_bazzica():
    st = make_state(rules=CU, mani={0: ["C4", "C8", "B10"], 1: ["D7", "S1", "B3"]}, tavola=["S9"])
    apply_inplace(st, play(0, "C4"))
    apply_inplace(st, Action("bazzica", 1, sette=4))   # 4 + 1 + 3 = 8: tre diverse
    g = giocata(apply_inplace(st, play(1, "D7", ["C4"])))
    assert g["piccola"]


def test_piccola_e_grande_vale_solo_grande():
    # Piccola e Grande insieme sono possibili solo con il 7 bello di Bazzica
    # (due carte normali dello stesso valore hanno semi diversi).
    st = make_state(rules=CU, mani={0: ["D4", "C8", "B2"], 1: ["D7", "S1", "B3"]}, tavola=["S9"])
    apply_inplace(st, play(0, "D4"))
    apply_inplace(st, Action("bazzica", 1, sette=4))
    g = giocata(apply_inplace(st, play(1, "D7", ["D4"])))
    assert g["grande"] and not g["piccola"]
    assert sorted(e[2] for e in st.prese[1] if e[1]) == ["grande", "grande"]


# ------------------------------------------------------------------ Curie: Grande

def test_grande_presa_multipla_stesso_seme():
    st = make_state(rules=CU, mani={0: ["C7", "S9", "B10"]}, tavola=["C3", "C4", "S10"])
    g = giocata(apply_inplace(st, play(0, "C7", ["C3", "C4"])))
    assert g["grande"] and not g["scopa"]
    assert sum(1 for e in st.prese[0] if e[1]) == 3


def test_grande_che_sparecchia_conta_solo_la_grande():
    st = make_state(rules=CU, mani={0: ["C7", "S9", "B10"]}, tavola=["C3", "C4"])
    g = giocata(apply_inplace(st, play(0, "C7", ["C3", "C4"])))
    assert g["grande"] and not g["scopa"]
    assert sum(1 for e in st.prese[0] if e[1]) == 3


def test_grande_con_sette_bello_su_denari():
    st = make_state(rules=CU, mani={0: ["D7", "S1", "B3"]}, tavola=["D5", "S9"])
    apply_inplace(st, Action("bazzica", 0, sette=5))
    g = giocata(apply_inplace(st, play(0, "D7", ["D5"])))
    assert g["grande"]
    assert sorted(e[2] for e in st.prese[0] if e[1]).count("grande") == 2


def test_grande_con_sette_bello_somma_di_denari():
    st = make_state(rules=CU, mani={0: ["D7", "S1", "B3"]}, tavola=["D2", "D3", "S10"])
    apply_inplace(st, Action("bazzica", 0, sette=5))
    g = giocata(apply_inplace(st, play(0, "D7", ["D2", "D3"])))
    assert g["grande"]
    assert sum(1 for e in st.prese[0] if e[2] == "grande") == 3


def test_grande_asso_piglia_tutto_stesso_seme():
    st = make_state(rules=CU, mani={0: ["B1", "S9", "C10"]}, tavola=["B5", "B8"])
    g = giocata(apply_inplace(st, play(0, "B1", ["B5", "B8"])))
    assert g["grande"] and not g["scopa"]
    assert sum(1 for e in st.prese[0] if e[1]) == 3


def test_niente_grande_se_semi_diversi():
    st = make_state(rules=CU, mani={0: ["B1", "S9", "C10"]}, tavola=["B5", "C8"])
    g = giocata(apply_inplace(st, play(0, "B1", ["B5", "C8"])))
    assert not g["grande"] and g["scopa"]


def test_grande_asso_in_bazzica_senza_pascal_non_vale():
    r = with_flags(preset("Heisenberg"), curie=True)
    st = make_state(rules=r, mani={0: ["B1", "S3", "C5"]}, tavola=["B5", "B8"])
    apply_inplace(st, Action("bazzica", 0))
    g = giocata(apply_inplace(st, play(0, "B1", ["B5", "B8"])))
    assert not g["grande"] and g["scopa"]


def test_ultima_giocata_niente_piccola_ne_grande():
    st = make_state(rules=CU, mani={3: ["C7"]}, tavola=["C3", "C4"], turno=3, corrente=3,
                    giocato=[True] * 4, mazzo=[])
    g = giocata(apply_inplace(st, play(3, "C7", ["C3", "C4"])))
    assert not g["grande"] and not g["scopa"]
    st = make_state(rules=CU, mani={3: ["C4"]}, tavola=["S4"], turno=3, corrente=3,
                    giocato=[True] * 4, mazzo=[], piccola_target="S4")
    g = giocata(apply_inplace(st, play(3, "C4", ["S4"])))
    assert not g["piccola"]


# ------------------------------------------------------------------ Avogadro

def test_avogadro_asso_preso_fa_scopa():
    st = make_state(rules=AV, mani={0: ["C2", "S9", "B10"]}, tavola=["D1", "S1", "B5"])
    st.mani[0] = CC("C6", "S9", "B10")
    g = giocata(apply_inplace(st, play(0, "C6", ["D1", "B5"])))
    assert g["assi"] == [C("D1")]
    assert [e[2] for e in st.prese[0] if e[1]] == ["asso"]


def test_avogadro_asso_su_asso_due_scope():
    st = make_state(rules=AV, mani={0: ["C1", "S9", "B10"]}, tavola=["D1", "B5"])
    g = giocata(apply_inplace(st, play(0, "C1", ["D1"])))
    assert sorted(g["assi"]) == sorted(CC("C1", "D1"))
    assert sum(1 for e in st.prese[0] if e[1]) == 2


def test_avogadro_asso_che_piglia_tutto_non_raddoppia():
    st = make_state(rules=AV, mani={0: ["C1", "S9", "B10"]}, tavola=["D2", "S5"])
    g = giocata(apply_inplace(st, play(0, "C1", ["D2", "S5"])))
    assert g["scopa"] and g["assi"] == []
    assert sum(1 for e in st.prese[0] if e[1]) == 1


def test_avogadro_asso_in_grande_non_raddoppia():
    st = make_state(rules=AV, mani={0: ["C7", "S9", "B10"]}, tavola=["C1", "C6", "S10"])
    g = giocata(apply_inplace(st, play(0, "C7", ["C1", "C6"])))
    assert g["grande"] and g["assi"] == []
    assert sum(1 for e in st.prese[0] if e[1]) == 3


def test_avogadro_ultima_giocata_e_residue_niente_scopa():
    st = make_state(rules=AV, mani={3: ["C6"]}, tavola=["D1", "B5", "S1", "C9"], turno=3, corrente=3,
                    giocato=[True] * 4, mazzo=[])
    st.ultima_presa_squadra = 0
    ev = apply_inplace(st, play(3, "C6", ["D1", "B5"]))
    assert giocata(ev)["assi"] == []
    rie = next(e for e in ev if e["tipo"] == "fine_mano")["riepilogo"]
    assert rie["squadre"][1]["scope"] == 0   # residue (S1, C9) alla squadra 1, ultima presa
    assert rie["squadre"][0]["scope"] == 0


def test_avogadro_credito_dopo_assi():
    st = make_state(rules=AV, mani={0: ["C6", "S9", "B10"]}, tavola=["D1", "B5", "S8"], credito=(1, 0))
    apply_inplace(st, play(0, "C6", ["D1", "B5"]))
    orig = sorted(e[2] for e in st.prese[0] if e[1])
    assert orig == ["asso", "bazzica"] and st.credito[0] == 0


# ------------------------------------------------------------------ Fine partita

def _chiudi_mano(st, punti):
    st.punteggi = list(punti)
    from bazzica.engine.game import _controlla_fine
    return _controlla_fine(st)


def test_fine_partita_21_e_vantaggio():
    st, _ = new_game(preset("Vanilla"), seed=1)
    assert _chiudi_mano(st, (21, 15)) == 0
    assert _chiudi_mano(st, (20, 15)) is None
    assert _chiudi_mano(st, (22, 25)) == 1
    assert _chiudi_mano(st, (10, 21)) == 1


def test_spareggio_ad_oltranza():
    st, _ = new_game(preset("Vanilla"), seed=1)
    assert _chiudi_mano(st, (23, 23)) is None


def test_margherita_hack_quattro_mani_e_parita():
    st, _ = new_game(preset("Vanilla", margherita_hack=True), seed=1)
    st.mano_n = 3
    assert _chiudi_mano(st, (40, 5)) is None
    st.mano_n = 4
    assert _chiudi_mano(st, (10, 10)) == "pari"
    assert _chiudi_mano(st, (3, 10)) == 1


def test_margherita_hack_ognuno_fa_il_mazziere():
    st, _ = new_game(preset("Vanilla", margherita_hack=True), seed=5)
    mazzieri = []
    while st.fase != "fine_partita":
        if st.fase == "fine_mano":
            apply_inplace(st, system_action(st))
            continue
        if st.turno == 1 and not any(st.giocato_turno) and (not mazzieri or mazzieri[-1][0] != st.mano_n):
            mazzieri.append((st.mano_n, st.mazziere))
        s = required_actors(st)[0]
        a = [x for x in legal_actions(st, s) if x.tipo in ("gioca", "passa")][0]
        apply_inplace(st, a)
    assert st.mano_n == 4
    assert sorted(m for _, m in mazzieri) == [0, 1, 2, 3]
