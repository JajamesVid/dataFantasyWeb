import json
import os
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import date
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask, abort, flash, g, redirect, render_template, request, send_from_directory, session, url_for,
)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

import supabase_data
from twitter_post import post_tweet_for_article

load_dotenv()

app = Flask(__name__)
# Sin FLASK_SECRET_KEY se genera una al arrancar (las sesiones se pierden al
# reiniciar): nunca una fija en el código, que es público.
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # solo por HTTPS cuando la web se sirva con HTTPS (en local es http)
    SESSION_COOKIE_SECURE=os.environ.get("SITE_BASE_URL", "").startswith("https://"),
    MAX_CONTENT_LENGTH=10 * 1024 * 1024,  # subidas de imágenes del panel
)

# En el servidor la web va detrás de Caddy (que a su vez está detrás de
# Cloudflare): sin esto request.remote_addr sería siempre 127.0.0.1 y el
# límite de intentos de login bloquearía a todo el mundo a la vez. Caddy
# reescribe X-Forwarded-For con la IP real, así que basta con fiarse de 1 salto.
if os.environ.get("BEHIND_PROXY") == "1":
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: blob: https:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


@app.after_request
def security_headers(response):
    response.headers.setdefault("Content-Security-Policy", CSP)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if app.config["SESSION_COOKIE_SECURE"]:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    if request.path.startswith("/panel"):
        response.headers["Cache-Control"] = "no-store"
    return response

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH")
SUPABASE_TEMPORADA = os.environ.get("SUPABASE_TEMPORADA", "25/26")

# Temporadas que el visitante puede elegir en el selector de la nav. La URL usa el
# slug (sin barra, más limpio en un query string); Supabase usa el valor "db" tal cual
# está guardado en la columna `temporada`. Con una sola opción el selector no se muestra.
TEMPORADA_OPTIONS = [
    {"slug": "26-27", "label": "2026/27", "db": "26/27"},
]
TEMPORADA_BY_SLUG = {t["slug"]: t["db"] for t in TEMPORADA_OPTIONS}
TEMPORADA_SLUG_BY_DB = {t["db"]: t["slug"] for t in TEMPORADA_OPTIONS}

DATA = Path(__file__).parent / "data"
# Lo que se escribe desde la web (artículos, sus imágenes y las visitas). En el
# servidor CONTENT_DIR apunta fuera del repo para que `git pull` no lo pise; en
# local, sin CONTENT_DIR, sigue en data/ y static/img/articles como siempre.
CONTENT_DIR = Path(os.environ["CONTENT_DIR"]) if os.environ.get("CONTENT_DIR") else None
CONTENT = CONTENT_DIR or DATA
ARTICLES_IMG = CONTENT_DIR / "articles_img" if CONTENT_DIR else Path(__file__).parent / "static" / "img" / "articles"
BADGES_DIR = Path(__file__).parent / "static" / "img" / "escudos"
PLAYERS_DIR = Path(__file__).parent / "static" / "img" / "jugadores"
ALLOWED_IMAGE_EXT = {"jpg", "jpeg", "png", "webp", "gif"}
BADGE_EXTENSIONS = ("webp", "png", "svg", "jpg", "jpeg")
TAGS = ["Jornada", "Análisis", "Mercado"]


def load_json(filename, folder=DATA):
    with open(folder / filename, encoding="utf-8") as f:
        return json.load(f)


def save_json(filename, data):
    """Escribe en un temporal y lo renombra: un lector nunca ve el fichero a medias."""
    tmp = CONTENT / f".{filename}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, CONTENT / filename)


def load_all_articles():
    return load_json("articles.json", CONTENT)


def save_all_articles(articles):
    save_json("articles.json", articles)


def load_articles():
    published = [a for a in load_all_articles() if a.get("status") == "published"]
    return sorted(published, key=lambda a: a["date"], reverse=True)


def load_teams():
    return load_json("teams.json")


def load_analytics():
    return load_json("analytics.json", CONTENT)


