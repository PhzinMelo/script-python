#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
send_to_ai.py — Envia imagem ou texto para Gemini ou Copilot e exibe resposta.

Uso:
  python3 send_to_ai.py --image screenshot.png
  python3 send_to_ai.py --text "texto extraído pelo OCR"
"""

import sys
import os
import argparse
import time
import base64
import json
import requests
from pathlib import Path

# ── Codificação UTF-8 forçada ────────────────────────────────────────────────
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# ── Carrega config.env ───────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.env"

def load_env(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                env[key.strip()] = val.strip().strip('"').strip("'")
    return env

cfg = load_env(CONFIG_FILE)
GEMINI_API_KEY  = cfg.get("GEMINI_API_KEY",  os.environ.get("GEMINI_API_KEY",  ""))
COPILOT_API_KEY = cfg.get("COPILOT_API_KEY", os.environ.get("COPILOT_API_KEY", ""))
DEFAULT_PROVIDER = cfg.get("PROVIDER", os.environ.get("PROVIDER", "gemini")).lower()
GEMINI_MODEL    = cfg.get("MODEL", "gemini-flash-latest")

# ── Constantes ───────────────────────────────────────────────────────────────
MAX_RETRIES   = 3
RETRY_DELAY   = 5   # segundos entre tentativas

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent?key={{key}}"
)
COPILOT_URL = "https://api.openai.com/v1/chat/completions"  # Azure/OpenAI compat

SYSTEM_PROMPT = (
    "Você é um assistente direto e objetivo. "
    "Responda de forma concisa, sem rodeios e sem repetir a pergunta. "
    "Use português do Brasil quando possível."
)

# ── Helpers ──────────────────────────────────────────────────────────────────
def encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def extract_text_from_response(provider: str, data: dict) -> str:
    """Normaliza JSON de resposta e retorna apenas o texto relevante."""
    try:
        if provider == "gemini":
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        else:  # copilot / openai-compat
            return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        return json.dumps(data, ensure_ascii=False, indent=2)


def is_token_limit_error(provider: str, data: dict) -> bool:
    """Detecta erros de limite de tokens ou quota."""
    dump = json.dumps(data).lower()
    keywords = ["token", "quota", "rate limit", "429", "resource_exhausted"]
    return any(k in dump for k in keywords)

# ── Chamadas de API ──────────────────────────────────────────────────────────
def call_gemini(image_path: str = None, text: str = None) -> str:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY não configurado em config.env")

    url = GEMINI_URL.format(key=GEMINI_API_KEY)
    parts = []

    # Instrução de sistema como parte de texto inicial
    parts.append({"text": SYSTEM_PROMPT})

    if image_path:
        b64 = encode_image(image_path)
        parts.append({
            "inline_data": {
                "mime_type": "image/png",
                "data": b64
            }
        })
        parts.append({"text": "Descreva o que está sendo exibido na tela e responda de forma útil e concisa."})
    elif text:
        parts.append({"text": text})

    payload = {"contents": [{"parts": parts}]}
    resp = requests.post(url, json=payload, timeout=60)

    if resp.status_code != 200:
        data = resp.json()
        if is_token_limit_error("gemini", data):
            raise RuntimeError("TOKEN_LIMIT:" + json.dumps(data))
        raise RuntimeError(f"Gemini HTTP {resp.status_code}: {resp.text[:300]}")

    return extract_text_from_response("gemini", resp.json())


def call_copilot(text: str) -> str:
    """Copilot via Azure OpenAI ou OpenAI-compat endpoint."""
    if not COPILOT_API_KEY:
        raise ValueError("COPILOT_API_KEY não configurado em config.env")

    headers = {
        "Authorization": f"Bearer {COPILOT_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": text},
        ],
        "max_tokens": 1024,
    }
    resp = requests.post(COPILOT_URL, headers=headers, json=payload, timeout=60)

    if resp.status_code != 200:
        data = resp.json()
        if is_token_limit_error("copilot", data):
            raise RuntimeError("TOKEN_LIMIT:" + json.dumps(data))
        raise RuntimeError(f"Copilot HTTP {resp.status_code}: {resp.text[:300]}")

    return extract_text_from_response("copilot", resp.json())

# ── Lógica principal com retry + fallback ────────────────────────────────────
def send_with_retry(provider: str, image_path: str = None, text: str = None) -> str:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"[INFO] Tentativa {attempt}/{MAX_RETRIES} — provedor: {provider}", flush=True)
            if provider == "gemini":
                return call_gemini(image_path=image_path, text=text)
            else:
                # Copilot só aceita texto
                if image_path and not text:
                    raise RuntimeError("Copilot não aceita imagem diretamente.")
                return call_copilot(text=text)
        except RuntimeError as e:
            msg = str(e)
            print(f"[AVISO] Erro: {msg[:120]}", file=sys.stderr)
            if attempt < MAX_RETRIES:
                print(f"[INFO] Aguardando {RETRY_DELAY}s antes de nova tentativa...", flush=True)
                time.sleep(RETRY_DELAY)
            else:
                raise


def send(image_path: str = None, text: str = None) -> str:
    providers = [DEFAULT_PROVIDER]
    fallback = "copilot" if DEFAULT_PROVIDER == "gemini" else "gemini"
    providers.append(fallback)

    # Se modo é imagem e fallback é copilot, pula (copilot não aceita imagem)
    for provider in providers:
        if image_path and not text and provider == "copilot":
            print(f"[INFO] Pulando Copilot para imagem (não suportado).", flush=True)
            continue
        try:
            result = send_with_retry(provider, image_path=image_path, text=text)
            return result
        except Exception as e:
            print(f"[AVISO] Provedor '{provider}' falhou definitivamente: {e}", file=sys.stderr)

    raise RuntimeError("Todos os provedores falharam.")

# ── Entry point ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Envia conteúdo para IA e exibe resposta.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--image", metavar="FILE",  help="Caminho para screenshot PNG")
    group.add_argument("--text",  metavar="TEXT",  help="Texto extraído pelo OCR")
    args = parser.parse_args()

    try:
        if args.image:
            if not Path(args.image).exists():
                print(f"[ERRO] Arquivo não encontrado: {args.image}", file=sys.stderr)
                sys.exit(1)
            response = send(image_path=args.image)
        else:
            if not args.text.strip():
                print("[ERRO] Texto vazio.", file=sys.stderr)
                sys.exit(1)
            response = send(text=args.text)

        print("\n" + "─" * 60)
        print("RESPOSTA DA IA:")
        print("─" * 60)
        print(response)
        print("─" * 60 + "\n")

    except Exception as e:
        print(f"\n[ERRO FATAL] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()