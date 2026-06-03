# Redact PDF v3.3 - Guida Deployment

---

## ⚠️ Prima esecuzione — avvisi di sicurezza (Windows e macOS)

L'eseguibile **non è firmato digitalmente** (la firma costa centinaia di euro/anno).
Il file è sicuro: il codice sorgente è interamente disponibile in questo repository
e chiunque può verificarlo. Gli avvisi qui sotto sono normali per qualsiasi programma
gratuito e indipendente distribuito senza certificato commerciale.

### Windows — SmartScreen

Al primo avvio Windows mostra *"Il PC è stato protetto"*:

1. Clicca **"Ulteriori informazioni"** (in basso a sinistra nella finestra dell'avviso).
2. Clicca **"Esegui comunque"**.

Questo passaggio va fatto **una volta sola**: le esecuzioni successive non mostrano
più l'avviso.

In alternativa, prima di eseguire il file:

1. Tasto destro sull'EXE → **Proprietà**.
2. In fondo alla scheda *Generale*, spunta **"Sblocca"**.
3. Clicca OK.

### macOS — Gatekeeper

macOS blocca l'apertura di applicazioni scaricate da internet non firmate da Apple.

**Metodo 1 — clic destro (più semplice):**

1. Tasto destro (o Control+clic) sul file → **Apri**.
2. Nella finestra di avviso clicca **"Apri"**.

Anche qui basta farlo **una volta sola**.

**Metodo 2 — Impostazioni di Sistema:**

1. Prova ad aprire il file normalmente (verrà bloccato).
2. Vai in **Impostazioni di Sistema → Privacy e Sicurezza**.
3. Scorri fino alla sezione *Sicurezza*: trovi il messaggio relativo al file bloccato.
4. Clicca **"Apri comunque"**.

**Metodo 3 — Terminale (rimuove il blocco in modo definitivo):**

```bash
xattr -d com.apple.quarantine /percorso/redact_pdf
```

---

## Cosa fa

Converte le annotazioni rettangolari (quadrati, cerchi, ink, ecc.)
aggiunte con PDF-XChange Editor o altri editor PDF in **redazioni vere**
che rimuovono permanentemente il testo e le immagini sottostanti.

Dalla v3.0 include anche un **editor visuale**: si possono disegnare le
redazioni direttamente sul PDF col mouse, senza usare un altro programma.

## Novità v3.3 — Eliminazione puntuale dei segni

> **Problema risolto:** con il solo Ctrl+Z era impossibile rimuovere un segno
> specifico (es. il primo di cinquanta) senza annullare anche tutti quelli
> successivi.

Nuovo strumento **↖ Selezione** nell'editor visuale:

1. Cliccare su **↖ Selezione** nella barra strumenti.
2. Cliccare su qualsiasi segno già disegnato: si evidenzia con **bordo rosso**.
3. Premere **Canc** (o Backspace) oppure il pulsante **"🗑 Elimina selezionato"**
   per rimuoverlo — gli altri segni restano intatti.

In caso di segni sovrapposti viene selezionato automaticamente quello con
area minore. La selezione si azzera cambiando strumento o pagina.


## Doppia modalità

- **Con argomenti** (es. "Invia a"): elaborazione silenziosa, nessuna finestra
- **Senza argomenti** (doppio clic): interfaccia grafica con drag & drop
  **+ editor visuale** (doppio clic su un file in lista, o "Apri ed edita")


## File inclusi

| File                | Descrizione                                        |
|---------------------|----------------------------------------------------|
| `redact_pdf.py`     | Sorgente Python                                    |
| `build.bat`         | Compila l'EXE con PyInstaller                      |
| `deploy_gpo.bat`    | Deploy via GPO (crea .lnk in SendTo)               |


## Istruzioni

### 1. Compilare l'EXE

Su una macchina con Python 3.8+:

```
cd redact-pdf
build.bat
```

L'EXE viene creato in `dist\redact_pdf.exe`.


### 2. Preparare la share di rete

```
\\SERVER\tools$\RedactPDF\
    redact_pdf.exe
    deploy_gpo.bat
```

Permessi: Domain Users → Lettura + Esecuzione


### 3. Configurare il percorso

In `deploy_gpo.bat` modificare:

```
set "EXE_PATH=\\SERVER\tools$\RedactPDF\redact_pdf.exe"
```


### 4. Deploy GPO

1. Copiare `deploy_gpo.bat` in `\\SERVER\NETLOGON\`
2. GPO > User Configuration > Policies > Windows Settings > Scripts > Logon
3. Aggiungere `deploy_gpo.bat`
4. `gpupdate /force`

Ogni utente trova **"Redact PDF"** in Invia a.


### 5. Aggiornamento

Sostituire `redact_pdf.exe` sulla share. Le macchine usano sempre l'ultima versione.


## Uso

### Modalità silenziosa (Invia a)
Tasto destro su PDF > Invia a > Redact PDF
→ `nomefile_redacted.pdf` appare nella stessa cartella, nessuna finestra

### Modalità grafica (doppio clic)
Lanciare `redact_pdf.exe` senza argomenti
→ Si apre la GUI: trascinare i PDF, cliccare REDACT (modalità batch)

### Editor visuale (novità v3.0)
Nella GUI, **doppio clic** su un file in lista (o selezionarlo e premere
**"Apri ed edita"**) apre l'editor:

| Strumento | Scorciatoia | Descrizione |
|-----------|-------------|-------------|
| **▭ Rettangolo** | — | Trascina per coprire un'area. Funziona **anche sui PDF scansionati**. |
| **✎ Testo** | — | Trascina sul testo da nascondere: si aggancia alle parole (solo PDF con testo reale). |
| **〰 Mano libera** | — | Traccia col mouse sopra firme, timbri, aree irregolari. |
| **↖ Selezione** *(v3.3)* | — | Clicca su un segno per selezionarlo (bordo rosso), poi Canc per eliminarlo. |
| **↶ Annulla** | Ctrl+Z | Annulla l'ultimo segno aggiunto. |
| **🗑 Elimina selezionato** *(v3.3)* | Canc | Elimina il segno selezionato, gli altri restano intatti. |
| **✔ Applica e salva** | Ctrl+S | Crea `nomefile_redacted.pdf`. |

Le redazioni rimuovono **davvero** il contenuto sottostante; l'originale non
viene modificato.


## Test

La suite copre la logica di redazione senza GUI: `mark_to_rects`, `apply_secure_redactions`,
`process_pdf` su PDF vettoriale (rimozione testo) e su PDF scansionato (pixel-level).

### Prerequisiti

```bash
uv sync --group dev
```

### Esecuzione

```bash
uv run pytest
# oppure con output dettagliato:
uv run pytest -v
```

I file di riferimento (`scan.pdf`, `vector.pdf`) si trovano in `tests/resources/`.
Ogni test usa una copia temporanea e non modifica i file originali.


## Troubleshooting

- Log: `redact_pdf.log` accanto all'EXE
- Annotazioni supportate (modalità batch): Square, Circle, Ink, Polygon, PolyLine, Line, Highlight, StrikeOut
- Se il drag & drop non funziona: usare il pulsante Sfoglia (windnd opzionale)
- **PDF scansionati**: usare lo strumento **Rettangolo** (la selezione testo non
  funziona dove non c'è testo vero). Dalla v3.0 redarre una scansione non
  "spagina" più il documento: viene cancellata solo l'area coperta.
- Verifica rapida della logica senza interfaccia: `redact_pdf.exe --selftest`
