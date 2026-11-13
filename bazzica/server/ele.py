"""eLE, l'Elo della Bazzica: parametri, statistiche per posto ricavate dagli eventi e calcolo (puro).

Tutti i parametri stanno qui, come costanti con nome. Le funzioni non toccano né il database né il
server: ``statistiche_da_eventi`` legge gli eventi del motore, ``calcola`` restituisce le variazioni.
Il comando ``python -m bazzica.admin ricalcola`` rifà tutta la classifica con questi parametri
partendo dalle statistiche grezze salvate, quindi cambiarli è sempre possibile.
"""
from __future__ import annotations

from ..engine.bazzica import opzioni_bazzica

# --------------------------------------------------------------------------- parametri
ELE_INIZIALE = 1550.0
K_PROVVISORIO = 40.0          # K nelle prime PARTITE_PROVVISORIE partite valutate
K_NORMALE = 30.0
PARTITE_PROVVISORIE = 15
SCALA = 400.0                 # E = 1 / (1 + 10^((R_avv - R_sq) / SCALA))

RIPARTIZIONE_COSTANTE = 3.0   # q = (p_i + 3) / (p_i + p_compagno + 6)
RIPARTIZIONE_PESO = 0.5       # vittoria: D·(1 + 0,5·(2q - 1)); sconfitta: D·(1 - 0,5·(2q - 1))

SPETTACOLO_R_PIENO = 0.2      # fino a questo scarto relativo il guadagno dei vincitori è pieno
SPETTACOLO_R_MINIMO = 0.6     # da qui in poi il guadagno è ridotto al minimo
SPETTACOLO_MINIMO = 0.25      # moltiplicatore minimo sul guadagno dei vincitori

BONUS_NAPOLEONE = 3.0         # a ciascuno dei due compagni
BONUS_BAZZICA_7 = 1.0         # Bazzica da 7 Scope riscossa per intero
BONUS_FATTORE_MIN = 0.5       # i bonus si moltiplicano per 2·(1 - E_squadra), limitato a [0,5; 1,5]
BONUS_FATTORE_MAX = 1.5

FATTORE_K_ABBANDONO = 0.5     # K degli altri giocatori se qualcuno ha abbandonato
QUOTA_CARTA_PASSATA = 0.5     # parte di chi gioca quando la presa (o la Bazzica) si deve alla carta del compagno


def k_di(partite_valutate: int) -> float:
    """K del giocatore in base alle partite valutate già giocate (prima di questa)."""
    return K_PROVVISORIO if partite_valutate < PARTITE_PROVVISORIE else K_NORMALE


def provvisorio(partite_valutate: int) -> bool:
    return partite_valutate < PARTITE_PROVVISORIE


def atteso(r_squadra: float, r_avversari: float) -> float:
    return 1.0 / (1.0 + 10 ** ((r_avversari - r_squadra) / SCALA))


def moltiplicatore_spettacolo(punti_a: float, punti_b: float) -> float:
    """Regola dello spettacolo: una vittoria troppo larga non soddisfa il pubblico.

    r = |A - B| / (|A| + |B|) (uguale a |A - B| / (A + B) con punteggi non negativi; con i valori
    assoluti la formula funziona anche con i totali negativi possibili in Margherita Hack)."""
    den = abs(punti_a) + abs(punti_b)
    r = abs(punti_a - punti_b) / den if den else 0.0
    if r <= SPETTACOLO_R_PIENO:
        return 1.0
    if r >= SPETTACOLO_R_MINIMO:
        return SPETTACOLO_MINIMO
    frazione = (r - SPETTACOLO_R_PIENO) / (SPETTACOLO_R_MINIMO - SPETTACOLO_R_PIENO)
    return 1.0 - frazione * (1.0 - SPETTACOLO_MINIMO)


# --------------------------------------------------------------------------- statistiche
def statistiche_vuote() -> dict:
    return {"scope": 0, "piccole": 0, "grandi": 0, "carte_grande": 0, "assi": 0,
            "bazziche": [], "napoleoni": 0}


