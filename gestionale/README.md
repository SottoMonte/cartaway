# Gestionale locale Cartaway

Backend, interfaccia web e test sono raccolti in questa cartella. I file `../data/products.json` e `../data/site.json` restano nella radice perché sono condivisi con il negozio e il CMS; il programma non legge la configurazione YAML del CMS. Se necessario, i percorsi dei JSON si possono cambiare con le opzioni `--products` e `--site`. Il database SQLite viene salvato fuori dal repository in `~/.local/share/cartaway/gestionale.sqlite3`.

I comandi seguenti si eseguono dalla cartella principale del progetto. Il gestionale richiede Python 3.9 o successivo; la generazione dei PDF usa ReportLab.

## Avvio e comandi

```bash
python3 -m pip install -r gestionale/requirements.txt
python3 -m gestionale init
python3 -m gestionale stock list
python3 -m gestionale stock set carta-igienica-mini-jumbo-12-rotoli 20
python3 -m gestionale stock add carta-igienica-mini-jumbo-12-rotoli 5
python3 -m gestionale orders
python3 -m gestionale route
```

Le giacenze partono come "da impostare": inizializzale con `stock set`, poi aggiornatele con `stock set` o `stock add`. Nell'interfaccia e nei comandi stock, la quantità inserita è espressa in confezioni della variante selezionata. Per condividere l'inventario tra formati dello stesso articolo, assegna loro lo stesso campo opzionale `stock_group` in `data/products.json` (modificabile anche dal CMS). Il gestionale converte ogni confezione usando `unit.quantity` nell'unità `unit.measure`: per esempio, un gruppo con confezioni da 2 e 6 rotoli tiene un unico saldo in rotoli, e consegnare un pacco da 6 ne sottrae sei. Le varianti dello stesso gruppo devono usare la stessa unità di misura; la schermata mostra sia i pacchi disponibili per variante sia il totale condiviso. Al primo avvio dopo aver associato prodotti con `stock_group`, le vecchie giacenze si sommano convertite solo se sono tutte impostate; se anche una è da censire, il nuovo saldo condiviso resta "da impostare" per evitare quantità inventate: fai il conteggio fisico e impostalo da una delle varianti.

Se aggiungi a un gruppo esistente una variante con giacenza autonoma nota, il gestionale la converte e la somma al saldo condiviso; se quella giacenza è da impostare, anche il saldo del gruppo diventa da censire. Prima di rimuovere o cambiare `stock_group`, oppure modificare `unit.measure`, porta il saldo condiviso a zero e completa le consegne già confermate. Con una giacenza attiva la modifica viene rifiutata; inoltre, lo scarico di un ordine confermato viene fermato se gruppo o unità non corrispondono a quelli registrati alla conferma.

Nell'interfaccia, "Imposta giacenza" sostituisce la quantità registrata; "Aggiungi pezzi" incrementa quella già presente. Le richieste e la conferma email non scalano lo stock: nella scheda Consegne, dopo la consegna effettiva, usa "Segna consegnato" sull'ordine. Il gestionale sottrae una sola volta le quantità dell'ordine e registra data e ora. Se la giacenza non basta o non è impostata, non modifica né stock né stato: aggiorna prima la quantità fisica e riprova. Gli articoli marcati `available: false` nel catalogo risultano non disponibili; se la quantità locale non è stata impostata, l'app segnala che serve una verifica invece di dichiarare il prodotto esaurito.

Per ricevere le richieste, configura una copia CC/BCC del template EmailJS verso una casella operativa. Imposta le variabili d'ambiente prima di avviare la lettura; non salvarle nel repository:

```text
IMAP_HOST, IMAP_USER, IMAP_PASSWORD
SMTP_HOST, SMTP_USER, SMTP_PASSWORD
```

La sincronizzazione legge solo i messaggi non letti della cartella `INBOX`, per evitare di elaborare lo storico o i messaggi inviati, e marca come letti i riepiloghi importati. Per le caselle Aruba standard usa `IMAP_HOST=imaps.aruba.it` e `IMAP_PORT=993`; `smtps.aruba.it` è il server SMTP in uscita. Per PEC o servizi Aruba diversi verifica i parametri specifici del provider. Ogni richiesta già registrata viene ignorata. Le giacenze non impostate e gli articoli non riconosciuti richiedono una verifica manuale prima della conferma.

Il Buono Tech è convalidato solo per il primo riepilogo del mese associato all'email o al telefono, se codice, importo e subtotale rispettano il calcolo e i limiti configurati in `site.json`. Il periodo usa la data dell'email nel fuso `Europe/Rome`. Ogni codice convalidato è registrato nella tabella locale `valid_vouchers` e mostrato nella lista "Buoni Tech validi"; i codici già registrati non possono essere riutilizzati. Se per un ordine ricorrente mancano il subtotale o lo sconto, il gestionale tenta di ricostruire il subtotale netto dal totale e dalla consegna salvati, senza riapplicare lo sconto. Se mancano anche questi importi o il valore del buono, mostra "Da verificare" e non aggiunge il codice alla lista. Per gli ordini già confermati, la scheda Ordini mostra "Registra buono" quando il voucher è recuperabile; l'azione non invia email e non modifica le consegne programmate. Il database SQLite locale registra ordini e contatti per evitare riutilizzi; limita l'accesso al file e proteggilo nei backup. Il riepilogo EmailJS non è firmato crittograficamente: limita l'accesso alla casella e i domini autorizzati EmailJS. Questa automazione non prova l'autenticità dell'ordine né il pagamento; la conferma commerciale resta a carico dell'attività.

