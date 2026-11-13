"""PRNG del gioco: mulberry32.

Usato per il primo mazziere, i mescolamenti e gli spareggi dei bot, così che una
partita sia riproducibile dal solo seed (il seed è scritto nel log di ogni partita).
Ogni operazione è su interi a 32 bit senza segno.
"""
from __future__ import annotations

import random as _random

MASK = 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    return (a * b) & MASK


class Mulberry32:
    def __init__(self, seed: int = 0):
        self.stato = int(seed) & MASK

    def next_u32(self) -> int:
        self.stato = (self.stato + 0x6D2B79F5) & MASK
        t = self.stato
        t = _imul(t ^ (t >> 15), t | 1)
        t ^= (t + _imul(t ^ (t >> 7), t | 61)) & MASK
        return (t ^ (t >> 14)) & MASK

    def random(self) -> float:
        """Numero in [0, 1) con 32 bit di risoluzione."""
        return self.next_u32() / 4294967296.0

    def randbelow(self, n: int) -> int:
        """Intero in [0, n) (moltiplicazione e shift, nessuna divisione in virgola mobile)."""
        if n <= 0:
            raise ValueError("n deve essere positivo")
        return (self.next_u32() * n) >> 32

    def shuffle(self, lista: list) -> None:
        """Fisher–Yates dall'ultimo elemento al secondo."""
        for i in range(len(lista) - 1, 0, -1):
            j = self.randbelow(i + 1)
            lista[i], lista[j] = lista[j], lista[i]

    def choice(self, seq):
        return seq[self.randbelow(len(seq))]

    def copia(self) -> "Mulberry32":
        r = Mulberry32()
        r.stato = self.stato
        return r


def seed_casuale() -> int:
    """Seed non deterministico (solo quando non ne viene fornito uno)."""
    return _random.SystemRandom().randrange(1 << 32)
