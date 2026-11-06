# Bazzica mobile — piano (Fase 0: analisi)

Documento di lavoro per portare la Bazzica su Android/iOS come app Flutter che gioca in rete
locale senza internet. La versione Python resta il **riferimento ufficiale delle regole**.

Stato di partenza verificato il 6/11/2026: il codice nella cartella `Desktop\Claude\Bazzica`
coincide file per file con la copia di lavoro; 100 test Python verdi.

---

## 1. Architettura di arrivo

```
┌──────────────── telefono HOST (app Flutter) ────────────────┐
│  Schermate native: Home · Nome/Avatar · QR                   │
│  Server Dart (dart:io)  ── HTTP: /, /web/*, /assets/*, /api/* │
│     ├─ motore Dart (port 1:1 di bazzica/engine)              │
│     ├─ HeuristicAgent Dart (port 1:1 di bazzica/bots)        │
│     └─ WebSocket /ws  (protocollo identico al server Python) │
│  WebView ──► http://127.0.0.1:<porta>/  (stesso frontend)    │
│  mDNS: annuncia _bazzica._tcp (nome tavolo, porta, versione) │
└──────────────────────────────────────────────────────────────┘
        ▲ Wi-Fi o hotspot dell'host (nessun internet)
┌───────┴────── telefono CLIENT (stessa app) ──────┐   ┌── PC/telefono senza app ──┐
│  Home → "Unisciti": lista host da mDNS / QR      │   │ browser → http://IP:porta │
│  WebView ──► http://<ip host>:<porta>/           │   └───────────────────────────┘
└──────────────────────────────────────────────────┘
```

Scelte proposte:
- **Server con `dart:io` puro** (`HttpServer` + `WebSocketTransformer`), senza shelf: zero
  dipendenze esterne, gira identico in `dart test` sul PC e dentro l'app. Shelf resta un'opzione
  se serve.
- Il motore, i bot e il server stanno in un **pacchetto Dart puro** (`mobile/packages/bazzica_core/`)
  usato dall'app Flutter: si testa con `dart test` senza emulatori.
- Il frontend è **una sola sorgente** (`bazzica/web`). Lo script `mobile/tool/copia_web.py`
  (o `.dart`) lo copia negli asset Flutter al momento della build; nessuna modifica a mano.
- Le immagini delle carte (`assets/cards`, ~14 MB in PNG) vengono copiate dallo stesso script;
  vedi domanda D5 sulla compressione.

---

## 2. Mappa moduli Python → Dart

