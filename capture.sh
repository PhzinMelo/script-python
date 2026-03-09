#!/usr/bin/env bash
# capture.sh — Script Cola Linux v5.0
# Uso:
#   ./capture.sh image  <caminho_completo.png>
#   ./capture.sh ocr    <caminho_completo.png>  <base_saida_sem_extensao>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$SCRIPT_DIR/config.env"

# Carrega SCREENSHOT_DIR do config.env
SCREENSHOT_DIR_REL="screenshots"
if [[ -f "$CONFIG" ]]; then
    val=$(grep -E '^SCREENSHOT_DIR=' "$CONFIG" | tail -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
    [[ -n "$val" ]] && SCREENSHOT_DIR_REL="$val"
fi
SCREENSHOT_DIR="$SCRIPT_DIR/$SCREENSHOT_DIR_REL"
mkdir -p "$SCREENSHOT_DIR"

# Parâmetros
MODE="${1:-image}"
SCREENSHOT="${2:-$SCREENSHOT_DIR/screenshot.png}"
OCR_BASE="${3:-$SCREENSHOT_DIR/ocr_output}"

case "$MODE" in
  image|ocr) ;;
  *)
    echo "[ERRO] Modo invalido: '$MODE'. Use 'image' ou 'ocr'."
    exit 1
    ;;
esac

# Verifica ADB
if ! command -v adb &>/dev/null; then
    echo "[ERRO] adb nao encontrado. Instale: sudo apt install adb"
    exit 1
fi

# Garante diretório de destino
mkdir -p "$(dirname "$SCREENSHOT")"

# Captura via ADB
echo "[INFO] Capturando tela..."
adb exec-out screencap -p > "$SCREENSHOT"

if [[ ! -s "$SCREENSHOT" ]]; then
    echo "[ERRO] Screenshot vazio. Verifique a conexao ADB."
    rm -f "$SCREENSHOT"
    exit 1
fi
echo "[INFO] Imagem salva: $SCREENSHOT"

# Modo OCR
if [[ "$MODE" == "ocr" ]]; then
    if ! command -v tesseract &>/dev/null; then
        echo "[ERRO] Tesseract nao encontrado. Instale: sudo apt install tesseract-ocr tesseract-ocr-por"
        exit 1
    fi
    echo "[INFO] Executando OCR..."
    tesseract "$SCREENSHOT" "$OCR_BASE" -l por+eng --psm 6 --oem 1 2>/dev/null || true
    if [[ ! -s "${OCR_BASE}.txt" ]]; then
        echo "[AVISO] OCR nao encontrou texto."
    else
        CHARS=$(wc -c < "${OCR_BASE}.txt")
        echo "[INFO] OCR concluido: ${OCR_BASE}.txt ($CHARS bytes)"
    fi
fi