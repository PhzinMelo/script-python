#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daemon.py — Script Cola v5.0 | Listener de atalhos globais
Compatível com Windows e Linux.

  Shift+Z  ->  Nova sessão (limpa capturas e screenshots antigos)
  Shift+X  ->  Capturar como IMAGEM
  Shift+C  ->  Capturar como OCR (extrai texto)
  Shift+V  ->  Enviar tudo para a IA
  Shift+A  ->  Alternar provedor (Gemini / OpenRouter)
  Shift+M  ->  Alternar modelo do provedor ativo
  Esc      ->  Encerrar daemon

Dependências:
  pip install pynput requests pillow
"""

import subprocess
import sys
import time
import platform
import shutil
from pathlib import Path

try:
    from pynput import keyboard
except ImportError:
    print("[ERRO] Modulo 'pynput' nao encontrado.")
    print("       Execute:  pip install pynput")
    sys.exit(1)

# ── Detecta sistema operacional ───────────────────────────────────────────────
IS_WINDOWS = platform.system() == "Windows"
OS_NAME    = "Windows" if IS_WINDOWS else "Linux"

# ── Caminhos ──────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent
SEND_SCRIPT = SCRIPT_DIR / "send_to_ai.py"

if IS_WINDOWS:
    CAPTURE_SCRIPT = SCRIPT_DIR / "capture.bat"
    CAPTURE_CMD    = lambda mode, *args: ["cmd.exe", "/c", str(CAPTURE_SCRIPT), mode, *args]
else:
    CAPTURE_SCRIPT = SCRIPT_DIR / "capture.sh"
    CAPTURE_CMD    = lambda mode, *args: ["bash", str(CAPTURE_SCRIPT), mode, *args]

for f in (CAPTURE_SCRIPT, SEND_SCRIPT):
    if not f.exists():
        print(f"[ERRO] Arquivo nao encontrado: {f}", file=sys.stderr)
        sys.exit(1)

# ── Diretório de screenshots (configurável via config.env) ────────────────────
def _read_cfg_value(key: str, default: str) -> str:
    cfg_file = SCRIPT_DIR / "config.env"
    if cfg_file.exists():
        for line in cfg_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    return default

SCREENSHOT_DIR = SCRIPT_DIR / _read_cfg_value("SCREENSHOT_DIR", "screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)

# ── Modelos por provedor ──────────────────────────────────────────────────────
PROVIDER_MODELS: dict[str, list[str]] = {
    "gemini": [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-flash-latest",
        "gemini-pro-latest",
    ],
    "openrouter": [
        "mistralai/mistral-7b-instruct",
        "meta-llama/llama-3-70b-instruct",
        "anthropic/claude-3.5-sonnet",
    ],
}
PROVIDERS = list(PROVIDER_MODELS.keys())

# Inicializa com o provedor/modelo do config.env, se disponível
_cfg_provider = _read_cfg_value("PROVIDER", "gemini").lower()
_cfg_model    = _read_cfg_value("MODEL",    "gemini-2.5-flash")
active_provider_idx = PROVIDERS.index(_cfg_provider) if _cfg_provider in PROVIDERS else 0
active_model_idx    = 0
# Tenta posicionar no modelo configurado
_prov = PROVIDERS[active_provider_idx]
if _cfg_model in PROVIDER_MODELS[_prov]:
    active_model_idx = PROVIDER_MODELS[_prov].index(_cfg_model)

# ── Estado da sessão ──────────────────────────────────────────────────────────
session_images: list[Path] = []
session_texts:  list[str]  = []
capture_index:  int        = 0
is_processing:  bool       = False   # evita envios simultâneos

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

# ── Getters de estado ─────────────────────────────────────────────────────────
def active_provider() -> str:
    return PROVIDERS[active_provider_idx]

def active_model() -> str:
    return PROVIDER_MODELS[active_provider()][active_model_idx]

def status_line() -> str:
    return f"  [{OS_NAME}]  Provedor: {active_provider().upper():<12} Modelo: {active_model()}"

# ── Helpers ───────────────────────────────────────────────────────────────────
def _run_capture(mode: str, *extra_args: str):
    cmd = CAPTURE_CMD(mode, *extra_args)
    result = subprocess.run(
        cmd, cwd=str(SCRIPT_DIR),
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.stdout.strip():
        print(result.stdout.strip(), flush=True)
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return result

def _sep(char="─", n=52):
    print(char * n, flush=True)

def _cleanup_screenshots():
    """Remove screenshots e OCRs antigos do diretório de screenshots."""
    removed = 0
    for pattern in ("screenshot*.png", "ocr*.txt"):
        for f in SCREENSHOT_DIR.glob(pattern):
            try:
                f.unlink()
                removed += 1
            except Exception:
                pass
    if removed:
        print(f"  [Limpo] {removed} arquivo(s) antigo(s) removido(s).", flush=True)

# ── Ações ─────────────────────────────────────────────────────────────────────
def action_new_session():
    global session_images, session_texts, capture_index
    _sep("═")
    print("  [Shift+Z] Nova sessão iniciada.", flush=True)
    _cleanup_screenshots()
    session_images, session_texts, capture_index = [], [], 0
    print(status_line(), flush=True)
    _sep("═")

def action_add_image():
    global capture_index
    if not debounce():
        return
    capture_index += 1
    fname = f"screenshot{capture_index}.png"
    dest  = SCREENSHOT_DIR / fname
    _sep()
    print(f"[Shift+X] Capturando imagem -> {fname}", flush=True)
    _run_capture("image", str(dest))
    if dest.exists() and dest.stat().st_size > 0:
        session_images.append(dest)
        print(f"  ok {fname}  ({len(session_images)} img | {len(session_texts)} txt)", flush=True)
    else:
        print("  ERRO: falha ao capturar imagem.", file=sys.stderr)

def action_add_ocr():
    global capture_index
    if not debounce():
        return
    capture_index += 1
    fname    = f"screenshot{capture_index}.png"
    ocr_base = str(SCREENSHOT_DIR / f"ocr{capture_index}")
    dest_img = SCREENSHOT_DIR / fname
    _sep()
    print(f"[Shift+C] Capturando OCR -> {fname}", flush=True)
    _run_capture("ocr", str(dest_img), ocr_base)
    ocr_file = Path(ocr_base + ".txt")
    if ocr_file.exists():
        text = ocr_file.read_text(encoding="utf-8").strip()
        if text:
            session_texts.append(text)
            preview = text[:72].replace("\n", " ")
            print(f"  ok OCR  ({len(session_images)} img | {len(session_texts)} txt): {preview}...",
                  flush=True)
        else:
            print("  AVISO: OCR nao encontrou texto.", flush=True)
    else:
        print("  ERRO: arquivo OCR nao gerado.", file=sys.stderr)

def action_send():
    global is_processing
    if not debounce():
        return
    if is_processing:
        print("\n[Shift+V] Aguarde — envio em andamento...\n", flush=True)
        return
    if not session_images and not session_texts:
        print("\n[Shift+V] Sessao vazia. Use Shift+X ou Shift+C primeiro.\n", flush=True)
        return

    is_processing = True
    _sep("═")
    print(f"[Shift+V] Enviando para IA...", flush=True)
    print(f"  Imagens : {len(session_images)}", flush=True)
    print(f"  Textos  : {len(session_texts)}", flush=True)
    print(status_line(), flush=True)
    _sep("─")

    cmd = [
        sys.executable, str(SEND_SCRIPT),
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
    finally:
        is_processing = False
    _sep("═")

def action_toggle_provider():
    global active_provider_idx, active_model_idx
    active_provider_idx = (active_provider_idx + 1) % len(PROVIDERS)
    active_model_idx    = 0
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
        print("\n[DAEMON] Encerrando...", flush=True)
        return False

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 50)
    print("  Script Cola v5.0  —  " + OS_NAME)
    print("=" * 50)
    print("  Shift+Z  ->  nova sessao")
    print("  Shift+X  ->  capturar IMAGEM")
    print("  Shift+C  ->  capturar OCR")
    print("  Shift+V  ->  enviar para IA")
    print("  Shift+A  ->  alternar PROVEDOR")
    print("  Shift+M  ->  alternar MODELO")
    print("  Esc      ->  encerrar")
    print("=" * 50)
    print(status_line())
    print(f"  Screenshots em: {SCREENSHOT_DIR}")
    print("[DAEMON] Aguardando atalhos...\n", flush=True)

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        try:
            listener.join()
        except KeyboardInterrupt:
            print("\n[DAEMON] Interrompido via Ctrl+C.", flush=True)

if __name__ == "__main__":
    main()