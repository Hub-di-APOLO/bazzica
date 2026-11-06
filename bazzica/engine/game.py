"""Macchina a stati deterministica della Bazzica.

API principale:
    new_game(rules, seed, mazziere=None) -> (GameState, eventi)
    legal_actions(state, seat) -> [Action]
    apply(state, action) -> (nuovo_stato, eventi)     (copia)
    apply_inplace(state, action) -> eventi            (modifica lo stato)
    observation(state, seat) -> dict JSON con le sole informazioni visibili a ``seat``

Posti: 0=Nord, 1=Est, 2=Sud, 3=Ovest. Squadra = posto % 2 (0 = Nord e Sud, 1 = Est e Ovest).
Il gioco procede in senso orario: dopo il posto ``s`` gioca ``(s+1) % 4``.
"""
from __future__ import annotations

from .prng import Mulberry32
from dataclasses import dataclass, field
from typing import Optional

from .cards import MAZZO, SETTE_BELLO, val, seme, is_asso, nome, nomi
from .rules import RulesConfig
from .bazzica import opzioni_bazzica, puo_dire_che_palo, descrivi_opzione
from .scoring import riepilogo_mano

NOMI_POSTI = ("Nord", "Est", "Sud", "Ovest")
NOMI_SQUADRE = ("Squadra 1", "Squadra 2")  # nomi predefiniti; il tavolo può personalizzarli

FASE_SCAMBIO = "scambio"
FASE_GIOCO = "gioco"
FASE_FINE_MANO = "fine_mano"
FASE_FINE_PARTITA = "fine_partita"


def squadra(seat: int) -> int:
    return seat % 2


def compagno(seat: int) -> int:
    return (seat + 2) % 4


class IllegalAction(Exception):
    pass


# --------------------------------------------------------------------------- Azioni

@dataclass(frozen=True)
class Action:
    """Azione di un giocatore (o di sistema per ``nuova_mano``).

    tipo: 'gioca' | 'bazzica' | 'che_palo' | 'passa' | 'attendi' | 'nuova_mano'
    """
    tipo: str
    seat: Optional[int] = None
    carta: Optional[str] = None
    presa: tuple = ()
    sette: Optional[int] = None
    veloce: bool = False

    def key(self):
        return (self.tipo, self.seat, self.carta, tuple(sorted(self.presa)), self.sette, self.veloce)

    def to_dict(self) -> dict:
        return {"tipo": self.tipo, "seat": self.seat, "carta": self.carta,
                "presa": list(self.presa), "sette": self.sette, "veloce": self.veloce}

    @staticmethod
    def from_dict(d: dict) -> "Action":
        return Action(tipo=d["tipo"], seat=d.get("seat"), carta=d.get("carta"),
                      presa=tuple(d.get("presa") or ()), sette=d.get("sette"),
                      veloce=bool(d.get("veloce", False)))

    def descrivi(self) -> str:
        if self.tipo == "gioca":
            if self.presa:
                return f"Gioca {nome(self.carta)} prendendo {nomi(self.presa)}"
            return f"Gioca {nome(self.carta)} (resta in tavola)"
        if self.tipo == "bazzica":
            s = "Chiama Bazzica"
            if self.sette is not None:
                s += f" con il 7 bello che vale {self.sette}"
            return s
        if self.tipo == "che_palo":
            return "Esclama \"Che Palo!\""
        if self.tipo == "passa":
            return f"Passa {nome(self.carta)} al compagno" + (" (veloce)" if self.veloce else "")
        if self.tipo == "attendi":
            return "Attendi (non fare nulla per ora)"
        if self.tipo == "nuova_mano":
            return "Inizia la Mano successiva"
        return self.tipo


def ev(tipo: str, visibile=None, **data) -> dict:
    """Evento serializzabile. ``visibile``: None = tutti, altrimenti lista di posti."""
    d = {"tipo": tipo, **data}
    d["visibile"] = list(visibile) if visibile is not None else None
    return d


# --------------------------------------------------------------------------- Stato

