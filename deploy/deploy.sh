#!/usr/bin/env bash
# Publica en el servidor lo que haya en GitHub. Se ejecuta en tu equipo:
#
#   deploy/deploy.sh
#
# Requiere el alias `datafantasy` en ~/.ssh/config (ver DEPLOY.md) o
# DEPLOY_HOST=root@<ip> deploy/deploy.sh
set -euo pipefail

HOST="${DEPLOY_HOST:-datafantasy}"
APP=/srv/datafantasy/dataFantasyWeb

cd "$(dirname "$0")/.."
git fetch -q
if [ -n "$(git log '@{u}..' 2>/dev/null)" ]; then
    echo "Tienes commits sin subir: el servidor se baja lo que hay en GitHub. Haz git push primero."
    exit 1
fi

ssh "$HOST" bash -s <<EOF
set -euo pipefail
sudo -u datafantasy git -C $APP pull --ff-only
sudo -u datafantasy $APP/venv/bin/pip install -q -r $APP/requirements.txt
cp $APP/deploy/datafantasy-web.service /etc/systemd/system/
systemctl daemon-reload
systemctl restart datafantasy-web
sleep 2
systemctl is-active datafantasy-web
EOF

code=$(curl -s -o /dev/null -w '%{http_code}' https://datafantasylab.com/)
echo "https://datafantasylab.com/ -> $code"
[ "$code" = 200 ]
