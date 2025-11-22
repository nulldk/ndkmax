import httpx
from aiocron import crontab
from urllib.parse import unquote, quote
from fastapi import FastAPI, Response, Request
from fastapi.middleware.cors import CORSMiddleware

import state
from metadata.tmdb import TMDB
from utils.logger import setup_logger
from utils.stremio_parser import parse_hls_to_stremio
from utils.dixmax import GestorPerfiles, Perfil, obtener_enlace
from utils.hls_proxy import fetch_and_rewrite_manifest
from config import PERFILES, ROOT_PATH, IS_DEV, VERSION, ADDON_URL

logger = setup_logger(__name__)

limits = httpx.Limits(max_keepalive_connections=100, max_connections=500, keepalive_expiry=30)
timeout = httpx.Timeout(15.0, connect=5.0)

http_client = httpx.AsyncClient(
    timeout=timeout,
    limits=limits,
    follow_redirects=True,
    verify=False,
    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
)

app = FastAPI(root_path=f"/{ROOT_PATH}" if ROOT_PATH and not ROOT_PATH.startswith("/") else ROOT_PATH)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def actualizar_perfiles_periodicamente():
    state.INSTANCIAS = {} 
    for nombre, cred in PERFILES.items():
        p = Perfil(cred)
        if p.valido:
            state.INSTANCIAS[nombre] = p
    if state.INSTANCIAS:
        state.gestor = GestorPerfiles(state.INSTANCIAS)
        print(f"[INFO] Perfiles activos: {len(state.INSTANCIAS)}")
    else:
        logger.error("PERFILES: Ninguno válido.")

@app.on_event("startup")
async def startup_event():
    actualizar_perfiles_periodicamente()

@app.on_event("shutdown")
async def shutdown_event():
    await http_client.aclose()

@app.api_route("/proxy/manifest", methods=["GET", "HEAD"])
async def proxy_manifest_endpoint(request: Request, url: str):
    if not url: return Response(status_code=400)
    target_url = unquote(url)
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.netloc)
    current_proxy_base = f"{scheme}://{host}{ROOT_PATH}"
    content, status, content_type = await fetch_and_rewrite_manifest(http_client, target_url, current_proxy_base)
    if status != 200:
        return Response(status_code=status)
    return Response(
        content=content,
        media_type=content_type or "application/octet-stream",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=120",
            "X-Proxy-Agent": "NDKMAX-Opt"
        }
    )

@app.get("/manifest.json")
async def get_manifest():
    return {
        "id": "ndk.ndkmax.ndk",
        "version": VERSION,
        "resources": ["stream"],
        "types": ["movie", "series"],
        "name": "NDKMAX",
        "catalogs": [],
        "behaviorHints": {"configurable": False},
    }

@app.get("/stream/{stream_type}/{stream_id}")
async def get_results(stream_type: str, stream_id: str):
    try:
        stream_id = stream_id.replace(".json", "")
        metadata_provider = TMDB(http_client)
        media = await metadata_provider.get_metadata(stream_id, stream_type)

        if not media: return {"streams": []}

        if media.type == "movie":
            titulo = media.titles[0]
            duracion = await metadata_provider.get_duration(media.id, media.type)
            search_results = await obtener_enlace(http_client, media.id, is_movie=True)
        else:
            titulo = f"{media.titles[0]} S{media.season}E{media.episode}"
            duracion = await metadata_provider.get_duration(media.id, media.type, media.season, media.episode)
            search_results = await obtener_enlace(http_client, media.id, is_movie=False, season=media.season, episode=media.episode)

        if not search_results: return {"streams": []}

        final_results = []
        base_url = str(ADDON_URL).rstrip('/')

        for result in search_results:
            stream_entry = await parse_hls_to_stremio(http_client, result, titulo, duracion)
            original_url = stream_entry["url"]
            proxied_url = f"{base_url}/proxy/manifest?url={quote(original_url)}"
            
            stream_entry["url"] = proxied_url
            stream_entry["behaviorHints"]["notWebReady"] = False
            final_results.append(stream_entry)

        return {"streams": final_results}
    except Exception as e:
        logger.error(f"Error en streams: {e}")
        return {"streams": []}

@crontab("0 */4 * * *", start=not IS_DEV)
async def actualizar_perfiles():
    actualizar_perfiles_periodicamente()

@crontab("* * * * *", start=not IS_DEV)
async def ping_service():
    """Mantiene el servicio activo en plataformas como Render haciendo un ping cada minuto."""
    try:
        async with httpx.AsyncClient() as client:
            await client.get(ADDON_URL)
    except httpx.RequestError as e:
        logger.error(f"Fallo en el ping al servicio: {e}")
