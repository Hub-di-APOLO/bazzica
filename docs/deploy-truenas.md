# Bazzica su TrueNAS SCALE — guida passo passo

Obiettivo: il server della Bazzica sempre acceso sul NAS, raggiungibile dagli amici (anche da telefono) su
**https://coverinas.duckdns.org:7845**, con certificato Let's Encrypt e codice d'accesso. Le porte 80 e 443 del
modem **restano come sono** (interfaccia del NAS): la Bazzica ha una porta sua.

Schema:

```
https://coverinas.duckdns.org        → modem :443   → NAS :443  → interfaccia di TrueNAS (come oggi)
https://coverinas.duckdns.org:7845  → modem :7845 → NAS :7845 → [caddy] ──http──▶ [bazzica] :8000
in LAN anche:  http://192.168.0.32:8000  (direttamente, senza Caddy)
```

Il nome DuckDNS porta solo fino al modem; è la **porta** a decidere dove si arriva: senza porta si arriva al
login del NAS, con `:7845` alla Bazzica.

Le due app girano in Docker come un'unica "app custom" di TrueNAS: `bazzica` e `caddy`, entrambe con immagini
costruite sul NAS. Caddy fa HTTPS e inoltra le WebSocket; il certificato lo ottiene con la **verifica DNS di
DuckDNS** (scrive un record temporaneo tramite il tuo token DuckDNS), quindi non ha bisogno delle porte 80/443.

I tuoi dati (già scritti nei comandi di questa guida):

| Cosa                    | Valore                                         |
|-------------------------|------------------------------------------------|
| Repository              | `https://github.com/Hub-di-APOLO/bazzica.git`  |
| Indirizzo DuckDNS       | `coverinas.duckdns.org`                        |
| IP del NAS in LAN       | `192.168.0.32`                                 |
| Porta della Bazzica     | `7845` (sul modem) → `7845` (sul NAS)          |
| Indirizzo per gli amici | **https://coverinas.duckdns.org:7845**        |
| In casa                 | http://192.168.0.32:8000                       |

Restano da sostituire, dove compaiono:

| Segnaposto              | Con                                                                          |
|-------------------------|------------------------------------------------------------------------------|
| `POOL`                  | il nome del pool di dischi del NAS (vedi sotto come trovarlo)                |
| `cambia-questo-codice`  | il codice d'accesso da dare agli amici (solo nel YAML, passo 4)              |
| `IL-TUO-TOKEN-DUCKDNS`  | il token del tuo account, in alto nella pagina di duckdns.org (solo nel YAML) |

**Cos'è `POOL`.** Su TrueNAS i dischi sono riuniti in un *pool* (ZFS), che ha un nome scelto quando hai installato
il NAS: lo vedi in **Storage** (es. `tank`, `dati`, `pool1`). Ogni pool compare nel sistema come cartella
`/mnt/<nome del pool>`, e dentro si creano i *dataset* (cartelle "speciali" con permessi, snapshot e quote proprie).
Quindi `/mnt/POOL/apps/bazzica` significa: nel tuo pool, il dataset `apps`, dentro il dataset `bazzica`. Se il pool si
chiama `tank`, il percorso è `/mnt/tank/apps/bazzica`. Per vederli dalla shell: `ls /mnt`.
Se hai già un dataset per le app (es. `/mnt/tank/apps` o `/mnt/tank/docker`), puoi usare quello al posto di `apps`.

---

## 0. Prima di iniziare

