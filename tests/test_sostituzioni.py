"""Uscita dalla partita, sostituzione con un bot (uscita, inattività, disconnessione), rientro,
permessi per eliminare e modificare i tavoli."""
import time

from fastapi.testclient import TestClient

from bazzica.server.app import create_app
from bazzica.server.config import Config
from bazzica.server.tables import Manager, FRASI


def nuovo_client(tmp_path, **cfg):
    m = Manager(cartella_log=str(tmp_path / "logs"), db_path=str(tmp_path / "s.db"), ritardo_bot=(0, 0),
                pausa_fine_mano=0, config=Config(max_msg_secondo=0, **cfg))
    c = TestClient(create_app(m))
    c.manager = m
    return c


def ricevi_fino(ws, cond, max_msg=5000):
    for _ in range(max_msg):
        msg = ws.receive_json()
        if cond(msg):
            return msg
    raise AssertionError("messaggio atteso non ricevuto")


def eventi_di_tipo(tipo):
    return lambda m: m["type"] == "eventi" and any(e["tipo"] == tipo for e in m["eventi"])


def tavolo_due_umani(ws_a, ws_b, variante="Vanilla"):
    """A crea il tavolo e siede a Nord, B siede a Sud (compagni), due bot. Restituisce l'id."""
    ws_a.send_json({"type": "crea_tavolo", "variante": variante, "nome": "Prova"})
    tid = ricevi_fino(ws_a, lambda m: m["type"] == "tavolo")["tavolo"]["id"]
    ws_a.send_json({"type": "siedi", "tavolo": tid, "posto": 0, "nome": "Anna"})
    ws_b.send_json({"type": "siedi", "tavolo": tid, "posto": 2, "nome": "Bruno"})
    for p in (1, 3):
        ws_a.send_json({"type": "bot", "tavolo": tid, "posto": p, "aggiungi": True})
    ricevi_fino(ws_a, lambda m: m["type"] == "tavolo" and all(m["tavolo"]["posti"]))
    return tid


def avvia(c, ws, tid):
    ws.send_json({"type": "avvia", "tavolo": tid})
    ricevi_fino(ws, lambda m: m["type"] == "stato")
    return c.manager.tavoli[tid]


def aspetta(cond, secondi=5.0):
    fine = time.monotonic() + secondi
    while time.monotonic() < fine:
        if cond():
            return
        time.sleep(0.02)
    raise AssertionError("condizione non raggiunta")


def controlla(c, ora):
    return c.portal.call(c.manager.inattivita, ora)


# --------------------------------------------------------------------------- uscita e rientro

def test_esci_mette_un_bot_e_la_partita_continua(tmp_path):
    with nuovo_client(tmp_path) as c:
        with c.websocket_connect("/ws?token=aaa&nome=Anna") as a, c.websocket_connect("/ws?token=bbb&nome=Bruno") as b:
            tid = tavolo_due_umani(a, b)
            tav = avvia(c, a, tid)
            a.send_json({"type": "esci", "tavolo": tid})
            msg = ricevi_fino(a, lambda m: m["type"] == "sostituito")
            assert msg["motivo"] == "uscito" and not msg["interrotta"]
            info = ricevi_fino(a, lambda m: m["type"] == "tavolo")["tavolo"]
            assert info["miei"] == [] and info["sostituiti"] == [0]
            ev = ricevi_fino(b, eventi_di_tipo("sostituito"))
            e = next(e for e in ev["eventi"] if e["tipo"] == "sostituito")
            assert (e["seat"], e["nome"], e["motivo"]) == (0, "Anna", "uscito")
            assert tav.stato == "in_corso"
            assert tav.posti[0]["tipo"] == "bot" and tav.posti[0]["nome"] == "Anna (bot)"
            assert 0 in tav.agents
            # B vede il bot al posto di Anna
            st = ricevi_fino(b, lambda m: m["type"] == "stato")
            assert st["info"]["tipi"][0] == "bot"


