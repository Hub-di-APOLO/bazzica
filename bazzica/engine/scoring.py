"""Calcolo del punteggio di fine Mano."""
from __future__ import annotations

from .cards import SEMI, PRIMIERA, SETTE_BELLO, RE_BELLO, DUE_DENARI, val, seme, card
from .rules import RulesConfig

ORIGINI_SCOPA = ("sparecchio", "bazzica", "piccola", "grande", "asso")


def primiera(carte):
    """Restituisce (punteggio, dettaglio per seme, semi mancanti)."""
    dettaglio = {}
    mancanti = []
    for s in SEMI:
        cs = [c for c in carte if seme(c) == s]
        if not cs:
            mancanti.append(s)
            dettaglio[s] = None
            continue
        best = max(cs, key=lambda c: PRIMIERA[val(c)])
        dettaglio[s] = {"carta": best, "punti": PRIMIERA[val(best)]}
    tot = sum(d["punti"] for d in dettaglio.values() if d)
    return tot, dettaglio, mancanti


def napola(carte) -> int:
    """Lunghezza della scala di denari a partire dall'asso (0 se meno di A-2-3)."""
    s = set(carte)
    n = 0
    for v in range(1, 11):
        if card("denari", v) in s:
            n = v
        else:
            break
    return n if n >= 3 else 0


def riepilogo_mano(prese, rules: RulesConfig) -> dict:
    """``prese``: per ciascuna squadra lista di [carta, faccia_in_su, origine].

    Restituisce un dict con il dettaglio per squadra e il totale della Mano.
    """
    sq = []
    for t in (0, 1):
        carte = [e[0] for e in prese[t]]
        pt, det, manc = primiera(carte)
        scope = {o: 0 for o in ORIGINI_SCOPA}
        for e in prese[t]:
            if e[1]:
                scope[e[2] or "sparecchio"] = scope.get(e[2] or "sparecchio", 0) + 1
        sq.append({
            "carte": len(carte),
            "denari": sum(1 for c in carte if seme(c) == "denari"),
            "primiera": pt,
            "primiera_dettaglio": det,
            "semi_mancanti": manc,
            "sette_bello": SETTE_BELLO in carte,
            "re_bello": RE_BELLO in carte,
            "due_denari": DUE_DENARI in carte,
            "scope_dettaglio": scope,
            "scope": sum(scope.values()),
            "napola_len": napola(carte),
        })

    a, b = sq
    punti = [{"carte": 0, "denari": 0, "primiera": 0, "sette_bello": 0, "re_bello": 0} for _ in (0, 1)]
    if a["carte"] > 20:
        punti[0]["carte"] = 1
    elif b["carte"] > 20:
        punti[1]["carte"] = 1
    if a["denari"] > 5:
        punti[0]["denari"] = 1
    elif b["denari"] > 5:
        punti[1]["denari"] = 1
    ma, mb = bool(a["semi_mancanti"]), bool(b["semi_mancanti"])
    if ma and not mb:
        punti[1]["primiera"] = 1
    elif mb and not ma:
        punti[0]["primiera"] = 1
    elif not ma and not mb:
        if a["primiera"] > b["primiera"]:
            punti[0]["primiera"] = 1
        elif b["primiera"] > a["primiera"]:
            punti[1]["primiera"] = 1
    for t in (0, 1):
        punti[t]["sette_bello"] = 1 if sq[t]["sette_bello"] else 0
        punti[t]["re_bello"] = 1 if sq[t]["re_bello"] else 0

    for t in (0, 1):
        d = sq[t]
        d["punti_mazzo_dettaglio"] = punti[t]
        d["punti_mazzo"] = sum(punti[t].values())
        if d["due_denari"]:
            d["punti_due_denari"] = -5 + (d["punti_mazzo"] if rules.fermi else 0)
        else:
            d["punti_due_denari"] = 0
        d["napola"] = 0
        d["napola_nome"] = None
        if rules.federico and d["napola_len"] >= 3:
            d["napola"] = d["napola_len"]
            d["napola_nome"] = "Napoleone" if d["napola_len"] == 10 else f"Napola al {d['napola_len']}"
        elif rules.fermi and d["napola_len"] == 10:
            d["napola"] = 10
            d["napola_nome"] = "Napoleone"
        d["totale"] = d["punti_mazzo"] + d["scope"] + d["punti_due_denari"] + d["napola"]
    return {"squadre": sq, "totali": [sq[0]["totale"], sq[1]["totale"]]}
