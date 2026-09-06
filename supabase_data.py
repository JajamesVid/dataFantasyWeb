"""Agregación de datos reales de Supabase para sustituir los JSON de muestra.

Una sola carga por temporada (`_load_season_bundle`, cacheada) trae las tablas
compartidas por las 4 vistas; cada `build_*` deriva su resultado de ese bundle
sin volver a golpear la red.
"""
import json
import os
import re
import statistics
import time
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

from supabase_client import fetch_all, fetch_in_chunks, fetch_many

DATA_DIR = Path(__file__).parent / "data"
CACHE_TTL_SECONDS = 900

# Temporadas (formato "26/27") que todavía viven en tablas _stg (staging) en vez de
# las de producción — para poder previsualizar un volcado antes de promocionarlo.
# Se retira de aquí (variable de entorno) el día que esos datos pasen a producción.
STAGING_TEMPORADAS = {
    t.strip() for t in os.environ.get("SUPABASE_STAGING_TEMPORADAS", "").split(",") if t.strip()
}


def _table_name(base_name, temporada):
    """`equipos`/`jugadores`/`historial_equipos_jugador` son catálogos compartidos entre
    temporadas y nunca tienen variante _stg; solo las tablas por-partido la tienen."""
    return f"{base_name}_stg" if temporada in STAGING_TEMPORADAS else base_name

# nombre_equipo (Supabase) -> slug (teams.json), para los equipos que coinciden.
# Los que faltan (p.ej. equipos de otra temporada/división) quedan como "solo gráfica":
# aparecen en las gráficas pero sin página propia, igual que ya soporta el código de app.py.
TEAM_NAME_TO_SLUG = {
    "Athletic Club": "athletic-club",
    "Atlético Madrid": "atletico-madrid",
    "Celta Vigo": "celta",
    "Deportivo Alavés": "alaves",
    "Elche": "elche",
    "Espanyol": "espanyol",
    "FC Barcelona": "barcelona",
    "Getafe": "getafe",
    "Levante UD": "levante",
    "Osasuna": "osasuna",
    "Rayo Vallecano": "rayo-vallecano",
    "Real Betis": "real-betis",
    "Real Madrid": "real-madrid",
    "Real Sociedad": "real-sociedad",
    "Sevilla": "sevilla",
    "Valencia": "valencia",
    "Villarreal": "villarreal",
}

MIN_MATCHES_RADAR = 10
MIN_MATCHES_CATEGORY = 10
MIN_MATCHES_REVELACION = 3
MIN_PASES_ACIERTO = 50
RECENT_JORNADAS_WINDOW = 6

POSITION_LABELS = {
    "POR": "Portero",
    "LD": "Lateral derecho",
    "LI": "Lateral izquierdo",
    "DFC": "Defensa central",
    "MCD": "Mediocentro defensivo",
    "MC": "Centrocampista",
    "MCO": "Mediapunta",
    "ED": "Extremo derecho",
    "EI": "Extremo izquierdo",
    "DC": "Delantero centro",
    "SD": "Segundo delantero",
}

# Agrupación en las 4 líneas clásicas, para el reparto de puntos por posición
# (gráfico de sectores de la home) — más legible que las 11 posiciones exactas.
POSITION_GROUPS = {
    "POR": "portero",
    "LD": "defensa", "LI": "defensa", "DFC": "defensa",
    "MCD": "centrocampista", "MC": "centrocampista", "MCO": "centrocampista",
    "ED": "delantero", "EI": "delantero", "DC": "delantero", "SD": "delantero",
}

POSITION_GROUP_LABELS = {
    "portero": "Portero",
    "defensa": "Defensa",
    "centrocampista": "Centrocampista",
    "delantero": "Delantero",
}

CATEGORY_META = {
    "valorado": ("Mejor valorado", "El más consistente en valoración esta temporada"),
    "regularidad": ("Más regular", "El más fiable jornada tras jornada"),
    "racha": ("En racha", "El de mejor forma reciente"),
    "acierto": ("Más acertado", "El de mayor precisión de pase"),
    "influencia": ("Más influyente", "El que más goles y asistencias suma"),
    "revelacion": ("La revelación", "La sorpresa de la temporada"),
}

