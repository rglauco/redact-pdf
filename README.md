# Redact PDF v3.0 - Guida Deployment

## Cosa fa

Converte le annotazioni rettangolari (quadrati, cerchi, ink, ecc.)
aggiunte con PDF-XChange Editor o altri editor PDF in **redazioni vere**
che rimuovono permanentemente il testo e le immagini sottostanti.

Dalla v3.0 include anche un **editor visuale**: si possono disegnare le
redazioni direttamente sul PDF col mouse, senza usare un altro programma.

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

- **▭ Rettangolo** — trascina per coprire un'area. Funziona **anche sui PDF
  scansionati**.
- **✎ Testo** — trascina sul testo da nascondere: si aggancia alle parole
  (solo PDF con testo reale, non scansioni).
- **〰 Mano libera** — traccia col mouse sopra firme, timbri, aree irregolari.
- **↶ Annulla** (Ctrl+Z), navigazione pagine, zoom + / −.
- **✔ Applica e salva** (Ctrl+S) → crea `nomefile_redacted.pdf`.

Le redazioni rimuovono **davvero** il contenuto sottostante; l'originale non
viene modificato.


## Troubleshooting

- Log: `redact_pdf.log` accanto all'EXE
- Annotazioni supportate (modalità batch): Square, Circle, Ink, Polygon, PolyLine, Line, Highlight, StrikeOut
- Se il drag & drop non funziona: usare il pulsante Sfoglia (windnd opzionale)
- **PDF scansionati**: usare lo strumento **Rettangolo** (la selezione testo non
  funziona dove non c'è testo vero). Dalla v3.0 redarre una scansione non
  "spagina" più il documento: viene cancellata solo l'area coperta.
- Verifica rapida della logica senza interfaccia: `redact_pdf.exe --selftest`
