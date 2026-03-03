#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daemon.py — Script Cola | Listener de atalhos globais de teclado

  Shift+Z  →  Nova sessão: limpa todas as capturas acumuladas
  Shift+X  →  Adicionar captura como IMAGEM (screenshot numerado)
  Shift+C  →  Adicionar captura como OCR  (extrai texto da tela)
  Shift+V  →  Enviar tudo acumulado para a IA e exibir resposta
  Esc      →  Encerrar o daemon

Fluxo típico:
  1. Shift+Z   → inicia sessão
  2. Shift+X / Shift+C  (repetir quantas vezes quiser)
  3. Shift+V   → envia e recebe resposta no terminal

Dependência:
  pip install pynput
"""

import subprocess
import sys
import time
from pathlib import Path
from pynput import keyboard

# ── Configuração de caminhos ──────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent
CAPTURE_SH  = SCRIPT_DIR / "capture.sh"
SEND_SCRIPT = SCRIPT_DIR / "send_to_ai.py"

if not CAPTURE_SH.exists():
    print(f"[ERRO] capture.sh não encontrado em {SCRIPT_DIR}", file=sys.stderr)
    sys.exit(1)
if not SEND_SCRIPT.exists():
    print(f"[ERRO] send_to_ai.py não encontrado em {SCRIPT_DIR}", file=sys.stderr)
    sys.exit(1)

# ── Estado da sessão ──────────────────────────────────────────────────────────
session_images: list[Path] = []   # caminhos dos screenshots salvos
session_texts:  list[str]  = []   # textos OCR extraídos
capture_index: int = 0            # contador de screenshots da sessão

# ── Controle de debounce (evita disparo duplo rápido) ─────────────────────────
_last_action: float = 0.0
DEBOUNCE_SEC: float = 0.4


def debounce() -> bool:
    global _last_action
    now = time.time()
    if now - _last_action < DEBOUNCE_SEC:
        return False
    _last_action = now
    return True


# ── Ações ─────────────────────────────────────────────────────────────────────
def action_new_session():
    global session_images, session_texts, capture_index
    session_images = []
    session_texts  = []
    capture_index  = 0
    print("\n" + "═"*50, flush=True)
    print("  [Shift+Z] Nova sessão iniciada — listas limpas.", flush=True)
    print("═"*50 + "\n", flush=True)


def action_add_image():
    global capture_index
    if not debounce():
        return
    capture_index += 1
    filename = f"screenshot{capture_index}.png"
    dest     = SCRIPT_DIR / filename

    print(f"\n[Shift+X] Capturando imagem → {filename}", flush=True)
    result = subprocess.run(
        ["bash", str(CAPTURE_SH), "image", filename],
        cwd=str(SCRIPT_DIR),
        capture_output=True, text=True
    )
    _print_proc(result)

    if dest.exists() and dest.stat().st_size > 0:
        session_images.append(dest)
        print(f"  ✔ Imagem adicionada à sessão ({len(session_images)} imagem(ns)).\n", flush=True)
    else:
        print("  ✘ Falha ao capturar imagem.\n", file=sys.stderr)


def action_add_ocr():
    global capture_index
    if not debounce():
        return
    capture_index += 1
    filename     = f"screenshot{capture_index}.png"
    ocr_filename = f"ocr{capture_index}"

    print(f"\n[Shift+C] Capturando OCR → {filename}", flush=True)
    result = subprocess.run(
        ["bash", str(CAPTURE_SH), "ocr", filename, ocr_filename],
        cwd=str(SCRIPT_DIR),
        capture_output=True, text=True
    )
    _print_proc(result)

    ocr_file = SCRIPT_DIR / f"{ocr_filename}.txt"
    if ocr_file.exists():
        text = ocr_file.read_text(encoding="utf-8").strip()
        if text:
            session_texts.append(text)
            preview = text[:80].replace("\n", " ")
            print(f"  ✔ Texto adicionado ({len(session_texts)} texto(s)): {preview}…\n", flush=True)
        else:
            print("  ⚠ OCR não encontrou texto nesta captura.\n", flush=True)
    else:
        print("  ✘ Arquivo OCR não gerado.\n", file=sys.stderr)


def action_send():
    if not debounce():
        return
    if not session_images and not session_texts:
        print("\n[Shift+V] Nenhuma captura na sessão. Use Shift+X ou Shift+C primeiro.\n", flush=True)
        return

    print(f"\n{'═'*50}", flush=True)
    print(f"[Shift+V] Enviando sessão para IA…", flush=True)
    print(f"  Imagens : {len(session_images)}", flush=True)
    print(f"  Textos  : {len(session_texts)}", flush=True)
    print(f"{'─'*50}", flush=True)

    cmd = ["python3", str(SEND_SCRIPT)]
    for img in session_images:
        cmd += ["--image", str(img)]
    if session_texts:
        combined = "\n\n---\n\n".join(session_texts)
        cmd += ["--text", combined]

    try:
        subprocess.run(cmd, cwd=str(SCRIPT_DIR))
    except Exception as e:
        print(f"[ERRO] {e}", file=sys.stderr)

    print(f"{'═'*50}\n", flush=True)


def _print_proc(result):
    """Imprime stdout/stderr de subprocesso se não vazio."""
    if result.stdout.strip():
        print(result.stdout.strip(), flush=True)
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)


# ── Listener de teclado ───────────────────────────────────────────────────────
current_keys: set = set()


def normalize(key):
    try:
        return key.char
    except AttributeError:
        return key


def on_press(key):
    current_keys.add(normalize(key))

    shift = (keyboard.Key.shift in current_keys or
             keyboard.Key.shift_l in current_keys or
             keyboard.Key.shift_r in current_keys)

    char = normalize(key)

    if shift and char in ('z', 'Z'):
        action_new_session()
    elif shift and char in ('x', 'X'):
        action_add_image()
    elif shift and char in ('c', 'C'):
        action_add_ocr()
    elif shift and char in ('v', 'V'):
        action_send()


def on_release(key):
    current_keys.discard(normalize(key))
    if key == keyboard.Key.esc:
        print("\n[DAEMON] Encerrando (Esc pressionado).", flush=True)
        return False


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("╔══════════════════════════════════════════╗")
    print("║          Script Cola  —  daemon  v2.0    ║")
    print("╠══════════════════════════════════════════╣")
    print("║  Shift+Z  →  nova sessão (limpar tudo)   ║")
    print("║  Shift+X  →  capturar como IMAGEM        ║")
    print("║  Shift+C  →  capturar como OCR           ║")
    print("║  Shift+V  →  enviar tudo para a IA       ║")
    print("║  Esc      →  encerrar daemon              ║")
    print("╚══════════════════════════════════════════╝")
    print(f"\n[DAEMON] Aguardando atalhos…\n", flush=True)

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        try:
            listener.join()
        except KeyboardInterrupt:
            print("\n[DAEMON] Interrompido via Ctrl+C.", flush=True)


if __name__ == "__main__":
    main()