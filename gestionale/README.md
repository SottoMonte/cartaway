# Gestionale locale Cartaway

Backend, interfaccia web e test sono raccolti in questa cartella. I file `../data/products.json` e `../data/site.json` restano nella radice perché sono condivisi con il negozio e il CMS; il programma non legge la configurazione YAML del CMS. Se necessario, i percorsi dei JSON si possono cambiare con le opzioni `--products` e `--site`. Il database SQLite viene salvato fuori dal repository in `~/.local/share/cartaway/gestionale.sqlite3`.

I comandi seguenti si eseguono dalla cartella principale del progetto. Il gestionale richiede Python 3.9 o successivo e usa solo la libreria standard.

## Avvio e comandi

```bash
python3 -m gestionale init
python3 -m gestionale stock list
python3 -m gestionale stock set carta-igienica-mini-jumbo-12-rotoli 20
python3 -m gestionale stock add carta-igienica-mini-jumbo-12-rotoli 5
python3 -m gestionale orders
python3 -m gestionale route
```

Le giacenze partono come "da impostare": inizializzale con `stock set`, poi aggiornatele con `stock set` o `stock add`. Nell'interfaccia, "Imposta giacenza" sostituisce la quantità registrata con il nuovo totale fisico; "Aggiungi pezzi" incrementa quella già presente. Le richieste e la conferma email non scalano lo stock: nella scheda Consegne, dopo la consegna effettiva, usa "Segna consegnato" sull'ordine. Il gestionale sottrae una sola volta le quantità dell'ordine e registra data e ora. Se la giacenza non basta o non è impostata, non modifica né stock né stato: aggiorna prima la quantità fisica e riprova. Gli articoli marcati `available: false` nel catalogo risultano non disponibili; se la quantità locale non è stata impostata, l'app segnala che serve una verifica invece di dichiarare il prodotto esaurito.

Per ricevere le richieste, configura una copia CC/BCC del template EmailJS verso una casella operativa. Imposta le variabili d'ambiente prima di avviare la lettura; non salvarle nel repository:

```text
IMAP_HOST, IMAP_USER, IMAP_PASSWORD
SMTP_HOST, SMTP_USER, SMTP_PASSWORD
```

La sincronizzazione legge solo i messaggi non letti della cartella `INBOX`, per evitare di elaborare lo storico o i messaggi inviati, e marca come letti i riepiloghi importati. Per le caselle Aruba standard usa `IMAP_HOST=imaps.aruba.it` e `IMAP_PORT=993`; `smtps.aruba.it` è il server SMTP in uscita. Per PEC o servizi Aruba diversi verifica i parametri specifici del provider. Ogni richiesta già registrata viene ignorata. Le giacenze non impostate e gli articoli non riconosciuti richiedono una verifica manuale prima della conferma.

Il Buono Tech è convalidato solo per il primo riepilogo del mese associato all'email o al telefono, se codice, importo e subtotale rispettano il calcolo e i limiti configurati in `site.json`. Il periodo usa la data dell'email nel fuso `Europe/Rome`. Ogni codice convalidato è registrato nella tabella locale `valid_vouchers` e mostrato nella lista "Buoni Tech validi"; i codici già registrati non possono essere riutilizzati. Se il riepilogo non contiene il valore del buono o il subtotale, il gestionale mostra "Da verificare" e non aggiunge il codice alla lista. Il database SQLite locale registra ordini e contatti per evitare riutilizzi; limita l'accesso al file e proteggilo nei backup. Il riepilogo EmailJS non è firmato crittograficamente: limita l'accesso alla casella e i domini autorizzati EmailJS. Questa automazione non prova l'autenticità dell'ordine né il pagamento; la conferma commerciale resta a carico dell'attività.

## Consegne ricorrenti e itinerari

La scheda Ordini separa gli ordini ancora operativi dallo Storico ordini. Un ordine confermato passa allo storico quando risulta consegnato e non ha una ricorrenza attiva; se una ricorrenza viene disattivata, l'eventuale consegna già programmata resta tra gli ordini in corso fino al completamento.

`python3 -m gestionale route` resta disponibile per inserire manualmente un giro da terminale. Nella UI, la scheda Consegne include gli ordini confermati non ancora consegnati per la data assegnata; dopo la prima conferma manuale, le ricorrenze attive avanzano alla cadenza concordata quando la consegna viene registrata. Ogni occorrenza ricorrente compare nel planner solo nel giorno previsto, con frequenza e giorno richiesto; la ricorrenza si disattiva dalla riga della consegna senza annullare quella già in programma. Il controllo di stock alloca virtualmente i pezzi in ordine di data e ricezione, senza modificare la giacenza. Il giro dà precedenza alla città di partenza, salvo città con orari richiesti più urgenti; all'interno di ogni città ordina per fascia e orario, mantenendo l'ordine di ricezione a parità o senza preferenze. Se un orario specifico o una fascia generica non è compatibile con l'orario complessivo del giro, la UI mostra un avviso. Maps riceve le tappe nell'ordine indicato ma non ottimizza le distanze e non garantisce l'orario di arrivo; Calendar crea un solo evento per la finestra generale scelta e include nei dettagli data, preferenza, prodotti, note e cadenza richiesta. Per più di nove tappe intermedie vengono creati più link.

## Interfaccia web locale

Avvia il gestionale solo sul computer locale:

```bash
python3 -m gestionale web
```

Apri `http://127.0.0.1:8765/`. La schermata permette di cercare prodotti e impostare o incrementare le giacenze, sincronizza automaticamente la posta ogni minuto e consente di verificare e confermare gli ordini uno alla volta. La scheda Consegne prepara link Maps e Calendar dagli ordini confermati per la data selezionata. Il server resta legato a `127.0.0.1` e non è esposto alla rete; chiudilo con `Ctrl+C`. Se la porta è occupata, avvia con `python3 -m gestionale web --port 8766`.

## Test

```bash
python3 -m unittest gestionale.test_gestionale -v
```
