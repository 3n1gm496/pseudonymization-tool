@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM Local Pseudonymization Tool — Script di Avvio (Windows)
REM Versione: 1.0.3
REM Target Python: 3.11 (testato e supportato)
REM ─────────────────────────────────────────────────────────────────────────────
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
set "BACKEND_DIR=%REPO_ROOT%\backend"
set "VENV_DIR=%REPO_ROOT%\.venv"
set "LOG_FILE=%SCRIPT_DIR%install.log"
set "HOST=127.0.0.1"
set "PORT=8000"

echo.
echo   +------------------------------------------------------+
echo   ^|      Local Pseudonymization Tool -- MVP v1.0.0      ^|
echo   ^|  Solo uso locale -- Nessun dato inviato all'esterno  ^|
echo   +------------------------------------------------------+
echo.

REM ─── Verifica Python ─────────────────────────────────────────────────────────
echo [INFO] Verifica Python...

REM Cerca Python 3.11 specificamente (versione testata e supportata).
REM Accetta anche versioni 3.10 e 3.12 come fallback.
REM Rifiuta Python 3.13+ (non ancora testato con questo tool).
set "PYTHON_CMD="

for %%P in (py python python3) do (
    if not defined PYTHON_CMD (
        where %%P >nul 2>&1
        if !ERRORLEVEL! == 0 (
            REM Accetta 3.10, 3.11, 3.12 — rifiuta < 3.10 e >= 3.13
            %%P -c "import sys; v=sys.version_info; exit(0 if (3,10)<=v<(3,13) else 1)" >nul 2>&1
            if !ERRORLEVEL! == 0 (
                set "PYTHON_CMD=%%P"
            )
        )
    )
)

if not defined PYTHON_CMD (
    echo [ERR]  Python 3.10, 3.11 o 3.12 non trovato.
    echo.
    echo        Questo tool e' testato con Python 3.11 (raccomandato).
    echo        Python 3.13+ non e' ancora supportato.
    echo.
    echo        Scaricare Python 3.11 da:
    echo        https://www.python.org/downloads/release/python-3119/
    echo        Durante l'installazione: selezionare "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

REM Ottieni la versione per il messaggio informativo
for /f "tokens=* usebackq" %%V in (`!PYTHON_CMD! -c "import sys; print(str(sys.version_info.major)+'.'+str(sys.version_info.minor)+'.'+str(sys.version_info.micro))"`) do set "PY_VER=%%V"
echo [OK]   Python !PY_VER! trovato (comando: !PYTHON_CMD!).

REM Avvisa se non è 3.11
!PYTHON_CMD! -c "import sys; exit(0 if sys.version_info[:2]==(3,11) else 1)" >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [WARN] Versione consigliata: Python 3.11. La versione !PY_VER! potrebbe funzionare ma non e' stata testata.
)

REM ─── Verifica Tesseract OCR ───────────────────────────────────────────────────
echo [INFO] Verifica Tesseract OCR...
where tesseract >nul 2>&1
if !ERRORLEVEL! == 0 (
    echo [OK]   Tesseract trovato.
) else (
    echo [WARN] Tesseract OCR non trovato. L'OCR su immagini non sara' disponibile.
    echo [WARN] Scaricarlo da: https://github.com/UB-Mannheim/tesseract/wiki
)

REM ─── Ambiente Virtuale ────────────────────────────────────────────────────────
echo [INFO] Configurazione ambiente virtuale...

if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [INFO] Creazione ambiente virtuale in %VENV_DIR% ...
    !PYTHON_CMD! -m venv "%VENV_DIR%"
    if !ERRORLEVEL! NEQ 0 (
        echo [ERR]  Impossibile creare l'ambiente virtuale.
        pause
        exit /b 1
    )
    echo [OK]   Ambiente virtuale creato.
) else (
    echo [OK]   Ambiente virtuale esistente trovato.
)

call "%VENV_DIR%\Scripts\activate.bat"
if !ERRORLEVEL! NEQ 0 (
    echo [ERR]  Impossibile attivare l'ambiente virtuale.
    pause
    exit /b 1
)

REM ─── Installazione Dipendenze ─────────────────────────────────────────────────
echo [INFO] Verifica dipendenze Python...

