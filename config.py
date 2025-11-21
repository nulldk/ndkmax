import os
from dotenv import load_dotenv, dotenv_values

# --- Constantes de configuración ---
load_dotenv()

VERSION = "1.0.0"
IS_DEV = os.getenv("NODE_ENV") == "development"
ROOT_PATH = os.environ.get("ROOT_PATH", "")

PING_URL = os.getenv("ADDON_URL") 
ADDON_URL = os.getenv("ADDON_URL")

TMDB_KEY = os.getenv("TMDB_KEY")
URL_BASE = os.getenv("URL_BASE")
APP_KEY = os.getenv("APP_KEY")
AUTH_STR = os.getenv("AUTH_STR")

# Perfiles
PERFILES = {key: value for key, value in os.environ.items() if key.startswith("PERFIL")}
