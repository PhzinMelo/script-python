#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
send_to_ai.py — Script Cola v5.0
Envia imagens e/ou textos para Gemini ou OpenRouter.

Uso:
  python send_to_ai.py --image foto1.png --text "ocr..."
  python send_to_ai.py --provider gemini --model gemini-2.5-flash --image tela.png
  python send_to_ai.py --provider openrouter --model mistralai/mistral-7b-instruct --text "..."
"""

import sys, os, argparse, time, base64, json, subprocess, tempfile, mimetypes
import requests
from pathlib import Path

# ── UTF-8 (essencial no Windows) ──────────────────────────────────────────────
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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

# Configuráveis via config.env
TIMEOUT     = int(cfg.get("TIMEOUT",    "20"))
MAX_RETRIES = int(cfg.get("MAX_RETRIES", "2"))
MAX_TOKENS  = int(cfg.get("MAX_TOKENS", "400"))
IMG_MAX_W   = int(cfg.get("IMAGE_MAX_SIZE", "1280"))
IMG_QUALITY = int(cfg.get("IMAGE_QUALITY",  "80"))

# Fallback enxuto — apenas 2 modelos por provedor para resposta rápida
GEMINI_FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-flash-latest",
]
OPENROUTER_FALLBACK_MODELS = [
    "mistralai/mistral-7b-instruct",
    "meta-llama/llama-3-70b-instruct",
]

SYSTEM_PROMPT = (
    "Você é um assistente direto e objetivo. "
    "Responda de forma concisa, sem rodeios e sem repetir a pergunta. "
    "Use português do Brasil quando possível."
)

# ── Pillow opcional (redimensionamento) ───────────────────────────────────────
try:
    from PIL import Image as PILImage
    import io as _io
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ── Helpers ───────────────────────────────────────────────────────────────────
def prepare_image(path: str) -> tuple[str, str]:
    """
    Redimensiona e comprime a imagem se necessário.
    Retorna (base64_data, mime_type).
    Detecta MIME automaticamente via mimetypes.
    """
    mime, _ = mimetypes.guess_type(path)
    mime = mime or "image/png"

    if HAS_PIL:
        img = PILImage.open(path).convert("RGB")
        # Redimensiona se largura > IMG_MAX_W
        if img.width > IMG_MAX_W:
            ratio  = IMG_MAX_W / img.width
            new_h  = int(img.height * ratio)
            img    = img.resize((IMG_MAX_W, new_h), PILImage.LANCZOS)
        buf = _io.BytesIO()
        img.save(buf, format="JPEG", quality=IMG_QUALITY, optimize=True)
        data = base64.b64encode(buf.getvalue()).decode("utf-8")
        mime = "image/jpeg"
    else:
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")

    return data, mime


def extract_gemini_text(data: dict) -> str:
    """Concatena todos os parts de todos os candidates."""
    try:
        parts = []
        for candidate in data.get("candidates", []):
            finish = candidate.get("finishReason", "STOP")
            if finish not in ("STOP", "MAX_TOKENS"):
                continue
            for part in candidate.get("content", {}).get("parts", []):
                t = part.get("text", "").strip()
                if t:
                    parts.append(t)
        if parts:
            return "\n".join(parts)
        # Resposta bloqueada ou vazia
        blocked = data.get("promptFeedback", {}).get("blockReason", "")
        if blocked:
            return f"[Resposta bloqueada pelo Gemini: {blocked}]"
        return "[Resposta vazia do Gemini]"
    except Exception:
        return json.dumps(data, ensure_ascii=False, indent=2)


def extract_openrouter_text(data: dict) -> str:
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        return json.dumps(data, ensure_ascii=False, indent=2)


def safe_json(resp) -> dict:
    """Tenta decodificar JSON; retorna dict com erro em caso de falha."""
    try:
        return resp.json()
    except Exception:
        return {"error": resp.text[:300]}


def is_rate_limit(data: dict) -> bool:
    dump = json.dumps(data).lower()
    return any(k in dump for k in [
        "quota", "rate_limit", "rate limit", "resource_exhausted", "429", "too many"
    ])


def ocr_image(img_path: str) -> str:
    """OCR via Tesseract com parâmetros rápidos (PSM 6 = bloco uniforme)."""
    tmp_base = Path(tempfile.mktemp())
    try:
        result = subprocess.run(
            ["tesseract", img_path, str(tmp_base),
             "-l", "por+eng", "--psm", "6", "--oem", "1"],
            capture_output=True, timeout=15, check=False
        )
        txt_file = Path(str(tmp_base) + ".txt")
        if txt_file.exists():
            text = txt_file.read_text(encoding="utf-8").strip()
            return text if text else ""
        return ""
    except subprocess.TimeoutExpired:
        print("[AVISO] OCR demorou demais — ignorado.", file=sys.stderr)
        return ""
    except FileNotFoundError:
        print("[AVISO] Tesseract não encontrado — pulando OCR.", file=sys.stderr)
        return ""
    finally:
        for suffix in (".txt", ""):
            p = Path(str(tmp_base) + suffix)
            if p.exists():
                try: p.unlink()
                except Exception: pass


# ── Chamada Gemini ────────────────────────────────────────────────────────────
def call_gemini(model: str, images: list, texts: list) -> str:
    if not GEMINI_KEY:
        raise ValueError("GEMINI_API_KEY não configurado em config.env")

    url   = (f"https://generativelanguage.googleapis.com/v1beta/models/"
             f"{model}:generateContent?key={GEMINI_KEY}")
    parts = [{"text": SYSTEM_PROMPT}]

    for img in images:
        b64, mime = prepare_image(img)
        parts.append({"inline_data": {"mime_type": mime, "data": b64}})
    if images:
        parts.append({"text": "Analise as imagens acima de forma útil e concisa."})
    if texts:
        parts.append({"text": "\n\n---\n\n".join(texts)})

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"maxOutputTokens": MAX_TOKENS},
    }

    try:
        resp = requests.post(url, json=payload, timeout=TIMEOUT)
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Gemini [{model}] timeout após {TIMEOUT}s")
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(f"Gemini [{model}] erro de rede: {e}")

    data = safe_json(resp)
    if resp.status_code != 200:
        raise RuntimeError(
            ("RATE_LIMIT: " if is_rate_limit(data) else "") +
            f"Gemini [{model}] HTTP {resp.status_code}: {str(data)[:200]}"
        )
    return extract_gemini_text(data)


# ── Chamada OpenRouter ────────────────────────────────────────────────────────
def call_openrouter(model: str, images: list, texts: list) -> str:
    if not OPENROUTER_KEY:
        raise ValueError("OPENROUTER_API_KEY não configurado em config.env")

    all_texts = list(texts)
    for img in images:
        print(f"[INFO] OCR automático: {Path(img).name}", flush=True)
        ocr = ocr_image(img)
        if ocr:
            all_texts.append(f"[OCR de {Path(img).name}]\n{ocr}")
        else:
            print(f"[AVISO] OCR vazio para {Path(img).name} — ignorado.", file=sys.stderr)

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
        "max_tokens": MAX_TOKENS,
    }

    try:
        resp = requests.post(
            cfg.get("OPENROUTER_ENDPOINT", "https://openrouter.ai/api/v1/chat/completions"),
            headers=headers, json=payload, timeout=TIMEOUT
        )
    except requests.exceptions.Timeout:
        raise RuntimeError(f"OpenRouter [{model}] timeout após {TIMEOUT}s")
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(f"OpenRouter [{model}] erro de rede: {e}")

    data = safe_json(resp)
    if resp.status_code != 200:
        raise RuntimeError(
            ("RATE_LIMIT: " if is_rate_limit(data) else "") +
            f"OpenRouter [{model}] HTTP {resp.status_code}: {str(data)[:200]}"
        )
    return extract_openrouter_text(data)


# ── Dispatcher ────────────────────────────────────────────────────────────────
CALLERS = {
    "gemini":     call_gemini,
    "openrouter": call_openrouter,
}


# ── Retry enxuto ─────────────────────────────────────────────────────────────
def try_once(provider: str, model: str, images: list, texts: list) -> str:
    caller = CALLERS.get(provider)
    if not caller:
        raise ValueError(f"Provedor desconhecido: '{provider}'. Use: gemini, openrouter.")
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return caller(model, images, texts)
        except RuntimeError as e:
            last_err = e
            print(f"[AVISO] tentativa {attempt}/{MAX_RETRIES}: {str(e)[:100]}", file=sys.stderr)
            if attempt < MAX_RETRIES:
                time.sleep(2)
    raise last_err


# ── Fallback enxuto ───────────────────────────────────────────────────────────
def send(primary_provider: str, primary_model: str, images: list, texts: list) -> str:
    """
    Ordem de tentativas (rápido e direto):
      1. primary_provider / primary_model
      2. Um modelo de fallback do mesmo provedor
      3. Provedor alternativo com seu primeiro modelo de fallback
    """
    fallback_map = {
        "gemini":     GEMINI_FALLBACK_MODELS,
        "openrouter": OPENROUTER_FALLBACK_MODELS,
    }

    # 1. Modelo solicitado
    try:
        return try_once(primary_provider, primary_model, images, texts)
    except Exception as e:
        print(f"[AVISO] {primary_provider}/{primary_model} falhou: {e}", file=sys.stderr)

    # 2. Primeiro fallback do mesmo provedor (não repetir o modelo já tentado)
    for fb_model in fallback_map.get(primary_provider, []):
        if fb_model == primary_model:
            continue
        print(f"[INFO] Fallback → {primary_provider}/{fb_model}", flush=True)
        try:
            return try_once(primary_provider, fb_model, images, texts)
        except Exception as e:
            print(f"[AVISO] {primary_provider}/{fb_model} falhou: {e}", file=sys.stderr)
        break  # tenta só 1 fallback no mesmo provedor

    # 3. Provedor alternativo (apenas o primeiro modelo)
    alt = "openrouter" if primary_provider == "gemini" else "gemini"
    alt_model = fallback_map.get(alt, [""])[0]
    if alt_model:
        print(f"[INFO] Fallback final → {alt}/{alt_model}", flush=True)
        try:
            return try_once(alt, alt_model, images, texts)
        except Exception as e:
            print(f"[AVISO] {alt}/{alt_model} falhou: {e}", file=sys.stderr)

    raise RuntimeError("Todos os provedores falharam.")


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

    pil_status = "sim" if HAS_PIL else "nao (pip install pillow)"
    print(f"[INFO] Provider  : {args.provider.upper()}", flush=True)
    print(f"[INFO] Model     : {args.model}", flush=True)
    print(f"[INFO] Images    : {len(args.image)}", flush=True)
    print(f"[INFO] Texts     : {len(args.text)}", flush=True)
    print(f"[INFO] Pillow    : {pil_status}", flush=True)
    print(f"[INFO] Timeout   : {TIMEOUT}s  |  Max retries: {MAX_RETRIES}", flush=True)

    t0 = time.time()
    try:
        response = send(args.provider, args.model, args.image, args.text)
        elapsed = time.time() - t0
        print(f"[INFO] Response time: {elapsed:.1f}s", flush=True)
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