def test_chi_esce_puo_riprendere_il_posto(tmp_path):
    with nuovo_client(tmp_path) as c:
        with c.websocket_connect("/ws?token=aaa&nome=Anna") as a, c.websocket_connect("/ws?token=bbb&nome=Bruno") as b:
            tid = tavolo_due_umani(a, b)
            tav = avvia(c, a, tid)
            a.send_json({"type": "esci", "tavolo": tid})
            ricevi_fino(a, lambda m: m["type"] == "sostituito")
            a.send_json({"type": "riprendi", "tavolo": tid})
            info = ricevi_fino(a, lambda m: m["type"] == "tavolo" and m["tavolo"]["miei"] == [0])["tavolo"]
            assert info["sostituiti"] == []
            st = ricevi_fino(a, lambda m: m["type"] == "stato" and m["posto"] == 0)
            assert st["info"]["tipi"][0] == "umano"
            ev = ricevi_fino(b, eventi_di_tipo("rientrato"))
            assert any(e["tipo"] == "rientrato" and e["seat"] == 0 for e in ev["eventi"])
            assert tav.posti[0] == {"tipo": "umano", "token": "aaa", "nome": "Anna", "avatar": tav.posti[0]["avatar"]}
            assert 0 not in tav.agents
            # chi non è mai stato sostituito non può "riprendere"
            b.send_json({"type": "riprendi", "tavolo": tid})
            assert "riprendere" in ricevi_fino(b, lambda m: m["type"] == "errore")["messaggio"]


def test_se_esce_l_ultimo_umano_la_partita_e_interrotta(tmp_path):
    with nuovo_client(tmp_path) as c:
        with c.websocket_connect("/ws?token=aaa&nome=Anna") as a:
            a.send_json({"type": "crea_tavolo", "variante": "Vanilla"})
            tid = ricevi_fino(a, lambda m: m["type"] == "tavolo")["tavolo"]["id"]
            a.send_json({"type": "siedi", "tavolo": tid, "posto": 0, "nome": "Anna"})
            for p in (1, 2, 3):
                a.send_json({"type": "bot", "tavolo": tid, "posto": p, "aggiungi": True})
            ricevi_fino(a, lambda m: m["type"] == "tavolo" and all(m["tavolo"]["posti"]))
            tav = avvia(c, a, tid)
            a.send_json({"type": "esci", "tavolo": tid})
            msg = ricevi_fino(a, lambda m: m["type"] == "sostituito")
            assert msg["interrotta"]
            assert tav.stato == "finita"
            r = c.get("/api/storico").json()
            righe = r if isinstance(r, list) else r.get("partite", [])
            assert righe and righe[0]["esito"] == "interrotta"
            # a partita finita non si può più "riprendere"
            a.send_json({"type": "riprendi", "tavolo": tid})
            ricevi_fino(a, lambda m: m["type"] == "errore")
            # tornati nella stanza, il posto è di un bot normale
            a.send_json({"type": "alzati", "tavolo": tid, "posto": 1})
            ricevi_fino(a, lambda m: m["type"] == "tavolo" and m["tavolo"]["stato"] == "lobby")
            assert tav.posti[0] == {"tipo": "bot", "nome": "Bot Nord", "avatar": "🤖"}


# --------------------------------------------------------------------------- inattività

def test_inattivo_da_5_minuti_viene_sostituito(tmp_path):
    with nuovo_client(tmp_path, inattivita_min=5) as c:
        with c.websocket_connect("/ws?token=aaa&nome=Anna") as a, c.websocket_connect("/ws?token=bbb&nome=Bruno") as b:
            tid = tavolo_due_umani(a, b)
            tav = avvia(c, a, tid)
            aspetta(lambda: tav.tokens_attesi())          # i bot giocano finché tocca a un umano
            fermo = next(iter(tav.tokens_attesi()))
            altro = "bbb" if fermo == "aaa" else "aaa"
            t0 = time.monotonic()
            assert controlla(c, t0) == []
            for i in range(1, 10):                         # 4 minuti e mezzo: ancora niente
                assert controlla(c, t0 + 30 * i) == []
            assert controlla(c, t0 + 300) == [(tid, fermo, "inattivo")]
            assert not tav.posti_di(fermo) and tav.sostituiti_di(fermo)
            assert tav.posti_di(altro)
            ws_fermo = a if fermo == "aaa" else b
            assert ricevi_fino(ws_fermo, lambda m: m["type"] == "sostituito")["motivo"] == "inattivo"


