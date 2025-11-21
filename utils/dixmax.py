import httpx

import state
from config import URL_BASE, APP_KEY, AUTH_STR

class Perfil:
    def __init__(self, credenciales: str):
        self.credenciales = credenciales      # "mail:pass"
        self.username, self.password = credenciales.split(":")
        self.sid = None
        self.valido = False

        self._login()

        self.usage_counter = 0 

    def _login(self):
        login_url = f"{URL_BASE}/get/login/{APP_KEY}"
        data = {"username": self.username, "password": self.password}
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        resp = httpx.post(login_url, data=data, headers=headers)

        if resp.status_code != 200:
            return

        try:
            self.sid = resp.json()["result"]["sid"]
            self.valido = True
        except KeyError:
            self.valido = False


class GestorPerfiles:
    def __init__(self,  instancias: dict):
        # lista de perfiles válidos
        self.instancias = list(instancias.values())
        self.index = 0

    def siguiente(self) -> Perfil:
        if not self.instancias:
            raise RuntimeError("No hay perfiles válidos")
        perfil = self.instancias[self.index]
        self.index = (self.index + 1) % len(self.instancias)
        perfil.usage_counter += 1
        return perfil


async def obtener_enlace(client, media_id: str, is_movie: bool, season=0, episode=0):
    if state.gestor is None:
        logger.error("El gestor de perfiles no está inicializado en state.")
        return []

    perfil = state.gestor.siguiente()
    sid = perfil.sid
    tipo = 0 if is_movie else 1

    url = f"{URL_BASE}/get/hash_link_v5/{APP_KEY}/{sid}/{tipo}/{media_id}"
    data = {"auth": AUTH_STR, "season": season, "episode": episode}

    resp = await client.post(url, json=data)
    if resp.status_code == 200:
        data = resp.json().get("data", [])
        return data if isinstance(data, list) else [data]
    return []
