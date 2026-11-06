"""Esecuzione di partite solo-bot (simulazioni)."""
from __future__ import annotations

from ..engine import (new_game, legal_actions, apply_inplace, observation, required_actors,
                      optional_actors, system_action, FASE_FINE_PARTITA)


def gioca_partita(rules, agents, seed=0, max_azioni=100000, on_events=None):
    """Gioca una partita completa con 4 agenti. Restituisce lo stato finale."""
    st, events = new_game(rules, seed=seed)
    if on_events:
        on_events(st, events)
    n = 0
    while st.fase != FASE_FINE_PARTITA:
        n += 1
        if n > max_azioni:
            raise RuntimeError("Troppe azioni: possibile stallo")
        sa = system_action(st)
        if sa:
            events = apply_inplace(st, sa)
            if on_events:
                on_events(st, events)
            continue
        attori = optional_actors(st) + required_actors(st)
        progress = False
        for s in attori:
            legal = legal_actions(st, s)
            if not legal:
                continue
            a = agents[s].choose_action(observation(st, s), legal)
            events = apply_inplace(st, a)
            if on_events:
                on_events(st, events)
            progress = True
            break
        if not progress:
            raise RuntimeError("Nessun giocatore può agire: stallo")
    return st