# gunicorn atiende con varios hilos: sin el lock, dos visitas a la vez leen el
# mismo contador y una de las dos se pierde.
_analytics_lock = threading.Lock()


def update_analytics(change):
    with _analytics_lock:
        analytics = load_analytics()
        change(analytics)
        save_json("analytics.json", analytics)


# Protección CSRF: todo POST debe traer el token de la sesión en el campo _csrf
# (los formularios lo incluyen con {{ csrf_token() }}). Sin esto, una web ajena
# podría publicar o borrar artículos usando la sesión abierta del admin.
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def check_csrf():
    if request.method == "POST":
        token = request.form.get("_csrf", "")
        if not token or not secrets.compare_digest(token, session.get("_csrf", "")):
            abort(400)


# Límite de intentos de login por IP (en memoria: la web corre en un solo proceso).
LOGIN_MAX_FALLOS = 5
LOGIN_VENTANA_SEGUNDOS = 15 * 60
_login_fallos = defaultdict(deque)


def login_bloqueado(ip):
    fallos = _login_fallos[ip]
    while fallos and time.time() - fallos[0] > LOGIN_VENTANA_SEGUNDOS:
        fallos.popleft()
    return len(fallos) >= LOGIN_MAX_FALLOS


def safe_next_url(next_url):
    """Solo rutas internas: si no, el login serviría para redirigir a una web ajena."""
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return url_for("admin_articles")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


MESES_ABREV = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


# Visitas por comunidad autónoma. La región la pone Cloudflare en cabeceras
# (CF-IPCountry siempre; cf-region-code con el Managed Transform "Add visitor
# location headers"): la web nunca guarda IPs, solo el contador agregado.
COMUNIDADES = {
    "AN": "Andalucía", "AR": "Aragón", "AS": "Asturias", "IB": "Baleares",
    "CN": "Canarias", "CB": "Cantabria", "CL": "Castilla y León", "CM": "Castilla-La Mancha",
    "CT": "Cataluña", "VC": "Comunidad Valenciana", "EX": "Extremadura", "GA": "Galicia",
    "MD": "Madrid", "MC": "Murcia", "NC": "Navarra", "PV": "País Vasco", "RI": "La Rioja",
    "CE": "Ceuta", "ML": "Melilla",
}
# Por si Cloudflare da la provincia (ISO 3166-2 de 2º nivel) en vez de la comunidad.
PROVINCIA_A_COMUNIDAD = {
    "AL": "AN", "CA": "AN", "CO": "AN", "GR": "AN", "H": "AN", "J": "AN", "MA": "AN", "SE": "AN",
    "HU": "AR", "TE": "AR", "Z": "AR", "O": "AS", "PM": "IB", "GC": "CN", "TF": "CN", "S": "CB",
    "AV": "CL", "BU": "CL", "LE": "CL", "P": "CL", "SA": "CL", "SG": "CL", "SO": "CL", "VA": "CL",
    "ZA": "CL", "AB": "CM", "CR": "CM", "CU": "CM", "GU": "CM", "TO": "CM",
    "B": "CT", "GI": "CT", "L": "CT", "T": "CT", "A": "VC", "CS": "VC", "V": "VC",
    "BA": "EX", "CC": "EX", "C": "GA", "LU": "GA", "OR": "GA", "PO": "GA", "M": "MD", "MU": "MC",
    "NA": "NC", "BI": "PV", "SS": "PV", "VI": "PV", "LO": "RI",
}
REGION_INTERNACIONAL = "INT"
REGION_ESPANA_SIN_DATO = "ES"
REGION_DESCONOCIDA = "ND"
REGION_LABELS = {
    **COMUNIDADES,
    REGION_INTERNACIONAL: "Internacional",
    REGION_ESPANA_SIN_DATO: "España (sin región)",
    REGION_DESCONOCIDA: "Sin datos",
}


