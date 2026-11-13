"""Frontend: nessuna risorsa da internet e scelta ws:// / wss:// per la WebSocket."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "bazzica" / "web"


def test_nessuna_risorsa_esterna():
    """Il gioco deve funzionare senza internet: niente font, script o fogli di stile da altri siti."""
    esterni = re.compile(r"""(?:src|href)\s*=\s*["']\s*(?:https?:)?//|url\(\s*["']?\s*(?:https?:)?//|@import\s+["']?(?:https?:)?//""",
                         re.I)
    for f in list(WEB.rglob("*.html")) + list(WEB.rglob("*.css")) + list(WEB.rglob("*.js")):
        testo = f.read_text(encoding="utf-8")
        assert not esterni.search(testo), f"risorsa esterna in {f.name}"
        assert "fonts.googleapis" not in testo and "gstatic" not in testo, f.name
    assert (WEB / "fonts" / "fredoka-latin-wght-normal.woff2").exists()


def test_la_pagina_non_fissa_lo_schema_della_websocket():
    for f in WEB.rglob("*.js"):
        assert not re.search(r"""["'`]wss?://""", f.read_text(encoding="utf-8")), f.name


CASI = [
    ({"protocol": "https:", "host": "bazzica.duckdns.org"}, "wss://bazzica.duckdns.org/ws?"),
    ({"protocol": "http:", "host": "192.168.1.23:8000"}, "ws://192.168.1.23:8000/ws?"),
    ({"protocol": "https:", "host": "esempio.duckdns.org:20443"}, "wss://esempio.duckdns.org:20443/ws?"),
    ({"protocol": "http:", "host": "localhost:8000"}, "ws://localhost:8000/ws?"),
]


@pytest.mark.skipif(not shutil.which("node"), reason="serve Node.js per eseguire il JavaScript")
def test_url_websocket_ws_o_wss():
    script = f"""
      const {{ urlWebSocket }} = await import({json.dumps((WEB / "js" / "net.js").as_uri())});
      const casi = {json.dumps([c[0] for c in CASI])};
      const out = casi.map((loc) => urlWebSocket(loc, {{ token: "t", nome: "Bea & Co", avatar: "", codice: "7 bello" }}));
      console.log(JSON.stringify(out));
    """
    # net.js importa util.js, che non tocca il DOM al caricamento
    r = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    risultati = json.loads(r.stdout)
    for (loc, inizio), url in zip(CASI, risultati):
        assert url.startswith(inizio), url
        assert url.endswith("token=t&nome=Bea%20%26%20Co&codice=7%20bello")   # avatar vuoto omesso


@pytest.mark.skipif(not shutil.which("node"), reason="serve Node.js per eseguire il JavaScript")
def test_frasi_uguali_tra_server_e_pagina():
    """Le frasi della chat si inviano per indice: l'elenco del browser deve coincidere con quello del server."""
    from bazzica.server.tables import FRASI
    script = f"""
      const {{ FRASI }} = await import({json.dumps((WEB / "js" / "util.js").as_uri())});
      console.log(JSON.stringify(FRASI));
    """
    r = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == FRASI
    assert "Che provocateur" in FRASI


def test_token_di_sessione_mai_nell_indirizzo_della_websocket():
    """Il token di sessione viaggia nel primo messaggio, non nell'URL (che finisce nei log dei proxy)."""
    net = (WEB / "js" / "net.js").read_text(encoding="utf-8")
    parametri = re.search(r"urlWebSocket\(location, \{(.*?)\}\)", net, re.S).group(1)
    assert "sessione:" not in parametri and "sessione," not in parametri
    assert 'type: "sessione"' in net


@pytest.mark.skipif(not shutil.which("node"), reason="serve Node.js per eseguire il JavaScript")
def test_formato_ele_e_variazioni():
    script = f"""
      const {{ testoEle, conSegno }} = await import({json.dumps((WEB / "js" / "util.js").as_uri())});
      console.log(JSON.stringify([
        testoEle({{ ele: 1532.4, provvisorio: true }}), testoEle({{ ele: 1600.6, provvisorio: false }}), testoEle({{}}),
        conSegno(16.875), conSegno(-13.125), conSegno(0), conSegno(-0.01), conSegno(3.75, 2),
      ]));
    """
    r = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == ["1532?", "1601", "", "+16,9", "−13,1", "0,0", "0,0", "+3,75"]
