@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM Local Pseudonymization Tool — Preparazione Pacchetto Offline (Windows)
REM
REM UTILIZZO:
REM   Eseguire questo script su una macchina CON accesso internet.
REM   Verrà creata la cartella "wheelhouse\" con tutti i wheel precompilati.
REM   Copiare l'intera cartella del tool (incluso wheelhouse\) sulla macchina
REM   target senza internet e avviare start.bat normalmente.
REM
REM   start.bat rileva automaticamente la presenza di wheelhouse\ e usa
REM   l'installazione offline senza richiedere connessione internet.
REM ─────────────────────────────────────────────────────────────────────────────
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "BACKEND_DIR=%SCRIPT_DIR%backend"
set "WHEELHOUSE_DIR=%SCRIPT_DIR%wheelhouse"

echo.
echo   +------------------------------------------------------+
echo   ^|  Preparazione Pacchetto Offline                     ^|
echo   ^|  Local Pseudonymization Tool -- MVP v1.0.0          ^|
echo   +------------------------------------------------------+
echo.

REM Verifica Python
set "PYTHON_CMD="
for %%P in (py python python3) do (
    if not defined PYTHON_CMD (
        where %%P >nul 2>&1
        if !ERRORLEVEL! == 0 (
            %%P -c "import sys; v=sys.version_info; exit(0 if (3,10)<=v<(3,13) else 1)" >nul 2>&1
            if !ERRORLEVEL! == 0 (
                set "PYTHON_CMD=%%P"
            )
        )
    )
)

if not defined PYTHON_CMD (
    echo [ERR]  Python 3.10/3.11/3.12 non trovato.
    pause
    exit /b 1
)

for /f "tokens=* usebackq" %%V in (`!PYTHON_CMD! -c "import sys; print(str(sys.version_info.major)+'.'+str(sys.version_info.minor)+'.'+str(sys.version_info.micro))"`) do set "PY_VER=%%V"
echo [INFO] Python !PY_VER! trovato.
echo [INFO] Download wheel in: %WHEELHOUSE_DIR%
echo [INFO] Connessione internet richiesta...
echo.

REM Crea la cartella wheelhouse
if not exist "%WHEELHOUSE_DIR%" mkdir "%WHEELHOUSE_DIR%"

REM Scarica tutti i wheel (incluse dipendenze transitive)
!PYTHON_CMD! -m pip download ^
    --dest "%WHEELHOUSE_DIR%" ^
    --python-version 3.11 ^
    --platform win_amd64 ^
    --only-binary :all: ^
    -r "%BACKEND_DIR%\requirements.txt"

if !ERRORLEVEL! NEQ 0 (
    echo.
    echo [WARN] Download con --only-binary fallito per alcuni pacchetti.
    echo [INFO] Ritento senza restrizioni di piattaforma...
    !PYTHON_CMD! -m pip download ^
        --dest "%WHEELHOUSE_DIR%" ^
        -r "%BACKEND_DIR%\requirements.txt"
    if !ERRORLEVEL! NEQ 0 (
        echo [ERR]  Download fallito. Verificare la connessione internet.
        pause
        exit /b 1
    )
)

echo.
echo [OK]   Wheel scaricati in: %WHEELHOUSE_DIR%
echo.
echo        Contenuto:
dir /b "%WHEELHOUSE_DIR%"
echo.
echo   +------------------------------------------------------+
echo   ^|  PROSSIMI PASSI:                                    ^|
echo   ^|  1. Copiare l'intera cartella del tool sulla        ^|
echo   ^|     macchina target (incluso wheelhouse\)           ^|
echo   ^|  2. Sulla macchina target: eseguire start.bat       ^|
echo   ^|     (rileva automaticamente wheelhouse\)            ^|
echo   +------------------------------------------------------+
echo.
pause
endlocal
