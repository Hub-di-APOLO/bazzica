"""Spettatori delle partite con giocatori umani: solo informazioni pubbliche, frasi rapide, permesso."""
import json
import time

from fastapi.testclient import TestClient

from bazzica.server.app import create_app
from bazzica.server.config import Config
from bazzica.server.tables import Manager, FRASI


def nuovo_client(tmp_path, ritardo=(0, 0)):
    m = Manager(cartella_log=str(tmp_path / "logs"), db_path=str(tmp_path / "s.db"), ritardo_bot=ritardo,
                pausa_fine_mano=0, config=Config(max_msg_secondo=0))
    c = TestClient(create_app(m))
    c.manager = m
    return c


def ricevi_fino(ws, cond, max_msg=5000):
    for _ in range(max_msg):
        msg = ws.receive_json()
        if cond(msg):
            return msg
    raise AssertionError("messaggio atteso non ricevuto")


def aspetta(cond, secondi=5.0):
    fine = time.monotonic() + secondi
    while time.monotonic() < fine:
        if cond():
            return
        time.sleep(0.02)
    raise AssertionError("condizione non raggiunta")


def tavolo_con_umano(ws, variante="Heisenberg", spettatori=None):
    ws.send_json({"type": "crea_tavolo", "variante": variante, "nome": "Prova"})
    tid = ricevi_fino(ws, lambda m: m["type"] == "tavolo")["tavolo"]["id"]
    ws.send_json({"type": "siedi", "tavolo": tid, "posto": 0, "nome": "Anna"})
    for p in (1, 2, 3):
        ws.send_json({"type": "bot", "tavolo": tid, "posto": p, "aggiungi": True})
    if spettatori is not None:
        ws.send_json({"type": "imposta", "tavolo": tid, "spettatori": spettatori})
    ricevi_fino(ws, lambda m: m["type"] == "tavolo" and all(m["tavolo"]["posti"])
                and (spettatori is None or m["tavolo"]["spettatori_ammessi"] == spettatori))
    ws.send_json({"type": "avvia", "tavolo": tid})
    ricevi_fino(ws, lambda m: m["type"] == "stato")
    return tid


def carte_private(st):
    """Carte che uno spettatore non deve mai vedere: le mani senza Bazzica dichiarata."""
    return {c for s in range(4) if st.bazzica[s] is None for c in st.mani[s]}


def test_lo_spettatore_non_vede_le_carte_in_mano(tmp_path):
    """Partita Heisenberg (con scambio segreto) giocata in automatico: ogni messaggio inviato allo
    spettatore viene controllato nel momento dell'invio contro le mani in quel momento."""
    with nuovo_client(tmp_path) as c:
        m = c.manager
        inviati = []
        invia_vero = m.invia

        async def spia(token, msg):
            if token == "sss":
                tid_ = msg.get("tavolo")
                tav_ = m.tavoli.get(tid_) if isinstance(tid_, str) else None
                privati = carte_private(tav_.st) if tav_ and tav_.st else set()
                inviati.append((msg, privati))
            await invia_vero(token, msg)
        m.invia = spia
        with c.websocket_connect("/ws?token=aaa&nome=Anna") as a, c.websocket_connect("/ws?token=sss&nome=Sara") as sp:
            tid = tavolo_con_umano(a)
            tav = m.tavoli[tid]
            ricevi_fino(sp, lambda x: x["type"] == "lobby" and any(t["id"] == tid and t["guardabile"] for t in x["tavoli"]))
            sp.send_json({"type": "guarda", "tavolo": tid})
            st = ricevi_fino(sp, lambda x: x["type"] == "stato")
            assert st["spettatore"] and st["obs"]["pubblica"] and st["legali"] == []
            info_a = ricevi_fino(a, lambda x: x["type"] == "stato" and x["info"]["spettatori"])["info"]
            assert info_a["spettatori"] == ["Sara"]
            # Anna è "umana" ma gioca il timer al posto suo: la partita va avanti da sola
            async def timer_rapidi():
                tav.durata_scambio = tav.durata_giocata = 0.02
                tav.aggiorna_timer()
            c.portal.call(timer_rapidi)
            for _ in range(60):
                if tav.st.fase == "fine_mano" or tav.stato != "in_corso":
                    break
                time.sleep(0.1)
            assert tav.st.fase == "fine_mano"
        stati = [x for x, _ in inviati if x["type"] == "stato"]
        eventi = [x for x, _ in inviati if x["type"] == "eventi"]
        assert len(stati) > 10 and len(eventi) > 10
        for msg, privati in inviati:
            if msg["type"] == "stato":
                testo = json.dumps({k: v for k, v in msg["obs"].items() if k != "storico_mani"})
            elif msg["type"] == "eventi":
                testo = json.dumps([e for e in msg["eventi"] if e["tipo"] != "fine_mano"])
            else:
                testo = json.dumps(msg)
            for carta in privati:
                assert f'"{carta}"' not in testo, (carta, msg)
        tipi = {e["tipo"] for x in eventi for e in x["eventi"]}
        assert "giocata" in tipi and not tipi & {"carte_ricevute", "scambio_carta", "scambio_ricevuta"}
        assert all(e["visibile"] is None for x in eventi for e in x["eventi"])