_CACHE = {}


def _slugify(text):
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()


def _load_teams_json():
    with open(DATA_DIR / "teams.json", encoding="utf-8") as f:
        return json.load(f)


def _fetch_season_bundle(temporada):
    # Primera tanda: independientes entre sí, se piden todas a la vez.
    first = fetch_many([
        ("partidos", lambda: fetch_all(_table_name("partidos", temporada), {
            "temporada": f"eq.{temporada}",
            "select": "partido_id,jornada,fecha_partido,equipo_local_id,equipo_visitante_id,"
                      "abreviatura_local,abreviatura_visitante",
            "order": "partido_id.asc",
        })),
        ("historial", lambda: fetch_all("historial_equipos_jugador", {"order": "historial_id.asc"})),
        ("jugadores", lambda: fetch_all("jugadores", {
            "select": "jugador_id,nombre_jugador,fecha_nacimiento,posicion,altura_cm", "order": "jugador_id.asc",
        })),
        ("equipos", lambda: fetch_all("equipos", {"select": "equipo_id,nombre_equipo", "order": "equipo_id.asc"})),
    ])
    partidos = first["partidos"]
    historial = first["historial"]
    jugadores = first["jugadores"]
    equipos = first["equipos"]

    partido_ids = [p["partido_id"] for p in partidos]
    partidos_by_id = {p["partido_id"]: p for p in partidos}

    # Segunda tanda: dependen de partido_ids, pero son independientes entre sí.
    second = fetch_many([
        ("statsequipos", lambda: fetch_in_chunks(_table_name("statsequipos", temporada), "partido_id", partido_ids, {
            "select": "partido_id,equipo_id,puntos_acumulados,diferencia_goles_acumulada,goles_favor_acumulados",
            "order": "estadistica_equipo_id.asc",
        })),
        ("puntuaciones", lambda: fetch_in_chunks(_table_name("puntuaciones", temporada), "partido_id", partido_ids, {
            "select": "partido_id,jugador_id,puntuacion_media,racha_puntuacion_media_14d",
            "order": "puntuacion_id.asc",
        })),
        ("statsjugadores", lambda: fetch_in_chunks(_table_name("statsjugadores", temporada), "partido_id", partido_ids, {
            "select": "partido_id,jugador_id,equipo_id,goles,asistencias_gol,pases_precisos,pases_totales,minutos_jugados",
            "order": "estadistica_id.asc",
        })),
    ])
    statsequipos = second["statsequipos"]
    puntuaciones = second["puntuaciones"]
    statsjugadores = second["statsjugadores"]

    statsjugadores_idx = {(s["partido_id"], s["jugador_id"]): s["equipo_id"] for s in statsjugadores}

    historial_by_jugador = defaultdict(list)
    for h in historial:
        historial_by_jugador[h["jugador_id"]].append((h["fecha_inicio"], h["fecha_fin"], h["equipo_id"]))

    return {
        "partidos": partidos,
        "partidos_by_id": partidos_by_id,
        "statsequipos": statsequipos,
        "puntuaciones": puntuaciones,
        "statsjugadores": statsjugadores,
        "statsjugadores_idx": statsjugadores_idx,
        "historial_by_jugador": dict(historial_by_jugador),
        "jugadores_by_id": {j["jugador_id"]: j for j in jugadores},
        "equipos_by_id": {e["equipo_id"]: e for e in equipos},
    }


def _load_season_bundle(temporada):
    cached = _CACHE.get(temporada)
    if cached and (time.time() - cached[1] < CACHE_TTL_SECONDS):
        return cached[0]
    bundle = _fetch_season_bundle(temporada)
    _CACHE[temporada] = (bundle, time.time())
    return bundle


