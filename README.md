# Installation & Dépendances

Ce projet utilise **`uv`** comme gestionnaire de paquets Python (plus rapide que `pip`) et nécessite **Python 3.10+**.

---

## Prérequis

- Python 3.10 ou supérieur
- Une clé API **Anthropic** (pour le client)

---

## 1. Installer `uv`

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

Redémarre ton terminal après l’installation pour que uv soit disponible.

## 2. Dépendances du **serveur météo** (`weather-server-python/`)

Dans le dossier `weather-server-python/` :

```bash
uv add mcp httpx

## 3. Dépendances du **client MCP** (`mcp-client-python/`)

Dans le dossier `mcp-client-python/` :

```bash
uv add mcp anthropic python-dotenv

## 4. Clé API

Crée un fichier `.env` dans `mcp-client-python/` :

```env
API_KEY=

Ajoute .env à ton .gitignore :
bashecho ".env" >> .gitignore