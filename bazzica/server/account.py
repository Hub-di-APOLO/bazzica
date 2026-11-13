"""Account dei giocatori: nomi utente, password (scrypt), sessioni e limiti dei tentativi.

- Le password si salvano solo come hash scrypt con un sale casuale per account.
- Il token di sessione si dà al client una volta sola; nel database c'è solo il suo SHA-256.
- Password e token non vanno mai nei log né nelle risposte (tranne il token al login, al suo client).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import re
import secrets
import time
import unicodedata

# parametri di scrypt (circa 16 MB di memoria e qualche decina di millisecondi per hash)
SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_LUNGHEZZA = 32

NOME_MIN, NOME_MAX = 3, 20
PASSWORD_MIN, PASSWORD_MAX = 8, 128
NOME_VALIDO = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9 _-]+")
PREFISSO_IDENTITA = "acc:"     # identità interna delle connessioni con account (mai inviata ai client)


class ErroreAccount(ValueError):
    """Errore da mostrare all'utente (testo in italiano)."""


def adesso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def normalizza_nome(nome: str) -> str:
    """Forma usata per l'unicità: minuscolo, senza accenti, spazi, trattini e trattini bassi."""
    s = unicodedata.normalize("NFKD", nome or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[\s_\-]+", "", s).casefold()


def sembra_bot(nome: str) -> bool:
    """I nomi dei bot sono "Bot Nord", … e "<nome> (bot)": un account non deve poterli imitare."""
    n = normalizza_nome(nome)
    return n.startswith("bot") or "(bot)" in (nome or "").casefold() or "🤖" in (nome or "")


def controlla_nome(nome: str) -> str:
    nome = re.sub(r"\s+", " ", (nome or "").strip())
    if not NOME_MIN <= len(nome) <= NOME_MAX:
        raise ErroreAccount(f"Il nome utente deve avere da {NOME_MIN} a {NOME_MAX} caratteri")
    if not NOME_VALIDO.fullmatch(nome):
        raise ErroreAccount("Nel nome utente sono ammessi solo lettere, cifre, spazi, _ e -")
    if sembra_bot(nome):
        raise ErroreAccount("Il nome utente non può somigliare al nome di un bot")
    return nome


def controlla_password(password: str):
    if not isinstance(password, str) or not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        raise ErroreAccount(f"La password deve avere almeno {PASSWORD_MIN} caratteri")


def hash_password(password: str, sale: bytes | None = None) -> tuple[str, str]:
    """Restituisce (hash, sale) in esadecimale."""
    sale = sale or secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode("utf-8"), salt=sale, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
                       dklen=SCRYPT_LUNGHEZZA)
    return h.hex(), sale.hex()


def verifica_password(password: str, hash_hex: str, sale_hex: str) -> bool:
    h, _ = hash_password(password, bytes.fromhex(sale_hex))
    return hmac.compare_digest(h, hash_hex)


# hash di una password qualsiasi: con un nome inesistente si fa lo stesso lavoro (stessi tempi)
_HASH_FINTO = None


def _verifica_finta(password: str):
    global _HASH_FINTO
    if _HASH_FINTO is None:
        _HASH_FINTO = hash_password("password-che-non-esiste")
    verifica_password(password, *_HASH_FINTO)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def identita(account_id: int) -> str:
    return f"{PREFISSO_IDENTITA}{account_id}"


def account_da_identita(token: str) -> int | None:
    if token and token.startswith(PREFISSO_IDENTITA):
        try:
            return int(token[len(PREFISSO_IDENTITA):])
        except ValueError:
            return None
    return None


