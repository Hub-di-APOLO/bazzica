import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest  # noqa: E402

from bazzica.engine import MAZZO, GameState, preset, Action  # noqa: E402
from bazzica.engine.prng import Mulberry32  # noqa: E402

_SEMI = {"D": "denari", "C": "coppe", "S": "spade", "B": "bastoni"}


def C(s: str) -> str:
    """'D7' -> 'denari_07', 'B10' -> 'bastoni_10'."""
    return f"{_SEMI[s[0]]}_{int(s[1:]):02d}"


def CC(*xs):
    return [C(x) for x in xs]


def make_state(rules=None, mani=None, tavola=(), turno=1, mazziere=3, corrente=None,
               prese=None, credito=(0, 0), mazzo=None, giocato=None, punteggi=(0, 0),
               mano_n=1, piccola_target=None, bazzica=None, fase="gioco"):
    rules = rules or preset("Vanilla")
    mani = mani or {}
    m = [CC(*mani.get(s, [])) for s in range(4)]
    tav = CC(*tavola)
    pr = [[], []]
    for t in (0, 1):
        for e in (prese[t] if prese else []):
            if isinstance(e, str):
                pr[t].append([C(e), False, None])
            else:
                pr[t].append([C(e[0]), e[1], e[2] if len(e) > 2 else ("sparecchio" if e[1] else None)])
    usate = set(sum(m, [])) | set(tav) | {e[0] for p in pr for e in p}
    if mazzo is None:
        mazzo = [c for c in MAZZO if c not in usate]
    else:
        mazzo = CC(*mazzo)
    st = GameState(rules=rules, seed=0, rng=Mulberry32(0), fase=fase, mazziere=mazziere,
                   primo_mazziere=mazziere, turno=turno, mano_n=mano_n, mazzo=mazzo, tavola=tav,
                   mani=m, distribuite=[list(x) for x in m], prese=pr, credito=list(credito),
                   corrente=(mazziere + 1) % 4 if corrente is None else corrente,
                   punteggi=list(punteggi), piccola_target=C(piccola_target) if piccola_target else None)
    if giocato:
        st.giocato_turno = list(giocato)
    if bazzica:
        st.bazzica = bazzica
    return st


def play(seat, carta, presa=()):
    return Action("gioca", seat, carta=C(carta), presa=tuple(CC(*presa)))


@pytest.fixture
def mk():
    return make_state