def test_osservazione_pubblica_senza_mani(tmp_path):
    with nuovo_client(tmp_path, ritardo=(5, 5)) as c:          # bot lenti: lo stato resta fermo
        with c.websocket_connect("/ws?token=aaa&nome=Anna") as a:
            tid = tavolo_con_umano(a)
            tav = c.manager.tavoli[tid]
            obs = tav.osservazione_pubblica()
            assert obs["mano"] == [] and obs["mano_coperte"] == len(tav.st.mani[0]) == 3
            assert obs["scambio"]["distribuite"] == [] and obs["scambio"]["ricevuta"] is None
            assert all(v["carte"] is None for v in obs["altri"].values())
            testo = json.dumps(tav.messaggio_spettatore())
            for carta in carte_private(tav.st):
                assert f'"{carta}"' not in testo, carta


def test_frasi_degli_spettatori_arrivano_ai_giocatori(tmp_path):
    with nuovo_client(tmp_path, ritardo=(5, 5)) as c:
        with c.websocket_connect("/ws?token=aaa&nome=Anna") as a, c.websocket_connect("/ws?token=sss&nome=Sara") as sp:
            tid = tavolo_con_umano(a)
            sp.send_json({"type": "guarda", "tavolo": tid})
            ricevi_fino(sp, lambda m: m["type"] == "stato")
            # durante lo scambio i giocatori non parlano, gli spettatori sì (non conoscono le carte)
            assert c.manager.tavoli[tid].st.fase == "scambio"
            sp.send_json({"type": "frase", "tavolo": tid, "indice": FRASI.index("Che provocateur")})
            for ws in (a, sp):
                ev = ricevi_fino(ws, lambda m: m["type"] == "eventi" and any(e["tipo"] == "frase_spettatore" for e in m["eventi"]))
                e = ev["eventi"][0]
                assert (e["nome"], e["testo"]) == ("Sara", "Che provocateur")
            # anti-spam: una seconda frase subito dopo viene ignorata
            sp.send_json({"type": "frase", "tavolo": tid, "indice": 0})
            sp.send_json({"type": "frase", "tavolo": tid, "indice": 99})
            assert "sconosciuta" in ricevi_fino(sp, lambda m: m["type"] == "errore")["messaggio"]
            # chi non guarda non può mandare frasi da spettatore
        with c.websocket_connect("/ws?token=zzz&nome=Zeno") as z:
            z.send_json({"type": "frase", "tavolo": tid, "indice": 0})
            ricevi_fino(z, lambda m: m["type"] == "errore")


def test_il_continua_dello_spettatore_non_conta(tmp_path):
    with nuovo_client(tmp_path, ritardo=(5, 5)) as c:
        with c.websocket_connect("/ws?token=aaa&nome=Anna") as a, c.websocket_connect("/ws?token=sss&nome=Sara") as sp:
            tid = tavolo_con_umano(a)
            tav = c.manager.tavoli[tid]
            sp.send_json({"type": "guarda", "tavolo": tid})
            ricevi_fino(sp, lambda m: m["type"] == "stato")
            tav.st.fase = "fine_mano"                          # simulato: basta per il controllo
            sp.send_json({"type": "prosegui", "tavolo": tid})
            sp.send_json({"type": "lista"})
            ricevi_fino(sp, lambda m: m["type"] == "lobby")
            assert "sss" not in tav.ack


def test_spettatori_non_ammessi(tmp_path):
    with nuovo_client(tmp_path) as c:
        with c.websocket_connect("/ws?token=aaa&nome=Anna") as a, c.websocket_connect("/ws?token=sss&nome=Sara") as sp:
            tid = tavolo_con_umano(a, spettatori=False)
            lobby = ricevi_fino(sp, lambda m: m["type"] == "lobby"
                                and any(t["id"] == tid and t["stato"] == "in_corso" for t in m["tavoli"]))
            assert not next(t for t in lobby["tavoli"] if t["id"] == tid)["guardabile"]
            sp.send_json({"type": "guarda", "tavolo": tid})
            assert "spettatori" in ricevi_fino(sp, lambda m: m["type"] == "errore")["messaggio"]
            # chi è seduto non può fare lo spettatore della propria partita
            a.send_json({"type": "guarda", "tavolo": tid})
            assert "seduto" in ricevi_fino(a, lambda m: m["type"] == "errore")["messaggio"]
            # cambiare il permesso spetta a chi gestisce il tavolo, e non a partita in corso
            a.send_json({"type": "imposta", "tavolo": tid, "spettatori": True})
            ricevi_fino(a, lambda m: m["type"] == "errore")
