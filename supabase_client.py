"""Cliente HTTP mínimo para leer datos de Supabase vía la API REST de PostgREST."""
import os

import requests

PAGE_SIZE = 1000
CHUNK_SIZE = 50


def _base_url_and_headers():
    url = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_KEY"]
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    return url, headers


def fetch_all(table, params=None):
    """Trae todas las filas de `table`, paginando con Range hasta agotar resultados."""
    base_url, headers = _base_url_and_headers()
    rows = []
    offset = 0
    while True:
        page_headers = {**headers, "Range": f"{offset}-{offset + PAGE_SIZE - 1}"}
        response = requests.get(f"{base_url}/rest/v1/{table}", headers=page_headers, params=params, timeout=30)
        response.raise_for_status()
        page = response.json()
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def fetch_in_chunks(table, column, values, params=None):
    """Trae filas de `table` donde `column` está en `values`, troceando la lista en lotes."""
    rows = []
    values = list(values)
    for i in range(0, len(values), CHUNK_SIZE):
        chunk = values[i:i + CHUNK_SIZE]
        in_filter = "(" + ",".join(str(v) for v in chunk) + ")"
        chunk_params = {**(params or {}), column: f"in.{in_filter}"}
        rows.extend(fetch_all(table, chunk_params))
    return rows
