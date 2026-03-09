@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

:: capture.bat — Script Cola Windows v5.1
:: Uso:
::   capture.bat image  <caminho_completo.png>
::   capture.bat ocr    <caminho_completo.png>  <base_saida_sem_extensao>
::
:: O argumento 2 pode ser:
::   - caminho absoluto  : C:\Users\...\screenshots\screenshot1.png  (daemon.py)
::   - caminho relativo  : screenshots\screenshot1.png
::   - omitido           : usa o padrao screenshots\screenshot.png

set "MODE=%~1"
set "SCREENSHOT_ARG=%~2"
set "OCR_ARG=%~3"

:: ── Modo padrao ───────────────────────────────────────────────────────────────
if "%MODE%"=="" set "MODE=image"

:: ── Valida modo ───────────────────────────────────────────────────────────────
if /i not "%MODE%"=="image" if /i not "%MODE%"=="ocr" (
    echo [ERRO] Modo invalido: "%MODE%". Use "image" ou "ocr".
    exit /b 1
)

:: ── Verifica ADB e Python ─────────────────────────────────────────────────────
where adb    >nul 2>&1 || (echo [ERRO] adb nao encontrado. Adicione ao PATH. & exit /b 1)
where python >nul 2>&1 || (echo [ERRO] python nao encontrado. Adicione ao PATH. & exit /b 1)

:: ── Resolve caminho do screenshot via Python ──────────────────────────────────
::
::  PROBLEMA CORRIGIDO:
::  Versoes anteriores faziam:
::      set "SCREENSHOT=%SCRIPT_DIR%%SCREENSHOT_NAME%"
::  Se SCREENSHOT_NAME ja era absoluto (ex: C:\...\screenshot1.png), o resultado
::  era um caminho invalido duplicado:
::      C:\projeto\C:\...\screenshot1.png
::
::  SOLUCAO:
::  Delegamos a normalizacao ao Python.
::  pathlib.Path(arg).resolve() faz exatamente o que o capture.sh faz com "${2:-default}":
::    - Se o argumento for absoluto  -> usa ele diretamente (sem concatenar nada)
::    - Se for relativo              -> resolve a partir do CWD
::    - Se estiver vazio             -> usa o padrao dentro de screenshots/
::
::  O caminho normalizado e retornado via stdout e capturado na variavel SCREENSHOT.
::  Isso tambem evita o problema de caminhos com espacos dentro de "python -c",
::  pois o caminho nao e mais interpolado como string literal no codigo Python.
::
set "SCREENSHOTS_DEFAULT=%~dp0screenshots\screenshot.png"
set "OCR_DEFAULT=%~dp0screenshots\ocr_output"

for /f "usebackq delims=" %%P in (
    `python -c "import pathlib,sys; a=sys.argv[1]; p=pathlib.Path(a).resolve() if a else pathlib.Path(sys.argv[2]).resolve(); print(p)" "%SCREENSHOT_ARG%" "%SCREENSHOTS_DEFAULT%"`
) do set "SCREENSHOT=%%P"

if "%SCREENSHOT%"=="" (
    echo [ERRO] Nao foi possivel resolver o caminho do screenshot.
    exit /b 1
)

:: Resolve OCR_BASE da mesma forma
for /f "usebackq delims=" %%P in (
    `python -c "import pathlib,sys; a=sys.argv[1]; p=pathlib.Path(a).resolve() if a else pathlib.Path(sys.argv[2]).resolve(); print(p)" "%OCR_ARG%" "%OCR_DEFAULT%"`
) do set "OCR_BASE=%%P"

:: ── Garante que o diretorio de destino existe ─────────────────────────────────
for %%F in ("%SCREENSHOT%") do set "DEST_DIR=%%~dpF"
if not exist "%DEST_DIR%" mkdir "%DEST_DIR%"

:: ── Captura via Python (bytes puros — sem corrupcao do CMD ou PowerShell) ─────
::
::  O caminho e passado via variavel de ambiente SC_DEST, nao por interpolacao
::  de string no codigo Python. Isso garante compatibilidade com espacos,
::  acentos e caracteres especiais no caminho.
::
echo [INFO] Capturando tela...
set "SC_DEST=%SCREENSHOT%"
python -c "import subprocess,pathlib,os; pathlib.Path(os.environ['SC_DEST']).write_bytes(subprocess.check_output(['adb','exec-out','screencap','-p']))"
if errorlevel 1 (
    echo [ERRO] Falha ao executar adb. Verifique a conexao ADB.
    exit /b 1
)

:: ── Valida arquivo gerado ─────────────────────────────────────────────────────
if not exist "%SCREENSHOT%" (
    echo [ERRO] Screenshot nao gerado.
    exit /b 1
)
for %%F in ("%SCREENSHOT%") do set "FSIZE=%%~zF"
if "%FSIZE%"=="0" (
    echo [ERRO] Screenshot vazio.
    del "%SCREENSHOT%" 2>nul
    exit /b 1
)

:: ── Modo IMAGE: apenas salva ──────────────────────────────────────────────────
if /i "%MODE%"=="image" (
    echo [INFO] Imagem salva: %SCREENSHOT%
    exit /b 0
)

:: ── Modo OCR: Tesseract ───────────────────────────────────────────────────────
where tesseract >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Tesseract nao encontrado.
    echo        Instale em: https://github.com/UB-Mannheim/tesseract/wiki
    exit /b 1
)
echo [INFO] Executando OCR...
set "SC_OCR=%OCR_BASE%"
tesseract "%SCREENSHOT%" "%OCR_BASE%" -l por+eng --psm 6 --oem 1 2>nul
if not exist "%OCR_BASE%.txt" (
    echo [AVISO] OCR nao encontrou texto.
) else (
    for %%F in ("%OCR_BASE%.txt") do echo [INFO] OCR concluido: %%~nxF ^(%%~zF bytes^)
)