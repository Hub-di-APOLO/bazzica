"""Codice d'accesso, IP reale dietro reverse proxy e limiti contro gli abusi."""
from __future__ import annotations

import hmac
import ipaddress
import time

# codici di chiusura della WebSocket (4000–4999 sono liberi per le applicazioni)
CHIUSURA_CODICE = 4401        # codice d'accesso mancante o errato
CHIUSURA_TROPPE_CONN = 4429   # troppe connessioni dallo stesso IP
CHIUSURA_MESSAGGIO = 4413     # messaggio troppo grande
CHIUSURA_FREQUENZA = 4408     # troppi messaggi al secondo (dopo un avviso)


def codice_valido(atteso: str, fornito: str | None) -> bool:
    """True se non serve un codice o se quello fornito è corretto (confronto a tempo costante)."""
    if not atteso:
        return True
    return hmac.compare_digest(atteso.encode("utf-8"), (fornito or "").strip().encode("utf-8"))


def _ip(testo):
    try:
        return ipaddress.ip_address(testo.strip())
    except (ValueError, AttributeError):
        return None


def ip_reale(peer: str | None, x_forwarded_for: str | None, proxy_fidati) -> str:
    """IP del client. X-Forwarded-For si usa solo se la connessione arriva da un proxy fidato:
    si scorre la catena da destra e si prende il primo indirizzo che non è un proxy fidato."""
    peer = peer or "?"
    ip_peer = _ip(peer)
    if not proxy_fidati or ip_peer is None or not x_forwarded_for:
        return peer

    def fidato(ip):
        return any(ip.version == rete.version and ip in rete for rete in proxy_fidati)

    if not fidato(ip_peer):
        return peer
    catena = [x for x in (p.strip() for p in x_forwarded_for.split(",")) if x]
    for voce in reversed(catena):
        ip = _ip(voce)
        if ip is None:
            return peer          # catena illeggibile: non ci si fida
        if not fidato(ip):
            return str(ip)
    # tutta la catena è fatta di proxy fidati: il più a sinistra è il client
    primo = _ip(catena[0]) if catena else None
    return str(primo) if primo else peer


class Secchiello:
    """Limite di frequenza 'a secchiello': `raffica` messaggi di fila, poi `al_secondo` in media."""

    def __init__(self, al_secondo: float, raffica: int, orologio=time.monotonic):
        self.al_secondo = al_secondo
        self.raffica = max(1, raffica)
        self.gettoni = float(self.raffica)
        self.orologio = orologio
        self.ultimo = orologio()

    def consenti(self) -> bool:
        if self.al_secondo <= 0:
            return True
        ora = self.orologio()
        self.gettoni = min(self.raffica, self.gettoni + (ora - self.ultimo) * self.al_secondo)
        self.ultimo = ora
        if self.gettoni >= 1:
            self.gettoni -= 1
            return True
        return False


class ContaConnessioni:
    """Connessioni WebSocket aperte per IP."""

    def __init__(self):
        self.per_ip: dict[str, int] = {}

    def apri(self, ip: str, massimo: int) -> bool:
        n = self.per_ip.get(ip, 0)
        if massimo and n >= massimo:
            return False
        self.per_ip[ip] = n + 1
        return True

    def chiudi(self, ip: str):
        n = self.per_ip.get(ip, 0) - 1
        if n > 0:
            self.per_ip[ip] = n
        else:
            self.per_ip.pop(ip, None)
