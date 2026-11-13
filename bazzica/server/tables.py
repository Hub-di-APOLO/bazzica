"""Tavoli, lobby, giocatori connessi e ciclo di gioco (bot, pause, riconnessioni)."""
from __future__ import annotations

import asyncio
import random
import secrets
import time
from typing import Optional

from ..engine import (preset, VARIANTI, new_game, legal_actions, apply_inplace, observation, Action,
                      required_actors, optional_actors, system_action, anteprima, IllegalAction,
                      NOMI_POSTI, NOMI_SQUADRE, compagno, descrivi_opzione, opzioni_bazzica,
                      FASE_FINE_MANO, FASE_FINE_PARTITA, FASE_SCAMBIO, FASE_GIOCO)
from ..engine.game import ev
from ..bots import HeuristicAgent
from . import ele as ELE
from .account import Account, account_da_identita, normalizza_nome
from .config import Config
from .log import GameLogger
from .storico import Storico

NOMI_BOT = ["Bot Nord", "Bot Est", "Bot Sud", "Bot Ovest"]
AVATAR = ["🦊", "🐻", "🐸", "🦁", "🐼", "🐵", "🦉", "🐙", "🐱", "🐲", "🐢", "🦭"]
AVATAR_BOT = "🤖"
FRASI = ["Veloce?!?", "Di#p?@co", "Praticamente pari", "Che culo...", "Aperta come...",
         "Faccio una giocata un po' particolare", "Stai giocando con paura", "Sei MATTO?!", "Ma hai tutti gli assi??", "CHE CULO",
         "Che provocateur"]