def visitor_region():
    """Código de comunidad, 'INT' fuera de España, 'ES' o 'ND' si falta el dato.

    Solo se fía de las cabeceras detrás de Cloudflare: en local cualquiera podría
    mandarlas (y en local no hay ubicación que sacar).
    """
    if os.environ.get("BEHIND_PROXY") != "1":
        return REGION_DESCONOCIDA
    country = request.headers.get("CF-IPCountry", "").upper()
    if not country or country in ("XX", "T1"):  # desconocido / Tor
        return REGION_DESCONOCIDA
    if country != "ES":
        return REGION_INTERNACIONAL
    code = request.headers.get("cf-region-code", "").upper()
    if code.startswith("ES-"):
        code = code[3:]
    code = PROVINCIA_A_COMUNIDAD.get(code, code)
    return code if code in COMUNIDADES else REGION_ESPANA_SIN_DATO


def month_label(month_key):
    """'2026-08' -> 'ago 2026'."""
    year, month = month_key.split("-")
    return f"{MESES_ABREV[int(month) - 1]} {year}"


@app.before_request
def track_visit():
    if request.path.startswith(("/panel", "/static", "/media")):
        return
    def count(analytics):
        analytics["total_visits"] = analytics.get("total_visits", 0) + 1
        month_key = date.today().strftime("%Y-%m")
        monthly_visits = analytics.setdefault("monthly_visits", {})
        monthly_visits[month_key] = monthly_visits.get(month_key, 0) + 1
        region_visits = analytics.setdefault("region_visits", {})
        region_visits[region] = region_visits.get(region, 0) + 1

    region = visitor_region()
    update_analytics(count)


@app.before_request
def resolve_temporada():
    """Which temporada to show, picked via ?temporada=<slug> (see TEMPORADA_OPTIONS).

    Defaults to SUPABASE_TEMPORADA (the env-configured season) when missing or
    unrecognised, so a bad/old query string can never point at a season that
    doesn't exist.
    """
    slug = request.args.get("temporada")
    g.temporada = TEMPORADA_BY_SLUG.get(slug, SUPABASE_TEMPORADA)
    g.temporada_slug = TEMPORADA_SLUG_BY_DB.get(g.temporada, TEMPORADA_SLUG_BY_DB[SUPABASE_TEMPORADA])


@app.context_processor
def inject_temporada_context():
    return {
        "temporada_options": TEMPORADA_OPTIONS,
        "current_temporada_slug": g.get("temporada_slug", TEMPORADA_SLUG_BY_DB[SUPABASE_TEMPORADA]),
    }


@app.url_defaults
def inject_temporada(endpoint, values):
    """Makes every url_for() inside a request keep the current ?temporada=... —
    so switching season and then clicking around the site doesn't silently reset
    to the default one. Left off entirely for the default season, so ordinary
    URLs are unaffected (no query string noise) unless a non-default season is active.
    """
    if endpoint == "static" or "temporada" in values:
        return
    if g.get("temporada") and g.temporada != SUPABASE_TEMPORADA:
        values["temporada"] = g.temporada_slug


def team_badge_url(slug):
    """Look up a team crest in static/img/escudos/<slug>.<ext>, if one has been uploaded."""
    for ext in BADGE_EXTENSIONS:
        if (BADGES_DIR / f"{slug}.{ext}").exists():
            return url_for("static", filename=f"img/escudos/{slug}.{ext}")
    return None


def player_photo_url(jugador_id):
    """Look up a player photo in static/img/jugadores/<jugador_id>.<ext>.

    No real photo source is wired up yet, so this is a placeholder hook: templates
    fall back to an initials avatar when it returns None, same as team_badge_url.
    """
    for ext in BADGE_EXTENSIONS:
        if (PLAYERS_DIR / f"{jugador_id}.{ext}").exists():
            return url_for("static", filename=f"img/jugadores/{jugador_id}.{ext}")
    return None


def load_team_matchday_snapshot():
    data = supabase_data.build_team_matchday_snapshot(g.temporada)
    real_slugs = {t["slug"] for t in load_teams()}
    for team in data["teams"]:
        team["badge"] = team_badge_url(team["slug"])
        team["has_page"] = team["slug"] in real_slugs
    return data