def _equipo_lookup(bundle):
    """equipo_id -> {slug, name, short} para los equipos que jugaron esa temporada."""
    abrev = {}
    for p in bundle["partidos"]:
        abrev[p["equipo_local_id"]] = p["abreviatura_local"]
        abrev[p["equipo_visitante_id"]] = p["abreviatura_visitante"]

    teams_by_slug = {t["slug"]: t for t in _load_teams_json()}

    result = {}
    for equipo_id in sorted(abrev):
        nombre = bundle["equipos_by_id"].get(equipo_id, {}).get("nombre_equipo", f"Equipo {equipo_id}")
        slug = TEAM_NAME_TO_SLUG.get(nombre)
        team_json = teams_by_slug.get(slug) if slug else None
        if team_json:
            result[equipo_id] = {"slug": slug, "name": team_json["name"], "short": team_json["short"]}
        else:
            result[equipo_id] = {"slug": slug or _slugify(nombre), "name": nombre, "short": abrev[equipo_id]}
    return result


def _resolve_via_historial(jugador_id, fecha_partido, historial_by_jugador):
    for inicio, fin, equipo_id in historial_by_jugador.get(jugador_id, []):
        if inicio and inicio <= fecha_partido and (fin is None or fecha_partido < fin):
            return equipo_id
    return None


def _resolve_equipo(jugador_id, partido_id, fecha_partido, bundle):
    equipo_id = bundle["statsjugadores_idx"].get((partido_id, jugador_id))
    if equipo_id is not None:
        return equipo_id
    return _resolve_via_historial(jugador_id, fecha_partido, bundle["historial_by_jugador"])


def _current_team_for_player(jugador_id, historial_by_jugador):
    entries = historial_by_jugador.get(jugador_id, [])
    if not entries:
        return None
    active = [e for e in entries if e[1] is None]
    if active:
        return active[0][2]
    return max(entries, key=lambda e: e[0])[2]


def build_classification_evolution(temporada):
    bundle = _load_season_bundle(temporada)
    equipo_info = _equipo_lookup(bundle)
    jornadas_max = max((p["jornada"] for p in bundle["partidos"]), default=0)

    rows_by_equipo_jornada = {}
    for row in bundle["statsequipos"]:
        partido = bundle["partidos_by_id"].get(row["partido_id"])
        if not partido:
            continue
        rows_by_equipo_jornada[(row["equipo_id"], partido["jornada"])] = row

    equipo_ids = sorted(equipo_info)
    positions = {eid: [] for eid in equipo_ids}
    last_known = {}
    for jornada in range(1, jornadas_max + 1):
        standings = []
        for eid in equipo_ids:
            row = rows_by_equipo_jornada.get((eid, jornada))
            if row is not None:
                last_known[eid] = row
            row = row or last_known.get(eid)
            puntos = row["puntos_acumulados"] if row else 0
            dif = row["diferencia_goles_acumulada"] if row else 0
            favor = row["goles_favor_acumulados"] if row else 0
            standings.append((eid, puntos, dif, favor))
        standings.sort(key=lambda t: (-t[1], -t[2], -t[3]))
        for pos, (eid, *_rest) in enumerate(standings, start=1):
            positions[eid].append(pos)

    teams_out = [
        {**equipo_info[eid], "positions": positions[eid]}
        for eid in equipo_ids
    ]
    return {"jornadas": [f"J{n}" for n in range(1, jornadas_max + 1)], "teams": teams_out}


def build_points_evolution(temporada):
    bundle = _load_season_bundle(temporada)
    equipo_info = _equipo_lookup(bundle)
    jornadas_max = max((p["jornada"] for p in bundle["partidos"]), default=0)

    points_by_equipo_jornada = defaultdict(lambda: defaultdict(float))
    unresolved = 0
    for punt in bundle["puntuaciones"]:
        partido = bundle["partidos_by_id"].get(punt["partido_id"])
        if not partido:
            continue
        equipo_id = _resolve_equipo(punt["jugador_id"], punt["partido_id"], partido["fecha_partido"], bundle)
        if equipo_id is None:
            unresolved += 1
            continue
        points_by_equipo_jornada[equipo_id][partido["jornada"]] += punt.get("puntuacion_media") or 0

    if unresolved:
        print(f"[supabase_data] build_points_evolution({temporada}): {unresolved} filas de puntuaciones sin equipo resuelto")

    teams_out = []
    for eid in sorted(equipo_info):
        running = 0.0
        cumulative = []
        for jornada in range(1, jornadas_max + 1):
            running += points_by_equipo_jornada.get(eid, {}).get(jornada, 0)
            cumulative.append(round(running, 1))
        teams_out.append({**equipo_info[eid], "points": cumulative})

    return {"jornadas": [f"J{n}" for n in range(1, jornadas_max + 1)], "teams": teams_out}