@dataclass
class GameState:
    rules: RulesConfig
    seed: int
    rng: Mulberry32
    fase: str = FASE_GIOCO
    punteggi: list = field(default_factory=lambda: [0, 0])
    mano_n: int = 0
    mazziere: int = 0
    primo_mazziere: int = 0
    turno: int = 0
    mazzo: list = field(default_factory=list)
    tavola: list = field(default_factory=list)
    mani: list = field(default_factory=lambda: [[], [], [], []])
    distribuite: list = field(default_factory=lambda: [[], [], [], []])
    # prese[t] = lista di [carta, faccia_in_su, origine]
    prese: list = field(default_factory=lambda: [[], []])
    credito: list = field(default_factory=lambda: [0, 0])
    corrente: int = 0
    giocato_turno: list = field(default_factory=lambda: [False] * 4)
    bazzica: list = field(default_factory=lambda: [None] * 4)
    che_palo: list = field(default_factory=lambda: [False] * 4)
    palo_considerato: list = field(default_factory=lambda: [False] * 4)
    scambio_passata: list = field(default_factory=lambda: [None] * 4)
    scambio_ricevuta: list = field(default_factory=lambda: [None] * 4)
    scambio_veloce: list = field(default_factory=lambda: [False] * 4)
    scambio_attesa: list = field(default_factory=lambda: [False] * 4)
    piccola_target: Optional[str] = None
    ultima_presa_squadra: Optional[int] = None
    giocate_mano: list = field(default_factory=list)
    storico_mani: list = field(default_factory=list)
    vincitore: object = None  # 0, 1, 'pari' o None
    carte_iniziali_tavola: list = field(default_factory=list)

    def copy(self) -> "GameState":
        return GameState(
            rules=self.rules, seed=self.seed, rng=self.rng.copia(), fase=self.fase,
            punteggi=list(self.punteggi), mano_n=self.mano_n, mazziere=self.mazziere,
            primo_mazziere=self.primo_mazziere, turno=self.turno, mazzo=list(self.mazzo),
            tavola=list(self.tavola), mani=[list(m) for m in self.mani],
            distribuite=[list(m) for m in self.distribuite],
            prese=[[list(e) for e in p] for p in self.prese], credito=list(self.credito),
            corrente=self.corrente, giocato_turno=list(self.giocato_turno),
            bazzica=[dict(b) if b else None for b in self.bazzica],
            che_palo=list(self.che_palo), palo_considerato=list(self.palo_considerato),
            scambio_passata=list(self.scambio_passata), scambio_ricevuta=list(self.scambio_ricevuta),
            scambio_veloce=list(self.scambio_veloce), scambio_attesa=list(self.scambio_attesa),
            piccola_target=self.piccola_target, ultima_presa_squadra=self.ultima_presa_squadra,
            giocate_mano=[list(g) for g in self.giocate_mano],
            storico_mani=list(self.storico_mani), vincitore=self.vincitore,
            carte_iniziali_tavola=list(self.carte_iniziali_tavola),
        )


# --------------------------------------------------------------------------- Avvio

def new_game(rules: RulesConfig, seed: int = 0, mazziere: Optional[int] = None):
    rng = Mulberry32(seed)
    if mazziere is None:
        mazziere = rng.randbelow(4)
    st = GameState(rules=rules, seed=seed, rng=rng, mazziere=mazziere, primo_mazziere=mazziere)
    events = [ev("inizio_partita", variante=rules.descrizione(), mazziere=mazziere)]
    events += _inizia_mano(st)
    return st, events


def _inizia_mano(st: GameState):
    st.mano_n += 1
    st.mazzo = list(MAZZO)
    st.rng.shuffle(st.mazzo)
    st.tavola = []
    st.mani = [[], [], [], []]
    st.prese = [[], []]
    st.credito = [0, 0]
    st.turno = 0
    st.ultima_presa_squadra = None
    st.giocate_mano = []
    st.fase = FASE_GIOCO
    events = [ev("nuova_mano", mano=st.mano_n, mazziere=st.mazziere)]
    st.tavola = [st.mazzo.pop() for _ in range(4)]
    st.carte_iniziali_tavola = list(st.tavola)
    events += _inizia_turno(st)
    return events


