#!/usr/bin/env bash
# WaveBook backend deployment script (VPS / Ubuntu)
# Usage: bash deploy.sh
# Installs dependencies into a venv and starts the FastAPI server on port 8000.
set -euo pipefail

cd "$(dirname "$0")"

echo "==> Creating virtualenv (if missing)"
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate

echo "==> Installing dependencies"
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Ensuring uploads directory exists"
mkdir -p uploads

echo "==> Starting WaveBook backend on 0.0.0.0:8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