def load_player_radar():
    data = supabase_data.build_player_radar(g.temporada)
    for player in data["players"]:
        player["team_badge"] = team_badge_url(player["team_slug"])
        player["photo"] = player["photo_url"] or player_photo_url(player.get("jugador_id"))
    return data


def load_position_breakdown():
    return supabase_data.build_position_points_breakdown(g.temporada)


def load_team_evolution(slug):
    """A single team's Fantasy points per match, coloured by result (V/E/D), plus its
    league position and average points per result, for the strip on its own page.

    Not every team in teams.json has data for the configured temporada, so this
    returns None when there's nothing to plot.
    """
    data = supabase_data.build_team_evolution(slug, g.temporada)
    if data is None:
        return None
    return {**data, "badge": team_badge_url(slug)}


def load_team_player_stats(slug):
    """Not every team has a roster to draw from yet (see load_team_evolution), so this
    returns None when there's nothing to show.
    """
    return supabase_data.build_team_player_stats(slug, g.temporada)


def load_players():
    players = supabase_data.build_player_directory(g.temporada)
    real_slugs = {t["slug"] for t in load_teams()}
    for player in players:
        player["team_has_page"] = player["team_slug"] in real_slugs
        player["photo"] = player["photo_url"] or player_photo_url(player["jugador_id"])
    return players


def load_player(slug):
    player = supabase_data.build_player_detail(slug, g.temporada)
    if player is None:
        return None
    real_slugs = {t["slug"] for t in load_teams()}
    player["team_has_page"] = player["team_slug"] in real_slugs
    player["photo"] = player["photo_url"] or player_photo_url(player["jugador_id"])
    return player


@app.route("/media/articles/<path:filename>")
def article_image(filename):
    return send_from_directory(ARTICLES_IMG, filename)