def _inizia_turno(st: GameState):
    st.turno += 1
    st.giocato_turno = [False] * 4
    st.bazzica = [None] * 4
    st.che_palo = [False] * 4
    st.palo_considerato = [False] * 4
    st.scambio_passata = [None] * 4
    st.scambio_ricevuta = [None] * 4
    st.scambio_veloce = [False] * 4
    st.scambio_attesa = [False] * 4
    st.piccola_target = None
    primo = (st.mazziere + 1) % 4
    events = []
    for i in range(4):
        s = (primo + i) % 4
        carte = [st.mazzo.pop() for _ in range(3)]
        st.mani[s] = carte
        st.distribuite[s] = list(carte)
        events.append(ev("carte_ricevute", visibile=[s], seat=s, carte=list(carte)))
    events.insert(0, ev("distribuzione", mano=st.mano_n, turno=st.turno, mazziere=st.mazziere,
                        tavola=list(st.tavola), carte_per_giocatore=3))
    st.corrente = primo
    if st.rules.scambio:
        st.fase = FASE_SCAMBIO
        events.append(ev("inizio_scambio", turno=st.turno))
    else:
        st.fase = FASE_GIOCO
        events.append(ev("inizio_giocate", turno=st.turno, corrente=st.corrente))
    return events


# --------------------------------------------------------------------------- Prese

def valore_effettivo(st: GameState, seat: int, carta: str) -> int:
    b = st.bazzica[seat]
    if carta == SETTE_BELLO and b and b.get("sette") is not None:
        return b["sette"]
    return val(carta)


def asso_piglia_tutto(st: GameState, seat: int, carta: str) -> bool:
    """L'asso piglia tutto, salvo (Pascal) se il giocatore ha chiamato Bazzica nel Turno.
    Il 7 bello a cui è assegnato 1 non piglia mai tutto."""
    if not is_asso(carta):
        return False
    if st.rules.pascal and st.bazzica[seat] is not None:
        return False
    return True


def _combinazioni(tavola, target):
    """Tutti i sottoinsiemi di almeno 2 carte con somma ``target``."""
    items = sorted(tavola, key=val)
    out = []

    def rec(i, rem, acc):
        if rem == 0:
            if len(acc) >= 2:
                out.append(tuple(acc))
            return
        for j in range(i, len(items)):
            v = val(items[j])
            if v > rem:
                break
            acc.append(items[j])
            rec(j + 1, rem - v, acc)
            acc.pop()

    rec(0, target, [])
    return out


def opzioni_presa(st: GameState, seat: int, carta: str):
    """Elenco delle prese possibili per ``carta``. ``[()]`` se la carta resta in tavola."""
    tav = st.tavola
    if not tav:
        return [()]
    if asso_piglia_tutto(st, seat, carta):
        assi = [c for c in tav if is_asso(c)]
        if assi:
            return [(a,) for a in assi]
        return [tuple(tav)]
    v = valore_effettivo(st, seat, carta)
    singole = [c for c in tav if val(c) == v]
    if singole:
        return [(c,) for c in singole]
    combo = _combinazioni(tav, v)
    if combo:
        return combo
    return [()]


# --------------------------------------------------------------------------- Azioni legali

def _puo_palo(st: GameState, seat: int) -> bool:
    """Vero se l'esclamazione "Che Palo!" è *sensata* (mano a una carta da una Bazzica,
    prima della propria prima carta, non ancora esclamata). Usata per proporla ai bot:
    i giocatori possono comunque premere il pulsante quando vogliono."""
    return (st.fase == FASE_GIOCO and not st.giocato_turno[seat] and not st.che_palo[seat]
            and st.bazzica[seat] is None and puo_dire_che_palo(st.mani[seat], st.rules))