def build_team_evolution(slug, temporada):
    points = build_points_evolution(temporada)
    classification = build_classification_evolution(temporada)
    team_points = next((t for t in points["teams"] if t["slug"] == slug), None)
    if team_points is None:
        return None
    team_class = next((t for t in classification["teams"] if t["slug"] == slug), None)
    return {
        "jornadas": points["jornadas"],
        "points": team_points["points"],
        "positions": team_class["positions"] if team_class else None,
    }


def build_player_radar(temporada):
    bundle = _load_season_bundle(temporada)

    agg = defaultdict(lambda: {"sum_media": 0.0, "medias": [], "goles": 0, "asistencias": 0, "matches": 0})
    for punt in bundle["puntuaciones"]:
        media = punt.get("puntuacion_media")
        if media is None:
            continue
        a = agg[punt["jugador_id"]]
        a["sum_media"] += media
        a["medias"].append(media)
        a["matches"] += 1

    for sj in bundle["statsjugadores"]:
        a = agg[sj["jugador_id"]]
        a["goles"] += sj.get("goles") or 0
        a["asistencias"] += sj.get("asistencias_gol") or 0

    pool = {jid: a for jid, a in agg.items() if a["matches"] >= MIN_MATCHES_RADAR} or agg
    if not pool:
        return {"metrics": ["Goles", "Asistencias", "Regularidad", "Valoración", "Puntos Fantasy"], "players": []}

    raw = {}
    for jid, a in pool.items():
        stdev = statistics.pstdev(a["medias"]) if len(a["medias"]) > 1 else 0.0
        raw[jid] = {
            "goles": a["goles"],
            "asistencias": a["asistencias"],
            "regularidad": -stdev,
            "valoracion": a["sum_media"] / a["matches"],
            "puntos_fantasy": a["sum_media"],
        }

    def normalize(key):
        values = [v[key] for v in raw.values()]
        lo, hi = min(values), max(values)
        spread = hi - lo
        return {jid: 100.0 if spread == 0 else (v[key] - lo) / spread * 100 for jid, v in raw.items()}

    metric_keys = ["goles", "asistencias", "regularidad", "valoracion", "puntos_fantasy"]
    norm = {key: normalize(key) for key in metric_keys}

    top3 = sorted(pool, key=lambda jid: raw[jid]["puntos_fantasy"], reverse=True)[:3]
    equipo_info = _equipo_lookup(bundle)

    players_out = []
    for jid in top3:
        jugador = bundle["jugadores_by_id"].get(jid, {})
        team_id = _current_team_for_player(jid, bundle["historial_by_jugador"])
        info = equipo_info.get(team_id, {})
        players_out.append({
            "slug": _slugify(jugador.get("nombre_jugador", str(jid))),
            "name": jugador.get("nombre_jugador", f"Jugador {jid}"),
            "team_slug": info.get("slug"),
            "team_short": info.get("short"),
            "values": [round(norm[key][jid], 1) for key in metric_keys],
        })

    return {"metrics": ["Goles", "Asistencias", "Regularidad", "Valoración", "Puntos Fantasy"], "players": players_out}


def _season_date_bounds(partidos):
    fechas = [p["fecha_partido"] for p in partidos]
    if not fechas:
        return None, None
    return min(fechas), max(fechas)


