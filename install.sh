#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "Listo. Para activar el entorno virtual usa:"
echo "  source venv/bin/activate"
echo "Para arrancar la app:"
echo "  python app.py"