def legal_actions(st: GameState, seat: int):
    """Azioni legali per ``seat``. "Che Palo!" è sempre disponibile durante scambio e giocate."""
    if st.fase == FASE_SCAMBIO:
        acts = [Action("che_palo", seat)]
        if st.scambio_passata[seat] is not None:
            return acts
        for c in st.distribuite[seat]:
            if c in st.mani[seat] and c != st.scambio_ricevuta[seat]:
                acts.append(Action("passa", seat, carta=c, veloce=False))
                acts.append(Action("passa", seat, carta=c, veloce=True))
        p = compagno(seat)
        if (st.scambio_passata[p] is None and not st.scambio_attesa[p]
                and not st.scambio_attesa[seat]):
            acts.append(Action("attendi", seat))
        return acts
    if st.fase != FASE_GIOCO:
        return []
    acts = [Action("che_palo", seat)]
    if seat == st.corrente:
        if not st.giocato_turno[seat] and st.bazzica[seat] is None:
            for op in opzioni_bazzica(st.mani[seat], st.rules):
                acts.append(Action("bazzica", seat, sette=op["sette"]))
        for c in st.mani[seat]:
            for presa in opzioni_presa(st, seat, c):
                acts.append(Action("gioca", seat, carta=c, presa=tuple(presa)))
    elif not st.palo_considerato[seat] and _puo_palo(st, seat):
        acts.append(Action("attendi", seat))
    return acts


def palo_sensato(st: GameState, seat: int) -> bool:
    return _puo_palo(st, seat)


def required_actors(st: GameState):
    """Posti che devono agire perché la partita prosegua."""
    if st.fase == FASE_SCAMBIO:
        return [s for s in range(4) if st.scambio_passata[s] is None]
    if st.fase == FASE_GIOCO:
        return [st.corrente]
    return []


def optional_actors(st: GameState):
    """Posti fuori turno a cui proporre (una volta) il "Che Palo!" quando è sensato (per i bot)."""
    if st.fase != FASE_GIOCO:
        return []
    return [s for s in range(4) if s != st.corrente and not st.palo_considerato[s] and _puo_palo(st, s)]


def system_action(st: GameState):
    if st.fase == FASE_FINE_MANO:
        return Action("nuova_mano")
    return None


# --------------------------------------------------------------------------- Apply

def apply(st: GameState, action: Action, validate: bool = True):
    nuovo = st.copy()
    events = apply_inplace(nuovo, action, validate)
    return nuovo, events


def apply_inplace(st: GameState, a: Action, validate: bool = True):
    if a.tipo == "nuova_mano":
        if st.fase != FASE_FINE_MANO:
            raise IllegalAction("La Mano non è terminata")
        st.mazziere = (st.mazziere + 1) % 4
        return _inizia_mano(st)
    if validate:
        k = a.key()
        if not any(x.key() == k for x in legal_actions(st, a.seat)):
            raise IllegalAction(f"Azione non valida: {a}")
    if a.tipo == "passa":
        return _passa(st, a)
    if a.tipo == "attendi":
        if st.fase == FASE_SCAMBIO:
            st.scambio_attesa[a.seat] = True
        else:
            st.palo_considerato[a.seat] = True
        return []
    if a.tipo == "che_palo":
        st.che_palo[a.seat] = True
        st.palo_considerato[a.seat] = True
        return [ev("che_palo", seat=a.seat)]
    if a.tipo == "bazzica":
        return _bazzica(st, a)
    if a.tipo == "gioca":
        return _gioca(st, a)
    raise IllegalAction(f"Tipo di azione sconosciuto: {a.tipo}")


def _passa(st: GameState, a: Action):
    """Lo scambio è segreto: la carta passata resta "in viaggio" e arriva al compagno
    solo quando anche lui ha passato la sua."""
    s, p = a.seat, compagno(a.seat)
    st.mani[s].remove(a.carta)
    st.scambio_passata[s] = a.carta
    st.scambio_veloce[s] = a.veloce
    st.scambio_attesa[s] = False
    events = [
        ev("scambio_carta", visibile=[s], seat=s, a=p, carta=a.carta, veloce=a.veloce),
        ev("scambio", seat=s, a=p, veloce=a.veloce),
    ]
    if st.scambio_passata[p] is not None:
        for x in (s, p):
            c = st.scambio_passata[compagno(x)]
            st.mani[x].append(c)
            st.scambio_ricevuta[x] = c
            events.append(ev("scambio_ricevuta", visibile=[x], seat=x, da=compagno(x), carta=c))
        events.append(ev("scambio_completato", squadra=squadra(s)))
    if all(x is not None for x in st.scambio_passata):
        st.fase = FASE_GIOCO
        st.corrente = (st.mazziere + 1) % 4
        events.append(ev("fine_scambio", turno=st.turno))
        events.append(ev("inizio_giocate", turno=st.turno, corrente=st.corrente))
    return events