class Tavolo:
    def __init__(self, manager: "Manager", tid: str, nome: str, owner: str, variante: str, margherita: bool):
        self.m = manager
        self.id = tid
        self.nome = nome
        self.owner = owner
        self.variante = variante
        self.margherita = margherita
        self.posti: list[Optional[dict]] = [None] * 4
        self.stato = "lobby"
        self.st = None
        self.agents = {}
        self.logger: Optional[GameLogger] = None
        self.partita_id = None
        self.ack: set = set()
        self.task: Optional[asyncio.Task] = None
        self.lock = asyncio.Lock()
        self.ultimo_evento = time.monotonic()
        self.ultima_attivita = time.monotonic()  # comandi ed eventi: serve alla pulizia automatica
        self.senza_umani_da = None             # da quando la partita è senza umani connessi
        self.creato = time.time()
        self.ultimo_palo = [0.0] * 4
        self.ultima_striscia = [0.0] * 4
        self.squadre = list(NOMI_SQUADRE)      # nomi delle squadre scelti nella stanza
        self.timer_attivo = True
        self.durata_scambio = None             # secondi; None = predefinito (nessuno), 0 = nessun timer
        self.durata_giocata = None             # secondi; None = predefinito (nessuno), 0 = nessun timer
        self.spettatori: dict = {}             # token -> ultima versione vista
        self.spettatori_ammessi = True         # se False si possono guardare solo le partite tra soli bot
        self.ultima_frase_spett: dict = {}     # token dello spettatore -> ora dell'ultima frase
        self.versione = 0                      # cresce a ogni gruppo di eventi
        self.timer_chiave = None
        self.timer_task: Optional[asyncio.Task] = None
        self.timer_scadenza = None             # time.monotonic() della scadenza
        self.timer_totale = 0.0
        self.terminata_da = None
        self.attesa: dict = {}                 # token -> secondi in cui tocca a lui senza che agisca
        self.disconnesso_da: dict = {}         # token -> time.monotonic() della disconnessione
        self.ultimo_controllo = None           # ultimo controllo dell'inattività
        self.valutata = False                  # partita valutata eLE (deciso all'avvio)
        self.raccoglitore = None               # statistiche per posto della partita valutata
        self.esito_ele = None                  # variazioni di eLE dell'ultima partita valutata

    # ------------------------------------------------------------------ info
    def tokens_umani(self):
        return {p["token"] for p in self.posti if p and p["tipo"] == "umano"}

    def posti_di(self, token):
        return [s for s, p in enumerate(self.posti) if p and p["tipo"] == "umano" and p["token"] == token]

    def sostituiti_di(self, token):
        """Posti in cui ``token`` è stato sostituito da un bot durante la partita in corso."""
        return [s for s, p in enumerate(self.posti)
                if p and p.get("sostituisce") and p["sostituisce"]["token"] == token]

    def puo_gestire(self, token):
        """Creatore del tavolo o giocatore seduto: può cambiare impostazioni, terminare, eliminare."""
        return token == self.owner or token in self.tokens_umani()

    def abbandonato(self):
        """Nessun giocatore seduto connesso e creatore non connesso."""
        return not any(self.m.connesso(k) for k in self.tokens_umani() | {self.owner})

    def puo_eliminare(self, token):
        return self.puo_gestire(token) or self.abbandonato()

    def solo_bot(self):
        return not self.tokens_umani()

    def guardabile(self, token=None):
        """Si può guardare: partita in corso, spettatori ammessi (sempre tra soli bot), e non ci si è seduti."""
        if self.stato != "in_corso" or (token is not None and self.posti_di(token)):
            return False
        return self.solo_bot() or self.spettatori_ammessi

    def nomi_spettatori(self):
        return [self.m.nome_di(t) for t in self.spettatori if not self.posti_di(t)]

    def nomi(self):
        return [p["nome"] if p else "—" for p in self.posti]

    def disconnessi(self):
        return [p["nome"] for p in self.posti
                if p and p["tipo"] == "umano" and not self.m.connesso(p["token"])]

    @property
    def in_pausa(self):
        return self.stato == "in_corso" and bool(self.disconnessi())

    def info(self, token=None):
        return {
            "miei": self.posti_di(token) if token else [],
            "owner": token is not None and token == self.owner,
            "gestore": token is not None and self.puo_gestire(token),
            "puo_eliminare": token is not None and self.puo_eliminare(token),
            "sostituiti": self.sostituiti_di(token) if token and self.stato == "in_corso" else [],
            "id": self.id, "nome": self.nome, "variante": self.variante, "margherita": self.margherita,
            "squadre": list(self.squadre), "timer": self.timer_attivo,
            "timer_scambio": self.secondi_timer("scambio"), "timer_giocata": self.secondi_timer("giocata"),
            "guardabile": self.guardabile(token),
            "spettatori": len(self.spettatori),
            "spettatori_ammessi": self.spettatori_ammessi,
            "stato": self.stato, "owner_nome": self.m.nome_di(self.owner),
            "posti": [None if p is None else {"tipo": p["tipo"], "nome": p["nome"], "avatar": p.get("avatar"),
                                               "connesso": p["tipo"] == "bot" or self.m.connesso(p["token"]),
                                               **self.m.ele_pubblico(p.get("account_id"))}
                      for p in self.posti],
            "punteggi": list(self.st.punteggi) if self.st else None,
            "valutata": self.info_valutazione(),
            "anteprima_ele": self.anteprima_ele(),
        }

    # ------------------------------------------------------------------ eLE
    def valutazione(self):
        """(valutabile, motivo): serve che i 4 posti siano di 4 account diversi (niente bot, ospiti
        o più posti dallo stesso giocatore)."""
        if any(p is None for p in self.posti):
            return False, "Servono 4 giocatori con account"
        for s, p in enumerate(self.posti):
            if p["tipo"] == "bot":
                return False, f"C'è un bot ({NOMI_POSTI[s]})"
        for p in self.posti:
            if not p.get("account_id"):
                return False, f"{p['nome']} gioca come ospite"
        if len({p["token"] for p in self.posti}) < 4 or len({p["account_id"] for p in self.posti}) < 4:
            return False, "Un giocatore occupa più posti"
        return True, ""

    def info_valutazione(self):
        if self.stato == "in_corso":
            return {"si": self.valutata, "motivo": "" if self.valutata else "Partita non valutata"}
        si, motivo = self.valutazione()
        return {"si": si, "motivo": motivo}

    def anteprima_ele(self):
        """eLE delle squadre e probabilità di vittoria, se tutti e 4 i posti hanno un account."""
        ids = []
        for p in self.posti:
            aid = (p or {}).get("account_id") or ((p or {}).get("sostituisce") or {}).get("account_id")
            if not aid:
                return None
            ids.append(aid)
        valori = [self.m.ele_cache_di(a)["ele"] for a in ids]
        sq = [(valori[0] + valori[2]) / 2, (valori[1] + valori[3]) / 2]
        return {"ele_squadre": [round(x) for x in sq], "probabilita": round(ELE.atteso(sq[0], sq[1]), 3)}

    def valuta_fine(self, vincitore, punteggi):
        """Aggiorna l'eLE a fine partita; restituisce l'evento pubblico ``ele`` (o None)."""
        if not self.valutata or not self.raccoglitore:
            return None
        posti = []
        for s, p in enumerate(self.posti):
            sost = p.get("sostituisce")
            aid = sost["account_id"] if sost else p.get("account_id")
            if not aid:
                return None   # non dovrebbe succedere: la partita era valutata all'avvio
            posti.append({"account_id": aid, "abbandono": bool(sost), "stat": self.raccoglitore.posti[s]})
        risultati = self.m.storico.registra_valutazione(self.partita_id, punteggi, vincitore, posti)
        variazioni = []
        for s, r in enumerate(risultati):
            self.m.aggiorna_ele_cache(r["account_id"], r["dopo"], r["partite"])
            p = self.posti[s]
            nome = p["sostituisce"]["nome"] if p.get("sostituisce") else p["nome"]
            variazioni.append({"posto": s, "nome": nome, "prima": round(r["prima"], 2), "dopo": round(r["dopo"], 2),
                               "delta": round(r["delta"], 2), "esito": r["esito"],
                               "provvisorio": ELE.provvisorio(r["partite"]), "dettaglio": r["dettaglio"]})
        self.esito_ele = variazioni
        return ev("ele", variazioni=variazioni,
                  spettacolo=round(ELE.moltiplicatore_spettacolo(punteggi[0], punteggi[1]), 4))

    # ------------------------------------------------------------------ lobby
    def siedi(self, token, posto, nome, avatar=None):
        if self.stato != "lobby":
            raise ValueError("La partita è già iniziata")
        if self.posti[posto] is not None:
            raise ValueError("Posto occupato")
        if avatar not in AVATAR:
            avatar = self.m.avatar.get(token) or AVATAR[posto]
        posto_d = {"tipo": "umano", "token": token, "nome": nome[:24] or "Giocatore", "avatar": avatar}
        aid = account_da_identita(token)
        if aid and not any(p.get("account_id") for p in (self.posti[s] for s in self.posti_di(token))):
            # il primo posto di un account è il giocatore dell'account, con il suo nome
            posto_d["nome"] = self.m.nome_di(token)
            posto_d["account_id"] = aid
        elif self.m.nome_riservato(posto_d["nome"]):
            raise ValueError("Questo nome appartiene a un account: scegline un altro")
        self.posti[posto] = posto_d

    def alzati(self, token, posto):
        if self.stato != "lobby":
            raise ValueError("La partita è già iniziata")
        p = self.posti[posto]
        if p and (p["tipo"] == "bot" or p["token"] == token or token == self.owner):
            self.posti[posto] = None

    def bot(self, posto, aggiungi: bool):
        if self.stato != "lobby":
            raise ValueError("La partita è già iniziata")
        if aggiungi:
            if self.posti[posto] is not None:
                raise ValueError("Posto occupato")
            self.posti[posto] = {"tipo": "bot", "nome": NOMI_BOT[posto], "avatar": AVATAR_BOT}
        elif self.posti[posto] and self.posti[posto]["tipo"] == "bot":
            self.posti[posto] = None

    # ------------------------------------------------------------------ partita
    def avvia(self):
        if self.stato == "in_corso":
            raise ValueError("Partita già in corso")
        if any(p is None for p in self.posti):
            raise ValueError("Servono 4 giocatori (umani o bot)")
        rules = preset(self.variante, self.margherita)
        seed = random.randrange(1 << 30)
        self.st, events = new_game(rules, seed=seed)
        self.agents = {s: HeuristicAgent(seed=seed + s) for s, p in enumerate(self.posti) if p["tipo"] == "bot"}
        self.stato = "in_corso"
        self.ack = set()
        self.terminata_da = None
        self.attesa = {}
        self.disconnesso_da = {}
        self.ultimo_controllo = None
        self.valutata, _ = self.valutazione()
        self.raccoglitore = ELE.Raccoglitore(rules) if self.valutata else None
        self.esito_ele = None
        self.logger = GameLogger(self.m.cartella_log, self.nome, rules.descrizione(), self.nomi(), self.squadre)
        self.logger.nota(f"Seed: {seed}")
        giocatori = [{"nome": p["nome"], "bot": p["tipo"] == "bot", "posto": NOMI_POSTI[s],
                      "squadra": self.squadre[s % 2], "account": bool(p.get("account_id"))}
                     for s, p in enumerate(self.posti)]
        self.partita_id = self.m.storico.nuova_partita(self.nome, self.variante, self.margherita, giocatori,
                                                       self.logger.path, valutata=self.valutata)
        if self.valutata:
            self.logger.nota("Partita valutata eLE")
        return events

    def termina(self, motivo="interrotta", da=None):
        if self.stato == "in_corso" and self.partita_id:
            self.m.storico.chiudi_partita(self.partita_id, motivo, self.st.punteggi)
            if self.logger:
                self.logger.nota(f"\nPartita {motivo}" + (f" da {da}." if da else "."))
        if self.stato == "in_corso":
            self.terminata_da = da
        self.stato = "finita"
        self.ferma_timer()

    def torna_in_lobby(self):
        if self.stato == "in_corso":
            raise ValueError("Partita in corso")
        self.stato = "lobby"
        self.st = None
        # i bot che sostituivano un giocatore restano come bot normali
        for s, p in enumerate(self.posti):
            if p and p.get("sostituisce"):
                self.posti[s] = {"tipo": "bot", "nome": NOMI_BOT[s], "avatar": AVATAR_BOT}

    # ------------------------------------------------------------------ sostituzioni (uscita, inattività)
    def sostituisci(self, token, motivo):
        """Mette un bot al posto di ``token`` (tutti i suoi posti). Restituisce gli eventi."""
        events = []
        for s in self.posti_di(token):
            p = self.posti[s]
            self.posti[s] = {"tipo": "bot", "nome": f"{p['nome']} (bot)"[:30], "avatar": AVATAR_BOT,
                             "sostituisce": {"token": token, "nome": p["nome"], "avatar": p.get("avatar"),
                                             "account_id": p.get("account_id")}}
            self.agents[s] = HeuristicAgent(seed=random.randrange(1 << 30))
            events.append(ev("sostituito", seat=s, nome=p["nome"], motivo=motivo))
        self.ack.discard(token)
        self.attesa.pop(token, None)
        self.disconnesso_da.pop(token, None)
        return events

    async def applica_sostituzione(self, token, motivo):
        """Sostituisce ``token`` con un bot e avvisa tutti; se non resta nessun umano la partita è interrotta."""
        events = self.sostituisci(token, motivo)
        if not events:
            return
        if not self.tokens_umani():
            if self.logger:
                self.logger.scrivi(events)
            self.termina(motivo="interrotta")
            if self.logger:
                self.logger.nota("(nessun giocatore rimasto al tavolo)")
        else:
            await self.gestisci_eventi(events)
        await self.m.invia(token, {"type": "sostituito", "tavolo": self.id, "motivo": motivo,
                                   "interrotta": self.stato != "in_corso"})
        await self.m.invia(token, {"type": "tavolo", "tavolo": self.info(token)})
        await self.m.invia_lobby()
        self.sveglia()

    async def esci(self, token):
        """Il giocatore lascia la partita: al suo posto gioca un bot (può rientrare più tardi)."""
        async with self.lock:
            if self.stato != "in_corso":
                raise ValueError("Nessuna partita in corso")
            if not self.posti_di(token):
                raise ValueError("Non sei seduto a questo tavolo")
            await self.applica_sostituzione(token, "uscito")

    async def riprendi(self, token):
        """Chi era stato sostituito da un bot riprende i suoi posti (con le carte che ha il bot)."""
        async with self.lock:
            if self.stato != "in_corso":
                raise ValueError("La partita è finita")
            posti = self.sostituiti_di(token)
            if not posti:
                raise ValueError("Non hai posti da riprendere a questo tavolo")
            events = []
            self.spettatori.pop(token, None)
            for s in posti:
                vecchio = self.posti[s]["sostituisce"]
                self.posti[s] = {"tipo": "umano", "token": token, "nome": vecchio["nome"], "avatar": vecchio["avatar"]}
                if vecchio.get("account_id"):
                    self.posti[s]["account_id"] = vecchio["account_id"]
                self.agents.pop(s, None)
                events.append(ev("rientrato", seat=s, nome=vecchio["nome"]))
            self.attesa[token] = 0.0
            await self.m.invia(token, {"type": "tavolo", "tavolo": self.info(token)})
            await self.gestisci_eventi(events)
        self.sveglia()

    def tokens_attesi(self):
        """Giocatori umani da cui la partita sta aspettando una mossa (o il "Continua" di fine Mano)."""
        st = self.st
        if self.stato != "in_corso" or not st or self.in_pausa:
            return set()
        if st.fase == FASE_FINE_MANO:
            return self.tokens_umani() - self.ack
        out = set()
        for s in required_actors(st):
            p = self.posti[s]
            if p and p["tipo"] == "umano" and any(a.tipo != "attendi" for a in legal_actions(st, s)):
                out.add(p["token"])
        return out

    def attivo(self, token):
        """Il giocatore ha fatto qualcosa: si azzera il suo tempo di inattività."""
        if token in self.attesa:
            self.attesa[token] = 0.0

    def da_sostituire(self, ora, limite):
        """Giocatori da sostituire per inattività: (token, motivo). Aggiorna i contatori.

        Si sostituisce solo se c'è almeno un altro giocatore umano connesso che sta aspettando:
        da soli contro i bot (o tutti disconnessi) la partita aspetta, come prima."""
        dt = 0.0 if self.ultimo_controllo is None else min(max(0.0, ora - self.ultimo_controllo), 30.0)
        self.ultimo_controllo = ora
        if self.stato != "in_corso" or not self.st:
            self.attesa.clear()
            self.disconnesso_da.clear()
            return []
        umani = self.tokens_umani()
        connessi = {t for t in umani if self.m.connesso(t)}
        for t in list(self.attesa):
            if t not in umani:
                del self.attesa[t]
        for t in list(self.disconnesso_da):
            if t not in umani or t in connessi:
                del self.disconnesso_da[t]
        attesi = self.tokens_attesi()
        out = []
        for t in sorted(umani):
            altri = bool(connessi - {t})
            if t not in connessi:
                da = self.disconnesso_da.setdefault(t, ora)
                if limite and altri and ora - da >= limite - 1e-6:
                    out.append((t, "disconnesso"))
                continue
            if t in attesi:
                self.attesa[t] = self.attesa.get(t, 0.0) + dt
            else:
                self.attesa.setdefault(t, 0.0)
            if limite and altri and self.attesa[t] >= limite - 1e-6:     # tolleranza sugli arrotondamenti
                out.append((t, "inattivo"))
        return out

    # ------------------------------------------------------------------ messaggi
    def _legali_dettaglio(self, s):
        st = self.st
        legal = legal_actions(st, s)
        out = []
        ops = {o["sette"]: o for o in opzioni_bazzica(st.mani[s], st.rules)} if any(
            a.tipo == "bazzica" for a in legal) else {}
        for a in legal:
            if a.tipo == "attendi":
                continue
            d = a.to_dict()
            d["descrizione"] = a.descrivi()
            if a.tipo == "gioca":
                d["anteprima"] = anteprima(st, a)
            if a.tipo == "bazzica":
                op = ops[a.sette]
                d["opzione"] = op
                d["descrizione"] = descrivi_opzione(op)
            out.append(d)
        return out

    def messaggio_stato(self, s):
        st = self.st
        obs = observation(st, s)
        return {
            "type": "stato", "tavolo": self.id, "posto": s, "obs": obs,
            "legali": self._legali_dettaglio(s),
            "info": self.info_partita(),
        }

    def info_partita(self):
        st = self.st
        return {
            "versione": self.versione,
            "nomi": self.nomi(),
            "tipi": [p["tipo"] for p in self.posti],
            "avatar": [p.get("avatar") for p in self.posti],
            "pausa": self.disconnessi() if self.stato == "in_corso" else [],
            "stato": self.stato,
            "attesa_ack": st.fase == FASE_FINE_MANO,
            "ack": [self.m.nome_di(t) for t in self.ack],
            "variante": st.rules.descrizione(),
            "squadre": list(self.squadre),
            "terminata_da": self.terminata_da,
            "timer": self.info_timer(),
            "spettatori": self.nomi_spettatori(),
            "ele": [self.m.ele_pubblico((p or {}).get("account_id")) or None for p in self.posti],
            "valutata": self.valutata,
            "esito_ele": self.esito_ele,
        }

    # ------------------------------------------------------------------ timer
    def info_timer(self):
        if self.timer_scadenza is None or not self.timer_chiave:
            return None
        return {"tipo": self.timer_chiave[0], "seat": self.timer_chiave[-1] if self.timer_chiave[0] == "giocata" else None,
                "restanti": max(0.0, self.timer_scadenza - time.monotonic()), "totale": self.timer_totale}

    def ferma_timer(self):
        if self.timer_task and not self.timer_task.done():
            self.timer_task.cancel()
        self.timer_task = None
        self.timer_chiave = None
        self.timer_scadenza = None

    def secondi_timer(self, tipo):
        if not self.timer_attivo:
            return 0
        if tipo == "scambio":
            return self.m.timer_scambio if self.durata_scambio is None else self.durata_scambio
        return self.m.timer_giocata if self.durata_giocata is None else self.durata_giocata

    def chiave_timer(self):
        """Quale timer deve correre adesso (None se nessuno)."""
        st = self.st
        if not self.timer_attivo or not st or self.stato != "in_corso" or self.in_pausa:
            return None
        if st.fase == FASE_SCAMBIO and self.secondi_timer("scambio") > 0:
            return ("scambio", st.mano_n, st.turno)
        if st.fase == FASE_GIOCO and self.secondi_timer("giocata") > 0 and self.posti[st.corrente]["tipo"] == "umano":
            giocate = len(st.giocate_mano)
            return ("giocata", st.mano_n, st.turno, giocate, st.corrente)
        return None

    def aggiorna_timer(self):
        chiave = self.chiave_timer()
        if chiave == self.timer_chiave:
            return
        self.ferma_timer()
        if chiave is None:
            return
        durata = self.secondi_timer(chiave[0])
        self.timer_chiave = chiave
        self.timer_totale = durata
        self.timer_scadenza = time.monotonic() + durata
        self.timer_task = asyncio.create_task(self._scadenza(chiave, durata))

    async def _scadenza(self, chiave, durata):
        try:
            await asyncio.sleep(durata)
        except asyncio.CancelledError:
            return
        async with self.lock:
            if self.timer_chiave != chiave or self.chiave_timer() != chiave:
                return
            self.timer_task = None
            st = self.st
            events = []
            if chiave[0] == "scambio":
                # chi non ha ancora passato passa una carta a caso (le squadre che hanno già scambiato no)
                for s in range(4):
                    if st.scambio_passata[s] is None:
                        passe = [a for a in legal_actions(st, s) if a.tipo == "passa" and not a.veloce]
                        if passe:
                            a = random.choice(passe)
                            if self.logger:
                                self.logger.nota(f"  Tempo scaduto: {self.posti[s]['nome']} passa una carta a caso.")
                            events += apply_inplace(st, a)
            else:
                s = chiave[-1]
                gioca = [a for a in legal_actions(st, s) if a.tipo == "gioca"]
                if gioca:
                    a = HeuristicAgent(seed=random.randrange(1 << 30)).choose_action(observation(st, s), gioca)
                    if self.logger:
                        self.logger.nota(f"  Tempo scaduto: per {self.posti[s]['nome']} gioca il bot.")
                    events += apply_inplace(st, a)
            if events:
                events.insert(0, ev("tempo_scaduto", fase=chiave[0], seat=None if chiave[0] == "scambio" else chiave[-1]))
                await self.gestisci_eventi(events)
        self.sveglia()

    async def invia_tutto(self, token=None):
        """Invia lo stato a tutti gli umani e agli spettatori (o al solo ``token``)."""
        if not self.st:
            return
        tokens = [token] if token else list(self.tokens_umani() | set(self.spettatori))
        for t in tokens:
            if t in self.spettatori and not self.posti_di(t):
                await self.m.invia(t, self.messaggio_spettatore())
                continue
            for s in self.posti_di(t):
                await self.m.invia(t, self.messaggio_stato(s))

    # ------------------------------------------------------------------ spettatori
    def osservazione_pubblica(self):
        """Quello che vede uno spettatore di una partita con giocatori umani: solo le informazioni
        pubbliche (tavola, prese, Bazziche dichiarate, punteggi...), nessuna carta in mano."""
        st = self.st
        obs = observation(st, 0)
        scoperta0 = st.bazzica[0] is not None          # una Bazzica dichiarata è pubblica
        obs["mano"] = list(st.mani[0]) if scoperta0 else []
        obs["mano_coperte"] = 0 if scoperta0 else len(st.mani[0])
        obs["scambio"]["mia_passata"] = None
        obs["scambio"]["ricevuta"] = None
        obs["scambio"]["distribuite"] = []
        obs["pubblica"] = True
        return obs

    def messaggio_spettatore(self):
        """Partita tra soli bot: lo spettatore vede tutto (le mani dei 4 bot sono scoperte).
        Partita con giocatori umani: solo le informazioni pubbliche."""
        st = self.st
        if self.solo_bot():
            obs = observation(st, 0)
            for k in obs["altri"]:
                obs["altri"][k]["carte"] = list(st.mani[int(k)])
        else:
            obs = self.osservazione_pubblica()
        info = self.info_partita()
        info["spettatore"] = True
        return {"type": "stato", "tavolo": self.id, "posto": 0, "obs": obs, "legali": [], "info": info,
                "spettatore": True}

    def guarda(self, token):
        if self.stato != "in_corso":
            raise ValueError("Nessuna partita in corso da guardare")
        if self.posti_di(token):
            raise ValueError("Sei seduto a questo tavolo: rientra in partita")
        if not self.guardabile():
            raise ValueError("A questo tavolo non sono ammessi spettatori")
        self.spettatori[token] = -1

    def smetti(self, token):
        self.spettatori.pop(token, None)
        self.ultima_frase_spett.pop(token, None)
        self.sveglia()

    async def frase_spettatore(self, token, indice):
        """Frase rapida di uno spettatore: la vedono giocatori e spettatori."""
        if self.stato != "in_corso" or token not in self.spettatori or self.posti_di(token):
            raise ValueError("Non stai guardando questa partita")
        if not isinstance(indice, int) or not 0 <= indice < len(FRASI):
            raise ValueError("Frase sconosciuta")
        ora = time.monotonic()
        if ora - self.ultima_frase_spett.get(token, -1e9) < self.m.pausa_palo:
            return
        self.ultima_frase_spett[token] = ora
        nome = self.m.nome_di(token)
        if self.logger:
            self.logger.nota(f"  [spettatore] {nome}: «{FRASI[indice]}»")
        await self.invia_eventi([ev("frase_spettatore", nome=nome, testo=FRASI[indice])])

    def visto(self, token, versione):
        if token in self.spettatori and isinstance(versione, int):
            self.spettatori[token] = max(self.spettatori[token], versione)

    async def _attendi_spettatori(self, massimo=10.0):
        """Ritmo umano: aspetta che gli spettatori abbiano finito di vedere le animazioni."""
        inizio = time.monotonic()
        while self.spettatori and min(self.spettatori.values()) < self.versione:
            if time.monotonic() - inizio > massimo:
                break
            await asyncio.sleep(0.15)

    async def invia_eventi(self, events):
        if not events:
            return
        # con giocatori umani gli spettatori ricevono solo gli eventi pubblici (mai carte in mano)
        pubblici = events if self.solo_bot() else [e for e in events if e.get("visibile") is None]
        if pubblici:
            for t in list(self.spettatori):
                if not self.posti_di(t):
                    await self.m.invia(t, {"type": "eventi", "tavolo": self.id, "posto": 0, "eventi": pubblici,
                                           "spettatore": True})
        for t in self.tokens_umani():
            for s in self.posti_di(t):
                vis = [e for e in events if e.get("visibile") is None or s in e["visibile"]]
                if vis:
                    await self.m.invia(t, {"type": "eventi", "tavolo": self.id, "posto": s, "eventi": vis})

    async def gestisci_eventi(self, events):
        self.ultimo_evento = self.ultima_attivita = time.monotonic()
        self.versione += 1
        extra = []
        for e in events:
            if self.raccoglitore is not None:
                self.raccoglitore.evento(e)
            if e["tipo"] == "fine_mano" and self.partita_id:
                self.m.storico.registra_mano(self.partita_id, e["riepilogo"])
            if e["tipo"] == "fine_partita" and self.partita_id:
                v = e["vincitore"]
                esito = "pari" if v == "pari" else self.squadre[v]
                self.m.storico.chiudi_partita(self.partita_id, esito, e["punteggi"])
                self.stato = "finita"
                try:
                    ev_ele = self.valuta_fine(v, e["punteggi"])
                except Exception as ex:  # pragma: no cover - l'eLE non deve mai bloccare la partita
                    ev_ele = None
                    if self.logger:
                        self.logger.nota(f"ERRORE nel calcolo dell'eLE: {ex!r}")
                if ev_ele:
                    extra.append(ev_ele)
        events = list(events) + extra
        if self.logger:
            self.logger.scrivi(events)
        self.aggiorna_timer()
        await self.invia_eventi(events)
        await self.invia_tutto()
        await self.m.invia_lobby()

    # ------------------------------------------------------------------ azioni umane
    async def azione_umana(self, token, posto, ad: dict):
        async with self.lock:
            if self.stato != "in_corso":
                raise ValueError("Nessuna partita in corso")
            if self.in_pausa:
                raise ValueError("Partita in pausa: in attesa di riconnessione")
            if posto not in self.posti_di(token):
                raise ValueError("Non controlli questo posto")
            self.attivo(token)
            ad = dict(ad)
            ad["seat"] = posto
            a = Action.from_dict(ad)
            if a.tipo == "che_palo" and self.st.fase == FASE_SCAMBIO:
                raise ValueError("Durante lo scambio non si può parlare")
            if a.tipo == "che_palo":
                ora = time.monotonic()
                if ora - self.ultimo_palo[posto] < self.m.pausa_palo:
                    return  # anti-spam: esclamazioni troppo ravvicinate vengono ignorate
                self.ultimo_palo[posto] = ora
            try:
                events = apply_inplace(self.st, a)
            except IllegalAction as ex:
                raise ValueError(str(ex))
            await self.gestisci_eventi(events)
        self.sveglia()

    async def frase(self, token, posto, indice):
        """Frase rapida (comunicazione consentita): non cambia lo stato del gioco."""
        if self.stato != "in_corso" or self.in_pausa:
            return
        if posto not in self.posti_di(token):
            raise ValueError("Non controlli questo posto")
        if not isinstance(indice, int) or not 0 <= indice < len(FRASI):
            raise ValueError("Frase sconosciuta")
        self.attivo(token)
        if self.st.fase == FASE_SCAMBIO:
            raise ValueError("Durante lo scambio non si può parlare")
        ora = time.monotonic()
        if ora - self.ultimo_palo[posto] < self.m.pausa_palo:
            return
        self.ultimo_palo[posto] = ora
        events = [ev("frase", seat=posto, testo=FRASI[indice])]
        if self.logger:
            self.logger.nota(f"  {self.posti[posto]['nome']} ({NOMI_POSTI[posto]}): «{FRASI[indice]}»")
        await self.invia_eventi(events)

    async def striscia(self, token, posto):
        """Carta "strisciata" sul tavolo per mettere fretta al giocatore precedente (solo effetto)."""
        if self.stato != "in_corso" or self.in_pausa or self.st.fase != FASE_GIOCO:
            return
        if posto not in self.posti_di(token):
            raise ValueError("Non controlli questo posto")
        self.attivo(token)
        precedente = (posto + 3) % 4
        if self.st.corrente != precedente:
            return  # il turno è appena passato: si ignora senza errori
        ora = time.monotonic()
        if ora - self.ultima_striscia[posto] < self.m.pausa_striscia:
            return
        self.ultima_striscia[posto] = ora
        await self.invia_eventi([ev("striscia", seat=posto, verso=precedente)])

    async def prosegui(self, token):
        async with self.lock:
            if not self.st or self.st.fase != FASE_FINE_MANO:
                return
            if not self.solo_bot() and token not in self.tokens_umani():
                return      # con giocatori umani il "Continua" degli spettatori non conta
            self.attivo(token)
            self.ack.add(token)
        self.sveglia()
        await self.invia_tutto()

    # ------------------------------------------------------------------ ciclo bot
    def sveglia(self):
        if self.stato != "in_corso":
            return
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._ciclo())

    def _bot_da_far_agire(self):
        st = self.st
        candidati = optional_actors(st) + required_actors(st)
        for s in candidati:
            if s not in self.agents:
                continue
            if st.fase == FASE_SCAMBIO and st.scambio_attesa[s] and st.scambio_passata[compagno(s)] is None:
                continue
            legal = legal_actions(st, s)
            if legal:
                return s, legal
        return None, None

    async def _ciclo(self):
        try:
            while self.stato == "in_corso" and not self.in_pausa:
                st = self.st
                if st.fase == FASE_FINE_MANO:
                    umani = self.tokens_umani()
                    if umani and not umani.issubset(self.ack):
                        return
                    if not umani and self.spettatori:
                        # partita tra bot guardata: si prosegue quando gli spettatori premono "Continua"
                        # (al massimo dopo 15 secondi)
                        inizio = time.monotonic()
                        while self.spettatori and not set(self.spettatori).issubset(self.ack) \
                                and time.monotonic() - inizio < 15 and self.stato == "in_corso":
                            await asyncio.sleep(0.25)
                    elif not umani:
                        await asyncio.sleep(self.m.pausa_fine_mano)
                    async with self.lock:
                        self.ack = set()
                        events = apply_inplace(self.st, system_action(self.st))
                        await self.gestisci_eventi(events)
                    continue
                s, legal = self._bot_da_far_agire()
                if s is None:
                    return
                lo, hi = self.m.ritardo_bot
                ritardo = random.uniform(lo, hi) if hi > 0 else 0
                if any(a.tipo == "attendi" for a in legal) and st.fase != FASE_SCAMBIO:
                    ritardo = min(ritardo, 0.3)
                if self.spettatori and not self.tokens_umani():
                    await self._attendi_spettatori()
                await asyncio.sleep(ritardo)
                async with self.lock:
                    if self.stato != "in_corso" or self.in_pausa:
                        return
                    if s not in self.agents:
                        continue    # il giocatore ha ripreso il suo posto
                    legal = legal_actions(self.st, s)
                    if not legal:
                        continue
                    a = self.agents[s].choose_action(observation(self.st, s), legal)
                    events = apply_inplace(self.st, a)
                    await self.gestisci_eventi(events)
        except Exception as ex:  # pragma: no cover - log difensivo
            if self.logger:
                self.logger.nota(f"ERRORE nel ciclo dei bot: {ex!r}")
            raise


