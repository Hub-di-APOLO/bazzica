"""Punti di mazzo, Primiera, Scope, 2 di denari, Fermi, Napola."""
from conftest import C, CC
from bazzica.engine import riepilogo_mano, preset, MAZZO, primiera, napola


def P(cards, faceup=()):
    fu = set(CC(*faceup))
    return [[c, c in fu, "sparecchio" if c in fu else None] for c in cards]


def split(team0):
    a = set(team0)
    return [c for c in MAZZO if c in a], [c for c in MAZZO if c not in a]


def test_carte_pari_e_vinte():
    a, b = MAZZO[:20], MAZZO[20:]
    r = riepilogo_mano([P(a), P(b)], preset("Vanilla"))
    assert r["squadre"][0]["punti_mazzo_dettaglio"]["carte"] == 0
    assert r["squadre"][1]["punti_mazzo_dettaglio"]["carte"] == 0
    a, b = MAZZO[:21], MAZZO[21:]
    r = riepilogo_mano([P(a), P(b)], preset("Vanilla"))
    assert r["squadre"][0]["punti_mazzo_dettaglio"]["carte"] == 1


def test_denari_pari():
    den = CC("D1", "D2", "D3", "D4", "D5")
    a, b = split(den + CC("C1", "C2"))
    r = riepilogo_mano([P(a), P(b)], preset("Vanilla"))
    assert r["squadre"][0]["punti_mazzo_dettaglio"]["denari"] == 0
    assert r["squadre"][1]["punti_mazzo_dettaglio"]["denari"] == 0
    a, b = split(den + CC("D6"))
    r = riepilogo_mano([P(a), P(b)], preset("Vanilla"))
    assert r["squadre"][0]["punti_mazzo_dettaglio"]["denari"] == 1


def test_sette_bello_re_bello_e_due_denari():
    a, b = split(CC("D7", "D10", "D2"))
    r = riepilogo_mano([P(a), P(b)], preset("Vanilla"))
    s0 = r["squadre"][0]
    assert s0["punti_mazzo_dettaglio"]["sette_bello"] == 1
    assert s0["punti_mazzo_dettaglio"]["re_bello"] == 1
    assert s0["punti_due_denari"] == -5


def test_primiera_calcolo():
    pt, det, manc = primiera(CC("D7", "D6", "C1", "S5", "B10", "B2"))
    assert pt == 21 + 16 + 15 + 12 and manc == []
    assert det["bastoni"]["carta"] == C("B2")


def test_primiera_vinta_e_pari():
    # squadra 0 ha tutti i 7: vince la primiera
    a, b = split(CC("D7", "C7", "S7", "B7"))
    r = riepilogo_mano([P(a), P(b)], preset("Vanilla"))
    assert r["squadre"][0]["punti_mazzo_dettaglio"]["primiera"] == 1
    # primiera pari: stesse carte migliori per seme
    a = CC("D7", "C7", "S6", "B6")
    b = CC("S7", "B7", "D6", "C6")
    resto = [c for c in MAZZO if c not in a + b and int(c[-2:]) >= 8]
    r = riepilogo_mano([P(a + resto[:6]), P(b + resto[6:])], preset("Vanilla"))
    assert r["squadre"][0]["primiera"] == r["squadre"][1]["primiera"]
    assert r["squadre"][0]["punti_mazzo_dettaglio"]["primiera"] == 0
    assert r["squadre"][1]["punti_mazzo_dettaglio"]["primiera"] == 0


def test_primiera_seme_mancante_una_squadra():
    # squadra 0 ha tutte le spade: la squadra 1 manca di un seme -> primiera alla 0
    spade = [c for c in MAZZO if c.startswith("spade")]
    a, b = split(spade + CC("D10", "C10", "B10"))
    r = riepilogo_mano([P(a), P(b)], preset("Vanilla"))
    assert r["squadre"][1]["semi_mancanti"] == ["spade"]
    assert r["squadre"][0]["punti_mazzo_dettaglio"]["primiera"] == 1


def test_primiera_seme_mancante_entrambe():
    spade = [c for c in MAZZO if c.startswith("spade")]
    coppe = [c for c in MAZZO if c.startswith("coppe")]
    a, b = split(spade)
    b = [c for c in b if c not in coppe]
    a = a + coppe
    r = riepilogo_mano([P(a), P(b)], preset("Vanilla"))
    assert r["squadre"][0]["semi_mancanti"] and r["squadre"][1]["semi_mancanti"]
    assert r["squadre"][0]["punti_mazzo_dettaglio"]["primiera"] == 0
    assert r["squadre"][1]["punti_mazzo_dettaglio"]["primiera"] == 0


def test_scope_contano_e_totale_negativo():
    a, b = split(CC("D2", "C3"))
    r = riepilogo_mano([P(a, faceup=["C3"]), P(b)], preset("Vanilla"))
    s0 = r["squadre"][0]
    assert s0["scope"] == 1
    assert s0["totale"] == s0["punti_mazzo"] + 1 - 5
    assert s0["totale"] < 0


def test_fermi_due_denari_e_napoleone():
    den = [c for c in MAZZO if c.startswith("denari")]
    a, b = split(den)
    r = riepilogo_mano([P(a), P(b)], preset("Fermi"))
    s0 = r["squadre"][0]
    # denari, 7 bello, re bello (+ primiera? la 0 manca di 3 semi) -> 3 punti di mazzo
    assert s0["punti_mazzo"] == 3
    assert s0["punti_due_denari"] == -2
    assert s0["napola"] == 10 and s0["napola_nome"] == "Napoleone"
    # senza Fermi il Napoleone non esiste
    r = riepilogo_mano([P(a), P(b)], preset("Heisenberg"))
    assert r["squadre"][0]["napola"] == 0 and r["squadre"][0]["punti_due_denari"] == -5


def test_fermi_due_denari_non_conta_napola():
    a, b = split(CC("D1", "D2", "D3", "D4", "D5"))
    r = riepilogo_mano([P(a), P(b)], preset("Federico II"))
    s0 = r["squadre"][0]
    assert s0["napola"] == 5 and s0["napola_nome"] == "Napola al 5"
    assert s0["punti_due_denari"] == -5 + s0["punti_mazzo"]


def test_napola():
    assert napola(CC("D1", "D2")) == 0
    assert napola(CC("D1", "D2", "D3")) == 3
    assert napola(CC("D1", "D2", "D3", "D4", "D5", "D7")) == 5
    a, b = split(CC("D1", "D2", "D3"))
    r = riepilogo_mano([P(a), P(b)], preset("Fermi"))
    assert r["squadre"][0]["napola"] == 0  # Napola solo da Federico II


def test_napoleone_in_federico_vale_10_non_cumulato():
    den = [c for c in MAZZO if c.startswith("denari")]
    a, b = split(den)
    r = riepilogo_mano([P(a), P(b)], preset("Federico II"))
    assert r["squadre"][0]["napola"] == 10
