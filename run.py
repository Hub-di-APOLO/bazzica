"""Avvia il server della Bazzica:  python run.py  [--port 8000]"""
import argparse
import dataclasses
import os
import socket
import sys

import uvicorn


def ip_locali():
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass
    return sorted(ips)


def main():
    from bazzica.server.config import Config
    try:
        cfg = Config.da_ambiente()
    except ValueError as ex:
        sys.exit(f"Configurazione non valida: {ex}")
    ap = argparse.ArgumentParser(description="Server della Bazzica (configurabile anche con le variabili "
                                             "d'ambiente BAZZICA_*, vedi bazzica/server/config.py)")
    ap.add_argument("--port", type=int, default=cfg.porta)
    ap.add_argument("--host", default=cfg.host)
    args = ap.parse_args()
    cfg = dataclasses.replace(cfg, host=args.host, porta=args.port)

    from bazzica.server.app import create_app
    app = create_app(config=cfg)

    print("=" * 60)
    print(" BAZZICA — server avviato")
    print("=" * 60)
    print(f" Su questo PC:      http://localhost:{args.port}")
    for ip in ip_locali():
        print(f" In rete locale:    http://{ip}:{args.port}")
    print()
    print(" Gli altri giocatori aprono l'indirizzo 'In rete locale' nel browser.")
    if os.name == "nt":
        print(f" Ricorda di consentire la porta {args.port} (TCP) nel firewall di Windows")
        print(" per le reti private, altrimenti gli altri PC non riusciranno a collegarsi.")
    if cfg.codice:
        print(" Codice d'accesso attivo (BAZZICA_CODICE).")
    print(f" Storico: {cfg.db_path}   Log: {cfg.cartella_log}")
    print(" Premi CTRL+C per fermare il server.")
    print("=" * 60)
    sys.stdout.flush()
    # proxy_headers=False: X-Forwarded-For lo interpreta l'app solo dai proxy fidati (BAZZICA_PROXY_FIDATI);
    # ws_max_size: tetto di sicurezza del server WebSocket, sopra al limite applicativo dei messaggi
    uvicorn.run(app, host=cfg.host, port=cfg.porta, log_level="warning", proxy_headers=False,
                ws_max_size=max(65536, 4 * cfg.max_messaggio))


if __name__ == "__main__":
    main()