class Raccoglitore:
    """Statistiche grezze per posto, aggiornate evento per evento durante la partita.

    Punti individuali: Scope (sparecchio), Piccole, Grandi (una Scopa per carta), assi Avogadro e
    Bazziche. Una Bazzica conta solo per le Scope **riscosse**: quelle girate subito alla chiamata e
    quelle del credito pagato dopo (anche con una presa del compagno o con le carte residue). Il
    credito è unico per squadra: si paga in ordine di chiamata, quindi il credito perso a fine Mano
    resta all'ultima Bazzica chiamata. Le carte girate per pagare il credito non contano per chi fa
    la presa.

    Carta passata dal compagno: se Scopa, Piccola, Grande o assi Avogadro si fanno giocando la carta
    ricevuta nello scambio di quel Turno, i punti vanno metà a chi gioca e metà al compagno. Una
    Bazzica è "condivisa" se la carta ricevuta è stata decisiva: con le carte che il giocatore aveva
    prima dello scambio non c'era una Bazzica di quel valore. Le sue Scope riscosse (e il bonus della
    Bazzica da 7) vanno metà per uno."""

    def __init__(self, rules=None):
        self.rules = rules
        self.posti = [statistiche_vuote() for _ in range(4)]
        self._coda = [[], []]          # per squadra: Bazziche con credito ancora da riscuotere
        self._distribuite = [None] * 4  # carte ricevute nella distribuzione del Turno (prima dello scambio)
        self._ricevuta = [None] * 4     # carta ricevuta dal compagno nello scambio del Turno

    def _aggiungi(self, seat: int, campo: str, n: float, carta_passata: bool):
        """Somma ``n`` al campo di ``seat``; con la carta del compagno metà va al compagno."""
        if carta_passata:
            parte = n * QUOTA_CARTA_PASSATA
            self.posti[seat][campo] += parte
            self.posti[(seat + 2) % 4][campo] += n - parte
        else:
            self.posti[seat][campo] += n

    def _condivisa(self, seat: int, scope: int) -> bool:
        if self._ricevuta[seat] is None or self._distribuite[seat] is None or self.rules is None:
            return False
        prima = opzioni_bazzica(self._distribuite[seat], self.rules)
        return max((o["scope"] for o in prima), default=0) < scope

    def _paga(self, squadra: int, n: int):
        coda = self._coda[squadra]
        while n > 0 and coda:
            b = coda[0]
            pagate = min(n, b["scope"] - b["riscosse"])
            b["riscosse"] += pagate
            n -= pagate
            if b["riscosse"] >= b["scope"]:
                coda.pop(0)

    def evento(self, e: dict):
        tipo = e.get("tipo")
        if tipo == "carte_ricevute":
            s = e["seat"]
            self._distribuite[s] = list(e["carte"])
            self._ricevuta[s] = None
        elif tipo == "scambio_ricevuta":
            self._ricevuta[e["seat"]] = e["carta"]
        elif tipo == "bazzica":
            s = e["seat"]
            b = {"scope": int(e["scope"]), "riscosse": int(e.get("girate", 0))}
            if self._condivisa(s, b["scope"]):
                b["condivisa"] = True
            self.posti[s]["bazziche"].append(b)
            if b["riscosse"] < b["scope"]:
                self._coda[s % 2].append(b)
        elif tipo == "giocata":
            if not e.get("presa"):
                return
            s = e["seat"]
            passata = self._ricevuta[s] is not None and e.get("carta") == self._ricevuta[s]
            if e.get("grande"):
                self._aggiungi(s, "grandi", 1, passata)
                self._aggiungi(s, "carte_grande", sum(1 for g in e.get("girate", []) if g[1] == "grande"), passata)
            elif e.get("piccola"):
                self._aggiungi(s, "piccole", 1, passata)
            elif e.get("scopa"):
                self._aggiungi(s, "scope", 1, passata)
            if e.get("assi"):
                self._aggiungi(s, "assi", len(e["assi"]), passata)
            if e.get("credito_pagato"):
                self._paga(e["squadra"], int(e["credito_pagato"]))
        elif tipo == "carte_residue":
            if e.get("credito_pagato"):
                self._paga(e["squadra"], int(e["credito_pagato"]))
        elif tipo == "fine_mano":
            self._coda = [[], []]      # il credito non riscosso si perde
            for t, sq in enumerate(e["riepilogo"]["squadre"]):
                if sq.get("napola_nome") == "Napoleone":
                    self.posti[t]["napoleoni"] += 1
                    self.posti[t + 2]["napoleoni"] += 1


def statistiche_da_eventi(eventi, rules=None) -> list:
    r = Raccoglitore(rules)
    for e in eventi:
        r.evento(e)
    return r.posti


def _quota_bazzica(b: dict, propria: bool) -> float:
    """Parte di una Bazzica che spetta a chi l'ha chiamata (propria) o al compagno."""
    if not b.get("condivisa"):
        return 1.0 if propria else 0.0
    return QUOTA_CARTA_PASSATA if propria else 1.0 - QUOTA_CARTA_PASSATA


def punti_individuali(st: dict, compagno: dict | None = None) -> float:
    """Punti individuali di un posto; ``compagno`` serve per le Bazziche condivise del compagno."""
    p = (st["scope"] + st["piccole"] + st["carte_grande"] + st["assi"]
         + sum(b["riscosse"] * _quota_bazzica(b, True) for b in st["bazziche"]))
    if compagno:
        p += sum(b["riscosse"] * _quota_bazzica(b, False) for b in compagno["bazziche"])
    return p


