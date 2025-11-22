import httpx
import time
from aiocron import crontab
from urllib.parse import unquote, quote

from fastapi import FastAPI, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

import state
from metadata.tmdb import TMDB
from utils.logger import setup_logger
from utils.stremio_parser import parse_hls_to_stremio
from utils.dixmax import GestorPerfiles, Perfil, obtener_enlace
from utils.hls_proxy import fetch_and_rewrite_manifest
from config import PERFILES, ROOT_PATH, IS_DEV, VERSION, ADDON_URL, PING_URL

logger = setup_logger(__name__)
http_client = httpx.AsyncClient(timeout=30, follow_redirects=True)

app = FastAPI(root_path=f"/{ROOT_PATH}" if ROOT_PATH and not ROOT_PATH.startswith("/") else ROOT_PATH)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- GESTIÓN DE PERFILES ---
def actualizar_perfiles_periodicamente():
    state.INSTANCIAS = {} 
    for nombre, cred in PERFILES.items():
        p = Perfil(cred)
        if p.valido:
            state.INSTANCIAS[nombre] = p
    if state.INSTANCIAS:
        state.gestor = GestorPerfiles(state.INSTANCIAS)
        logger.info(f"PERFILES: {len(state.INSTANCIAS)} perfiles activos.")
    else:
        logger.error("PERFILES: Ninguno válido.")

@app.on_event("startup")
async def startup_event():
    actualizar_perfiles_periodicamente()

# --- ENDPOINT PROXY ---
@app.api_route("/proxy/manifest", methods=["GET", "HEAD"])
async def proxy_manifest_endpoint(request: Request, url: str):
    target_url = unquote(url)
    logger.debug(f"PROXY_REQ: Cliente solicita -> {target_url}")
    
    current_proxy_base = str(ADDON_URL).rstrip('/')
    
    content, status = await fetch_and_rewrite_manifest(http_client, target_url, current_proxy_base)
    
    if status != 200:
        logger.error(f"PROXY_ERR: Origen respondió {status}")
        return Response(status_code=status)
    
    logger.info("PROXY_OK: Entregando manifiesto modificado.")
    
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Cache-Control": "no-cache, no-store, must-revalidate"
    }
    
    return Response(content=content, media_type="application/vnd.apple.mpegurl", headers=headers)

# --- ENDPOINT PRINCIPAL (STREMIO) ---
@app.get("/manifest.json")
async def get_manifest():
    return {
        "id": "ndk.ndkmax.ndk",
        "version": VERSION,
        "resources": ["stream"],
        "types": ["movie", "series"],
        "name": "NDKMAX Proxy",
        "catalogs": [],
        "behaviorHints": {"configurable": False},
    }

@app.get("/stream/{stream_type}/{stream_id}")
async def get_results(stream_type: str, stream_id: str):
    logger.info(f"STREAM_REQ: Solicitud recibida para {stream_id} ({stream_type})")
    
    start_time = time.time()
    stream_id = stream_id.replace(".json", "")

    metadata_provider = TMDB(http_client)
    media = await metadata_provider.get_metadata(stream_id, stream_type)

    if not media:
        return {"streams": []}

    if media.type == "movie":
        titulo = media.titles[0]
        duracion = await metadata_provider.get_duration(media.id, media.type)
        search_results = await obtener_enlace(http_client, media.id, is_movie=True)
    else:
        titulo = f"{media.titles[0]} S{media.season}E{media.episode}"
        duracion = await metadata_provider.get_duration(media.id, media.type, media.season, media.episode)
        search_results = await obtener_enlace(http_client, media.id, is_movie=False, season=media.season, episode=media.episode)

    if not search_results:
        logger.info("STREAM_RES: 0 resultados encontrados.")
        return {"streams": []}

    final_results = []
    base_url = str(ADDON_URL).rstrip('/')
    

    for result in search_results:
        stream_entry = await parse_hls_to_stremio(http_client, result, titulo, duracion)
        
        original_url = stream_entry["url"]
        encoded_url = quote(original_url)
        proxied_url = f"{base_url}/proxy/manifest?url={encoded_url}"
        
        stream_entry["url"] = proxied_url
        stream_entry["behaviorHints"]["notWebReady"] = False
        
        final_results.append(stream_entry)

    logger.info(f"STREAM_RES: {len(final_results)} streams generados (con proxy).")
    return {"streams": final_results}

@crontab("* * * * *", start=not IS_DEV)
async def ping_service():
    pass 

@crontab("0 */4 * * *", start=not IS_DEV)
async def actualizar_perfiles():
    actualizar_perfiles_periodicamente()
