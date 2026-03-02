#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daemon.py — Escuta atalhos globais de teclado e dispara capture.sh

  Ctrl+Space  →  ./capture.sh image
  Alt+Space   →  ./capture.sh text

Dependência:
  pip install pynput
"""

import subprocess
import sys
import os
from pathlib import Path
from pynput import keyboard

# ── Caminho do capture.sh (mesmo diretório do daemon.py) ─────────────────────
SCRIPT_DIR   = Path(__file__).parent
CAPTURE_SH   = SCRIPT_DIR / "capture.sh"

if not CAPTURE_SH.exists():
    print(f"[ERRO] capture.sh não encontrado em {SCRIPT_DIR}", file=sys.stderr)
    sys.exit(1)

# ── Conjunto de teclas pressionadas no momento ────────────────────────────────
current_keys: set = set()

def run(mode: str):
    """Executa capture.sh com o modo indicado e imprime saída em tempo real."""
    print(f"\n{'─'*50}", flush=True)
    print(f"[DAEMON] Atalho acionado → capture.sh {mode}", flush=True)
    print(f"{'─'*50}", flush=True)
    try:
        subprocess.run(
            ["bash", str(CAPTURE_SH), mode],
            cwd=str(SCRIPT_DIR),
        )
    except Exception as e:
        print(f"[ERRO] Falha ao executar capture.sh: {e}", file=sys.stderr)
    print(f"{'─'*50}\n", flush=True)


def normalize(key):
    """Retorna uma representação hashável e comparável da tecla."""
    try:
        return key.char  # teclas normais: 'a', 'b', ' '...
    except AttributeError:
        return key        # teclas especiais: Key.ctrl_l, Key.space...


def on_press(key):
    current_keys.add(normalize(key))

    pressed = current_keys

    # Ctrl + Space
    ctrl_held  = (keyboard.Key.ctrl_l  in pressed or keyboard.Key.ctrl_r  in pressed)
    alt_held   = (keyboard.Key.alt_l   in pressed or keyboard.Key.alt_r   in pressed
                  or keyboard.Key.alt_gr in pressed)
    space_held = (keyboard.Key.space in pressed or ' ' in pressed)

    if ctrl_held and space_held and not alt_held:
        current_keys.discard(keyboard.Key.space)   # evita disparo duplo
        current_keys.discard(' ')
        run("image")

    elif alt_held and space_held and not ctrl_held:
        current_keys.discard(keyboard.Key.space)
        current_keys.discard(' ')
        run("text")


def on_release(key):
    current_keys.discard(normalize(key))
    # Sair com Ctrl+C capturado via pynput (Esc como saída alternativa)
    if key == keyboard.Key.esc:
        print("\n[DAEMON] Encerrando (Esc pressionado).", flush=True)
        return False   # para o listener


def main():
    print("╔══════════════════════════════════════════╗")
    print("║      Android AI Screen Daemon  v1.0      ║")
    print("╠══════════════════════════════════════════╣")
    print("║  Ctrl+Space  →  capture.sh image         ║")
    print("║  Alt+Space   →  capture.sh text          ║")
    print("║  Esc         →  encerrar daemon          ║")
    print("╚══════════════════════════════════════════╝")
    print(f"\n[DAEMON] Monitorando atalhos... (script: {CAPTURE_SH})\n", flush=True)

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        try:
            listener.join()
        except KeyboardInterrupt:
            print("\n[DAEMON] Interrompido via Ctrl+C.", flush=True)


if __name__ == "__main__":
    main()