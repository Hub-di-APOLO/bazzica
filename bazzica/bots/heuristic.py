"""Bot euristico: valuta prese, rischi di Scopa avversaria, Bazziche, scambio e segnali."""
from __future__ import annotations

from ..engine.prng import Mulberry32, seed_casuale
from math import comb

from ..engine import (Action, MAZZO, SETTE_BELLO, RE_BELLO, DUE_DENARI, val, seme, RulesConfig,
                      opzioni_bazzica, anteprima, stato_da_osservazione, puo_dire_che_palo)
from ..engine.game import opzioni_presa
from .base import Agent


def valore_carta(c: str, r: RulesConfig) -> float:
    """Valore indicativo (in punti) di avere ``c`` nel proprio mazzo delle prese."""
    if c == "?":
        return 0.06
    v = 0.06
    if seme(c) == "denari":
        v += 0.12
        if r.federico and val(c) <= 3:
            v += 0.25
    v += {7: 0.3, 6: 0.18, 1: 0.15, 5: 0.06}.get(val(c), 0)
    if c == SETTE_BELLO:
        v += 1.2
    elif c == RE_BELLO:
        v += 1.0
    elif c == DUE_DENARI:
        v -= 3.0 if r.fermi else 4.5
    return v


def p_almeno_uno(n_pool: int, k: int, n_mano: int) -> float:
    """Probabilità che una mano di ``n_mano`` carte estratte da ``n_pool`` ne contenga
    almeno una tra ``k`` specifiche."""
    if k <= 0 or n_mano <= 0 or n_pool <= 0:
        return 0.0
    n_mano = min(n_mano, n_pool)
    if n_pool - k < n_mano:
        return 1.0
    return 1.0 - comb(n_pool - k, n_mano) / comb(n_pool, n_mano)


def miglior_bazzica(cards, r: RulesConfig) -> int:
    ops = opzioni_bazzica(cards, r)
    return max((o["scope"] for o in ops), default=0)


