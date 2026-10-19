# Cartaway

Negozio statico in italiano per prodotti di carta con consegna locale a Montoro e nei comuni vicini. Contatti e catalogo sono file JSON; Decap CMS li modifica senza database o server applicativo. Il carrello invia al cliente un riepilogo via email con EmailJS; non inoltra la richiesta all'attività. WhatsApp resta disponibile per i contatti diretti. Data e fascia oraria sono facoltative, e non sono attivi pagamenti online.

`index.html` è la pagina principale e ospita il catalogo completo con ricerca, filtri, carrello e confronto dei prezzi. `catalogo.html` è mantenuta come URL storico e reindirizzata alla pagina principale su Netlify. `chi-siamo.html` presenta il servizio, `primi-passi.html` spiega come ordinare e `faq.html` raccoglie le risposte frequenti. Ogni scheda prodotto apre `/prodotti/ID-PRODOTTO/`; gli URL storici `prodotto.html?id=ID-PRODOTTO` restano supportati.

## Avvio locale

Dalla cartella del progetto avvia un server statico:

```bash
python3 -m http.server 4173
python3 -m gestionale web --port 8765
```

Apri `http://localhost:4173`. La pagina `/admin` va collegata a Decap Turbo prima di consentire modifiche online.


## Pubblicazione

1. Crea un repository GitHub sul branch `main` e carica il progetto.
2. Su Netlify importa quel repository. Imposta il comando di build su `node scripts/generate-sitemap.mjs` e la cartella di pubblicazione su `.`; aggiungi poi il dominio personalizzato. Le schede statiche dei prodotti e la sitemap vengono rigenerate dal catalogo a ogni pubblicazione.
3. Crea l'organizzazione Decap Turbo con l'account del cliente. Il piano Free include un sito e un utente, quindi l'account cliente deve essere il proprietario. Collega GitHub, installa l'app Turbo sul repository e crea un sito con branch `main`, percorso di configurazione `admin/config.yml` e URL admin `https://IL-TUO-SITO/admin/`.
4. Copia la Site ID mostrata da Turbo in `admin/config.yml`, al posto di `SOSTITUISCI-CON-LA-SITE-ID-DECAP-TURBO`, e invia la modifica a GitHub. Netlify pubblicherà la configurazione aggiornata.
5. Accedi da `https://IL-TUO-SITO/admin/` con Decap Turbo. Da lì il cliente può aggiornare i recapiti e i prodotti; ogni salvataggio aggiorna il JSON su GitHub e avvia una nuova pubblicazione.

Il CMS usa il backend GitHub di Decap Turbo, distribuito al momento come release beta: lo script in `admin/index.html` è fissato alla versione indicata nella documentazione. Il piano Turbo Free attuale include un sito e un utente; altri utenti o siti richiedono un piano superiore. Mantieni aggiornato in Turbo l'URL admin anche dopo aver collegato il dominio definitivo.

## Dati e contatti

- `data/products.json`: prodotti, profili attività (ID configurati in `site.profiles`), categoria come array di percorso dal livello principale alla sottocategoria (per esempio `["Monouso in carta", "Rotoloni"]`), confezione, prezzo, foto principale, foto aggiuntive, caratteristiche e disponibilità. Il percorso deve esistere nell'albero `categories` di `data/site.json`; il CMS carica profili e categorie da lì. Prezzi e stock iniziali sono dimostrativi: sostituiscili con quelli effettivi prima della pubblicazione.
- `data/site.json`: nome, zona, recapiti, indirizzo e dati dell'impresa. `profiles` contiene ID e nomi visualizzati delle attività. `prices_include_vat` specifica se i prezzi sono lordi; ogni nodo di `categories` contiene `name`, `vat_rate` ed eventuali `children`. Verifica le aliquote con la documentazione fiscale prima di compilarle. Se i prezzi sono IVA esclusa, configura l'aliquota sul nodo corrispondente al percorso di ogni prodotto.
- Il catalogo iniziale usa immagini dimostrative da Unsplash. Caricando le foto definitive da Decap, i file vengono salvati in `uploads/` nel repository.

I tempi di consegna sono indicativi: Montoro circa 2 ore, comuni vicini in giornata e, per la Zona 03, spedizione standard con tempi variabili. Le tariffe vengono calcolate in base alla zona; i dettagli dell'ordine vengono confermati dall'attività dopo la richiesta.

## Email ordini

Il checkout invia al cliente un riepilogo, non una conferma d'ordine, e non trasmette la richiesta all'attività. Per la gestione locale di ordini, giacenze e consegne, consulta la [guida del gestionale](gestionale/README.md).