def _gira(st: GameState, t: int, n: int, origine: str):
    """Gira a faccia in su fino a ``n`` carte coperte del mazzo delle prese; restituisce quante."""
    girate = 0
    for e in reversed(st.prese[t]):
        if girate >= n:
            break
        if not e[1]:
            e[1] = True
            e[2] = origine
            girate += 1
    return girate


def _bazzica(st: GameState, a: Action):
    s = a.seat
    ops = opzioni_bazzica(st.mani[s], st.rules)
    op = next(o for o in ops if o["sette"] == a.sette)
    t = squadra(s)
    st.bazzica[s] = {"tipo": op["tipo"], "scope": op["scope"], "sette": op["sette"],
                     "carte": list(st.mani[s])}
    girate = _gira(st, t, op["scope"], "bazzica")
    st.credito[t] += op["scope"] - girate
    return [ev("bazzica", seat=s, carte=list(st.mani[s]), tipo_bazzica=op["tipo"], scope=op["scope"],
               sette=op["sette"], girate=girate, credito=st.credito[t], squadra=t,
               descrizione=descrivi_opzione(op))]


def risolvi_giocata(st: GameState, s: int, c: str, presa, ultima: bool):
    """Calcola (senza modificare lo stato) l'esito di una giocata con presa.

    Restituisce (entrate, flags, credito_residuo) dove ``entrate`` sono le carte che
    finiscono nel mazzo delle prese come [carta, faccia_in_su, origine].
    """
    t = squadra(s)
    presa = list(presa)
    v_eff = valore_effettivo(st, s, c)
    flags = {"scopa": False, "piccola": False, "grande": False, "assi": [], "credito_pagato": 0,
             "sparecchio": False}
    if not presa:
        return [], flags, st.credito[t]
    resto = list(st.tavola)
    for x in presa:
        resto.remove(x)
    sparecchio = len(resto) == 0
    flags["sparecchio"] = sparecchio
    entrate = [[c, False, None]] + [[x, False, None] for x in presa]
    if not ultima:
        r = st.rules
        stesso_seme = len({seme(e[0]) for e in entrate}) == 1
        asso_bazzica = is_asso(c) and st.bazzica[s] is not None
        grande = r.curie and stesso_seme and not asso_bazzica
        piccola = (r.curie and not grande and st.piccola_target is not None
                   and presa == [st.piccola_target] and val(st.piccola_target) == v_eff)
        if grande:
            for e in entrate:
                e[1], e[2] = True, "grande"
            flags["grande"] = True
        elif piccola:
            entrate[0][1], entrate[0][2] = True, "piccola"
            flags["piccola"] = True
        elif sparecchio:
            entrate[0][1], entrate[0][2] = True, "sparecchio"
            flags["scopa"] = True
        if r.avogadro:
            for e in entrate:
                if is_asso(e[0]) and not e[1]:
                    e[1], e[2] = True, "asso"
                    flags["assi"].append(e[0])
    credito = st.credito[t]
    pagato = 0
    for e in entrate:
        if credito > 0 and not e[1]:
            e[1], e[2] = True, "bazzica"
            credito -= 1
            pagato += 1
    flags["credito_pagato"] = pagato
    return entrate, flags, credito