def build_team_player_stats(slug, temporada):
    bundle = _load_season_bundle(temporada)
    equipo_info = _equipo_lookup(bundle)
    equipo_id = next((eid for eid, info in equipo_info.items() if info["slug"] == slug), None)
    if equipo_id is None:
        return None

    jornadas_max = max((p["jornada"] for p in bundle["partidos"]), default=0)
    temporada_inicio, temporada_fin = _season_date_bounds(bundle["partidos"])

    per_player = defaultdict(lambda: {
        "medias_by_jornada": {}, "racha_by_jornada": {}, "matches": 0, "sum_media": 0.0,
        "medias": [], "goles": 0, "asistencias": 0, "pases_precisos": 0, "pases_totales": 0,
    })

    for punt in bundle["puntuaciones"]:
        partido = bundle["partidos_by_id"].get(punt["partido_id"])
        if not partido:
            continue
        equipo_jugador = _resolve_equipo(punt["jugador_id"], punt["partido_id"], partido["fecha_partido"], bundle)
        if equipo_jugador != equipo_id:
            continue
        media = punt.get("puntuacion_media")
        if media is None:
            continue
        p = per_player[punt["jugador_id"]]
        p["medias_by_jornada"][partido["jornada"]] = media
        p["matches"] += 1
        p["sum_media"] += media
        p["medias"].append(media)
        if punt.get("racha_puntuacion_media_14d") is not None:
            p["racha_by_jornada"][partido["jornada"]] = punt["racha_puntuacion_media_14d"]

    for sj in bundle["statsjugadores"]:
        if sj.get("equipo_id") != equipo_id:
            continue
        p = per_player[sj["jugador_id"]]
        p["goles"] += sj.get("goles") or 0
        p["asistencias"] += sj.get("asistencias_gol") or 0
        p["pases_precisos"] += sj.get("pases_precisos") or 0
        p["pases_totales"] += sj.get("pases_totales") or 0

    newcomers = {
        jugador_id
        for jugador_id, entries in bundle["historial_by_jugador"].items()
        for inicio, _fin, eid in entries
        if eid == equipo_id and inicio and temporada_inicio <= inicio <= temporada_fin
    }

    eligible = [jid for jid, p in per_player.items() if p["matches"] >= MIN_MATCHES_CATEGORY] or list(per_player)

    chosen = {}

    def pick(category_key, candidates, keyfn):
        remaining = [jid for jid in candidates if jid not in chosen.values()]
        if remaining:
            chosen[category_key] = max(remaining, key=keyfn)

    pick("valorado", eligible, lambda jid: per_player[jid]["sum_media"] / per_player[jid]["matches"])
    pick("regularidad", eligible,
         lambda jid: -statistics.pstdev(per_player[jid]["medias"]) if len(per_player[jid]["medias"]) > 1 else 0)
    pick("racha", eligible,
         lambda jid: per_player[jid]["racha_by_jornada"].get(max(per_player[jid]["racha_by_jornada"], default=0), -999))

    acierto_pool = [jid for jid in eligible if per_player[jid]["pases_totales"] >= MIN_PASES_ACIERTO] or eligible
    pick("acierto", acierto_pool, lambda jid: per_player[jid]["pases_precisos"] / max(per_player[jid]["pases_totales"], 1))

    pick("influencia", eligible, lambda jid: per_player[jid]["goles"] + per_player[jid]["asistencias"])

    revelacion_pool = [
        jid for jid in per_player
        if jid in newcomers and per_player[jid]["matches"] >= MIN_MATCHES_REVELACION and jid not in chosen.values()
    ]
    if revelacion_pool:
        chosen["revelacion"] = max(revelacion_pool, key=lambda jid: per_player[jid]["sum_media"] / per_player[jid]["matches"])
    else:
        remaining = [
            jid for jid in per_player
            if jid not in chosen.values() and bundle["jugadores_by_id"].get(jid, {}).get("fecha_nacimiento")
        ]
        if remaining:
            chosen["revelacion"] = max(remaining, key=lambda jid: bundle["jugadores_by_id"][jid]["fecha_nacimiento"])

    recent_jornadas = list(range(max(1, jornadas_max - RECENT_JORNADAS_WINDOW + 1), jornadas_max + 1))

    players_out = []
    for category_key, jugador_id in chosen.items():
        p = per_player[jugador_id]
        jugador = bundle["jugadores_by_id"].get(jugador_id, {})
        label, description = CATEGORY_META[category_key]
        players_out.append({
            "name": jugador.get("nombre_jugador", f"Jugador {jugador_id}"),
            "scores": [round(p["medias_by_jornada"].get(j, 0), 1) for j in recent_jornadas],
            "avg": round(p["sum_media"] / p["matches"], 1) if p["matches"] else 0,
            "goals": p["goles"],
            "assists": p["asistencias"],
            "category_key": category_key,
            "category_label": label,
            "category_description": description,
        })

    return {"jornadas": [f"J{n}" for n in recent_jornadas], "players": players_out}


