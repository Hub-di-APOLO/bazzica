"""Rigioca le tracce con il motore e i bot Python e ne misura la copertura.

È la stessa verifica che faranno i test Dart: se passa qui, le tracce sono complete e
riproducibili dal solo seed (PRNG mulberry32).

Uso: python tools/verifica_tracce.py [cartella]
"""
from __future__ import annotations

import collections
import gzip
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

from esporta_tracce import (  # noqa: E402
    USCITA_DEFAULT, canonico, impronta, stato_json, legali_json, hash_osservazioni, crea_agente,
)
from bazzica.engine import (  # noqa: E402
    Action, RulesConfig, new_game, apply_inplace, observation, legal_actions,
)


def verifica(tr: dict, copertura: collections.Counter):
    rules = RulesConfig.from_dict(tr["regole"])
    agenti = [crea_agente(x) for x in tr["agenti"]]
    st, eventi = new_game(rules, seed=tr["seed"])
    p0 = tr["passi"][0]
    assert canonico(eventi) == canonico(p0["eventi"]), "eventi iniziali"
    assert impronta(stato_json(st)) == p0["stato_hash"], "stato iniziale"
    # il mazzo registrato è coerente con le carte uscite (4 in tavola dalla cima)
    assert st.tavola == list(reversed(p0["mazzo_mano"][-4:])), "mazzo iniziale"
    for k, p in enumerate(tr["passi"][1:], 1):
        if p["attore"] is None:
            a = Action.from_dict(p["azione"])
        else:
            s = p["attore"]
            oss = observation(st, s)
            assert canonico(oss) == canonico(p["oss"]), f"osservazione passo {k}"
            assert canonico(legali_json(st, s)) == canonico(p["legali"]), f"legali passo {k}"
            a = agenti[s].choose_action(oss, legal_actions(st, s))
            assert canonico(a.to_dict()) == canonico(p["azione"]), f"scelta del bot passo {k}"
            assert agenti[s].rng.stato == p["rng_bot"], f"rng del bot passo {k}"
        ev = apply_inplace(st, a)
        assert canonico(ev) == canonico(p["eventi"]), f"eventi passo {k}"
        assert impronta(stato_json(st)) == p["stato_hash"], f"stato passo {k}"
        assert hash_osservazioni(st) == p["oss_hash"], f"osservazioni passo {k}"
        if "stato" in p:
            assert canonico(stato_json(st)) == canonico(p["stato"]), f"stato completo passo {k}"
        copertura["azione:" + a.tipo + (":veloce" if a.veloce else "")] += 1
        for e in ev:
            copertura["evento:" + e["tipo"]] += 1
            if e["tipo"] == "giocata":
                for f in ("scopa", "piccola", "grande", "sparecchio", "ultima_giocata"):
                    if e[f]:
                        copertura["giocata:" + f] += 1
                if e["assi"]:
                    copertura["giocata:assi_avogadro"] += 1
                if e["credito_pagato"]:
                    copertura["giocata:credito_riscosso"] += 1
                if e["valore"] != int(e["carta"][-2:]):
                    copertura["giocata:7bello_con_valore"] += 1
            if e["tipo"] == "bazzica":
                copertura[f"bazzica:{e['scope']}_scope"] += 1
                if e["credito"]:
                    copertura["bazzica:con_credito"] += 1
            if e["tipo"] == "fine_mano":
                r = e["riepilogo"]
                if any(r["credito_perso"]):
                    copertura["mano:credito_perso"] += 1
                for sq in r["squadre"]:
                    if sq["napola"]:
                        copertura["mano:" + ("napoleone" if sq["napola_len"] == 10 else "napola")] += 1
                    if sq["semi_mancanti"]:
                        copertura["mano:semi_mancanti"] += 1
                    if sq["totale"] < 0:
                        copertura["mano:totale_negativo"] += 1
            if e["tipo"] == "fine_partita":
                copertura["esito:" + ("pari" if e["vincitore"] == "pari" else "vittoria")] += 1
    assert list(st.punteggi) == tr["finale"]["punteggi"], "punteggi finali"
    assert canonico(stato_json(st)) == canonico(tr["finale"]["stato"]), "stato finale"


def main():
    cartella = sys.argv[1] if len(sys.argv) > 1 else USCITA_DEFAULT
    indice = json.load(open(os.path.join(cartella, "indice.json"), encoding="utf-8"))
    cop = collections.Counter()
    for voce in indice["tracce"]:
        with gzip.open(os.path.join(cartella, voce["file"]), "rb") as f:
            tr = json.loads(f.read().decode("utf-8"))
        try:
            verifica(tr, cop)
        except AssertionError as ex:
            print(f"DIFFERENZA in {voce['file']}: {ex}")
            sys.exit(1)
    print(f"{len(indice['tracce'])} tracce rigiocate: tutto identico.")
    print("Copertura:")
    for k in sorted(cop):
        print(f"  {k:32s} {cop[k]}")


if __name__ == "__main__":
    main()
