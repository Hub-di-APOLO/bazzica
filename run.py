"""Avvia il server della Bazzica:  python run.py  [--port 8000]"""
import argparse
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
    ap = argparse.ArgumentParser(description="Server della Bazzica")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()

    from bazzica.server.app import create_app
    app = create_app()

    print("=" * 60)
    print(" BAZZICA — server avviato")
    print("=" * 60)
    print(f" Su questo PC:      http://localhost:{args.port}")
    for ip in ip_locali():
        print(f" In rete locale:    http://{ip}:{args.port}")
    print()
    print(" Gli altri giocatori aprono l'indirizzo 'In rete locale' nel browser.")
    print(f" Ricorda di consentire la porta {args.port} (TCP) nel firewall di Windows")
    print(" per le reti private, altrimenti gli altri PC non riusciranno a collegarsi.")
    print(" Premi CTRL+C per fermare il server.")
    print("=" * 60)
    sys.stdout.flush()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