class HeuristicAgent(Agent):
    nome = "Bot"

    def __init__(self, seed=None, ritardo=(0.8, 1.5)):
        self.rng = Mulberry32(seed_casuale() if seed is None else seed)
        self.ritardo = ritardo

    # ------------------------------------------------------------------ utilità
    def _ignote(self, obs) -> list:
        """Carte che potrebbero essere in mano agli altri o nel mazzo."""
        viste = set(obs["mano"]) | set(obs["tavola"]) | set(obs["carte_iniziali_tavola"])
        for s, c, presa in obs["giocate_mano"]:
            viste.add(c)
            viste.update(presa)
        for o in obs["altri"].values():
            if o["carte"]:
                viste.update(o["carte"])
        mia = obs["scambio"]["mia_passata"]
        if mia:
            viste.add(mia)
        return [c for c in MAZZO if c not in viste]

    def _rischio(self, obs, st, tavola_dopo, carta_lasciata, r: RulesConfig, ignote) -> float:
        """Rischio (in punti) che il prossimo avversario sfrutti il tavolo lasciato."""
        if not tavola_dopo:
            return 0.0
        opp = (obs["seat"] + 1) % 4
        o = obs["altri"][str(opp)]
        n_opp = o["n"]
        if n_opp <= 0:
            return 0.0
        rivelata = o["carte"]
        pascal_opp = r.pascal and str(opp) in obs["bazziche"]
        vincenti = set()
        valori_tavola = [val(c) for c in tavola_dopo]
        if 1 not in valori_tavola and not pascal_opp:
            vincenti.update(c for c in (rivelata or ignote) if val(c) == 1)
        if len(tavola_dopo) == 1:
            w = valori_tavola[0]
            vincenti.update(c for c in (rivelata or ignote) if val(c) == w)
        else:
            s = sum(valori_tavola)
            if s <= 10:
                vincenti.update(c for c in (rivelata or ignote) if val(c) == s)
        if rivelata is not None:
            p = 1.0 if vincenti else 0.0
        else:
            p = p_almeno_uno(len(ignote), len(vincenti), n_opp)
        rischio = p * (1.0 + sum(max(valore_carta(c, r), 0) for c in tavola_dopo))
        # Piccola avversaria sulla carta appena lasciata
        if r.curie and carta_lasciata is not None:
            w = val(carta_lasciata)
            k = [c for c in (rivelata or ignote) if val(c) == w]
            pp = (1.0 if k else 0.0) if rivelata is not None else p_almeno_uno(len(ignote), len(k), n_opp)
            rischio += 0.6 * pp
        # Il prossimo avversario prenderà comunque qualcosa: perdita attesa delle carte di valore
        presa_gen = 0.35 * sum(max(valore_carta(c, r), 0) for c in tavola_dopo)
        return rischio + presa_gen * 0.5

    def valuta_giocata(self, obs, st, a: Action, ignote) -> float:
        r = st.rules
        pre = anteprima(st, a)
        gain = 0.0
        if a.presa:
            for c in [a.carta, *a.presa]:
                gain += valore_carta(c, r)
            gain += pre["scoperte"]
            tavola_dopo = [c for c in st.tavola if c not in a.presa]
            lasciata = None
        else:
            gain -= 0.5 * valore_carta(a.carta, r)
            tavola_dopo = st.tavola + [a.carta]
            lasciata = a.carta
        if not pre["ultima_giocata"]:
            gain -= self._rischio(obs, st, tavola_dopo, lasciata, r, ignote)
        # conservare l'asso (piglia tutto) per dopo, se non serve ora
        if not a.presa and val(a.carta) == 1:
            gain -= 0.4
        return gain

    def _miglior_giocata(self, obs, st, gioc, ignote):
        best, best_v = None, -1e9
        for a in gioc:
            v = self.valuta_giocata(obs, st, a, ignote) + self.rng.random() * 1e-3
            if v > best_v:
                best, best_v = a, v
        return best, best_v

    # ------------------------------------------------------------------ scelta
    def choose_action(self, obs, legal):
        tipi = {a.tipo for a in legal}
        if "che_palo" in tipi and self._vuole_palo(obs):
            return next(a for a in legal if a.tipo == "che_palo")
        if "passa" in tipi:
            return self._scambio(obs, legal)
        if "gioca" not in tipi:
            # azione facoltativa fuori turno: niente da fare
            return next((a for a in legal if a.tipo == "attendi"), legal[0])
        st = stato_da_osservazione(obs)
        ignote = self._ignote(obs)
        gioc = [a for a in legal if a.tipo == "gioca"]
        baz = [a for a in legal if a.tipo == "bazzica"]
        if baz:
            return self._scegli_bazzica(obs, st, baz, gioc, ignote)
        return self._miglior_giocata(obs, st, gioc, ignote)[0]

    def _vuole_palo(self, obs) -> bool:
        """Il bot esclama una sola volta per Turno, prima della sua prima carta, quando la
        mano è davvero a una carta da una Bazzica."""
        s = obs["seat"]
        if obs["fase"] != "gioco" or s in obs["che_palo"] or obs["giocato_turno"][s]:
            return False
        if str(s) in obs["bazziche"]:
            return False
        r = RulesConfig.from_dict(obs["regole"])
        return puo_dire_che_palo(obs["mano"], r) and self._palo_significativo(obs["mano"])

    @staticmethod
    def _palo_significativo(mano) -> bool:
        """Il bot esclama solo per i "pali" veri: una coppia (manca il tris) o il 7 bello."""
        valori = [val(c) for c in mano]
        return len(set(valori)) < len(valori) or SETTE_BELLO in mano

    def _scegli_bazzica(self, obs, st, baz, gioc, ignote):
        r = st.rules
        ops = {o["sette"]: o for o in opzioni_bazzica(st.mani[obs["seat"]], r)}
        _, v_senza = self._miglior_giocata(obs, st, gioc, ignote)
        best, best_v = None, v_senza
        for a in baz:
            op = ops[a.sette]
            st2 = stato_da_osservazione(obs)
            st2.bazzica[obs["seat"]] = {"tipo": op["tipo"], "scope": op["scope"], "sette": op["sette"],
                                        "carte": list(obs["mano"])}
            gioc2 = self._giocate(st2, obs["seat"])
            _, v = self._miglior_giocata(obs, st2, gioc2, ignote)
            tot = op["scope"] + v
            if tot > best_v:
                best, best_v = a, tot
        if best is not None:
            return best
        return self._miglior_giocata(obs, st, gioc, ignote)[0]

    @staticmethod
    def _giocate(st, seat):
        return [Action("gioca", seat, carta=c, presa=tuple(p))
                for c in st.mani[seat] for p in opzioni_presa(st, seat, c)]

    # ------------------------------------------------------------------ scambio
    def _attesa_bazzica(self, kept, r, ignote) -> float:
        """Scope attese della Bazzica con le carte tenute più una carta ignota dal compagno."""
        if len(kept) >= 3:
            return float(miglior_bazzica(kept[:3], r))
        if not ignote:
            return 0.0
        tot = 0.0
        for c in ignote:
            tot += miglior_bazzica(kept + [c], r)
        return tot / len(ignote)

    def _scambio(self, obs, legal):
        r = RulesConfig.from_dict(obs["regole"])
        sc = obs["scambio"]
        p = obs["compagno"]
        mano = list(obs["mano"])
        ricevuta = sc["ricevuta"]
        compagno_passato = sc["passati"][p]
        compagno_veloce = sc["veloci"][p]
        candidati = sorted({a.carta for a in legal if a.tipo == "passa"})
        ignote = self._ignote(obs)
        dealt = [c for c in sc["distribuite"] if c in mano]

        # Se ho già una coppia/tris interessante e il compagno non ha passato, segnalo subito
        valori = [val(c) for c in dealt]
        coppia = [v for v in set(valori) if valori.count(v) >= 2]
        if not compagno_passato:
            if coppia and SETTE_BELLO not in dealt and miglior_bazzica(dealt, r) < 7:
                v = coppia[0]
                altra = [c for c in dealt if val(c) != v]
                if altra:
                    return Action("passa", obs["seat"], carta=altra[0], veloce=True)
            if any(a.tipo == "attendi" for a in legal) and miglior_bazzica(dealt, r) < 7:
                return next(a for a in legal if a.tipo == "attendi")

        best, best_v = None, -1e9
        for c in candidati:
            kept = [x for x in mano if x != c]
            if ricevuta is None and not compagno_passato:
                v = self._attesa_bazzica(kept, r, ignote)
            else:
                v = float(miglior_bazzica(kept, r)) if len(kept) == 3 else self._attesa_bazzica(kept, r, ignote)
            # valore per il compagno
            if compagno_veloce:
                if c == SETTE_BELLO:
                    v += 3.0
                v += (10 - val(c)) * 0.08
            else:
                v += (10 - val(c)) * 0.03
                if c == SETTE_BELLO:
                    v += 0.2
            v += self.rng.random() * 1e-3
            if v > best_v:
                best, best_v = c, v
        return Action("passa", obs["seat"], carta=best, veloce=False)
