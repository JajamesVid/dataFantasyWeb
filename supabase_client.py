"""Cliente HTTP mínimo para leer datos de Supabase vía la API REST de PostgREST."""
import os
from concurrent.futures import ThreadPoolExecutor

import requests

PAGE_SIZE = 1000
CHUNK_SIZE = 50

# Dos pools separados a propósito: `fetch_many` orquesta varias llamadas (algunas de
# las cuales, como fetch_in_chunks, a su vez lanzan peticiones al pool de abajo). Si
# compartieran el mismo pool, un hilo orquestador podría quedar esperando un hueco
# que solo se libera cuando otro hilo orquestador (bloqueado igual) termina.
_CHUNK_EXECUTOR = ThreadPoolExecutor(max_workers=16)
_ORCHESTRATION_EXECUTOR = ThreadPoolExecutor(max_workers=8)


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
    """Trae filas de `table` donde `column` está en `values`, troceando la lista en lotes
    y pidiendo todos los lotes en paralelo (son peticiones de red independientes)."""
    values = list(values)
    chunks = [values[i:i + CHUNK_SIZE] for i in range(0, len(values), CHUNK_SIZE)]

    def fetch_chunk(chunk):
        in_filter = "(" + ",".join(str(v) for v in chunk) + ")"
        chunk_params = {**(params or {}), column: f"in.{in_filter}"}
        return fetch_all(table, chunk_params)

    rows = []
    for result in _CHUNK_EXECUTOR.map(fetch_chunk, chunks):
        rows.extend(result)
    return rows


def fetch_many(specs):
    """Ejecuta varias llamadas (p.ej. a fetch_all/fetch_in_chunks) en paralelo.

    `specs` es una lista de (nombre, fn) donde fn es una función sin argumentos
    (p.ej. `lambda: fetch_all("equipos")`). Devuelve un dict {nombre: resultado}.
    Corre en un pool aparte del de fetch_in_chunks (ver comentario arriba).
    """
    futures = {name: _ORCHESTRATION_EXECUTOR.submit(fn) for name, fn in specs}
    return {name: future.result() for name, future in futures.items()}