def test_un_azione_azzera_l_inattivita(tmp_path):
    with nuovo_client(tmp_path, inattivita_min=5) as c:
        with c.websocket_connect("/ws?token=aaa&nome=Anna") as a, c.websocket_connect("/ws?token=bbb&nome=Bruno") as b:
            tid = tavolo_due_umani(a, b)
            tav = avvia(c, a, tid)
            aspetta(lambda: tav.tokens_attesi())
            fermo = next(iter(tav.tokens_attesi()))
            t0 = time.monotonic()
            controlla(c, t0)
            for i in range(1, 9):
                controlla(c, t0 + 30 * i)
            assert tav.attesa[fermo] >= 240
            ws = a if fermo == "aaa" else b
            ws.send_json({"type": "frase", "tavolo": tid, "posto": tav.posti_di(fermo)[0], "indice": 0})
            aspetta(lambda: tav.attesa[fermo] == 0)
            assert controlla(c, t0 + 300) == []


def test_da_solo_contro_i_bot_non_si_viene_sostituiti(tmp_path):
    with nuovo_client(tmp_path, inattivita_min=5) as c:
        with c.websocket_connect("/ws?token=aaa&nome=Anna") as a:
            a.send_json({"type": "crea_tavolo", "variante": "Vanilla"})
            tid = ricevi_fino(a, lambda m: m["type"] == "tavolo")["tavolo"]["id"]
            a.send_json({"type": "siedi", "tavolo": tid, "posto": 0, "nome": "Anna"})
            for p in (1, 2, 3):
                a.send_json({"type": "bot", "tavolo": tid, "posto": p, "aggiungi": True})
            ricevi_fino(a, lambda m: m["type"] == "tavolo" and all(m["tavolo"]["posti"]))
            tav = avvia(c, a, tid)
            aspetta(lambda: tav.tokens_attesi())
            t0 = time.monotonic()
            for i in range(0, 40):
                assert controlla(c, t0 + 30 * i) == []
            assert tav.posti_di("aaa") == [0]


def test_disconnesso_da_5_minuti_viene_sostituito_e_la_pausa_finisce(tmp_path):
    with nuovo_client(tmp_path, inattivita_min=5) as c:
        with c.websocket_connect("/ws?token=aaa&nome=Anna") as a:
            with c.websocket_connect("/ws?token=bbb&nome=Bruno") as b:
                tid = tavolo_due_umani(a, b)
                tav = avvia(c, a, tid)
            aspetta(lambda: tav.in_pausa)
            t0 = time.monotonic()
            assert controlla(c, t0 + 60) == []
            assert controlla(c, t0 + 301) == [(tid, "bbb", "disconnesso")]
            assert not tav.in_pausa and tav.stato == "in_corso"
            assert tav.sostituiti_di("bbb") == [2]
            ricevi_fino(a, eventi_di_tipo("sostituito"))
        # Bruno torna: in lobby gli viene detto che può riprendere il posto
        with c.websocket_connect("/ws?token=bbb&nome=Bruno") as b:
            info = ricevi_fino(b, lambda m: m["type"] == "tavolo" and m["tavolo"]["id"] == tid)["tavolo"]
            assert info["sostituiti"] == [2]


def test_tutti_disconnessi_la_partita_resta_in_pausa(tmp_path):
    with nuovo_client(tmp_path, inattivita_min=5) as c:
        with c.websocket_connect("/ws?token=aaa&nome=Anna") as a, c.websocket_connect("/ws?token=bbb&nome=Bruno") as b:
            tid = tavolo_due_umani(a, b)
            tav = avvia(c, a, tid)
        aspetta(lambda: not c.manager.conn)
        t0 = time.monotonic()
        assert controlla(c, t0 + 3600) == []
        assert sorted(tav.tokens_umani()) == ["aaa", "bbb"]


def test_inattivita_disattivata(tmp_path):
    with nuovo_client(tmp_path, inattivita_min=0) as c:
        with c.websocket_connect("/ws?token=aaa&nome=Anna") as a:
            with c.websocket_connect("/ws?token=bbb&nome=Bruno") as b:
                tid = tavolo_due_umani(a, b)
                tav = avvia(c, a, tid)
            aspetta(lambda: tav.in_pausa)
            assert controlla(c, time.monotonic() + 10 * 3600) == []


