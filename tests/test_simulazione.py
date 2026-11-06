"""Simulazione: migliaia di partite solo-bot con verifica degli invarianti."""
import os

import pytest

from bazzica.bots import HeuristicAgent, RandomAgent
from bazzica.bots.runner import gioca_partita
from bazzica.engine import preset, VARIANTI, MAZZO, observation

N_PER_VARIANTE = int(os.environ.get("BAZZICA_SIM", "250"))


def controlla_invarianti(st, events):
    tutte = list(st.mazzo) + list(st.tavola) + [c for m in st.mani for c in m] + \
        [e[0] for p in st.prese for e in p] + \
        [st.scambio_passata[x] for x in range(4)                 # carte "in viaggio" nello scambio
         if st.fase == "scambio" and st.scambio_passata[x] and st.scambio_ricevuta[(x + 2) % 4] is None]
    assert len(tutte) == 40, f"carte non conservate: {len(tutte)}"
    assert sorted(tutte) == sorted(MAZZO), "carte duplicate o mancanti"
    assert st.credito[0] >= 0 and st.credito[1] >= 0
    for e in events:
        if e["tipo"] == "fine_mano":
            rie = e["riepilogo"]
            for t in (0, 1):
                faceup = sum(1 for x in st.prese[t] if x[1])
                assert rie["squadre"][t]["scope"] == faceup
                s = rie["squadre"][t]
                assert s["totale"] == s["punti_mazzo"] + s["scope"] + s["punti_due_denari"] + s["napola"]
            pm = [rie["squadre"][t]["punti_mazzo"] for t in (0, 1)]
            assert sum(pm) <= 5
        if e["tipo"] == "giocata" and e["presa"]:
            assert len(e["girate"]) >= (1 if (e["scopa"] or e["piccola"]) else 0)
    # sicurezza informativa: nessuna osservazione contiene mani altrui coperte
    for s in range(4):
        o = observation(st, s)
        for k, a in o["altri"].items():
            if st.bazzica[int(k)] is None:
                assert a["carte"] is None


@pytest.mark.parametrize("variante", VARIANTI)
def test_simulazione_solo_bot(variante):
    for i in range(N_PER_VARIANTE):
        seed = 1000 * VARIANTI.index(variante) + i
        rules = preset(variante, margherita_hack=(i % 5 == 0))
        if i % 3 == 0:
            agents = [RandomAgent(seed + k) for k in range(4)]
        else:
            agents = [HeuristicAgent(seed + k) for k in range(4)]
        st = gioca_partita(rules, agents, seed=seed, on_events=controlla_invarianti)
        assert st.fase == "fine_partita"
        if rules.margherita_hack:
            assert st.mano_n == 4
        else:
            a, b = st.punteggi
            assert a != b and max(a, b) >= 21
            assert st.vincitore == (0 if a > b else 1)
        assert sum(r["totali"][0] for r in st.storico_mani) == st.punteggi[0]
