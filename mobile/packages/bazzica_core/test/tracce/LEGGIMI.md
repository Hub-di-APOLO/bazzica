# Tracce di riferimento (generate dal Python)

Generazione (dalla cartella del progetto):

```
py tools/esporta_tracce.py            # 200 partite + 9 speciali, ~16 MB, ~25 s
py tools/verifica_tracce.py           # le rigioca con il motore Python: deve dire "tutto identico"
py tools/esporta_tracce.py --per-variante 250 --uscita tracce_grandi   # verifica estesa (2.000 partite)
```

I file `*.json.gz` sono generati: non vanno modificati a mano. Se cambia il motore Python
(il riferimento delle regole) si rigenerano e i test Dart devono tornare verdi.

## Formato (versione 1)

```
{
  "versione": 1, "variante": "Curie", "margherita": false, "regole": {...RulesConfig...},
  "seed": 600003, "dettagliata": false,
  "agenti": [{"tipo": "euristico"|"casuale", "seed": <u32>}, ... 4 posti],
  "passi": [
    { "attore": null, "azione": null,                // passo 0 = new_game(regole, seed)
      "eventi": [...], "mazzo_mano": [40 carte],     // ordine del mazzo dopo il mescolamento
      "stato_hash": "<sha256>", "oss_hash": [4 sha256], "stato": {...} (solo se dettagliata) },
    { "attore": null, "azione": {"tipo": "nuova_mano", ...},     // azione di sistema
      "mazzo_mano": [...], "eventi": [...], "stato_hash": ..., "oss_hash": [...] },
    { "attore": 2, "oss": {...osservazione completa del posto 2...},
      "legali": [ {azione..., "anteprima": {...} solo per "gioca"} ],
      "azione": {...scelta del bot...}, "rng_bot": <stato mulberry32 del bot dopo la scelta>,
      "eventi": [...], "stato_hash": ..., "oss_hash": [...] }
  ],
  "finale": {"punteggi": [a, b], "vincitore": 0|1|"pari", "mani": n, "stato": {...}}
}
```

Ordine degli attori a ogni passo (identico a `bots/runner.py`): se c'è un'azione di sistema
(`nuova_mano`) si applica quella; altrimenti il primo posto con azioni legali in
`optional_actors(st) + required_actors(st)`.

## Confronto

- **JSON canonico**: chiavi ordinate, separatori `,` e `:` senza spazi, caratteri non ASCII
  in chiaro (UTF-8), escape come `json.dumps` di Python (`\"`, `\\`, `\n`, `\r`, `\t`, `\b`,
  `\f`, altri caratteri di controllo come `\u00XX` minuscolo). Le tracce non contengono
  numeri in virgola mobile negli stati, eventi e osservazioni.
- `stato_hash` = SHA-256 del JSON canonico di `stato_json(st)` (definito in
  `tools/esporta_tracce.py`); `oss_hash[s]` = SHA-256 del JSON canonico di `observation(st, s)`.
- Il test Dart deve verificare a ogni passo: osservazione dell'attore, azioni legali con
  anteprima, eventi, hash dello stato, hash delle 4 osservazioni; nelle tracce dettagliate lo
  stato completo; alla fine punteggi e stato finale. Per il bot (Fase 3): stessa azione e
  stesso `rng_bot`.

## PRNG

`mulberry32` (vedi `bazzica/engine/prng.py`), vettori di prova in `tests/test_prng.py`.
`new_game`: `Mulberry32(seed)`, poi `randbelow(4)` per il primo mazziere (se non dato), poi
`shuffle` del mazzo a ogni Mano con lo stesso generatore. I bot: `Mulberry32(seed)` per gli
spareggi (`random()`), `RandomAgent` usa `choice` = `seq[randbelow(len)]`.