# --------------------------------------------------------------------------- permessi

def test_eliminare_e_modificare_il_tavolo(tmp_path):
    with nuovo_client(tmp_path) as c:
        with c.websocket_connect("/ws?token=aaa&nome=Anna") as a, \
                c.websocket_connect("/ws?token=bbb&nome=Bruno") as b, \
                c.websocket_connect("/ws?token=ccc&nome=Carla") as estraneo:
            tid = tavolo_due_umani(a, b)
            info_b = ricevi_fino(b, lambda m: m["type"] == "tavolo" and all(m["tavolo"]["posti"]))["tavolo"]
            assert info_b["gestore"] and info_b["puo_eliminare"] and not info_b["owner"]
            # chi è seduto (non creatore) può cambiare le impostazioni
            b.send_json({"type": "imposta", "tavolo": tid, "variante": "Pascal"})
            ricevi_fino(b, lambda m: m["type"] == "tavolo" and m["tavolo"]["variante"] == "Pascal")
            # un estraneo no, né può eliminare un tavolo con giocatori connessi
            estraneo.send_json({"type": "apri", "tavolo": tid})
            info_c = ricevi_fino(estraneo, lambda m: m["type"] == "tavolo")["tavolo"]
            assert not info_c["gestore"] and not info_c["puo_eliminare"]
            estraneo.send_json({"type": "imposta", "tavolo": tid, "variante": "Vanilla"})
            ricevi_fino(estraneo, lambda m: m["type"] == "errore")
            estraneo.send_json({"type": "elimina", "tavolo": tid})
            ricevi_fino(estraneo, lambda m: m["type"] == "errore")
            assert tid in c.manager.tavoli
            # partita in corso: B (seduto, non creatore) la elimina; A vede "interrotta"
            avvia(c, a, tid)
            b.send_json({"type": "elimina", "tavolo": tid})
            st = ricevi_fino(a, lambda m: m["type"] == "stato" and m["info"]["stato"] == "finita")
            assert st["info"]["terminata_da"] == "Bruno"
            ricevi_fino(a, lambda m: m["type"] == "lobby" and not m["tavoli"])
            assert tid not in c.manager.tavoli


def test_tavolo_abbandonato_lo_elimina_chiunque(tmp_path):
    with nuovo_client(tmp_path) as c:
        with c.websocket_connect("/ws?token=aaa&nome=Anna") as a:
            a.send_json({"type": "crea_tavolo", "variante": "Vanilla"})
            tid = ricevi_fino(a, lambda m: m["type"] == "tavolo")["tavolo"]["id"]
            a.send_json({"type": "siedi", "tavolo": tid, "posto": 0, "nome": "Anna"})
            for p in (1, 2, 3):
                a.send_json({"type": "bot", "tavolo": tid, "posto": p, "aggiungi": True})
            ricevi_fino(a, lambda m: m["type"] == "tavolo" and all(m["tavolo"]["posti"]))
            avvia(c, a, tid)
        with c.websocket_connect("/ws?token=zzz&nome=Zeno") as z:
            lobby = ricevi_fino(z, lambda m: m["type"] == "lobby")
            t = next(t for t in lobby["tavoli"] if t["id"] == tid)
            assert t["puo_eliminare"] and not t["gestore"]
            z.send_json({"type": "elimina", "tavolo": tid})
            ricevi_fino(z, lambda m: m["type"] == "lobby" and not m["tavoli"])


def test_nuova_frase_che_provocateur(tmp_path):
    assert "Che provocateur" in FRASI
    with nuovo_client(tmp_path) as c:
        with c.websocket_connect("/ws?token=aaa&nome=Anna") as a, c.websocket_connect("/ws?token=bbb&nome=Bruno") as b:
            tid = tavolo_due_umani(a, b)
            tav = avvia(c, a, tid)
            aspetta(lambda: tav.st.fase == "gioco")
            a.send_json({"type": "frase", "tavolo": tid, "posto": 0, "indice": FRASI.index("Che provocateur")})
            ev = ricevi_fino(b, eventi_di_tipo("frase"))
            assert ev["eventi"][0]["testo"] == "Che provocateur"