def _player_slug(jugador_id, nombre):
    return f"{_slugify(nombre)}-{jugador_id}"


def _jugador_id_from_slug(slug):
    match = re.search(r"-(\d+)$", slug or "")
    return int(match.group(1)) if match else None


def _age_from_birthdate(fecha_nacimiento):
    if not fecha_nacimiento:
        return None
    born = date.fromisoformat(fecha_nacimiento)
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


RECENT_SCORES_WINDOW = 5


def _score_band(value):
    """Código de colores usado en toda la sección de jugadores para una puntuación
    individual de partido: <=1 rojo, (1,5] naranja, (5,9] verde, >9 azul."""
    if value <= 1:
        return "red"
    if value <= 5:
        return "orange"
    if value <= 9:
        return "green"
    return "blue"


def build_player_directory(temporada):
    bundle = _load_season_bundle(temporada)
    equipo_info = _equipo_lookup(bundle)

    agg = defaultdict(lambda: {"sum_media": 0.0, "matches": 0, "goles": 0, "asistencias": 0, "by_jornada": {}})
    for punt in bundle["puntuaciones"]:
        media = punt.get("puntuacion_media")
        if media is None:
            continue
        partido = bundle["partidos_by_id"].get(punt["partido_id"])
        if not partido:
            continue
        a = agg[punt["jugador_id"]]
        a["sum_media"] += media
        a["matches"] += 1
        a["by_jornada"][partido["jornada"]] = media

    for sj in bundle["statsjugadores"]:
        a = agg[sj["jugador_id"]]
        a["goles"] += sj.get("goles") or 0
        a["asistencias"] += sj.get("asistencias_gol") or 0

    players_out = []
    for jid, a in agg.items():
        if a["matches"] < 1:
            continue
        jugador = bundle["jugadores_by_id"].get(jid, {})
        nombre = jugador.get("nombre_jugador", f"Jugador {jid}")
        team_id = _current_team_for_player(jid, bundle["historial_by_jugador"])
        team = equipo_info.get(team_id, {})
        posicion = jugador.get("posicion")

        recent_jornadas = sorted(a["by_jornada"])[-RECENT_SCORES_WINDOW:]
        recent_scores = [
            {"jornada": j, "score": round(a["by_jornada"][j], 1), "band": _score_band(a["by_jornada"][j])}
            for j in recent_jornadas
        ]

        players_out.append({
            "slug": _player_slug(jid, nombre),
            "jugador_id": jid,
            "name": nombre,
            "age": _age_from_birthdate(jugador.get("fecha_nacimiento")),
            "position": posicion,
            "position_label": POSITION_LABELS.get(posicion, posicion),
            "team_slug": team.get("slug"),
            "team_name": team.get("name"),
            "team_short": team.get("short"),
            "matches": a["matches"],
            "total": round(a["sum_media"], 1),
            "avg": round(a["sum_media"] / a["matches"], 1),
            "goals": a["goles"],
            "assists": a["asistencias"],
            "recent_scores": recent_scores,
        })

    players_out.sort(key=lambda p: p["total"], reverse=True)
    return players_out