Configura una copia all'attività come CC/BCC nel template EmailJS. Il parametro `reply_to` è solo l'indirizzo a cui il cliente può rispondere, non invia una copia. Crea un servizio e un template, poi configura nel CMS Public Key, Service ID e Template ID.

Il codice HTML pronto da incollare nel template EmailJS è in `email/order-summary.html`. Imposta `To Email` su `{{email}}`, `Reply To` su `{{reply_to}}` e oggetto su `Riepilogo richiesta #{{order_id}} - {{brand}}`. Allega il logo come immagine inline con Content ID esatto `logo.png` perché il template lo richiama con `cid:logo.png`. Le immagini prodotto usano URL pubblici assoluti.

Il template riceve `brand`, `website_url`, `cart_url`, `order_id`, `email`, `reply_to`, `orders` (array con `name`, `units`, `price` unitario, `line_total`, `image_url`), `cost.shipping`, `cost.tax`, `cost.total`, `tech_voucher_id`, `tech_voucher_value`, `tech_voucher_percent` (percentuale applicata all'ordine), `tech_voucher_standard_percent`, `tech_voucher_recurring_percent`, `tech_voucher_maximum`, `tech_voucher_validity`, `customer_name`, `customer_email`, `customer_phone`, `delivery_address`, `delivery_city`, `delivery_zone`, `estimated_delivery_time`, `preferred_delivery_date`, `preferred_delivery_time`, `delivery_notes`, `recurring_order`, `recurring_frequency`, `recurring_day`, `recurring_discount` e `price_lock_months`. Il link `cart_url` ricrea il carrello con i prodotti e le quantità della richiesta precedente per preparare un riordino; non conserva i dati di consegna e usa prezzi e disponibilità correnti. Le percentuali singola e ricorrente sono lette dalla configurazione del sito (25% e 50% predefiniti), fino al massimale configurato; il codice è candidato, il valore stimato e l'attivazione resta soggetta a verifica manuale sul primo ordine mensile del cliente. Imposte e costi non determinabili sono mostrati come "Da confermare".

Il campo `email` è il destinatario cliente; `reply_to` usa l'email di contatto dell'attività configurata in `data/site.json`. Sostituisci il valore dimostrativo prima del rilascio, limita in EmailJS i domini autorizzati al dominio del negozio e verifica l'invio reale. Questi identificativi sono pubblici nel browser: non inserire chiavi private o credenziali del provider email. L'email è solo un riepilogo al cliente; per trasmettere l'ordine all'attività serve un canale separato.

La tabella costi del template email riceve `cost.products` (subtotale a prezzo pieno) e `cost.discount` (sconto già sottratto dal totale). Gli articoli in `orders` mostrano i prezzi unitari a prezzo pieno e includono `product_url` per aprire la scheda prodotto.

## Gestionale locale

Il codice, l'interfaccia e i test del gestionale sono raccolti nella cartella `gestionale/`. Le istruzioni per configurazione, avvio e uso sono nella [guida dedicata](gestionale/README.md).

## Costi e limiti

Netlify Free costa attualmente €0 e include un limite di 300 crediti al mese. Le pubblicazioni di produzione e il traffico consumano crediti: oltre la quota il servizio può fermarsi fino al rinnovo o richiedere un piano superiore. Controlla i consumi e non attivare ricariche automatiche se l'obiettivo è non superare il budget. Il costo del dominio resta separato. Le quote e i piani dei servizi possono cambiare.

Per un sito commerciale non usare il piano Vercel Hobby: i termini attuali lo limitano a progetti personali o non commerciali.

## SEO

La pagina principale `/` è il catalogo e la sua canonical è l'URL principale. `_redirects` consolida `/index.html` e `/catalogo.html` su `/`. Il comando di build genera una pagina HTML distinta per ogni prodotto disponibile in `/prodotti/ID/`, con contenuti, canonical, metadati e JSON-LD già presenti nell'HTML iniziale. Genera inoltre `sitemap.xml` con gli URL canonici delle pagine pubbliche e dei prodotti disponibili in `data/products.json`; `robots.txt` la pubblica. Gli URL storici `prodotto.html?id=ID` continuano a funzionare e impostano la canonical sulla nuova scheda. Lo schema `Product` include un'offerta solo quando il prezzo visualizzato è calcolabile; non vengono inventate recensioni o valutazioni. I dati generici `Organization` non sostituiscono una scheda Google Business Profile verificata. Su Netlify, `_headers` applica `X-Robots-Tag: noindex` al frammento HTML usato come template email.