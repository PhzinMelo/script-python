#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
send_to_ai.py — Script Cola | Envia imagens e/ou textos para Gemini ou Copilot

Uso:
  python3 send_to_ai.py --image foto1.png --image foto2.png --text "texto ocr"
  python3 send_to_ai.py --image screenshot1.png
  python3 send_to_ai.py --text "conteúdo extraído pelo OCR"

Múltiplas flags --image e --text são aceitas e combinadas numa única requisição.
"""

import sys
import os
import argparse
import time
import base64
import json
import requests
from pathlib import Path

# ── UTF-8 forçado ─────────────────────────────────────────────────────────────
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# ── Carrega config.env ────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent
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

GEMINI_API_KEY   = cfg.get("GEMINI_API_KEY",  os.environ.get("GEMINI_API_KEY",  ""))
COPILOT_API_KEY  = cfg.get("COPILOT_API_KEY", os.environ.get("COPILOT_API_KEY", ""))
DEFAULT_PROVIDER = cfg.get("PROVIDER",        os.environ.get("PROVIDER", "gemini")).lower()
GEMINI_MODEL     = cfg.get("MODEL", "gemini-flash-latest")
COPILOT_MODEL    = cfg.get("COPILOT_MODEL", "gpt-4o")
COPILOT_URL      = cfg.get("COPILOT_ENDPOINT", "https://api.openai.com/v1/chat/completions")

GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent?key={{key}}"
)

MAX_RETRIES = 3
RETRY_DELAY = 5

SYSTEM_PROMPT = (
    "Você é um assistente direto e objetivo. "
    "Responda de forma concisa, sem rodeios e sem repetir a pergunta. "
    "Use português do Brasil quando possível."
)

# ── Helpers ───────────────────────────────────────────────────────────────────
def encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def extract_text(provider: str, data: dict) -> str:
    try:
        if provider == "gemini":
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        else:
            return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        return json.dumps(data, ensure_ascii=False, indent=2)


def is_rate_limit(data: dict) -> bool:
    dump = json.dumps(data).lower()
    return any(k in dump for k in ["token", "quota", "rate limit", "429", "resource_exhausted"])


# ── Chamadas de API ───────────────────────────────────────────────────────────
def call_gemini(images: list[str], texts: list[str]) -> str:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY não configurado em config.env")

    url = GEMINI_URL.format(key=GEMINI_API_KEY)
    parts = [{"text": SYSTEM_PROMPT}]

    for img_path in images:
        parts.append({
            "inline_data": {
                "mime_type": "image/png",
                "data": encode_image(img_path)
            }
        })

    if images:
        parts.append({"text": "Analise as imagens acima e responda de forma útil e concisa."})

    if texts:
        combined = "\n\n---\n\n".join(texts)
        parts.append({"text": combined})

    resp = requests.post(url, json={"contents": [{"parts": parts}]}, timeout=90)

    if resp.status_code != 200:
        data = resp.json()
        if is_rate_limit(data):
            raise RuntimeError("RATE_LIMIT:" + json.dumps(data))
        raise RuntimeError(f"Gemini HTTP {resp.status_code}: {resp.text[:300]}")

    return extract_text("gemini", resp.json())


def call_copilot(texts: list[str]) -> str:
    if not COPILOT_API_KEY:
        raise ValueError("COPILOT_API_KEY não configurado em config.env")

    combined = "\n\n---\n\n".join(texts) if texts else ""
    headers  = {
        "Authorization": f"Bearer {COPILOT_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": COPILOT_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": combined},
        ],
        "max_tokens": 1024,
    }
    resp = requests.post(COPILOT_URL, headers=headers, json=payload, timeout=90)

    if resp.status_code != 200:
        data = resp.json()
        if is_rate_limit(data):
            raise RuntimeError("RATE_LIMIT:" + json.dumps(data))
        raise RuntimeError(f"Copilot HTTP {resp.status_code}: {resp.text[:300]}")

    return extract_text("copilot", resp.json())


# ── Retry + fallback ──────────────────────────────────────────────────────────
def call_with_retry(provider: str, images: list[str], texts: list[str]) -> str:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"[INFO] Tentativa {attempt}/{MAX_RETRIES} — {provider.upper()}", flush=True)
            if provider == "gemini":
                return call_gemini(images, texts)
            else:
                if images and not texts:
                    raise RuntimeError("Copilot não aceita imagens. Sem texto OCR disponível.")
                return call_copilot(texts)
        except RuntimeError as e:
            print(f"[AVISO] {str(e)[:120]}", file=sys.stderr)
            if attempt < MAX_RETRIES:
                print(f"[INFO] Aguardando {RETRY_DELAY}s…", flush=True)
                time.sleep(RETRY_DELAY)
            else:
                raise


def send(images: list[str], texts: list[str]) -> str:
    providers = [DEFAULT_PROVIDER,
                 "copilot" if DEFAULT_PROVIDER == "gemini" else "gemini"]

    for provider in providers:
        # Copilot não suporta imagem sem texto
        if provider == "copilot" and images and not texts:
            print("[INFO] Pulando Copilot (sem texto OCR para enviar).", flush=True)
            continue
        try:
            return call_with_retry(provider, images, texts)
        except Exception as e:
            print(f"[AVISO] '{provider}' falhou definitivamente: {e}", file=sys.stderr)

    raise RuntimeError("Todos os provedores falharam.")


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Script Cola — envia imagens e/ou textos para IA."
    )
    parser.add_argument("--image", metavar="FILE", action="append", default=[],
                        help="Caminho para screenshot PNG (repetível)")
    parser.add_argument("--text",  metavar="TEXT", action="append", default=[],
                        help="Texto OCR a enviar (repetível)")
    args = parser.parse_args()

    if not args.image and not args.text:
        print("[ERRO] Forneça pelo menos --image ou --text.", file=sys.stderr)
        sys.exit(1)

    # Valida existência dos arquivos de imagem
    for img in args.image:
        if not Path(img).exists():
            print(f"[ERRO] Arquivo não encontrado: {img}", file=sys.stderr)
            sys.exit(1)

    print(f"[INFO] Imagens : {len(args.image)} | Textos: {len(args.text)}", flush=True)

    try:
        response = send(args.image, args.text)
        print("\n" + "─"*60)
        print("RESPOSTA DA IA:")
        print("─"*60)
        print(response)
        print("─"*60 + "\n")
    except Exception as e:
        print(f"\n[ERRO FATAL] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()