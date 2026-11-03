# Deploy de datafantasylab.com

```
visitante ──HTTPS──> Cloudflare ──HTTPS (cert. de origen)──> VPS: Caddy :443 ──> gunicorn 127.0.0.1:8000 (app.py)
                     (DNS, anti-DDoS,                          firewall: 443 solo desde Cloudflare, 22 con clave
                      Access en /panel)
```

- **El pipeline sigue en tu equipo** (timer martes/viernes): escribe en Supabase y la
  web del servidor lo lee. La caché de la web dura 15 min, así que los datos nuevos
  aparecen solos como mucho 15 min después de que termine el pipeline.
- **Los artículos, sus imágenes y las visitas viven en el servidor**, en
  `/srv/datafantasy/content/`, fuera del repo, para que `git pull` no los pise. Lo
  que escribas en el panel publicado no está en git: de eso se encargan las copias
  diarias (paso 7).

## Antes de empezar (obligatorio)

1. **Clave publicable de Supabase.** Ejecuta `DataFantasy/BBDD/03_politicas_lectura_web.sql`
   en Supabase > SQL Editor. Después usa la clave `sb_publishable_...` (Settings > API) en
   el `.env` del servidor. La secreta **nunca** sale de tu equipo.
2. **Contraseña de admin nueva**, porque la actual ha pasado por el chat. Genera el
   hash con `python scripts/generate_admin_hash.py`.
3. Haz commit y `git push` de dataFantasyWeb: el servidor se baja el código de GitHub.

## 1. Crear el VPS

En Hetzner Cloud: **CX22, Ubuntu 24.04**, unos 4–5 €/mes. Cualquier proveedor sirve.

- Si no tienes clave SSH, créala en tu equipo con `ssh-keygen -t ed25519` y añade
  `~/.ssh/id_ed25519.pub` al crear el servidor.
- Apunta la IP y añade a `~/.ssh/config` de tu equipo:

  ```
  Host datafantasy
      HostName <IP_DEL_VPS>
      User root
      IdentityFile ~/.ssh/id_ed25519
  ```

## 2. Cloudflare y el dominio

1. Crea una cuenta en Cloudflare (plan Free), pulsa *Add a site* y escribe
   `datafantasylab.com`. En tu registrador, cambia los nameservers por los dos que
   te indique Cloudflare. Se activa en minutos o en unas horas.
2. **DNS**, ambos con la nube naranja (*Proxied*):
   - `A` `@` → `<IP_DEL_VPS>`
   - `CNAME` `www` → `datafantasylab.com`
3. **SSL/TLS > Overview**: modo **Full (strict)**.
4. **SSL/TLS > Edge Certificates**: activa *Always Use HTTPS*, *Minimum TLS 1.2* y
   (más adelante, cuando todo funcione) *HSTS*.
5. **Security > Bots**: activa *Bot Fight Mode*.

## 3. Certificado de origen

En **SSL/TLS > Origin Server > Create Certificate**, deja RSA, los hostnames
`*.datafantasylab.com, datafantasylab.com` y 15 años. En el servidor:

```bash
ssh datafantasy
mkdir -p /etc/caddy/certs
nano /etc/caddy/certs/origin.pem   # pega el "Origin Certificate"
nano /etc/caddy/certs/origin.key   # pega la "Private Key" (solo se muestra una vez)
```

## 4. Preparar el servidor

```bash
ssh datafantasy
curl -fsSL https://raw.githubusercontent.com/JajamesVid/dataFantasyWeb/article_creation/deploy/setup_server.sh -o setup_server.sh
bash setup_server.sh
nano /srv/datafantasy/dataFantasyWeb/.env
```

Contenido del `.env` del servidor. Usa valores **nuevos**: no copies el `.env` de tu
equipo, que lleva la clave secreta.

```
SITE_BASE_URL=https://datafantasylab.com
SUPABASE_URL=https://<proyecto>.supabase.co
SUPABASE_KEY=sb_publishable_...
SUPABASE_TEMPORADA=26/27
SUPABASE_STAGING_TEMPORADAS=
FLASK_SECRET_KEY=<python3 -c "import secrets; print(secrets.token_hex(32))">
ADMIN_USERNAME=<usuario>
ADMIN_PASSWORD_HASH='<hash nuevo, entre comillas simples>'
# TWITTER_*=... si vas a tuitear desde el panel publicado
```

Arranca la web:

```bash
systemctl restart datafantasy-web
systemctl status datafantasy-web caddy
```

`SITE_BASE_URL` con `https://` activa la cookie *Secure* y HSTS.

## 5. Proteger /panel con Cloudflare Access

En **Zero Trust > Access > Applications > Add an application > Self-hosted**:

- Dominio `datafantasylab.com` con ruta `panel`. Añade también `panel/*` si el
  formulario lo separa.
- Política *Allow*, regla *Emails*: tu correo y el de Miguel.
- Método de login: *One-time PIN*, un código por email.

Con esto nadie de fuera llega siquiera al formulario de login. El usuario y la
contraseña de la app siguen funcionando como segunda barrera.

## 6. Comprobar

Desde tu equipo:

```bash
curl -sI https://datafantasylab.com/ | grep -iE "^HTTP|content-security|x-frame|strict-transport"
curl -sI https://datafantasylab.com/panel/login | head -1   # 302 hacia cloudflareaccess.com
curl -m 5 -k https://<IP_DEL_VPS>/                          # debe fallar (timeout): solo Cloudflare entra
```

Abre la web, un equipo, un jugador y un artículo, y entra al panel por el PIN.

## 7. Día a día

- **Publicar cambios de código:** `git push` y luego `deploy/deploy.sh` desde
  `dataFantasyWeb/`. El script se niega a publicar si tienes commits sin subir.
- **Logs:** `ssh datafantasy journalctl -u datafantasy-web -f`
- **Copias:** cada día a las 04:00 se guarda `/srv/datafantasy/backups/content-FECHA.tar.gz`
  (se conservan 14 días). Para tener otra copia fuera del servidor, tráetelas de vez en
  cuando con:
  `rsync -a datafantasy:/srv/datafantasy/backups/ ~/backups/datafantasy/`
- **Rangos de Cloudflare:** cambian muy de vez en cuando. Si un día la web da 52x,
  relanza `bash setup_server.sh`, que los refresca.
- **La web local** (`localhost:5000`) sigue funcionando como hasta ahora, con
  `data/` y `static/img/articles` del repo. Los artículos de verdad pasan a ser los
  del servidor.
