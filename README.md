# 📱 Android Screen AI — Automatize capturas e consultas à IA

Sistema que captura a tela do seu Android via ADB e envia para Gemini ou Copilot automaticamente.

---

## 🗂️ Arquivos

| Arquivo | Função |
|---|---|
| `capture.sh` | Script principal (captura + envia para IA) |
| `send_to_ai.py` | Comunicação com Gemini / Copilot |
| `config.env` | Chaves de API e provedor padrão |

---

## ⚡ Uso rápido

```bash
# Enviar screenshot como IMAGEM para a IA (Gemini)
./capture.sh image

# Extrair texto via OCR e enviar para a IA
./capture.sh text
```

A resposta aparece diretamente no terminal, de forma limpa e objetiva.

---

## 🔧 Instalação de dependências

### 1. ADB e scrcpy

```bash
sudo apt update
sudo apt install adb scrcpy
```

Habilite a **Depuração USB** 
- Configurações → Sobre o telefone → toque 7x em "Número da versão"
- Configurações → Opções do desenvolvedor → Depuração USB: ativado

Conecte o cabo e confirme o par de RSA no celular. Teste com:

```bash
adb devices
```

### 2. Tesseract OCR

```bash
sudo apt install tesseract-ocr tesseract-ocr-por tesseract-ocr-eng
```

### 3. Python 3 e dependências

```bash
sudo apt install python3 python3-pip
pip install requests
```

### 4. Torne o script executável

```bash
chmod +x capture.sh
```

### 5. Configure suas chaves de API

Edite o `config.env`:

```bash
GEMINI_API_KEY="sua-chave-aqui"
COPILOT_API_KEY="sua-chave-aqui"
PROVIDER="gemini"   # ou "copilot"
```

- **Gemini API Key**: https://aistudio.google.com/app/apikey
- **Copilot/OpenAI Key**: https://platform.openai.com/api-keys

---

## 🤖 Comportamento do sistema

### Modos de captura

| Comando | O que faz |
|---|---|
| `./capture.sh image` | Captura PNG → envia imagem para Gemini → exibe resposta |
| `./capture.sh text` | Captura PNG → OCR → envia texto para Gemini ou Copilot → exibe resposta |

### Suporte por provedor

| Recurso | Gemini | Copilot |
|---|---|---|
| Envio de imagem | ✅ | ❌ |
| Envio de texto (OCR) | ✅ | ✅ |
| Fallback automático | ✅ | ✅ |

> **Nota:** Se você usar `./capture.sh image` com `PROVIDER=copilot`, o sistema converte automaticamente para OCR antes de enviar.

### Fallback automático

1. OCR retorna vazio + provedor é Gemini → envia a imagem diretamente.
2. Provedor principal falha (erro de API, quota, timeout) → tenta até **3x** com intervalo de **5s**.
3. Se ainda falhar, troca automaticamente para o outro provedor.

### Saída normalizada

Independente do formato JSON retornado pela API, o script extrai apenas o texto e imprime de forma limpa:

```
────────────────────────────────────────────────────────────
RESPOSTA DA IA:
────────────────────────────────────────────────────────────
[texto da IA aqui]
────────────────────────────────────────────────────────────
```

### Respostas concisas

O prompt enviado instrui a IA a ser **objetiva e direta**, sem repetir a pergunta ou adicionar rodeios desnecessários.

---

## 🖥️ Transmissão da tela com scrcpy

Para espelhar a tela enquanto usa o sistema:

```bash
scrcpy &
```

Você pode usar as capturas `./capture.sh` enquanto o scrcpy exibe a tela em tempo real.

---

## 🛠️ Problemas comuns

| Problema | Solução |
|---|---|
| `adb devices` não lista o celular | Reconecte o cabo, confirme a depuração USB no celular |
| Screenshot vazio | Desbloqueie a tela do celular antes de capturar |
| OCR retorna lixo | Ajuste o idioma: edite `capture.sh` e mude `-l por+eng` |
| Erro 401 na API | Verifique a chave em `config.env` |
| Erro 429 / quota | O sistema fará retry automático e trocará de provedor |