- TrueNAS SCALE 25.04 con le app attive (**Apps** → se richiesto, *Configure* → scegli il pool per le app).
- Il NAS ha l'IP fisso `192.168.0.32` ✔.
- Il sottodominio DuckDNS deve puntare al tuo IP pubblico e restare aggiornato (aggiornamento DuckDNS attivo sul
  modem, su un'app o con un cron). Verifica: `nslookup coverinas.duckdns.org` deve dare il tuo IP pubblico
  (lo vedi su un sito tipo "qual è il mio IP").
- L'interfaccia di TrueNAS resta raggiungibile da internet come oggi: almeno usa una password robusta e attiva
  l'autenticazione a due fattori (*Credentials → Two-Factor Authentication*).
- **Sul PC: commit e push** di tutto il progetto su GitHub. In PowerShell (o nel terminale di PyCharm):

  ```powershell
  cd C:\Users\paven\Desktop\Claude\Bazzica
  git status
  ```

  Nell'elenco devono comparire, tra gli altri, `Dockerfile`, `.dockerignore`, `requirements-docker.txt`, `deploy/`,
  `bazzica/server/config.py`, `bazzica/server/sicurezza.py`, `bazzica/web/fonts/`; **non** devono comparire
  `data/storico.db` né `logs/` (li esclude già il `.gitignore`). Poi:

  ```powershell
  git add -A
  git commit -m "Pubblicazione su TrueNAS: configurazione, codice d'accesso, limiti, pulizia tavoli, Docker e Caddy"
  git push
  ```

  Se `git push` dice che non c'è un remote (`git remote -v` non mostra nulla):

  ```powershell
  git remote add origin https://github.com/Hub-di-APOLO/bazzica.git
  git branch -M main
  git push -u origin main
  ```

  Al primo push Windows apre la finestra di accesso a GitHub. Controlla poi su
  https://github.com/Hub-di-APOLO/bazzica che ci siano `Dockerfile` e la cartella `deploy/truenas`.
  Da qui in avanti, a ogni modifica: `git add -A`, `git commit -m "…"`, `git push`.

## 1. Dataset e cartelle

Dall'interfaccia: **Datasets** → seleziona il pool → *Add Dataset*:

1. `apps` (se non esiste già), preset *Generic*;
2. dentro `apps`: `bazzica`, preset *Apps*;
3. dentro `bazzica` crea quattro dataset: `codice` (preset *Generic*), `data` e `logs` (preset *Apps*), `caddy`
   (preset *Generic*).

Poi apri la shell (**System → Shell**, oppure SSH con l'utente amministratore) e sistema cartelle e proprietari:

```sh
sudo mkdir -p /mnt/POOL/apps/bazzica/caddy/data /mnt/POOL/apps/bazzica/caddy/config
sudo chown -R 568:568 /mnt/POOL/apps/bazzica/data /mnt/POOL/apps/bazzica/logs
```

568 è l'utente `apps` di TrueNAS: il server della Bazzica gira con quell'utente (mai come root) e deve poter
scrivere solo in `data` (storico) e `logs`.

## 2. Il codice sul NAS (git)

```sh
sudo git clone https://github.com/Hub-di-APOLO/bazzica.git /mnt/POOL/apps/bazzica/codice
```

- Se il repository è privato, git chiede utente e password: come password usa un *personal access token* (Settings → Developer settings →
  Fine-grained tokens, permesso *Contents: read-only* sul solo repository). Per non reinserirlo ogni volta:
  `sudo git -C /mnt/POOL/apps/bazzica/codice config credential.helper store` (lo salva in chiaro in
  `/root/.git-credentials`: va bene su un NAS di casa).
- Se `git` dice che la cartella non è vuota, il dataset `codice` contiene qualcosa: svuotalo o clona altrove.
- Se nella shell non ci fosse `git`, usa un container usa e getta:
  `sudo docker run --rm -v /mnt/POOL/apps/bazzica:/lavoro alpine/git clone https://github.com/Hub-di-APOLO/bazzica.git /lavoro/codice`.

**Storico esistente (facoltativo):** per tenere le partite giocate finora, copia `data\storico.db` dal PC in
`/mnt/POOL/apps/bazzica/data/` (per esempio da una condivisione SMB o con `scp`), poi
`sudo chown 568:568 /mnt/POOL/apps/bazzica/data/storico.db`.

## 3. Costruire l'immagine

```sh
cd /mnt/POOL/apps/bazzica/codice
V=$(sudo git rev-parse --short HEAD)
sudo docker build --build-arg VERSIONE=$V -t bazzica:locale .
```

La prima volta scarica l'immagine di Python e le dipendenze (qualche minuto); le volte successive, se
`requirements-docker.txt` non cambia, ci mette pochi secondi. `VERSIONE` serve solo a vedere quale versione
gira (la mostra `/api/salute`).

Se Docker dicesse che l'immagine `python:3.13.18-slim` non esiste, usa la serie 3.13 più recente:
`sudo docker build --build-arg PYTHON_IMAGE=python:3.13-slim --build-arg VERSIONE=$V -t bazzica:locale .`

Poi l'immagine di Caddy con il modulo DuckDNS (una volta sola; da rifare solo per aggiornare Caddy):

```sh
sudo docker build -t caddy-duckdns:locale /mnt/POOL/apps/bazzica/codice/deploy/truenas/caddy
```

## 4. Installare l'app ("Install via YAML")

1. Apri `deploy/truenas/bazzica.yaml` (sul PC o con `cat /mnt/POOL/apps/bazzica/codice/deploy/truenas/bazzica.yaml`).
2. Sostituisci `POOL` (in tutte le righe in cui compare), `cambia-questo-codice` e `IL-TUO-TOKEN-DUCKDNS`
   (il dominio `coverinas.duckdns.org` è già scritto).
   Il codice d'accesso è quello che darai agli amici: non deve essere difficile, ma nemmeno "1234". Si inserisce
   una volta per dispositivo. Il token DuckDNS resta solo nella configurazione dell'app sul NAS.
3. **Apps → Discover Apps → ⋮ (in alto a destra) → Install via YAML**: nome `bazzica`, incolla il testo, *Save*.

Cosa contiene il YAML:

- `bazzica`: immagine locale (`pull_policy: never`), utente 568, variabili d'ambiente (codice, limiti, pulizia),
  volumi `data` e `logs`, healthcheck su `/api/salute`, porta 8000 per l'uso diretto in LAN, riavvio automatico.
- `caddy`: immagine `caddy-duckdns:locale`, porta NAS 7845 → 443 del container, dominio e token DuckDNS, il
  `Caddyfile` letto dal codice (`deploy/truenas/Caddyfile`) e i certificati salvati in `caddy/data`.
  Parte solo quando la Bazzica risulta "healthy".
- una rete interna fissa `172.30.77.0/24`: Caddy ha l'indirizzo `172.30.77.20` ed è l'unico di cui la Bazzica si
  fida per l'IP reale dei client (`BAZZICA_PROXY_FIDATI`). Se quella rete coincidesse con una delle tue,
  cambia `172.30.77` in tutte e quattro le righe.

Dopo un minuto l'app deve risultare *Running*. Prova in LAN: `http://192.168.0.32:8000` (gioco) e
`http://192.168.0.32:8000/api/salute` (deve rispondere `"stato":"ok"` con la versione).

## 5. Port forwarding sul modem

Nella pagina del modem (di solito *NAT / Port forwarding / Virtual server*) **lascia le regole che ci sono** e
aggiungi:

| Porta esterna | Protocollo | Verso             | Serve per                                     |
|---------------|------------|-------------------|-----------------------------------------------|
| 7845         | TCP        | 192.168.0.32 : 7845 | la Bazzica in HTTPS (obbligatoria)            |
| 7845         | UDP        | 192.168.0.32 : 7845 | HTTP/3, più veloce sui telefoni (facoltativa) |

**Non** inoltrare la porta 8000: da internet si passa solo da Caddy, in HTTPS.

## 6. Primo accesso

1. All'avvio Caddy chiede il certificato a Let's Encrypt con la verifica DNS (uno o due minuti: deve aspettare che
   il record di DuckDNS sia visibile). Per vedere come va: **Apps → bazzica → Logs → caddy**; cerca
   `certificate obtained successfully`. Per questo passo non serve nemmeno il port forwarding.
2. Apri **https://coverinas.duckdns.org:7845** dal telefono **con i dati mobili** (non dal Wi-Fi di casa): compare
   la schermata del codice d'accesso, poi quella di accesso (account oppure "Gioca come ospite"), poi la lobby.
   Senza `:7845` arrivi al NAS, come oggi.
3. Manda agli amici l'indirizzo **con la porta** e il codice. Comodo: un collegamento sulla schermata Home del
   telefono (dal browser, *Aggiungi a schermata Home*), così la porta non va più scritta.

Problemi frequenti:

- *Il certificato non arriva*: controlla il token DuckDNS e il dominio nel YAML (nei log di Caddy compaiono errori
  `duckdns` o `DNS challenge`). Dopo vari tentativi falliti Let's Encrypt fa aspettare: correggi e riavvia l'app.
- *Certificato ok ma da fuori non si apre*: manca la regola 7845 sul modem, oppure l'operatore usa il CGNAT
  (l'IP che vede il modem è diverso da quello di "qual è il mio IP": serve chiedere un IP pubblico all'operatore).
  Alcune reti Wi-Fi aziendali o pubbliche bloccano le porte non standard: con i dati mobili funziona sempre.
- *Da casa l'indirizzo con :7845 non si apre ma dai dati mobili sì*: il modem non supporta il "NAT loopback".
  In casa usa `http://192.168.0.32:8000`.
- *La pagina si apre ma resta "Connessione persa"*: la WebSocket non passa. Con questo Caddyfile non dovrebbe
  succedere; controlla i log di `bazzica` e di `caddy`.

## 7. Aggiornare il codice

Sul PC: commit e push. Poi sul NAS:

```sh
cd /mnt/POOL/apps/bazzica/codice
sudo git pull
V=$(sudo git rev-parse --short HEAD)
sudo docker build --build-arg VERSIONE=$V -t bazzica:locale .
```

Infine **Apps → bazzica → Edit → Save** (senza cambiare nulla): TrueNAS ricrea il container con l'immagine nuova.
Controlla su `https://coverinas.duckdns.org:7845/api/salute` che `versione` sia quella appena costruita; se fosse ancora
la vecchia, fai *Stop* e poi *Start* dell'app.

Attenzione: i tavoli e le partite in corso stanno in memoria, quindi un aggiornamento li chiude (lo storico resta;
le partite aperte risultano "interrotta"). Aggiorna quando nessuno sta giocando (`"partite_in_corso": 0` in
`/api/salute`).

Le immagini vecchie restano sul disco: ogni tanto `sudo docker image prune` (toglie solo quelle non usate).

Se cambi solo il `Caddyfile` basta riavviare l'app (se cambia `deploy/truenas/caddy/Dockerfile`, ricostruisci
anche `caddy-duckdns:locale` come al passo 3); se cambi solo le variabili d'ambiente: *Edit*, modifica il
YAML, *Save*.

## 7 bis. Account ed eLE (amministrazione)

Gli account e la classifica eLE stanno nello stesso database dello storico (`data/storico.db`): le password
sono salvate solo come hash e le sessioni solo come impronta del token. Non c'è il recupero via email: se un
amico dimentica la password, gliene imposti una nuova tu dalla shell del NAS.

```sh
sudo docker ps --format '{{.Names}}' | grep bazzica          # nome del container, es. ix-bazzica-bazzica-1
sudo docker exec -it ix-bazzica-bazzica-1 python -m bazzica.admin elenco
sudo docker exec -it ix-bazzica-bazzica-1 python -m bazzica.admin password NOME   # chiede la nuova password
sudo docker exec -it ix-bazzica-bazzica-1 python -m bazzica.admin revoca NOME     # chiude tutte le sue sessioni
sudo docker exec -it ix-bazzica-bazzica-1 python -m bazzica.admin ricalcola       # rifà la classifica da zero
```

- `password` chiude anche tutte le sessioni dell'account: l'amico deve rientrare con la password nuova.
- `ricalcola` serve solo se si cambiano i parametri in `bazzica/server/ele.py` (dopo `git pull` e
  `docker build`): rifà tutta la classifica in ordine cronologico dalle statistiche salvate. Poi riavvia l'app,
  così i tavoli mostrano subito i valori nuovi.
- Sul PC gli stessi comandi si danno dalla cartella del progetto: `py -m bazzica.admin elenco`.

## 8. Backup dello storico

Lo storico è un solo file: `/mnt/POOL/apps/bazzica/data/storico.db`.

- **Snapshot automatiche** (consigliate): **Data Protection → Periodic Snapshot Tasks → Add**, dataset
  `POOL/apps/bazzica/data`, ogni giorno, conservazione per esempio 1 mese. Per recuperare un file: *Datasets* →
  `data` → *Snapshots*, oppure dalla cartella nascosta `.zfs/snapshot/` del dataset.
- **Copia sul PC**: copia di sicurezza "a caldo" fatta dal server stesso, poi scaricala da una condivisione SMB:

  ```sh
  sudo docker ps --format '{{.Names}}' | grep bazzica          # nome del container, es. ix-bazzica-bazzica-1
  sudo docker exec ix-bazzica-bazzica-1 python -c "import sqlite3; s=sqlite3.connect('/app/data/storico.db'); d=sqlite3.connect('/app/data/storico-backup.db'); s.backup(d); d.close()"
  ```
- I log delle partite (`logs/`) contengono anche le carte in mano a tutti: non condividerli e cancellali quando
  vuoi (non servono al gioco).

## 9. Impostazioni utili (variabili nel YAML)

| Variabile                      | Nel YAML | Significato                                               |
|--------------------------------|----------|-----------------------------------------------------------|
| `BAZZICA_CODICE`               | —        | codice d'accesso (vuoto = nessuno)                        |
| `BAZZICA_MAX_TAVOLI`           | 50       | tavoli in totale                                          |
| `BAZZICA_MAX_TAVOLI_TOKEN`     | 5        | tavoli creati da uno stesso browser                       |
| `BAZZICA_MAX_CONN_IP`          | 20       | connessioni aperte da uno stesso IP                       |
| `BAZZICA_TAVOLO_INATTIVO_MIN`  | 180      | minuti prima di eliminare un tavolo non avviato e vuoto   |
| `BAZZICA_PAUSA_MAX_ORE`        | 12       | ore prima di chiudere una partita senza nessuno connesso  |
| `BAZZICA_INATTIVITA_MIN`       | 5        | minuti dopo cui un giocatore inattivo o disconnesso è sostituito da un bot |
| `BAZZICA_RITARDO_BOT`          | 0.8-1.5  | pensiero dei bot nel ritmo Svelto (s); Normale ×1,25, Rilassato ×1,6 |
| `BAZZICA_SESSIONE_GIORNI`      | —        | giorni senza usarla dopo cui scade una sessione (90)      |
| `BAZZICA_LOGIN_MAX_FALLITI`    | —        | login sbagliati prima del blocco, per IP e per nome (5)   |
| `BAZZICA_LOGIN_BLOCCO_MIN`     | —        | minuti di blocco dopo troppi login sbagliati (15)         |
| `BAZZICA_REGISTRAZIONI_ORA`    | —        | nuovi account all'ora da uno stesso IP (5)                |

L'elenco completo è in cima a `bazzica/server/config.py`. Per i limiti, 0 = nessun limite.