class Account:
    """Operazioni sugli account nel database dello storico."""

    def __init__(self, storico, durata_sessione_giorni: float = 90):
        self.storico = storico
        self.durata = dt.timedelta(days=durata_sessione_giorni)

    def _scadenza(self):
        return (dt.datetime.now() + self.durata).isoformat(timespec="seconds")

    # ------------------------------------------------------------------ account
    def per_nome(self, nome: str):
        with self.storico._conn() as c:
            r = c.execute("SELECT * FROM account WHERE nome_norm=?", (normalizza_nome(nome),)).fetchone()
        return dict(r) if r else None

    def per_id(self, account_id: int):
        with self.storico._conn() as c:
            r = c.execute("SELECT * FROM account WHERE id=?", (account_id,)).fetchone()
        return dict(r) if r else None

    def nome_registrato(self, nome: str) -> bool:
        return self.per_nome(nome) is not None

    def registra(self, nome: str, password: str) -> dict:
        nome = controlla_nome(nome)
        controlla_password(password)
        h, sale = hash_password(password)
        with self.storico.lock, self.storico._conn() as c:
            if c.execute("SELECT 1 FROM account WHERE nome_norm=?", (normalizza_nome(nome),)).fetchone():
                raise ErroreAccount("Questo nome utente è già usato")
            cur = c.execute(
                "INSERT INTO account (nome, nome_norm, hash, sale, creato) VALUES (?,?,?,?,?)",
                (nome, normalizza_nome(nome), h, sale, adesso()))
            aid = cur.lastrowid
            c.execute("INSERT INTO ele (account_id, ele) VALUES (?, ?)", (aid, self.storico.ele_iniziale))
        return self.per_id(aid)

    def verifica(self, nome: str, password: str):
        """Account se nome e password sono giusti, altrimenti None (stessi tempi in entrambi i casi)."""
        a = self.per_nome(nome or "")
        if a is None or not isinstance(password, str):
            _verifica_finta(password if isinstance(password, str) else "")
            return None
        return a if verifica_password(password, a["hash"], a["sale"]) else None

    def imposta_password(self, nome: str, password: str):
        """Nuova password (comando di amministrazione): revoca anche tutte le sessioni."""
        controlla_password(password)
        a = self.per_nome(nome)
        if not a:
            raise ErroreAccount("Account inesistente")
        h, sale = hash_password(password)
        with self.storico.lock, self.storico._conn() as c:
            c.execute("UPDATE account SET hash=?, sale=? WHERE id=?", (h, sale, a["id"]))
            c.execute("UPDATE sessioni SET revocata=1 WHERE account_id=?", (a["id"],))

    def imposta_avatar(self, account_id: int, avatar: str):
        with self.storico.lock, self.storico._conn() as c:
            c.execute("UPDATE account SET avatar=? WHERE id=?", (avatar, account_id))

    # ------------------------------------------------------------------ sessioni
    def nuova_sessione(self, account_id: int) -> str:
        token = secrets.token_urlsafe(32)
        with self.storico.lock, self.storico._conn() as c:
            c.execute("INSERT INTO sessioni (account_id, token_hash, creata, ultimo_uso, scadenza) VALUES (?,?,?,?,?)",
                      (account_id, hash_token(token), adesso(), adesso(), self._scadenza()))
            c.execute("UPDATE account SET ultimo_accesso=? WHERE id=?", (adesso(), account_id))
        return token

    def da_sessione(self, token: str):
        """Account della sessione, se valida (non scaduta né revocata); ne prolunga la scadenza."""
        if not token or not isinstance(token, str) or len(token) > 200:
            return None
        th = hash_token(token)
        with self.storico.lock, self.storico._conn() as c:
            s = c.execute("SELECT * FROM sessioni WHERE token_hash=?", (th,)).fetchone()
            if not s or s["revocata"] or s["scadenza"] < adesso():
                return None
            c.execute("UPDATE sessioni SET ultimo_uso=?, scadenza=? WHERE id=?", (adesso(), self._scadenza(), s["id"]))
            a = c.execute("SELECT * FROM account WHERE id=?", (s["account_id"],)).fetchone()
        return dict(a) if a else None

    def revoca_sessione(self, token: str):
        with self.storico.lock, self.storico._conn() as c:
            c.execute("UPDATE sessioni SET revocata=1 WHERE token_hash=?", (hash_token(token or ""),))

    def revoca_tutte(self, nome: str) -> int:
        a = self.per_nome(nome)
        if not a:
            raise ErroreAccount("Account inesistente")
        with self.storico.lock, self.storico._conn() as c:
            return c.execute("UPDATE sessioni SET revocata=1 WHERE account_id=? AND revocata=0", (a["id"],)).rowcount

    def elenco(self):
        with self.storico._conn() as c:
            rows = c.execute(
                "SELECT a.id, a.nome, a.creato, a.ultimo_accesso, e.ele, e.partite, "
                "(SELECT COUNT(*) FROM sessioni s WHERE s.account_id=a.id AND s.revocata=0 AND s.scadenza>=?) "
                "AS sessioni FROM account a LEFT JOIN ele e ON e.account_id=a.id ORDER BY a.nome_norm",
                (adesso(),)).fetchall()
        return [dict(r) for r in rows]


class LimiteTentativi:
    """Tentativi falliti per chiave (IP o nome utente) in una finestra di tempo: oltre il massimo
    la chiave è bloccata per ``blocco`` secondi."""

    def __init__(self, massimo: int, finestra: float, blocco: float, orologio=time.monotonic):
        self.massimo, self.finestra, self.blocco = massimo, finestra, blocco
        self.orologio = orologio
        self.falliti: dict[str, list] = {}
        self.bloccato_fino: dict[str, float] = {}

    def bloccato(self, chiave: str) -> bool:
        if not self.massimo:
            return False
        fino = self.bloccato_fino.get(chiave)
        if fino is None:
            return False
        if self.orologio() >= fino:
            del self.bloccato_fino[chiave]
            self.falliti.pop(chiave, None)
            return False
        return True

    def fallito(self, chiave: str):
        if not self.massimo:
            return
        ora = self.orologio()
        lista = [t for t in self.falliti.get(chiave, []) if ora - t < self.finestra] + [ora]
        self.falliti[chiave] = lista
        if len(lista) >= self.massimo:
            self.bloccato_fino[chiave] = ora + self.blocco

    def riuscito(self, chiave: str):
        self.falliti.pop(chiave, None)

    def pulisci(self):
        ora = self.orologio()
        for k in [k for k, v in self.bloccato_fino.items() if v <= ora]:
            del self.bloccato_fino[k]
        for k in [k for k, v in self.falliti.items() if not v or ora - v[-1] >= self.finestra]:
            del self.falliti[k]
