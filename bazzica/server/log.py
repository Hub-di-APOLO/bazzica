"""Log testuale delle partite (debug lato server, in italiano leggibile)."""
from __future__ import annotations

import datetime as dt
import os
import re

from ..engine import nome, nomi, NOMI_POSTI, NOMI_SQUADRE
from ..engine.bazzica import NOMI_TIPO

ORIGINI = {"sparecchio": "sparecchio", "bazzica": "Bazzica", "piccola": "Piccola",
           "grande": "Grande", "asso": "assi"}


def descrivi_riepilogo(rie: dict, squadre=NOMI_SQUADRE) -> str:
    righe = [f"Riepilogo Mano {rie['mano']} (mazziere {NOMI_POSTI[rie['mazziere']]}):"]
    w = 22
    righe.append(" " * w + f"{squadre[0]:>12}{squadre[1]:>12}")
    a, b = rie["squadre"]

    def riga(label, x, y):
        righe.append(f"{label:<{w}}{str(x):>12}{str(y):>12}")

    def pm(k):
        return a["punti_mazzo_dettaglio"][k], b["punti_mazzo_dettaglio"][k]

    riga("Carte", f"{a['carte']} ({pm('carte')[0]})", f"{b['carte']} ({pm('carte')[1]})")
    riga("Denari", f"{a['denari']} ({pm('denari')[0]})", f"{b['denari']} ({pm('denari')[1]})")
    riga("Primiera", f"{a['primiera']} ({pm('primiera')[0]})", f"{b['primiera']} ({pm('primiera')[1]})")
    riga("7 bello", *pm("sette_bello"))
    riga("Re bello", *pm("re_bello"))
    riga("Punti di mazzo", a["punti_mazzo"], b["punti_mazzo"])
    for o, lab in ORIGINI.items():
        x, y = a["scope_dettaglio"].get(o, 0), b["scope_dettaglio"].get(o, 0)
        if x or y:
            riga(f"  Scope ({lab})", x, y)
    riga("Scope totali", a["scope"], b["scope"])
    riga("2 di denari", a["punti_due_denari"], b["punti_due_denari"])
    if a["napola"] or b["napola"]:
        riga("Napola/Napoleone", a["napola"], b["napola"])
    riga("TOTALE MANO", a["totale"], b["totale"])
    riga("Totale partita", rie["punteggi"][0], rie["punteggi"][1])
    if any(rie.get("credito_perso", [0, 0])):
        riga("Credito perso", *rie["credito_perso"])
    return "\n".join(righe)


