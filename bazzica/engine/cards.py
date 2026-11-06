"""Carte piacentine: rappresentazione e utilità.

Una carta è una stringa nel formato ``{seme}_{valore:02d}`` (es. ``denari_07``),
la stessa convenzione dei nomi dei file immagine.
"""
from __future__ import annotations

SEMI = ("denari", "coppe", "spade", "bastoni")
VALORI = tuple(range(1, 11))

SETTE_BELLO = "denari_07"
RE_BELLO = "denari_10"
DUE_DENARI = "denari_02"

NOMI_VALORE = {
    1: "Asso", 2: "Due", 3: "Tre", 4: "Quattro", 5: "Cinque", 6: "Sei",
    7: "Sette", 8: "Fante", 9: "Cavallo", 10: "Re",
}

PRIMIERA = {7: 21, 6: 18, 1: 16, 5: 15, 4: 14, 3: 13, 2: 12, 8: 10, 9: 10, 10: 10}


def card(seme: str, valore: int) -> str:
    return f"{seme}_{valore:02d}"


MAZZO = tuple(card(s, v) for s in SEMI for v in VALORI)

_VAL = {c: int(c.split("_")[1]) for c in MAZZO}
_SEME = {c: c.split("_")[0] for c in MAZZO}


def val(c: str) -> int:
    return _VAL[c]


def seme(c: str) -> str:
    return _SEME[c]


def is_asso(c: str) -> bool:
    return _VAL[c] == 1


def nome(c: str) -> str:
    """Nome leggibile in italiano, es. 'Sette di denari'."""
    if c == SETTE_BELLO:
        return "Sette bello"
    if c == RE_BELLO:
        return "Re bello"
    return f"{NOMI_VALORE[_VAL[c]]} di {_SEME[c]}"


def nomi(cards) -> str:
    return ", ".join(nome(c) for c in cards) if cards else "nessuna"
