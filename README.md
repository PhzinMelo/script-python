# Script Cola 📋

Capture a tela do seu dispositivo Android, acumule prints e envie tudo de uma vez para uma IA — direto do terminal, sem abrir navegador ou copiar nada manualmente.

---

## Como funciona

1. Abra um terminal e rode `python3 daemon.py`
2. Use os atalhos de teclado para acumular capturas
3. Ao finalizar, pressione **Shift+V** para enviar tudo à IA
4. A resposta aparece no mesmo terminal

---

## Atalhos

| Atalho    | Ação                                              |
|-----------|---------------------------------------------------|
| `Shift+Z` | **Nova sessão** — limpa todas as capturas         |
| `Shift+X` | **Capturar imagem** — salva screenshot numerado   |
| `Shift+C` | **Capturar OCR** — extrai texto da tela           |
| `Shift+V` | **Enviar para IA** — manda tudo acumulado         |
| `Esc`     | Encerrar o daemon                                 |

### Exemplo de uso

```
[terminal]
$ python3 daemon.py

# Na tela do celular aparece algo que você quer analisar:
Shift+Z   →  nova sessão
Shift+X   →  captura a tela como imagem
Shift+C   →  captura a tela e extrai o texto
Shift+X   →  captura mais uma tela como imagem
Shift+V   →  envia as 2 imagens + 1 texto para a IA

RESPOSTA DA IA:
────────────────────────────────────────────────────────────
[resposta aparece aqui]
────────────────────────────────────────────────────────────
```

---

## Instalação

### 1. ADB

```bash
sudo apt install adb
```

Conecte o dispositivo via USB e habilite **Depuração USB** nas opções de desenvolvedor. Verifique:

```bash
adb devices
```

### 2. Tesseract OCR

```bash
sudo apt install tesseract-ocr tesseract-ocr-por
```

### 3. Python e dependências

```bash
sudo apt install python3 python3-pip
pip install requests pynput
```

---

## Configuração

Crie o arquivo `config.env` na mesma pasta dos scripts:

```env
# Provedor padrão: gemini | copilot
PROVIDER=gemini

# Modelo do Gemini — altere aqui sem precisar editar o código
MODEL=gemini-flash-latest

# Chave da API do Gemini (https://aistudio.google.com/app/apikey)
GEMINI_API_KEY=SUA_CHAVE_AQUI

# Chave da API do OpenAI/Copilot (https://platform.openai.com/api-keys)
COPILOT_API_KEY=SUA_CHAVE_AQUI
```

> ⚠️ **Não suba o `config.env` para repositórios públicos.** Adicione ao `.gitignore`:
> ```
> config.env
> *.png
> *.txt
> ```

---

## Estrutura de arquivos

```
script-cola/
├── daemon.py       ← rodar este para iniciar
├── capture.sh      ← chamado automaticamente pelo daemon
├── send_to_ai.py   ← chamado automaticamente no Shift+V
├── config.env      ← suas chaves e configurações
└── README.md
```

Arquivos gerados automaticamente durante o uso:

```
screenshot1.png, screenshot2.png…  ← capturas de tela
ocr1.txt, ocr2.txt…                ← textos extraídos
```

---

## Provedores suportados

| Recurso         | Gemini | Copilot (OpenAI) |
|-----------------|--------|------------------|
| Envio de imagem | ✅     | ❌               |
| Envio de texto  | ✅     | ✅               |
| Fallback auto   | ✅     | ✅               |

Se o Gemini falhar, o sistema tenta automaticamente o Copilot (com retry de até 3×).
Se houver apenas imagens sem texto OCR, o Copilot é ignorado no fallback.

---

## Iniciando

```bash
chmod +x capture.sh
python3 daemon.py
```