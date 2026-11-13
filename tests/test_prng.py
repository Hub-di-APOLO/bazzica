"""Vettori di riferimento del PRNG mulberry32 (stessi valori dell'implementazione JavaScript originale)."""
from bazzica.engine.prng import Mulberry32

VETTORI = {
    1: [2693262067, 11749833, 2265367787, 4213581821, 4159151403],
    0xDEADBEEF: [4043151706, 1147597007, 3315858022],
}


def test_vettori_next_u32():
    for seed, attesi in VETTORI.items():
        r = Mulberry32(seed)
        assert [r.next_u32() for _ in attesi] == attesi


def test_riferimento_javascript():
    # mulberry32(1)() in JavaScript restituisce 0.6270739405881613
    assert Mulberry32(1).random() == 0.6270739405881613


def test_shuffle_randbelow_random():
    r = Mulberry32(42)
    lista = list(range(10))
    r.shuffle(lista)
    assert lista == [0, 7, 3, 5, 2, 1, 8, 9, 4, 6]
    assert r.randbelow(40) == 18
    assert r.random() == 0.24992373422719538


def test_copia_indipendente():
    a = Mulberry32(7)
    a.next_u32()
    b = a.copia()
    assert a.next_u32() == b.next_u32()