def descrivi_evento(e: dict, nomi_giocatori=None, squadre=NOMI_SQUADRE) -> str | None:
    def P(s):
        n = NOMI_POSTI[s]
        if nomi_giocatori:
            return f"{nomi_giocatori[s]} ({n})"
        return n

    t = e["tipo"]
    if t == "inizio_partita":
        return f"Inizio partita — variante {e['variante']}. Primo mazziere: {P(e['mazziere'])}."
    if t == "nuova_mano":
        return f"\n===== Mano {e['mano']} — mazziere {P(e['mazziere'])} ====="
    if t == "distribuzione":
        s = f"--- Turno {e['turno']}: distribuite 3 carte a testa."
        if e["turno"] == 1:
            s += f" In tavola: {nomi(e['tavola'])}."
        return s
    if t == "carte_ricevute":
        return f"  Carte di {P(e['seat'])}: {nomi(e['carte'])}"
    if t == "inizio_scambio":
        return "  Fase di scambio carte."
    if t == "scambio_carta":
        return f"  {P(e['seat'])} passa {nome(e['carta'])} a {P(e['a'])}" + (" — PASSA VELOCE!" if e["veloce"] else "")
    if t == "fine_scambio":
        return "  Scambio completato."
    if t == "bazzica":
        s = f"  {P(e['seat'])} chiama BAZZICA: {NOMI_TIPO[e['tipo_bazzica']]}, {e['scope']} Scope"
        if e["sette"] is not None:
            s += f" (7 bello = {e['sette']})"
        s += f". Carte: {nomi(e['carte'])}. Girate {e['girate']}, credito di squadra {e['credito']}."
        return s
    if t == "che_palo":
        return f"  {P(e['seat'])}: «Che Palo!»"
    if t == "giocata":
        s = f"  {P(e['seat'])} gioca {nome(e['carta'])}"
        if e["valore"] != int(e["carta"][-2:]):
            s += f" (vale {e['valore']})"
        if e["presa"]:
            s += f" e prende {nomi(e['presa'])}"
            extra = []
            if e["scopa"]:
                extra.append("SCOPA")
            if e["piccola"]:
                extra.append("PICCOLA")
            if e["grande"]:
                extra.append(f"GRANDE da {len(e['presa']) + 1}")
            if e["assi"]:
                extra.append(f"assi a faccia in su: {nomi(e['assi'])}")
            if e["credito_pagato"]:
                extra.append(f"credito riscosso {e['credito_pagato']} (residuo {e.get('credito', 0)})")
            if e["ultima_giocata"]:
                extra.append("ultima giocata della Mano")
            if extra:
                s += " — " + "; ".join(extra)
        else:
            s += " (resta in tavola)"
        s += f". Tavola: {nomi(e['tavola'])}."
        return s
    if t == "fine_turno":
        return f"--- Fine Turno {e['turno']}."
    if t == "carte_residue":
        s = f"  Carte rimaste in tavola a {squadre[e['squadra']]}: {nomi(e['carte'])}"
        if e["credito_pagato"]:
            s += f" (credito riscosso {e['credito_pagato']})"
        return s
    if t == "fine_mano":
        return descrivi_riepilogo(e["riepilogo"], squadre)
    if t == "fine_partita":
        v = e["vincitore"]
        esito = "PAREGGIO" if v == "pari" else f"vince {squadre[v]}"
        return f"\n##### Fine partita dopo {e['mani']} Mani: {esito} ({e['punteggi'][0]} - {e['punteggi'][1]}) #####"
    if t == "ele":
        righe = [f"  {v['nome']}: {v['prima']:.1f} -> {v['dopo']:.1f} ({v['delta']:+.1f}, {v['esito']})"
                 for v in e["variazioni"]]
        return f"eLE (moltiplicatore spettacolo {e['spettacolo']:g}):\n" + "\n".join(righe)
    if t == "sostituito":
        motivo = {"uscito": "è uscito dalla partita", "inattivo": "è inattivo da troppo tempo",
                  "disconnesso": "è disconnesso da troppo tempo"}.get(e.get("motivo"), "è uscito")
        return f"  {e['nome']} ({NOMI_POSTI[e['seat']]}) {motivo}: al suo posto gioca un bot."
    if t == "rientrato":
        return f"  {e['nome']} ({NOMI_POSTI[e['seat']]}) riprende il suo posto al posto del bot."
    return None


class GameLogger:
    def __init__(self, cartella: str, tavolo: str, variante: str, giocatori: list[str], squadre=NOMI_SQUADRE):
        os.makedirs(cartella, exist_ok=True)
        ora = dt.datetime.now()
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", tavolo)[:30]
        self.path = os.path.join(cartella, f"{ora:%Y%m%d_%H%M%S}_{safe}.txt")
        self.nomi = giocatori
        self.squadre = list(squadre)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(f"Bazzica — log partita\nData: {ora:%d/%m/%Y %H:%M:%S}\nTavolo: {tavolo}\n"
                    f"Variante: {variante}\n")
            for s in range(4):
                f.write(f"{NOMI_POSTI[s]}: {giocatori[s]} (squadra {self.squadre[s % 2]})\n")
            f.write("\n")

    def scrivi(self, events):
        righe = [descrivi_evento(e, self.nomi, self.squadre) for e in events]
        righe = [r for r in righe if r]
        if righe:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write("\n".join(righe) + "\n")

    def nota(self, testo: str):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(testo + "\n")
