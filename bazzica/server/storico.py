"""Storico delle partite in SQLite."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS partite (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inizio TEXT NOT NULL,
    fine TEXT,
    tavolo TEXT,
    variante TEXT,
    margherita INTEGER,
    giocatori TEXT,          -- JSON: [{nome, bot, posto, squadra}]
    punti_ns INTEGER DEFAULT 0,
    punti_eo INTEGER DEFAULT 0,
    esito TEXT,              -- 'Elementini', 'Messicani', 'pari', 'interrotta' o NULL (in corso)
    log TEXT
);
CREATE TABLE IF NOT EXISTS mani (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    partita_id INTEGER NOT NULL REFERENCES partite(id),
    numero INTEGER,
    mazziere INTEGER,
    punti_ns INTEGER,
    punti_eo INTEGER,
    totale_ns INTEGER,
    totale_eo INTEGER,
    riepilogo TEXT           -- JSON completo del riepilogo
);
"""


class Storico:
    def __init__(self, path: str):
        self.path = path
        self.lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)
            # partite rimaste aperte da un'esecuzione precedente del server
            c.execute("UPDATE partite SET esito='interrotta' WHERE esito IS NULL")

    def _conn(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    def controlla(self):
        """Solleva un'eccezione se il database non è leggibile (per l'endpoint di salute)."""
        with self._conn() as c:
            c.execute("SELECT 1 FROM partite LIMIT 1").fetchall()

    def nuova_partita(self, tavolo, variante, margherita, giocatori, log_path) -> int:
        with self.lock, self._conn() as c:
            cur = c.execute(
                "INSERT INTO partite (inizio, tavolo, variante, margherita, giocatori, log) VALUES (?,?,?,?,?,?)",
                (dt.datetime.now().isoformat(timespec="seconds"), tavolo, variante, int(margherita),
                 json.dumps(giocatori, ensure_ascii=False), log_path))
            return cur.lastrowid

    def registra_mano(self, partita_id, rie):
        with self.lock, self._conn() as c:
            c.execute(
                "INSERT INTO mani (partita_id, numero, mazziere, punti_ns, punti_eo, totale_ns, totale_eo, riepilogo)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (partita_id, rie["mano"], rie["mazziere"], rie["totali"][0], rie["totali"][1],
                 rie["punteggi"][0], rie["punteggi"][1], json.dumps(rie, ensure_ascii=False)))
            c.execute("UPDATE partite SET punti_ns=?, punti_eo=? WHERE id=?",
                      (rie["punteggi"][0], rie["punteggi"][1], partita_id))

    def chiudi_partita(self, partita_id, esito, punteggi):
        with self.lock, self._conn() as c:
            c.execute("UPDATE partite SET fine=?, esito=?, punti_ns=?, punti_eo=? WHERE id=?",
                      (dt.datetime.now().isoformat(timespec="seconds"), esito, punteggi[0], punteggi[1],
                       partita_id))

    def elenco(self, limite=200):
        with self._conn() as c:
            rows = c.execute(
                "SELECT p.*, (SELECT COUNT(*) FROM mani m WHERE m.partita_id=p.id) AS n_mani "
                "FROM partite p ORDER BY p.id DESC LIMIT ?", (limite,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["giocatori"] = json.loads(d["giocatori"] or "[]")
            out.append(d)
        return out

    def dettaglio(self, partita_id):
        with self._conn() as c:
            p = c.execute("SELECT * FROM partite WHERE id=?", (partita_id,)).fetchone()
            if not p:
                return None
            mani = c.execute("SELECT * FROM mani WHERE partita_id=? ORDER BY numero", (partita_id,)).fetchall()
        d = dict(p)
        d["giocatori"] = json.loads(d["giocatori"] or "[]")
        d["mani"] = []
        for m in mani:
            md = dict(m)
            md["riepilogo"] = json.loads(md["riepilogo"])
            d["mani"].append(md)
        return d
