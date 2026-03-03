#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daemon.py — Script Cola v3.0 | Listener de atalhos globais

  Shift+Z  →  Nova sessão: limpa capturas acumuladas
  Shift+X  →  Capturar como IMAGEM (screenshot numerado)
  Shift+C  →  Capturar como OCR  (extrai texto da tela)
  Shift+V  →  Enviar tudo acumulado para a IA
  Shift+A  →  Alternar provedor ativo (Gemini → Copilot → OpenRouter → …)
  Shift+M  →  Alternar modelo do provedor ativo
  Esc      →  Encerrar daemon

Dependência:
  pip install pynput
"""

import subprocess
import sys
import time
from pathlib import Path
from pynput import keyboard

# ── Caminhos ──────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent
CAPTURE_SH  = SCRIPT_DIR / "capture.sh"
SEND_SCRIPT = SCRIPT_DIR / "send_to_ai.py"

for f in (CAPTURE_SH, SEND_SCRIPT):
    if not f.exists():
        print(f"[ERRO] Arquivo não encontrado: {f}", file=sys.stderr)
        sys.exit(1)

# ── Modelos disponíveis por provedor ─────────────────────────────────────────
PROVIDER_MODELS: dict[str, list[str]] = {
    "gemini":     ["gemini-flash-latest", "gemini-1.5-pro", "gemini-pro"],
    "copilot":    ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
    "openrouter": ["mistralai/mistral-7b-instruct", "openai/gpt-4o-mini",
                   "google/gemini-flash-1.5"],
}
PROVIDERS = list(PROVIDER_MODELS.keys())

# ── Estado ativo ──────────────────────────────────────────────────────────────
active_provider_idx: int = 0
active_model_idx:    int = 0

def active_provider() -> str:
    return PROVIDERS[active_provider_idx]

def active_model() -> str:
    return PROVIDER_MODELS[active_provider()][active_model_idx]

def status_line() -> str:
    return f"  Provedor: {active_provider().upper():<12} Modelo: {active_model()}"

# ── Listas da sessão ──────────────────────────────────────────────────────────
session_images: list[Path] = []
session_texts:  list[str]  = []
capture_index:  int        = 0

# ── Debounce ──────────────────────────────────────────────────────────────────
_last_action: float = 0.0
DEBOUNCE_SEC: float = 0.4

def debounce() -> bool:
    global _last_action
    now = time.time()
    if now - _last_action < DEBOUNCE_SEC:
        return False
    _last_action = now
    return True

# ── Helpers ───────────────────────────────────────────────────────────────────
def _run_capture(mode: str, *extra_args: str):
    """Roda capture.sh e devolve stdout+stderr."""
    result = subprocess.run(
        ["bash", str(CAPTURE_SH), mode, *extra_args],
        cwd=str(SCRIPT_DIR), capture_output=True, text=True
    )
    if result.stdout.strip():
        print(result.stdout.strip(), flush=True)
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return result

def _sep(char="─", n=52):
    print(char * n, flush=True)

# ── Ações ─────────────────────────────────────────────────────────────────────
def action_new_session():
    global session_images, session_texts, capture_index
    session_images, session_texts, capture_index = [], [], 0
    _sep("═")
    print("  [Shift+Z] Nova sessão — listas limpas.", flush=True)
    print(status_line(), flush=True)
    _sep("═")

def action_add_image():
    global capture_index
    if not debounce():
        return
    capture_index += 1
    fname = f"screenshot{capture_index}.png"
    dest  = SCRIPT_DIR / fname
    _sep()
    print(f"[Shift+X] Capturando imagem → {fname}", flush=True)
    _run_capture("image", fname)
    if dest.exists() and dest.stat().st_size > 0:
        session_images.append(dest)
        print(f"  ✔ {fname} adicionado  "
              f"({len(session_images)} img | {len(session_texts)} txt)", flush=True)
    else:
        print("  ✘ Falha ao capturar imagem.", file=sys.stderr)

def action_add_ocr():
    global capture_index
    if not debounce():
        return
    capture_index += 1
    fname    = f"screenshot{capture_index}.png"
    ocr_base = f"ocr{capture_index}"
    _sep()
    print(f"[Shift+C] Capturando OCR → {fname}", flush=True)
    _run_capture("ocr", fname, ocr_base)
    ocr_file = SCRIPT_DIR / f"{ocr_base}.txt"
    if ocr_file.exists():
        text = ocr_file.read_text(encoding="utf-8").strip()
        if text:
            session_texts.append(text)
            preview = text[:72].replace("\n", " ")
            print(f"  ✔ OCR adicionado  "
                  f"({len(session_images)} img | {len(session_texts)} txt): {preview}…",
                  flush=True)
        else:
            print("  ⚠ OCR não encontrou texto nesta captura.", flush=True)
    else:
        print("  ✘ Arquivo OCR não gerado.", file=sys.stderr)

def action_send():
    if not debounce():
        return
    if not session_images and not session_texts:
        print("\n[Shift+V] Sessão vazia. Use Shift+X ou Shift+C primeiro.\n", flush=True)
        return
    _sep("═")
    print(f"[Shift+V] Enviando para IA…", flush=True)
    print(f"  Imagens : {len(session_images)}", flush=True)
    print(f"  Textos  : {len(session_texts)}", flush=True)
    print(status_line(), flush=True)
    _sep("─")

    cmd = [
        "python3", str(SEND_SCRIPT),
        "--provider", active_provider(),
        "--model",    active_model(),
    ]
    for img in session_images:
        cmd += ["--image", str(img)]
    if session_texts:
        cmd += ["--text", "\n\n---\n\n".join(session_texts)]

    try:
        subprocess.run(cmd, cwd=str(SCRIPT_DIR))
    except Exception as e:
        print(f"[ERRO] {e}", file=sys.stderr)
    _sep("═")

def action_toggle_provider():
    global active_provider_idx, active_model_idx
    active_provider_idx = (active_provider_idx + 1) % len(PROVIDERS)
    active_model_idx    = 0                          # reseta modelo ao trocar provedor
    _sep()
    print(f"[Shift+A] Provedor alterado!", flush=True)
    print(status_line(), flush=True)
    _sep()

def action_toggle_model():
    global active_model_idx
    models = PROVIDER_MODELS[active_provider()]
    active_model_idx = (active_model_idx + 1) % len(models)
    _sep()
    print(f"[Shift+M] Modelo alterado!", flush=True)
    print(status_line(), flush=True)
    _sep()

# ── Listener ──────────────────────────────────────────────────────────────────
current_keys: set = set()

def normalize(key):
    try:
        return key.char
    except AttributeError:
        return key

def on_press(key):
    current_keys.add(normalize(key))
    shift = any(k in current_keys for k in (
        keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r))
    char = normalize(key)

    if not shift:
        return

    dispatch = {
        ('z', 'Z'): action_new_session,
        ('x', 'X'): action_add_image,
        ('c', 'C'): action_add_ocr,
        ('v', 'V'): action_send,
        ('a', 'A'): action_toggle_provider,
        ('m', 'M'): action_toggle_model,
    }
    for chars, fn in dispatch.items():
        if char in chars:
            fn()
            break

def on_release(key):
    current_keys.discard(normalize(key))
    if key == keyboard.Key.esc:
        print("\n[DAEMON] Encerrando…", flush=True)
        return False

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("╔══════════════════════════════════════════════╗")
    print("║       Script Cola  —  daemon  v3.0           ║")
    print("╠══════════════════════════════════════════════╣")
    print("║  Shift+Z  →  nova sessão (limpar tudo)       ║")
    print("║  Shift+X  →  capturar como IMAGEM            ║")
    print("║  Shift+C  →  capturar como OCR               ║")
    print("║  Shift+V  →  enviar tudo para a IA           ║")
    print("║  Shift+A  →  alternar PROVEDOR               ║")
    print("║  Shift+M  →  alternar MODELO                 ║")
    print("║  Esc      →  encerrar daemon                 ║")
    print("╚══════════════════════════════════════════════╝")
    print(f"\n{status_line()}")
    print("[DAEMON] Aguardando atalhos…\n", flush=True)

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        try:
            listener.join()
        except KeyboardInterrupt:
            print("\n[DAEMON] Interrompido via Ctrl+C.", flush=True)

if __name__ == "__main__":
    main()