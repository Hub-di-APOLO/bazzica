"""Striscia: finestra garantita contro i bot, Striscia arrivata appena dopo il turno, bot che giocano di fretta
quando sono strisciati, bot che strisciano verso il giocatore umano che li precede."""
import asyncio
import time

import pytest

from bazzica.engine import legal_actions, apply_inplace, FASE_GIOCO
from bazzica.server import tables as T
from bazzica.server.config import Config
from bazzica.server.tables import Manager, Tavolo, RITMI


class FintoWS:
    def __init__(self):
        self.msgs = []

    async def send_json(self, m):
        self.msgs.append(m)


def manager(tmp_path, attesa=True):
    return Manager(cartella_log=str(tmp_path / "logs"), db_path=str(tmp_path / "s.db"), ritardo_bot=(0, 0),
                   pausa_fine_mano=0, config=Config(), attesa_giocatori=attesa)


def tavolo(m):
    """Umano "u1" al posto 0 (Nord), bot negli altri: il bot che lo precede è al posto 3, quello dopo al posto 1."""
    t = Tavolo(m, "t1", "Prova", "u1", "Vanilla", False)
    m.tavoli["t1"] = t
    ws = FintoWS()
    m.conn["u1"] = {ws}
    m.nomi["u1"] = "u1"
    t.siedi("u1", 0, "u1")
    for p in (1, 2, 3):
        t.bot(p, True)
    t.ws = ws
    return t


@pytest.fixture
def ritmi(monkeypatch):
    nuovi = {k: dict(v, tetto=2.0, respiro=0.0, finestra=0.6) for k, v in RITMI.items()}
    monkeypatch.setattr(T, "RITMI", nuovi)
    monkeypatch.setattr(T, "PROB_STRISCIA_BOT", 0.0)
    monkeypatch.setattr(T, "PROB_STRISCIA_BOT_PERICOLO", 0.0)
    return nuovi


def giocate(t):
    return len(t.st.giocate_mano) + 100 * t.st.mano_n


async def porta_a(t, posto):
    """Fa giocare tutti (subito) finché non tocca a ``posto`` nella fase di gioco."""
    await t.gestisci_eventi(t.avvia())
    for _ in range(12):
        st = t.st
        if st.fase == FASE_GIOCO and st.corrente == posto:
            return
        s = st.corrente
        a = next(a for a in legal_actions(st, s) if a.tipo == "gioca")
        if t.posti[s]["tipo"] == "umano":
            await t.azione_umana("u1", s, a.to_dict())
        else:
            await t.gestisci_eventi(apply_inplace(st, a))
    raise AssertionError("turno non raggiunto")


def strisce(t):
    return [e for m in t.ws.msgs if m["type"] == "eventi" for e in m["eventi"] if e["tipo"] == "striscia"]


async def gioca_entro(t, g, secondi):
    """Aspetta che il bot giochi; intanto il client conferma ogni nuova versione (il bot può dichiarare la
    Bazzica prima di giocare, e allora si riparte dal nuovo "visto")."""
    inizio = time.monotonic()
    while giocate(t) == g and time.monotonic() - inizio < secondi:
        if t.visti.get("u1", -1) < t.versione:
            await t.visto("u1", t.versione)
        await asyncio.sleep(0.02)
    return time.monotonic() - inizio


# --------------------------------------------------------------------------- finestra garantita

def test_il_bot_che_precede_un_umano_lascia_il_tempo_per_strisciare(tmp_path, ritmi):
    m = manager(tmp_path)

    async def corpo():
        t = tavolo(m)
        await porta_a(t, 3)
        g = giocate(t)
        await t.visto("u1", t.versione)
        t.sveglia()
        attesa = await gioca_entro(t, g, 3)
        assert giocate(t) > g and 0.55 <= attesa < 1.6        # almeno la finestra dopo il "visto"
        t.task.cancel()
    asyncio.run(corpo())


def test_il_bot_seguito_da_un_bot_non_aspetta_la_finestra(tmp_path, ritmi):
    m = manager(tmp_path)

    async def corpo():
        t = tavolo(m)
        await porta_a(t, 1)                                       # dopo il posto 1 c'è il bot del posto 2
        g = giocate(t)
        await t.visto("u1", t.versione)
        t.sveglia()
        attesa = await gioca_entro(t, g, 3)
        assert giocate(t) > g and attesa < 0.4
        t.task.cancel()
    asyncio.run(corpo())


def test_il_bot_strisciato_gioca_di_fretta(tmp_path, ritmi):
    ritmi["rilassato"]["finestra"] = 5.0
    m = manager(tmp_path)

    async def corpo():
        t = tavolo(m)
        await porta_a(t, 3)
        g = giocate(t)
        await t.visto("u1", t.versione)
        t.sveglia()
        await gioca_entro(t, g, 0.3)
        assert giocate(t) == g                                    # finestra lunga: il bot aspetta
        await t.striscia("u1", 0, t.versione)
        assert strisce(t)[-1] == {"tipo": "striscia", "seat": 0, "verso": 3, "visibile": None}
        attesa = await gioca_entro(t, g, 2)
        assert giocate(t) > g and attesa <= T.FRETTA_STRISCIA + 0.25
        t.task.cancel()
    asyncio.run(corpo())


# --------------------------------------------------------------------------- Striscia appena dopo il turno

