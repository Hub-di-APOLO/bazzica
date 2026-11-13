"""Storico delle partite in SQLite."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading

from . import ele as E

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

# versione 1: account, sessioni ed eLE (PRAGMA user_version)
SCHEMA_ELE = """
CREATE TABLE IF NOT EXISTS account (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    nome_norm TEXT NOT NULL UNIQUE,  -- per l'unicità: minuscolo, senza accenti né spazi
    hash TEXT NOT NULL,              -- scrypt della password (mai la password)
    sale TEXT NOT NULL,
    avatar TEXT,
    creato TEXT NOT NULL,
    ultimo_accesso TEXT
);
CREATE TABLE IF NOT EXISTS sessioni (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES account(id),
    token_hash TEXT NOT NULL UNIQUE, -- SHA-256 del token (il token in chiaro non si salva)
    creata TEXT NOT NULL,
    ultimo_uso TEXT,
    scadenza TEXT NOT NULL,
    revocata INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ele (
    account_id INTEGER PRIMARY KEY REFERENCES account(id),
    ele REAL NOT NULL,
    partite INTEGER NOT NULL DEFAULT 0,
    vittorie INTEGER NOT NULL DEFAULT 0,
    sconfitte INTEGER NOT NULL DEFAULT 0,
    pareggi INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS valutazioni (
    partita_id INTEGER PRIMARY KEY REFERENCES partite(id),
    fine TEXT NOT NULL,
    punteggi TEXT NOT NULL,          -- JSON [squadra 0, squadra 1]
    vincitore TEXT NOT NULL,         -- '0', '1' o 'pari'
    posti TEXT NOT NULL              -- JSON per posto: {account_id, abbandono, stat} (statistiche grezze)
);
CREATE TABLE IF NOT EXISTS ele_partite (
    partita_id INTEGER NOT NULL REFERENCES partite(id),
    account_id INTEGER NOT NULL REFERENCES account(id),
    posto INTEGER NOT NULL,
    ele_prima REAL NOT NULL,
    ele_dopo REAL NOT NULL,
    delta REAL NOT NULL,
    k REAL NOT NULL,
    esito TEXT NOT NULL,
    dettaglio TEXT,                  -- JSON: quota di squadra, ripartizione, spettacolo, bonus
    PRIMARY KEY (partita_id, account_id)
);
CREATE INDEX IF NOT EXISTS ele_partite_account ON ele_partite(account_id);
CREATE INDEX IF NOT EXISTS sessioni_account ON sessioni(account_id);
"""
VERSIONE_SCHEMA = 1


class Storico:
    ele_iniziale = E.ELE_INIZIALE

    def __init__(self, path: str):
        self.path = path
        self.lock = threading.RLock()
        with self._conn() as c:
            c.executescript(SCHEMA)
            self._migra(c)
            # partite rimaste aperte da un'esecuzione precedente del server
            c.execute("UPDATE partite SET esito='interrotta' WHERE esito IS NULL")

    @staticmethod
    def _migra(c):
        """Aggiorna lo schema dei database creati da versioni precedenti, senza perdere lo storico."""
        versione = c.execute("PRAGMA user_version").fetchone()[0]
        if versione < 1:
            colonne = {r[1] for r in c.execute("PRAGMA table_info(partite)")}
            if "valutata" not in colonne:
                # le partite giocate prima dell'eLE non sono valutate
                c.execute("ALTER TABLE partite ADD COLUMN valutata INTEGER NOT NULL DEFAULT 0")
            c.executescript(SCHEMA_ELE)
            c.execute(f"PRAGMA user_version = {VERSIONE_SCHEMA}")

    def _conn(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    def controlla(self):
        """Solleva un'eccezione se il database non è leggibile (per l'endpoint di salute)."""
        with self._conn() as c:
            c.execute("SELECT 1 FROM partite LIMIT 1").fetchall()

    def nuova_partita(self, tavolo, variante, margherita, giocatori, log_path, valutata=False) -> int:
        with self.lock, self._conn() as c:
            cur = c.execute(
                "INSERT INTO partite (inizio, tavolo, variante, margherita, giocatori, log, valutata)"
                " VALUES (?,?,?,?,?,?,?)",
                (dt.datetime.now().isoformat(timespec="seconds"), tavolo, variante, int(margherita),
                 json.dumps(giocatori, ensure_ascii=False), log_path, int(bool(valutata))))
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
        d["ele"] = [{k: r[k] for k in ("nome", "posto", "ele_prima", "ele_dopo", "delta", "esito")}
                    for r in self.ele_partita(partita_id)]
        d["mani"] = []
        for m in mani:
            md = dict(m)
            md["riepilogo"] = json.loads(md["riepilogo"])
            d["mani"].append(md)
        return d

    # ------------------------------------------------------------------ eLE
    def ele_di(self, account_ids) -> dict:
        """account_id -> {ele, partite, vittorie, sconfitte, pareggi}."""
        ids = [int(a) for a in account_ids]
        if not ids:
            return {}
        with self._conn() as c:
            rows = c.execute(f"SELECT * FROM ele WHERE account_id IN ({','.join('?' * len(ids))})", ids).fetchall()
        out = {r["account_id"]: dict(r) for r in rows}
        for a in ids:
            out.setdefault(a, {"account_id": a, "ele": E.ELE_INIZIALE, "partite": 0, "vittorie": 0,
                               "sconfitte": 0, "pareggi": 0})
        return out

    def _applica(self, c, partita_id, punteggi, vincitore, posti):
        """Calcola e salva l'eLE di una partita valutata (dentro una transazione aperta)."""
        attuali = {}
        for p in posti:
            r = c.execute("SELECT * FROM ele WHERE account_id=?", (p["account_id"],)).fetchone()
            attuali[p["account_id"]] = dict(r) if r else {"ele": E.ELE_INIZIALE, "partite": 0}
        giocatori = [{"ele": attuali[p["account_id"]]["ele"], "partite": attuali[p["account_id"]]["partite"],
                      "abbandono": p["abbandono"], "stat": p["stat"]} for p in posti]
        risultati = E.calcola(giocatori, punteggi, vincitore)
        for s, (p, r) in enumerate(zip(posti, risultati)):
            aid = p["account_id"]
            prima = giocatori[s]["ele"]
            colonna = {"vittoria": "vittorie", "sconfitta": "sconfitte", "pareggio": "pareggi"}[r["esito"]]
            c.execute("INSERT OR IGNORE INTO ele (account_id, ele) VALUES (?, ?)", (aid, E.ELE_INIZIALE))
            c.execute(f"UPDATE ele SET ele=?, partite=partite+1, {colonna}={colonna}+1 WHERE account_id=?",
                      (r["dopo"], aid))
            c.execute("INSERT OR REPLACE INTO ele_partite (partita_id, account_id, posto, ele_prima, ele_dopo, delta,"
                      " k, esito, dettaglio) VALUES (?,?,?,?,?,?,?,?,?)",
                      (partita_id, aid, s, prima, r["dopo"], r["delta"], r["k"], r["esito"],
                       json.dumps(r["dettaglio"], ensure_ascii=False)))
            r["prima"] = prima
            r["account_id"] = aid
            r["partite"] = giocatori[s]["partite"] + 1
        return risultati

    def registra_valutazione(self, partita_id, punteggi, vincitore, posti):
        """Salva le statistiche grezze della partita e aggiorna l'eLE dei 4 giocatori.

        ``posti``: per posto {account_id, abbandono, stat}. Restituisce i risultati per posto."""
        with self.lock, self._conn() as c:
            c.execute("INSERT INTO valutazioni (partita_id, fine, punteggi, vincitore, posti) VALUES (?,?,?,?,?)",
                      (partita_id, dt.datetime.now().isoformat(timespec="seconds"), json.dumps(list(punteggi)),
                       str(vincitore), json.dumps(posti, ensure_ascii=False)))
            c.execute("UPDATE partite SET valutata=1 WHERE id=?", (partita_id,))
            return self._applica(c, partita_id, punteggi, vincitore, posti)

    def ricalcola(self) -> int:
        """Rifà da zero tutta la classifica, partita per partita in ordine cronologico, con i parametri
        attuali di ``ele.py``. Restituisce il numero di partite ricalcolate."""
        with self.lock, self._conn() as c:
            c.execute("DELETE FROM ele_partite")
            c.execute("UPDATE ele SET ele=?, partite=0, vittorie=0, sconfitte=0, pareggi=0", (E.ELE_INIZIALE,))
            c.execute("INSERT OR IGNORE INTO ele (account_id, ele) SELECT id, ? FROM account", (E.ELE_INIZIALE,))
            rows = c.execute("SELECT * FROM valutazioni ORDER BY fine, partita_id").fetchall()
            for r in rows:
                v = r["vincitore"]
                vincitore = "pari" if v == "pari" else int(v)
                self._applica(c, r["partita_id"], json.loads(r["punteggi"]), vincitore, json.loads(r["posti"]))
        return len(rows)

    def classifica(self):
        """Giocatori con account, dal più alto eLE, con l'andamento partita per partita."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT a.id, a.nome, a.avatar, e.ele, e.partite, e.vittorie, e.sconfitte, e.pareggi "
                "FROM account a JOIN ele e ON e.account_id=a.id ORDER BY e.partite = 0, e.ele DESC, a.nome_norm").fetchall()
            storia = c.execute(
                "SELECT ep.account_id, ep.partita_id, ep.ele_dopo, ep.delta, v.fine FROM ele_partite ep "
                "JOIN valutazioni v ON v.partita_id=ep.partita_id ORDER BY v.fine, ep.partita_id").fetchall()
        andamento = {}
        for s in storia:
            andamento.setdefault(s["account_id"], []).append(
                {"partita": s["partita_id"], "fine": s["fine"], "ele": round(s["ele_dopo"], 2),
                 "delta": round(s["delta"], 2)})
        out = []
        for r in rows:
            d = dict(r)
            aid = d.pop("id")
            d["ele"] = round(d["ele"], 2)
            d["provvisorio"] = E.provvisorio(d["partite"])
            d["andamento"] = andamento.get(aid, [])
            out.append(d)
        return {"giocatori": out, "iniziale": E.ELE_INIZIALE}

    def ele_partita(self, partita_id):
        with self._conn() as c:
            rows = c.execute("SELECT ep.*, a.nome FROM ele_partite ep JOIN account a ON a.id=ep.account_id "
                             "WHERE partita_id=? ORDER BY posto", (partita_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["dettaglio"] = json.loads(d["dettaglio"] or "{}")
            out.append(d)
        return out