def _gioca(st: GameState, a: Action):
    s, c = a.seat, a.carta
    t = squadra(s)
    presa = list(a.presa)
    v_eff = valore_effettivo(st, s, c)
    st.mani[s].remove(c)
    st.giocato_turno[s] = True
    ultima = st.turno == 3 and all(len(m) == 0 for m in st.mani)
    events = []
    info = {"seat": s, "carta": c, "valore": v_eff, "presa": presa, "squadra": t,
            "scopa": False, "piccola": False, "grande": False, "assi": [],
            "girate": [], "credito_pagato": 0, "ultima_giocata": ultima, "sparecchio": False}
    if not presa:
        st.tavola.append(c)
        st.piccola_target = c
        st.giocate_mano.append([s, c, []])
        info["tavola"] = list(st.tavola)
        events.append(ev("giocata", **info))
    else:
        entrate, flags, credito = risolvi_giocata(st, s, c, presa, ultima)
        info.update(flags)
        for x in presa:
            st.tavola.remove(x)
        st.credito[t] = credito
        info["girate"] = [[e[0], e[2]] for e in entrate if e[1]]
        info["credito"] = st.credito[t]
        st.prese[t].extend(entrate)
        st.ultima_presa_squadra = t
        st.piccola_target = None
        st.giocate_mano.append([s, c, list(presa)])
        info["tavola"] = list(st.tavola)
        events.append(ev("giocata", **info))

    if all(len(m) == 0 for m in st.mani):
        events.append(ev("fine_turno", turno=st.turno))
        if st.turno < 3:
            events += _inizia_turno(st)
        else:
            events += _fine_mano(st)
    else:
        st.corrente = (s + 1) % 4
    return events


def _fine_mano(st: GameState):
    events = []
    if st.tavola:
        t = st.ultima_presa_squadra if st.ultima_presa_squadra is not None else squadra(st.mazziere)
        entrate = [[x, False, None] for x in st.tavola]
        pagato = 0
        for e in entrate:
            if st.credito[t] > 0:
                e[1], e[2] = True, "bazzica"
                st.credito[t] -= 1
                pagato += 1
        st.prese[t].extend(entrate)
        events.append(ev("carte_residue", squadra=t, carte=list(st.tavola), credito_pagato=pagato))
        st.tavola = []
    credito_perso = list(st.credito)
    rie = riepilogo_mano(st.prese, st.rules)
    rie["mano"] = st.mano_n
    rie["mazziere"] = st.mazziere
    rie["credito_perso"] = credito_perso
    st.credito = [0, 0]
    for t in (0, 1):
        st.punteggi[t] += rie["totali"][t]
    rie["punteggi"] = list(st.punteggi)
    st.storico_mani.append(rie)
    events.append(ev("fine_mano", riepilogo=rie))
    vinc = _controlla_fine(st)
    if vinc is not None:
        st.vincitore = vinc
        st.fase = FASE_FINE_PARTITA
        events.append(ev("fine_partita", vincitore=vinc, punteggi=list(st.punteggi), mani=st.mano_n))
    else:
        st.fase = FASE_FINE_MANO
    return events


def _controlla_fine(st: GameState):
    a, b = st.punteggi
    if st.rules.margherita_hack:
        if st.mano_n >= 4:
            return 0 if a > b else 1 if b > a else "pari"
        return None
    if a == b:
        return None
    lead = 0 if a > b else 1
    if st.punteggi[lead] >= st.rules.punti_vittoria:
        return lead
    return None


# --------------------------------------------------------------------------- Osservazione

