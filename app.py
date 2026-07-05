import json
from pathlib import Path
from flask import Flask, render_template, abort

app = Flask(__name__)
DATA = Path(__file__).parent / "data"

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


def load_articles():
    articles = load_json("articles.json")
    return sorted(articles, key=lambda a: a["date"], reverse=True)


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


if __name__ == "__main__":
    app.run(debug=True)
