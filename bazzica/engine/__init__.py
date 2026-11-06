"""Motore puro delle regole della Bazzica (nessun I/O, nessuna rete)."""
from .cards import MAZZO, SEMI, SETTE_BELLO, RE_BELLO, DUE_DENARI, card, val, seme, nome, nomi
from .rules import RulesConfig, preset, VARIANTI, with_flags
from .game import (
    Action, GameState, IllegalAction, new_game, legal_actions, apply, apply_inplace,
    observation, required_actors, optional_actors, system_action, opzioni_presa, anteprima,
    stato_da_osservazione, e_ultima_giocata, risolvi_giocata,
    squadra, compagno, NOMI_POSTI, NOMI_SQUADRE,
    FASE_SCAMBIO, FASE_GIOCO, FASE_FINE_MANO, FASE_FINE_PARTITA,
)
from .bazzica import opzioni_bazzica, puo_dire_che_palo, valuta_valori, descrivi_opzione
from .scoring import riepilogo_mano, primiera, napola
