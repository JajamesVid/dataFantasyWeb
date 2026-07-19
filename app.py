import json
import uuid
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from twitter_post import post_tweet_for_article

load_dotenv()

app = Flask(__name__)
app.secret_key = "dev-only-secret-key"  # TODO: move to env var once admin auth is added

DATA = Path(__file__).parent / "data"
ARTICLES_IMG = Path(__file__).parent / "static" / "img" / "articles"
ALLOWED_IMAGE_EXT = {"jpg", "jpeg", "png", "webp", "gif"}
TAGS = ["Jornada", "Análisis", "Mercado"]

# 4-3-3: (left%, top%) within the pitch container
# SVG viewBox is 0 0 100 150; top% = svgY / 150 * 100
FORMATION_433 = [
    (50, 86),                                          # GK
    (13, 72), (35, 72), (65, 72), (87, 72),           # DEF
    (22, 52), (50, 52), (78, 52),                     # MID
    (15, 27), (50, 27), (85, 27),                     # FWD
]


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


def format_name(slug):
    return " ".join(w.capitalize() for w in slug.split("-"))


def get_lineup(sofascore_id):
    if not sofascore_id:
        return []
    all_players = load_json("players_to_analyze.json")
    team_data = next(
        (t for t in all_players["teams"] if t["sofascore_id"] == sofascore_id),
        None,
    )
    if not team_data:
        return []
    lineup = []
    for player, (px, py) in zip(team_data["players"][:11], FORMATION_433):
        lineup.append({
            "name": format_name(player["name"]),
            "x": px,
            "y": py,
            "probability": player.get("probability"),
        })
    return lineup


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
    return render_template("index.html", articles=load_articles())


@app.route("/article/<int:article_id>")
def article(article_id):
    match = next((a for a in load_articles() if a["id"] == article_id), None)
    if match is None:
        abort(404)
    return render_template("article.html", article=match)


@app.route("/equipos")
def equipos():
    return render_template("equipos.html", teams=load_teams())


@app.route("/equipos/<slug>")
def equipo(slug):
    teams = load_teams()
    team = next((t for t in teams if t["slug"] == slug), None)
    if team is None:
        abort(404)
    articles = [a for a in load_articles() if slug in a.get("teams", [])]
    lineup = get_lineup(team["sofascore_id"])
    return render_template("equipo.html", team=team, articles=articles, lineup=lineup)


# ── Admin: gestión de artículos ─────────────────────────────────────
# TODO: proteger esta sección con autenticación de administrador.

@app.route("/admin")
def admin_home():
    return redirect(url_for("admin_articles"))


@app.route("/admin/articles")
def admin_articles():
    articles = sorted(load_all_articles(), key=lambda a: a["date"], reverse=True)
    return render_template("admin/articles.html", articles=articles)


@app.route("/admin/articles/new")
def admin_new_article():
    empty = {
        "id": None, "title": "", "summary": "", "date": date.today().isoformat(),
        "tag": TAGS[0], "author": "DataFantasy", "teams": [], "cover": None,
        "body": [], "status": "draft",
    }
    return render_template("admin/article_form.html", article=empty, teams=load_teams(), tags=TAGS)


@app.route("/admin/articles/<int:article_id>/edit")
def admin_edit_article(article_id):
    match = next((a for a in load_all_articles() if a["id"] == article_id), None)
    if match is None:
        abort(404)
    return render_template("admin/article_form.html", article=match, teams=load_teams(), tags=TAGS)


@app.route("/admin/articles/save", methods=["POST"])
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


@app.route("/admin/articles/<int:article_id>/publish", methods=["POST"])
def admin_publish_article(article_id):
    articles = load_all_articles()
    match = next((a for a in articles if a["id"] == article_id), None)
    if match is None:
        abort(404)
    match["status"] = "published"
    save_all_articles(articles)
    flash("Artículo publicado.")
    return redirect(url_for("admin_articles"))


@app.route("/admin/articles/<int:article_id>/tweet", methods=["POST"])
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


@app.route("/admin/articles/<int:article_id>/delete", methods=["POST"])
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