def allowed_image(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXT


def save_uploaded_image(file_storage, prefix):
    if not file_storage or not file_storage.filename or not allowed_image(file_storage.filename):
        return None
    ext = secure_filename(file_storage.filename).rsplit(".", 1)[1].lower()
    filename = f"{prefix}-{uuid.uuid4().hex[:8]}.{ext}"
    ARTICLES_IMG.mkdir(parents=True, exist_ok=True)
    file_storage.save(ARTICLES_IMG / filename)
    return filename


def article_from_form(existing):
    """Build an article dict from the submitted admin form, reusing `existing` (or {}) as base."""
    article_id = existing.get("id")
    prefix = str(article_id) if article_id is not None else "new"

    cover_file = request.files.get("cover")
    cover = save_uploaded_image(cover_file, f"{prefix}-cover") or request.form.get("existing_cover") or None

    teams = request.form.getlist("teams")

    block_ids = [b for b in request.form.get("blocks_order", "").split(",") if b]
    body = []
    for bid in block_ids:
        block_type = request.form.get(f"block_type_{bid}")
        if block_type == "text":
            content = request.form.get(f"block_content_{bid}", "").strip()
            if content:
                body.append({"type": "text", "content": content})
        elif block_type == "image":
            image_file = request.files.get(f"block_image_{bid}")
            src = save_uploaded_image(image_file, f"{prefix}-block") or request.form.get(f"block_existing_{bid}") or None
            caption = request.form.get(f"block_caption_{bid}", "").strip()
            if src:
                body.append({"type": "image", "src": src, "caption": caption or None})

    return {
        "id": article_id,
        "title": request.form.get("title", "").strip(),
        "summary": request.form.get("summary", "").strip(),
        "date": request.form.get("date") or existing.get("date") or date.today().isoformat(),
        "tag": request.form.get("tag", TAGS[0]),
        "author": request.form.get("author", "DataFantasy").strip() or "DataFantasy",
        "teams": teams,
        "cover": cover,
        "body": body,
        "status": existing.get("status", "draft"),
    }


@app.route("/")
def index():
    return render_template(
        "index.html",
        articles=load_articles(),
        team_matchday=load_team_matchday_snapshot(),
        player_radar=load_player_radar(),
        position_breakdown=load_position_breakdown(),
    )


@app.route("/article/<int:article_id>")
def article(article_id):
    match = next((a for a in load_articles() if a["id"] == article_id), None)
    if match is None:
        abort(404)

    def count(analytics):
        article_visits = analytics.setdefault("article_visits", {})
        article_visits[str(article_id)] = article_visits.get(str(article_id), 0) + 1

    update_analytics(count)

    return render_template("article.html", article=match)


@app.route("/equipos")
def equipos():
    teams = load_teams()
    for team in teams:
        team["badge"] = team_badge_url(team["slug"])
    return render_template("equipos.html", teams=teams)


@app.route("/equipos/<slug>")
def equipo(slug):
    teams = load_teams()
    team = next((t for t in teams if t["slug"] == slug), None)
    if team is None:
        abort(404)
    team["badge"] = team_badge_url(slug)
    articles = [a for a in load_articles() if slug in a.get("teams", [])]
    player_stats = load_team_player_stats(slug)
    points_evolution = load_team_evolution(slug)
    return render_template(
        "equipo.html",
        team=team,
        articles=articles,
        player_stats=player_stats,
        points_evolution=points_evolution,
    )


@app.route("/puntuacion-datafantasy")
def puntuacion_datafantasy():
    return render_template("puntuacion_datafantasy.html")


@app.route("/jugadores")
def jugadores():
    return render_template("jugadores.html", players=load_players())


@app.route("/jugadores/<slug>")
def jugador(slug):
    player = load_player(slug)
    if player is None:
        abort(404)
    return render_template("jugador.html", player=player)


# ── Panel de administración (protegido con login) ───────────────────

@app.route("/panel/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        ip = request.remote_addr
        if login_bloqueado(ip):
            flash("Demasiados intentos fallidos. Espera 15 minutos y vuelve a probar.")
            return render_template("admin/login.html", next=request.form.get("next", "")), 429
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        valid_user = ADMIN_USERNAME is not None and secrets.compare_digest(username, ADMIN_USERNAME)
        valid_password = ADMIN_PASSWORD_HASH is not None and check_password_hash(ADMIN_PASSWORD_HASH, password)
        if valid_user and valid_password:
            _login_fallos.pop(ip, None)
            session.clear()
            session["admin_logged_in"] = True
            return redirect(safe_next_url(request.form.get("next")))
        _login_fallos[ip].append(time.time())
        flash("Usuario o contraseña incorrectos.")
    return render_template("admin/login.html", next=request.args.get("next", ""))


@app.route("/panel/logout", methods=["POST"])
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))


@app.route("/panel/analiticas")
@login_required
def admin_analytics():
    analytics = load_analytics()
    article_visits = analytics.get("article_visits", {})
    articles = [
        {**a, "visits": article_visits.get(str(a["id"]), 0)}
        for a in load_all_articles()
    ]
    articles.sort(key=lambda a: a["visits"], reverse=True)

    monthly_visits = analytics.get("monthly_visits", {})
    current_month_key = date.today().strftime("%Y-%m")
    sorted_months = sorted(monthly_visits)

    region_visits = analytics.get("region_visits", {})
    region_total = sum(region_visits.values())
    regions = sorted(
        (
            {
                "label": REGION_LABELS.get(code, code),
                "visits": n,
                "share": n / region_total if region_total else 0,
                "is_spain": code in COMUNIDADES,
            }
            for code, n in region_visits.items()
        ),
        key=lambda r: r["visits"],
        reverse=True,
    )

    return render_template(
        "admin/analytics.html",
        regions=regions,
        region_total=region_total,
        total_visits=analytics.get("total_visits", 0),
        current_month_visits=monthly_visits.get(current_month_key, 0),
        monthly_chart={
            "labels": [month_label(m) for m in sorted_months],
            "values": [monthly_visits[m] for m in sorted_months],
        },
        articles=articles,
    )


