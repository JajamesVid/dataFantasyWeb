import json
import os
import uuid
from datetime import date
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

import supabase_data
from twitter_post import post_tweet_for_article

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-secret-key")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH")
SUPABASE_TEMPORADA = os.environ.get("SUPABASE_TEMPORADA", "25/26")

DATA = Path(__file__).parent / "data"
ARTICLES_IMG = Path(__file__).parent / "static" / "img" / "articles"
BADGES_DIR = Path(__file__).parent / "static" / "img" / "escudos"
ALLOWED_IMAGE_EXT = {"jpg", "jpeg", "png", "webp", "gif"}
BADGE_EXTENSIONS = ("webp", "png", "svg", "jpg", "jpeg")
TAGS = ["Jornada", "Análisis", "Mercado"]


def load_json(filename):
    with open(DATA / filename, encoding="utf-8") as f:
        return json.load(f)


def load_all_articles():
    return load_json("articles.json")


def save_all_articles(articles):
    with open(DATA / "articles.json", "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_articles():
    published = [a for a in load_all_articles() if a.get("status") == "published"]
    return sorted(published, key=lambda a: a["date"], reverse=True)


def load_teams():
    return load_json("teams.json")


def load_analytics():
    return load_json("analytics.json")


def save_analytics(analytics):
    with open(DATA / "analytics.json", "w", encoding="utf-8") as f:
        json.dump(analytics, f, ensure_ascii=False, indent=2)
        f.write("\n")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


MESES_ABREV = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def month_label(month_key):
    """'2026-08' -> 'ago 2026'."""
    year, month = month_key.split("-")
    return f"{MESES_ABREV[int(month) - 1]} {year}"


@app.before_request
def track_visit():
    if request.path.startswith("/panel") or request.path.startswith("/static"):
        return
    analytics = load_analytics()
    analytics["total_visits"] = analytics.get("total_visits", 0) + 1
    month_key = date.today().strftime("%Y-%m")
    monthly_visits = analytics.setdefault("monthly_visits", {})
    monthly_visits[month_key] = monthly_visits.get(month_key, 0) + 1
    save_analytics(analytics)


def team_badge_url(slug):
    """Look up a team crest in static/img/escudos/<slug>.<ext>, if one has been uploaded."""
    for ext in BADGE_EXTENSIONS:
        if (BADGES_DIR / f"{slug}.{ext}").exists():
            return url_for("static", filename=f"img/escudos/{slug}.{ext}")
    return None


def load_points_evolution():
    data = supabase_data.build_points_evolution(SUPABASE_TEMPORADA)
    real_slugs = {t["slug"] for t in load_teams()}
    for team in data["teams"]:
        team["badge"] = team_badge_url(team["slug"])
        # A few chart-only entries (e.g. teams from a different season) don't have a real team page.
        team["has_page"] = team["slug"] in real_slugs
    return data


def load_classification_evolution():
    data = supabase_data.build_classification_evolution(SUPABASE_TEMPORADA)
    real_slugs = {t["slug"] for t in load_teams()}
    for team in data["teams"]:
        team["badge"] = team_badge_url(team["slug"])
        team["has_page"] = team["slug"] in real_slugs
    return data


def load_player_radar():
    data = supabase_data.build_player_radar(SUPABASE_TEMPORADA)
    for player in data["players"]:
        player["team_badge"] = team_badge_url(player["team_slug"])
    return data


def load_team_evolution(slug):
    """A single team's jornada-by-jornada points and league position, overlaid on the
    strip chart on its own page.

    Not every team in teams.json has data for the configured temporada, so this
    returns None when there's nothing to plot.
    """
    data = supabase_data.build_team_evolution(slug, SUPABASE_TEMPORADA)
    if data is None:
        return None
    return {**data, "badge": team_badge_url(slug)}


def load_team_player_stats(slug):
    """Not every team has a roster to draw from yet (see load_team_evolution), so this
    returns None when there's nothing to show.
    """
    return supabase_data.build_team_player_stats(slug, SUPABASE_TEMPORADA)


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
        points_evolution=load_points_evolution(),
        classification_evolution=load_classification_evolution(),
        player_radar=load_player_radar(),
    )


@app.route("/article/<int:article_id>")
def article(article_id):
    match = next((a for a in load_articles() if a["id"] == article_id), None)
    if match is None:
        abort(404)

    analytics = load_analytics()
    article_visits = analytics.setdefault("article_visits", {})
    article_visits[str(article_id)] = article_visits.get(str(article_id), 0) + 1
    save_analytics(analytics)

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


# ── Panel de administración (protegido con login) ───────────────────

@app.route("/panel/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        valid_user = ADMIN_USERNAME is not None and username == ADMIN_USERNAME
        valid_password = ADMIN_PASSWORD_HASH is not None and check_password_hash(ADMIN_PASSWORD_HASH, password)
        if valid_user and valid_password:
            session["admin_logged_in"] = True
            next_url = request.form.get("next") or url_for("admin_articles")
            return redirect(next_url)
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

    return render_template(
        "admin/analytics.html",
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