class Manager:
    def __init__(self, cartella_log="logs", db_path="bazzica.db", ritardo_bot=(0.8, 1.5), pausa_fine_mano=2.0,
                 timer_scambio=0, timer_giocata=0, config: Optional[Config] = None):
        self.config = config or Config()
        self.tavoli: dict[str, Tavolo] = {}
        self.conn: dict[str, set] = {}       # token -> set di websocket
        self.nomi: dict[str, str] = {}       # token -> nome
        self.avatar: dict[str, str] = {}     # token -> avatar scelto
        self.cartella_log = cartella_log
        self.storico = Storico(db_path)
        self.ritardo_bot = ritardo_bot
        self.pausa_fine_mano = pausa_fine_mano
        self.pausa_palo = 3.0
        self.pausa_striscia = 1.0
        self.timer_scambio = timer_scambio
        self.timer_giocata = timer_giocata
        self.account = Account(self.storico, self.config.sessione_giorni)
        self.ele_cache: dict[int, dict] = {}     # account_id -> {ele, partite}

    # ------------------------------------------------------------------ account ed eLE
    def ele_cache_di(self, account_id):
        if account_id not in self.ele_cache:
            r = self.storico.ele_di([account_id])[account_id]
            self.ele_cache[account_id] = {"ele": r["ele"], "partite": r["partite"]}
        return self.ele_cache[account_id]

    def aggiorna_ele_cache(self, account_id, ele, partite):
        self.ele_cache[account_id] = {"ele": ele, "partite": partite}

    def ele_pubblico(self, account_id):
        """eLE mostrato accanto al nome (intero) e segno di provvisorio; {} per bot e ospiti."""
        if not account_id:
            return {}
        e = self.ele_cache_di(account_id)
        return {"ele": round(e["ele"]), "provvisorio": ELE.provvisorio(e["partite"])}

    def info_account(self, token):
        aid = account_da_identita(token)
        if not aid:
            return None
        return {"nome": self.nome_di(token), **self.ele_pubblico(aid), "partite": self.ele_cache_di(aid)["partite"]}

    def nome_riservato(self, nome):
        """Un ospite non può usare il nome di un account."""
        return bool(normalizza_nome(nome or "")) and self.account.nome_registrato(nome)

    def nome_di(self, token):
        return self.nomi.get(token, "?")

    def connesso(self, token):
        return bool(self.conn.get(token))

    async def invia(self, token, msg):
        for ws in list(self.conn.get(token, ())):
            try:
                await ws.send_json(msg)
            except Exception:
                self.conn.get(token, set()).discard(ws)

    def lobby_msg(self, token=None):
        return {"type": "lobby", "tavoli": [t.info(token) for t in self.tavoli.values()],
                "varianti": list(VARIANTI)}

    async def invia_lobby(self):
        for token in list(self.conn):
            await self.invia(token, self.lobby_msg(token))

    def tavoli_di(self, token):
        return [t for t in self.tavoli.values() if token in t.tokens_umani()]

    # ------------------------------------------------------------------ connessioni
    async def connetti(self, token, ws, nome=None, avatar=None, account=None):
        self.conn.setdefault(token, set()).add(ws)
        if account:
            # connessione con account: il nome è quello dell'account (anche su più dispositivi)
            self.nomi[token] = account["nome"]
            if account.get("avatar") in AVATAR:
                self.avatar[token] = account["avatar"]
            if avatar in AVATAR and not account.get("avatar"):
                self.avatar[token] = avatar
                self.account.imposta_avatar(account["id"], avatar)
            self.ele_cache.pop(account["id"], None)
        else:
            if nome:
                nome = nome[:24]
                if self.nome_riservato(nome):
                    nome = f"{nome[:15]} (ospite)"
                self.nomi[token] = nome
            if avatar in AVATAR:
                self.avatar[token] = avatar
        # l'identità di un account non si manda al client: il browser conserva il suo token da ospite
        await ws.send_json({"type": "benvenuto", "token": None if account else token, "nome": self.nomi.get(token),
                            "avatar": self.avatar.get(token), "account": self.info_account(token)})
        await ws.send_json(self.lobby_msg(token))
        for t in self.tavoli.values():
            if t.stato == "in_corso" and t.sostituiti_di(token):
                await self.invia(token, {"type": "tavolo", "tavolo": t.info(token)})
        for t in self.tavoli_di(token):
            t.disconnesso_da.pop(token, None)
            t.attivo(token)
            await self.invia(token, {"type": "tavolo", "tavolo": t.info(token)})
            if t.st:
                t.aggiorna_timer()
                await t.invia_tutto()  # aggiorna anche gli altri (fine pausa)
                t.sveglia()
        await self.invia_lobby()

    async def disconnetti(self, token, ws):
        s = self.conn.get(token)
        if s:
            s.discard(ws)
            if not s:
                del self.conn[token]
                for t in self.tavoli.values():
                    if token in t.spettatori:
                        t.smetti(token)
                        await t.invia_tutto()     # i giocatori vedono chi ha smesso di guardare
        for t in self.tavoli_di(token):
            if t.stato == "in_corso" and not self.connesso(token):
                t.disconnesso_da.setdefault(token, time.monotonic())
            if t.st:
                t.aggiorna_timer()   # in pausa il timer si ferma; riparte da capo alla ripresa
                await t.invia_tutto()
        await self.invia_lobby()

    # ------------------------------------------------------------------ pulizia automatica
    async def pulizia(self, ora=None):
        """Elimina i tavoli non avviati inattivi da troppo tempo e termina le partite in pausa senza
        nessun umano connesso da più di `pausa_max_ore`. Restituisce (eliminati, terminati)."""
        ora = time.monotonic() if ora is None else ora
        cfg = self.config
        eliminati, terminati = [], []
        for t in list(self.tavoli.values()):
            umani = t.tokens_umani()
            if t.stato == "in_corso":
                if not umani or any(self.connesso(k) for k in umani):
                    t.senza_umani_da = None          # partita tra bot o con qualcuno connesso
                    continue
                if t.senza_umani_da is None:
                    t.senza_umani_da = ora
                if cfg.pausa_max_ore and ora - t.senza_umani_da >= cfg.pausa_max_ore * 3600:
                    t.termina(motivo="interrotta")
                    if t.logger:
                        t.logger.nota(f"(pulizia automatica: nessun giocatore connesso da {cfg.pausa_max_ore:g} ore)")
                    t.ultima_attivita = ora
                    terminati.append(t.id)
                    await t.invia_tutto()
                continue
            # tavolo non avviato (o partita finita): chi è seduto o l'ha creato, se connesso, lo tiene in vita
            if any(self.connesso(k) for k in umani | {t.owner}) or any(self.connesso(k) for k in t.spettatori):
                t.ultima_attivita = ora
                continue
            if cfg.tavolo_inattivo_min and ora - t.ultima_attivita >= cfg.tavolo_inattivo_min * 60:
                del self.tavoli[t.id]
                eliminati.append(t.id)
        # nomi e avatar dei token spariti (non connessi e non seduti da nessuna parte)
        in_uso = set(self.conn) | {t.owner for t in self.tavoli.values()}
        for t in self.tavoli.values():
            in_uso |= t.tokens_umani()
        for diz in (self.nomi, self.avatar):
            for k in [k for k in diz if k not in in_uso]:
                del diz[k]
        if eliminati or terminati:
            await self.invia_lobby()
        return eliminati, terminati

    async def inattivita(self, ora=None):
        """Sostituisce con un bot chi è inattivo (o disconnesso) da `inattivita_min` minuti mentre
        altri giocatori aspettano. Restituisce l'elenco (tavolo, token, motivo)."""
        ora = time.monotonic() if ora is None else ora
        limite = self.config.inattivita_min * 60
        fatti = []
        for t in list(self.tavoli.values()):
            for token, motivo in t.da_sostituire(ora, limite):
                async with t.lock:
                    if t.stato != "in_corso" or not t.posti_di(token):
                        continue
                    await t.applica_sostituzione(token, motivo)
                fatti.append((t.id, token, motivo))
        return fatti

    async def ciclo_inattivita(self, intervallo=5.0):
        while True:
            await asyncio.sleep(intervallo)
            try:
                await self.inattivita()
            except Exception as ex:  # pragma: no cover - il controllo non deve mai fermare il server
                print(f"Errore nel controllo dell'inattività: {ex!r}")

    async def ciclo_pulizia(self, intervallo=60.0):
        while True:
            await asyncio.sleep(intervallo)
            try:
                await self.pulizia()
            except Exception as ex:  # pragma: no cover - la pulizia non deve mai fermare il server
                print(f"Errore nella pulizia dei tavoli: {ex!r}")

    # ------------------------------------------------------------------ comandi
    def nuovo_token(self):
        return secrets.token_hex(16)

    async def comando(self, token, msg):
        tipo = msg.get("type")
        tav = self.tavoli.get(msg.get("tavolo")) if msg.get("tavolo") else None
        if tipo == "nome":
            aid = account_da_identita(token)
            if aid:
                if msg.get("avatar") in AVATAR:
                    self.account.imposta_avatar(aid, msg["avatar"])
            else:
                nome = (msg.get("nome") or "Giocatore")[:24]
                if self.nome_riservato(nome):
                    raise ValueError("Questo nome appartiene a un account: accedi oppure scegline un altro")
                self.nomi[token] = nome
            if msg.get("avatar") in AVATAR:
                self.avatar[token] = msg["avatar"]
                # aggiorna l'avatar sui posti dei tavoli non ancora iniziati
                for t in self.tavoli.values():
                    if t.stato != "in_corso":
                        for p in t.posti:
                            if p and p.get("token") == token and p["nome"] == self.nomi[token]:
                                p["avatar"] = msg["avatar"]
            await self.invia_lobby()
            return
        if tipo == "lista":
            await self.invia(token, self.lobby_msg(token))
            return
        if tipo == "crea_tavolo":
            cfg = self.config
            if cfg.max_tavoli and len(self.tavoli) >= cfg.max_tavoli:
                raise ValueError("Ci sono già troppi tavoli: riprova più tardi o usa un tavolo esistente")
            if cfg.max_tavoli_token and sum(t.owner == token for t in self.tavoli.values()) >= cfg.max_tavoli_token:
                raise ValueError(f"Hai già {cfg.max_tavoli_token} tavoli: eliminane uno prima di crearne un altro")
            var = msg.get("variante", "Vanilla")
            if var not in VARIANTI:
                raise ValueError("Variante sconosciuta")
            tid = secrets.token_hex(3)
            nome = (msg.get("nome") or f"Tavolo di {self.nome_di(token)}")[:40]
            t = Tavolo(self, tid, nome, token, var, bool(msg.get("margherita")))
            self.tavoli[tid] = t
            await self.invia(token, {"type": "tavolo", "tavolo": t.info(token)})
            await self.invia_lobby()
            return
        if tav is None:
            raise ValueError("Tavolo inesistente")
        tav.ultima_attivita = time.monotonic()
        if tipo == "apri":
            await self.invia(token, {"type": "tavolo", "tavolo": tav.info(token)})
            if tav.st and token in tav.tokens_umani():
                await tav.invia_tutto(token)
            return
        if tipo == "imposta":
            if not tav.puo_gestire(token):
                raise ValueError("Solo chi ha creato il tavolo o chi è seduto può cambiare le impostazioni")
            if tav.stato == "in_corso":
                raise ValueError("Partita in corso: terminala per cambiare le impostazioni")
            if msg.get("variante") in VARIANTI:
                tav.variante = msg["variante"]
            if "margherita" in msg:
                tav.margherita = bool(msg["margherita"])
            if "timer" in msg:
                tav.timer_attivo = bool(msg["timer"])
            for chiave, attr in (("timer_scambio", "durata_scambio"), ("timer_giocata", "durata_giocata")):
                if chiave in msg:
                    v = int(msg[chiave])
                    if not 0 <= v <= 300:
                        raise ValueError("Durata del timer non valida")
                    setattr(tav, attr, v)
                    tav.timer_attivo = True
            if "spettatori" in msg:
                tav.spettatori_ammessi = bool(msg["spettatori"])
            if isinstance(msg.get("squadre"), list) and len(msg["squadre"]) == 2:
                tav.squadre = [(str(n or "").strip()[:20] or NOMI_SQUADRE[i]) for i, n in enumerate(msg["squadre"])]
        elif tipo == "siedi":
            if tav.stato == "finita":
                tav.torna_in_lobby()
            tav.siedi(token, int(msg["posto"]), msg.get("nome") or self.nome_di(token), msg.get("avatar"))
        elif tipo == "alzati":
            if tav.stato == "finita":
                tav.torna_in_lobby()
            tav.alzati(token, int(msg["posto"]))
        elif tipo == "bot":
            if tav.stato == "finita":
                tav.torna_in_lobby()
            tav.bot(int(msg["posto"]), bool(msg.get("aggiungi", True)))
        elif tipo == "avvia":
            if tav.stato == "finita":
                tav.torna_in_lobby()
            events = tav.avvia()
            for t in tav.tokens_umani():
                await self.invia(t, {"type": "tavolo", "tavolo": tav.info(t)})
            await tav.gestisci_eventi(events)
            tav.sveglia()
            return
        elif tipo == "azione":
            await tav.azione_umana(token, int(msg["posto"]), msg["azione"])
            return
        elif tipo == "guarda":
            tav.guarda(token)
            await self.invia(token, {"type": "tavolo", "tavolo": tav.info(token)})
            await tav.invia_tutto()          # anche i giocatori vedono chi guarda
            await self.invia_lobby()
            return
        elif tipo == "smetti":
            tav.smetti(token)
            await tav.invia_tutto()
            await self.invia_lobby()
            return
        elif tipo == "visto":
            tav.visto(token, msg.get("versione"))
            return
        elif tipo == "striscia":
            await tav.striscia(token, int(msg["posto"]))
            return
        elif tipo == "frase":
            if msg.get("posto") is None and token in tav.spettatori:
                await tav.frase_spettatore(token, msg.get("indice"))
            else:
                await tav.frase(token, int(msg["posto"]), msg.get("indice"))
            return
        elif tipo == "prosegui":
            await tav.prosegui(token)
            return
        elif tipo == "esci":
            await tav.esci(token)
            return
        elif tipo == "riprendi":
            await tav.riprendi(token)
            return
        elif tipo == "termina":
            if token != tav.owner and token not in tav.tokens_umani():
                raise ValueError("Solo chi è seduto al tavolo può terminare la partita")
            if tav.stato != "in_corso":
                raise ValueError("Nessuna partita in corso")
            tav.termina(da=self.nome_di(token))
            await tav.invia_tutto()
        elif tipo == "elimina":
            if not tav.puo_eliminare(token):
                raise ValueError("Solo chi ha creato il tavolo o chi è seduto può eliminarlo")
            if tav.stato == "in_corso":
                tav.termina(da=self.nome_di(token))
                await tav.invia_tutto()      # chi sta giocando vede "Partita interrotta"
            tav.spettatori.clear()
            del self.tavoli[tav.id]
            await self.invia_lobby()
            return
        else:
            raise ValueError(f"Comando sconosciuto: {tipo}")
        for t in tav.tokens_umani() | {token}:
            await self.invia(t, {"type": "tavolo", "tavolo": tav.info(t)})
        await self.invia_lobby()