def test_striscia_appena_dopo_il_turno_vale_se_si_guardava_quel_turno(tmp_path, ritmi):
    m = manager(tmp_path)

    async def corpo():
        t = tavolo(m)
        await porta_a(t, 3)
        vista = t.versione                                        # il client mostra il turno del bot
        a = next(a for a in legal_actions(t.st, 3) if a.tipo == "gioca")
        await t.gestisci_eventi(apply_inplace(t.st, a))         # il bot ha appena giocato
        assert t.st.corrente != 3
        await t.striscia("u1", 0)                                 # senza versione: turno passato, ignorata
        assert not strisce(t)
        await t.striscia("u1", 0, t.versione)                     # versione già dopo la giocata: ignorata
        assert not strisce(t)
        await t.striscia("u1", 0, vista)                          # stava guardando quel turno: vale
        assert len(strisce(t)) == 1
        t.ultima_striscia[0] = 0
        inizio, fine, quando = t.turni_finiti[3]
        t.turni_finiti[3] = (inizio, fine, quando - T.GRAZIA_STRISCIA - 0.1)
        await t.striscia("u1", 0, vista)                          # troppo tardi
        assert len(strisce(t)) == 1
    asyncio.run(corpo())


def test_striscia_versione_validata_e_anti_spam(tmp_path, ritmi):
    m = manager(tmp_path)

    async def corpo():
        t = tavolo(m)
        await porta_a(t, 3)
        for cattiva in ("3", 1.5, True, -1, t.versione + 1):
            with pytest.raises(ValueError):
                await t.striscia("u1", 0, cattiva)
        with pytest.raises(ValueError):
            await t.striscia("u1", 2)                             # posto non suo
        await t.striscia("u1", 0, t.versione)
        await t.striscia("u1", 0, t.versione)                     # entro la pausa: ignorata
        assert len(strisce(t)) == 1
    asyncio.run(corpo())


def test_striscia_ignorata_se_non_tocca_al_precedente(tmp_path, ritmi):
    m = manager(tmp_path)

    async def corpo():
        t = tavolo(m)
        await porta_a(t, 1)
        await t.striscia("u1", 0, t.versione)
        assert not strisce(t)
    asyncio.run(corpo())


# --------------------------------------------------------------------------- i bot strisciano

def test_il_bot_striscia_verso_l_umano_che_lo_precede(tmp_path, ritmi, monkeypatch):
    monkeypatch.setattr(T, "PROB_STRISCIA_BOT", 1.0)
    monkeypatch.setattr(T, "PROB_STRISCIA_BOT_PERICOLO", 1.0)
    monkeypatch.setattr(T, "ATTESA_STRISCIA_BOT", (0.05, 0.1))
    m = manager(tmp_path)

    async def corpo():
        t = tavolo(m)
        await porta_a(t, 0)
        await asyncio.sleep(0.3)
        assert not strisce(t)                                     # prima l'umano deve vedere che tocca a lui
        await t.visto("u1", t.versione)
        await asyncio.sleep(0.4)
        assert strisce(t) == [{"tipo": "striscia", "seat": 1, "verso": 0, "visibile": None}]
        await asyncio.sleep(0.3)
        assert len(strisce(t)) == 1                               # una sola volta per turno
    asyncio.run(corpo())


def test_il_bot_non_striscia_se_il_turno_e_passato(tmp_path, ritmi, monkeypatch):
    monkeypatch.setattr(T, "PROB_STRISCIA_BOT", 1.0)
    monkeypatch.setattr(T, "PROB_STRISCIA_BOT_PERICOLO", 1.0)
    monkeypatch.setattr(T, "ATTESA_STRISCIA_BOT", (0.3, 0.3))
    m = manager(tmp_path)

    async def corpo():
        t = tavolo(m)
        await porta_a(t, 0)
        await t.visto("u1", t.versione)
        a = next(a for a in legal_actions(t.st, 0) if a.tipo == "gioca")
        await t.azione_umana("u1", 0, a.to_dict())               # l'umano gioca subito
        await asyncio.sleep(0.5)
        assert not strisce(t)
    asyncio.run(corpo())


def test_niente_strisce_dei_bot_con_bot_istantanei(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "PROB_STRISCIA_BOT", 1.0)
    monkeypatch.setattr(T, "PROB_STRISCIA_BOT_PERICOLO", 1.0)
    m = manager(tmp_path, attesa=False)

    async def corpo():
        t = tavolo(m)
        await porta_a(t, 0)
        assert t.striscia_bot_task is None
    asyncio.run(corpo())


def test_pericolo_per_il_bot(tmp_path):
    m = manager(tmp_path)

    async def corpo():
        t = tavolo(m)
        await t.gestisci_eventi(t.avvia())
        st = t.st
        st.mani[1] = ["coppe_05"]
        st.tavola = ["denari_02"]
        assert t.pericolo_per(1)                                  # tavolo quasi vuoto
        st.tavola = ["denari_02", "spade_01", "bastoni_02", "coppe_07", "spade_09"]
        assert not t.pericolo_per(1)
        st.mani[1] = ["coppe_07", "spade_10"]
        st.tavola = ["denari_02", "spade_01", "bastoni_03", "coppe_04"]
        assert t.pericolo_per(1)                                  # il 10 prende tutto (2+1+3+4)
        st.mani[1] = []
        assert not t.pericolo_per(1)
    asyncio.run(corpo())