if not exist "%VENV_DIR%\.deps_installed" (
    echo [INFO] Prima esecuzione: installazione dipendenze...
    echo [INFO] Connessione internet richiesta solo per questo passaggio.
    echo [INFO] Il log completo viene salvato in: %LOG_FILE%
    echo [INFO] Attendere prego...

    REM Inizializza il log
    echo [%DATE% %TIME%] Avvio installazione dipendenze > "%LOG_FILE%" 2>&1
    echo Python: !PY_VER! >> "%LOG_FILE%" 2>&1
    echo Requirements: %BACKEND_DIR%\requirements.txt >> "%LOG_FILE%" 2>&1
    echo. >> "%LOG_FILE%" 2>&1

    REM Step 1: aggiorna pip, setuptools e wheel (riduce fallimenti di build)
    echo [INFO] Aggiornamento pip, setuptools, wheel...
    python -m pip install --upgrade pip setuptools wheel >> "%LOG_FILE%" 2>&1
    if !ERRORLEVEL! NEQ 0 (
        echo [WARN] Aggiornamento pip/setuptools/wheel fallito (non critico, continuo).
    )

    REM Step 2: installa le dipendenze applicative
    REM IMPORTANTE: tutto l'output di pip viene rediretto su file (stdout+stderr)
    REM per evitare che i caratteri ">", "->", ">=" nell'output di pip vengano
    REM interpretati come operatori di redirezione dal parser del batch script.
    echo [INFO] Installazione dipendenze applicative...
    if exist "%SCRIPT_DIR%wheelhouse\" (
        echo [INFO] Modalita' OFFLINE: uso wheelhouse\ locale. >> "%LOG_FILE%" 2>&1
        echo [INFO] Modalita' OFFLINE rilevata: uso wheelhouse\ locale.
        python -m pip install --no-index --find-links "%SCRIPT_DIR%wheelhouse" -r "%BACKEND_DIR%\requirements.txt" >> "%LOG_FILE%" 2>&1
    ) else (
        echo [INFO] Modalita' ONLINE: download da PyPI. >> "%LOG_FILE%" 2>&1
        python -m pip install -r "%BACKEND_DIR%\requirements.txt" >> "%LOG_FILE%" 2>&1
    )
    set "PIP_EXIT=!ERRORLEVEL!"

    echo. >> "%LOG_FILE%" 2>&1
    echo [%DATE% %TIME%] Fine installazione. Exit code: !PIP_EXIT! >> "%LOG_FILE%" 2>&1

    if !PIP_EXIT! NEQ 0 (
        echo.
        echo [ERR]  Installazione dipendenze fallita (exit code: !PIP_EXIT!).
        echo        Log completo: %LOG_FILE%
        echo.
        echo        Ultime righe del log:
        echo        ─────────────────────────────────────────────────────
        REM Stampa le ultime ~60 righe del log
        python -c "
import sys
try:
    with open(r'%LOG_FILE%', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    for line in lines[-60:]:
        print('  ' + line.rstrip())
except Exception as e:
    print('  (impossibile leggere il log: ' + str(e) + ')')
" 2>nul
        echo        ─────────────────────────────────────────────────────
        echo.
        echo        Soluzioni comuni:
        echo        1. Verificare la connessione internet
        echo        2. Per proxy aziendale: set HTTPS_PROXY=http://proxy:porta
        echo        3. Eliminare la cartella .venv e riprovare
        echo        4. Usare la modalita' offline (vedi README.md sezione Offline)
        echo.
        pause
        exit /b 1
    )

    echo. > "%VENV_DIR%\.deps_installed"
    echo [OK]   Dipendenze installate. Log: %LOG_FILE%
) else (
    echo [OK]   Dipendenze gia' installate.
)

REM ─── Avvio Server ─────────────────────────────────────────────────────────────
echo.
echo   +------------------------------------------------------+
echo   ^|  Apri il browser su: http://localhost:%PORT%           ^|
echo   ^|  Premi Ctrl+C per fermare il server                  ^|
echo   +------------------------------------------------------+
echo.

REM Apri il browser automaticamente dopo 2 secondi
start "" /B cmd /C "timeout /T 2 /NOBREAK >nul && start http://localhost:%PORT%"

REM Avvia uvicorn tramite python -m (piu' robusto di chiamare uvicorn.exe direttamente)
cd /d "%BACKEND_DIR%"
python -m uvicorn app.main:app --host %HOST% --port %PORT% --log-level info --no-access-log

if !ERRORLEVEL! NEQ 0 (
    echo.
    echo [ERR]  Il server si e' fermato con un errore (codice: !ERRORLEVEL!).
    echo.
    echo        Cause comuni:
    echo        - Porta %PORT% gia' in uso: chiudere altre istanze del tool
    echo        - Eliminare la cartella .venv e riavviare lo script
    echo.
    pause
)
endlocal
