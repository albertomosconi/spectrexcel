"""Minimal dict-based translation layer.

English is the source language: wrap user-facing strings with _() at the point
of use and add the Italian translation to TRANSLATIONS_IT. Use
_("... {value} ...").format(value=...) for interpolation; never wrap f-strings,
as runtime values would end up in the lookup key. Strings written into the
generated Excel files are intentionally not translated.

The language is selected once at startup (Settings > main/language, falling
back to the OS locale) and applies to the whole UI on the next launch.
"""

import locale
import os
import sys

LANGUAGES = {"en": "English", "it": "Italiano"}

TRANSLATIONS_IT: dict[str, str] = {
    # main window
    "Check updates": "Verifica aggiornamenti",
    "Checking...": "Verifica in corso...",
    "Update {tag}": "Aggiorna a {tag}",
    "App settings": "Impostazioni",
    "ACTIVITY": "ATTIVITÀ",
    "Developed by Alberto Mosconi": "Sviluppato da Alberto Mosconi",
    "Source code": "Codice sorgente",
    "LOADED ASSAY: {name}": "ASSAY CARICATO: {name}",
    # assay names
    "binding / titration": "binding / titolazione",
    "kinetics": "cinetiche",
    "spectrum family": "famiglia di spettri",
    "About assay": "Informazioni sull'assay",
    "Use this assay to compare a series of absorbance spectra collected "
    "during a binding or titration experiment. Select a TXT or SD file, "
    "then choose wavelength and absorbance ranges for the chart axes. "
    "SpectrExcel removes standard-deviation values and, when the input "
    "contains an identical repeated set of spectra, keeps only one copy. "
    "The generated Excel workbook contains wavelength and absorbance data "
    "for each signal, together with an overlaid spectrum chart using the "
    "selected axis ranges.":
        "Usa questo assay per confrontare una serie di spettri di assorbanza "
        "raccolti durante un esperimento di binding o titolazione. Seleziona "
        "un file TXT o SD, quindi scegli gli intervalli di lunghezza d'onda e "
        "assorbanza per gli assi del grafico. SpectrExcel rimuove i valori di "
        "deviazione standard e, quando l'input contiene una serie identica e "
        "ripetuta di spettri, ne conserva una sola copia. La cartella di lavoro "
        "Excel generata contiene i dati di lunghezza d'onda e assorbanza per "
        "ciascun segnale, insieme a un grafico sovrapposto degli spettri che "
        "usa gli intervalli selezionati per gli assi.",
    "Use this assay to follow absorbance changes over time across one or "
    "more kinetic measurements. Select KD files, arrange them in the "
    "desired order, then specify a reading wavelength and a correction "
    "wavelength. For every file and time point, SpectrExcel subtracts the "
    "absorbance at the correction wavelength from the absorbance at the "
    "reading wavelength and shifts the time axis so the first measurement "
    "starts at zero seconds. The generated Excel workbook contains the "
    "corrected traces and a comparison chart in the chosen file order.":
        "Usa questo assay per seguire le variazioni di assorbanza nel tempo in "
        "una o più misure cinetiche. Seleziona i file KD, disponili nell'ordine "
        "desiderato, quindi specifica una lunghezza d'onda di lettura e una di "
        "correzione. Per ogni file e istante, SpectrExcel sottrae l'assorbanza "
        "alla lunghezza d'onda di correzione da quella alla lunghezza d'onda di "
        "lettura e trasla l'asse temporale in modo che la prima misura inizi a "
        "zero secondi. La cartella di lavoro Excel generata contiene le tracce "
        "corrette e un grafico di confronto nell'ordine scelto per i file.",
    "Use this assay to inspect how a complete absorbance spectrum changes "
    "during one kinetic measurement. Select a KD file containing spectra "
    "recorded at successive acquisition times. SpectrExcel exports the "
    "acquisition times, wavelengths, and absorbance values for every "
    "recorded spectrum. The generated Excel workbook also includes an "
    "overlaid wavelength-versus-absorbance chart showing one spectrum out "
    "of every two, making the progression easier to inspect.":
        "Usa questo assay per osservare come cambia uno spettro completo di "
        "assorbanza durante una misura cinetica. Seleziona un file KD contenente "
        "spettri registrati a tempi di acquisizione successivi. SpectrExcel "
        "esporta i tempi di acquisizione, le lunghezze d'onda e i valori di "
        "assorbanza per ogni spettro registrato. La cartella di lavoro Excel "
        "generata include anche un grafico sovrapposto lunghezza d'onda-"
        "assorbanza che mostra uno spettro ogni due, rendendo più facile "
        "osservare l'andamento.",
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
    "Excel workbook": "Cartella di lavoro Excel",
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
