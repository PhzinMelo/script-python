# Script Cola 📋

Ferramenta de terminal que captura a tela do seu Android, envia para uma IA e mostra a resposta — tudo sem sair do terminal.

---

## Requisitos

- Python 3.10+
- ADB instalado e no PATH
- Tesseract OCR instalado
- Dependências Python:

```
pip install pynput requests pillow
```

---

## Instalação

### Windows

```
pip install pynput requests pillow
```

- ADB: baixe o [Platform Tools](https://developer.android.com/tools/releases/platform-tools) e adicione ao PATH
- Tesseract: baixe em [UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki), marque o idioma **Portuguese** e adicione ao PATH

### Linux

```bash
sudo apt install adb tesseract-ocr tesseract-ocr-por
pip install pynput requests pillow
chmod +x capture.sh
```

---

## Configuração

Preencha o arquivo `config.env` com suas chaves de API e o provedor desejado.

> Não versione o `config.env`. Adicione ao `.gitignore`.

---

## Como usar

Conecte o dispositivo Android via USB com **Depuração USB** ativada e verifique:

```
adb devices
```

Inicie o daemon:

```
python daemon.py
```

---

## Atalhos

| Atalho    | Ação                            |
|-----------|---------------------------------|
| `Shift+Z` | Nova sessão                     |
| `Shift+X` | Capturar tela como imagem       |
| `Shift+C` | Capturar tela com OCR           |
| `Shift+V` | Enviar capturas para a IA       |
| `Shift+A` | Alternar provedor               |
| `Shift+M` | Alternar modelo                 |
| `Esc`     | Encerrar                        |

---

## Estrutura

```
script-cola/
├── daemon.py
├── send_to_ai.py
├── capture.bat        ← Windows
├── capture.sh         ← Linux
├── config.env
└── screenshots/
```

---

## Compatibilidade

| Sistema | Suporte  |
|---------|----------|
| Windows | ✅       |
| Linux   | ✅       |
| WSL     | Parcial* |

*WSL pode exigir configuração adicional de USB.