#!/usr/bin/env bash
# capture.sh — Script Cola | Captura tela do Android e processa
#
# Uso:
#   ./capture.sh image [arquivo.png]       # captura imagem
#   ./capture.sh ocr   [arquivo.png] [saida_sem_extensao]  # captura + OCR
#
# Exemplos:
#   ./capture.sh image screenshot1.png
#   ./capture.sh ocr   screenshot2.png ocr2

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$SCRIPT_DIR/config.env"

# ── Carrega configurações ─────────────────────────────────────────────────────
if [[ ! -f "$CONFIG" ]]; then
  echo "[ERRO] config.env não encontrado em $SCRIPT_DIR"
  exit 1
fi
source "$CONFIG"
PROVIDER="${PROVIDER:-gemini}"

# ── Verifica dependências ─────────────────────────────────────────────────────
for cmd in adb python3; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "[ERRO] Dependência ausente: $cmd"
    exit 1
  fi
done

# ── Parâmetros ────────────────────────────────────────────────────────────────
MODE="${1:-image}"
SCREENSHOT_NAME="${2:-screenshot.png}"
OCR_BASE="${3:-ocr_output}"

SCREENSHOT="$SCRIPT_DIR/$SCREENSHOT_NAME"
OCR_OUTPUT="$SCRIPT_DIR/$OCR_BASE"

# ── Valida modo ───────────────────────────────────────────────────────────────
case "$MODE" in
  image|ocr) ;;
  *)
    echo "[ERRO] Modo inválido: '$MODE'. Use 'image' ou 'ocr'."
    exit 1
    ;;
esac

# ── Captura a tela via ADB ────────────────────────────────────────────────────
echo "[INFO] Capturando tela → $SCREENSHOT_NAME"
adb exec-out screencap -p > "$SCREENSHOT"

if [[ ! -s "$SCREENSHOT" ]]; then
  echo "[ERRO] Screenshot vazio — verifique a conexão ADB."
  exit 1
fi

# ── Processa conforme o modo ──────────────────────────────────────────────────
if [[ "$MODE" == "image" ]]; then
  echo "[INFO] Imagem salva: $SCREENSHOT"

elif [[ "$MODE" == "ocr" ]]; then
  if ! command -v tesseract &>/dev/null; then
    echo "[ERRO] tesseract não instalado."
    echo "       Execute: sudo apt install tesseract-ocr tesseract-ocr-por"
    exit 1
  fi

  echo "[INFO] Executando OCR (por+eng)…"
  tesseract "$SCREENSHOT" "$OCR_OUTPUT" -l por+eng 2>/dev/null || true

  if [[ ! -s "${OCR_OUTPUT}.txt" ]]; then
    echo "[AVISO] OCR não encontrou texto na imagem."
  else
    CHARS=$(wc -c < "${OCR_OUTPUT}.txt")
    echo "[INFO] OCR concluído: ${OCR_OUTPUT}.txt ($CHARS bytes)"
  fi
fi