## Consegne ricorrenti e itinerari

La scheda Ordini separa gli ordini ancora operativi dallo Storico ordini. Un ordine confermato passa allo storico quando risulta consegnato e non ha una ricorrenza attiva; se una ricorrenza viene disattivata, l'eventuale consegna già programmata resta tra gli ordini in corso fino al completamento. Gli ordini rifiutati passano allo storico e restano distinguibili dalle consegne completate. "Rifiuta ordine" richiede una conferma esplicita e invia al cliente un'email standard; se l'invio fallisce l'ordine resta da confermare, mentre se manca l'indirizzo email il rifiuto viene registrato e lo storico segnala che l'email non è stata inviata.

`python3 -m gestionale route` resta disponibile per inserire manualmente un giro da terminale. Nella UI, la scheda Consegne include gli ordini confermati non ancora consegnati per la data assegnata; dopo la prima conferma manuale, le ricorrenze attive avanzano alla cadenza concordata quando la consegna viene registrata. Ogni occorrenza ricorrente compare nel planner solo nel giorno previsto, con frequenza e giorno richiesto; la ricorrenza si disattiva dalla riga della consegna senza annullare quella già in programma. Il controllo di stock alloca virtualmente i pezzi in ordine di data e ricezione, senza modificare la giacenza. L'itinerario dà precedenza alla città di partenza quando gli orari lo consentono; gli appuntamenti con orario specifico vengono mantenuti in ordine temporale e le altre città sono inserite minimizzando la deviazione stimata sui centri comunali. Preferenze e note dell'ordine sono riportate nei dettagli Calendar; gli orari effettivi di arrivo dipendono da strade e traffico e vanno verificati. Gli ordini incompatibili con le fasce configurate o con il turno selezionato restano non assegnati e vengono mostrati con il motivo. Maps mantiene l'ordine delle tappe e calcola il tragitto stradale; non garantisce l'orario di arrivo. Per più di nove tappe intermedie vengono creati più link.

Nella scheda Consegne, il riepilogo Carico previsto somma le quantità degli ordini disponibili e pronti per la data. Per ogni prodotto puoi indicare `volume_liters` in `data/products.json` (per esempio `"volume_liters": 2.5`): è il volume in litri per confezione/unità venduta e ha la precedenza sulla misura manuale. I valori attualmente inseriti sono stime conservative basate sulle specifiche disponibili, non misure certificate dell'imballo: verifica i prodotti reali prima di affidarti alla capacità del furgone. Se il campo manca, la misura si può inserire da Consegne e resta salvata nel database locale; anche la capacità utile di ciascun furgone viene configurata lì. La scheda Impostazioni permette di configurare le fasce operative (inizialmente 09:00–13:00 e 15:00–18:00), il punto di partenza predefinito, l'orario standard del turno, i minuti per consegna e la velocità media stimata. Le fasce sono vincoli per tutti i planner e devono essere in ordine e senza sovrapposizioni; l'orario del singolo giro può comunque restringere il turno. Con un solo furgone il planner crea giri sequenziali, mantiene intero ogni ordine, considera prima le finestre orarie e riusa l'ottimizzazione delle tappe per comune. Se una finestra costringerebbe il mezzo ad attendere oltre due ore tra una consegna e la successiva, il planner chiude il giro, considera rientro e ricarica e ne crea uno nuovo per l'appuntamento tardivo. Ogni giro mostra partenza, arrivo alle consegne, rientro o fine giro e l'ora da cui il mezzo è disponibile per una nuova partenza; Maps e Calendar ricevono link distinti per giro. La stima usa i centri comunali, un fattore stradale 1,35, velocità e minuti per consegna configurabili, 20 minuti per ricaricare e, se mancano coordinate, 25 minuti per tratta. Sono valori indicativi, non ETA di Google Maps: controlla traffico e tempi effettivi. Se una scadenza non è raggiungibile nel turno, la UI mostra l'avviso; se un singolo ordine supera la capacità o manca una misura, resta non assegnato. La ripartizione considera solo il volume dichiarato, non peso, forma o possibilità fisica di incastro: usa capacità utili prudenti e verifica il carico reale.

## Interfaccia web locale

Avvia il gestionale solo sul computer locale:

```bash
python3 -m gestionale web
```

Apri `http://127.0.0.1:8765/`. La schermata aggiorna automaticamente riepilogo, ordini, inventario e consegne ogni 30 secondi; la posta si sincronizza ogni minuto. Il pulsante "Aggiorna dati" resta disponibile per un aggiornamento immediato. La schermata permette anche di cercare prodotti, impostare o incrementare le giacenze e verificare, confermare o rifiutare gli ordini uno alla volta. Il rifiuto richiede una conferma nel browser prima dell'invio dell'email standard. La scheda Consegne prepara link Maps e Calendar dagli ordini confermati per la data selezionata. Il server resta legato a `127.0.0.1` e non è esposto alla rete; chiudilo con `Ctrl+C`. Se la porta è occupata, avvia con `python3 -m gestionale web --port 8766`.

## Test

```bash
python3 -m unittest gestionale.test_gestionale -v
```
