"""Interfaccia comune degli agenti (bot euristici oggi, bot LLM domani).

Un agente riceve esattamente l'``observation`` che riceverebbe un umano seduto in quel
posto (dict JSON-serializzabile) e l'elenco delle azioni legali, e restituisce una di esse.
Per un agente LLM sono disponibili ``testo_osservazione`` e ``Action.descrivi()``.
"""
from __future__ import annotations

from ..engine.prng import Mulberry32, seed_casuale
from abc import ABC, abstractmethod

from ..engine import Action, nome, nomi, NOMI_POSTI, NOMI_SQUADRE


class Agent(ABC):
    nome: str = "Agente"

    @abstractmethod
    def choose_action(self, observation: dict, legal_actions: list[Action]) -> Action:
        ...


class RandomAgent(Agent):
    nome = "Casuale"

    def __init__(self, seed=None):
        self.rng = Mulberry32(seed_casuale() if seed is None else seed)

    def choose_action(self, observation, legal_actions):
        scelte = [a for a in legal_actions if a.tipo not in ("attendi", "che_palo")] or legal_actions
        return self.rng.choice(scelte)


def testo_osservazione(obs: dict) -> str:
    """Descrizione testuale (italiano) dell'osservazione, utile per un bot LLM."""
    s = obs["seat"]
    righe = [
        f"Sei {NOMI_POSTI[s]} (squadra {NOMI_SQUADRE[obs['squadra']]}), compagno: {NOMI_POSTI[obs['compagno']]}.",
        f"Variante: {obs['regole']['nome_variante']}. Mano {obs['mano_n']}, Turno {obs['turno']}, "
        f"mazziere {NOMI_POSTI[obs['mazziere']]}, tocca a {NOMI_POSTI[obs['corrente']]}.",
        f"Punteggio partita: {NOMI_SQUADRE[0]} {obs['punteggi'][0]}, {NOMI_SQUADRE[1]} {obs['punteggi'][1]}.",
        f"La tua mano: {nomi(obs['mano'])}.",
        f"In tavola: {nomi(obs['tavola'])}.",
    ]
    for k, o in obs["altri"].items():
        if o["carte"] is not None:
            righe.append(f"Mano scoperta di {NOMI_POSTI[int(k)]}: {nomi(o['carte'])}.")
        else:
            righe.append(f"{NOMI_POSTI[int(k)]} ha {o['n']} carte coperte.")
    for t in (0, 1):
        p = obs["prese"][t]
        righe.append(f"Prese {NOMI_SQUADRE[t]}: {p['n']} carte, Scope (a faccia in su): {len(p['scoperte'])}, "
                     f"credito di Bazzica: {obs['credito'][t]}.")
    for k, b in obs["bazziche"].items():
        righe.append(f"{NOMI_POSTI[int(k)]} ha chiamato Bazzica ({b['tipo']}, {b['scope']} Scope).")
    if obs["che_palo"]:
        righe.append("Hanno esclamato \"Che Palo!\": " + ", ".join(NOMI_POSTI[x] for x in obs["che_palo"]) + ".")
    sc = obs["scambio"]
    if sc["ricevuta"]:
        righe.append(f"Hai ricevuto dal compagno: {nome(sc['ricevuta'])}.")
    for x, v in enumerate(sc["veloci"]):
        if v:
            righe.append(f"{NOMI_POSTI[x]} ha passato veloce.")
    return "\n".join(righe)
