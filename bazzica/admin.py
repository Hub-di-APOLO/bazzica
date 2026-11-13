"""Comandi di amministrazione degli account e della classifica eLE.

Uso (sul PC dalla cartella del progetto, sul NAS dentro il container):

    python -m bazzica.admin elenco               # account, eLE, partite valutate, sessioni attive
    python -m bazzica.admin password NOME        # nuova password (chiesta a video); revoca le sessioni
    python -m bazzica.admin revoca NOME          # chiude tutte le sessioni dell'account
    python -m bazzica.admin ricalcola            # rifà la classifica da zero con i parametri attuali

Sul NAS:  sudo docker exec -it ix-bazzica-bazzica-1 python -m bazzica.admin elenco
Il database è quello indicato da BAZZICA_DATI (come per il server). Le password non compaiono mai:
si scrivono solo quando richiesto, senza eco.
"""
from __future__ import annotations

import argparse
import getpass
import sys

from .server.account import Account, ErroreAccount
from .server.config import Config
from .server.ele import provvisorio
from .server.storico import Storico


def main(argv=None, leggi_password=getpass.getpass, out=sys.stdout) -> int:
    parser = argparse.ArgumentParser(prog="python -m bazzica.admin", description="Account e classifica eLE")
    parser.add_argument("--db", help="percorso del database (predefinito: quello di BAZZICA_DATI)")
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("elenco", help="elenca gli account")
    p = sub.add_parser("password", help="reimposta la password di un account")
    p.add_argument("nome")
    r = sub.add_parser("revoca", help="chiude tutte le sessioni di un account")
    r.add_argument("nome")
    sub.add_parser("ricalcola", help="ricalcola la classifica da zero")
    args = parser.parse_args(argv)

    storico = Storico(args.db or Config.da_ambiente().db_path)
    acc = Account(storico)
    try:
        if args.comando == "elenco":
            righe = acc.elenco()
            if not righe:
                print("Nessun account.", file=out)
            for a in righe:
                ele = round(a["ele"]) if a["ele"] is not None else "-"
                segno = "?" if provvisorio(a["partite"] or 0) else ""
                print(f"{a['nome']:<20} eLE {ele}{segno:<2} partite {a['partite'] or 0:<4} "
                      f"sessioni {a['sessioni']:<3} ultimo accesso {a['ultimo_accesso'] or '-'}", file=out)
        elif args.comando == "password":
            if not acc.per_nome(args.nome):
                raise ErroreAccount("Account inesistente")
            nuova = leggi_password("Nuova password: ")
            if nuova != leggi_password("Ripeti la password: "):
                raise ErroreAccount("Le due password non coincidono")
            acc.imposta_password(args.nome, nuova)
            print("Password cambiata; tutte le sessioni dell'account sono state chiuse.", file=out)
        elif args.comando == "revoca":
            n = acc.revoca_tutte(args.nome)
            print(f"Sessioni chiuse: {n}.", file=out)
        elif args.comando == "ricalcola":
            n = storico.ricalcola()
            print(f"Classifica ricalcolata da {n} partite valutate. Riavvia l'app per aggiornare gli eLE "
                  "mostrati ai tavoli già aperti.", file=out)
    except ErroreAccount as ex:
        print(f"Errore: {ex}", file=out)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
