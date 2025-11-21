import httpx
import time
from aiocron import crontab


from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

import state
from metadata.tmdb import TMDB
from utils.logger import setup_logger
from utils.stremio_parser import parse_hls_to_stremio
from utils.dixmax import GestorPerfiles, Perfil, obtener_enlace
from config import PERFILES, ROOT_PATH, IS_DEV, VERSION
# --- Inicialización ---
logger = setup_logger(__name__)


# OPTIMIZADO: Crear un cliente httpx para reutilizar conexiones
http_client = httpx.AsyncClient(timeout=30)

def actualizar_perfiles_periodicamente():
    state.INSTANCIAS = {} # Reset
    for nombre, cred in PERFILES.items():
        p = Perfil(cred)
        if p.valido:
            state.INSTANCIAS[nombre] = p
    
    if state.INSTANCIAS:
        state.gestor = GestorPerfiles(state.INSTANCIAS)
        logger.info(f"Perfiles válidos: {', '.join(state.INSTANCIAS.keys())}")
    else:
        logger.error("No hay perfiles válidos.")

# Configuración de la aplicación FastAPI
app = FastAPI(root_path=f"/{ROOT_PATH}" if ROOT_PATH and not ROOT_PATH.startswith("/") else ROOT_PATH)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Endpoints de la Interfaz y Manifiesto ---

@app.on_event("startup")
async def startup_event():
    logger.info("Empezando comprobaciones de perfiles...")
    actualizar_perfiles_periodicamente()
    logger.info("Comprobacion de perfiles acabada.")


@app.get("/", include_in_schema=False)
async def root():
    """Redirige a la página de configuración."""
    return RedirectResponse(url="/manifest.json")

@app.get("/manifest.json")
async def get_manifest():
    """
    Proporciona el manifiesto del addon a Stremio.
    Define las capacidades y metadatos del addon.
    """
    addon_name = f"NDKMAX{' (Dev)' if IS_DEV else ''}"
    return {
        "id": "ndk.ndkmax.ndk",
        "icon": "https://i.ibb.co/zGmkQZm/ndk.jpg",
        "version": VERSION,
        "catalogs": [],
        "resources": ["stream"],
        "types": ["movie", "series"],
        "name": addon_name,
        "description": "Addon que usa DixMax para su reproduducción en Stremio. El contenido es obtenido de la app de Dixmax, fuentes de terceros.",
        "behaviorHints": {"configurable": False},
    }


# --- Lógica Principal del Addon ---
@app.get("/stream/{stream_type}/{stream_id}")
async def get_results(stream_type: str, stream_id: str):
    """
    Busca y devuelve los streams disponibles para un item (película o serie).
    """
    start_time = time.time()
    stream_id = stream_id.replace(".json", "")

    metadata_provider = TMDB(http_client)
    media = await metadata_provider.get_metadata(stream_id, stream_type)

    if media.type == "movie":
        titulo = f"{media.titles[0]}"
        duracion = await metadata_provider.get_duration(media.id, media.type)
        search_results = await obtener_enlace(http_client, media.id, is_movie = True)
    else:
        titulo = f"{media.titles[0]} S{media.season}E{media.episode}"
        duracion = await metadata_provider.get_duration(media.id, media.type, media.season, media.episode)
        search_results = await obtener_enlace(http_client, media.id, is_movie = False, season = media.season, episode = media.episode)

    if not search_results:
        logger.info(f"No se encontraron resultados para {media.type} {stream_id}. Tiempo total: {time.time() - start_time:.2f}s")
        return {"streams": []}
    
    final_results = []
    for result in search_results:
        final_results.append(await parse_hls_to_stremio(http_client, result, titulo, duracion))
    
    logger.info(f"Resultados encontrados. Tiempo total: {time.time() - start_time:.2f}s")
    return {"streams": final_results}

@crontab("* * * * *", start=not IS_DEV)
async def ping_service():
    """Mantiene el servicio activo en plataformas como Render haciendo un ping cada minuto."""
    try:
        await http_client.get(PING_URL)
    except httpx.RequestError as e:
        logger.error(f"Fallo en el ping al servicio: {e}")

@crontab("* * * * *", start=not IS_DEV)
async def actualizar_perfiles():
    actualizar_perfiles_periodicamente()