@app.route("/panel")
@login_required
def admin_home():
    return redirect(url_for("admin_articles"))


@app.route("/panel/articles")
@login_required
def admin_articles():
    articles = sorted(load_all_articles(), key=lambda a: a["date"], reverse=True)
    return render_template("admin/articles.html", articles=articles)


@app.route("/panel/articles/new")
@login_required
def admin_new_article():
    empty = {
        "id": None, "title": "", "summary": "", "date": date.today().isoformat(),
        "tag": TAGS[0], "author": "DataFantasy", "teams": [], "cover": None,
        "body": [], "status": "draft",
    }
    return render_template("admin/article_form.html", article=empty, teams=load_teams(), tags=TAGS)


@app.route("/panel/articles/<int:article_id>/edit")
@login_required
def admin_edit_article(article_id):
    match = next((a for a in load_all_articles() if a["id"] == article_id), None)
    if match is None:
        abort(404)
    return render_template("admin/article_form.html", article=match, teams=load_teams(), tags=TAGS)


@app.route("/panel/articles/save", methods=["POST"])
@login_required
def admin_save_article():
    articles = load_all_articles()
    article_id = request.form.get("id")
    action = request.form.get("action")

    if article_id:
        article_id = int(article_id)
        existing = next((a for a in articles if a["id"] == article_id), None)
        if existing is None:
            abort(404)
    else:
        existing = {"id": max((a["id"] for a in articles), default=0) + 1, "status": "draft"}

    updated = article_from_form(existing)

    if action == "preview":
        back_url = url_for("admin_edit_article", article_id=updated["id"]) if request.form.get("id") else None
        return render_template("admin/article_preview.html", article=updated, back_url=back_url)

    if action == "publish":
        updated["status"] = "published"

    articles = [a for a in articles if a["id"] != updated["id"]] + [updated]
    save_all_articles(articles)

    flash("Artículo publicado." if action == "publish" else "Artículo guardado como borrador.")
    return redirect(url_for("admin_edit_article", article_id=updated["id"]))


@app.route("/panel/articles/<int:article_id>/publish", methods=["POST"])
@login_required
def admin_publish_article(article_id):
    articles = load_all_articles()
    match = next((a for a in articles if a["id"] == article_id), None)
    if match is None:
        abort(404)
    match["status"] = "published"
    save_all_articles(articles)
    flash("Artículo publicado.")
    return redirect(url_for("admin_articles"))


@app.route("/panel/articles/<int:article_id>/tweet", methods=["POST"])
@login_required
def admin_tweet_article(article_id):
    articles = load_all_articles()
    match = next((a for a in articles if a["id"] == article_id), None)
    if match is None:
        abort(404)

    if match["status"] != "published":
        flash("Publica el artículo antes de tuitearlo.")
        return redirect(url_for("admin_edit_article", article_id=article_id))

    result = post_tweet_for_article(match)
    if result["sent"]:
        flash("Tuit enviado.")
    elif result["reason"] == "missing_credentials":
        flash("Tuit no enviado: faltan credenciales de Twitter en el entorno.")
    else:
        flash(f"Falló el tuit: {result['reason']}")
    return redirect(url_for("admin_edit_article", article_id=article_id))


@app.route("/panel/articles/<int:article_id>/delete", methods=["POST"])
@login_required
def admin_delete_article(article_id):
    articles = load_all_articles()
    match = next((a for a in articles if a["id"] == article_id), None)
    if match is None:
        abort(404)

    image_files = [match.get("cover")]
    image_files += [b.get("src") for b in match.get("body", []) if b.get("type") == "image"]
    for filename in image_files:
        if not filename:
            continue
        path = ARTICLES_IMG / filename
        if path.exists():
            path.unlink()

    articles = [a for a in articles if a["id"] != article_id]
    save_all_articles(articles)
    flash("Artículo eliminado.")
    return redirect(url_for("admin_articles"))


if __name__ == "__main__":
    app.run(debug=True)
