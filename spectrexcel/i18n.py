"""Minimal dict-based translation layer.

English is the source language: wrap user-facing strings with _() at the point
of use and add the Italian translation to TRANSLATIONS_IT. Use
_("... {value} ...").format(value=...) for interpolation; never wrap f-strings,
as runtime values would end up in the lookup key. The optional info worksheet
follows the app language; measurement sheets and charts are not translated.

The language is selected once at startup (Settings > main/language, falling
back to the OS locale) and applies to the whole UI on the next launch.
"""

import locale
import os
import sys

LANGUAGES = {"en": "English", "it": "Italiano"}

TRANSLATIONS_IT: dict[str, str] = {
    "Layout:": "Layout:",
    "ERROR: unable to save the layout preference":
        "ERRORE: impossibile salvare la preferenza del layout",
    "Updating chart...": "Aggiornamento del grafico...",
    "Loading chart data...": "Caricamento dei dati del grafico...",
    "Select input files to preview the chart.":
        "Seleziona i file di input per visualizzare l'anteprima del grafico.",
    "Unable to preview chart: {error}": "Impossibile visualizzare l'anteprima: {error}",
    "Unable to preview chart: input loading failed.":
        "Impossibile visualizzare l'anteprima: caricamento dei file non riuscito.",
    "parameters only": "solo parametri",
    "parameters + preview": "parametri + anteprima",
    "axis minimum must be lower than its maximum":
        "il minimo dell'asse deve essere inferiore al massimo",
    "Include info sheet": "Includi foglio info",
    # optional info worksheet
    "SpectrExcel version": "Versione di SpectrExcel",
    "Export timestamp": "Data e ora di esportazione",
    "Reproduction": "Riproducibilità",
    "Retain original input files; hashes identify the loaded inputs.":
        "Conserva i file di input originali; gli hash identificano gli input caricati.",
    "Sources": "Fonti",
    "Filename": "Nome file",
    "Source file": "File sorgente",
    "Settings": "Impostazioni",
    "Value": "Valore",
    "Processing": "Elaborazione",
    "Step": "Passaggio",
    "Processing step": "Passaggio di elaborazione",
    "Chart spectrum stride": "Passo degli spettri nel grafico",
    "Duplicate spectra removed": "Spettri duplicati rimossi",
    "Disabled": "Disabilitata",
    "Yes": "Sì",
    "No": "No",
    "unknown": "sconosciuta",
    "Subtract each spectrum's absorbance at the correction wavelength.":
        "Sottrai l'assorbanza di ogni spettro alla lunghezza d'onda di correzione.",
    "Export all spectra; plot every second spectrum, starting with the first.":
        "Esporta tutti gli spettri; rappresenta uno spettro ogni due, iniziando dal primo.",
    "Remove identical repeated half of spectra.":
        "Rimuovi la metà ripetuta identica degli spettri.",
    "Remove standard-deviation column.":
        "Rimuovi la colonna della deviazione standard.",
    "Plot all exported spectra.": "Rappresenta tutti gli spettri esportati.",
    "Subtract correction-wavelength absorbance from reading-wavelength absorbance.":
        "Sottrai l'assorbanza alla lunghezza d'onda di correzione da quella alla lunghezza d'onda di lettura.",
    "Shift each trace's timestamps so its first measurement is at zero seconds.":
        "Trasla i tempi di ogni traccia in modo che la prima misura sia a zero secondi.",
    "Keep original acquisition intervals; export traces in the listed source order.":
        "Mantieni gli intervalli di acquisizione originali; esporta le tracce nell'ordine delle fonti elencate.",
    # main window
    "Check updates": "Verifica aggiornamenti",
    "Checking...": "Verifica in corso...",
    "Update {tag}": "Aggiorna a {tag}",
    "App settings": "Impostazioni",
    "ACTIVITY": "ATTIVITÀ",
    "Developed by Alberto Mosconi": "Sviluppato da Alberto Mosconi",
    "DOI: ": "DOI: ",
    "Source code": "Codice sorgente",
    "All versions; resolves to latest release.":
        "Tutte le versioni; rimanda alla versione più recente.",
    "Cite SpectrExcel version {version}.": "Cita SpectrExcel versione {version}.",
    "LOADED ASSAY: {name}": "ASSAY CARICATO: {name}",
    # assay names
    "binding / titration": "binding / titolazione",
    "kinetics": "cinetiche",
    "spectrum family": "famiglia di spettri",
    "About assay": "Informazioni sull'assay",
    "Compare absorbance spectra from binding or titration experiments "
    "and export them for further analysis. Select a TXT or SD file and "
    "choose chart axis ranges. SpectrExcel removes the standard-deviation "
    "column, if present, and keeps one copy of identical repeated halves. "
    "Optional correction subtracts absorbance at a reference wavelength "
    "from each spectrum to remove a constant baseline offset. Choose a "
    "wavelength where your sample does not absorb. When correction is "
    "applied, a raw sheet preserves values before subtraction.":
        "Confronta gli spettri di assorbanza di esperimenti di binding o "
        "titolazione ed esportali per ulteriori analisi. Seleziona un file "
        "TXT o SD e scegli gli intervalli degli assi del grafico. SpectrExcel "
        "rimuove la colonna della deviazione standard, se presente, e conserva "
        "una sola copia di due metà identiche ripetute. La correzione "
        "facoltativa sottrae da ogni spettro l'assorbanza a una lunghezza "
        "d'onda di riferimento per rimuovere uno spostamento costante della "
        "linea di base. Scegli una lunghezza d'onda a cui il campione non "
        "assorbe. Quando applichi la correzione, un foglio raw conserva i "
        "valori prima della sottrazione.",
    "Export absorbance changes over time from KD files, in your chosen "
    "file order. SpectrExcel subtracts absorbance at a reference wavelength "
    "from absorbance at the reading wavelength to remove a constant "
    "baseline offset. Choose a reference wavelength where your sample "
    "does not absorb. Each trace starts at zero seconds at its first "
    "recorded measurement, not necessarily the start of the reaction. "
    "The Excel file includes a comparison chart and a raw sheet with "
    "values before subtraction. Reaction rates and rate constants "
    "are not calculated.":
        "Esporta le variazioni di assorbanza nel tempo da file KD, nell'ordine "
        "scelto. SpectrExcel sottrae l'assorbanza a una lunghezza d'onda di "
        "riferimento da quella alla lunghezza d'onda di lettura per rimuovere "
        "uno spostamento costante della linea di base. Scegli una lunghezza "
        "d'onda di riferimento a cui il campione non assorbe. Ogni traccia "
        "parte da zero secondi alla prima misura registrata, non "
        "necessariamente all'inizio della reazione. Il file Excel "
        "include un grafico di confronto e un foglio raw con i valori prima "
        "della sottrazione. Non vengono calcolate velocità di reazione o "
        "costanti cinetiche.",
    "Export absorbance spectra recorded over time from one KD file. "
    "Tables include acquisition times, wavelengths, and all spectra; "
    "charts show every second spectrum, starting with the first. "
    "Optional correction subtracts absorbance at a reference wavelength "
    "from each spectrum to remove a constant baseline offset. Choose a "
    "wavelength where your sample does not absorb. When correction is "
    "applied, a raw sheet preserves values before subtraction.":
        "Esporta gli spettri di assorbanza registrati nel tempo da un file KD. "
        "Le tabelle includono i tempi di acquisizione, le lunghezze d'onda e "
        "tutti gli spettri; i grafici mostrano uno spettro ogni due, "
        "iniziando dal primo. La correzione facoltativa sottrae da ogni "
        "spettro l'assorbanza a una lunghezza d'onda di riferimento per "
        "rimuovere uno spostamento costante della linea di base. Scegli una "
        "lunghezza d'onda a cui il campione non assorbe. Quando applichi la "
        "correzione, un foglio raw conserva i valori prima della sottrazione.",
    # settings modal
    "Theme:": "Tema:",
    "System": "Sistema",
    "Light": "Chiaro",
    "Dark": "Scuro",
    "System is detected now. Restart or reselect System after changing your OS theme.":
        "Il tema di sistema è attivo. Riavvia o riseleziona 'Sistema' dopo "
        "aver cambiato il tema del sistema operativo.",
    "Language:": "Lingua:",
    "Restart SpectrExcel to apply the language.":
        "Riavvia SpectrExcel per applicare la lingua.",
    "Close": "Chiudi",
    "ERROR: unable to save the theme preference":
        "ERRORE: impossibile salvare la preferenza del tema",
    "ERROR: unable to save the language preference":
        "ERRORE: impossibile salvare la preferenza della lingua",
    # update flow
    "checking for updates...": "verifica degli aggiornamenti in corso...",
    "no updates found": "nessun aggiornamento trovato",
    "NEW APP VERSION FOUND: {tag}": "NUOVA VERSIONE DISPONIBILE: {tag}",
    "ERROR: unable to check for updates: {error}":
        "ERRORE: impossibile verificare gli aggiornamenti: {error}",
    "Update available": "Aggiornamento disponibile",
    "Version {tag} is available. Open the download in your browser and close "
    "SpectrExcel? Replace the old application file with the downloaded one.":
        "La versione {tag} è disponibile. Aprire il download nel browser e "
        "chiudere SpectrExcel? Sostituisci il vecchio file dell'applicazione "
        "con quello scaricato.",
    "What's new in {tag}:": "Novità nella versione {tag}:",
    "View full changelog": "Visualizza il changelog completo",
    "Download and close": "Scarica e chiudi",
    "Not now": "Non ora",
    "finish the current operation before downloading the update":
        "termina l'operazione corrente prima di scaricare l'aggiornamento",
    "ERROR: unable to open update download: {error}":
        "ERRORE: impossibile aprire il download dell'aggiornamento: {error}",
    "ERROR: unable to open update download in the browser":
        "ERRORE: impossibile aprire il download dell'aggiornamento nel browser",
    "update opened in the browser; closing SpectrExcel...":
        "aggiornamento aperto nel browser; chiusura di SpectrExcel...",
    # shared dialogs and parsers
    "Excel file": "File Excel",
    "ERROR: unable to open the system file picker: {error}":
        "ERRORE: impossibile aprire il selettore file di sistema: {error}",
    "Replace existing file?": "Sostituire il file esistente?",
    "{name} already exists. Replace it?": "{name} esiste già. Sostituirlo?",
    "Replace": "Sostituisci",
    "Cancel": "Annulla",
    "Invalid file extension": "Estensione del file non valida",
    "Unable to read file contents: no headers found.":
        "Impossibile leggere il contenuto del file: nessuna intestazione trovata.",
    "Unable to read file contents: no spectra found.":
        "Impossibile leggere il contenuto del file: nessuno spettro trovato.",
    "Unable to read file contents: {error}":
        "Impossibile leggere il contenuto del file: {error}",
    "Unable to read file contents: invalid text table.":
        "Impossibile leggere il contenuto del file: tabella di testo non valida.",
    "Unable to read file contents: unterminated sample name.":
        "Impossibile leggere il contenuto del file: nome del campione non terminato.",
    "Unable to read file contents: truncated spectrum.":
        "Impossibile leggere il contenuto del file: spettro incompleto.",
    "Unable to read file contents: truncated acquisition time.":
        "Impossibile leggere il contenuto del file: tempo di acquisizione incompleto.",
    "Unable to read file contents: sample and spectrum counts differ.":
        "Impossibile leggere il contenuto del file: il numero di campioni e spettri non coincide.",
    "Unable to read file contents: time and spectrum counts differ.":
        "Impossibile leggere il contenuto del file: il numero di tempi e spettri non coincide.",
    "ERROR: {error}": "ERRORE: {error}",
    "Save Excel file": "Salva file Excel",
    "generating excel file...": "generazione del file excel in corso...",
    "excel file saved successfully": "file excel salvato con successo",
    "Preview chart": "Anteprima grafico",
    "Chart preview": "Anteprima grafico",
    # cinetiche
    "1. Upload KD files": "1. Carica file KD",
    "Select input files (.KD)": "Seleziona file di input (.KD)",
    "Reorder files": "Riordina file",
    "No files selected": "Nessun file selezionato",
    "2. Configure parameters": "2. Configura i parametri",
    "Reading wavelength (nm)": "Lunghezza d'onda di lettura (nm)",
    "Correction wavelength (nm)": "Lunghezza d'onda di correzione (nm)",
    "Enable wavelength correction": "Abilita la correzione alla lunghezza d'onda",
    "3. Create Excel file": "3. Crea file Excel",
    "Generate Excel": "Genera Excel",
    "Select kinetic data files": "Seleziona file di dati cinetici",
    "Kinetic data files": "File di dati cinetici",
    "selected {count} files": "selezionati {count} file",
    "Loading {count} files...": "Caricamento di {count} file...",
    "{count} files ready": "{count} file pronti",
    "failed to parse {name}": "analisi di {name} non riuscita",
    "loaded {name}": "caricato {name}",
    "Reorder kinetic files": "Riordina file cinetici",
    "Files and chart traces will use this order.":
        "I file e le tracce del grafico useranno questo ordine.",
    "Up": "Su",
    "Down": "Giù",
    "Failed to load files": "Caricamento dei file non riuscito",
    "no kinetic data loaded": "nessun dato cinetico caricato",
    "reading wavelength {wl}nm is unavailable":
        "lunghezza d'onda di lettura {wl}nm non disponibile",
    "correction wavelength {wl}nm is unavailable":
        "lunghezza d'onda di correzione {wl}nm non disponibile",
    # titolazione
    "X-axis minimum must be lower than its maximum":
        "Il minimo dell'asse X deve essere inferiore al suo massimo",
    "Y-axis minimum must be lower than its maximum":
        "Il minimo dell'asse Y deve essere inferiore al suo massimo",
    "1. Upload a TXT or SD file": "1. Carica un file TXT o SD",
    "Select input file (.txt, .SD)": "Seleziona file di input (.txt, .SD)",
    "No file selected": "Nessun file selezionato",
    "2. Configure axis ranges": "2. Configura gli intervalli degli assi",
    "X-axis minimum (nm)": "Minimo asse X (nm)",
    "X-axis maximum (nm)": "Massimo asse X (nm)",
    "Y-axis minimum (AU)": "Minimo asse Y (AU)",
    "Y-axis maximum (AU)": "Massimo asse Y (AU)",
    "Select a spectra file": "Seleziona un file di spettri",
    "Spectra files": "File di spettri",
    "selected {path}": "selezionato {path}",
    "Loading {name}...": "Caricamento di {name}...",
    "unknown input format": "formato di input sconosciuto",
    "{name} - {count} signals": "{name} - {count} segnali",
    "deleted duplicate spectra": "spettri duplicati eliminati",
    "the file contains {count} signals": "il file contiene {count} segnali",
    "Failed to load {name}": "Caricamento di {name} non riuscito",
    "ERROR: axis minimum must be lower than its maximum":
        "ERRORE: il minimo dell'asse deve essere inferiore al suo massimo",
    # famiglia di spettri
    "1. Upload a KD file": "1. Carica un file KD",
    "Select input file (.KD)": "Seleziona file di input (.KD)",
    "2. Create Excel file": "2. Crea file Excel",
    "Select a kinetic data file": "Seleziona un file di dati cinetici",
    "{name} - {count} spectra": "{name} - {count} spettri",
    "failed to parse file": "analisi del file non riuscita",
    # native dialogs
    "install Zenity or KDialog to use the system file picker":
        "installa Zenity o KDialog per usare il selettore file di sistema",
    "system file picker failed": "selettore file di sistema non riuscito",
    "Windows file picker failed with error 0x{code:04x}":
        "selettore file di Windows non riuscito con errore 0x{code:04x}",
    # updater
    "updates are not supported on {platform}":
        "gli aggiornamenti non sono supportati su {platform}",
    "invalid release version: {error}": "versione di rilascio non valida: {error}",
    "release {tag} is missing {asset}": "il rilascio {tag} non include {asset}",
}

_current = "en"


def get_language() -> str:
    return _current


def set_language(code: str) -> None:
    global _current
    _current = code if code in LANGUAGES else "en"


def _(text: str) -> str:
    if _current == "it":
        return TRANSLATIONS_IT.get(text, text)
    return text


def detect_language() -> str:
    for candidate in _locale_candidates():
        if candidate and candidate.lower().replace("-", "_").startswith("it"):
            return "it"
    return "en"


def _locale_candidates() -> list[str | None]:
    candidates: list[str | None] = []
    try:
        candidates.append(locale.getlocale()[0])
    except ValueError:
        pass
    candidates.extend(os.environ.get(name) for name in ("LANGUAGE", "LC_ALL", "LANG"))
    if sys.platform == "win32":
        candidates.append(_windows_ui_language())
    return candidates


def _windows_ui_language() -> str | None:
    try:
        import ctypes

        # LANGID primary language 0x10 is Italian.
        return "it" if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x10 else None
    except (AttributeError, OSError):
        return None
