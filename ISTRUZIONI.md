# Bazzica — istruzioni di avvio

## Requisiti
- Python 3.11 o successivo
- Le immagini delle carte in `assets/cards/` (nomi `{seme}_{valore:02d}.png` più `dorso.png`; se i nomi sono diversi, crea `assets/cards/mapping.json` del tipo `{"denari_07": "mio_file.png", ...}`). Le carte mancanti vengono disegnate in CSS.

## Installazione (una volta sola)
Apri un terminale nella cartella del progetto:
```
python -m pip install -r requirements.txt
```

## Avvio
```
python run.py
```
(porta diversa: `python run.py --port 9000`)

La console mostra gli indirizzi da aprire, per esempio:
```
 Su questo PC:      http://localhost:8000
 In rete locale:    http://192.168.1.23:8000
```

## Giocare in rete locale (LAN)
1. Avvia il server su un PC (l'host).
2. **Firewall:** la prima volta Windows chiede se consentire Python sulle reti private: rispondi *Consenti*. In alternativa, apri la porta TCP 8000 in *Windows Defender Firewall → Regole connessioni in entrata* per le reti private.
3. Ogni giocatore apre nel browser l'indirizzo "In rete locale" (anche da tablet), inserisce il nome, apre il tavolo dalla lobby e si siede su un posto libero.
4. Chi ha creato il tavolo sceglie variante e Margherita Hack, mette i bot sui posti vuoti e preme **Avvia partita**.

Squadre: Nord e Sud contro Est e Ovest. Nella stanza del tavolo si possono scegliere i nomi delle squadre (altrimenti "Squadra 1" e "Squadra 2") e la durata dei timer (scambio e singola carta, oppure "Nessuno"). Il primo mazziere è sorteggiato.

All'ingresso ognuno sceglie nome e avatar (12 disponibili); i bot hanno l'avatar del robot.

## Account ed eLE
- All'ingresso si può **accedere** con un account (nome utente e password), **crearne uno nuovo** oppure **giocare come ospite** come prima. L'accesso resta ricordato sul dispositivo; lo stesso account funziona su più dispositivi (PC e telefono). "Esci" nella lobby esce dall'account solo su quel dispositivo.
- Con l'account il nome al tavolo è quello dell'account; si sceglie solo l'avatar. Un ospite non può usare il nome di un account.
- Le partite con 4 account diversi (niente bot, ospiti o hot-seat) sono **valutate eLE**: la stanza lo dice, con l'eLE delle squadre e la probabilità di vittoria. A fine partita compare la variazione di ciascuno con il dettaglio del calcolo. Regole complete nel `README.md` (il regolamento), capitolo 12 (eLE).
- La pagina **Classifica** (nella lobby) mostra l'eLE di tutti e il grafico dell'andamento. Toccando un giocatore si apre la sua **scheda** con le statistiche: carriera, giocate spettacolari (Scope, Piccole, Grandi, Bazziche per tipo, Bazziche fatte fare, assist, Napoleoni, "Che Palo!"…), carte prese (assi, 7 bello, re bello, 2 di denari…), compagni e rivali. La propria scheda si apre anche toccando il proprio nome nella lobby. Contano tutte le partite concluse giocate con l'account (anche con bot o ospiti, anche non valutate); un interruttore mostra solo le valutate eLE. Chi abbandona prende una sconfitta.
- Password dimenticata, sessioni da chiudere, ricalcolo della classifica: `py -m bazzica.admin elenco | password NOME | revoca NOME | ricalcola` (sul NAS dentro il container, vedi `docs/deploy-truenas.md`).

## Giocare sullo stesso PC (hot-seat)
Dallo stesso browser siediti su più posti: dal secondo in poi si apre una finestra per il nome e l'avatar del nuovo giocatore. Durante la partita, quando tocca a un altro giocatore umano compare la schermata **"Passa a …"**: passa il dispositivo e tocca per mostrare le carte. Anche lo scambio segreto della variante Heisenberg resta segreto.

## Durante la partita
- Tocca una carta: compaiono le prese possibili con l'anteprima (Scopa, Piccola, Grande, assi, credito); tocca l'opzione per giocare.
- **Bazzica!** apre la scelta delle Bazziche valide (con il valore del 7 bello).
- Il pulsante tondo 💬 **Chat** (in basso a destra; sul telefono accanto alla mano) apre "Che Palo!" e tutte le frasi (una esclamazione ogni 3 secondi al massimo).
- **Pre-mossa**: mentre giocano gli altri puoi già toccare la carta che vuoi giocare (diventa "pronta"); quando tocca a te compaiono subito le sue prese e basta premere il pulsante.
- **Striscia** (pulsante azzurro 🃏): si può premere solo mentre gioca il giocatore che viene prima di te; fa comparire vicino a lui una carta strisciata sul tavolo, per mettergli fretta.
- **Timer** (durate scelte nella stanza; di base "Nessuno", cioè disattivati): allo scadere dello scambio chi non ha passato passa una carta a caso; allo scadere del tempo per una carta gioca il computer al posto tuo. In pausa per disconnessione il timer si ferma e riparte da capo.
- **Partita tra soli bot**: metti 4 bot e premi "Avvia partita" (oppure "👀 Guarda" nella lobby): la partita si guarda a ritmo umano, con tutte le carte scoperte. I bot aspettano che le animazioni siano finite prima di giocare.
- **Spettatori**: con "👀 Guarda" nella lobby (o "Guarda la partita" nella stanza) si può assistere a qualunque partita in corso a cui non si è seduti. Nelle partite con giocatori umani lo spettatore vede solo le carte giocate in tavola, le prese, le Bazziche dichiarate e i punteggi, mai le carte in mano né lo scambio. Con la Chat manda le frasi rapide (non "Che Palo!"), anche durante lo scambio: le vedono giocatori e spettatori. Il contatore 👀 sul tavolo dice quanti stanno guardando (toccandolo, chi). Nella stanza la casella "Spettatori ammessi" (attiva di base) permette di vietarli; le partite tra soli bot si possono sempre guardare.
- La **chat** (pulsante "Chat", con "Che Palo!" e le frasi) si apre solo quando lo scambio delle carte è finito.
- Dal menu ☰ qualsiasi giocatore seduto può **terminare la partita** (conferma dentro il gioco): tutti vedono "Partita interrotta" e possono tornare al tavolo.
- **Tavoli con una partita in corso**: "Apri" nella lobby porta alla stanza del tavolo (in partita si entra con "Rientra"). Chi ha creato il tavolo o chi è seduto può terminare la partita, cambiare poi le impostazioni ed eliminare il tavolo; un tavolo senza nessun giocatore connesso può eliminarlo chiunque.
- Il pulsante 👀 **Ultima presa** (in alto a sinistra) mostra chi ha fatto l'ultima presa della Mano e con quali carte.
- Nello scambio: scegli una delle tue carte, poi **Passa** o **Passa veloce**. La carta del compagno si vede solo quando avete passato entrambi; di lui sai solo se ha già passato e se ha passato veloce.
- A fine Mano compare il riepilogo; la Mano successiva parte quando tutti hanno premuto **Continua**. Con **Esci dalla partita** si torna alla stanza del tavolo e al proprio posto gioca un bot; se escono tutti i giocatori la partita viene chiusa come "interrotta".
- Se un giocatore si disconnette la partita va in pausa finché non riapre la pagina dallo stesso browser (la sessione è ricordata).
- **Inattività**: chi non gioca per 5 minuti in tutto quando tocca a lui (anche il "Continua" di fine Mano), oppure resta disconnesso per 5 minuti, viene sostituito da un bot, ma solo se c'è almeno un altro giocatore connesso che aspetta (da soli contro i bot la partita aspetta). Ogni azione azzera il conteggio. Durata: `BAZZICA_INATTIVITA_MIN`.
- Chi è stato sostituito da un bot (uscito o inattivo) può **riprendere il posto** finché la partita è in corso, dalla lobby o dalla stanza del tavolo: riprende le carte che ha in mano il bot.
- Il pulsante con l'altoparlante attiva/disattiva i suoni; i file opzionali vanno in `assets/sounds/` (vedi `LEGGIMI.txt`).

## Log e storico
- Un log di debug per partita in `logs/` (contiene anche le mani di tutti: non mostrarlo ai giocatori!).
- Lo storico (SQLite) è in `data/storico.db`; si consulta dalla pagina **Storico** della lobby. Nello stesso file ci sono gli account (password solo come hash) e la classifica eLE.

## Opzioni (variabili d'ambiente)
Tutte facoltative; su Windows si impostano con `set NOME=valore` prima di `python run.py`. L'elenco completo è in cima a `bazzica/server/config.py`.
- `BAZZICA_RITARDO_BOT`: pausa dei bot, es. `0.3-0.6`. Default `0.8-1.5` secondi.
- `BAZZICA_PORTA`, `BAZZICA_HOST`: porta e indirizzo di ascolto (`--port`/`--host` hanno la precedenza).
- `BAZZICA_DATI`, `BAZZICA_LOG`: cartelle dello storico e dei log.
- `BAZZICA_CODICE`: codice d'accesso. Se impostato, chi apre il gioco deve inserirlo (una volta per dispositivo).
- Account: `BAZZICA_SESSIONE_GIORNI` (scadenza delle sessioni, default 90 giorni dall'ultimo uso), `BAZZICA_LOGIN_MAX_FALLITI` e `BAZZICA_LOGIN_BLOCCO_MIN` (dopo 5 login sbagliati blocco di 15 minuti, per IP e per nome utente), `BAZZICA_REGISTRAZIONI_ORA` (nuovi account all'ora per IP, default 5).
- Limiti contro gli abusi (`BAZZICA_MAX_TAVOLI`, `BAZZICA_MAX_TAVOLI_TOKEN`, `BAZZICA_MAX_CONN_IP`, `BAZZICA_MAX_MESSAGGIO`, `BAZZICA_MAX_MSG_SECONDO`) e pulizia automatica (`BAZZICA_TAVOLO_INATTIVO_MIN`, default 180 minuti per i tavoli non avviati abbandonati; `BAZZICA_PAUSA_MAX_ORE`, default 12 ore per le partite senza nessuno connesso; `BAZZICA_INATTIVITA_MIN`, default 5 minuti prima di sostituire con un bot un giocatore inattivo). 0 = nessun limite.

Stato del server: `http://localhost:8000/api/salute`.

## Pubblicare su internet (TrueNAS)
Guida passo passo in `docs/deploy-truenas.md` (Docker + Caddy con HTTPS su un sottodominio DuckDNS).

## Test
```
python -m pytest
```
(i test del frontend in `tests/test_frontend.py` usano Node.js, se installato; altrimenti vengono saltati)
La simulazione solo-bot gioca 2.000 partite (250 per variante); per una prova veloce: `set BAZZICA_SIM=10`.

## Struttura
```
bazzica/engine/   regole pure (stato, azioni legali, punteggio)
bazzica/bots/     interfaccia Agent e bot euristico (base per futuri bot LLM)
bazzica/server/   FastAPI, lobby, WebSocket, log, storico, configurazione (config.py), sicurezza (sicurezza.py),
                  account (account.py), calcolo eLE (ele.py)
bazzica/admin.py  comandi di amministrazione: python -m bazzica.admin
bazzica/web/      interfaccia (HTML/CSS/JS senza build; font Fredoka incluso in web/fonts)
deploy/truenas/   YAML per TrueNAS e Caddyfile; Dockerfile e requirements-docker.txt nella radice
tests/            test pytest
```

## Scelte di regolamento concordate
- Il 7 bello a cui si assegna 1 non piglia mai tutto (vale 1).
- Il credito di Bazzica si riscuote dopo Scope/Piccole/Grandi/assi, su tutte le carte coperte della presa, compresa quella giocata.
- "Che Palo!": si può esclamare quando si vuole (i bot lo fanno solo se la mano è davvero a una carta da una Bazzica).
- Scambio: la carta del compagno arriva solo quando entrambi i compagni hanno passato.
- Avogadro: anche l'asso giocato che fa presa va a faccia in su.
- Einstein: qualsiasi tris che contiene il 7 bello vale 5 Scope.