def build_position_points_breakdown(temporada):
    """Reparto de los puntos Fantasy repartidos esta temporada entre las 4 líneas
    (portero/defensa/centrocampista/delantero) — para el gráfico de sectores de la home."""
    bundle = _load_season_bundle(temporada)

    totals = defaultdict(float)
    for punt in bundle["puntuaciones"]:
        media = punt.get("puntuacion_media")
        if media is None:
            continue
        jugador = bundle["jugadores_by_id"].get(punt["jugador_id"])
        if not jugador:
            continue
        group = POSITION_GROUPS.get(jugador.get("posicion"))
        if not group:
            continue
        totals[group] += media

    total_sum = sum(totals.values()) or 1.0
    order = ["portero", "defensa", "centrocampista", "delantero"]
    return [
        {
            "key": key,
            "label": POSITION_GROUP_LABELS[key],
            "value": round(totals.get(key, 0.0), 1),
            "pct": round(totals.get(key, 0.0) / total_sum * 100, 1),
        }
        for key in order
    ]


def build_player_detail(slug, temporada):
    jugador_id = _jugador_id_from_slug(slug)
    if jugador_id is None:
        return None

    bundle = _load_season_bundle(temporada)
    jugador = bundle["jugadores_by_id"].get(jugador_id)
    if jugador is None:
        return None

    equipo_info = _equipo_lookup(bundle)
    statsjugadores_by_match = {
        (sj["partido_id"], sj["jugador_id"]): sj for sj in bundle["statsjugadores"] if sj["jugador_id"] == jugador_id
    }

    matches_out = []
    sum_media, goles, asistencias, minutos = 0.0, 0, 0, 0
    for punt in bundle["puntuaciones"]:
        if punt["jugador_id"] != jugador_id:
            continue
        partido = bundle["partidos_by_id"].get(punt["partido_id"])
        if not partido:
            continue
        media = punt.get("puntuacion_media")
        if media is None:
            continue

        equipo_id = _resolve_equipo(jugador_id, punt["partido_id"], partido["fecha_partido"], bundle)
        if equipo_id == partido["equipo_local_id"]:
            rival = partido["abreviatura_visitante"]
        elif equipo_id == partido["equipo_visitante_id"]:
            rival = partido["abreviatura_local"]
        else:
            rival = None

        sj = statsjugadores_by_match.get((punt["partido_id"], jugador_id), {})
        match_goles = sj.get("goles") or 0
        match_asistencias = sj.get("asistencias_gol") or 0
        match_minutos = sj.get("minutos_jugados") or 0

        sum_media += media
        goles += match_goles
        asistencias += match_asistencias
        minutos += match_minutos

        matches_out.append({
            "jornada": partido["jornada"],
            "fecha": partido["fecha_partido"],
            "rival": rival,
            "score": round(media, 1),
            "band": _score_band(media),
            "goals": match_goles,
            "assists": match_asistencias,
            "minutes": match_minutos,
        })

    matches_out.sort(key=lambda m: m["jornada"])
    total_matches = len(matches_out)

    team_id = _current_team_for_player(jugador_id, bundle["historial_by_jugador"])
    team = equipo_info.get(team_id, {})
    posicion = jugador.get("posicion")

    valoraciones = fetch_all("valoraciones_jugador", {
        "jugador_id": f"eq.{jugador_id}",
        "select": "fecha,valor_eur",
        "order": "fecha.asc",
    })

    return {
        "slug": slug,
        "name": jugador.get("nombre_jugador", f"Jugador {jugador_id}"),
        "jugador_id": jugador_id,
        "age": _age_from_birthdate(jugador.get("fecha_nacimiento")),
        "height_cm": jugador.get("altura_cm"),
        "position": posicion,
        "position_label": POSITION_LABELS.get(posicion, posicion),
        "team_slug": team.get("slug"),
        "team_name": team.get("name"),
        "team_short": team.get("short"),
        "matches": matches_out,
        "totals": {
            "matches": total_matches,
            "avg": round(sum_media / total_matches, 1) if total_matches else 0,
            "goals": goles,
            "assists": asistencias,
            "minutes": minutos,
        },
        "valuations": valoraciones or None,
    }
