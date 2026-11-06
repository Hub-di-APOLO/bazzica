"""Valutazione delle Bazziche e del "Che Palo!"."""
from __future__ import annotations

from .cards import SETTE_BELLO, val
from .rules import RulesConfig

TRIS = "tris"
COPPIA = "coppia"
DIVERSE = "diverse"

NOMI_TIPO = {
    TRIS: "Tris",
    COPPIA: "Coppia con somma ≤ 9",
    DIVERSE: "Tre carte diverse con somma ≤ 9",
}


def valuta_valori(valori, rules: RulesConfig, con_sette_bello: bool):
    """Valuta una terna di valori. Restituisce (tipo, scope) della Bazzica più alta o None.

    ``con_sette_bello`` indica se la mano contiene il 7 bello (rilevante per Einstein:
    un tris che contiene il 7 bello vale 5 invece di 7).
    """
    if len(valori) != 3:
        return None
    a, b, c = valori
    somma = a + b + c
    distinti = len({a, b, c})
    if distinti == 1:
        return (TRIS, 5 if (rules.einstein and con_sette_bello) else 7)
    if distinti == 2 and somma <= 9:
        return (COPPIA, 3)
    if distinti == 3 and somma <= 9:
        return (DIVERSE, 2)
    return None


def opzioni_bazzica(mano, rules: RulesConfig):
    """Elenco delle Bazziche chiamabili con la mano (3 carte).

    Ogni opzione è un dict: {"sette": valore assegnato al 7 bello o None,
    "tipo": ..., "scope": ...}. Con il 7 bello si ha un'opzione per ogni valore
    (1..10) che produce una Bazzica valida.
    """
    if len(mano) != 3:
        return []
    out = []
    if SETTE_BELLO in mano:
        for v in range(1, 11):
            valori = [v if c == SETTE_BELLO else val(c) for c in mano]
            r = valuta_valori(valori, rules, True)
            if r:
                out.append({"sette": v, "tipo": r[0], "scope": r[1]})
    else:
        r = valuta_valori([val(c) for c in mano], rules, False)
        if r:
            out.append({"sette": None, "tipo": r[0], "scope": r[1]})
    return out


def puo_dire_che_palo(mano, rules: RulesConfig) -> bool:
    """Vero se la mano non contiene una Bazzica ma è a una carta di distanza da una Bazzica."""
    if len(mano) != 3 or opzioni_bazzica(mano, rules):
        return False
    for i in range(3):
        resto = [c for j, c in enumerate(mano) if j != i]
        ha_sette = SETTE_BELLO in resto
        for w in range(1, 11):
            if ha_sette:
                for v in range(1, 11):
                    valori = [v if c == SETTE_BELLO else val(c) for c in resto] + [w]
                    if valuta_valori(valori, rules, True):
                        return True
            else:
                if valuta_valori([val(c) for c in resto] + [w], rules, False):
                    return True
    return False


def descrivi_opzione(op) -> str:
    s = f"{NOMI_TIPO[op['tipo']]} — {op['scope']} Scope"
    if op.get("sette") is not None:
        s += f" (7 bello = {op['sette']})"
    return s