def bazziche_da_7(st: dict, compagno: dict | None = None) -> float:
    """Bazziche da 7 riscosse per intero (metà ciascuno se condivise)."""
    n = sum(_quota_bazzica(b, True) for b in st["bazziche"] if b["scope"] == 7 and b["riscosse"] >= 7)
    if compagno:
        n += sum(_quota_bazzica(b, False) for b in compagno["bazziche"] if b["scope"] == 7 and b["riscosse"] >= 7)
    return n


# --------------------------------------------------------------------------- calcolo
def calcola(giocatori: list, punteggi, vincitore) -> list:
    """Variazioni di eLE di una partita valutata.

    ``giocatori``: 4 dict per posto (0=Nord, 1=Est, 2=Sud, 3=Ovest; squadre 0-2 e 1-3) con
    ``ele`` (prima della partita), ``partite`` (partite valutate già giocate), ``abbandono``
    (sostituito da un bot e non rientrato) e ``stat`` (statistiche grezze del posto).
    ``punteggi``: [squadra 0, squadra 1] finali; ``vincitore``: 0, 1 o "pari".
    Restituisce per posto: ``delta``, ``dopo``, ``k``, ``esito`` ("vittoria"/"sconfitta"/"pareggio")
    e ``dettaglio`` (tutti i passaggi del calcolo, per il riepilogo e per lo storico)."""
    r = [(giocatori[t]["ele"] + giocatori[t + 2]["ele"]) / 2 for t in (0, 1)]
    e_sq = [atteso(r[0], r[1]), atteso(r[1], r[0])]
    if vincitore == "pari":
        s_sq = [0.5, 0.5]
    else:
        s_sq = [1.0 if t == vincitore else 0.0 for t in (0, 1)]
    spettacolo = moltiplicatore_spettacolo(punteggi[0], punteggi[1])
    abbandoni = any(g.get("abbandono") for g in giocatori)
    punti = [punti_individuali(g["stat"], giocatori[(i + 2) % 4]["stat"]) for i, g in enumerate(giocatori)]

    out = []
    for i, g in enumerate(giocatori):
        t = i % 2
        k = k_di(g["partite"])
        E = e_sq[t]
        det = {"ele_squadra": round(r[t], 2), "ele_avversari": round(r[1 - t], 2), "atteso": round(E, 4),
               "punti": punti[i], "punti_compagno": punti[(i + 2) % 4], "spettacolo": 1.0, "bonus": 0.0,
               "fattore_k": 1.0, "abbandono": bool(g.get("abbandono"))}
        if g.get("abbandono"):
            # chi abbandona prende la sconfitta piena, senza ripartizione, spettacolo né bonus
            s = 0.0
            delta = k * (s - E)
            det.update({"risultato": s, "quota_squadra": round(delta, 4), "ripartizione": 1.0})
            esito = "sconfitta"
        else:
            s = s_sq[t]
            if abbandoni:
                k *= FATTORE_K_ABBANDONO
                det["fattore_k"] = FATTORE_K_ABBANDONO
            d = k * (s - E)
            p_i, p_c = punti[i], punti[(i + 2) % 4]
            q = (p_i + RIPARTIZIONE_COSTANTE) / (p_i + p_c + 2 * RIPARTIZIONE_COSTANTE)
            come_vittoria = s == 1.0 or (s == 0.5 and d >= 0)
            segno = 1 if come_vittoria else -1
            ripartizione = 1 + segno * RIPARTIZIONE_PESO * (2 * q - 1)
            quota = d * ripartizione
            if s == 1.0 and quota > 0:
                quota *= spettacolo
                det["spettacolo"] = round(spettacolo, 4)
            fattore_bonus = min(BONUS_FATTORE_MAX, max(BONUS_FATTORE_MIN, 2 * (1 - E)))
            b7 = bazziche_da_7(g["stat"], giocatori[(i + 2) % 4]["stat"])
            bonus_base = BONUS_NAPOLEONE * g["stat"]["napoleoni"] + BONUS_BAZZICA_7 * b7
            bonus = bonus_base * fattore_bonus
            delta = quota + bonus
            det.update({"risultato": s, "quota_squadra": round(d, 4), "q": round(q, 4),
                        "ripartizione": round(ripartizione, 4), "bonus": round(bonus, 4),
                        "bonus_base": bonus_base, "fattore_bonus": round(fattore_bonus, 4),
                        "napoleoni": g["stat"]["napoleoni"], "bazziche_7": b7})
            esito = "pareggio" if s == 0.5 else "vittoria" if s == 1.0 else "sconfitta"
        det["k"] = k
        out.append({"delta": delta, "dopo": g["ele"] + delta, "k": k, "esito": esito, "dettaglio": det})
    return out
