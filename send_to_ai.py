#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
send_to_ai.py — Script Cola v4.0
Envia imagens e/ou textos para Gemini ou OpenRouter.

Uso:
  python3 send_to_ai.py --image foto1.png --image foto2.png --text "ocr..."
  python3 send_to_ai.py --provider gemini --model gemini-2.5-flash --image tela.png
  python3 send_to_ai.py --provider openrouter --model mistralai/mistral-7b-instruct --text "..."

Flags repetíveis: --image, --text

Consultar modelos disponíveis:
  Gemini:
    curl "https://generativelanguage.googleapis.com/v1beta/models?key=SUA_CHAVE"
  OpenRouter:
    curl -H "Authorization: Bearer SUA_CHAVE" https://openrouter.ai/api/v1/models
"""

import sys, os, argparse, time, base64, json, subprocess, tempfile
import requests
from pathlib import Path

# ── UTF-8 ─────────────────────────────────────────────────────────────────────
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.env"

def load_env(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env

cfg = load_env(CONFIG_FILE)

GEMINI_KEY     = cfg.get("GEMINI_API_KEY",     os.environ.get("GEMINI_API_KEY",     ""))
OPENROUTER_KEY = cfg.get("OPENROUTER_API_KEY", os.environ.get("OPENROUTER_API_KEY", ""))

DEFAULT_PROVIDER = cfg.get("PROVIDER", "gemini").lower()
DEFAULT_MODEL    = cfg.get("MODEL",    "gemini-2.5-flash")

# ── Modelos de fallback ───────────────────────────────────────────────────────
# Gemini: tentados em sequência se o modelo primário falhar
GEMINI_FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-flash-latest",
    "gemini-pro-latest",
]

# OpenRouter: tentados em sequência se o modelo primário falhar
OPENROUTER_FALLBACK_MODELS = [
    "mistralai/mistral-7b-instruct",
    "meta-llama/llama-3-70b-instruct",
    "anthropic/claude-3.5-sonnet",
]

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
    return any(k in dump for k in [
        "quota", "rate_limit", "rate limit", "resource_exhausted", "429", "too many"
    ])

def ocr_image(img_path: str) -> str:
    """Roda tesseract na imagem e devolve o texto extraído."""
    with tempfile.NamedTemporaryFile(suffix="", delete=False) as tmp:
        base = tmp.name
    try:
        subprocess.run(
            ["tesseract", img_path, base, "-l", "por+eng"],
            capture_output=True, check=False
        )
        txt_file = Path(base + ".txt")
        return txt_file.read_text(encoding="utf-8").strip() if txt_file.exists() else ""
    finally:
        for ext in (".txt", ""):
            p = Path(base + ext)
            if p.exists():
                p.unlink(missing_ok=True)

# ── Chamada Gemini ────────────────────────────────────────────────────────────
def call_gemini(model: str, images: list, texts: list) -> str:
    if not GEMINI_KEY:
        raise ValueError("GEMINI_API_KEY não configurado em config.env")

    url   = (f"https://generativelanguage.googleapis.com/v1beta/models/"
             f"{model}:generateContent?key={GEMINI_KEY}")
    parts = [{"text": SYSTEM_PROMPT}]

    for img in images:
        parts.append({"inline_data": {
            "mime_type": "image/png",
            "data": encode_image(img)
        }})
    if images:
        parts.append({"text": "Analise as imagens acima de forma útil e concisa."})
    if texts:
        parts.append({"text": "\n\n---\n\n".join(texts)})

    resp = requests.post(url, json={"contents": [{"parts": parts}]}, timeout=90)
    if resp.status_code != 200:
        data = resp.json()
        raise RuntimeError(
            ("RATE_LIMIT: " if is_rate_limit(data) else "") +
            f"Gemini [{model}] HTTP {resp.status_code}: {resp.text[:200]}"
        )
    return extract_text("gemini", resp.json())

# ── Chamada OpenRouter ────────────────────────────────────────────────────────
def call_openrouter(model: str, images: list, texts: list) -> str:
    if not OPENROUTER_KEY:
        raise ValueError("OPENROUTER_API_KEY não configurado em config.env")

    # OpenRouter não aceita imagens → OCR automático
    all_texts = list(texts)
    for img in images:
        print(f"[INFO] OCR automático em {Path(img).name} (OpenRouter não aceita imagens)…",
              flush=True)
        ocr = ocr_image(img)
        if ocr:
            all_texts.append(f"[Texto extraído via OCR de {Path(img).name}]\n{ocr}")
        else:
            print(f"[AVISO] OCR vazio para {img} — imagem ignorada.", file=sys.stderr)

    if not all_texts:
        raise RuntimeError("OpenRouter: sem conteúdo para enviar após OCR.")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  cfg.get("OPENROUTER_SITE_URL", "https://github.com/script-cola"),
        "X-Title":       cfg.get("OPENROUTER_APP_NAME", "Script Cola"),
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": "\n\n---\n\n".join(all_texts)},
        ],
        "max_tokens": 1024,
    }
    resp = requests.post(
        cfg.get("OPENROUTER_ENDPOINT", "https://openrouter.ai/api/v1/chat/completions"),
        headers=headers, json=payload, timeout=90
    )
    if resp.status_code != 200:
        data = resp.json()
        raise RuntimeError(
            ("RATE_LIMIT: " if is_rate_limit(data) else "") +
            f"OpenRouter [{model}] HTTP {resp.status_code}: {resp.text[:200]}"
        )
    return extract_text("openrouter", resp.json())

# ── Dispatcher ────────────────────────────────────────────────────────────────
CALLERS = {
    "gemini":     call_gemini,
    "openrouter": call_openrouter,
}

# ── Retry num único provedor+modelo ──────────────────────────────────────────
def try_once(provider: str, model: str, images: list, texts: list) -> str:
    caller = CALLERS.get(provider)
    if not caller:
        raise ValueError(f"Provedor desconhecido: '{provider}'. Use: gemini, openrouter.")
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"[INFO] {provider.upper()} / {model}  (tentativa {attempt}/{MAX_RETRIES})",
                  flush=True)
            return caller(model, images, texts)
        except RuntimeError as e:
            print(f"[AVISO] {str(e)[:140]}", file=sys.stderr)
            if attempt < MAX_RETRIES:
                print(f"[INFO] Aguardando {RETRY_DELAY}s…", flush=True)
                time.sleep(RETRY_DELAY)
            else:
                raise

# ── Fallback inteligente ──────────────────────────────────────────────────────
def send(primary_provider: str, primary_model: str, images: list, texts: list) -> str:
    """
    Estratégia de fallback:
      1. Tenta primary_provider / primary_model (com retry até MAX_RETRIES)
      2. Se Gemini: tenta demais modelos de GEMINI_FALLBACK_MODELS
         Se OpenRouter: tenta demais modelos de OPENROUTER_FALLBACK_MODELS
      3. Se todos falharam no provedor primário → tenta o outro provedor
         (com seus próprios modelos de fallback)
    """
    # ── 1. modelo solicitado
    try:
        return try_once(primary_provider, primary_model, images, texts)
    except Exception as e:
        print(f"[AVISO] {primary_provider}/{primary_model} falhou: {e}", file=sys.stderr)

    # ── 2. outros modelos do mesmo provedor
    fallback_map = {
        "gemini":     GEMINI_FALLBACK_MODELS,
        "openrouter": OPENROUTER_FALLBACK_MODELS,
    }
    for fb_model in fallback_map.get(primary_provider, []):
        if fb_model == primary_model:
            continue
        try:
            print(f"[INFO] Fallback {primary_provider} → {fb_model}", flush=True)
            return try_once(primary_provider, fb_model, images, texts)
        except Exception as e:
            print(f"[AVISO] {primary_provider}/{fb_model} falhou: {e}", file=sys.stderr)

    # ── 3. provedor alternativo
    alt_provider = "openrouter" if primary_provider == "gemini" else "gemini"
    alt_models   = fallback_map.get(alt_provider, [])
    print(f"[INFO] Todos os modelos de '{primary_provider}' falharam. "
          f"Tentando {alt_provider.upper()}…", flush=True)
    for fb_model in alt_models:
        try:
            print(f"[INFO] Fallback {alt_provider} → {fb_model}", flush=True)
            return try_once(alt_provider, fb_model, images, texts)
        except Exception as e:
            print(f"[AVISO] {alt_provider}/{fb_model} falhou: {e}", file=sys.stderr)

    raise RuntimeError("Todos os provedores e modelos falharam.")

# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Script Cola — envia capturas para IA.")
    parser.add_argument("--image",    metavar="FILE", action="append", default=[])
    parser.add_argument("--text",     metavar="TEXT", action="append", default=[])
    parser.add_argument("--provider", metavar="PROV", default=DEFAULT_PROVIDER,
                        choices=list(CALLERS))
    parser.add_argument("--model",    metavar="MDL",  default=DEFAULT_MODEL)
    args = parser.parse_args()

    if not args.image and not args.text:
        print("[ERRO] Forneça pelo menos --image ou --text.", file=sys.stderr)
        sys.exit(1)

    for img in args.image:
        if not Path(img).exists():
            print(f"[ERRO] Arquivo não encontrado: {img}", file=sys.stderr)
            sys.exit(1)

    print(f"[INFO] Provedor: {args.provider.upper()} | Modelo: {args.model} | "
          f"Imagens: {len(args.image)} | Textos: {len(args.text)}", flush=True)

    try:
        response = send(args.provider, args.model, args.image, args.text)
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