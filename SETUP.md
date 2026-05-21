# Setup (Windows)

## 1) Baixar o repositório

```powershell
git clone https://github.com/ViniciusNoetzold/MezzoldConnect.git
cd MezzoldConnect
```

## 2) Criar ambiente virtual Python (venv)

```powershell
python -m venv .venv
```

## 3) Ativar a venv no PowerShell

```powershell
.\.venv\Scripts\Activate.ps1
```

## 4) Instalar dependências

```powershell
pip install -r requirements.txt
```

## 5) Rodar o app desktop principal

```powershell
python main.py
```

## 6) Rodar testes com unittest

```powershell
python -m unittest discover -s tests -p "test*.py"
```

## 7) Validar compilação de módulos Python

```powershell
python -m compileall .
```

## 8) Gerar build no Windows

```powershell
.\build.ps1
```

Executável gerado:

```text
dist\Mezzold Connect.exe
```

## Observação sobre Node/TypeScript

Este repositório também contém um serviço separado em Node/TypeScript (pasta `src/` e arquivo `README.node-service.md`) para rotinas de aquecimento/serviço backend.

Esse serviço é opcional e não é necessário para rodar o app desktop principal em Python (`python main.py`).