| Python | Dart (`mobile/packages/bazzica_core/lib/`) | Note per un port 1:1 |
|---|---|---|
| `engine/cards.py` | `engine/carte.dart` | Carte come `String` `seme_vv`, stesso ordine di `MAZZO`. |
| `engine/rules.py` | `engine/regole.dart` | `RulesConfig` immutabile, `preset()`, `toJson/fromJson` con le stesse chiavi. |
| `engine/bazzica.py` | `engine/bazzica.dart` | Ordine delle opzioni del 7 bello: v = 1..10. |
| `engine/scoring.py` | `engine/punteggio.dart` | `max(..., key)` di Python restituisce il **primo** massimo: replicare. Ordine delle chiavi dei dict nel riepilogo. |
| `engine/game.py` | `engine/partita.dart` | `GameState`, `Action`, `legal_actions`, `apply`, `observation`, `anteprima`, `stato_da_osservazione`. Vedi §4. |
| `bots/base.py` | `bots/agente.dart` | `Agent`, `RandomAgent`, `testo_osservazione`. |
| `bots/heuristic.py` | `bots/euristico.dart` | Aritmetica in virgola mobile nello **stesso ordine** di somma; `math.comb` esatto con interi. |
| `bots/runner.py` | `bots/simulazione.dart` | Ordine degli attori: `optional_actors + required_actors`. |
| `server/tables.py` | `server/tavoli.dart` | Tavolo, Manager, ciclo bot, pausa, anti-spam, ack di fine Mano. |
| `server/app.py` | `server/http.dart` | Rotte HTTP + WebSocket; `/api/carte` legge gli asset dell'app. |
| `server/log.py` | `server/log.dart` | Log testuale (sul telefono: cartella documenti dell'app). |
| `server/storico.py` | `server/storico.dart` | Fase 7, `sqflite` (solo nell'app; nei test un'implementazione in memoria). |
| `web/*` | asset Flutter (copia) | Nessun fork: adattamenti per telefono via media query nel sorgente unico. |
| `tests/*` | `test/*` | I test Dart principali sono le **tracce** esportate dal Python (§5). |

---

## 3. Protocollo completo (da replicare esattamente)

### 3.1 HTTP
| Rotta | Risposta |
|---|---|
| `GET /` | `web/index.html` con `Cache-Control: no-cache` |
| `GET /web/<file>` | file statici del frontend |
| `GET /assets/<file>` | carte (`assets/cards/*`) e suoni (`assets/sounds/*`) |
| `GET /api/carte` | `{"carte": {id: url}, "mancanti": [id...], "suoni": [nomefile...]}`; rispetta `assets/cards/mapping.json` |
| `GET /api/storico` | elenco partite (ultime 200, più recenti prima, con `n_mani`) |
| `GET /api/storico/{id}` | partita + `mani[]` con `riepilogo`; 404 `{"detail": "Partita non trovata"}` |
| `WS /ws?token=&nome=&avatar=` | canale di gioco; token vuoto o più lungo di 64 caratteri ⇒ nuovo token (32 hex) |

### 3.2 Messaggi client → server (JSON con `type`)
| `type` | Campi | Effetto / validazioni |
|---|---|---|
| `nome` | `nome`, `avatar?` | nome troncato a 24 car. (default "Giocatore"); avatar solo se tra i 10 ammessi; aggiorna l'avatar sui posti di tavoli non in corso con stesso token e nome; broadcast lobby |
| `lista` | — | risponde con `lobby` |
| `crea_tavolo` | `nome?`, `variante`, `margherita` | variante valida o errore; id tavolo 6 hex; nome default "Tavolo di <nome>" (max 40); risponde `tavolo`, broadcast lobby |
| `apri` | `tavolo` | risponde `tavolo`; se ci sei seduto e c'è partita, rimanda i tuoi `stato` |
| `imposta` | `tavolo`, `variante?`, `margherita?` | solo se non in corso |
| `siedi` | `tavolo`, `posto`, `nome?`, `avatar?` | se tavolo finito torna in lobby; posto libero; avatar non valido ⇒ avatar del token o `AVATAR[posto]` |
| `alzati` | `tavolo`, `posto` | libera se bot, se tuo, o se sei il creatore |
| `bot` | `tavolo`, `posto`, `aggiungi` | aggiunge/toglie bot (`Bot Nord`… con avatar 🤖) |
| `avvia` | `tavolo` | servono 4 posti; seed casuale; crea log e riga storico; invia `tavolo`, eventi e stati; avvia ciclo bot |
| `azione` | `tavolo`, `posto`, `azione{tipo,carta,presa,sette,veloce}` | partita in corso, non in pausa, posto tuo; "che_palo" soggetto ad anti-spam 3 s (silenzioso); azione illegale ⇒ `errore` |
| `frase` | `tavolo`, `posto`, `indice` 0..9 | non passa dal motore; anti-spam condiviso con Che Palo; evento `frase` a tutti; riga nel log |
| `prosegui` | `tavolo` | ack di fine Mano del token |
| `termina` | `tavolo` | solo creatore; storico "interrotta" |
| `elimina` | `tavolo` | solo creatore; se in corso la termina |

Dopo quasi ogni comando: `tavolo` personalizzato a chi è seduto + chi ha inviato, poi `lobby` a tutti.
Eccezioni `ValueError/KeyError/TypeError` ⇒ `{"type":"errore","messaggio": str(ex)}` (nota: per
`KeyError` Python produce il nome tra apici, es. `'posto'`).

### 3.3 Messaggi server → client
| `type` | Struttura |
|---|---|
| `benvenuto` | `token`, `nome`, `avatar` |
| `lobby` | `tavoli: [info(token)]`, `varianti: [8 nomi]` — personalizzato per token |
| `tavolo` | `tavolo: info(token)` = `{miei, owner, id, nome, variante, margherita, stato, owner_nome, posti:[null \| {tipo,nome,avatar,connesso}], punteggi}` |
| `eventi` | `tavolo`, `posto`, `eventi: [...]` filtrati per visibilità del posto (un messaggio per posto controllato dal token: hot-seat) |
| `stato` | `tavolo`, `posto`, `obs` (osservazione), `legali` (azioni senza `attendi`, con `descrizione`; `gioca` con `anteprima`; `bazzica` con `opzione`), `info{nomi,tipi,avatar,pausa,stato,attesa_ack,ack,variante}` |
| `errore` | `messaggio` |

Ordine di invio dopo un'azione: `eventi` di tutti i posti, poi `stato` di tutti i posti, poi `lobby`.

### 3.4 Eventi (campo `visibile`: `null` = tutti, altrimenti lista di posti)
| Evento | Campi | Visibilità |
|---|---|---|
| `inizio_partita` | variante, mazziere | tutti |
| `nuova_mano` | mano, mazziere | tutti |
| `distribuzione` | mano, turno, mazziere, tavola, carte_per_giocatore | tutti |
| `carte_ricevute` | seat, carte | solo `seat` |
| `inizio_scambio` | turno | tutti |
| `scambio_carta` | seat, a, carta, veloce | solo chi passa |
| `scambio` | seat, a, veloce | tutti (mai la carta) |
| `scambio_ricevuta` | seat, da, carta | solo `seat`, quando la coppia ha passato |
| `scambio_completato` | squadra | tutti |
| `fine_scambio` / `inizio_giocate` | turno (+ corrente) | tutti |
| `bazzica` | seat, carte, tipo_bazzica, scope, sette, girate, credito, squadra, descrizione | tutti |
| `che_palo` | seat | tutti |
| `giocata` | seat, carta, valore, presa, squadra, scopa, piccola, grande, assi, girate, credito_pagato, ultima_giocata, sparecchio, tavola (+ `credito` solo se c'è presa) | tutti |
| `fine_turno` | turno | tutti |
| `carte_residue` | squadra, carte, credito_pagato | tutti |
| `fine_mano` | riepilogo | tutti |
| `fine_partita` | vincitore (0/1/"pari"), punteggi, mani | tutti |
| `frase` (server) | seat, testo | tutti |

### 3.5 Comportamenti del server da replicare
- **Pausa**: partita in corso con almeno un token umano senza connessioni ⇒ pausa (`info.pausa` = nomi). Nessun timeout, nessun bot sostitutivo. Al ritorno dello stesso token: `benvenuto`, `lobby`, `tavolo`, stati, ripresa del ciclo.
- **Ciclo bot**: un compito per tavolo; ordine `optional_actors + required_actors`; salta i bot in `attendi` di scambio finché il compagno non passa; ritardo casuale 0,8–1,5 s (max 0,3 s per le decisioni facoltative fuori turno); ricontrolla lo stato dopo l'attesa.
- **Fine Mano**: aspetta l'ack (`prosegui`) di tutti i token umani; senza umani attende 2 s.
- **Anti-spam**: un timestamp per posto, condiviso tra Che Palo e frasi, 3 s.
- **Hot-seat**: stesso token su più posti; eventi e stati inviati per ogni posto.
- **Sicurezza informativa**: osservazioni ed eventi filtrati lato server; il client non riceve mai carte coperte altrui né la carta di scambio prima del tempo.
- **Avvio server**: le partite rimaste aperte nello storico diventano "interrotta".

---

## 4. Determinismo: dove il port può divergere

Fonti di casualità oggi:
1. `new_game`: `random.Random(seed)` → `randrange(4)` per il primo mazziere e `shuffle` del mazzo a **ogni Mano** (stesso generatore).
2. `HeuristicAgent`: `rng.random() * 1e-3` sommato ai punteggi per spareggiare (giocate e scambio).
3. `RandomAgent`: `rng.choice`.
4. Server: seed della partita, ritardo dei bot, token e id tavolo (non influiscono sulle regole).

Trappole di linguaggio individuate (da coprire con le tracce):
- `sorted(..., key=val)` è **stabile** in Python; `List.sort` di Dart **non** lo garantisce ⇒ usare un ordinamento stabile (influisce sull'ordine delle combinazioni di presa).
- `max(iterabile, key=...)` restituisce il primo massimo; i bot usano `>` stretto per lo stesso effetto.
- Divisioni intere `a / b` in Python sono correttamente arrotondate; in Dart `a / b` tra `int` < 2^53 dà lo stesso `double`. `math.comb` resta su interi (massimo ~1,4·10^11, sicuro).
- Ordine di somma dei `float` nei bot: va mantenuto identico.
- Iterazione su `set` nei bot: usata solo per contare o con al più un elemento ⇒ nessun effetto.
- Presenza/assenza di campi negli eventi (es. `credito` in `giocata`) e ordine delle opzioni.
- Confronto tra stringhe (ordinamento dei candidati allo scambio): ASCII ⇒ identico.

**Proposta per le tracce e il PRNG** (vedi domanda D1): introdurre un PRNG semplice e
documentato (`mulberry32`, 32 bit, poche righe) usato da `new_game` per mazziere e mescolamenti e
dai bot per gli spareggi, implementato identico in Python e Dart. Le regole non cambiano; cambia
solo quale mano esce con un certo seed. In alternativa le tracce salvano i mazzi mescolati
(nessuna modifica al Python) ma allora il bot Dart non può essere confrontato 1:1 con il Python
senza registrare anche i numeri casuali che consuma.

---

## 5. Tracce di riferimento (Fase 1)

`tools/esporta_tracce.py` → `mobile/packages/bazzica_core/test/tracce/*.json`, una per partita:
```json
{
  "versione": 1, "variante": "Curie", "margherita": false, "seed": 1234,
  "agenti": ["euristico", "euristico", "casuale", "euristico"],
  "passi": [
    {"tipo": "nuova_partita", "mazzo_mano": ["coppe_03", ...], "mazziere": 2, "eventi": [...]},
    {"azione": {...}, "attore": 1, "eventi": [...],
     "osservazioni": {"0": {...}, "1": {...}, "2": {...}, "3": {...}},
     "legali": {"1": [...]}, "rng_bot": [0.123, ...]}
  ],
  "finale": {"punteggi": [21, 14], "vincitore": 0, "storico_mani": [...]}
}
```
- Varianti × Margherita Hack × agenti misti; N configurabile (proposta: 200 partite per i test
  ordinari, 2.000 per la verifica completa; le osservazioni complete solo su un sottoinsieme per
  contenere le dimensioni, sulle altre un hash SHA-256 del JSON canonico).
- Il test Dart rigioca le azioni e confronta eventi, osservazioni, azioni legali e punteggi
  con JSON canonico (chiavi ordinate). Tolleranza zero.

---

## 6. App Flutter (Fasi 5–6)

- **Home**: "Crea partita" (avvia server su porta 8000 o la prima libera, annuncio mDNS,
  apre la WebView su `127.0.0.1`) · "Unisciti" (lista host trovati via mDNS, aggiornata dal vivo;
  pulsante "Leggi QR"; inserimento manuale IP:porta).
- **Nome e avatar**: schermata nativa che salva le preferenze e le passa al frontend (stesse chiavi
  `localStorage`: `bazzica_nome`, `bazzica_avatar`) così il frontend salta la sua schermata.
- **QR**: l'host mostra `http://<ip>:<porta>/` (anche come testo, per chi entra da browser).
  Se l'host è in hotspot, si mostra l'IP dell'interfaccia hotspot.
- **mDNS**: servizio `_bazzica._tcp`, nome = nome del tavolo/host, TXT: `v` (versione protocollo),
  `porta`. Client con versione diversa: avviso chiaro.
- **WebView**: JavaScript e `localStorage` attivi, audio senza gesto richiesto dove possibile,
  tasto Indietro di Android gestito (menu invece di uscire).
- **Host**: wakelock durante la partita; alla chiusura dell'app o perdita del server i client
  vedono "L'host ha chiuso la partita" (oggi vedono solo "riconnessione in corso").
- **Frontend sul telefono**: media query per schermi stretti/verticali (griglia 3x3 più compatta,
  mano più grande, menu frasi a tutta larghezza). Va rimosso il font da Google Fonts (vedi D4).
- **Android**: `INTERNET`, `ACCESS_WIFI_STATE`, `CHANGE_WIFI_MULTICAST_STATE` (+ multicast lock
  per mDNS), `network_security_config` con cleartext consentito (gli IP locali non si possono
  elencare a priori: proposta cleartext consentito in generale, l'app non parla con internet).
- **iOS**: `NSLocalNetworkUsageDescription`, `NSBonjourServices` = `_bazzica._tcp`,
  `NSAppTransportSecurity/NSAllowsLocalNetworking`, permesso fotocamera per il QR.

### Pacchetti (versioni lette dai repository, da riconfermare su pub.dev)
| Pacchetto | Versione | Requisiti | Note |
|---|---|---|---|
| Flutter stabile | 3.47.x | — | ultimi tag 3.47.7–3.47.9 |
| bonsoir | 7.1.6 | Dart ≥ 3.13 | mDNS Android/iOS |
| webview_flutter | 4.14.1 | Flutter ≥ 3.41 | pacchetto ufficiale |
| mobile_scanner | 7.5.0 | Flutter ≥ 3.29 | lettura QR |
| qr_flutter | 4.1.0 | — | fermo dal 2023; alternativa: `qr` (pure Dart) + disegno nostro |
| wakelock_plus | (fluttercommunity) | — | versione da verificare |
| sqflite | 2.4.5 | Flutter ≥ 3.44 | Fase 7 |

Non ho potuto verificare manutenzione e punteggi su pub.dev: da questo ambiente `pub.dev` è
bloccato (vedi D2).

---

## 7. Rischi
1. **Ambiente di build** (il più serio): da questo workspace cloud `pub.dev` e
   `storage.googleapis.com` sono bloccati, quindi non posso installare Dart/Flutter né scaricare
   pacchetti. Senza sblocco, test Dart e build vanno fatti sul tuo PC.
2. **iOS in background**: iOS sospende l'app host pochi secondi dopo che va in background, server
   compreso. Si può solo mettere in pausa e riprendere quando l'host torna in primo piano.
   Android può restare attivo con un servizio in primo piano (notifica permanente).
3. **mDNS sull'hotspot**: su alcuni telefoni Android l'annuncio sull'interfaccia hotspot non
   funziona; il QR e l'IP manuale restano il ripiego.
4. **Prestazioni** delle animazioni pesanti (Bazzica da 7, Napoleone) nella WebView di telefoni
   economici: da misurare, eventuale riduzione automatica degli effetti.
5. **Peso dell'app**: carte PNG ~14 MB (dorso 2,2 MB).

---

## 8. Decisioni prese (6/11/2026)
- **D1 – PRNG**: sì, `mulberry32` condiviso Python/Dart per mescolamento, primo mazziere e spareggi dei bot.
- **D2 – Build**: Dart/Flutter si installano sul PC dell'utente; io preparo codice e comandi, l'utente
  lancia test e build e riporta l'esito (la logica pura resta testabile anche con il solo Dart SDK).
- **D3 – iOS**: niente Mac per ora ⇒ si parte con **Android**; la parte iOS (Info.plist, permessi)
  viene preparata nel codice ma compilata più avanti.
- **D4 – Font**: Fredoka (OFL) incluso in `bazzica/web`, niente Google Fonts, anche per il PC.

- **D5 – Carte**: sì, copie compresse generate in build solo per l'app; originali intatti.
- **D6 – Background host**: su Android come su iOS la partita va in pausa finché l'host non torna
  nell'app (niente servizio in primo piano).
- **D7 – Identità**: app "Bazzica", identificativo `com.elements.bazzica`.
- **D8 – Porta**: 8000, con ripiego sulla prima libera.

## 8b. Domande (storico)
- ~~D1~~ deciso. Testo originale: va bene introdurre `mulberry32` anche nel Python (mescolamento, primo mazziere,
  spareggi dei bot)? Le regole e i 100 test restano invariati, ma uno stesso seed darà mani
  diverse da oggi. In alternativa salvo i mazzi nelle tracce e rendo deterministici gli spareggi
  del bot registrando i numeri casuali.
- **D2 – Dove compilare e testare**: posso chiedere all'amministratore di sbloccare per questo
  ambiente `pub.dev`, `storage.googleapis.com` (e per Android `dl.google.com`, `maven.google.com`,
  `services.gradle.org`, `repo.maven.apache.org`, `plugins.gradle.org`)? Altrimenti i test Dart e
  la build li lanci tu sul PC con Flutter installato (io preparo codice e comandi).
- **D3 – iOS**: hai un Mac con Xcode? Senza Mac non si compila per iOS. Distribuzione:
  installazione diretta (APK per Android; iOS con account Apple gratuito vale 7 giorni) o store?
- **D4 – Font**: tolgo Google Fonts e includo il font Fredoka (licenza OFL) dentro `bazzica/web`?
  Vale anche per la versione PC, che così funziona del tutto offline.
- **D5 – Carte**: per l'app posso generare in fase di build copie compresse (es. WebP a
  risoluzione ridotta) senza toccare gli originali? Le immagini sono utilizzabili in un'app
  distribuita, se un giorno andasse sugli store?
- **D6 – Background host**: su Android va bene un servizio in primo piano con notifica per tenere
  vivo il server? Su iOS accettiamo "pausa finché l'host non torna nell'app"?
- **D7 – Identità**: nome dell'app ("Bazzica"?) e identificativo (es. `com.elements.bazzica`)?
- **D8 – Porta**: 8000 come sul PC, con ripiego sulla prima libera?

---

## 9. Fasi e consegne
| Fase | Consegna | Verifica |
|---|---|---|
| 0 | questo documento | revisione tua |
| 1 ✅ | `bazzica/engine/prng.py` (mulberry32), `tools/esporta_tracce.py`, `tools/verifica_tracce.py` | 104 test Python verdi; 209 tracce rigiocate identiche |
| 2 | motore Dart | tutte le tracce identiche al 100% |
| 3 | HeuristicAgent Dart | stesse scelte sulle tracce; 2.000 partite con statistiche a confronto |
| 4 | server Dart | client web invariato funziona; test di protocollo (partita, pausa, hot-seat, anti-spam) |
| 5 | app Flutter | Home, mDNS, QR, WebView; frontend responsive |
| 6 | piattaforme | permessi, wakelock, background, messaggio host uscito |
| 7 | storico SQLite | (bassa priorità) |

---

## 10. Esito Fase 1 (6/11/2026)
- PRNG `mulberry32` in `bazzica/engine/prng.py`; usato da `new_game` (primo mazziere e
  mescolamenti), da `HeuristicAgent` (spareggi) e da `RandomAgent`. Vettori di prova in
  `tests/test_prng.py`, verificati anche contro l'implementazione JavaScript di riferimento.
- `tools/esporta_tracce.py`: 200 partite (25 per variante, una su cinque con Margherita Hack,
  una su quattro con bot casuali, una su dieci "dettagliata") + 9 speciali (Napoleone,
  pareggio, credito di Bazzica perso). ~16 MB compressi.
- `tools/verifica_tracce.py`: rigioca tutto dal solo seed e controlla osservazioni, azioni
  legali con anteprima, scelte dei bot, eventi e stati. Esito: tutto identico.
- Copertura delle 209 tracce: ~26.000 giocate, 2.580 Scope, 513 Piccole, 126 Grandi,
  1.121 Bazziche (509 da 2, 464 da 3, 70 da 5, 78 da 7), 251 prese col 7 bello a valore
  assegnato, 73 assi Avogadro, 558 riscossioni di credito, 38 Napole, 3 Napoleoni, 4 pareggi,
  1.361 passaggi veloci.
- Trovato durante il lavoro: `observation()` restituisce `storico_mani` per riferimento
  (lo stesso oggetto dello stato). Il server lo serializza subito quindi non è un problema,
  ma nel port Dart conviene restituire una copia; le tracce congelano i dati al momento.

---

## 11. Aggiunte al protocollo (7/11/2026) — da replicare nel server Dart
- `imposta` accetta anche `squadre: [nome1, nome2]` (max 20 caratteri, vuoto ⇒ "Squadra 1"/"Squadra 2")
  e `timer: bool`. `info` del tavolo e `info` dello stato includono `squadre`; lo storico salva il nome
  della squadra di ogni giocatore e l'esito con il nome della squadra vincitrice.
- `termina`: lo può chiedere qualsiasi giocatore seduto (non solo il creatore); `info.terminata_da`.
- `striscia` {tavolo, posto}: valido solo in fase di gioco mentre `corrente == (posto + 3) % 4`
  (altrimenti ignorato in silenzio); anti-spam 1 s per posto; evento `striscia` {seat, verso}.
- Chat bloccata durante lo scambio: `frase` e l'azione `che_palo` in fase `scambio` ⇒ `errore`.
- **Timer** (se attivo): 30 s per lo scambio (allo scadere chi non ha passato passa una carta a caso,
  non veloce), 15 s per ogni carta dei giocatori umani (allo scadere sceglie l'euristico tra le sole
  azioni `gioca`). Evento `tempo_scaduto` {fase, seat}. `info.timer` = {tipo, seat, restanti, totale}
  oppure null; si ferma in pausa e riparte da capo alla ripresa.
- Avatar: 12 (aggiunti 🐢 e 🦭). Nomi predefiniti delle squadre nel motore: "Squadra 1", "Squadra 2".
- (7/11) `imposta` accetta `timer_scambio` e `timer_giocata` in secondi (0–300, 0 = nessun timer);
  l'`info` del tavolo li riporta, più `guardabile` (partita in corso senza umani) e `spettatori`.
- (7/11) Spettatori delle partite tra soli bot: `guarda` / `smetti` / `visto {versione}`. Lo spettatore
  riceve `stato` ed `eventi` con `spettatore: true`, posto 0, tutte le mani scoperte e tutti gli eventi;
  `info.versione` cresce a ogni gruppo di eventi e i bot aspettano (max 10 s) che ogni spettatore
  abbia confermato la versione corrente; a fine Mano si prosegue con il `prosegui` degli spettatori
  (max 15 s).
