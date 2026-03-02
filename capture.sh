#!/usr/bin/env bash
# capture.sh — Captura tela do Android e envia para IA (Gemini ou Copilot)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCREENSHOT="$SCRIPT_DIR/screenshot.png"
OCR_OUTPUT="$SCRIPT_DIR/ocr_output"
SEND_SCRIPT="$SCRIPT_DIR/send_to_ai.py"
CONFIG="$SCRIPT_DIR/config.env"

# ── Carrega configurações ────────────────────────────────────────────────────
if [[ ! -f "$CONFIG" ]]; then
  echo "[ERRO] Arquivo config.env não encontrado em $SCRIPT_DIR"
  exit 1
fi
source "$CONFIG"

PROVIDER="${PROVIDER:-gemini}"

# ── Verifica dependências básicas ────────────────────────────────────────────
for cmd in adb python3; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "[ERRO] Dependência ausente: $cmd"
    exit 1
  fi
done

# ── Captura a tela via ADB ───────────────────────────────────────────────────
echo "[INFO] Capturando tela do dispositivo..."
adb exec-out screencap -p > "$SCREENSHOT"

if [[ ! -s "$SCREENSHOT" ]]; then
  echo "[ERRO] Screenshot vazio — verifique a conexão ADB."
  exit 1
fi
echo "[INFO] Screenshot salvo em $SCREENSHOT"

# ── Processa modo ────────────────────────────────────────────────────────────
MODE="${1:-image}"

case "$MODE" in
  image|text) ;;
  *)
    echo "[ERRO] Modo inválido: '$MODE'. Use 'image' ou 'text'."
    exit 1
    ;;
esac

# Copilot não aceita imagens — força OCR automaticamente
if [[ "$MODE" == "image" && "${PROVIDER,,}" == "copilot" ]]; then
  echo "[INFO] Copilot não suporta imagens — convertendo para OCR automaticamente..."
  MODE="text"
fi

# ── Envia para a IA ──────────────────────────────────────────────────────────
if [[ "$MODE" == "image" ]]; then
  echo "[INFO] Enviando imagem para a IA ($PROVIDER)..."
  python3 "$SEND_SCRIPT" --image "$SCREENSHOT"
else
  # ── OCR ──────────────────────────────────────────────────────────────────
  if ! command -v tesseract &>/dev/null; then
    echo "[ERRO] tesseract não instalado."
    echo "       Execute: sudo apt install tesseract-ocr tesseract-ocr-por"
    exit 1
  fi

  echo "[INFO] Executando OCR (pt+en)..."
  tesseract "$SCREENSHOT" "$OCR_OUTPUT" -l por+eng 2>/dev/null || true
  OCR_TEXT_FILE="${OCR_OUTPUT}.txt"

  if [[ ! -s "$OCR_TEXT_FILE" ]]; then
    echo "[AVISO] OCR retornou vazio."
    if [[ "${PROVIDER,,}" == "gemini" ]]; then
      echo "[INFO] Fallback: enviando imagem diretamente para o Gemini..."
      python3 "$SEND_SCRIPT" --image "$SCREENSHOT"
    else
      echo "[ERRO] OCR vazio e Copilot não aceita imagem. Abortando."
      exit 1
    fi
  else
    OCR_TEXT="$(cat "$OCR_TEXT_FILE")"
    echo "[INFO] Enviando texto OCR para a IA ($PROVIDER)..."
    python3 "$SEND_SCRIPT" --text "$OCR_TEXT"
  fi
fi

# fim do script