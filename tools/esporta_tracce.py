"""Esporta tracce di riferimento di partite solo-bot per verificare il port Dart.

Uso:
    python tools/esporta_tracce.py                 # 25 partite per variante (200 in tutto)
    python tools/esporta_tracce.py --per-variante 250 --uscita /tmp/tracce

Ogni traccia (``<nome>.json.gz``) contiene, per ogni passo della partita:
- l'attore e l'azione scelta dal bot;
- le azioni legali dell'attore (con l'anteprima delle giocate, come le invia il server);
- l'osservazione completa dell'attore (cioè l'input del bot);
- tutti gli eventi emessi (con il campo ``visibile``);
- l'hash SHA-256 del JSON canonico dello stato completo e delle 4 osservazioni.
Le tracce "dettagliate" includono anche lo stato completo dopo ogni passo.

JSON canonico: ``json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)``
in UTF-8. Il formato dello stato è definito da ``stato_json`` qui sotto: il port Dart deve
produrre esattamente lo stesso dizionario.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from bazzica.bots import HeuristicAgent, RandomAgent  # noqa: E402
from bazzica.engine.prng import Mulberry32  # noqa: E402
from bazzica.engine import (  # noqa: E402
    MAZZO, VARIANTI, preset, new_game, legal_actions, apply_inplace, observation, anteprima,
    required_actors, optional_actors, system_action, FASE_FINE_PARTITA,
)

VERSIONE_FORMATO = 1
USCITA_DEFAULT = os.path.join(ROOT, "mobile", "packages", "bazzica_core", "test", "tracce")


# --------------------------------------------------------------------------- serializzazione

def canonico(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def congela(obj):
    """Copia profonda via JSON: alcune strutture (es. ``storico_mani``) sono condivise con lo
    stato e verrebbero modificate dai passi successivi."""
    return json.loads(canonico(obj))


def impronta(obj) -> str:
    return hashlib.sha256(canonico(obj).encode("utf-8")).hexdigest()


def stato_json(st) -> dict:
    """Stato completo del motore in forma JSON (formato condiviso con il port Dart)."""
    return {
        "regole": st.rules.to_dict(),
        "seed": st.seed,
        "rng": st.rng.stato,
        "fase": st.fase,
        "punteggi": list(st.punteggi),
        "mano_n": st.mano_n,
        "mazziere": st.mazziere,
        "primo_mazziere": st.primo_mazziere,
        "turno": st.turno,
        "mazzo": list(st.mazzo),
        "tavola": list(st.tavola),
        "mani": [list(m) for m in st.mani],
        "distribuite": [list(m) for m in st.distribuite],
        "prese": [[list(e) for e in p] for p in st.prese],
        "credito": list(st.credito),
        "corrente": st.corrente,
        "giocato_turno": list(st.giocato_turno),
        "bazzica": [dict(b) if b else None for b in st.bazzica],
        "che_palo": list(st.che_palo),
        "palo_considerato": list(st.palo_considerato),
        "scambio_passata": list(st.scambio_passata),
        "scambio_ricevuta": list(st.scambio_ricevuta),
        "scambio_veloce": list(st.scambio_veloce),
        "scambio_attesa": list(st.scambio_attesa),
        "piccola_target": st.piccola_target,
        "ultima_presa_squadra": st.ultima_presa_squadra,
        "giocate_mano": [list(g) for g in st.giocate_mano],
        "storico_mani": st.storico_mani,
        "vincitore": st.vincitore,
        "carte_iniziali_tavola": list(st.carte_iniziali_tavola),
    }


def mazzo_mescolato(rng) -> list:
    """Ordine del mazzo che produrrà il prossimo mescolamento (su una copia del generatore)."""
    m = list(MAZZO)
    rng.copia().shuffle(m)
    return m


def legali_json(st, seat) -> list:
    out = []
    for a in legal_actions(st, seat):
        d = a.to_dict()
        if a.tipo == "gioca":
            d["anteprima"] = anteprima(st, a)
        out.append(d)
    return out


def hash_osservazioni(st) -> list:
    return [impronta(observation(st, s)) for s in range(4)]


# --------------------------------------------------------------------------- agenti

def crea_agente(spec: dict):
    if spec["tipo"] == "euristico":
        return HeuristicAgent(seed=spec["seed"])
    if spec["tipo"] == "casuale":
        return RandomAgent(seed=spec["seed"])
    raise ValueError(spec)


def specifiche_agenti(seed: int, i: int) -> list:
    """Per lo più bot euristici; una partita su quattro ha anche bot casuali (più copertura)."""
    specs = []
    for s in range(4):
        tipo = "casuale" if (i % 4 == 3 and s % 2 == 1) or (i % 8 == 7) else "euristico"
        specs.append({"tipo": tipo, "seed": (seed * 7 + s * 101) & 0xFFFFFFFF})
    return specs


# --------------------------------------------------------------------------- partita registrata

def registra_partita(variante: str, margherita: bool, seed: int, specs: list, dettagliata: bool):
    rules = preset(variante, margherita)
    agenti = [crea_agente(x) for x in specs]
    r0 = Mulberry32(seed)
    r0.randbelow(4)
    primo_mazzo = mazzo_mescolato(r0)
    st, eventi = new_game(rules, seed=seed)
    passi = [{
        "attore": None, "azione": None, "eventi": congela(eventi),
        "mazzo_mano": primo_mazzo,
        "stato_hash": impronta(stato_json(st)), "oss_hash": hash_osservazioni(st),
        **({"stato": congela(stato_json(st))} if dettagliata else {}),
    }]
    n = 0
    while st.fase != FASE_FINE_PARTITA:
        n += 1
        if n > 100000:
            raise RuntimeError("stallo")
        passo = {}
        sa = system_action(st)
        if sa is not None:
            passo["attore"] = None
            passo["azione"] = sa.to_dict()
            passo["mazzo_mano"] = mazzo_mescolato(st.rng)
            ev = apply_inplace(st, sa)
        else:
            attore, legali = None, None
            for s in optional_actors(st) + required_actors(st):
                leg = legal_actions(st, s)
                if leg:
                    attore, legali = s, leg
                    break
            if attore is None:
                raise RuntimeError("nessuno può agire")
            oss = observation(st, attore)
            passo["attore"] = attore
            passo["legali"] = congela(legali_json(st, attore))
            passo["oss"] = congela(oss)
            a = agenti[attore].choose_action(oss, legali)
            passo["azione"] = a.to_dict()
            passo["rng_bot"] = agenti[attore].rng.stato
            ev = apply_inplace(st, a)
        passo["eventi"] = congela(ev)
        passo["stato_hash"] = impronta(stato_json(st))
        passo["oss_hash"] = hash_osservazioni(st)
        if dettagliata:
            passo["stato"] = congela(stato_json(st))
        passi.append(passo)
    return {
        "versione": VERSIONE_FORMATO,
        "variante": variante,
        "margherita": margherita,
        "regole": rules.to_dict(),
        "seed": seed,
        "agenti": specs,
        "dettagliata": dettagliata,
        "passi": passi,
        "finale": {
            "punteggi": list(st.punteggi), "vincitore": st.vincitore, "mani": st.mano_n,
            "stato": stato_json(st),
        },
    }


# Partite con casi rari, trovate cercando tra i seed: (etichetta, variante, margherita, seed, indice)
SPECIALI = [
    ("napoleone", "Federico II", True, 9000108, 108),
    ("napoleone", "Curie", False, 9000127, 127),
    ("napoleone", "Fermi", False, 9000130, 130),
    ("pari", "Federico II", True, 9000033, 33),
    ("pari", "Avogadro", True, 9000039, 39),
    ("pari", "Fermi", True, 9000060, 60),
    ("credito_perso", "Curie", True, 9000012, 12),
    ("credito_perso", "Curie", True, 9000042, 42),
    ("credito_perso", "Federico II", False, 9000068, 68),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--per-variante", type=int, default=25)
    ap.add_argument("--uscita", default=USCITA_DEFAULT)
    ap.add_argument("--ogni-dettagliata", type=int, default=10,
                    help="una partita ogni N include lo stato completo a ogni passo")
    args = ap.parse_args()

    os.makedirs(args.uscita, exist_ok=True)
    indice = []
    totale_byte = 0
    for vi, variante in enumerate(VARIANTI):
        for i in range(args.per_variante):
            seed = 100000 * (vi + 1) + i
            margherita = i % 5 == 4
            specs = specifiche_agenti(seed, i)
            dett = i % args.ogni_dettagliata == 0
            tr = registra_partita(variante, margherita, seed, specs, dett)
            nome = f"{variante.replace(' ', '_')}_{i:04d}.json.gz"
            dati = canonico(tr).encode("utf-8")
            with gzip.open(os.path.join(args.uscita, nome), "wb", compresslevel=9) as f:
                f.write(dati)
            totale_byte += os.path.getsize(os.path.join(args.uscita, nome))
            indice.append({"file": nome, "variante": variante, "margherita": margherita, "seed": seed,
                           "passi": len(tr["passi"]), "mani": tr["finale"]["mani"],
                           "punteggi": tr["finale"]["punteggi"], "dettagliata": dett})
    for k, (etichetta, variante, margherita, seed, i) in enumerate(SPECIALI):
        tr = registra_partita(variante, margherita, seed, specifiche_agenti(seed, i), True)
        nome = f"Speciale_{etichetta}_{k:02d}.json.gz"
        with gzip.open(os.path.join(args.uscita, nome), "wb", compresslevel=9) as f:
            f.write(canonico(tr).encode("utf-8"))
        totale_byte += os.path.getsize(os.path.join(args.uscita, nome))
        indice.append({"file": nome, "variante": variante, "margherita": margherita, "seed": seed,
                       "passi": len(tr["passi"]), "mani": tr["finale"]["mani"],
                       "punteggi": tr["finale"]["punteggi"], "dettagliata": True, "speciale": etichetta})
    with open(os.path.join(args.uscita, "indice.json"), "w", encoding="utf-8") as f:
        json.dump({"versione": VERSIONE_FORMATO, "tracce": indice}, f, ensure_ascii=False, indent=1)
    print(f"{len(indice)} tracce in {args.uscita} ({totale_byte / 1e6:.1f} MB compressi)")


if __name__ == "__main__":
    main()
