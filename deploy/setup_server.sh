#!/usr/bin/env bash
# Prepara un VPS Ubuntu 24.04 recién creado para servir la web. Se ejecuta UNA
# vez, como root, en el servidor:
#
#   curl -fsSL https://raw.githubusercontent.com/JajamesVid/dataFantasyWeb/article_creation/deploy/setup_server.sh -o setup_server.sh
#   bash setup_server.sh
#
# Es idempotente: se puede relanzar sin romper nada (p. ej. para refrescar los
# rangos de IP de Cloudflare). Ver deploy/DEPLOY.md para el proceso completo.
set -euo pipefail

REPO_URL="https://github.com/JajamesVid/dataFantasyWeb.git"
BRANCH="${BRANCH:-article_creation}"
BASE=/srv/datafantasy
APP="$BASE/dataFantasyWeb"
CONTENT="$BASE/content"

[ "$(id -u)" -eq 0 ] || { echo "Ejecuta como root"; exit 1; }

echo "==> Paquetes y actualizaciones automáticas de seguridad"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get -y upgrade
DEBIAN_FRONTEND=noninteractive apt-get -y install \
    git python3-venv ufw fail2ban unattended-upgrades curl \
    debian-keyring debian-archive-keyring apt-transport-https gnupg
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "==> Caddy (repositorio oficial)"
if ! command -v caddy >/dev/null; then
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update
    apt-get -y install caddy
fi

echo "==> SSH: solo con clave"
if [ -s /root/.ssh/authorized_keys ]; then
    cat > /etc/ssh/sshd_config.d/10-datafantasy.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
EOF
    systemctl reload ssh
else
    echo "   (sin /root/.ssh/authorized_keys: NO se desactiva la contraseña para no dejarte fuera)"
fi

echo "==> Usuario y código"
id datafantasy >/dev/null 2>&1 || useradd --system --home "$BASE" --shell /usr/sbin/nologin datafantasy
mkdir -p "$BASE" "$CONTENT/articles_img"
chown datafantasy:datafantasy "$BASE" "$CONTENT" "$CONTENT/articles_img"
if [ ! -d "$APP/.git" ]; then
    sudo -u datafantasy git clone --branch "$BRANCH" "$REPO_URL" "$APP"
fi
sudo -u datafantasy python3 -m venv "$APP/venv"
sudo -u datafantasy "$APP/venv/bin/pip" install -q --upgrade pip
sudo -u datafantasy "$APP/venv/bin/pip" install -q -r "$APP/requirements.txt"

# Contenido inicial: solo si aún no existe (nunca pisa lo publicado en el servidor)
for f in articles.json analytics.json; do
    [ -f "$CONTENT/$f" ] || sudo -u datafantasy cp "$APP/data/$f" "$CONTENT/$f"
done
sudo -u datafantasy cp -n "$APP"/static/img/articles/* "$CONTENT/articles_img/" 2>/dev/null || true

if [ ! -f "$APP/.env" ]; then
    install -o datafantasy -g datafantasy -m 600 /dev/null "$APP/.env"
    echo "   Creado $APP/.env vacío: rellénalo (ver DEPLOY.md, paso 4)"
fi

echo "==> Servicio de la web"
cp "$APP/deploy/datafantasy-web.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable datafantasy-web

echo "==> Rangos de Cloudflare (firewall y Caddy)"
CF_IPS="$(curl -fsSL https://www.cloudflare.com/ips-v4) $(curl -fsSL https://www.cloudflare.com/ips-v6)"
echo "trusted_proxies static $(echo $CF_IPS)" > /etc/caddy/cloudflare-ips.caddy

ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
for ip in $CF_IPS; do
    ufw allow proto tcp from "$ip" to any port 443 comment cloudflare >/dev/null
done
ufw --force enable

echo "==> Caddy"
mkdir -p /etc/caddy/certs /var/log/caddy
chown caddy:caddy /var/log/caddy
cp "$APP/deploy/Caddyfile" /etc/caddy/Caddyfile
if [ -f /etc/caddy/certs/origin.pem ] && [ -f /etc/caddy/certs/origin.key ]; then
    chown root:caddy /etc/caddy/certs/origin.key && chmod 640 /etc/caddy/certs/origin.key
    caddy validate --config /etc/caddy/Caddyfile
    systemctl reload caddy || systemctl restart caddy
else
    echo "   Falta el certificado de origen en /etc/caddy/certs/ (DEPLOY.md, paso 3)."
    echo "   Cuando lo pongas, relanza este script."
fi

echo "==> Copia diaria del contenido (14 días)"
cat > /etc/systemd/system/datafantasy-backup.service <<EOF
[Unit]
Description=Copia del contenido de DataFantasy

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'mkdir -p $BASE/backups && tar czf $BASE/backups/content-\$(date +%%F).tar.gz -C $BASE content && find $BASE/backups -name "content-*.tar.gz" -mtime +14 -delete'
EOF
cat > /etc/systemd/system/datafantasy-backup.timer <<'EOF'
[Unit]
Description=Copia diaria del contenido de DataFantasy

[Timer]
OnCalendar=*-*-* 04:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now datafantasy-backup.timer

echo
echo "Listo. Si .env ya está relleno: systemctl restart datafantasy-web"
