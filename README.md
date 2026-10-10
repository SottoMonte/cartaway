# Cartaway

Negozio statico in italiano per prodotti di carta con consegna locale a Montoro e nei comuni vicini. Contatti e catalogo sono file JSON; Decap CMS li modifica senza database o server applicativo. Il carrello resta nel browser e invia una richiesta precompilata su WhatsApp, con data e fascia oraria preferite facoltative da confermare: non sono attivi pagamenti online.

La home mette in vetrina i prodotti disponibili marcati come in evidenza nel CMS. `catalogo.html` contiene il catalogo completo con ricerca e filtri; ogni scheda apre `prodotto.html?id=ID-PRODOTTO`, con galleria fotografica e caratteristiche.

## Avvio locale

Dalla cartella del progetto avvia un server statico:

```bash
python3 -m http.server 4173
```

Apri `http://localhost:4173`. La pagina `/admin` va collegata a Decap Turbo prima di consentire modifiche online.


## Pubblicazione

1. Crea un repository GitHub sul branch `main` e carica il progetto.
2. Su Netlify importa quel repository. Lascia vuoto il comando di build e imposta la cartella di pubblicazione su `.`; aggiungi poi il dominio personalizzato.
3. Crea l'organizzazione Decap Turbo con l'account del cliente. Il piano Free include un sito e un utente, quindi l'account cliente deve essere il proprietario. Collega GitHub, installa l'app Turbo sul repository e crea un sito con branch `main`, percorso di configurazione `admin/config.yml` e URL admin `https://IL-TUO-SITO/admin/`.
4. Copia la Site ID mostrata da Turbo in `admin/config.yml`, al posto di `SOSTITUISCI-CON-LA-SITE-ID-DECAP-TURBO`, e invia la modifica a GitHub. Netlify pubblicherà la configurazione aggiornata.
5. Accedi da `https://IL-TUO-SITO/admin/` con Decap Turbo. Da lì il cliente può aggiornare i recapiti e i prodotti; ogni salvataggio aggiorna il JSON su GitHub e avvia una nuova pubblicazione.

Il CMS usa il backend GitHub di Decap Turbo, distribuito al momento come release beta: lo script in `admin/index.html` è fissato alla versione indicata nella documentazione. Il piano Turbo Free attuale include un sito e un utente; altri utenti o siti richiedono un piano superiore. Mantieni aggiornato in Turbo l'URL admin anche dopo aver collegato il dominio definitivo.

## Dati e contatti

- `data/products.json`: prodotti, categoria, confezione, prezzo, foto principale, foto aggiuntive, caratteristiche e disponibilità. La pagina prodotto mostra la galleria e le caratteristiche inserite qui o nel CMS. Prezzi e stock iniziali sono dimostrativi: sostituiscili con quelli effettivi prima della pubblicazione.
- `data/site.json`: nome, zona, recapiti, indirizzo e dati dell'impresa. Verifica che i contatti e le informazioni legali siano aggiornati e pertinenti all'attività.
- Il catalogo iniziale usa immagini dimostrative da Unsplash. Caricando le foto definitive da Decap, i file vengono salvati in `uploads/` nel repository.

I tempi indicati sono stime: Montoro circa 2 ore, comuni vicini in giornata su conferma. Il sito non calcola le spese di consegna né verifica automaticamente disponibilità e tempi; l'ordine viene confermato manualmente su WhatsApp.

## Costi e limiti

Netlify Free costa attualmente €0 e include un limite di 300 crediti al mese. Le pubblicazioni di produzione e il traffico consumano crediti: oltre la quota il servizio può fermarsi fino al rinnovo o richiedere un piano superiore. Controlla i consumi e non attivare ricariche automatiche se l'obiettivo è non superare il budget. Il costo del dominio resta separato. Le quote e i piani dei servizi possono cambiare.

Per un sito commerciale non usare il piano Vercel Hobby: i termini attuali lo limitano a progetti personali o non commerciali.