def observation(st: GameState, seat: int) -> dict:
    """Informazioni visibili a ``seat`` (JSON-serializzabile)."""
    altri = {}
    for s in range(4):
        if s == seat:
            continue
        visibile = st.bazzica[s] is not None
        altri[str(s)] = {"n": len(st.mani[s]), "carte": list(st.mani[s]) if visibile else None}
    prese = []
    for t in (0, 1):
        p = st.prese[t]
        prese.append({
            "n": len(p),
            "scoperte": [[e[0], e[2]] for e in p if e[1]],
            "coperte": sum(1 for e in p if not e[1]),
        })
    baz = {}
    for s in range(4):
        b = st.bazzica[s]
        if b:
            baz[str(s)] = {"tipo": b["tipo"], "scope": b["scope"], "sette": b["sette"], "carte": b["carte"]}
    return {
        "seat": seat,
        "squadra": squadra(seat),
        "compagno": compagno(seat),
        "fase": st.fase,
        "regole": st.rules.to_dict(),
        "mano_n": st.mano_n,
        "turno": st.turno,
        "mazziere": st.mazziere,
        "corrente": st.corrente,
        "punteggi": list(st.punteggi),
        "mano": list(st.mani[seat]),
        "altri": altri,
        "tavola": list(st.tavola),
        "prese": prese,
        "credito": list(st.credito),
        "bazziche": baz,
        "che_palo": [s for s in range(4) if st.che_palo[s]],
        "giocato_turno": list(st.giocato_turno),
        "scambio": {
            "passati": [st.scambio_passata[s] is not None for s in range(4)],
            "veloci": [st.scambio_veloce[s] for s in range(4)],
            "mia_passata": st.scambio_passata[seat],
            "ricevuta": st.scambio_ricevuta[seat],
            "distribuite": list(st.distribuite[seat]),
        },
        "piccola_target": st.piccola_target,
        "ultima_presa_squadra": st.ultima_presa_squadra,
        "giocate_mano": [list(g) for g in st.giocate_mano],
        "carte_iniziali_tavola": list(st.carte_iniziali_tavola),
        "carte_nel_mazzo": len(st.mazzo),
        "storico_mani": st.storico_mani,
        "vincitore": st.vincitore,
    }


def e_ultima_giocata(st: GameState, seat: int) -> bool:
    """Vero se la prossima carta di ``seat`` è l'ultima giocata della Mano."""
    return st.turno == 3 and len(st.mani[seat]) == 1 and all(
        len(m) == 0 for i, m in enumerate(st.mani) if i != seat)


def anteprima(st: GameState, a: Action) -> dict:
    """Cosa produrrebbe una giocata (per l'interfaccia e i bot): presa, Scopa, Piccola, Grande..."""
    if a.tipo != "gioca":
        return {}
    ultima = e_ultima_giocata(st, a.seat)
    entrate, flags, credito = risolvi_giocata(st, a.seat, a.carta, a.presa, ultima)
    out = dict(flags)
    out.update({"presa": list(a.presa), "valore": valore_effettivo(st, a.seat, a.carta),
                "ultima_giocata": ultima, "scoperte": sum(1 for e in entrate if e[1])})
    return out


def stato_da_osservazione(obs: dict, mani_altrui=None) -> GameState:
    """Ricostruisce uno stato *parziale* dal punto di vista di un giocatore.

    Le mani non visibili sono riempite con segnaposto ``"?"`` (o con ``mani_altrui`` se
    fornite, ad es. da un campionamento Monte Carlo). Utile per anteprime e bot.
    """
    seat = obs["seat"]
    mani = [[], [], [], []]
    for s in range(4):
        if s == seat:
            mani[s] = list(obs["mano"])
        elif mani_altrui and mani_altrui.get(s) is not None:
            mani[s] = list(mani_altrui[s])
        else:
            o = obs["altri"][str(s)]
            mani[s] = list(o["carte"]) if o["carte"] is not None else ["?"] * o["n"]
    prese = []
    for p in obs["prese"]:
        prese.append([[c, True, o] for c, o in p["scoperte"]] + [["?", False, None]] * p["coperte"])
    baz = [None] * 4
    for k, b in obs["bazziche"].items():
        baz[int(k)] = dict(b)
    return GameState(
        rules=RulesConfig.from_dict(obs["regole"]), seed=0, rng=Mulberry32(0), fase=obs["fase"],
        punteggi=list(obs["punteggi"]), mano_n=obs["mano_n"], mazziere=obs["mazziere"],
        turno=obs["turno"], tavola=list(obs["tavola"]), mani=mani, prese=prese,
        credito=list(obs["credito"]), corrente=obs["corrente"],
        giocato_turno=list(obs["giocato_turno"]), bazzica=baz,
        piccola_target=obs["piccola_target"], ultima_presa_squadra=obs["ultima_presa_squadra"],
    )
